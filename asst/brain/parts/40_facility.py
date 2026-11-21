# PART: 40_facility.py — STRUTTURE (ospedale, specialista, consultorio): hold, commit, check-in, referto
# Non è un modulo a sé: seats.py unisce i file di parts/ in ordine nel brain finale.
# --- facility ----------------------------------------------------------------------------------


def _facility_turn(message: Message) -> bool:
    head = first_word(message.text)
    kind = words(message.text)
    if message.sender == LEDGER and head in {"held", "committed", "checked_in", "reported"}:
        return True
    if message.sender == LEDGER and head == "refused" and kind & {"hold", "commit"}:
        return True
    if message.sender.startswith("citizen:") and (
        head == "checkin" or _explicit_arrival(message.text) or "check in" in message.text.lower()
        or "check-in" in message.text.lower()
    ):
        return True
    return (head == "confirm" and message.sender.startswith("citizen:")) or (
        "confirm" in kind and message.sender.startswith("agent:")
    )


async def _family(city: City, message: Message, chat: list[Message]) -> None:
    if _facility_turn(message) or (
        message.sender == LEDGER and _checkin_refused(city.agent_id, message, chat) is not None
    ) or (
        message.sender.startswith("citizen:")
        and first_word(message.text) not in {"need.request", "data.response", "consent", "cancel"}
        and any(
            row.recipient == message.sender and first_word(row.text) in {"booking.receipt", "facility.note"}
            for row in chat
        )
    ):
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
    if head == "emergency.notice" and message.sender.startswith("agent:"):
        # X-28: the gp warns us of a red flag. Answer at once (clock +1), once per need.
        if not _we(chat, city.agent_id, "emergency.ack", to=message.sender, word="emergency.ack"):
            await _say(
                city,
                message.sender,
                "emergency.ack Ricevuto: se il cittadino arriva da noi lo accogliamo subito e lo "
                "accompagniamo al pronto soccorso.",
            )
        return
    if head == "need.request" and message.sender.startswith("agent:"):
        if not _trusted(message.sender):  # X-13: unknown agent, no slots and no data
            if not _we(chat, city.agent_id, "", to=message.sender, word="cancel"):
                rid = fields_of(message.text).get("request_id", "")
                await _say(city, message.sender, f"cancel reason=unknown_partner request_id={rid}")
            return
        await _partner_request(city, message, chat)  # FA-12
        return
    if message.sender.startswith("agent:") and not _ours(message.sender) and not _trusted(message.sender):
        # X-13: an unknown agent never books here, but it always gets an answer (conformance needs an effect).
        if not _we(chat, city.agent_id, "", to=message.sender, word="cancel"):
            await _say(city, message.sender, "cancel reason=unknown_partner Non risultate tra le ASST partner: "
                       "scriveteci con need.request dal vostro centro prenotazioni.")
        return
    if message.sender == LEDGER and head == "held":
        await _on_held(city, message, chat)
    elif message.sender == LEDGER and head == "committed":
        await _on_committed(city, message, chat)
    elif message.sender == LEDGER and head == "refused" and kind & {"hold", "commit"}:
        await _on_refused(city, message, chat, hold_self=hold_self)
    elif message.sender == LEDGER and head == "checked_in":
        await _on_checked_in(city, message, chat, reports=reports)
    elif message.sender == LEDGER and head == "reported":
        await _on_reported(city, message, chat)
    elif message.sender == LEDGER:
        attempt = _checkin_refused(city.agent_id, message, chat)
        if attempt is not None:
            await _answer_checkin_refusal(city, attempt, chat, reason=message.text)
    elif head == "checkin" and message.sender.startswith("citizen:") and (
        "booking_id=" in message.text or not _checkin_question(message.text)
    ):  # P-francesco-12: act checkin + booking_id is always registered, even with a question
        await _on_checkin(city, message, chat, reports=reports)
    elif head == "confirm" or ("confirm" in kind and message.sender.startswith("agent:")):
        await _on_confirm(city, message, chat, hold_self=hold_self)
    elif message.sender.startswith("citizen:"):
        await _facility_free_text(city, message, chat, reports=reports)


