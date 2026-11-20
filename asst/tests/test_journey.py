"""End-to-end journey simulator: five of our agents, a scripted Ledger and a scripted citizen.

No network, no model. Every message goes through one in-memory mailbox; a message to one of
our agents opens a new turn via ``brain.handle``. Mode ``bk15`` drops from ``history()`` the
message that opened the running turn (production bug BK-15).

    ~/.local/share/uv/tools/city-cli/bin/python asst/tests/test_journey.py
"""
import asyncio
import importlib.util
import sys
from collections import deque
from pathlib import Path

from city_sdk.city import LEDGER, CapError, CivicAddress, Message, Peer

HERE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("brain", HERE / "brain" / "agent.py")
brain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brain)
brain._PULL_TRIES = 2
brain._PULL_PAUSE = 0.0

GP, BK, HOS, SPEC, FAM = ("agent:fddgaqmp6kb0", "agent:fn64xfq2jft4", "agent:jdj692g4145e",
                          "agent:jmjfst55vgjz", "agent:mm18nddkfc5w")
ROLE = {GP: "gp", BK: "booking_centre", HOS: "hospital", SPEC: "specialist_care", FAM: "family_counseling"}
DOORS = {GP: (45.5120, 9.1900, "Via Ornato 1", "gp"), BK: (45.5130, 9.1880, "Piazza Ospedale Maggiore 3", "booking_centre"),
         HOS: (45.5155, 9.1835, "Via Arganini Gerolamo 38", "hospital"),
         SPEC: (45.5106, 9.1867, "Viale Ca' Granda 28", "specialist_care"),
         FAM: (45.5080, 9.1950, "Via Giolli Raffaello 23", "family_counseling")}
NOW = "2026-11-04T09:00:00Z"  # a Wednesday
FACILITY_OF = {"VIS-FIS": (HOS, "h1"), "VIS-CARD": (SPEC, "s1")}


