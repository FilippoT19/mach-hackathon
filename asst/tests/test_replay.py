"""Replay tests: real booking journeys from the team console, played against the brain.

Each test rebuilds one journey that failed (or scored low) in production: the citizen's own
first words, the Ledger, our hospital and specialist (real brain) and the partner ASSTs with the
reply formats they really used. The citizen is the city's citizen as seen in the transcripts:
it confirms the first offer inside its answer set S (language, deadline counted from the
prescription, not in the past) and cancels every other offer with a reason.

What differs from tests/test_journey.py:
  * Ledger replies land in the case history and open NO turn (production: "the push may never
    arrive"). A booking desk that waits for the push stays silent for ever.
  * history() is the agent's own mailbox for the need, with real ``sent_at`` times.
  * two clocks: one real second is one agenda minute (kit e19: 60x).

Every replay checks the same outcome: language, a cap on messages, no citizen message left
without an answer, and exactly one final outcome.

    ~/.local/share/uv/tools/city-cli/bin/python tests/test_replay.py
"""
import asyncio
import importlib.util
import os
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from city_sdk.city import LEDGER, CapError, CivicAddress, Message, Peer

HERE = Path(__file__).resolve().parent.parent
# REPLAY_BRAIN=/path/to/an/older/agent.py shows how that brain fails the same journeys.
spec = importlib.util.spec_from_file_location("brain", os.environ.get("REPLAY_BRAIN") or HERE / "brain" / "agent.py")
brain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brain)
brain._PULL_TRIES = 2
brain._PULL_PAUSE = 0.0

GP, BK, HOS, SPEC = "agent:fddgaqmp6kb0", "agent:fn64xfq2jft4", "agent:jdj692g4145e", "agent:jmjfst55vgjz"
ROLE = {BK: "booking_centre", HOS: "hospital", SPEC: "specialist_care"}
DOORS = {GP: (45.5120, 9.1900, "Via Ornato 1", "gp"), BK: (45.5130, 9.1880, "Piazza Ospedale Maggiore 3", "booking_centre"),
         HOS: (45.5155, 9.1835, "Via Arganini Gerolamo 38", "hospital"),
         SPEC: (45.5106, 9.1867, "Viale Ca' Granda 28", "specialist_care")}
UTC = timezone.utc
# The city's registry as the citizen knows it (kit: the same doctors in every ASST).
DOCTOR = {"h1": ({"it", "en"}, ("mon", "tue", "wed")), "h2": ({"it"}, ("wed", "thu", "fri")),
          "h3": ({"it"}, ("tue", "thu")), "s1": ({"it", "en"}, ("mon", "wed", "fri")), "s2": ({"it"}, ("tue", "thu"))}
RARE = {"niguarda": "vi", "nord": "ur", "giambellino": "ka", "ortica": "wo", "greco": "si", "corvetto": "fr"}
OF_PROC = {"VIS-FIS": (HOS, ("h1", "h2", "h3"), "hospital.physiatry"),
           "VIS-CARD": (SPEC, ("s1", "s2"), "specialist_care.cardiology")}
HOURS = ("10:30", "12:00", "14:30", "16:00")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WAVE = "W01QQQ"
PUSH = False  # True: every Ledger reply also opens a turn (the other half of production)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def speaks(doctor_id: str, lang: str) -> bool:
    asst, key = doctor_id.removeprefix("asst-").rsplit("-", 1)
    langs, _ = DOCTOR.get(key, (set(), ()))
    return lang in langs or (key == "h3" and RARE.get(asst) == lang)


def slot_line(asst: str, key: str, when: datetime, facility: str, procedure: str) -> str:
    sid = f"{WAVE}-asst-{asst}-{key}-{when:%Y%m%d-%H%M}"
    return (f"slot_id={sid} doctor_id=asst-{asst}-{key} facility={facility} procedure={procedure} "
            f"at={iso(when)} day={DAYS[when.weekday()]}")


def offer_text(asst: str, key: str, when: datetime, facility: str, procedure: str, *, prefix="of-", extra="") -> str:
    sid = f"{WAVE}-asst-{asst}-{key}-{when:%Y%m%d-%H%M}"
    return (f"offer offer_id={prefix}{sid} slot_id={sid} doctor_id=asst-{asst}-{key} facility={facility} "
            f"procedure={procedure} agenda_date={iso(when)} agenda_day={DAYS[when.weekday()]} expiry={iso(when)}"
            + (f" {extra}" if extra else ""))


