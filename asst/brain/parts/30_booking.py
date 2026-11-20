# PART: 30_booking.py — CENTRO PRENOTAZIONI e CONSULTORIO (parte prenotazione): offerte, confirm, ricevuta
# Non è un modulo a sé: seats.py unisce i file di parts/ in ordine nel brain finale.
# --- centro prenotazioni and consultorio -------------------------------------------------------


def _ledger(chat: list[Message], head: str) -> dict[str, str] | None:
    found: dict[str, str] | None = None
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == head:
            found = fields_of(row.text)
    return found


def _prescription_reply(chat: list[Message], number: str | None) -> dict[str, str] | None:
    reply = _ledger(chat, "prescription")
    if number and reply is not None and reply.get("prescription_number") not in (None, number):
        return None
    return reply


def _expired_prescription(chat: list[Message], number: str | None) -> bool:
    expired: bool | None = None
    for row in chat:
        if row.sender != LEDGER:
            continue
        head = first_word(row.text)
        fields = fields_of(row.text)
        row_number = fields.get("prescription_number")
        if number and row_number and row_number != number:
            continue
        upper = row.text.upper()
        if head == "refused" and "PRESCRIPTION_EXPIRED" in upper:
            expired = True
        elif head == "prescription":
            state = fields.get("state", "").lower()
            expired = state == "expired" or "PRESCRIPTION_EXPIRED" in upper
    return expired is True


async def _ask_renewal(
    city: City, message: Message, chat: list[Message], citizen: str, number: str | None
) -> None:
    if not number or _we(
        chat,
        city.agent_id,
        "purpose=prescription_renewal",
        to=citizen,
        word="data.request",
    ):
        return
    line = await _human(
        city,
        chat,
        "the prescription has expired and the citizen must ask their GP for a renewal",
        "La ricetta è scaduta. Chieda al medico di base di rinnovarla usando questo numero.",
    )
    await _say(
        city,
        citizen,
        f"data.request purpose=prescription_renewal fields=prescription_number prescription_number={number} {line}",
    )


def _latest_slots(chat: list[Message]) -> str | None:
    found: str | None = None
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == "slots":
            found = row.text
    return found


def _page(text: str) -> tuple[int, int]:
    raw = fields_of(text.splitlines()[0] if text else "").get("page", "")
    left, _, right = raw.partition("/")
    if left.isdigit() and right.isdigit():
        return int(left), int(right)
    return 1, 1


def _asked(chat: list[Message], agent: str, procedure: str, page: int) -> bool:
    token = f"page={page}"
    proc = f"procedure={procedure}"
    for row in chat:
        if row.sender == agent and token in row.text.split() and proc in row.text.split():
            return True
    return False


def _offered(chat: list[Message], agent: str) -> set[str]:
    found: set[str] = set()
    for row in chat:
        if row.sender != agent or "offer" not in words(row.text):
            continue
        for offer in _offer_rows(row.text):
            if offer.get("slot_id"):
                found.add(offer["slot_id"])
    return found


def _withdrawn(chat: list[Message], agent: str) -> set[str]:
    """Slots we cancelled. The citizen drops the rest, so those are offered again."""

    by_offer: dict[str, str] = {}
    for row in chat:
        if row.sender != agent or "offer" not in words(row.text):
            continue
        for fields in _offer_rows(row.text):
            offer_id = fields.get("offer_id")
            slot = fields.get("slot_id")
            if offer_id and slot:
                by_offer[offer_id] = slot
    dropped: set[str] = set()
    for row in chat:
        if "cancel" not in words(row.text):
            continue
        slot = by_offer.get(fields_of(row.text).get("offer_id", ""))
        if slot:
            dropped.add(slot)
    return dropped


def _number(chat: list[Message]) -> str | None:
    for row in reversed(chat):
        if row.sender.startswith("citizen:"):
            number = fields_of(row.text).get("prescription_number")
            if number:
                return number
    return None


# X-30: the citizen writes to the GP without lang=, so the language comes from the words.
_IT_WORDS = frozenset("il lo la le gli un una di da che non per con sono ho mi ma è al del della dolore male vorrei grazie buongiorno salve gentile dottore visita sento".split())
_EN_WORDS = frozenset("knee back heart racing chest need want appointment book can you help the an i'm im my is are have has of to and with for it this that pain hurts would please thank thanks hello hi dear doctor feel been since".split())
_LANG_OF: OrderedDict[str, str] = OrderedDict()


def _guess_lang(text: str) -> str | None:
    tokens = [t.strip(".,;:!?()\"'").lower() for t in text.split() if "=" not in t]
    it = sum(t in _IT_WORDS for t in tokens)
    en = sum(t in _EN_WORDS for t in tokens)
    if it == en == 0:
        return None
    return "en" if en > it else "it"


def _note_lang(message: Message) -> None:
    """Remember the citizen's language for the need, for later turns whose history misses it."""
    if not message.sender.startswith("citizen:") or not message.need_id:
        return
    lang = fields_of(message.text).get("lang") or _guess_lang(message.text)
    if lang:
        _LANG_OF[message.need_id] = lang
        _LANG_OF.move_to_end(message.need_id)
        while len(_LANG_OF) > _SENT_NEEDS:
            _LANG_OF.popitem(last=False)