_ARRIVED = ("sono arrivat", "sono qui", "sono in struttura", "i am here", "i'm here", "i have arrived")
_RESCHEDULE = ("spost", "annull", "cancel", "cambia", "move", "reschedul")
_CHECKIN_HOURS = "08-13 / 13-18"


def _checkin_question(text: str) -> bool:
    low = text.lower()
    return "?" in low or any(word in low for word in (*_RESCHEDULE, "quando", "when"))


def _explicit_arrival(text: str) -> bool:
    low = text.lower().replace("’", "'")
    return not _checkin_question(low) and any(phrase in low for phrase in _ARRIVED) and not any(
        f"non {phrase}" in low for phrase in _ARRIVED
    )


async def _facility_free_text(city: City, message: Message, chat: list[Message], *, reports: bool) -> None:
    """FA-20: a citizen text that is not a checkin/confirm never gets silence."""
    low = message.text.lower()
    if _explicit_arrival(low):
        number = fields_of(message.text).get("booking_id") or next(
            (booking for r in reversed(chat)
             if first_word(r.text) == "booking.receipt"
             and (r.recipient == message.sender or r.sender == message.sender)
             and (booking := fields_of(r.text).get("booking_id"))),
            "",
        )
        await _on_checkin(city, message, chat, reports=reports, booking_id=number)
        return
    booking_it = "Per prenotare, spostare o annullare una visita, scriva al centro prenotazioni."
    booking_en = "To book, move or cancel a visit, please write to the booking centre."
    hours_it = f"Il check-in si fa nella mezza giornata della visita ({_CHECKIN_HOURS}) con il numero sulla ricevuta."
    hours_en = f"Check-in is during the half-day of your visit ({_CHECKIN_HOURS}) with the number on your receipt."
    facts_it, facts_en = hours_it, hours_en
    if city.agent_id == _OUR_AGENTS["hospital"]:
        street = _own_street(city)
        facts_it = f"L'ospedale è in {street} ed è accessibile in sedia a rotelle. {hours_it}"
        facts_en = f"The hospital is at {street} and is wheelchair accessible. {hours_en}"
    if any(word in low for word in _RESCHEDULE):
        fallback, en = booking_it, booking_en
    elif any(word in low for word in ("check in", "check-in", "checkin")):
        fallback, en = hours_it, hours_en
    else:
        fallback, en = f"{facts_it} {booking_it}", f"{facts_en} {booking_en}"
    line = await _human(
        city,
        [*chat, message],
        f"Answer the citizen's facility question using only these facts: {en}",
        fallback,
        en=en,
    )
    await _say(city, message.sender, f"facility.note {line}")


def _booking_of(chat: list[Message], agent: str, slot_id: str) -> tuple[str, str, str | None]:
    """Who asked us to book this slot, the consent, and the prescription, if we have them."""

    if not slot_id:
        return "", "", None
    token = f"slot_id={slot_id}"
    sender = ""
    consent = ""
    number: str | None = None
    for row in chat:
        if token not in row.text.split():
            continue
        fields = _line_fields(row.text, token)
        if "confirm" in words(row.text) and row.recipient == agent and row.sender not in (LEDGER, agent):
            sender = row.sender
            consent = fields.get("consent_ref", "")
            number = fields.get("prescription_number")
        if row.sender == agent and row.recipient == LEDGER and first_word(row.text) == "hold":
            consent = fields.get("consent_ref", consent)
            number = fields.get("prescription_number") or number
            sender = sender or fields.get("citizen", "")
    return sender, consent, number


def _hold_slot(chat: list[Message], agent: str, hold_id: str) -> str:
    if not hold_id:
        return ""
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


# FA-21 (0308): under load the held line came after the 12 s wait, so no commit left and the hold
# expired 10 minutes later. A hold lives minutes: wait for its line up to this many seconds.
_HOLD_WAIT = 30.0


