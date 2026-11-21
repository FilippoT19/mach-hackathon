# PART: 00_core.py — Avvio, costanti (medici, protocolli, red flag), main e smistamento per ruolo
# Non è un modulo a sé: seats.py unisce i file di parts/ in ordine nel brain finale.
"""Care-protocol example. ``city init`` does not copy this file.

The scaffold brain is ``templates/agent/agent/agent.py``. This one is the full care
protocol (prescribe, offer, hold, commit, check-in, report), one inbound message per
step. The role is ``role`` in ``card.yaml``. Ledger writes are chat to ``city:ledger``;
citizens read the act word and ``key=value`` tokens (ADR-110).
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import math
import os
import re
import time
from collections import OrderedDict
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

from city_sdk.city import LEDGER, CapError, City, Message, Need, OutOfScope, clinical, understood

ROLES = ("booking_centre", "gp", "hospital", "specialist_care", "family_counseling")
_MAX_PAGE = 20  # BK-38 (P-magesh-8): read the whole local catalogue before going cross-ASST
# Four agenda hours is about half a minute of real time at 480x, so a slot is still
# ahead when the citizen decides. One hour was already past by then.
_LEAD = timedelta(hours=4)
# Doctor key (the last segment of doctor_id) -> languages, gender, days. ``*`` is the ASST's
# rare language. The Ledger's slot line names the doctor; it does not repeat this table.
_DOCTORS: dict[str, tuple[frozenset[str], str, frozenset[str]]] = {
    "h1": (frozenset({"it", "en"}), "f", frozenset({"mon", "tue", "wed"})),
    "h2": (frozenset({"it"}), "m", frozenset({"wed", "thu", "fri"})),
    "h3": (frozenset({"it", "*"}), "m", frozenset({"tue", "thu"})),
    "s1": (frozenset({"it", "en"}), "m", frozenset({"mon", "wed", "fri"})),
    "s2": (frozenset({"it"}), "f", frozenset({"tue", "thu"})),
    "c1": (frozenset({"it", "en"}), "f", frozenset({"mon", "tue", "wed", "thu", "fri"})),
}
_PROTOCOLS: dict[str, tuple[str, str]] = {
    "SYM-BACK": ("VIS-FIS", "B"),
    "SYM-KNEE": ("VIS-FIS", "D"),
    "SYM-PALPITATIONS": ("VIS-CARD", "B"),
    "SYM-FOLLOWUP": ("VIS-CARD", "P"),
}
_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("SYM-BACK", ("mal di schiena", "back pain")),
    ("SYM-KNEE", ("ginocchio", "knee")),
    ("SYM-PALPITATIONS", ("cuore che batte", "heart racing", "palpitazion", "palpitation", "batticuore", "heart pounding", "heart beating fast", "heartbeat")),
    ("SYM-FOLLOWUP", ("controllo del cuore", "routine heart check")),
)
_RED_FLAGS = (
    "perdita di forza alle gambe",
    "loss of strength in the legs",
    "dolore al petto",
    "chest pain",
)
_DEADLINE_DAYS = {"B": 2, "D": 5}
_EMERGENCY_NEEDS: set[str] = set()
_EARLY_LLM: dict[str, "asyncio.Task[str | None]"] = {}  # OPS-09: msg_id -> symptom check started early
_RED_FLAGS_MORE = ("sanguinamento abbondante", "heavy bleeding", "non riesco a respirare", "can't breathe", "cannot breathe", "svenut", "fainted")
_RX = re.compile(r"^prescription_number-[A-Z0-9-]{4,40}$")
_LOG = logging.getLogger("care")
# The Relay accepts a ledger reply and then the agent rejects the push, so the reply sits in
# the case history and never opens a turn. Wait briefly and read it back from history.
_PULL_TRIES = 24
_PULL_PAUSE = 0.25
# BK-54: a wait is bounded by the clock, not by the number of tries. Under load one history()
# call takes seconds, so 24 tries became minutes and one booking turn lasted 950-1150 s.
_PULL_SECONDS = 6.0
# The whole search of one turn (catalogue pages) must end well inside the citizen's patience.
_TURN_SECONDS = 40.0
# Needs whose sent offers this process remembers; the oldest is forgotten first.
_SENT_NEEDS = 4096


def role_of() -> str:
    """The role this process serves, from ``CITY_ROLE`` or the card next to the brain."""

    forced = os.environ.get("CITY_ROLE", "").strip()
    if forced in ROLES:
        return forced
    path = os.environ.get("CITY_CARD", "")
    if not path:
        return ""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
    return _card_role(text)


async def main(need: Need, city: City) -> None:
    message = city.inbound
    if message is None:
        return
    # X-40: a clinical question (dose, diagnosis) is never a silent refusal: handle() answers
    # it in words and goes on with the journey (red flag first).
    if getattr(need, "is_emergency", False) is True and message.sender.startswith("citizen:"):
        _EMERGENCY_NEEDS.add(message.need_id or message.msg_id)
    # OPS-08: a message from another agent with no key=value token is not part of any MACH
    # exchange (the deploy conformance probe "visit" is one). End the turn at once: the Relay's
    # custody.ack check waits ~5 s, and a slow remote history read made the turn miss it.
    text = (message.text or "").strip()
    if (not message.sender.startswith("citizen:") and message.sender != LEDGER
            and "=" not in text and text != "__error__"):
        _LOG.info("ops08.skip sender=%s", message.sender[:40])
        return
    # OPS-09: the GP's symptom check (city.llm, up to 4 s) needs only the citizen's text, so it
    # runs while the case history is read instead of after it. _gp() takes the result.
    early = None
    if role_of() == "gp" and message.sender.startswith("citizen:") and text and not _emergency(message):
        early = asyncio.get_running_loop().create_task(
            _llm_symptom(city, message.text, emergency_only=_symptom(message) is not None))
        _EARLY_LLM[message.msg_id] = early
    try:
        case = await city.history(need_id=message.need_id)
        await handle(role_of(), city, message, case)
    finally:
        if early is not None and _EARLY_LLM.pop(message.msg_id, None) is not None:
            early.cancel()


def _asks_address(message: Message) -> bool:
    """True when this turn is a ``data.request`` that names the field ``address``."""

    text = message.text
    if text:
        named = False
        asked = False
        for token in text.split():
            bare = token.strip(".,;:!?()\"'")
            if bare == "data.request":
                named = True
            key, eq, value = bare.partition("=")
            if eq and key == "fields":
                names = {part.strip() for part in value.split(",") if part.strip()}
                asked = asked or "address" in names
        return named and asked
    if message.type != "data.request":
        return False
    raw = message.body.get("fields")
    if isinstance(raw, list):
        return "address" in raw
    if isinstance(raw, str):
        return "address" in {part.strip() for part in raw.replace(",", " ").split() if part.strip()}
    return False


def _own_street(city: City) -> str:
    """This agent's door: the city value, else the street shipped beside the brain."""

    street = getattr(city, "address", "")
    if isinstance(street, str) and street.strip():
        return street.strip()
    env = os.environ.get("CITY_ADDRESS", "").strip()
    if env:
        return env
    path = Path(__file__).with_name("door.txt")
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    # P-magesh-4: no door.txt ships with the image; never answer an empty address.
    door = _DOOR_FALLBACK.get(getattr(city, "agent_id", ""))
    return door[2] if door else ""