def _lang(chat: list[Message]) -> str:
    for row in chat:
        if row.sender.startswith("citizen:"):
            lang = fields_of(row.text).get("lang", "")
            if lang:
                return lang
    for row in chat:
        if row.need_id and row.need_id in _LANG_OF:
            return _LANG_OF[row.need_id]
    for row in chat:
        if row.sender.startswith("citizen:"):
            lang = _guess_lang(row.text)
            if lang:
                return lang
    return "it"


_PREF_BY_RX: dict[str, dict[str, str]] = {}


def _rx_pref(chat: list[Message], key: str) -> str | None:
    """X-33: a preference the GP passed in the referral for this prescription."""
    for row in chat:
        if row.sender.startswith("citizen:"):
            number = fields_of(row.text).get("prescription_number")
            if number and key in _PREF_BY_RX.get(number, {}):
                return _PREF_BY_RX[number][key]
    return None


def _gender(chat: list[Message]) -> str | None:
    pref = _gender_said(chat)
    return pref if pref is not None else _rx_pref(chat, "gender")


def _gender_said(chat: list[Message]) -> str | None:
    for row in chat:
        if not row.sender.startswith("citizen:"):
            continue
        raw = fields_of(row.text).get("gender_preference") or fields_of(row.text).get("gender")
        if raw in {"m", "f"}:
            return raw
    return None


_DAY_ALIASES = {
    "mon": "mon",
    "monday": "mon",
    "lun": "mon",
    "lunedì": "mon",
    "tue": "tue",
    "tuesday": "tue",
    "mar": "tue",
    "martedì": "tue",
    "wed": "wed",
    "wednesday": "wed",
    "mer": "wed",
    "mercoledì": "wed",
    "thu": "thu",
    "thursday": "thu",
    "gio": "thu",
    "giovedì": "thu",
    "fri": "fri",
    "friday": "fri",
    "ven": "fri",
    "venerdì": "fri",
}


def _days(chat: list[Message]) -> frozenset[str] | None:
    found: set[str] = set()
    for row in chat:
        if not row.sender.startswith("citizen:"):
            continue
        raw = fields_of(row.text).get("days", "")
        for value in raw.lower().replace(",", "/").split("/"):
            day = _DAY_ALIASES.get(value.strip())
            if day:
                found.add(day)
    return frozenset(found) or None


_RX_DATE_KEYS = ("issued_at", "issued", "issue_date", "prescribed_at", "created_at", "date")
_RX_LIMIT_KEYS = ("valid_until", "expires_at", "expiry", "deadline", "due", "due_by")


def _before_rx_deadline(slot: dict[str, str], reply: dict[str, str] | None, priority: str | None) -> bool:
    """BK-27: the priority window counts from the prescription, not from today. A slot after the
    citizen's deadline is refused (no_booking -1), so it is never offered."""
    if not reply:
        return True
    at = _when(slot.get("at", ""))
    if at is None:
        return True
    for key in _RX_LIMIT_KEYS:
        limit = _when(reply.get(key, ""))
        if limit is not None:
            return at <= limit
    days = _DEADLINE_DAYS.get(priority or "")
    if days is None:
        return True
    for key in _RX_DATE_KEYS:
        issued = _when(reply.get(key, ""))
        if issued is not None:
            return at <= issued + timedelta(days=days)
    return True


_FACILITY_ROLES = {"facility", "hospital", "specialist_care", "specialist", "family_counseling"}
_CROSS_SERVICE_TYPES = {
    "VIS-FIS": "hospital.physiatry",
    "VIS-CARD": "specialist_care.cardiology",
    "CTRL-CARD": "specialist_care.cardiology",
    "CONS-GIN": "family_counseling.gynecology",
}


def _peer_value(peer: object, key: str) -> object:
    if isinstance(peer, dict):
        return peer.get(key, "")
    return getattr(peer, key, "")


def _peer_id(peer: object) -> str:
    for key in ("agent_id", "id", "mailbox"):
        value = _peer_value(peer, key)
        if isinstance(value, str) and value.startswith("agent:"):
            return value
    value = str(peer)
    return value if value.startswith("agent:") else ""


def _cross_consent(chat: list[Message], agent: str) -> tuple[bool | None, str]:
    """Return (accepted/refused/unknown, consent_ref) for the latest cross-ASST request."""

    asked = False
    for row in chat:
        fields = fields_of(row.text)
        if row.sender == agent and fields.get("purpose") == "cross_asst":
            asked = True
            continue
        if not asked or not row.sender.startswith("citizen:"):
            continue
        consent = fields.get("consent_ref", "")
        if consent:
            return True, consent
        lowered = row.text.lower()
        if any(word in lowered.split() for word in {"no", "non", "rifiuto", "rifiutato"}):
            return False, ""
    return None, ""


def _cross_message(message: Message) -> bool:
    return fields_of(message.text).get("purpose") == "cross_asst"


def _partner_offer_ready(chat: list[Message], request_id: str) -> bool:
    for row in chat:
        if not row.sender.startswith("agent:") or "offer" not in words(row.text):
            continue
        if fields_of(row.text).get("request_id") == request_id:
            return True
    return False


def _offer_line(slot: dict[str, str], number: str | None, priority: str | None) -> str:
    parts = [
        "offer",
        f"offer_id=of-{slot['slot_id']}",
        f"slot_id={slot['slot_id']}",
        f"doctor_id={slot['doctor_id']}",
        f"facility={slot['facility']}",
        f"procedure={slot['procedure']}",
        f"agenda_date={slot['at']}",
        f"agenda_day={slot['day']}",
        f"expiry={slot['at']}",
    ]
    if priority:
        parts.append(f"priority={priority}")
    if number:
        parts.append(f"prescription_number={number}")
    return " ".join(parts)