async def _finish_booking(
    city: City, message: Message, chat: list[Message], slot: str, *, hold_self: bool,
    before: "asyncio.Future | None" = None,
) -> None:
    """Hold is in the mailbox. Read the held line and commit before this turn ends.

    OPS-11: ``before`` is a message to the citizen already on its way (the booking centre's
    address question). It runs while the held line is read and ends before the next message."""

    found = await _await_line(
        city, message.need_id, chat, "held", f"slot_id={slot}", op="hold", seconds=_HOLD_WAIT,
        refusal_matches=lambda row: row.recipient == city.agent_id
        and fields_of(row.text).get("slot_id", slot) == slot,
    )
    if before is not None:
        await before
    if found is None:
        _LOG.info("care.held.missing", extra={"need_id": (message.need_id or "")[:48]})
        return
    reply, fresh = found
    if first_word(reply.text) == "refused":
        await _on_refused(city, reply, fresh, hold_self=hold_self, slot=slot)
        return
    if not await _on_held(city, reply, fresh):
        return
    hold_id = fields_of(reply.text)["hold_id"]
    for _attempt in range(2):  # BK-62: a commit refused for its fence is sent once more
        done = await _await_line(
            city, message.need_id, fresh, "committed", f"booking_id={hold_id}", op="commit", seconds=_HOLD_WAIT,
            refusal_matches=lambda row: row.recipient == city.agent_id
            and fields_of(row.text).get("slot_id", slot) == slot
            and fields_of(row.text).get("hold_id", hold_id) == hold_id,
        )
        if done is None:
            _LOG.info("care.commit.missing", extra={"need_id": (message.need_id or "")[:48]})
            return
        reply, fresh = done
        if first_word(reply.text) == "committed":
            await _on_committed(city, reply, fresh)
            return
        if first_word(reply.text) != "refused" or not await _on_refused(
                city, reply, fresh, hold_self=hold_self, slot=slot, hold_id=hold_id):
            return


async def _on_held(city: City, message: Message, chat: list[Message]) -> bool:
    fields = fields_of(message.text)
    agent = city.agent_id
    hold_id = fields.get("hold_id", "")
    if not hold_id:
        _LOG.info("care.held.skip", extra={"head": first_word(message.text)[:40]})
        return False
    if _we(chat, agent, f"hold_id={hold_id}", to=LEDGER, word="cancel"):
        return False
    if _our_commit(chat, agent, hold_id):
        return True

    slot = fields.get("slot_id") or _hold_slot(chat, agent, hold_id)
    _, consent, number = _booking_of(chat, agent, slot)
    if not consent and slot:
        # A peer-scoped read can find the hold even when the general case history omitted it.
        try:
            ledger_chat = await city.history(LEDGER, need_id=message.need_id)
        except CapError:
            ledger_chat = []
        if ledger_chat:
            _, consent, number = _booking_of(ledger_chat, agent, slot)
    fence = fields.get("fence", "")
    if not consent:
        await _cancel_booking(city, chat, slot, reason="missing_consent_ref", hold_id=hold_id)
        return False
    # P-francesco-13: e19 documents commit without fence; never cancel a valid hold for it.
    parts = ["commit", f"hold_id={hold_id}", f"consent_ref={consent}"] + ([f"fence={fence}"] if fence else [])
    if number:
        parts.append(f"prescription_number={number}")
    return await _say(city, LEDGER, " ".join(parts))


_BOOKING_REQUESTS: OrderedDict[tuple[str, str, str], str] = OrderedDict()


def _remember_booking_request(agent: str, need_id: str | None, slot: str, sender: str) -> None:
    if need_id:
        _BOOKING_REQUESTS[agent, need_id, slot] = sender
        if len(_BOOKING_REQUESTS) > _SENT_NEEDS:
            _BOOKING_REQUESTS.popitem(last=False)