async def handle(role: str, city: City, message: Message, chat: list[Message]) -> None:
    street = _own_street(city)
    if street and _asks_address(message):
        await city.say(message.sender, f"address={street}")
        return
    _note_lang(message)  # X-30
    if await _on_emergency_where(city, message, chat):
        return
    if message.sender.startswith("citizen:"):
        # X-41: a red flag is sent to 112 by EVERY role, not only the GP.
        if role != "gp" and _red_flag(message):
            await _escalate(city, message, chat)
            return
        # X-40: clinical question -> a polite line, then the normal path.
        if clinical(message.text) and not _we(chat, city.agent_id, "", to=message.sender, word="scope.note"):
            en = _lang([*chat, message]) != "it"
            await city.say(
                message.sender,
                "scope.note "
                + (
                    "I understand your question. On that I cannot answer myself: the doctor will "
                    "explain it at the visit. Meanwhile I am taking care of your next step now."
                    if en
                    else "Capisco la sua domanda. Su questo non posso risponderle io: glielo "
                    "spiegherà il medico durante la visita. Intanto mi occupo subito del suo percorso."
                ),
            )
    if all(row.msg_id != message.msg_id for row in chat):
        chat = [*chat, message]  # BK-15: the case history can miss the inbound message (all roles)
    if role == "gp":
        await _gp(city, message, chat)
    elif role == "booking_centre":
        await _desk(city, message, chat, hold_self=False, fixed=None)
    elif role == "hospital":
        await _facility(city, message, chat, reports=False, hold_self=False)
    elif role == "specialist_care":
        await _facility(city, message, chat, reports=True, hold_self=False)
    elif role == "family_counseling":
        await _family(city, message, chat)


