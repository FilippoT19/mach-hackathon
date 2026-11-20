"""Router -> specialist pipeline.

1. The router (structured output, low effort) picks which specialist handles the turn.
2. The specialist runs an agentic tool loop (SDK tool runner) with the user's history.
"""
from dataclasses import dataclass
from typing import Literal

import anthropic
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from .registry import AGENTS
from .tools import build_tools

FALLBACK_BETA = "server-side-fallback-2026-07-01"
_client: anthropic.AsyncAnthropic | None = None


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY
    return _client


class Route(BaseModel):
    agent: Literal[tuple(AGENTS.keys())]  # type: ignore[valid-type]
    reason: str


@dataclass
class AgentReply:
    agent: str
    text: str


async def route(history: list[dict], user_msg: str) -> Route:
    catalog = "\n".join(f"- {a.key}: {a.description}" for a in AGENTS.values())
    recent = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-6:])
    resp = await client().beta.messages.parse(
        model=settings.claude_model,
        max_tokens=1024,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": settings.router_effort},
        system=f"Pick the single best agent for the user's latest message.\nAgents:\n{catalog}",
        messages=[{
            "role": "user",
            "content": f"Recent conversation:\n{recent or '(none)'}\n\nLatest message:\n{user_msg}",
        }],
        output_format=Route,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        return Route(agent="general", reason="router fallback")
    return resp.parsed_output


async def run_agent(
    agent_key: str, *, db: AsyncSession, user_id: str, user_profile: dict,
    history: list[dict], user_msg: str,
) -> AgentReply:
    spec = AGENTS[agent_key]
    system = spec.system + f"\n\nKnown user profile (JSON): {user_profile or {}}"
    runner = client().beta.messages.tool_runner(
        model=settings.claude_model,
        max_tokens=16000,
        max_iterations=10,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": settings.agent_effort},
        system=system,
        tools=build_tools(spec.tools, db=db, user_id=user_id, agent=spec.key),
        messages=[*history, {"role": "user", "content": user_msg}],
    )
    final = await runner.until_done()
    if final.stop_reason == "refusal":
        return AgentReply(spec.key, "Sorry, I can't help with that request.")
    text = "".join(b.text for b in final.content if b.type == "text").strip()
    return AgentReply(spec.key, text or "(no answer)")


async def handle_turn(**kw) -> AgentReply:
    r = await route(kw["history"], kw["user_msg"])
    return await run_agent(r.agent, **kw)