async def _on_committed(city: City, message: Message, chat: list[Message]) -> None:
    fields = fields_of(message.text)
    booking_id = fields.get("booking_id", "")
    ledger_ref = fields.get("ledger_ref", "")
    if not booking_id or not ledger_ref:
        return
    agent = city.agent_id
    _HELD_FOR.pop(fields.get("slot_id", ""), None)  # BK-63: booked; the catalogue no longer lists it
    async with _receipt_turn(city, message, chat, booking_id) as fresh:
        if fresh is None:
            return
        token = f"booking_id={booking_id}"
        if any(row.sender == agent and first_word(row.text) == "booking.receipt"
               and fields_of(row.text).get("booking_id") == booking_id for row in fresh):
            _remember_receipt(agent, message.need_id, booking_id)
            return
        slot = fields.get("slot_id") or _hold_slot(fresh, agent, fields.get("hold_id") or booking_id)
        sender, _, _ = _booking_of(fresh, agent, slot)
        if slot and message.need_id:
            sender = _BOOKING_REQUESTS.get((agent, message.need_id, slot), sender)
        if not slot:
            # Some committed replies omit the slot. A single booking centre in the
            # case is enough to route the receipt, even if the hold is out of view.
            centres = {
                row.sender for row in fresh if row.recipient == agent and row.sender.startswith("agent:")
                and first_word(row.text) == "confirm"
            }
            if message.need_id:
                centres.update(sender for (owner, need, _), sender in _BOOKING_REQUESTS.items()
                               if owner == agent and need == message.need_id)
            if len(centres) > 1:
                return
            sender = next(iter(centres), "")
        target = sender or _citizen(fresh)
        if (target and target.startswith("citizen:") and agent == _OUR_AGENTS["booking_centre"]
                and not _we(fresh, agent, token, to=target, word="booking.receipt")):
            # BK-61: the booking centre held this slot itself (BK-57). The citizen gets the same
            # receipt as when the facility books: sentence, GP notice, route, what to bring.
            facility = _BOOKED_AT.get(message.need_id or "") or next(
                (f.get("facility", "") for row in fresh if row.sender == agent and first_word(row.text) == "offer"
                 for f in _offer_rows(row.text) if slot and f.get("slot_id") == slot), "")
            if facility:
                await _send_forwarded_receipt(city, message, fresh, booking_id, ledger_ref, facility=facility, zone_route=False)
                return
        if target and await _say(city, target, f"booking.receipt {token} ledger_ref={ledger_ref}"):
            _remember_receipt(agent, message.need_id, booking_id)


async def _cancel_booking(
    city: City, chat: list[Message], slot: str, *, reason: str, hold_id: str = "",
) -> None:
    agent = city.agent_id
    if hold_id and not _we(chat, agent, f"hold_id={hold_id}", to=LEDGER, word="cancel"):
        await _say(city, LEDGER, f"cancel hold_id={hold_id}")
    target, _, _ = _booking_of(chat, agent, slot)
    if not target:
        return
    offer_id = ""
    for row in reversed(chat):
        if (row.sender == target and row.recipient == agent and "confirm" in words(row.text)) or (
            row.sender == agent and first_word(row.text) == "offer"
        ):
            offer_id = next(
                (fields["offer_id"] for fields in _offer_rows(row.text)
                 if fields.get("slot_id") == slot and fields.get("offer_id")),
                "",
            )
            if offer_id:
                break
    identity = f"offer_id={offer_id}" if offer_id else f"slot_id={slot}"
    if not _we(chat, agent, identity, to=target, word="cancel"):
        line = ""
        if target.startswith("citizen:"):  # BK-35 / BK-57: the citizen always reads a sentence
            line = (" I am sorry, that appointment is no longer available. I am looking for another one for you now."
                    if _lang(chat) != "it" else
                    " Mi dispiace, quel posto non è più disponibile. Le cerco subito un altro appuntamento.")
        await _say(city, target, f"cancel {identity} reason={reason}{line}")


_BOOKING_REFUSALS = {"prescription_expired", "consent_missing", "no_capacity"}