class Partner:
    """Another ASST's facility. ``offers`` is a list of (doctor key, datetime); ``style`` is the
    real reply format of that team; ``on_confirm`` is 'receipt', 'cancel' or 'silent'."""

    def __init__(self, asst, agent_id, offers, *, style="plain", on_confirm="receipt", reason=""):
        self.asst, self.agent_id, self.offers = asst, agent_id, offers
        self.style, self.on_confirm, self.reason = style, on_confirm, reason
        self.confirms: list[str] = []

    def reply(self, f: dict[str, str]) -> list[str]:
        rid, proc = f.get("request_id", ""), f.get("procedure", "VIS-FIS")
        if self.style == "none":  # journeys 0147, 0093: "cancel offer_id=none"
            return [f"cancel offer_id=none reason=no_availability request_id={rid}"]
        if self.style == "silent":
            return []
        rows = []
        for key, when in self.offers:
            extra = f"request_id={rid}"
            if self.style == "nord":  # doctor_lang, no priority
                langs = "/".join(sorted(DOCTOR[key][0] | ({RARE[self.asst]} if key == "h3" and self.asst in RARE else set())))
                extra = f"doctor_lang={langs} doctor_gender=m request_id={rid}"
            elif self.style in ("barona", "baggio", "lorenteggio"):
                extra = f"priority=B request_id={rid}"
            rows.append(offer_text(self.asst, key, when, self.agent_id, proc, extra=extra,
                                   prefix="po-" if self.style == "lorenteggio" else "of-"))
        if self.style == "barona":  # one message per offer
            return rows
        tail = {"baggio": ["Ecco i posti liberi della nostra struttura: confermate quello scelto dal cittadino e lo blocchiamo subito."],
                "lorenteggio": ["Collega, questi sono i nostri orari liberi per la sua richiesta: ci mandi la conferma con consent_ref."],
                "bovisa": ["info Per prenotare: confirm offer_id=<uno dei precedenti> slot_id=<suo slot> citizen=<id cittadino> consent_ref=<consenso del cittadino>."]}
        return ["\n".join(rows + tail.get(self.style, []))]

    def confirm(self, f: dict[str, str]) -> str:
        self.confirms.append(f.get("slot_id", ""))
        if self.on_confirm == "cancel":
            return "cancel offer_id=" + f.get("offer_id", "") + (f" reason={self.reason}" if self.reason else "")
        if self.on_confirm == "silent":
            return ""
        return f"booking.receipt booking_id=bk-{f.get('slot_id', '')[-13:]} ledger_ref=L-{self.asst} slot_id={f.get('slot_id', '')}"


