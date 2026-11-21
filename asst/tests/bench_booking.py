"""OPS-11: how long one booking turn lasts when every remote call costs 1 s.

No network, no model. The World of ``test_journey.py`` (scripted Ledger and citizen) with a
city in which ``history``, ``say``, ``find`` and ``llm`` each wait one unit. A Ledger reply
lands in the case history when the ``say`` that asked for it ends. One unit is ``UNIT`` real
seconds; the report is in units (= seconds at 1 s per call). Caches (Index doors, peers) are
empty at the start of each scenario: the worst case, a fresh process.

    ~/.local/share/uv/tools/city-cli/bin/python tests/bench_booking.py           (from asst/)
    ~/.local/share/uv/tools/city-cli/bin/python tests/bench_booking.py --calls   (+ every call)

Each turn prints its total and the remote calls in the order they started; calls with the same
start time ran in parallel.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["CITY_ROLE"] = "booking_centre"

import test_journey as tj  # noqa: E402  (loads the generated brain)
from city_sdk.city import LEDGER, CapError, CivicAddress, Peer  # noqa: E402

brain = tj.brain
brain._PULL_TRIES = 24
brain._PULL_PAUSE = 0.0  # the bench measures remote calls, not the pause between re-reads
UNIT = 0.05
BK, SPEC = tj.BK, tj.SPEC
FAR = ("agent:far-bicocca", "agent:far-lambrate")  # another ASST's facilities (cross-ASST)


class BenchWorld(tj.World):
    """The journey World, plus partner facilities of another ASST and a slot catalogue choice."""

    def __init__(self, citizen: str, need: str, *, local_slots: bool):
        super().__init__(citizen, "it", omit_inbound=False)
        self.local_slots = local_slots
        self.bk_need = need

    def ledger(self, agent, text, need):
        head, f = brain.first_word(text), brain.fields_of(text)
        if head == "world" and not self.local_slots:
            # Only a slot three weeks away: outside the B window, so the desk goes cross-ASST.
            row = (f"slot_id=S-FAR doctor_id=d-s1 facility={SPEC} procedure={f['procedure']} "
                   "at=2026-11-25T09:00:00Z day=wed free=1")
            self.post(LEDGER, agent, "slots page=1/1\n" + row, need)
            return
        super().ledger(agent, text, need)

    def partner(self, sender: str, partner: str, text: str, need: str) -> None:
        f = brain.fields_of(text)
        if brain.first_word(text) != "need.request":
            return
        n = FAR.index(partner) + 1
        self.post(partner, sender, (
            f"offer offer_id=of-X{n} slot_id=X{n} doctor_id=asst-bicocca-h1 facility={partner} "
            f"procedure={f.get('procedure')} agenda_date=2026-11-05T1{n}:00:00Z "
            f"priority={f.get('priority', 'B')} request_id={f.get('request_id')}"), need)


class BenchCity(tj.SimCity):
    """One booking turn: each remote call waits one unit and is written in ``calls``."""

    def __init__(self, world, agent_id, need, t0):
        super().__init__(world, agent_id, need)
        self.t0 = t0
        self.calls: list[tuple[float, float, str]] = []

    async def _cost(self, what: str) -> None:
        start = time.monotonic()
        await asyncio.sleep(UNIT)
        self.calls.append(((start - self.t0) / UNIT, (time.monotonic() - self.t0) / UNIT, what))

    async def say(self, to, text, *, status=None):
        who = tj.name(to) if (to in tj.ROLE or to == LEDGER) else to
        await self._cost(f"say {who}: {brain.first_word(text)}")
        if to in FAR:
            msg = self.world.post(self.agent_id, to, text, self.need)
            self.world.partner(self.agent_id, to, text, self.need)
            return msg.msg_id
        if to in tj.ROLE and to != self.agent_id:
            return self.world.post(self.agent_id, to, text, self.need).msg_id  # no turn opened
        return await super().say(to, text, status=status)

    async def history(self, peer=None, *, need_id=None):
        await self._cost("history")
        return await super().history(peer, need_id=need_id)

    async def find(self, query):
        await self._cost("find")
        ours = await super().find(query)
        far = [Peer(agent_id=a, role="hospital", service="hospital", district=9, capabilities=("hospital",),
                    address=CivicAddress(label=f"Via Lontana {i}", lon=9.21, lat=45.52)) for i, a in enumerate(FAR)]
        return far if "another ASST" in query else [*ours, *far]

    async def llm(self, messages, *, need_id=None):
        await self._cost("llm")
        raise CapError("KEY_UNKNOWN", "no model in the bench")


class Need:
    is_emergency = False


async def turn(world: BenchWorld, label: str, text: str, sender: str = "") -> tuple[str, float, list, list[str]]:
    """``sender`` (the citizen by default) writes ``text`` to the booking centre; one full turn
    through ``brain.main``."""

    msg = world.post(sender or world.citizen, BK, text, world.bk_need)
    world.current = msg.msg_id
    before = len(world.log)
    t0 = time.monotonic()
    city = BenchCity(world, BK, world.bk_need, t0)
    city.inbound = msg
    await brain.main(Need(), city)
    total = (time.monotonic() - t0) / UNIT
    world.queue.clear()  # the bench drives the citizen; its scripted reactions are not replayed
    said = [f"{tj.name(m.sender)} -> {tj.name(m.recipient)}: {m.text}" for m in world.log[before:]
            if m.sender == BK]
    return label, total, sorted(city.calls), said


def offers_to_citizen(world: BenchWorld) -> list[str]:
    return [m.text for m in world.log if m.sender == BK and m.recipient == world.citizen
            and brain.first_word(m.text) == "offer"]


def fresh_world(tag: str, *, local_slots: bool = True) -> BenchWorld:
    for store in (brain._SENT, brain._ANSWERED, brain._PEERS, brain._DOORS, brain._ZONES, brain._WHERE_OF,
                  brain._BOOKED_AT, brain._RECEIPTS, brain._ANSWERED_WHERE, brain._RECEIPT_SENT):
        store.clear()
    need = f"N-BENCH-{tag}"
    w = BenchWorld(f"citizen:bench-{tag}", need, local_slots=local_slots)
    w.post(LEDGER, brain._OUR_AGENTS["gp"], "prescribed prescription_number=prescription_number-RX-B1 "
           f"procedure={'VIS-FIS' if local_slots else 'VIS-CARD'} priority=B patient={w.citizen}", need)
    return w


REQUEST = ("Buongiorno, vorrei prenotare la visita need.request lang=it "
           "prescription_number=prescription_number-RX-B1 service_type=hospital.physiatry")


async def scenarios() -> list[tuple[str, float, list, list[str]]]:
    out = []
    # A. local offers, confirm (BK-57 hold/commit + receipt), address answer
    w = fresh_world("local")
    out.append(await turn(w, "1 need.request -> offerte locali", REQUEST))
    first = brain.fields_of(offers_to_citizen(w)[0].splitlines()[0])
    out.append(await turn(w, "2 confirm -> hold/commit (BK-57)",
                          f"confirm offer_id={first['offer_id']} consent_ref=cons-bench-booking"))
    out.append(await turn(w, "3 data.response -> percorso",
                          "data.response purpose=booking address=Via_Ornato_10 lat=45.519 lon=9.19 "
                          "disability=none car=false"))
    # B. cancel of an offer
    w = fresh_world("cancel")
    await turn(w, "", REQUEST)
    first = brain.fields_of(offers_to_citizen(w)[0].splitlines()[0])
    out.append(await turn(w, "4 cancel offerta", f"cancel offer_id={first['offer_id']} reason=time"))
    # C. cross-ASST with consent
    w = fresh_world("cross", local_slots=False)
    out.append(await turn(w, "5 need.request -> domanda consenso cross", REQUEST))
    out.append(await turn(w, "6 consenso cross -> partner + offerte",
                          "consent purpose=cross_asst consent_ref=cons-bench-cross"))
    offers = [o for o in offers_to_citizen(w) if "cross_asst=true" in o]
    if offers:
        first = brain.fields_of(offers[-1].splitlines()[0])
        out.append(await turn(w, "7 confirm offerta partner",
                              f"confirm offer_id={first['offer_id']} consent_ref=cons-bench-booking"))
        out.append(await turn(w, "8 ricevuta dal partner -> cittadino",
                              f"booking.receipt booking_id=B-{first['slot_id']} ledger_ref=L-{first['slot_id']} "
                              f"slot_id={first['slot_id']} offer_id={first['offer_id']}", sender=first["facility"]))
    return out


def main() -> int:
    rows = asyncio.run(scenarios())
    show_calls, show_text = "--calls" in sys.argv, "--text" in sys.argv
    for label, total, seq, said in rows:
        print(f"{label:<44} {total:5.1f} s  ({len(seq)} chiamate)")
        if show_calls:
            for start, end, what in seq:
                print(f"      t={start:4.1f}-{end:4.1f}  {what}")
        if show_text:
            for line in said:
                print("      > " + line.replace("\n", " | "))
    print(f"{'TOTALE':<44} {sum(r[1] for r in rows):5.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