async def _on_refused(
    city: City, message: Message, chat: list[Message], *, hold_self: bool,
    slot: str = "", hold_id: str = "",
) -> bool:
    """A refused hold or commit. True: the commit was sent again (BK-62), nothing is cancelled."""
    agent = city.agent_id
    fields = fields_of(message.text)
    commit_refused = "commit" in words(message.text)
    hold_id = fields.get("hold_id") or hold_id
    if commit_refused and not hold_id:
        # For a delayed refusal use the preceding commit, never a later request.
        previous = chat[:chat.index(message)] if message in chat else chat
        hold_id = next(
            (fields_of(row.text).get("hold_id", "") for row in reversed(previous)
             if row.sender == agent and row.recipient == LEDGER and first_word(row.text) == "commit"),
            "",
        )
    slot = fields.get("slot_id") or _hold_slot(chat, agent, hold_id) or slot
    if not slot and not commit_refused:
        previous = chat[:chat.index(message)] if message in chat else chat
        slot = next(
            (fields_of(row.text).get("slot_id", "") for row in reversed(previous)
             if row.sender == agent and row.recipient == LEDGER and first_word(row.text) == "hold"),
            "",
        )
    reason = (fields.get("reason") or fields.get("code") or "").lower()
    if not re.fullmatch(r"[a-z]+(?:_[a-z0-9]+)*", reason):
        reason = next(iter(words(message.text) & _BOOKING_REFUSALS), "facility_cancelled")
    if commit_refused and hold_id and "fence" in reason + " " + message.text.lower():
        # BK-62 (journeys 000149, 000248, 000290): the hold was ours, the commit came back
        # ``stale_fence`` and the hold expired: three citizens lost a confirmed visit. e19
        # documents commit without fence: send it once more without, before giving the slot up.
        notes = _sent(message.need_id or message.msg_id).notes
        if f"nofence:{hold_id}:{message.msg_id}" in notes:
            return True  # another turn already answered this same refusal
        if not any(note.startswith(f"nofence:{hold_id}:") for note in notes):
            _, consent, number = _booking_of(chat, agent, slot)
            consent = consent or next(
                (fields_of(row.text).get("consent_ref", "") for row in reversed(chat)
                 if row.sender == agent and row.recipient == LEDGER and first_word(row.text) == "commit"
                 and fields_of(row.text).get("hold_id") == hold_id), "")
            if consent:
                notes.add(f"nofence:{hold_id}:{message.msg_id}")
                parts = ["commit", f"hold_id={hold_id}", f"consent_ref={consent}"]
                if number:
                    parts.append(f"prescription_number={number}")
                if await _say(city, LEDGER, " ".join(parts)):
                    _LOG.info("bk62.commit_without_fence hold_id=%s", hold_id[:48])
                    return True
    held = _HELD_FOR.get(slot)
    if held and held[0] == (message.need_id or message.msg_id):
        _HELD_FOR.pop(slot, None)  # BK-63: our hold is gone, the slot is not ours to keep back
    await _cancel_booking(city, chat, slot, reason=reason, hold_id=hold_id if commit_refused else "")
    desk = agent == _OUR_AGENTS["booking_centre"]  # BK-57: the booking centre now holds our slots
    if desk and any(w in reason or w in message.text.lower() for w in _PERMISSION_WORDS):
        _DESK_HOLDS[0] = False
        _LOG.info("bk57.desk_holds_off reason=%s", reason[:40])
    if slot and (hold_self or desk):
        # P-magesh-9: the cancel just sent is not in ``chat`` yet, so the refused slot looked free
        # and went out again with the next offers. Remember it: it is never offered again.
        _sent(message.need_id or message.msg_id).notes.add("refused:" + slot)
        await _advance(city, message, chat, fixed=None if desk else "CONS-GIN", replacing=True)
    return False


_CHECKIN_LIMIT = 3
_LEDGER_REPLIES = {
    "checked_in", "held", "committed", "reported", "prescribed", "prescription",
    "slots", "agenda", "world", "rules", "catalogue", "history",
}
_CHECKIN_REQUESTS: OrderedDict[tuple[str, str | None, str], None] = OrderedDict()
_CHECKIN_GATES: dict[tuple[str, str | None, str], _Gate] = {}


