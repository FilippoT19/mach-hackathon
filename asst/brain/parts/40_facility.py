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
    if message.sender.startswith("agent:") and not _ours(message.sender):
        return  # X-13: only our booking may confirm or cancel at our facility
    if message.sender == LEDGER and head == "held":
        await _on_held(city, message, chat)
    elif message.sender == LEDGER and head == "committed":
        await _on_committed(city, message, chat)
    elif message.sender == LEDGER and head == "refused" and "hold" in kind:
        await _on_refused(city, message, chat, hold_self=hold_self)
    elif message.sender == LEDGER and head == "checked_in":
        await _on_checked_in(city, message, chat, reports=reports)
    elif message.sender == LEDGER and head == "reported":
        await _on_reported(city, message, chat)
    elif "checkin" in kind and message.sender.startswith("citizen:"):
        await _on_checkin(city, message, chat, reports=reports)
    elif "confirm" in kind:
        await _on_confirm(city, message, chat, hold_self=hold_self)
    elif message.sender.startswith("citizen:"):
        await _facility_free_text(city, message, chat, reports=reports)


_ARRIVED = ("check-in", "check in", "sono arrivat", "sono qui", "i am here", "i'm here", "i have arrived", "arrived")


async def _facility_free_text(city: City, message: Message, chat: list[Message], *, reports: bool) -> None:
    """FA-20: a citizen text that is not a checkin/confirm never gets silence."""
    low = message.text.lower()
    if "booking_id=" in message.text or any(w in low for w in _ARRIVED):
        number = fields_of(message.text).get("booking_id") or next(
            (fields_of(r.text).get("booking_id") for r in reversed(chat) if fields_of(r.text).get("booking_id")), None
        )
        if number:
            fake = Message(type=message.type, sender=message.sender, recipient=message.recipient,
                           msg_id=message.msg_id, need_id=message.need_id,
                           body={"text": f"checkin booking_id={number} {message.text}"})
            await _on_checkin(city, fake, chat, reports=reports)
            return
    if _we(chat, city.agent_id, "", to=message.sender, word="facility.note"):
        return
    en = _lang([*chat, message]) != "it"
    await _say(
        city,
        message.sender,
        "facility.note "
        + (
            "Hello, this is the facility. To book or move a visit please write to our booking "
            "centre; if you are already here, give me the number on your receipt and I will register your arrival."
            if en
            else "Buongiorno, sono la struttura. Per prenotare o spostare una visita scriva al nostro "
            "centro prenotazioni; se è già qui, mi dia il numero della ricevuta e registro subito il suo arrivo."
        ),
    )


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


async def _on_checkin(city: City, message: Message, chat: list[Message], *, reports: bool) -> None:
    booking_id = fields_of(message.text).get("booking_id", "")
    citizen = message.sender if message.sender.startswith("citizen:") else _citizen(chat)
    if not citizen:
        return
    en = _lang([*chat, message]) != "it"
    if not booking_id:
        # FA-03 (P-francesco-3): an id we do not have is asked, never guessed; never silent.
        if not _we(chat, city.agent_id, "", to=citizen, word="checkin.help"):
            await _say(city, citizen, "checkin.help " + (
                "Welcome! To register your arrival I need the booking number (booking_id) written "
                "on your receipt: could you write it to me?" if en else
                "Benvenuto! Per registrare il suo arrivo mi serve il numero di prenotazione "
                "(booking_id) scritto sulla ricevuta: me lo può scrivere?"))
        return
    token = f"booking_id={booking_id}"
    if not _we(chat, city.agent_id, token, to=LEDGER, word="checkin"):
        if not await _say(city, LEDGER, f"checkin booking_id={booking_id} citizen={citizen}"):
            return
    found = await _await_line(city, message.need_id, chat, "checked_in", token, op="checkin")
    if found is None:
        _LOG.info("care.checkin.missing", extra={"need_id": (message.need_id or "")[:48]})
        if not _we(chat, city.agent_id, token, to=citizen, word="checkin.wait"):
            await _say(city, citizen, f"checkin.wait {token} " + (
                "I have sent your check-in to the register: I will confirm as soon as the answer "
                "arrives." if en else
                "Ho inviato il suo check-in al registro: le confermo appena arriva la risposta."))
        return
    reply, fresh = found
    if first_word(reply.text) == "checked_in":
        await _on_checked_in(city, reply, fresh, reports=reports)
        return
    # FA-03: refused. Explain once per attempt, with the half-day window; after 3 send to booking.
    tries = sum(1 for r in chat if r.sender == city.agent_id and r.recipient == citizen
                and first_word(r.text) == "checkin.refused")
    if tries >= 3:
        return
    if tries < 2:
        line = ("I could not register your arrival: check-in opens in the half-day of the visit "
                "(08-13 or 13-18). If you are early, write to me again from that time." if en else
                "Non sono riuscito a registrare il suo arrivo: il check-in si fa nella mezza giornata "
                "della visita (08-13 o 13-18). Se è in anticipo, mi riscriva da quell'ora.")
    else:
        line = ("I am sorry, I cannot register the check-in with this booking. Please check the "
                "number on the receipt, or ask the booking centre, which can verify it." if en else
                "Mi dispiace, non riesco a registrare il check-in con questa prenotazione. Controlli "
                "il numero sulla ricevuta, oppure si rivolga al centro prenotazioni che può verificarla.")
    await _say(city, citizen, f"checkin.refused {token} {line}")