def _our_offer(chat: list[Message], agent: str, offer_id: str) -> dict[str, str]:
    token = f"offer_id={offer_id}"
    for row in chat:
        if row.sender == agent and token in row.text.split() and "offer" in words(row.text):
            return _line_fields(row.text, token)
    return {}


class _Gate:
    """One need's lock and how many turns hold it or wait for it."""

    __slots__ = ("lock", "turns")

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.turns = 0


class _Sent:
    """Offers this process sent for one need, which the case history may not show yet.

    ``offers`` holds every slot id (and waiting-list offer id) sent. A cancel makes the
    citizen drop all offers, so ``again`` holds only what was re-sent for ``trigger``.
    """

    __slots__ = ("offers", "trigger", "again", "cross_asked", "cross_sent", "cross_peers", "partner_offers")

    def __init__(self) -> None:
        self.offers: set[str] = set()
        self.trigger = ""
        self.again: set[str] = set()
        self.cross_asked = False
        self.cross_sent = False
        self.cross_peers: set[str] = set()
        self.partner_offers: set[str] = set()


# Every Ledger or citizen message opens its own turn, and turns of one need run at the same
# time. Each reads the case before the others' offers are in it, so offers wait on this.
# An entry lives only while a turn holds or waits on its lock.
_GATES: dict[str, _Gate] = {}
_SENT: OrderedDict[str, _Sent] = OrderedDict()


def _sent(key: str) -> _Sent:
    entry = _SENT.get(key)
    if entry is None:
        entry = _SENT[key] = _Sent()
        while len(_SENT) > _SENT_NEEDS:
            _SENT.popitem(last=False)
    else:
        _SENT.move_to_end(key)
    return entry


async def _cross_asst(
    city: City,
    message: Message,
    chat: list[Message],
    key: str,
    citizen: str,
    procedure: str,
    priority: str | None,
) -> bool:
    """Ask for cross-ASST consent, then request criteria-only offers from Index peers."""

    sent = _sent(key)
    accepted, _consent_ref = _cross_consent(chat, city.agent_id)
    if accepted is False:
        return False
    if accepted is None:
        if sent.cross_asked or _we(
            chat, city.agent_id, "purpose=cross_asst", to=citizen, word="consent"
        ):
            sent.cross_asked = True
            return True
        line = await _human(
            city,
            chat,
            "the citizen must consent before we search for an appointment in another ASST",
            "Nella sua ASST non c'è disponibilità. Posso cercare in un'altra ASST?",
        )
        if await _say(city, citizen, f"consent purpose=cross_asst {line}"):
            sent.cross_asked = True
        return True
    if sent.cross_sent:
        return True
    finder = getattr(city, "find", None)
    if not callable(finder):
        return False
    service_type = _CROSS_SERVICE_TYPES.get(procedure, "facility")
    try:
        peers = await finder(
            f"facility in another ASST with capability {service_type} for procedure {procedure}"
        )
    except Exception:
        return False
    request_id = f"cross-{message.need_id or message.msg_id}"
    sent_any = False
    for peer in peers or []:
        target = _peer_id(peer)
        if not target or target == city.agent_id or target in sent.cross_peers:
            continue
        role = _peer_value(peer, "role")
        capabilities = _peer_value(peer, "capabilities")
        if role and role not in _FACILITY_ROLES and service_type not in str(capabilities):
            continue
        parts = [
            "need.request",
            f"service_type={service_type}",
            f"procedure={procedure}",
            f"request_id={request_id}",
        ]
        if priority:
            parts.append(f"priority={priority}")
        if await _say(city, target, " ".join(parts)):
            sent.cross_peers.add(target)
            sent_any = True
    sent.cross_sent = sent_any
    if not sent_any:
        return False
    fresh = await _until(
        city,
        message.need_id,
        chat,
        lambda rows: _partner_offer_ready(rows, request_id),
    )
    for row in reversed(fresh):
        if row.sender.startswith("agent:") and fields_of(row.text).get("request_id") == request_id:
            await _partner_offer(city, row, fresh)
            return True
    return False


async def _index_facility(
    city: City, procedure: str, preferred: str | None = None
) -> str | None:
    """Resolve a facility through the Index before sending it a booking message."""

    finder = getattr(city, "find", None)
    if not callable(finder):
        return None
    service_type = _CROSS_SERVICE_TYPES.get(procedure, "facility")
    try:
        peers = await finder(f"facility offering {service_type} for procedure {procedure}")
    except Exception:
        return None
    candidates: list[str] = []
    for peer in peers or []:
        target = _peer_id(peer)
        if not target or target in candidates:
            continue
        role = _peer_value(peer, "role")
        capabilities = _peer_value(peer, "capabilities")
        if role and role not in _FACILITY_ROLES and service_type not in str(capabilities):
            continue
        candidates.append(target)
    if preferred:
        return preferred if preferred in candidates else None
    return candidates[0] if candidates else None


