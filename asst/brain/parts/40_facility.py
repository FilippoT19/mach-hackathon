# PART: 40_facility.py — STRUTTURE (ospedale, specialista, consultorio): hold, commit, check-in, referto
# Non è un modulo a sé: seats.py unisce i file di parts/ in ordine nel brain finale.
# --- facility ----------------------------------------------------------------------------------


def _facility_turn(message: Message) -> bool:
    head = first_word(message.text)
    kind = words(message.text)
    if message.sender == LEDGER and head in {"held", "committed", "checked_in", "reported"}:
        return True
    if message.sender == LEDGER and head == "refused" and "hold" in kind:
        return True
    if "checkin" in kind and message.sender.startswith("citizen:"):
        return True
    return "confirm" in kind and (
        message.sender.startswith("agent:") or message.sender.startswith("citizen:")
    )


async def _family(city: City, message: Message, chat: list[Message]) -> None:
    if _facility_turn(message):
        await _facility(city, message, chat, reports=False, hold_self=True)
        return
    await _desk(city, message, chat, hold_self=True, fixed="CONS-GIN")


async def _facility(
    city: City,
    message: Message,
    chat: list[Message],
    *,
    reports: bool,
    hold_self: bool,
) -> None:
    head = first_word(message.text)
    kind = words(message.text)
    if message.sender == LEDGER and head == "held":
        await _on_held(city, message, chat)
    elif message.sender == LEDGER and head == "committed":
        await _on_committed(city, message, chat)
    elif message.sender == LEDGER and head == "refused" and "hold" in kind:
        await _on_refused(city, message, chat, hold_self=hold_self)
    elif message.sender == LEDGER and head == "checked_in":
        await _checkin_gate(
            city, message, chat, lambda fresh: _on_checked_in(city, message, fresh, reports=reports)
        )
    elif message.sender == LEDGER and head == "reported":
        await _on_reported(city, message, chat)
    elif "checkin" in kind and message.sender.startswith("citizen:"):
        await _checkin_gate(
            city, message, chat, lambda fresh: _on_checkin(city, message, fresh, reports=reports)
        )
    elif "confirm" in kind:
        await _on_confirm(city, message, chat, hold_self=hold_self)
    elif message.sender == LEDGER:
        # FA-13: a refusal is plain language with no act word. It may come as its own turn.
        await _checkin_gate(city, message, chat, lambda fresh: _on_checkin_reply(city, message, fresh))
    elif message.sender.startswith("citizen:") and role_of() == "hospital":
        await _hospital_text(city, message, chat, reports=reports)


def _booking_of(chat: list[Message], agent: str, slot_id: str) -> tuple[str, str, str | None]:
    """Who asked us to book this slot, the consent, and the prescription, if we have them."""

    token = f"slot_id={slot_id}"
    sender = ""
    consent = ""
    number: str | None = None
    for row in chat:
        if token not in row.text.split():
            continue
        fields = _line_fields(row.text, token)
        if "confirm" in words(row.text) and row.sender not in (LEDGER, agent):
            sender = row.sender
            consent = fields.get("consent_ref", consent)
            number = fields.get("prescription_number") or number
        if row.sender == agent and "hold" in words(row.text):
            consent = fields.get("consent_ref", consent)
            number = fields.get("prescription_number") or number
            sender = sender or fields.get("citizen", "")
    return sender, consent, number


def _hold_slot(chat: list[Message], agent: str, hold_id: str) -> str:
    token = f"hold_id={hold_id}"
    for row in chat:
        if token in row.text.split() and (row.sender == agent or row.sender == LEDGER):
            slot = _line_fields(row.text, token).get("slot_id", "")
            if slot:
                return slot
    return ""


def _our_commit(chat: list[Message], agent: str, hold_id: str) -> bool:
    """A commit we actually sent. The ledger's held line also contains the word commit."""

    token = f"hold_id={hold_id}"
    for row in chat:
        if row.sender != agent or row.recipient != LEDGER:
            continue
        if row.text.strip().startswith("commit ") and token in row.text.split():
            return True
    return False