class World:
    """Shared mailbox, scripted Ledger and scripted citizen for one journey."""

    def __init__(self, citizen: str, lang: str, omit_inbound: bool):
        self.citizen, self.lang, self.omit = citizen, lang, omit_inbound
        self.log: list[Message] = []
        self.queue: deque[Message] = deque()
        self.current: str | None = None  # msg_id of the message that opened the running turn
        self.n = 0
        self.bk_need = ""
        self.facility = ""
        self.errors: list[str] = []

    def post(self, sender: str, to: str, text: str, need: str) -> Message:
        self.n += 1
        msg = Message(type="chat", sender=sender, msg_id=f"m{self.n}", need_id=need, recipient=to,
                      body={"text": text}, sent_at=f"t{self.n:04d}")
        self.log.append(msg)
        return msg

    # --- the Ledger ---------------------------------------------------------------------------
    def ledger(self, agent: str, text: str, need: str) -> None:
        f, head = brain.fields_of(text), brain.first_word(text)
        reply = None
        if head == "prescribe":
            reply = (f"prescribed prescription_number={f['prescription_number']} procedure={f['procedure']} "
                     f"priority={f['priority']} patient={f['patient']}")
        elif head == "prescription" and "prescription_number" in f:
            rx = next((m for m in self.log if m.sender == LEDGER and m.text.startswith("prescribed")
                       and f"prescription_number={f['prescription_number']}" in m.text.split()), None)
            if rx is None:
                reply = f"refused prescription reason=UNKNOWN prescription_number={f['prescription_number']}"
            else:
                g = brain.fields_of(rx.text)
                reply = (f"prescription prescription_number={g['prescription_number']} procedure={g['procedure']} "
                         f"priority={g['priority']} state=issued")
        elif text.strip() == "agenda":
            reply = f"agenda agenda_now={NOW}"
        elif head == "world":
            fac, doc = FACILITY_OF[f["procedure"]]
            rows = [f"slot_id=S-{i} doctor_id=d-{doc} facility={fac} procedure={f['procedure']} at={at} day=wed free=1"
                    for i, at in ((1, "2026-11-04T15:00:00Z"), (2, "2026-11-04T16:00:00Z"))]
            reply = "slots page=1/1\n" + "\n".join(rows)
        elif head == "hold":
            reply = f"held hold_id=H-{f['slot_id']} slot_id={f['slot_id']} need_id={need} next=commit"
        elif head == "commit":
            h = f["hold_id"]
            reply = f"committed booking_id={h} hold_id={h} slot_id={h[2:]} ledger_ref=L-{h}"
        elif head == "checkin":
            reply = f"checked_in booking_id={f['booking_id']}"
        elif head == "report":
            reply = f"reported booking_id={f['booking_id']} outcome_code={f.get('outcome_code', 'VISIT')}"
        if reply is None:
            self.errors.append(f"ledger: no script for {text!r}")
            return
        self.post(LEDGER, agent, reply, need)  # in the case history only: the push opens no turn

    # --- the citizen --------------------------------------------------------------------------
    def citizen_reacts(self, msg: Message) -> None:
        text, f, head = msg.text, brain.fields_of(msg.text), brain.first_word(msg.text)
        if head == "prescription" and "prescription_number" in f and not self.bk_need:
            self.bk_need = msg.need_id + "-BK"
            self.queue.append(self.post(self.citizen, BK, f"need.request lang={self.lang} prescription_number="
                                        f"{f['prescription_number']} area={{'district':_5}}", self.bk_need))
        elif head == "offer" and "offer_id" in f and not any(m.sender == self.citizen and "confirm" in m.text for m in self.log):
            first = brain.fields_of(text.splitlines()[0])
            self.facility = first.get("facility", "")
            self.queue.append(self.post(self.citizen, msg.sender, f"confirm offer_id={first['offer_id']} "
                                        f"consent_ref=cons-{msg.need_id}-booking", msg.need_id))
        elif head == "data.request":
            self.queue.append(self.post(self.citizen, msg.sender, "data.response address=Via_Ornato_10 lat=45.519 "
                                        "lon=9.19 disability=none car=false", msg.need_id))
        elif head == "booking.receipt" and self.facility:
            self.queue.append(self.post(self.citizen, self.facility, f"checkin booking_id={f['booking_id']}", msg.need_id))


class SimCity:
    """One agent's view of the city during one turn."""

    def __init__(self, world: World, agent_id: str, need: str):
        self.world, self.agent_id, self.need, self.address, self.inbound = world, agent_id, need, "", None

    async def say(self, to, text, *, status=None):
        w = self.world
        msg = w.post(self.agent_id, to, text, self.need)
        if to == LEDGER:
            w.ledger(self.agent_id, text, self.need)
        elif to in ROLE:
            w.queue.append(msg)
        elif to == w.citizen:
            w.citizen_reacts(msg)
        else:
            w.errors.append(f"{self.agent_id} wrote to unknown party {to}")
        return msg.msg_id

    async def find(self, query):
        return [Peer(agent_id=a, role=r, service=r, district=5, capabilities=(r,),
                     address=CivicAddress(label=label, lon=lon, lat=lat)) for a, (lat, lon, label, r) in DOORS.items()]

    async def history(self, peer=None, *, need_id=None):
        w = self.world
        return [m for m in w.log if m.need_id == need_id and not (w.omit and m.msg_id == w.current)]

    async def llm(self, messages, *, need_id=None):
        raise CapError("KEY_UNKNOWN", "no model in the simulator")


async def run(world: World, first_text: str, need: str) -> None:
    world.queue.append(world.post(world.citizen, GP, first_text, need))
    turns = 0
    while world.queue and turns < 60:
        turns += 1
        msg = world.queue.popleft()
        world.current = msg.msg_id
        city = SimCity(world, msg.recipient, msg.need_id)
        city.inbound = msg
        chat = await city.history(need_id=msg.need_id)
        try:
            await brain.handle(ROLE[msg.recipient], city, msg, chat)
        except Exception as exc:  # a crash is a finding, not the end of the run
            world.errors.append(f"{ROLE[msg.recipient]} crashed on {msg.text[:40]!r}: {exc!r}")
    world.current = None