def _checked_in(chat: list[Message], agent: str, token: str) -> Message | None:
    return _latest([row for row in chat if row.recipient == agent], "checked_in", token)


def _checkin_attempts(chat: list[Message], agent: str, booking_id: str) -> list[Message]:
    return [
        row for row in chat
        if row.sender == agent and row.recipient == LEDGER and row.text.startswith("checkin ")
        and fields_of(row.text).get("booking_id") == booking_id
    ]


def _checkin_refused(agent: str, message: Message, chat: list[Message]) -> Message | None:
    """Match a refusal to the preceding Ledger request addressed from this facility."""
    head = first_word(message.text)
    if message.sender != LEDGER or message.recipient != agent or head in _LEDGER_REPLIES:
        return None
    if head == "refused" and words(message.text) & {"hold", "commit", "prescribe", "prescription", "report"}:
        return None
    fields = fields_of(message.text)
    booking_id = fields.get("booking_id")
    previous = []
    for row in chat:
        if row.msg_id == message.msg_id:
            break
        previous.append(row)
    if booking_id:
        attempts = _checkin_attempts(previous, agent, booking_id)
        return attempts[-1] if attempts else None
    for row in reversed(previous):
        if row.sender == agent and row.recipient == LEDGER:
            return row if row.text.startswith("checkin ") else None
    return None


async def _answer_checkin_refusal(
    city: City, attempt: Message, chat: list[Message], *, reason: str,
) -> None:
    fields = fields_of(attempt.text)
    booking_id, citizen = fields.get("booking_id", ""), fields.get("citizen", "")
    if not booking_id or not citizen:
        return
    token = f"booking_id={booking_id}"
    later = chat[chat.index(attempt) + 1:]
    if _checked_in(chat, city.agent_id, token) or _we(
        later, city.agent_id, token, to=citizen, word="checkin.refused"
    ):
        return
    tries = len(_checkin_attempts(chat, city.agent_id, booking_id))
    await _checkin_failure(city, citizen, booking_id, chat, exhausted=tries >= _CHECKIN_LIMIT, reason=reason)


async def _checkin_failure(
    city: City, citizen: str, booking_id: str, chat: list[Message], *, exhausted: bool, reason: str = "",
) -> None:
    if exhausted:
        fallback = ("Non riesco a registrare il suo arrivo con questa prenotazione. Controlli il numero "
                    "sulla ricevuta o chieda al centro prenotazioni di verificarlo.")
        en = ("I could not register your arrival with this booking. Please check the number on the "
              "receipt or ask the booking centre to verify it.")
    else:
        fallback = (f"Non sono riuscito a registrare il suo arrivo. Il check-in si fa nella mezza "
                    f"giornata della visita ({_CHECKIN_HOURS}). Se è in anticipo, mi riscriva in quella fascia.")
        en = (f"I could not register your arrival. Check-in opens in the half-day of the visit "
              f"({_CHECKIN_HOURS}). If you are early, please write again during that window.")
    line = await _human(city, chat, f"Check-in could not be completed. Ledger response: {reason}", fallback, en=en)
    await _say(city, citizen, f"checkin.refused booking_id={booking_id} {line}")