async def _partner_offer(city: City, message: Message, chat: list[Message]) -> None:
    """Forward a remote facility's criteria-only offer to the citizen."""

    fields = fields_of(message.text)
    offer_id = fields.get("offer_id", "")
    slot = fields.get("slot_id", "")
    facility = fields.get("facility", "")
    citizen = _citizen(chat)
    if not offer_id or not slot or not facility or not citizen:
        return
    key = message.need_id or message.msg_id
    sent = _sent(key)
    if offer_id in sent.partner_offers or _we(
        chat, city.agent_id, f"offer_id={offer_id}", to=citizen, word="offer"
    ):
        return
    text = message.text
    if "cross_asst=true" not in text.split():
        text = f"{text} cross_asst=true"
    if await _say(city, citizen, text):
        sent.partner_offers.add(offer_id)


async def _desk(
    city: City,
    message: Message,
    chat: list[Message],
    *,
    hold_self: bool,
    fixed: str | None,
) -> None:
    if message.sender == city.agent_id:
        return
    # BK-15: the case history can miss the message that opened this turn. Without it the desk
    # finds no citizen and stays silent, so the inbound message always joins the case.
    if all(row.msg_id != message.msg_id for row in chat):
        chat = [*chat, message]
    kind = words(message.text)
    if first_word(message.text) == "referral" and message.sender.startswith("agent:"):
        await _on_referral(city, message, chat)
        return
    if _cross_message(message) and message.sender.startswith("citizen:"):
        await _advance(city, message, chat, fixed=fixed, replacing=False)
        return
    if "consent" in kind and message.sender.startswith("citizen:"):
        await _on_confirm(city, message, chat, hold_self=hold_self)
        return
    if "confirm" in kind and (
        message.sender.startswith("citizen:") or message.sender.startswith("agent:")
    ):
        await _on_confirm(city, message, chat, hold_self=hold_self)
        return
    if "offer" in kind and message.sender.startswith("agent:"):
        await _partner_offer(city, message, chat)
        return
    if "booking.receipt" in kind and message.sender.startswith("agent:"):
        await _forward_receipt(city, message, chat)
        return
    if message.sender.startswith("citizen:") and _asked_where(chat, city.agent_id, message):
        await _on_where(city, message, chat)
        return
    if "cancel" in kind and message.sender.startswith("agent:"):
        await _partner_cancel(city, message, chat, fixed=fixed)
        return
    if "cancel" in kind and message.sender.startswith("citizen:"):
        await _citizen_cancel(city, message, chat, fixed=fixed)
        return
    if message.sender == LEDGER or message.sender.startswith("citizen:"):
        await _advance(city, message, chat, fixed=fixed, replacing=False)


async def _on_referral(city: City, message: Message, chat: list[Message]) -> None:
    """X-27: the gp tells us a prescription is coming. Answer at once (clock +1), once per need."""

    number = fields_of(message.text).get("prescription_number", "")
    if not number:
        return
    token = f"prescription_number={number}"
    if _we(chat, city.agent_id, token, to=message.sender, word="referral.ack"):
        return
    procedure = fields_of(message.text).get("procedure", "")
    pref = {k: v for k, v in fields_of(message.text).items() if k in ("lang", "gender") and v}
    if pref:
        _PREF_BY_RX[number] = pref  # X-33
    parts = ["referral.ack", token] + ([f"procedure={procedure}"] if procedure else [])
    await _say(
        city,
        message.sender,
        " ".join(parts) + " Ricevuto: quando il cittadino ci contatta gli proponiamo subito i posti liberi.",
    )


async def _advance(
    city: City,
    message: Message,
    chat: list[Message],
    *,
    fixed: str | None,
    replacing: bool,
) -> None:
    key = message.need_id or message.msg_id
    gate = _GATES.get(key)
    if gate is None:
        gate = _GATES[key] = _Gate()
    gate.turns += 1
    try:
        async with gate.lock:
            await _advance_alone(city, message, chat, key, fixed=fixed, replacing=replacing)
    finally:
        gate.turns -= 1
        if gate.turns == 0 and _GATES.get(key) is gate:
            del _GATES[key]