async def _on_checked_in(
    city: City, message: Message, chat: list[Message], *, reports: bool
) -> None:
    booking_id = fields_of(message.text).get("booking_id", "")
    citizen = _citizen(chat)
    if not booking_id:
        return
    token = f"booking_id={booking_id}"
    if reports and not _we(chat, city.agent_id, token, to=LEDGER, word="report"):
        await _say(city, LEDGER, f"report booking_id={booking_id} outcome_code=VISIT")
    if citizen and not _we(chat, city.agent_id, token, to=citizen, word="checkin"):
        line = await _human(
            city,
            chat,
            "the citizen has checked in at the facility; the doctor will see them shortly",
            "Check-in registrato, benvenuto e grazie di essere arrivato puntuale. Il medico la "
            "riceve a breve; se ha bisogno di assistenza o di un accompagnamento, lo dica pure "
            "al nostro personale.",
            en="You are checked in, welcome and thank you for being on time. The doctor will see "
            "you shortly; if you need assistance or someone to accompany you, just ask our staff.",
        )
        await _say(city, citizen, f"checkin booking_id={booking_id} {line}")
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
    await _say(city, citizen, f"report booking_id={booking_id} outcome_code=VISIT {line}")


# --- FA-12: cross-ASST request from another booking centre (format agreed in the group) ------
_RARE_LANG = {"h3": "vi"}  # our h3 physiatrist speaks Vietnamese (registry)
_PARTNER_DONE: set[str] = set()


def _doctor_tokens(doctor_id: str) -> str:
    short = doctor_id.rsplit("-", 1)[-1]
    spec = _DOCTORS.get(short)
    if spec is None:
        return ""
    langs = sorted(l for l in spec[0] if l != "*")
    if short in _RARE_LANG:
        langs.append(_RARE_LANG[short])
    return f"doctor_lang={'/'.join(langs)} doctor_gender={spec[1]}"


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
            gender=fields.get("gender") or None, facility=agent, procedure=procedure,
        )[:3]
    if not picks:
        await _say(city, message.sender, f"cancel reason=no_availability request_id={request_id} Al momento non abbiamo posti adatti per {procedure}.")
        return
    lines = [
        f"offer offer_id=of-{s['slot_id']} slot_id={s['slot_id']} doctor_id={s['doctor_id']} facility={agent} "
        f"procedure={s['procedure']} agenda_date={s['at']} {_doctor_tokens(s['doctor_id'])} request_id={request_id}"
        + (" wheelchair=true" if agent == "agent:jdj692g4145e" else "")  # common format: accessible hospital
        for s in picks
    ]
    await _say(city, message.sender, "\n".join(lines + [
        "Ecco i nostri posti liberi. Dopo il consenso cross_asst del cittadino mandateci confirm "
        "con offer_id, slot_id, citizen, consent_ref e prescription_number: rispondiamo con la ricevuta."
    ]))
