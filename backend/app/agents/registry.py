"""Specialist agents. Add a new domain = add one AgentSpec here.

When the hackathon theme is announced, rename/replace these to match the
challenge (e.g. "permits", "waste", "school-enrollment", "pharmacy").
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSpec:
    key: str
    name: str
    description: str  # used by the router to pick an agent
    system: str
    tools: list[str] = field(default_factory=list)  # names from tools.TOOL_FACTORIES


COMMON_TOOLS = ["remember", "recall", "create_task", "list_tasks", "update_task"]

_BASE = """You are {name}, one specialist in a team of AI agents that help a citizen
of Milan (Italy) with city and public-service needs. Be concise, concrete and kind. Use the tools to keep
durable state: save facts the user tells you about themselves with `remember`,
check `recall` before asking something you might already know, and track every
request or follow-up as a task. Never invent official rules, deadlines or phone
numbers: say what you don't know and what the user should verify.
Answer in the user's language."""

AGENTS: dict[str, AgentSpec] = {
    a.key: a
    for a in [
        AgentSpec(
            key="general",
            name="Concierge",
            description="Greetings, general questions, anything that fits no other agent, "
            "overview of the user's open tasks across all domains.",
            system=_BASE.format(name="Concierge"),
            tools=COMMON_TOOLS,
        ),
        AgentSpec(
            key="health",
            name="Health Assistant",
            description="Healthcare: booking or tracking medical appointments, prescriptions, "
            "reminders for medication, finding the right service. Not a diagnosis tool.",
            system=_BASE.format(name="Health Assistant")
            + "\nYou are not a doctor: never diagnose. For urgent symptoms tell the user "
            "to call emergency services (112 in the EU).",
            tools=COMMON_TOOLS,
        ),
        AgentSpec(
            key="municipal",
            name="City Hall Assistant",
            description="Comune di Milano services: documents (CIE, residency), permits, "
            "waste collection, reporting issues (potholes, lights), local taxes (TARI), school enrollment.",
            system=_BASE.format(name="City Hall Assistant"),
            tools=COMMON_TOOLS,
        ),
        AgentSpec(
            key="mobility",
            name="Mobility Assistant",
            description="Getting around Milan: public transport (metro, tram, bus), tickets and passes, "
            "bike/scooter sharing, Area B / Area C traffic zones, parking.",
            system=_BASE.format(name="Mobility Assistant"),
            tools=COMMON_TOOLS,
        ),
        AgentSpec(
            key="state",
            name="Public Administration Assistant",
            description="National / state bureaucracy: taxes, pensions, benefits, bonuses, "
            "digital identity (SPID/CIE), INPS, Agenzia delle Entrate style procedures.",
            system=_BASE.format(name="Public Administration Assistant"),
            tools=COMMON_TOOLS,
        ),
    ]
}