async def _advance_alone(
    city: City,
    message: Message,
    chat: list[Message],
    key: str,
    *,
    fixed: str | None,
    replacing: bool,
) -> None:
    agent = city.agent_id
    citizen = _citizen(chat)
    if citizen is None:
        return
    number = _number(chat)
    reply = _prescription_reply(chat, number)
    priority = None if reply is None else reply.get("priority")
    procedure = fixed or (None if reply is None else reply.get("procedure"))
    agenda = _ledger(chat, "agenda")
    now = _when("" if agenda is None else agenda.get("agenda_now", ""))
    world = _latest_slots(chat)
    if fixed is None and _expired_prescription(chat, number):
        await _ask_renewal(city, message, chat, citizen, number)
        return
    # Ask, then read the reply from history: the push of a ledger message does not open a turn.
    for _pass in range(3):
        reply = _prescription_reply(chat, number)
        priority = None if reply is None else reply.get("priority")
        if fixed is None and _expired_prescription(chat, number):
            await _ask_renewal(city, message, chat, citizen, number)
            return
        if priority == "P":
            offer_id = f"wl-{message.need_id or message.msg_id}"
            token = f"offer_id={offer_id}"
            sent = _sent(key)
            if offer_id in sent.offers:
                return
            if not _we(chat, agent, token, to=citizen, word="offer"):
                en = _lang(chat) != "it"
                line = (
                    "Your prescription can be scheduled, so the right place for you is the waiting "
                    "list: I have already added you. As soon as a suitable slot opens I will offer it, "
                    "you do not need to call again."
                    if en
                    else "La sua ricetta è programmabile, quindi il posto giusto per lei è la lista "
                    "d'attesa: l'ho già inserita. Appena si libera un posto adatto glielo propongo io, "
                    "non deve richiamare."
                )
                extra = "".join(
                    f" {k}={v}" for k, v in (("procedure", procedure), ("priority", "P"), ("prescription_number", number)) if v
                )
                if await _say(city, citizen, f"offer offer_id={offer_id} waiting_list=true{extra} {line}"):
                    sent.offers.add(offer_id)
            return
        procedure = fixed or (None if reply is None else reply.get("procedure"))
        number = _number(chat)
        if fixed is None and number and not procedure:
            if _pass == 2:
                return
            if not any(
                row.sender == agent and f"prescription_number={number}" in row.text.split()
                for row in chat
            ):
                await _say(city, LEDGER, f"prescription prescription_number={number}")
            if not _exact(chat, agent, "agenda"):
                await _say(city, LEDGER, "agenda")
            chat = await _until(
                city,
                message.need_id,
                chat,
                lambda rows: (
                    _expired_prescription(rows, number)
                    or (_has_procedure(rows, number) and _has_agenda(rows))
                ),
            )
            continue
        if not procedure:
            return
        state = None if reply is None else reply.get("state")
        if fixed is None and state not in (None, "issued"):
            # BK-21: never silent on a prescription we cannot use.
            if not _we(chat, agent, "", to=citizen, word="prescription.note"):
                en = _lang(chat) != "it"
                await _say(city, citizen, "prescription.note state=" + str(state) + " " + (
                    "I cannot use this prescription for a new booking (it is already used or no longer "
                    "valid). Please write to your GP with this number: they will issue a new one, and I "
                    "will have the free slots ready for you."
                    if en else
                    "Non posso usare questa ricetta per una nuova prenotazione (risulta già usata o non "
                    "più valida). Scriva al suo medico di base con questo numero: gliene prepara una "
                    "nuova e io le tengo pronti i posti liberi."))
            return
        agenda = _ledger(chat, "agenda")
        now = _when("" if agenda is None else agenda.get("agenda_now", ""))
        world = _latest_slots(chat)
        if now is not None and world is not None:
            break
        if _pass == 2:
            return
        if now is None and not _exact(chat, agent, "agenda"):
            await _say(city, LEDGER, "agenda")
        if world is None and not _asked(chat, agent, procedure, 1):
            await _say(city, LEDGER, f"world procedure={procedure} page=1")
        chat = await _until(
            city,
            message.need_id,
            chat,
            lambda rows: _has_agenda(rows) and _latest_slots(rows) is not None,
        )
    else:
        return
    if now is None or world is None:
        return
    # A cancel drops every offer the citizen was holding, so the ones still free are sent again,
    # once per cancel: a second turn for the same cancel or refusal does not repeat them.
    sent = _sent(key)
    if replacing:
        trigger = fields_of(message.text).get("offer_id") or message.msg_id
        if sent.trigger != trigger:
            sent.trigger = trigger
            sent.again = set()
        taken = _withdrawn(chat, agent) | sent.again
    else:
        taken = _offered(chat, agent) | sent.offers
    chosen = [
        slot
        for slot in fitting(
            [line for line in world.splitlines() if "slot_id=" in line],
            now=now,
            priority=priority,
            lang=_lang(chat),
            gender=_gender(chat),
            days=_days(chat),
            facility=agent if fixed == "CONS-GIN" else None,
            procedure=procedure,
        )
        if slot.get("slot_id") not in taken and _before_rx_deadline(slot, reply, priority)
    ]
    if chosen:
        # BK-14: every slot in ONE message, one offer per line. The citizen chooses in the turn of
        # the first message that names a place; a later message does not enter that choice.
        picks = chosen[:3]
        line = None
        if fixed == "CONS-GIN":  # CO-20: the consultorio needs no prescription
            line = (
                "The family counselling centre needs no prescription. Here are the first free slots "
                "with our gynaecologist; choose the one you prefer and I will lock it. Your data "
                "stay confidential at the centre."
                if _lang(chat) != "it"
                else "Al consultorio si accede direttamente, senza ricetta. Ecco i primi posti liberi "
                "con la nostra ginecologa: scelga quello che preferisce e lo blocco subito. I suoi "
                "dati restano riservati al consultorio."
            )
        line = line or await _human(
            city,
            chat,
            "here are the free appointments that fit; the citizen picks one and confirms it",
            "Ecco i posti liberi adatti a lei, tutti nei tempi della sua ricetta e con un medico che "
            "parla la sua lingua. Mi risponda con quello che preferisce e lo blocco subito; se "
            "nessuno le va bene, me lo dica e cerco altri giorni o la metto in lista d'attesa.",
            en="Here are the free appointments that suit you, all within the time of your "
            "prescription and with a doctor who speaks your language. Reply with the one you "
            "prefer and I will lock it straight away; if none suits you, tell me and I will look "
            "for other days or put you on the waiting list.",
        )
        text = "\n".join([_offer_line(slot, number, priority) for slot in picks] + [line])
        if await _say(city, citizen, text):
            for slot in picks:
                sent.offers.add(slot["slot_id"])
                if replacing:
                    sent.again.add(slot["slot_id"])
        return
    dropped = message.sender.startswith("citizen:") and "cancel" in words(message.text)
    if taken and not replacing and not dropped:  # X-34: after a citizen cancel, go on to the waiting list
        if message.sender.startswith("citizen:") and "again" not in sent.offers:
            # BK-22: the citizen writes again after our offers: never silence, repeat them once.
            last = next((r.text for r in reversed(chat) if r.sender == agent and r.recipient == citizen and "offer" in words(r.text)), None)
            if last:
                sent.offers.add("again")
                await _say(city, citizen, last)
        return
    page, pages = _page(world)
    if page < pages and page < _MAX_PAGE:
        if not _asked(chat, agent, procedure, page + 1):
            await _say(city, LEDGER, f"world procedure={procedure} page={page + 1}")
        return
    # Search another ASST only after the complete local catalogue has been exhausted.
    if await _cross_asst(city, message, chat, key, citizen, procedure, priority):
        return
    # BK-10: every page read and no partner can serve it. The waiting list is the safe fallback.
    await _relaxed(city, message, chat, key, citizen, procedure, number, priority)