def name(party: str) -> str:
    return {LEDGER: "LEDGER", **{a: r.upper() for a, r in ROLE.items()}}.get(party, party)


def checks(w: World) -> list[tuple[str, bool, str]]:
    log, cz = w.log, w.citizen
    out: list[tuple[str, bool, str]] = []
    mute = [m.text[:50] for i, m in enumerate(log) if m.sender == cz and m.recipient in ROLE
            and not any(r.sender == m.recipient and r.recipient == cz for r in log[i + 1:])]
    out.append(("no mute: every citizen message gets a reply", not mute, f"unanswered: {mute}"))
    if w.lang == "en":
        it = []
        for m in log:
            if m.recipient == cz:
                prose = " ".join(t for t in m.text.split() if "=" not in t)
                if brain._guess_lang(prose) == "it":
                    it.append(m.text[:70])
        out.append(("English citizen gets English sentences", not it, f"Italian: {it}"))
    out.append(("GP sends referral to booking", any(m.sender == GP and m.recipient == BK
                and m.text.startswith("referral ") for m in log), ""))
    offers = [m for m in log if m.sender == BK and m.recipient == cz and brain.first_word(m.text) == "offer"]
    out.append(("booking offers in ONE message", len(offers) == 1 and len(brain._offer_rows(offers[0].text)) >= 1,
                f"{len(offers)} offer messages"))
    out.append(("booking.receipt reaches the citizen", any(m.recipient == cz and m.text.startswith("booking.receipt ")
                and "ledger_ref=" in m.text for m in log), ""))
    route = [m for m in log if m.sender == BK and m.recipient == cz and " km " in m.text]
    out.append(("X-31 route message arrives", bool(route), ""))
    out.append(("no simulator errors / crashes", not w.errors, "; ".join(w.errors)))
    return out


JOURNEYS = [
    ("it-back", "it", "Buongiorno dottore, ho mal di schiena da una settimana", "VIS-FIS"),
    ("en-back", "en", "Hello doctor, I have back pain since Monday", "VIS-FIS"),
    ("it-knee", "it", "Salve, mi fa male il ginocchio quando cammino", "VIS-FIS"),
    ("en-knee", "en", "Hi doctor, my knee hurts when I walk", "VIS-FIS"),
    ("it-cuore", "it", "Dottore, sento il cuore che batte forte da ieri", "VIS-CARD"),
    ("en-palp", "en", "Hello doctor, I have palpitations since yesterday", "VIS-CARD"),
]


async def main() -> int:
    failed = 0
    for mode in ("normal", "bk15"):
        for i, (label, lang, text, proc) in enumerate(JOURNEYS):
            brain._SENT.clear()
            w = World(f"citizen:sim-{mode}-{i}", lang, omit_inbound=(mode == "bk15"))
            await run(w, text, f"N-{mode.upper()}-{i}")
            print(f"\n=== {label} [{mode}] expects {proc} ===")
            for m in w.log:
                body = m.text.replace("\n", "\n" + " " * 30)
                print(f"  {name(m.sender):>16} -> {name(m.recipient):<10} {body[:400]}")
            got = next((brain.fields_of(m.text).get("procedure") for m in w.log if m.text.startswith("prescribe ")), None)
            results = [("GP prescribes " + proc, got == proc, f"got {got}")] + checks(w)
            for what, ok, why in results:
                print(f"  {'PASS' if ok else 'FAIL'}  {what}" + ("" if ok or not why else f"  ({why})"))
                failed += not ok
    print(f"\n{'ALL PASS' if not failed else f'{failed} check(s) FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