async def _on_checkin(
    city: City, message: Message, chat: list[Message], *, reports: bool, booking_id: str | None = None,
) -> None:
    if booking_id is None:
        booking_id = fields_of(message.text).get("booking_id", "")
    citizen = message.sender
    context = [*chat, message]
    en = _lang(context) != "it"
    if not booking_id:
        await _say(city, citizen, "checkin.help " + (
            "Welcome! To register your arrival I need the booking number (booking_id) written "
            "on your receipt. Could you write it to me?" if en else
            "Benvenuto! Per registrare il suo arrivo mi serve il numero di prenotazione "
            "(booking_id) scritto sulla ricevuta. Me lo può scrivere?"))
        return
    agent = city.agent_id
    token = f"booking_id={booking_id}"
    key = (agent, message.need_id, booking_id)
    gate = _CHECKIN_GATES.setdefault(key, _Gate())
    gate.turns += 1
    refresh = gate.turns > 1
    try:
        async with gate.lock:
            if refresh:
                # Count the preceding turn's write before reserving another attempt.
                try:
                    context = _keep(await city.history(need_id=message.need_id), context)
                except CapError:
                    await _checkin_failure(city, citizen, booking_id, context, exhausted=False)
                    return
            success = _checked_in(context, agent, token)
            if success is not None:
                await _confirm_checkin(city, success, context, citizen)
                return
            request = (agent, message.need_id, message.msg_id)
            if request in _CHECKIN_REQUESTS:
                return
            attempts = _checkin_attempts(context, agent, booking_id)
            if len(attempts) >= _CHECKIN_LIMIT:
                await _checkin_failure(city, citizen, booking_id, context, exhausted=True)
                return
            _CHECKIN_REQUESTS[request] = None
            if len(_CHECKIN_REQUESTS) > _SENT_NEEDS:
                _CHECKIN_REQUESTS.popitem(last=False)
            try:
                attempt_id = await city.say(LEDGER, f"checkin {token} citizen={citizen}")
            except CapError:
                await _checkin_failure(city, citizen, booking_id, context, exhausted=False)
                return
    finally:
        gate.turns -= 1
        if not gate.turns:
            del _CHECKIN_GATES[key]

    reply = None

    def ready(rows: list[Message]) -> bool:
        nonlocal reply
        for row in reversed(rows):
            if row.msg_id == attempt_id:
                break
            if row.sender != LEDGER or row.recipient != agent:
                continue
            if first_word(row.text) == "checked_in" and fields_of(row.text).get("booking_id") == booking_id:
                reply = row
                return True
            attempt = _checkin_refused(agent, row, rows)
            if attempt is not None and attempt.msg_id == attempt_id:
                reply = row
                return True
        return False

    fresh = await _until(city, message.need_id, context, ready)
    if reply is not None:
        if first_word(reply.text) == "checked_in":
            await _on_checked_in(city, reply, fresh, reports=reports, citizen=citizen)
        else:
            await _checkin_failure(
                city, citizen, booking_id, context,
                exhausted=len(attempts) + 1 >= _CHECKIN_LIMIT, reason=reply.text,
            )
        return
    await _say(city, citizen, f"checkin.wait {token} " + (
        "I have sent your check-in to the register. I will confirm as soon as the answer arrives." if en else
        "Ho inviato il suo check-in al registro. Le confermo appena arriva la risposta."))


async def _confirm_checkin(city: City, message: Message, chat: list[Message], citizen: str) -> None:
    fallback = "Check-in registrato, benvenuto. Se ha bisogno di assistenza, lo dica pure al nostro personale."
    en = "You are checked in, welcome. If you need assistance, please ask our staff."
    if city.agent_id == _OUR_AGENTS["hospital"]:
        fallback += " L'ospedale è accessibile anche in sedia a rotelle."
        en += " The hospital is wheelchair accessible."
    line = await _human(city, chat, f"The register confirmed the citizen's arrival. {en}", fallback, en=en)
    booking_id = fields_of(message.text)["booking_id"]
    tokens = [
        token for token in message.text.split()[1:] if "=" in token and not token.startswith("booking_id=")
    ]
    await _say(city, citizen, " ".join(["checkin", f"booking_id={booking_id}", *tokens, line]))