def _latest_hold(chat: list[Message], agent: str) -> tuple[str, str | None]:
    consent = ""
    number: str | None = None
    for row in chat:
        if row.sender != agent or not row.text.strip().startswith("hold "):
            continue
        fields = fields_of(row.text)
        consent = fields.get("consent_ref", consent)
        number = fields.get("prescription_number") or number
    return consent, number


async def _finish_booking(
    city: City, message: Message, chat: list[Message], slot: str, *, hold_self: bool
) -> None:
    """Hold is in the mailbox. Read the held line and commit before this turn ends."""

    found = await _await_line(city, message.need_id, chat, "held", f"slot_id={slot}", op="hold")
    if found is None:
        _LOG.info("care.held.missing", extra={"need_id": (message.need_id or "")[:48]})
        return
    reply, fresh = found
    if first_word(reply.text) == "refused":
        await _on_refused(city, reply, fresh, hold_self=hold_self)
        return
    await _on_held(city, reply, fresh)
    hold_id = fields_of(reply.text).get("hold_id", "")
    if not hold_id:
        return
    done = await _await_line(
        city, message.need_id, fresh, "committed", f"booking_id={hold_id}", op="commit"
    )
    if done is None:
        _LOG.info("care.commit.missing", extra={"need_id": (message.need_id or "")[:48]})
        return
    reply, fresh = done
    if first_word(reply.text) == "committed":
        await _on_committed(city, reply, fresh)
        return
    if first_word(reply.text) == "refused":
        await _on_refused(city, reply, fresh, hold_self=hold_self)


async def _on_held(city: City, message: Message, chat: list[Message]) -> None:
    fields = fields_of(message.text)
    hold_id = fields.get("hold_id", "")
    slot = fields.get("slot_id", "")
    if not hold_id or not slot:
        _LOG.info("care.held.skip", extra={"head": first_word(message.text)[:40]})
        return
    if _our_commit(chat, city.agent_id, hold_id):
        return
    _, consent, number = _booking_of(chat, city.agent_id, slot)
    if not consent:
        consent, held_number = _latest_hold(chat, city.agent_id)
        number = number or held_number
    need = fields.get("need_id", "")
    if not consent and need.startswith("N-"):
        # The citizen's booking consent is cons-<need_id>-booking. The held line does not
        # echo the real ref, and the hold that carried it may not be in this page of history.
        consent = f"cons-{need}-booking"
    if not consent:
        _LOG.info("care.held.noconsent", extra={"need_id": need[:48]})
        return
    parts = [
        "commit",
        f"hold_id={hold_id}",
        f"consent_ref={consent}",
        f"fence={fields.get('fence', '1')}",
    ]
    if number:
        parts.append(f"prescription_number={number}")
    await _say(city, LEDGER, " ".join(parts))


async def _on_committed(city: City, message: Message, chat: list[Message]) -> None:
    fields = fields_of(message.text)
    booking_id = fields.get("booking_id", "")
    ledger_ref = fields.get("ledger_ref", "")
    if not booking_id or not ledger_ref:
        return
    slot = fields.get("slot_id") or _hold_slot(chat, city.agent_id, fields.get("hold_id", ""))
    sender, _, _ = _booking_of(chat, city.agent_id, slot) if slot else ("", "", None)
    target = sender or _citizen(chat)
    if not target:
        return
    token = f"booking_id={booking_id}"
    if _we(chat, city.agent_id, token, to=target, word="booking.receipt"):
        return
    await _say(city, target, f"booking.receipt booking_id={booking_id} ledger_ref={ledger_ref}")


async def _on_refused(
    city: City, message: Message, chat: list[Message], *, hold_self: bool
) -> None:
    agent = city.agent_id
    slot = ""
    for row in chat:
        if row.sender == agent and row.recipient == LEDGER and "hold" in words(row.text):
            slot = fields_of(row.text).get("slot_id", slot)
    if not slot:
        return
    target, _, _ = _booking_of(chat, agent, slot)
    offer_id = ""
    for row in chat:
        if f"slot_id={slot}" in row.text.split():
            offer_id = _line_fields(row.text, f"slot_id={slot}").get("offer_id", offer_id)
    if (
        target
        and offer_id
        and not _we(chat, agent, f"offer_id={offer_id}", to=target, word="cancel")
    ):
        await _say(city, target, f"cancel offer_id={offer_id} reason=facility_cancelled")
    if hold_self:
        await _advance(city, message, chat, fixed="CONS-GIN", replacing=True)