async def _relaxed(
    city: City,
    message: Message,
    chat: list[Message],
    key: str,
    citizen: str,
    procedure: str,
    number: str | None,
    priority: str | None,
) -> None:
    offer_id = f"wl-{message.need_id or message.msg_id}"
    sent = _sent(key)
    if offer_id in sent.offers or _we(chat, city.agent_id, f"offer_id={offer_id}", to=citizen, word="offer"):
        return
    line = await _human(
        city,
        chat,
        "no appointment that fits the citizen is free in the time allowed; we put them on the "
        "waiting list and will offer the first suitable slot that opens",
        "Mi dispiace, al momento non c'è un posto adatto a lei nei tempi previsti. La metto "
        "subito in lista d'attesa: appena si libera un posto adatto glielo proponiamo. Se nel "
        "frattempo il disturbo cambia, ricontatti il suo medico di base.",
        en="I am sorry, right now there is no suitable appointment within the time allowed. I "
        "am putting you on the waiting list now: as soon as a suitable slot opens we will offer "
        "it to you. If your symptoms change in the meantime, contact your GP again.",
    )
    parts = ["offer", f"offer_id={offer_id}", "waiting_list=true", f"procedure={procedure}"]
    if priority:
        parts.append(f"priority={priority}")
    if number:
        parts.append(f"prescription_number={number}")
    if await _say(city, citizen, " ".join(parts) + f" {line}"):
        sent.offers.add(offer_id)


async def _on_confirm(
    city: City, message: Message, chat: list[Message], *, hold_self: bool
) -> None:
    agent = city.agent_id
    fields = fields_of(message.text)
    offer_id = fields.get("offer_id", "")
    consent = fields.get("consent_ref", "")
    offer = _our_offer(chat, agent, offer_id) if offer_id else {}
    slot = fields.get("slot_id") or offer.get("slot_id", "")
    facility = fields.get("facility") or offer.get("facility", "")
    if not slot:
        return
    citizen = fields.get("citizen") or (
        message.sender if message.sender.startswith("citizen:") else ""
    )
    if not consent and offer.get("cross_asst") == "true":
        accepted, cross_ref = _cross_consent(chat, agent)
        if accepted:
            consent = cross_ref
    if not consent:
        if not citizen:
            return
        consent_ref = f"cons-{message.need_id or message.msg_id}-booking"
        token = f"offer_id={offer_id}" if offer_id else f"slot_id={slot}"
        if _we(chat, agent, token, to=citizen, word="consent"):
            return
        line = await _human(
            city,
            chat,
            "the citizen must give consent before the selected appointment can be booked",
            "Per procedere con la prenotazione e la condivisione dei dati necessari, confermi il consenso.",
        )
        parts = [
            "consent",
            "consent_required=true",
            token,
            f"slot_id={slot}",
            f"consent_ref_required={consent_ref}",
        ]
        if facility:
            parts.append(f"facility={facility}")
        await _say(city, citizen, " ".join(parts) + f" {line}")
        return
    number = fields.get("prescription_number") or offer.get("prescription_number")
    procedure = fields.get("procedure") or offer.get("procedure", "")
    book_here = hold_self or message.sender.startswith("agent:") or facility == agent
    if book_here:
        if not _we(chat, agent, f"slot_id={slot}", to=LEDGER, word="hold"):
            parts = ["hold", f"slot_id={slot}"]
            if citizen:
                parts.append(f"citizen={citizen}")
            if number:
                parts.append(f"prescription_number={number}")
            parts.append(f"consent_ref={consent}")
            if not await _say(city, LEDGER, " ".join(parts)):
                return
        await _finish_booking(city, message, chat, slot, hold_self=hold_self)
        return
    if not facility or not citizen:
        return
    # The facility comes from our own Ledger offer: the Index only confirms it, never vetoes it
    # (Index roles are hospital/specialist_care/..., not 'facility').
    target = await _index_facility(city, procedure, preferred=facility) or facility
    if _we(chat, agent, f"slot_id={slot}", to=target, word="confirm"):
        return
    parts = [
        "confirm",
        f"offer_id={offer_id or offer.get('offer_id', '')}",
        f"slot_id={slot}",
        f"citizen={citizen}",
        f"consent_ref={consent}",
        f"facility={facility}",
    ]
    if number:
        parts.append(f"prescription_number={number}")
    await _say(city, target, " ".join(parts))