class Sim:
    """One journey: mailbox, two clocks, Ledger, our facilities, partners and the citizen."""

    def __init__(self, need: str, *, lang: str, procedure: str, agenda: str, first: str, priority: str = "B",
                 rx_age_min: float = 0.2, partners: list[Partner] | None = None, taken: set[str] | None = None,
                 cross: str = "ref", refuse_hold: set[str] | None = None, page_size: int = 10,
                 extra_token: str = "", disability: str = "none", push: bool | None = None,
                 lost_pages: set[int] | None = None):
        self.need, self.lang, self.procedure, self.priority = need, lang, procedure, priority
        self.citizen = f"citizen:{WAVE}-12-{need[-6:]}"
        self.rx = f"prescription_number-{need}"
        self.real = datetime(2026, 11, 21, 0, 15, 0, tzinfo=UTC)
        self.agenda0 = datetime.fromisoformat(agenda.replace("Z", "+00:00"))
        self.real0 = self.real
        self.partners = {p.agent_id: p for p in (partners or [])}
        self.taken, self.cross, self.refuse_hold = taken or set(), cross, refuse_hold or set()
        self.page_size, self.push, self.disability = page_size, PUSH if push is None else push, disability
        self.log: list[Message] = []
        self.queue: deque[Message] = deque()
        self.errors: list[str] = []
        self.n = 0
        self.chosen: str | None = None
        self.outcome: list[str] = []
        self.ledger_asks: list[str] = []
        self.holds: dict[str, str] = {}
        self.lost_pages = lost_pages or set()
        # The GP prescribed rx_age_min real minutes ago and told the booking centre (X-27).
        issued_real = self.real - timedelta(minutes=rx_age_min)
        self.issued = self.agenda_at(issued_real)
        self.deadline = self.issued + timedelta(days={"B": 2, "D": 5}.get(priority, 3650))
        pref = f" lang={lang}" if lang != "it" else ""
        self.post(GP, BK, f"referral prescription_number={self.rx} procedure={procedure} priority={priority}{pref}", at=issued_real)
        self.first = (f"{first} need.request area={{'district':_5}} lang={lang} prescription_number={self.rx} "
                      f"service_type={OF_PROC[procedure][2]}" + (f" {extra_token}" if extra_token else ""))

    # --- clocks -------------------------------------------------------------------------------
    def agenda_at(self, real: datetime) -> datetime:
        return self.agenda0 + (real - self.real0) * 60

    @property
    def agenda(self) -> datetime:
        return self.agenda_at(self.real)

    def wait(self, minutes: float) -> None:
        self.real += timedelta(minutes=minutes)

    # --- mailbox ------------------------------------------------------------------------------
    def post(self, sender: str, to: str, text: str, *, at: datetime | None = None) -> Message:
        self.n += 1
        if at is None:
            self.real += timedelta(seconds=1)
        msg = Message(type="chat", sender=sender, msg_id=f"m{self.n}", need_id=self.need, recipient=to,
                      body={"text": text}, sent_at=iso(at or self.real))
        self.log.append(msg)
        return msg

    def mailbox(self, agent: str) -> list[Message]:
        return [m for m in self.log if agent in (m.sender, m.recipient)]

    # --- the Ledger ---------------------------------------------------------------------------
    def catalogue(self, procedure: str) -> list[str]:
        facility, doctors, _ = OF_PROC[procedure]
        rows, day = [], self.agenda.replace(hour=0, minute=0, second=0, microsecond=0)
        for d in range(15):
            date = day + timedelta(days=d)
            for hour in HOURS:
                when = date.replace(hour=int(hour[:2]), minute=int(hour[3:]))
                for key in doctors:
                    if DAYS[date.weekday()] in DOCTOR[key][1] and when > self.agenda:
                        line = slot_line("niguarda", key, when, facility, procedure)
                        if brain.fields_of(line)["slot_id"] not in self.taken:
                            rows.append(line)
        return rows

    def ledger(self, agent: str, text: str) -> None:
        f, head = brain.fields_of(text), brain.first_word(text)
        self.ledger_asks.append(text)
        reply = None
        if head == "prescription":
            reply = (f"prescription prescription_number={f['prescription_number']} procedure={self.procedure} "
                     f"priority={self.priority} state=issued")
        elif text.strip() == "agenda":
            reply = f"agenda agenda_now={iso(self.agenda)}"
        elif head == "world":
            rows, size = self.catalogue(f.get("procedure", self.procedure)), self.page_size
            pages = max(1, -(-len(rows) // size))
            page = int(f.get("page", "1"))
            if page in self.lost_pages:
                return  # BK-39: the Ledger never answers this page
            reply = "\n".join([f"slots page={page}/{pages}"] + rows[(page - 1) * size: page * size])
        elif head == "hold":
            if f["slot_id"] in self.refuse_hold:
                reply = f"refused hold reason=NO_CAPACITY slot_id={f['slot_id']}"
            else:
                hold = "bk-" + f["slot_id"].removeprefix(WAVE + "-asst-")  # the real hold id is the booking id
                self.holds[hold] = f["slot_id"]
                reply = f"held hold_id={hold} slot_id={f['slot_id']} need_id={self.need} next=commit"
        elif head == "commit":
            h = f["hold_id"]
            self.taken.add(self.holds.get(h, ""))
            reply = f"committed booking_id={h} hold_id={h} slot_id={self.holds.get(h, '')} ledger_ref=L-{h[-13:]}"
        elif head == "cancel":
            reply = f"cancelled hold_id={f.get('hold_id', '')}"
        if reply is None:
            self.errors.append(f"ledger: no script for {text[:60]!r}")
            return
        msg = self.post(LEDGER, agent, reply)
        if self.push:
            self.queue.append(msg)

    # --- the citizen --------------------------------------------------------------------------
    def in_set(self, f: dict[str, str]) -> str:
        """'' when the offer is inside S, else the citizen's reason to cancel it."""
        when = brain._when(f.get("agenda_date", ""))
        if not speaks(f.get("doctor_id", "asst-x-zz"), self.lang):
            return "lang"
        if when is None:
            return "unknown_slot"
        if when <= self.agenda:
            return "past"
        if when > self.deadline:
            return "deadline"
        return ""

    def say(self, text: str) -> None:
        self.queue.append(self.post(self.citizen, BK, text))

    def citizen_reads(self, msg: Message) -> None:
        text, head, f = msg.text, brain.first_word(msg.text), brain.fields_of(msg.text)
        if head == "offer":
            for line in text.splitlines():
                o = brain.fields_of(line)
                if "offer_id" not in o:
                    continue
                if o.get("waiting_list") == "true":
                    self.outcome.append("waiting_list")
                    continue
                if "slot_id" not in o:
                    self.say("Which slot_id?")
                    continue
                why = self.in_set(o)
                if why:
                    self.say(f"I am sorry, this one is not for me. cancel offer_id={o['offer_id']} reason={why}")
                elif self.chosen is None:
                    self.chosen = o["offer_id"]
                    self.say(f"confirm consent_ref=cons-{self.need}-booking offer_id={o['offer_id']}")
        elif head == "cancel" and "offer_id" in f:
            if f["offer_id"] in ("none", "null", "-"):
                self.say("Which slot_id?")
            elif f["offer_id"] == self.chosen:
                self.chosen = None
        elif head == "consent" and f.get("purpose") == "cross_asst":
            if self.cross == "ref":
                self.say(f"Yes, I agree. consent consent_ref=cons-{self.need}-cross_asst purpose=cross_asst")
            elif self.cross == "data":  # journey 0175
                self.say("data.response purpose=cross_asst")
            elif self.cross == "no":
                self.say("No, I prefer to stay in my ASST.")
        elif head == "consent" and f.get("purpose") == "booking":
            self.say(f"consent consent_ref=cons-{self.need}-booking purpose=booking")
        elif head == "data.request" and f.get("purpose") == "booking":
            self.say(f"data.response address=Via_Ornato_Luigi_65 car=false car_euro_class=none disability={self.disability} purpose=booking")
        elif head == "data.request" and f.get("purpose") == "prescription_renewal":
            self.outcome.append("renewal")
        elif head == "booking.receipt":
            self.outcome.append("booked")

    # --- one agent's view ---------------------------------------------------------------------
    async def run(self) -> "Sim":
        turns = 0
        while self.queue and turns < 200:
            turns += 1
            msg = self.queue.popleft()
            city = _City(self, msg.recipient)
            city.inbound = msg
            try:
                await brain.handle(ROLE[msg.recipient], city, msg, self.mailbox(msg.recipient))
            except Exception as exc:  # a crash is a finding
                self.errors.append(f"{ROLE[msg.recipient]} crashed on {msg.text[:50]!r}: {exc!r}")
        if self.queue:
            self.errors.append("the journey never settles (200 turns)")
        return self

    async def start(self) -> "Sim":
        self.say(self.first)
        return await self.run()

    # --- reading the result -------------------------------------------------------------------
    def to_citizen(self) -> list[Message]:
        return [m for m in self.log if m.sender == BK and m.recipient == self.citizen]

    def offers(self) -> list[dict[str, str]]:
        return [o for m in self.to_citizen() if brain.first_word(m.text) == "offer"
                for o in brain._offer_rows(m.text) if o.get("slot_id")]

    def offer_messages(self) -> list[Message]:
        return [m for m in self.to_citizen() if brain.first_word(m.text) == "offer" and "slot_id=" in m.text]

    def dump(self) -> str:
        who = {LEDGER: "LEDGER", GP: "GP", BK: "BK", HOS: "HOS", SPEC: "SPEC", self.citizen: "CITIZEN"}
        return "\n".join(f"    {m.sent_at[11:19]} {who.get(m.sender, m.sender[-6:]):>7} -> {who.get(m.recipient, m.recipient[-6:]):<7} "
                         + m.text.replace(WAVE + "-asst-", "").replace("\n", " // ")[:230] for m in self.log)


class _City:
    def __init__(self, sim: Sim, agent_id: str):
        self.sim, self.agent_id, self.address, self.inbound = sim, agent_id, "", None

    async def say(self, to, text, *, status=None):
        s = self.sim
        if not 1 <= len(text) <= 2000:
            raise CapError("SCHEMA_INVALID", "text length")
        msg = s.post(self.agent_id, to, text)
        if to == LEDGER:
            s.ledger(self.agent_id, text)
        elif to in ROLE:
            s.queue.append(msg)
        elif to == s.citizen:
            s.citizen_reads(msg)
        elif to in s.partners:
            p, head, f = s.partners[to], brain.first_word(text), brain.fields_of(text)
            replies = p.reply(f) if head == "need.request" else [p.confirm(f)] if head == "confirm" else []
            for reply in replies:
                if reply:
                    s.queue.append(s.post(to, self.agent_id, reply))
        elif to != GP:
            s.errors.append(f"{self.agent_id} wrote to unknown party {to}")
        return msg.msg_id

    async def find(self, query):
        ours = [Peer(agent_id=a, role=r, service=r, district=5, capabilities=(r,),
                     address=CivicAddress(label=label, lon=lon, lat=lat)) for a, (lat, lon, label, r) in DOORS.items()
                if a != self.agent_id]
        theirs = [Peer(agent_id=p.agent_id, role="facility", service="hospital", district=2,
                       capabilities=("hospital.physiatry", "specialist_care.cardiology"),
                       address=CivicAddress(label=f"Via {p.asst} 1", lon=9.2, lat=45.48)) for p in self.sim.partners.values()]
        return ours + theirs

    async def history(self, peer=None, *, need_id=None):
        return self.sim.mailbox(self.agent_id)

    async def llm(self, messages, *, need_id=None):
        raise CapError("KEY_UNKNOWN", "no model in the replay")


# --- the outcome every journey must have -----------------------------------------------------------
_IT_ONLY = ("ecco ", " posti ", " sua ", " lei", "ricetta", "prenotat", "attesa", "grazie", " posso ", "appuntament",
            "struttura", "capito", "dispiace", "nessun")
_FINAL = ("booked", "waiting_list", "renewal")


def verdict(s: Sim, *, lang: str, max_messages: int, outcome: str, max_offer_messages: int = 2) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    mine = s.to_citizen()
    prose = [(m, " " + " ".join(t for t in m.text.lower().split() if "=" not in t) + " ") for m in mine]
    if lang == "it":
        wrong = [m.text[:60] for m, p in prose if brain._guess_lang(p) == "en"]
    else:
        wrong = [m.text[:60] for m, p in prose if any(w in p for w in _IT_ONLY)]
    out.append((f"language: every sentence in '{lang}'", not wrong, f"wrong: {wrong}"))
    out.append((f"at most {max_messages} messages to the citizen", len(mine) <= max_messages, f"sent {len(mine)}"))
    mute = [m.text[:50] for i, m in enumerate(s.log) if m.sender == s.citizen and m.recipient == BK
            and not any(r.sender == BK and r.recipient == s.citizen for r in s.log[i + 1:])]
    out.append(("no silence: every citizen message has an answer after it", not mute, f"unanswered: {mute}"))
    final = [o for o in s.outcome if o in _FINAL]
    out.append((f"one final outcome: {outcome}", final == [outcome], f"got {s.outcome}"))
    bad = [(o["offer_id"][-22:], s.in_set(o)) for o in s.offers() if s.in_set(o)]
    out.append(("no offer outside the citizen's answer set (lang, deadline, past)", not bad, f"{bad}"))
    out.append((f"at most {max_offer_messages} offer message(s)", len(s.offer_messages()) <= max_offer_messages,
                f"{len(s.offer_messages())} offer messages"))
    out.append(("no crash, no unknown party", not s.errors, "; ".join(s.errors)))
    return out


def reset() -> None:
    for name in ("_SENT", "_GATES", "_LANG_OF", "_PREF_BY_RX", "_ANSWERED", "_WHERE_OF", "_RECEIPT_SENT", "_RECEIPTS",
                 "_BOOKED_AT", "_PEERS", "_DOORS", "_ZONES", "_WORLD", "_AGENDA_ROW", "_ASKED_AT"):
        store = getattr(brain, name, None)
        if store is not None:
            store.clear()
    brain._ANSWERED_WHERE.clear()


def at(day: str, hour: str) -> datetime:
    return datetime.fromisoformat(f"2026-11-{day}T{hour}:00+00:00")


def ring() -> list[Partner]:
    """Partners on an agenda Wednesday: Italian and rare-language doctors only."""
    return [
        Partner("nord", "agent:gpr1zqe343gb", [("h3", at("19", "14:30")), ("h3", at("19", "16:00")), ("h2", at("19", "10:30"))], style="nord"),
        Partner("barona", "agent:w2str91zrrbq", [("h3", at("19", "16:00")), ("h2", at("19", "10:30")), ("h2", at("20", "12:00"))], style="barona"),
        Partner("bicocca", "agent:bb01ggxymm05", [("h2", at("19", "10:30"))]),
        Partner("corvetto", "agent:x0vr9rbwpesr", [], style="none"),
        Partner("lambrate", "agent:nanpr5mgm2py", [("h3", at("19", "12:00")), ("h3", at("19", "14:30")), ("h2", at("20", "10:30"))], style="barona"),
        Partner("baggio", "agent:t40mr7xsn2wh", [("h3", at("19", "14:30")), ("h2", at("20", "10:30"))], style="baggio"),
        Partner("bovisa", "agent:bovisa000001", [("h3", at("19", "10:30")), ("h3", at("19", "12:00"))], style="bovisa"),
        Partner("lorenteggio", "agent:tmt0bcv0st1f", [("h3", at("19", "14:30")), ("h2", at("19", "10:30"))], style="lorenteggio"),
    ]


def english_ring(*, est_confirm="receipt") -> list[Partner]:
    """Partners as they answered journeys 0147, 0049 and 0116 on an agenda Monday: h1 (English)
    has slots on Tue/Wed in other ASSTs, mixed with Italian-only doctors."""
    return [
        Partner("nord", "agent:gpr1zqe343gb", [("h3", at("17", "14:30")), ("h3", at("17", "16:00")), ("h1", at("18", "10:30")),
                                               ("h2", at("18", "10:30")), ("h1", at("18", "12:00"))], style="nord"),
        Partner("barona", "agent:w2str91zrrbq", [("h3", at("17", "16:00")), ("h2", at("18", "10:30")), ("h1", at("18", "12:00"))], style="barona"),
        Partner("bicocca", "agent:bb01ggxymm05", [("h2", at("18", "10:30"))]),
        Partner("corvetto", "agent:x0vr9rbwpesr", [], style="none"),
        Partner("lambrate", "agent:nanpr5mgm2py", [("h3", at("17", "12:00")), ("h3", at("17", "14:30")), ("h3", at("17", "16:00")),
                                                   ("h2", at("18", "10:30")), ("h1", at("18", "12:00"))], style="barona"),
        Partner("est", "agent:r8njm9a6c7pv", [("h3", at("17", "12:00")), ("h1", at("17", "14:30")), ("h3", at("17", "14:30"))], style="barona",
                on_confirm=est_confirm),
        Partner("lorenteggio", "agent:tmt0bcv0st1f", [("h3", at("17", "14:30")), ("h1", at("18", "10:30"))], style="lorenteggio"),
    ]


def local_slots(procedure: str, agenda: str) -> list[str]:
    probe = Sim("N-PROBE-000000", lang="it", procedure=procedure, agenda=agenda, first="x")
    return [brain.fields_of(line)["slot_id"] for line in probe.catalogue(procedure)]


def all_local(procedure: str, agenda: str) -> set[str]:
    """Every local slot of the next days already taken by earlier citizens (level 2+)."""
    return set(local_slots(procedure, agenda)[:40])


# --- the replays -----------------------------------------------------------------------------------
async def r01():
    """000180 (L5, 21/11 01:15): Italian, back pain. 'Sto controllando' and then nothing for 15 minutes:
    the next catalogue page only arrives in the history, no push opens a turn. (Page 1 holds only the
    slots of the afternoon, too close to now; the first slot that fits is on page 2.)"""
    agenda = "2026-11-18T15:25:00Z"
    s = await Sim("N-2026-11-02-890912000180", lang="it", procedure="VIS-FIS", agenda=agenda,
                  first="Gentili Signori, la prego di volermi fissare un appuntamento per una visita, in quanto avverto "
                  "dei dolori alla schiena ormai da diverse settimane. Distinti saluti.", page_size=2).start()
    return s, verdict(s, lang="it", max_messages=6, outcome="booked", max_offer_messages=1)


async def r02():
    """000179 (L4, 01:13): Italian, heart. Same silence after 'sto controllando' on cardiology."""
    agenda = "2026-11-18T13:20:00Z"
    s = await Sim("N-2026-11-02-890912000179", lang="it", procedure="VIS-CARD", agenda=agenda,
                  first="Buongiorno, sento il cuore che batte forte da ieri. Vorrei prenotare un controllo.",
                  page_size=2).start()
    return s, verdict(s, lang="it", max_messages=6, outcome="booked", max_offer_messages=1)


async def r03():
    """0001130004 (L3, 01:15): English, back pain. Our English physiatrist (h1) has nothing left inside
    the 2 days: the answer is another ASST, asked and offered in English, with English doctors only."""
    agenda = "2026-11-16T15:15:00Z"
    s = await Sim("N-2026-11-02-8909120001130004", lang="en", procedure="VIS-FIS", agenda=agenda,
                  first="Hello, I need an appointment for my back. English-speaking doctor if possible, please.",
                  taken=all_local("VIS-FIS", agenda), partners=english_ring()).start()
    return s, verdict(s, lang="en", max_messages=8, outcome="booked", max_offer_messages=1)


async def r04():
    """0001420003 (L4, 01:18): lang=am (Amharic). No doctor of ours speaks it: no local scan, and partner
    offers with Italian-only doctors are never forwarded (0001420002: 63 messages, 48 cancels)."""
    s = await Sim("N-2026-11-02-8909120001420003", lang="am", procedure="VIS-FIS", agenda="2026-11-18T12:18:00Z",
                  first="Hello, if it's no trouble, I have some back pain and was hoping to see a doctor who speaks English.",
                  partners=ring()).start()
    out = verdict(s, lang="en", max_messages=5, outcome="waiting_list", max_offer_messages=0)
    pages = [a for a in s.ledger_asks if a.startswith("world")]
    out.append(("no catalogue scan when no local doctor speaks the language", len(pages) <= 1, f"{len(pages)} world reads"))
    return s, out


async def r05():
    """000187 (L5, 01:22): lang=ka (Georgian). Only Giambellino's h3 speaks it: one offer, booked."""
    partners = ring() + [Partner("giambellino", "agent:h6r1v45esk77", [("h3", at("19", "10:30")), ("h2", at("19", "12:00"))])]
    s = await Sim("N-2026-11-02-890912000187", lang="ka", procedure="VIS-FIS", agenda="2026-11-18T12:22:00Z",
                  first="Good morning, my back hurts a lot. I would like a doctor who speaks my language, please.",
                  partners=partners).start()
    return s, verdict(s, lang="en", max_messages=7, outcome="booked", max_offer_messages=1)


async def r06():
    """000175 (L2, 01:05, failed -1): one local offer, confirm, the specialist answers no_capacity; then
    'consent purpose=cross_asst' seven times, each answered 'data.response purpose=cross_asst'."""
    agenda = "2026-11-17T23:05:00Z"
    local = local_slots("VIS-CARD", agenda)
    keep = next(sid for sid in local if "-s2-20261119-1430" in sid)
    s = await Sim("N-2026-11-02-890912000175", lang="it", procedure="VIS-CARD", agenda=agenda,
                  first="Ciao! Sento cuore battere veloce. Vorrei controllo al cuore.", extra_token="priority=B",
                  taken={sid for sid in local[:30] if sid != keep}, refuse_hold={keep}, cross="data",
                  partners=[Partner("gorla", "agent:gorla0000001", [("s1", at("20", "12:00"))])]).start()
    out = verdict(s, lang="it", max_messages=8, outcome="waiting_list", max_offer_messages=1)
    asks = [m for m in s.to_citizen() if brain.first_word(m.text) == "consent" and "purpose=cross_asst" in m.text]
    out.append(("the cross-ASST consent is asked at most twice", len(asks) <= 2, f"asked {len(asks)} times"))
    bare = [m.text for m in s.to_citizen() if brain.first_word(m.text) == "cancel" and len(m.text.split()) <= 3]
    out.append(("a facility cancel reaches the citizen with a sentence", not bare, f"{bare}"))
    return s, out


async def r07():
    """0001660002 (L4, 01:10): 'sto controllando', 16 minutes of silence, the citizen writes again. By then
    16 agenda hours of the 2-day window were gone: both partner offers came back 'reason=deadline'."""
    agenda = "2026-11-18T20:26:00Z"
    s = await Sim("N-2026-11-02-8909120001660002", lang="it", procedure="VIS-CARD", agenda=agenda, rx_age_min=16.5,
                  first="raga, ciao! lowkey ho il cuore a mille e boh, vorrei un controllo, tipo.",
                  taken=all_local("VIS-CARD", agenda),
                  partners=[Partner("gorla", "agent:gorla0000001", [("s1", at("20", "12:00")), ("s1", at("20", "14:30"))]),
                            Partner("nord", "agent:gpr1zqe343gb", [("s2", at("19", "14:30")), ("s1", at("20", "16:00"))])]).start()
    out = verdict(s, lang="it", max_messages=8, outcome="booked", max_offer_messages=1)
    out.append(("no 'reason=deadline' from the citizen", not any("reason=deadline" in m.text for m in s.log), ""))
    return s, out


async def r08():
    """0001110003 (L2, booking 1.0.10, failed -1): partner batch with two slots already past; the citizen
    cancels those and confirms the third in the same second. We sent the waiting list over the confirm,
    then the partner's no_capacity as a bare cancel, and stopped."""
    agenda = "2026-11-18T08:02:00Z"
    partners = [Partner("bovisa", "agent:bovisa000001", [("h3", at("17", "10:30"))]),
                Partner("nord", "agent:gpr1zqe343gb", [("h3", at("17", "16:00")), ("h2", at("18", "10:30"))],
                        on_confirm="cancel", reason="no_capacity"),
                Partner("barona", "agent:w2str91zrrbq", [("h2", at("18", "14:30")), ("h2", at("19", "10:30"))], style="barona")]
    s = await Sim("N-2026-11-02-8909120001110003", lang="it", procedure="VIS-FIS", agenda=agenda,
                  first="Ah, bene, la schiena mi sta salutando da settimane e, sorpresa sorpresa, avrei bisogno di una visita.",
                  extra_token="priority=B", taken=all_local("VIS-FIS", agenda), partners=partners).start()
    return s, verdict(s, lang="it", max_messages=10, outcome="booked", max_offer_messages=2)


async def r09():
    """000147 (L3, failed -1): English, sarcastic. 37 messages: eight partners forwarded one by one,
    Italian-only doctors offered, the confirmed slot cancelled by the partner, no next step."""
    agenda = "2026-11-16T14:27:00Z"
    s = await Sim("N-2026-11-02-890912000147", lang="en", procedure="VIS-FIS", agenda=agenda,
                  first="Another spin on the healthcare roulette wheel for my aching back. Can I *please* see someone "
                  "English-speaking, or is that too much to ask?",
                  taken=all_local("VIS-FIS", agenda), partners=english_ring(est_confirm="cancel")).start()
    out = verdict(s, lang="en", max_messages=10, outcome="booked", max_offer_messages=2)
    out.append(("after the partner's cancel the next offers come once", len(s.offer_messages()) == 2, f"{len(s.offer_messages())}"))
    out.append(("M5 Ca' Granda is not named for a facility of another ASST",
                not any("Ca' Granda" in m.text for m in s.to_citizen()), ""))
    return s, out


async def r10():
    """0001160002 (L3, failed -1): 19 partner replies became 19 offer messages. One message, three offers."""
    agenda = "2026-11-16T10:17:00Z"
    many = english_ring() + [Partner(f"asst{i}", f"agent:partner{i:06d}", [("h1", at("17", "10:30")), ("h3", at("17", "10:30"))],
                                     style=("barona", "baggio", "plain")[i % 3]) for i in range(12)]
    s = await Sim("N-2026-11-02-8909120001160002", lang="en", procedure="VIS-FIS", agenda=agenda,
                  first="Gentlemen, I am writing to request an appointment for a visit for back pain. I would be grateful "
                  "if you could assign me a doctor who speaks English. Best regards.",
                  taken=all_local("VIS-FIS", agenda), partners=many).start()
    out = verdict(s, lang="en", max_messages=7, outcome="booked", max_offer_messages=1)
    out.append(("at most 3 offers in the message", len(s.offers()) <= 3, f"{len(s.offers())} offers"))
    return s, out


async def r11():
    """0001220002 / 0000940002 (failed -1): the consent question was open when the citizen's need.request
    arrived again 32 minutes later. No answer, no_reply. One answer, in English, then the booking."""
    agenda = "2026-11-16T14:24:00Z"
    s = Sim("N-2026-11-02-8909120001220002", lang="en", procedure="VIS-FIS", agenda=agenda,
            first="Hello, I need an appointment for my back. English-speaking doctor if possible, please.",
            extra_token="priority=B", taken=all_local("VIS-FIS", agenda), partners=english_ring(), cross="mute")
    await s.start()
    s.wait(1)
    s.cross = "ref"
    s.say(s.first)
    await s.run()
    return s, verdict(s, lang="en", max_messages=9, outcome="booked", max_offer_messages=1)


async def r12():
    """000182 (L4, booked): the plain path must stay plain. One offer message, receipt, one question
    about the address, one route answer."""
    s = await Sim("N-2026-11-02-890912000182", lang="it", procedure="VIS-CARD", agenda="2026-11-18T11:17:00Z",
                  first="raga, il cuore mi fa tipo boh, extra veloce. lowkey mi servirebbe una visita, fr.").start()
    out = verdict(s, lang="it", max_messages=5, outcome="booked", max_offer_messages=1)
    routes = [m for m in s.to_citizen() if " km " in m.text and brain.first_word(m.text) != "booking.receipt"]
    out.append(("the route answer comes at most once", len(routes) <= 1, f"{len(routes)} route answers"))
    return s, out


async def r13():
    """0000930002 (failed -1): 'Which slot_id?' after a partner's 'cancel offer_id=none' reached the
    citizen; 33 minutes later the same confirm again, and no answer."""
    agenda = "2026-11-16T10:21:00Z"
    s = Sim("N-2026-11-02-8909120000930002", lang="en", procedure="VIS-FIS", agenda=agenda,
            first="Back pain, need a physiatrist. English-speaking doctor, please. Book it.",
            taken=all_local("VIS-FIS", agenda),
            partners=[Partner("corvetto", "agent:x0vr9rbwpesr", [], style="none"),
                      Partner("nord", "agent:gpr1zqe343gb", [("h1", at("17", "10:30"))], style="nord", on_confirm="silent")])
    await s.start()
    out = [("no 'offer_id=none' reaches the citizen", not any("offer_id=none" in m.text for m in s.to_citizen()), ""),
           ("the citizen confirmed the English doctor", s.chosen is not None, f"{s.outcome}")]
    s.wait(3)  # the citizen sends the same confirm again (journeys 0147, 0116, 0093)
    s.say(f"confirm consent_ref=cons-{s.need}-booking offer_id={s.chosen}")
    await s.run()
    mute = [m.text[:40] for i, m in enumerate(s.log) if m.sender == s.citizen and m.recipient == BK
            and not any(r.sender == BK and r.recipient == s.citizen for r in s.log[i + 1:])]
    out.append(("a confirm sent again is never left without an answer", not mute, f"{mute}"))
    out.append(("no crash", not s.errors, "; ".join(s.errors)))
    return s, out


async def r14():
    """000141 (L4, failed -1): lang=am, 47 messages. Brera, Est, Baggio answered without the doctor's
    language and every offer came back 'reason=lang'. Nothing outside S is offered; one waiting list."""
    s = await Sim("N-2026-11-02-890912000141", lang="am", procedure="VIS-FIS", agenda="2026-11-16T09:21:00Z",
                  first="To whom it may concern, I would kindly ask to book a medical appointment for back pain, ideally "
                  "with a physician who speaks my native language. Kind regards.", partners=english_ring()).start()
    out = verdict(s, lang="en", max_messages=5, outcome="waiting_list", max_offer_messages=0)
    out.append(("no cancel from the citizen", not any(m.sender == s.citizen and "cancel" in m.text for m in s.log), ""))
    return s, out


async def r15():
    """000143 (booked +2, review 0/0/0): motor disability, cardiology. The citizen must read how to get
    in with a wheelchair; a repeated data.response gets no second answer."""
    s = Sim("N-2026-11-02-890912000143", lang="it", procedure="VIS-CARD", agenda="2026-11-16T09:23:00Z", disability="motor",
            first="Gentile dottore, ultimamente sento un po' il cuore in subbuglio. Vorrei tanto un controllino, la ringrazio di cuore.")
    await s.start()
    before = len(s.to_citizen())
    s.say("data.response address=Via_Monti_Padre_Pier_Luigi_18D car=false car_euro_class=none disability=motor purpose=booking")
    await s.run()
    out = verdict(s, lang="it", max_messages=6, outcome="booked", max_offer_messages=1)[:2]
    out.append(("one final outcome: booked", s.outcome == ["booked"], f"{s.outcome}"))
    out.append(("a repeated data.response gets at most a short answer, no second route",
                not any(" km " in m.text for m in s.to_citizen()[before:]), ""))
    # X-54: the street is in the city street table, so the distance is from the citizen's own door.
    out.append(("X-54 the distance is from the citizen's street (Via Ornato), not the district",
                any(" km da lei" in m.text for m in s.to_citizen())
                and not any("dalla sua zona" in m.text for m in s.to_citizen()),
                " | ".join(m.text[:160] for m in s.to_citizen() if " km" in m.text)))
    out.append(("accessibility is named for a motor disability",
                any("sedia a rotelle" in m.text or "accessibil" in m.text for m in s.to_citizen()), ""))
    return s, out


async def r16():
    """0000490003 (L2, failed -1): the citizen refuses the other ASST in plain words (kit: a refusal comes
    without the act word). The waiting list follows at once; the question is not asked again."""
    agenda = "2026-11-16T12:25:00Z"
    s = await Sim("N-2026-11-02-8909120000490003", lang="en", procedure="VIS-FIS", agenda=agenda, cross="no",
                  first="I am writing to request a physiatry appointment. I would be grateful if I could be seen by a "
                  "doctor who speaks English.", taken=all_local("VIS-FIS", agenda), partners=english_ring()).start()
    return s, verdict(s, lang="en", max_messages=4, outcome="waiting_list", max_offer_messages=0)


async def r17():
    """000206 (L?, 01:37): 'sto controllando', then the Ledger never sends page 2. BK-39: the citizen
    gets the waiting list in the same turn, once, and nothing is offered blind."""
    agenda = "2026-11-18T15:25:00Z"
    s = await Sim("N-2026-11-02-890912000206", lang="it", procedure="VIS-FIS", agenda=agenda, page_size=2, lost_pages={2},
                  first="Buongiorno, ho mal di schiena da giorni e vorrei prenotare la visita.").start()
    return s, verdict(s, lang="it", max_messages=3, outcome="waiting_list", max_offer_messages=0)


async def r18():
    """000124 / 000166 (P-francesco-34): the partners were asked and never answered; the citizen writes
    again. No second 'I am waiting': the waiting list is the outcome."""
    agenda = "2026-11-16T12:25:00Z"
    s = Sim("N-2026-11-02-890912000124", lang="en", procedure="VIS-FIS", agenda=agenda,
            first="Hello, I have back pain and I need an English-speaking doctor, please.",
            taken=all_local("VIS-FIS", agenda), partners=[Partner("nord", "agent:gpr1zqe343gb", [], style="silent")])
    await s.start()
    s.wait(16)
    s.say(s.first)
    await s.run()
    return s, verdict(s, lang="en", max_messages=5, outcome="waiting_list", max_offer_messages=0)


def warm(s: Sim) -> None:
    """BK-67: an earlier case of this process already read agenda and catalogue from the Ledger."""
    if os.environ.get("REPLAY_COLD"):
        return
    rows, size = s.catalogue(s.procedure), s.page_size
    pages = max(1, -(-len(rows) // size))
    texts = [f"agenda agenda_now={iso(s.agenda)}"] + [
        "\n".join([f"slots page={n}/{pages}"] + rows[(n - 1) * size: n * size]) for n in range(1, pages + 1)]
    brain._remember_ledger([Message(type="chat", sender=LEDGER, msg_id=f"warm{i}", need_id="N-EARLIER", recipient=BK,
                                    body={"text": text}) for i, text in enumerate(texts)], BK)


async def r19():
    """0003250002 (L4, 21/11 05:15): Italian, back pain, B. The Ledger answered the catalogue after ~14
    minutes: 'sto controllando', then the waiting list while 286 slots were acceptable. Here the Ledger
    never answers a catalogue page: the offers come from the memory an earlier case filled (BK-67)."""
    s = Sim("N-2026-11-02-8909120003250002", lang="it", procedure="VIS-FIS", agenda="2026-11-18T15:25:00Z",
            first="Ancora qui, a quanto pare la mia schiena ha deciso di scioperare e non si decide a riprendere servizio.",
            page_size=2, lost_pages=set(range(1, 40)))
    warm(s)
    await s.start()
    out = verdict(s, lang="it", max_messages=6, outcome="booked", max_offer_messages=1)
    first = s.to_citizen()[0].text if s.to_citizen() else ""
    out.append(("BK-67 the first message to the citizen is the offers", brain.first_word(first) == "offer", first[:60]))
    return s, out


async def r20():
    """000351 (L5, 05:15): Italian, knee, D, 'solo in giorni specifici'. Four offers, all on Monday with
    the same doctor, all cancelled. With the remembered pages the first message covers several days."""
    s = Sim("N-2026-11-02-890912000351", lang="it", procedure="VIS-FIS", agenda="2026-11-16T07:00:00Z", priority="D",
            first="Le chiedo cortesemente di volermi indicare la disponibilità per una visita, tenendo presente che "
            "potrei presentarmi solo in giorni specifici.", page_size=3, lost_pages=set(range(1, 40)))
    warm(s)
    await s.start()
    out = verdict(s, lang="it", max_messages=6, outcome="booked", max_offer_messages=1)
    msgs = s.offer_messages()
    days = {o.get("agenda_day") for o in brain._offer_rows(msgs[0].text)} if msgs else set()
    out.append(("BK-67 the first offer message covers at least two days", len(days) >= 2, f"{sorted(d or '' for d in days)}"))
    return s, out


REPLAYS = [r18, r19, r20, r01, r02, r03, r04, r05, r06, r07, r08, r09, r10, r11, r12, r13, r14, r15, r16, r17]


async def main() -> int:
    global PUSH
    only = set(sys.argv[1:])
    failed = 0
    for PUSH in (False, True):
        mode = "Ledger replies also open a turn" if PUSH else "Ledger replies only in the history"
        for replay in REPLAYS:
            if only and replay.__name__ not in only:
                continue
            reset()
            sim, results = await replay()
            bad = [r for r in results if not r[1]]
            print(f"\n=== {replay.__name__} [{mode}]: {(replay.__doc__ or '').strip().splitlines()[0]}")
            if only:
                print(sim.dump())
            for what, ok, why in results:
                print(f"  {'PASS' if ok else 'FAIL'}  {what}" + ("" if ok or not why else f"  ({why})"))
            failed += len(bad)
    print(f"\n{'REPLAY OK' if not failed else f'{failed} check(s) FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