# --- check-in (FA-03, FA-13, FA-14) -------------------------------------------------------------
# A new citizen check-in after a refusal is a new request, not a resend of a 4xx: it is written
# again, at most _CHECKIN_TRIES times per booking. Nothing retries inside one turn. The citizen
# always gets an answer: confirmed, refused with the half-day window, or the booking id asked.
_CHECKIN_TRIES = 3
# Ledger heads that answer something else. Any other Ledger line to us after our checkin is
# its refusal: refusals are plain language with no act word (e19).
_LEDGER_OK = frozenset(
    {
        "checked_in", "held", "committed", "reported", "prescribed", "prescription", "slots",
        "agenda", "world", "rules", "catalogue", "recalled", "remembered", "history",
    }
)
_ARRIVAL = (
    "check-in", "check in", "sono arrivat", "sono qui", "sono in struttura", "arrived",
    "i'm here", "i am here",
)
_CHECKIN_GATES: dict[str, _Gate] = {}


def _checkin_state(
    chat: list[Message], agent: str, booking_id: str
) -> tuple[int, str, Message | None, bool]:
    """Our check-in for ``booking_id``: attempts, outcome, the Ledger line, citizen told after it.

    The outcome is "" (never sent), "pending", "refused" or "done". Done stays done.
    """

    token = f"booking_id={booking_id}"
    attempts = 0
    outcome = ""
    found: Message | None = None
    told = False
    for row in chat:
        if (
            row.sender == agent
            and row.recipient == LEDGER
            and row.text.strip().startswith("checkin ")
            and token in row.text.split()
        ):
            attempts += 1
            if outcome != "done":
                outcome, found, told = "pending", None, False
        elif row.sender == LEDGER and first_word(row.text) == "checked_in" and token in row.text.split():
            if outcome != "done":
                outcome, found, told = "done", row, False
        elif (
            outcome == "pending"
            and row.sender == LEDGER
            and row.recipient in (agent, "")
            and first_word(row.text) not in _LEDGER_OK
        ):
            outcome, found, told = "refused", row, False
        elif found is not None and row.sender == agent and row.recipient.startswith("citizen:"):
            told = True
    return attempts, outcome, found, told


async def _checkin_gate(
    city: City,
    message: Message,
    chat: list[Message],
    run: Callable[[list[Message]], object],
) -> None:
    """One check-in turn per need at a time, on a history read inside the lock."""

    key = message.need_id or message.msg_id
    gate = _CHECKIN_GATES.get(key)
    if gate is None:
        gate = _CHECKIN_GATES[key] = _Gate()
    gate.turns += 1
    try:
        async with gate.lock:
            try:
                fresh = await city.history(need_id=message.need_id)
            except CapError:
                fresh = chat
            if len(fresh) < len(chat):
                fresh = chat
            if all(row.msg_id != message.msg_id for row in fresh):
                fresh = [*fresh, message]
            await run(fresh)
    finally:
        gate.turns -= 1
        if gate.turns == 0 and _CHECKIN_GATES.get(key) is gate:
            del _CHECKIN_GATES[key]


async def _await_checkin(
    city: City, need_id: str | None, chat: list[Message], booking_id: str, attempts: int
) -> tuple[tuple[int, str, Message | None, bool], list[Message]]:
    """Re-read the case until the Ledger answers our ``attempts``-th checkin, or the wait ends."""

    fresh = chat
    for attempt in range(_PULL_TRIES):
        try:
            fresh = await city.history(need_id=need_id)
        except CapError:
            fresh = chat
        state = _checkin_state(fresh, city.agent_id, booking_id)
        if state[1] == "done" or (state[0] >= attempts and state[1] == "refused"):
            return state, fresh
        if attempt + 1 < _PULL_TRIES:
            await asyncio.sleep(_PULL_PAUSE)
    return _checkin_state(fresh, city.agent_id, booking_id), fresh


