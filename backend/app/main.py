from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .agents import orchestrator
from .agents.registry import AGENTS
from .config import settings
from .db import get_session, init_db
from .models import Conversation, Memory, Message, Task, User


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="MACH Hackathon API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)
DB = Depends(get_session)


@app.get("/health")
async def health(db: AsyncSession = DB):
    await db.execute(text("SELECT 1"))
    return {"ok": True, "model": settings.claude_model, "llm_key": bool(settings.anthropic_api_key)}


@app.get("/agents")
async def list_agents():
    return [{"key": a.key, "name": a.name, "description": a.description} for a in AGENTS.values()]


class UserIn(BaseModel):
    name: str
    email: str | None = None
    profile: dict = {}


@app.post("/users")
async def create_user(body: UserIn, db: AsyncSession = DB):
    user = User(name=body.name, email=body.email, profile=body.profile)
    db.add(user)
    await db.commit()
    return {"id": user.id, "name": user.name}


@app.get("/users/{user_id}/dashboard")
async def dashboard(user_id: str, db: AsyncSession = DB):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "user not found")
    tasks = (await db.scalars(select(Task).where(Task.user_id == user_id))).all()
    mems = (await db.scalars(select(Memory).where(Memory.user_id == user_id))).all()
    return {
        "user": {"id": user.id, "name": user.name, "profile": user.profile},
        "tasks": [{"id": t.id, "title": t.title, "status": t.status, "due_at": t.due_at,
                   "agent": t.agent} for t in tasks],
        "memories": [{"content": m.content, "agent": m.agent} for m in mems],
    }


class ChatIn(BaseModel):
    user_id: str
    message: str
    conversation_id: str | None = None
    agent: str | None = None  # force a specialist; otherwise the router decides


@app.post("/chat")
async def chat(body: ChatIn, db: AsyncSession = DB):
    user = await db.get(User, body.user_id)
    if not user:
        raise HTTPException(404, "user not found")
    if body.agent and body.agent not in AGENTS:
        raise HTTPException(400, f"unknown agent {body.agent}")

    if body.conversation_id:
        conv = await db.get(Conversation, body.conversation_id)
        if not conv or conv.user_id != user.id:
            raise HTTPException(404, "conversation not found")
    else:
        conv = Conversation(user_id=user.id, title=body.message[:80])
        db.add(conv)
        await db.flush()

    past = (await db.scalars(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    )).all()
    history = [{"role": m.role, "content": m.content} for m in past][-30:]

    kw = dict(db=db, user_id=user.id, user_profile=user.profile, history=history,
              user_msg=body.message)
    reply = (await orchestrator.run_agent(body.agent, **kw) if body.agent
             else await orchestrator.handle_turn(**kw))

    db.add(Message(conversation_id=conv.id, role="user", content=body.message))
    db.add(Message(conversation_id=conv.id, role="assistant", agent=reply.agent,
                   content=reply.text))
    await db.commit()
    return {"conversation_id": conv.id, "agent": reply.agent, "reply": reply.text}


@app.get("/places")
async def places(category: str, near: str = "", neighbourhood: str = "", query: str = "",
                 limit: int = 10, db: AsyncSession = DB):
    """Same search the agents use (handy for maps in the UI)."""
    import json as _json

    from .agents.tools import _find_places

    tool = _find_places(db, "", "api")
    out = await tool.call({"category": category, "near": near, "neighbourhood": neighbourhood,
                           "query": query, "limit": limit})
    try:
        return _json.loads(out)
    except ValueError:
        raise HTTPException(400, out)


@app.get("/places/categories")
async def place_categories():
    from .opendata import CATEGORIES

    return CATEGORIES