async def _on_checked_in(
    city: City, message: Message, chat: list[Message], *, reports: bool, citizen: str | None = None,
) -> None:
    fields = fields_of(message.text)
    booking_id = fields.get("booking_id", "")
    if not booking_id:
        return
    token = f"booking_id={booking_id}"
    if not citizen:
        attempts = _checkin_attempts(chat, city.agent_id, booking_id)
        citizen = fields.get("citizen") or (
            fields_of(attempts[-1].text).get("citizen") if attempts else _citizen(chat)
        )
    if citizen and not _we(chat, city.agent_id, token, to=citizen, word="checkin"):
        await _confirm_checkin(city, message, chat, citizen)
    if reports and not _we(chat, city.agent_id, token, to=LEDGER, word="report"):
        await _say(city, LEDGER, f"report booking_id={booking_id} outcome_code=VISIT")
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
        "La visita è conclusa e il referto è archiviato. Il suo medico di base può consultarlo; "
        "se serve un controllo, sarà lui a indicarglielo. Grazie di essersi affidato a noi.",
        en="Your visit is complete and the report is filed. Your GP can read it and will tell "
        "you if a follow-up is needed. Thank you for trusting us.",
    )
    # G5 / SP-20 / G10: share the report with the citizen's GP first, then say so to the citizen.
    gp = await _peer(city, "gp", "medico di base gp asst-niguarda")
    if gp and gp != city.agent_id and not _we(chat, city.agent_id, token, to=gp, word="report.notice"):
        if await _say(city, gp, f"report.notice {token} outcome_code=VISIT Referto archiviato per il vostro "
                      "paziente: potete leggerlo e decidere il controllo."):
            line += (" I have sent the report to your GP myself, so they can plan any follow-up with you."
                     if _lang(chat) != "it" else
                     " Ho inviato io il referto al suo medico di base, così potrà decidere con lei il controllo.")
    await _say(city, citizen, f"report booking_id={booking_id} outcome_code=VISIT {line}")


# --- FA-12: cross-ASST request from another booking centre (format agreed in the group) ------
_PARTNER_DONE: set[str] = set()


async def _partner_request(city: City, message: Message, chat: list[Message]) -> None:
    """Answer within seconds with our fitting slots, one per line; no citizen data needed."""
    fields = fields_of(message.text)
    request_id = fields.get("request_id") or message.need_id or message.msg_id
    if request_id in _PARTNER_DONE:
        return
    procedure = fields.get("procedure", "")
    priority = fields.get("priority") or None
    agent = city.agent_id
    if not procedure:
        _PARTNER_DONE.add(request_id)
        await _say(city, message.sender, f"cancel reason=no_availability request_id={request_id} Manca procedure=.")
        return
    if not _exact(chat, agent, "agenda"):
        await _say(city, LEDGER, "agenda")
    await _say(city, LEDGER, f"world procedure={procedure} facility={agent} page=1")
    chat = await _until(city, message.need_id, chat, lambda rows: _has_agenda(rows) and _latest_slots(rows) is not None)
    agenda = _ledger(chat, "agenda")
    now = _when("" if agenda is None else agenda.get("agenda_now", ""))
    world = _latest_slots(chat)
    _PARTNER_DONE.add(request_id)
    picks = []
    if now is not None and world is not None:
        picks = fitting(
            [line for line in world.splitlines() if "slot_id=" in line],
            now=now, priority=priority, lang=fields.get("lang", "it"),
            gender=fields.get("gender_preference") or fields.get("gender") or None, facility=agent, procedure=procedure,
        )
        limit = _when(fields.get("deadline", ""))  # MACH-1.2 (2): never a slot after the asker's deadline
        if limit is not None:
            picks = [slot for slot in picks if (_when(slot.get("at", "")) or limit) <= limit]
        picks = picks[:_OFFER_MAX]  # BK-55: every fitting slot in one answer
    if not picks:
        await _say(city, message.sender, f"cancel reason=no_availability request_id={request_id} Al momento non abbiamo posti adatti per {procedure}.")
        return
    lines = [
        f"offer offer_id=of-{s['slot_id']} slot_id={s['slot_id']} doctor_id={s['doctor_id']} facility={agent} "
        f"procedure={s['procedure']} agenda_date={s['at']} request_id={request_id}"
        + (" wheelchair=true" if agent == "agent:jdj692g4145e" else "")  # common format: accessible hospital
        for s in picks
    ]
    tail = ("Ecco i nostri posti liberi. Dopo il consenso cross_asst del cittadino inviateci la conferma "
        "con offer_id, slot_id, citizen, consent_ref e prescription_number: rispondiamo con la ricevuta.")
    await _say(city, message.sender, "\n".join(_fit(lines, tail) + [tail]))