async def _on_checkin(city: City, message: Message, chat: list[Message], *, reports: bool) -> None:
    agent = city.agent_id
    booking_id = fields_of(message.text).get("booking_id", "")
    citizen = message.sender if message.sender.startswith("citizen:") else _citizen(chat)
    if not citizen:
        return
    if not booking_id:
        # FA-14: an identifier is asked again, never guessed (e19).
        line = await _human(
            city,
            chat,
            "the citizen wants to check in but did not give the booking number; ask for the "
            "booking number written on the receipt",
            "Benvenuto! Per registrare il suo arrivo mi serve il numero di prenotazione "
            "(booking_id) scritto sulla ricevuta: me lo può scrivere?",
        )
        await _say(city, citizen, line)
        return
    attempts, outcome, row, _ = _checkin_state(chat, agent, booking_id)
    if outcome == "done" and row is not None:
        # A resend after success: the citizen did not see the confirmation, so say it again.
        await _on_checked_in(city, row, chat, reports=reports, again=True)
        return
    if attempts >= _CHECKIN_TRIES:
        await _tell_refused(city, chat, citizen, booking_id, row, last=True)
        return
    if not await _say(city, LEDGER, f"checkin booking_id={booking_id} citizen={citizen}"):
        line = await _human(
            city,
            chat,
            "the hospital cannot reach the register right now; the citizen can write again in a "
            "few minutes with the same booking number",
            "In questo momento non riesco a registrare il suo arrivo. Mi riscriva tra qualche "
            "minuto con lo stesso numero di prenotazione.",
        )
        await _say(city, citizen, f"booking_id={booking_id} {line}")
        return
    state, fresh = await _await_checkin(city, message.need_id, chat, booking_id, attempts + 1)
    _, outcome, row, _ = state
    if outcome == "done" and row is not None:
        await _on_checked_in(city, row, fresh, reports=reports, again=True)
    elif outcome == "refused":
        await _tell_refused(city, fresh, citizen, booking_id, row, last=state[0] >= _CHECKIN_TRIES)
    else:
        # The Ledger has not answered yet. Its line may come as its own turn and confirm then.
        _LOG.info("care.checkin.missing", extra={"need_id": (message.need_id or "")[:48]})
        line = await _human(
            city,
            fresh,
            "the hospital sent the check-in to the register and waits for its answer; the "
            "citizen gets the confirmation in a moment",
            "Ho inviato il suo check-in al registro: le confermo appena arriva la risposta.",
        )
        await _say(city, citizen, f"booking_id={booking_id} {line}")


async def _tell_refused(
    city: City,
    chat: list[Message],
    citizen: str,
    booking_id: str,
    row: Message | None,
    *,
    last: bool,
) -> None:
    """The check-in was refused: say why and what to do. No act word, so it is not a check-in."""

    reason = (row.text.strip() if row is not None else "")[:160] or "no reason given"
    if last:
        what = (
            "the check-in could not be registered after several tries (the register said: "
            f"{reason}); ask the citizen to check the booking number on the receipt or to contact "
            "the booking centre, which can verify the booking"
        )
        fallback = (
            "Mi dispiace, non riesco a registrare il check-in con questa prenotazione. Controlli "
            "il numero sulla ricevuta, oppure si rivolga al centro prenotazioni che può verificarla."
        )
    else:
        what = (
            f"the register did not accept the check-in (it said: {reason}); check-in is accepted "
            "only in the half-day of the visit, 08:00-13:00 or 13:00-18:00; if the citizen is "
            "early, they can write again from that time"
        )
        fallback = (
            "Non sono riuscito a registrare il suo arrivo: il check-in si fa nella mezza giornata "
            "della visita (08-13 o 13-18). Se è in anticipo, mi riscriva da quell'ora."
        )
    line = await _human(city, chat, what, fallback)
    await _say(city, citizen, f"booking_id={booking_id} {line}")