async def _forward_receipt(city: City, message: Message, chat: list[Message]) -> None:
    fields = fields_of(message.text)
    booking_id = fields.get("booking_id", "")
    ledger_ref = fields.get("ledger_ref", "")
    citizen = _citizen(chat)
    if not booking_id or not ledger_ref or not citizen:
        return
    token = f"booking_id={booking_id}"
    if _we(chat, city.agent_id, token, to=citizen, word="booking.receipt"):
        return
    line = await _human(
        city,
        chat,
        "the visit is booked and confirmed; on the day of the visit the citizen checks in at "
        "the facility with this receipt",
        "La visita è prenotata e confermata. Il giorno della visita si presenti "
        + _FACILITY_WHERE.get(message.sender, "in struttura")
        + " con questa ricevuta e la tessera sanitaria per il check-in. Se non può venire, "
        "ci scriva prima: le spostiamo l'appuntamento e liberiamo il posto per un altro cittadino.",
        en="Your visit is booked and confirmed. On the day, please come "
        + _FACILITY_WHERE_EN.get(message.sender, "to the facility")
        + " with this receipt and your health card for check-in. If you cannot come, write to "
        "us first: we will move the appointment and free the slot for another citizen.",
    )
    if not await _say(
        city, citizen, f"booking.receipt booking_id={booking_id} ledger_ref={ledger_ref} {line}"
    ):
        return
    # X-31: proactive next step — ask where the citizen lives and how they move, then tell them
    # the best way to reach the facility (distance from the map, transit, access, Area B).
    if message.need_id:
        _BOOKED_AT[message.need_id] = message.sender
    if not _we(chat, city.agent_id, "purpose=booking", to=citizen, word="data.request"):
        en = _lang(chat) != "it"
        await _say(
            city,
            citizen,
            f"data.request purpose=booking fields={_WHERE_FIELDS} "
            + (
                "To help you get there: may I have your address, and do you need any assistance "
                "or plan to come by car? I will tell you the easiest way to reach the visit."
                if en
                else "Per aiutarla ad arrivare: mi indica il suo indirizzo, se le serve assistenza "
                "e se pensa di venire in auto? Le dico il modo più comodo per raggiungere la visita."
            ),
        )


async def _partner_cancel(
    city: City, message: Message, chat: list[Message], *, fixed: str | None
) -> None:
    fields = fields_of(message.text)
    offer_id = fields.get("offer_id", "")
    citizen = _citizen(chat)
    if (
        offer_id
        and citizen
        and not _we(chat, city.agent_id, f"offer_id={offer_id}", to=citizen, word="cancel")
    ):
        await _say(city, citizen, f"cancel offer_id={offer_id} reason=facility_cancelled")
    await _advance(city, message, chat, fixed=fixed, replacing=True)




# --- X-31: map — how the citizen reaches the facility --------------------------------------
_WHERE_FIELDS = "address,disability,car,car_euro_class"
_BOOKED_AT: OrderedDict[str, str] = OrderedDict()
_DOORS: dict[str, tuple[float, float, str]] = {}
_ANSWERED_WHERE: set[str] = set()
# Fallback doors (Index cards carry the exact coordinates; these are used only if find fails).
_DOOR_FALLBACK = {
    "agent:jdj692g4145e": (45.5155, 9.1835, "Via Arganini Gerolamo 38"),
    "agent:jmjfst55vgjz": (45.5106, 9.1867, "Viale Ca' Granda 28"),
    "agent:mm18nddkfc5w": (45.5080, 9.1950, "Via Giolli Raffaello 23"),
}
_NUM = re.compile(r"-?\d{1,2}\.\d{3,}")


def _asked_where(chat: list[Message], agent: str, message: Message) -> bool:
    """True when our last word to this citizen was the X-31 data.request, still unanswered."""
    if message.need_id and message.need_id in _ANSWERED_WHERE:
        return False
    last = None
    for row in chat:
        if row.sender == agent and row.recipient == message.sender:
            last = row
    return last is not None and "data.request" in words(last.text) and "fields=" + _WHERE_FIELDS in last.text.split()


async def _door(city: City, facility: str) -> tuple[float, float, str] | None:
    if facility in _DOORS:
        return _DOORS[facility]
    try:
        peers = await asyncio.wait_for(city.find("ospedale specialista consultorio asst-niguarda"), timeout=4.0)
    except Exception:
        peers = []
    for peer in peers:
        addr = getattr(peer, "address", None)
        if addr is not None and getattr(addr, "lat", None) is not None:
            _DOORS[peer.agent_id] = (float(addr.lat), float(addr.lon), str(addr.label))
    return _DOORS.get(facility) or _DOOR_FALLBACK.get(facility)


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def _citizen_point(text: str) -> tuple[float, float] | None:
    fields = fields_of(text)
    lat, lon = fields.get("lat") or fields.get("latitude"), fields.get("lon") or fields.get("lng") or fields.get("longitude")
    try:
        if lat and lon:
            return float(lat), float(lon)
    except ValueError:
        pass
    nums = [float(n) for n in _NUM.findall(text)]
    pair = [n for n in nums if 44.0 < n < 47.0], [n for n in nums if 8.0 < n < 10.5]
    if pair[0] and pair[1]:
        return pair[0][0], pair[1][0]
    return None


def _route_line(en: bool, km: float | None, door: tuple[float, float, str] | None, fields: dict[str, str]) -> str:
    street = door[2] if door else ("the facility" if en else "la struttura")
    out: list[str] = []
    if km is None:
        out.append(
            f"The visit is at {street}, near the M5 metro (Ca' Granda stop) and several ATM bus lines."
            if en else
            f"La visita è in {street}, vicino alla metro M5 (fermata Ca' Granda) e a diverse linee ATM."
        )
    elif km < 1.2:
        mins = max(5, round(km * 13))
        out.append(
            f"{street} is about {km:.1f} km from you: an easy walk of about {mins} minutes."
            if en else
            f"{street} è a circa {km:.1f} km da lei: una passeggiata di circa {mins} minuti."
        )
    else:
        mins = round(10 + km * 4)
        out.append(
            f"{street} is about {km:.1f} km from you: by public transport (M5 metro, Ca' Granda stop, "
            f"or ATM buses) it takes about {mins} minutes; please allow some extra time."
            if en else
            f"{street} è a circa {km:.1f} km da lei: con i mezzi pubblici (metro M5, fermata Ca' Granda, "
            f"o bus ATM) servono circa {mins} minuti; tenga un po' di margine."
        )
    disability = fields.get("disability", "none").lower()
    if disability == "motor":
        out.append("The building is wheelchair accessible; our staff can meet you at the entrance." if en
                   else "La struttura è accessibile in sedia a rotelle; il nostro personale può accoglierla all'ingresso.")
    elif disability in {"visual", "hearing", "cognitive"}:
        out.append("Tell the front desk when you arrive: someone will accompany you to the visit." if en
                   else "All'arrivo lo dica all'accoglienza: qualcuno la accompagna fino alla visita.")
    car = fields.get("car", "").lower() == "true"
    euro = fields.get("car_euro_class", "")
    if car:
        old = euro[-1:].isdigit() and int(euro[-1]) <= 4
        out.append(
            (f"If you come by car: with a {euro} vehicle check the Area B limits first; public transport is "
             "easier and greener." if old else "If you come by car, check Area B and parking nearby; public "
             "transport is often easier and greener.")
            if en else
            (f"Se viene in auto: con un'auto {euro} controlli prima i limiti di Area B; i mezzi pubblici sono "
             "più comodi e inquinano meno." if old else "Se viene in auto, controlli Area B e i parcheggi "
             "vicini; spesso i mezzi pubblici sono più comodi e inquinano meno.")
        )
    out.append("See you at the visit!" if en else "A presto alla visita!")
    return " ".join(out)


async def _on_where(city: City, message: Message, chat: list[Message]) -> None:
    key = message.need_id or message.msg_id
    if key in _ANSWERED_WHERE:
        return
    _ANSWERED_WHERE.add(key)
    facility = _BOOKED_AT.get(key) or next(
        (row.sender for row in reversed(chat) if row.sender.startswith("agent:") and "booking.receipt" in words(row.text)),
        "agent:jdj692g4145e",
    )
    door = await _door(city, facility)
    point = _citizen_point(message.text)
    km = _km(point, door[:2]) if point and door else None
    en = _lang(chat) != "it"
    head = "Thank you." if en else "Grazie."
    if km is None and "address" not in fields_of(message.text):
        head = "No problem." if en else "Nessun problema."
    extra = await _nearest_line(city, point, en, facility) if point else ""
    await _say(city, message.sender, f"{head} {_route_line(en, km, door, fields_of(message.text))}{extra}")


async def _nearest_line(city: City, point: tuple[float, float], en: bool, booked: str) -> str:
    """X-32: the nearest hospital in the whole city (any ASST), from the Index doors."""
    try:
        peers = await asyncio.wait_for(city.find("ospedale hospital pronto soccorso Milano"), timeout=4.0)
    except Exception:
        return ""
    best: tuple[float, str] | None = None
    for peer in peers:
        addr = getattr(peer, "address", None)
        if addr is None or getattr(addr, "lat", None) is None:
            continue
        if "hospital" not in (peer.role or "") and not any("hospital" in c for c in peer.capabilities):
            continue
        d = _km(point, (float(addr.lat), float(addr.lon)))
        if best is None or d < best[0]:
            best = (d, str(addr.label))
    if best is None:
        return ""
    if en:
        return f" For any urgent need, the nearest hospital to you is at {best[1]}, about {best[0]:.1f} km away; in an emergency always call 112."
    return f" Per qualsiasi urgenza, l'ospedale più vicino a lei è in {best[1]}, a circa {best[0]:.1f} km; in emergenza chiami sempre il 112."


async def _citizen_cancel(
    city: City, message: Message, chat: list[Message], *, fixed: str | None
) -> None:
    """X-34: the citizen drops an offer (often reason=deadline). Never stay silent: acknowledge,
    then offer the next free slots that fit, or the waiting list."""
    offer_id = fields_of(message.text).get("offer_id", "")
    key = f"cancel:{message.need_id or message.msg_id}:{offer_id}"
    sent = _sent(key)
    if "ack" in sent.offers:
        return
    sent.offers.add("ack")
    en = _lang(chat) != "it"
    await _say(
        city,
        message.sender,
        (f"cancel.ack offer_id={offer_id} " if offer_id else "")
        + (
            "Understood, no problem: I have released that slot. I am checking right now for "
            "other free appointments within your prescription time and will send them to you."
            if en
            else "Capito, nessun problema: ho liberato quel posto. Cerco subito altri appuntamenti "
            "liberi nei tempi della sua ricetta e glieli mando."
        ),
    )
    await _advance(city, message, chat, fixed=fixed, replacing=False)