async def _on_checkin_reply(city: City, message: Message, chat: list[Message]) -> None:
    """A Ledger line that is no known answer: if it refuses our pending checkin, tell the citizen."""

    agent = city.agent_id
    booking_id = ""
    for row in chat:
        if row.sender == agent and row.recipient == LEDGER and row.text.strip().startswith("checkin "):
            booking_id = fields_of(row.text).get("booking_id", booking_id)
    citizen = _citizen(chat)
    if not booking_id or not citizen:
        return
    attempts, outcome, row, told = _checkin_state(chat, agent, booking_id)
    if outcome != "refused" or row is None or row.msg_id != message.msg_id or told:
        return
    await _tell_refused(city, chat, citizen, booking_id, row, last=attempts >= _CHECKIN_TRIES)


async def _hospital_text(
    city: City, message: Message, chat: list[Message], *, reports: bool
) -> None:
    """FA-15: a citizen writes to the hospital without an act word. Never leave it unanswered."""

    lowered = message.text.lower()
    if any(phrase in lowered for phrase in _ARRIVAL):
        await _checkin_gate(
            city, message, chat, lambda fresh: _on_checkin(city, message, fresh, reports=reports)
        )
        return
    line = await _human(
        city,
        chat,
        "the citizen wrote to the hospital desk (physiatry); on the day of the visit they check "
        "in by writing the booking number from the receipt; to book, move or cancel a visit they "
        "contact the booking centre; the hospital is wheelchair accessible",
        "Qui è l'accettazione dell'ospedale (fisiatria). Il giorno della visita mi scriva il "
        "numero di prenotazione della ricevuta e registro il suo arrivo; per prenotare o spostare "
        "una visita si rivolga al centro prenotazioni. La struttura è accessibile in sedia a rotelle.",
    )
    await _say(city, message.sender, line)


async def _on_checked_in(
    city: City, message: Message, chat: list[Message], *, reports: bool, again: bool = False
) -> None:
    fields = fields_of(message.text)
    booking_id = fields.get("booking_id", "")
    citizen = _citizen(chat)
    if not booking_id:
        return
    token = f"booking_id={booking_id}"
    if reports and not _we(chat, city.agent_id, token, to=LEDGER, word="report"):
        await _say(city, LEDGER, f"report booking_id={booking_id} outcome_code=VISIT")
    if citizen and (again or not _we(chat, city.agent_id, token, to=citizen, word="checkin")):
        # FA-03: answer with the register's values (e19), copied from the Ledger line.
        values = " ".join(
            f"{key}={value}"
            for key, value in _line_fields(message.text, token).items()
            if key != "booking_id"
        )
        if role_of() == "hospital":
            what = (
                "the citizen has checked in at the hospital; the doctor will see them shortly; "
                "the building is wheelchair accessible"
            )
            fallback = (
                "Check-in registrato, benvenuto. Il medico la riceve a breve; la struttura è "
                "accessibile anche in sedia a rotelle."
            )
        else:
            what = "the citizen has checked in at the facility; the doctor will see them shortly"
            fallback = "Check-in registrato, benvenuto. Il medico la riceve a breve."
        line = await _human(city, chat, what, fallback)
        head = f"checkin booking_id={booking_id}" + (f" {values}" if values else "")
        await _say(city, citizen, f"{head} {line}")
    if not reports:
        return
    found = await _await_line(city, message.need_id, chat, "reported", token, op="report")
    if found is None:
        _LOG.info("care.report.missing", extra={"need_id": (message.need_id or "")[:48]})
        return
    reply, fresh = found
    if first_word(reply.text) == "reported":
        await _on_reported(city, reply, fresh)


async def _on_reported(city: City, message: Message, chat: list[Message]) -> None:
    booking_id = fields_of(message.text).get("booking_id", "")
    citizen = _citizen(chat)
    if not booking_id or not citizen:
        return
    token = f"booking_id={booking_id}"
    if _we(chat, city.agent_id, token, to=citizen, word="report"):
        return
    line = await _human(
        city,
        chat,
        "the specialist visit is done and the report is filed; the citizen's GP can read it",
        "La visita è conclusa e il referto è archiviato. Il suo medico di base può consultarlo.",
    )
    await _say(city, citizen, f"report booking_id={booking_id} outcome_code=VISIT {line}")
