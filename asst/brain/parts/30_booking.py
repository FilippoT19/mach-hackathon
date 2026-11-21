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
        reply = None
    if reply is None and number:
        # BK-28: the Ledger may not answer in time. The GP's referral (or the prescription the GP
        # sent) carries procedure and priority for the same number: use it, never stay silent.
        for row in reversed(chat):
            if row.sender == LEDGER or not row.sender.startswith("agent:"):
                continue
            f = fields_of(row.text)
            if f.get("prescription_number") == number and f.get("procedure") and f.get("priority"):
                return {"prescription_number": number, "procedure": f["procedure"],
                        "priority": f["priority"], "state": "issued"}
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
    return (int(left), int(left)) if left.isdigit() else (1, 1)


def _slots_page(chat: list[Message], agent: str, page: int) -> Message | None:
    return next((row for row in reversed(chat)
                 if row.sender == LEDGER and row.recipient == agent and first_word(row.text) == "slots"
                 and _page(row.text)[0] == page), None)


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
        fields = fields_of(row.text)
        if row.sender.startswith("agent:") and row.sender != agent and not _expected_confirm_reply(
            chat, agent, row.sender, fields
        ):
            continue
        slot = by_offer.get(fields.get("offer_id", ""))
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
    decision: tuple[bool | None, str] = (None, "")
    for row in chat:
        fields = fields_of(row.text)
        head = first_word(row.text)
        if row.sender == agent and head == "consent" and fields.get("purpose") == "cross_asst":
            asked = True
            decision = (None, "")
            continue
        if not asked or decision[0] is not None or not row.sender.startswith("citizen:"):
            continue
        if head == "data.response" and fields.get("purpose") == "cross_asst":
            # BK-36: the citizen grants the cross-ASST consent as a data.response (000175).
            decision = (True, fields.get("consent_ref") or f"cx-{row.need_id or row.msg_id}")
            continue
        if fields.get("purpose") not in (None, "cross_asst") or head in {"confirm", "cancel", "data.response", "need.request"}:
            continue
        consent = fields.get("consent_ref", "")
        if consent:
            decision = (True, consent)
        elif head == "consent" or re.match(
            r"^(?:no|non\s+voglio|non\s+acconsento|rifiuto|rifiutato|preferisco\s+di\s+no|"
            r"i\s+(?:refuse|decline)|i\s+do\s+not\s+consent)\b", row.text.strip().lower()
        ):
            decision = (False, "")
    return decision


def _cross_replies(chat: list[Message], agent: str, request_id: str) -> list[Message]:
    return [
        row for row in chat
        if row.sender.startswith("agent:") and row.recipient == agent
        and first_word(row.text) in {"offer", "cancel"}
        and fields_of(row.text).get("request_id") == request_id
    ]


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

    __slots__ = ("offers", "trigger", "again", "replacement_page", "citizen_replacement", "cross_asked", "cross_sent",
                 "cross_peers", "partner_offers")

    def __init__(self) -> None:
        self.offers: set[str] = set()
        self.trigger = ""
        self.again: set[str] = set()
        self.replacement_page = None
        self.citizen_replacement = False
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


# X-51: hospital of the ASST whose h3 physiatrist speaks a rare language (ids from the groups).
_RARE_LANG_HOSPITAL = {
    "ka": ("agent:h6r1v45esk77", "Giambellino", "georgiano", "Georgian"),
    "ur": ("agent:gpr1zqe343gb", "Nord", "urdu", "Urdu"),
    "fr": ("agent:x0vr9rbwpesr", "Corvetto", "francese", "French"),
    "ja": ("agent:nanpr5mgm2py", "Lambrate", "giapponese", "Japanese"),
    "si": ("agent:xtj1dk9x3qej", "Greco", "singalese", "Sinhala"),
    "ti": ("agent:bb01ggxymm05", "Bicocca", "tigrino", "Tigrinya"),
}


def _rare_hospital(chat: list[Message], procedure: str | None) -> tuple[str, str, str, str] | None:
    if procedure != "VIS-FIS":
        return None
    return _RARE_LANG_HOSPITAL.get(_lang(chat) or "")


def _cross_question(chat: list[Message], procedure: str | None = None) -> str:
    rare = _rare_hospital(chat, procedure)
    if rare:
        return (f"May I ask the ASST {rare[1]} for you? Their physiatrist speaks {rare[3]}. "
                "Please reply with your consent reference."
                if _lang(chat) != "it" else
                f"Posso chiedere per lei all'ASST {rare[1]}, dove il fisiatra parla {rare[2]}? "
                "Mi risponda con il riferimento del suo consenso.")
    return ("May I look for an appointment in another ASST? Please reply with your consent reference."
            if _lang(chat) != "it" else
            "Posso cercare un appuntamento in un'altra ASST? Mi risponda con il riferimento del suo consenso.")


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
        if await _say(city, citizen, "consent purpose=cross_asst " + _cross_question(chat, procedure)):
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
    rare = _rare_hospital(chat, procedure)
    ordered: list[object] = [rare[0]] if rare else []  # X-51: the rare-language ASST first
    for peer in [*ordered, *(peers or [])]:
        target = peer if isinstance(peer, str) else _peer_id(peer)
        if not target or target == city.agent_id or _ours(target) or target in sent.cross_peers:
            continue
        if not isinstance(peer, str):
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
        # X-44: the citizen's criteria travel with the request (no personal data).
        want_lang = _lang(chat)
        if want_lang and want_lang != "it":
            parts.append(f"lang={want_lang}")
        want_gender = _gender(chat)
        if want_gender:
            parts.append(f"gender={want_gender} gender_preference={want_gender}")
        want_days = _days(chat)
        if want_days:
            parts.append("days=" + "/".join(sorted(want_days)))
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
        lambda rows: sent.cross_peers <= {
            row.sender for row in _cross_replies(rows, city.agent_id, request_id)
        },
    )
    replies = _cross_replies(fresh, city.agent_id, request_id)
    if await _partner_offer(city, replies, fresh, key):
        return True
    if sent.cross_peers - {row.sender for row in replies}:
        await _say(city, citizen, "booking.search " + (
            "I have asked other ASSTs for availability and am waiting for their replies."
            if _lang(chat) != "it" else
            "Ho chiesto disponibilità alle altre ASST e aspetto le loro risposte."))
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


_PARTNER_OFFER_FIELDS = ("offer_id", "slot_id", "doctor_id", "facility", "procedure", "agenda_date",
                         "agenda_day", "priority", "prescription_number", "expiry")


def _expected_offer(chat: list[Message], agent: str, message: Message, sent: _Sent) -> bool:
    if not _TRUSTED_PARTNERS:
        return True
    request_id = fields_of(message.text).get("request_id", "")
    return message.sender in sent.cross_peers or (
        bool(request_id) and _we(chat, agent, f"request_id={request_id}", to=message.sender, word="need.request")
    )


def _expected_confirm_reply(
    chat: list[Message], agent: str, sender: str, fields: dict[str, str],
) -> bool:
    if not _TRUSTED_PARTNERS:
        return True
    return any(
        row.sender == agent and row.recipient == sender
        and first_word(row.text) == "confirm" and "slot_id" in (confirm := fields_of(row.text))
        and all(confirm.get(key) == fields[key] for key in ("offer_id", "slot_id") if key in fields)
        for row in chat
    )


async def _partner_offer(city: City, replies: list[Message], chat: list[Message], key: str) -> bool:
    """Send the first batch of matching remote offers, with citizen-facing fields only."""

    citizen = _citizen(chat)
    if not citizen:
        return False
    sent = _sent(key)
    if sent.partner_offers or _we(chat, city.agent_id, "cross_asst=true", to=citizen, word="offer"):
        return True
    lang = _lang(chat)
    lines: dict[str, str] = {}
    for reply in replies:
        if first_word(reply.text) != "offer" or not _expected_offer(chat, city.agent_id, reply, sent):
            continue
        for line in reply.text.splitlines():
            if first_word(line) != "offer":
                continue
            fields = fields_of(line)
            offer_id = fields.get("offer_id", "")
            if not offer_id or not fields.get("slot_id") or not fields.get("facility"):
                continue
            if fields.get("doctor_lang") and lang.lower() not in re.split(r"[/|+]", fields["doctor_lang"].lower()):
                continue
            # Only emit identifiers and protocol values, never delimiters that can introduce tokens.
            values = {name: fields[name] for name in _PARTNER_OFFER_FIELDS
                      if name in fields and "=" not in fields[name]}
            if not all(name in values for name in ("offer_id", "slot_id", "facility")):
                continue
            tokens = [f"{name}={value}" for name, value in values.items()]
            lines.setdefault(offer_id, " ".join(["offer", *tokens, "cross_asst=true"]))
    if not lines:
        return False
    line = (
        "Here are the available appointments in other ASSTs. Reply with the offer you prefer."
        if lang != "it" else
        "Ecco gli appuntamenti disponibili in altre ASST. Mi risponda con l'offerta che preferisce."
    )
    if await _say(city, citizen, "\n".join([*lines.values(), line])):
        sent.partner_offers.update(lines)
        return True
    return False


async def _partner_reply(city: City, message: Message, chat: list[Message], fixed: str | None) -> None:
    key = message.need_id or message.msg_id
    sent = _sent(key)
    head = first_word(message.text)
    if not _expected_offer(chat, city.agent_id, message, sent):
        await _say(city, message.sender, f"{head}.ack status=ignored reason=unexpected_partner")
        return
    await _say(city, message.sender, f"{head}.ack status=received")
    async with _need_gate(_GATES, key):
        request_id = f"cross-{key}"
        if not sent.cross_peers or fields_of(message.text).get("request_id") != request_id:
            await _partner_offer(city, [message], chat, key)
            return
        # Include replies that arrived while the original search held the lock.
        try:
            chat = _keep(await city.history(need_id=message.need_id), chat)
        except CapError:
            pass
        replies = _cross_replies(chat, city.agent_id, request_id)
        if await _partner_offer(city, replies, chat, key):
            return
        if sent.cross_peers <= {reply.sender for reply in replies}:
            citizen = _citizen(chat)
            number = _number(chat)
            rx = _prescription_reply(chat, number) or {}
            procedure = fixed or rx.get("procedure")
            if citizen and procedure:
                await _relaxed(city, message, chat, key, citizen, procedure, number, rx.get("priority"))


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
    head = first_word(message.text)
    fields = fields_of(message.text)
    if message.sender.startswith("citizen:"):
        purpose = fields.get("purpose")
        cross_pending = (
            purpose is None and head not in {"confirm", "cancel", "need.request", "data.response"}
            and any(row.sender == city.agent_id and first_word(row.text) == "consent"
                    and fields_of(row.text).get("purpose") == "cross_asst" for row in chat)
            and _cross_consent([row for row in chat if row.msg_id != message.msg_id], city.agent_id)[0] is None
        )
        if purpose == "cross_asst" or cross_pending:
            if _cross_consent(chat, city.agent_id)[0] is None:
                await _say(city, message.sender, "consent purpose=cross_asst " + _cross_question(
                    chat, (_prescription_reply(chat, _number(chat)) or {}).get("procedure")))
            else:
                await _advance(city, message, chat, fixed=fixed, replacing=False)
            return
        if head == "consent" and purpose in (None, "booking"):
            await _on_confirm(city, message, chat, hold_self=hold_self)
            return
    agent_first = first_word(message.text) if message.sender.startswith("agent:") else ""
    if "confirm" in kind and (
        message.sender.startswith("citizen:") or agent_first == "confirm"
    ):
        await _on_confirm(city, message, chat, hold_self=hold_self)
        return
    if message.sender.startswith("agent:") and (
        head == "offer" or (head == "cancel" and fields.get("request_id") and not fields.get("offer_id"))
    ):
        await _partner_reply(city, message, chat, fixed)
        return
    if "booking.receipt" in kind and message.sender.startswith("agent:"):
        await _forward_receipt(city, message, chat)
        return
    if message.sender.startswith("citizen:") and _asked_where(chat, city.agent_id, message):
        await _on_where(city, message, chat)
        return
    if first_word(message.text) == "data.response" and (message.need_id or message.msg_id) in _ANSWERED_WHERE:
        return  # BK-28: a repeated address reply is already answered
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


@asynccontextmanager
async def _need_gate(gates: dict, key):
    gate = gates.setdefault(key, _Gate())
    gate.turns += 1
    try:
        async with gate.lock:
            yield
    finally:
        gate.turns -= 1
        if not gate.turns:
            del gates[key]


async def _advance(
    city: City,
    message: Message,
    chat: list[Message],
    *,
    fixed: str | None,
    replacing: bool,
) -> None:
    key = message.need_id or message.msg_id
    async with _need_gate(_GATES, key):
        await _advance_alone(city, message, chat, key, fixed=fixed, replacing=replacing)
        sent = _sent(key)
        # Some Ledger replies only land in history. The push, if it also opens a
        # turn, will find the page already processed under this same lock.
        while sent.replacement_page is not None:
            page = sent.replacement_page
            fresh = await _until(
                city, message.need_id, chat, lambda rows: _slots_page(rows, city.agent_id, page) is not None,
            )
            reply = _slots_page(fresh, city.agent_id, page)
            if reply is None:
                break
            chat = fresh
            await _advance_alone(city, reply, chat, key, fixed=fixed, replacing=False)
            if sent.replacement_page == page:
                break


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
            await _relaxed(city, message, chat, key, citizen, procedure, number, priority)
            return
        procedure = fixed or (None if reply is None else reply.get("procedure"))
        number = _number(chat)
        if fixed is None and number and not procedure:
            if _pass == 2:
                # BK-28: never mute. Tell the citizen we are checking and will write again.
                if not _we(chat, agent, "", to=citizen, word="prescription.wait"):
                    en = _lang(chat) != "it"
                    await _say(city, citizen, "prescription.wait " + (
                        "I have your request and I am checking your prescription with the regional "
                        "register right now. I will send you the free appointments in a moment."
                        if en else
                        "Ho la sua richiesta e sto verificando la ricetta nel registro regionale. "
                        "Tra un momento le mando i posti liberi adatti a lei."))
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
        replacement_reply = (
            message.sender == LEDGER and first_word(message.text) == "slots"
            and _sent(key).replacement_page == _page(message.text)[0]
        )
        world = message.text if replacement_reply else _latest_slots(chat)
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
    page, pages = _page(world)
    if replacing:
        trigger = message.msg_id
        if sent.trigger != trigger:
            sent.trigger = trigger
            sent.again.clear()
            sent.replacement_page = None
            sent.citizen_replacement = message.sender == citizen
    elif message.sender == LEDGER and first_word(message.text) == "slots":
        replacing = sent.replacement_page == _page(message.text)[0] == page
    if replacing:
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
            if replacing:
                sent.replacement_page = None
            for slot in picks:
                sent.offers.add(slot["slot_id"])
                if replacing:
                    sent.again.add(slot["slot_id"])
        return
    if taken and not replacing:
        if message.sender.startswith("citizen:") and "again" not in sent.offers:
            # BK-22: the citizen writes again after our offers: never silence, repeat them once.
            last = next((r.text for r in reversed(chat) if r.sender == agent and r.recipient == citizen and "offer" in words(r.text)), None)
            if last:
                sent.offers.add("again")
                await _say(city, citizen, last)
        return
    if page < pages and page < _MAX_PAGE:
        if replacing:
            sent.replacement_page = page + 1
        if not _asked(chat, agent, procedure, page + 1):
            await _say(city, LEDGER, f"world procedure={procedure} page={page + 1}")
            if page == 1 and "wait" not in sent.offers:
                # BK-30: a long catalogue takes many Ledger turns; never leave the citizen silent.
                sent.offers.add("wait")
                await _say(
                    city,
                    citizen,
                    "I have your request and I am checking every free appointment for you now; "
                    "I will write again in a moment."
                    if _lang(chat) != "it"
                    else "Ho la sua richiesta e sto controllando tutti i posti liberi per lei; "
                    "le riscrivo tra un momento.",
                )
        # BK-37: the Ledger's next page may never open a turn (the push is dropped), so the
        # citizen waited for ever after "I am checking". Read it back now and go on in this turn.
        nxt = page + 1
        if _slots_page(chat, agent, nxt) is None:
            chat = await _until(city, message.need_id, chat, lambda rows: _slots_page(rows, agent, nxt) is not None)
        if _slots_page(chat, agent, nxt) is not None and _page(_latest_slots(chat) or "")[0] == nxt:
            await _advance_alone(city, message, chat, key, fixed=fixed, replacing=replacing)
        return
    # Search another ASST only after the complete local catalogue has been exhausted.
    if replacing:
        sent.replacement_page = None
    citizen_replacement = replacing and sent.citizen_replacement
    if (not citizen_replacement or _cross_consent(chat, agent)[0] is True) and await _cross_asst(
        city, message, chat, key, citizen, procedure, priority
    ):
        return
    # BK-10: every page read and no partner can serve it. The waiting list is the safe fallback.
    await _relaxed(city, message, chat, key, citizen, procedure, number, priority)


async def _relaxed(
    city: City,
    message: Message,
    chat: list[Message],
    key: str,
    citizen: str,
    procedure: str | None,
    number: str | None,
    priority: str | None,
) -> None:
    offer_id = f"wl-{message.need_id or message.msg_id}"
    sent = _sent(key)
    if offer_id in sent.offers or _we(chat, city.agent_id, f"offer_id={offer_id}", to=citizen, word="offer"):
        return
    line = (
        "You are on the waiting list. If you need an earlier appointment, write to us again. "
        "If your symptoms change, contact your GP."
        if _lang(chat) != "it" else
        "È in lista d'attesa. Se le serve un appuntamento prima, ci riscriva. "
        "Se il disturbo cambia, contatti il suo medico di base."
    )
    parts = ["offer", f"offer_id={offer_id}", "waiting_list=true"]
    if procedure:
        parts.append(f"procedure={procedure}")
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
    if message.sender.startswith("citizen:") and first_word(message.text) == "consent" and not offer_id:
        # A purpose-only response belongs to the latest booking consent question.
        pending = next(
            (fields_of(row.text) for row in reversed(chat) if row.sender == agent
             and row.recipient == message.sender and first_word(row.text) == "consent"
             and ((request := fields_of(row.text)).get("purpose") == "booking"
                  or request.get("consent_required") == "true")
             and (not fields.get("slot_id") or request.get("slot_id") == fields["slot_id"])),
            {},
        )
        if pending:
            offer_id = pending.get("offer_id", "")
            fields = {**pending, **fields}
    offer = _our_offer(chat, agent, offer_id) if offer_id else {}
    slot = fields.get("slot_id") or offer.get("slot_id", "")
    facility = fields.get("facility") or offer.get("facility", "")
    if message.sender.startswith("agent:") and (not slot or not consent):
        # FA-01 (P-francesco-5): a confirm from an agent without slot or consent never gets silence;
        # the consent belongs to the booking centre, so we answer the sender and it can resend.
        why = "missing_slot_id" if not slot else "missing_consent_ref"
        if not _we(chat, agent, f"reason={why}", to=message.sender, word="cancel"):
            await _say(city, message.sender, f"cancel offer_id={offer_id} reason={why} "
                       f"Manca {why.split('_', 1)[1]}: rimandate il confirm completo e blocchiamo subito il posto.")
        return
    if not slot:
        if message.sender.startswith("citizen:"):
            await _say(city, message.sender, "Please send me the offer number to book your appointment."
                       if _lang(chat) != "it" else
                       "Mi scriva il numero dell'offerta per prenotare l'appuntamento.")
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
        line = (
            "To book this appointment, please reply with your consent reference."
            if _lang(chat) != "it" else
            "Per prenotare questo appuntamento, mi risponda con il riferimento del suo consenso."
        )
        parts = ["consent", "purpose=booking"]
        if offer_id:
            parts.append(f"offer_id={offer_id}")
        parts.append(f"slot_id={slot}")
        if facility:
            parts.append(f"facility={facility}")
        await _say(city, citizen, " ".join(parts) + f" {line}")
        return
    number = fields.get("prescription_number") or offer.get("prescription_number")
    procedure = fields.get("procedure") or offer.get("procedure", "")
    book_here = hold_self or message.sender.startswith("agent:") or facility == agent
    if book_here:
        if message.sender.startswith("agent:"):
            _remember_booking_request(agent, message.need_id, slot, message.sender)
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
    if offer.get("cross_asst") == "true" or target not in _OUR_AGENTS.values():
        accepted, cross_ref = _cross_consent(chat, agent)
        if accepted and cross_ref:
            parts.append(f"cross_asst_consent_ref={cross_ref}")  # common format between ASSTs
    await _say(city, target, " ".join(parts))


_RECEIPT_GATES: dict[tuple[str, str], _Gate] = {}
_RECEIPTS: OrderedDict[tuple[str, str | None, str], None] = OrderedDict()


@asynccontextmanager
async def _receipt_turn(city: City, message: Message, chat: list[Message], booking_id: str):
    key = (city.agent_id, message.need_id, booking_id)
    async with _need_gate(_RECEIPT_GATES, (city.agent_id, message.need_id or booking_id)):
        if key in _RECEIPTS:
            yield None
            return
        try:
            chat = _keep(await city.history(need_id=message.need_id), chat)
        except CapError:
            pass
        yield chat


def _remember_receipt(agent: str, need_id: str | None, booking_id: str) -> None:
    _RECEIPTS[agent, need_id, booking_id] = None
    if len(_RECEIPTS) > _SENT_NEEDS:
        _RECEIPTS.popitem(last=False)


async def _forward_receipt(city: City, message: Message, chat: list[Message]) -> None:
    fields = fields_of(message.text)
    booking_id = fields.get("booking_id", "")
    ledger_ref = fields.get("ledger_ref", "")
    if not booking_id or not ledger_ref:
        await _say(city, message.sender, "booking.receipt.ack status=ignored reason=missing_fields")
        return
    async with _receipt_turn(city, message, chat, booking_id) as fresh:
        if fresh is None:
            await _say(city, message.sender, "booking.receipt.ack status=received")
        elif not _expected_confirm_reply(fresh, city.agent_id, message.sender, fields):
            await _say(city, message.sender, "booking.receipt.ack status=ignored reason=unexpected_partner")
        else:
            await _say(city, message.sender, "booking.receipt.ack status=received")
            await _send_forwarded_receipt(city, message, fresh, booking_id, ledger_ref)


async def _send_forwarded_receipt(
    city: City, message: Message, chat: list[Message], booking_id: str, ledger_ref: str,
) -> None:
    citizen = _citizen(chat)
    if not citizen:
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
    # G5 / G10 collaboration: tell the GP first, then say it in the receipt (the review reads only
    # the citizen chat, so the agent-to-agent step must be visible there).
    gp = await _peer(city, "gp", "medico di base gp asst-niguarda")
    if gp and gp != city.agent_id and not _we(chat, city.agent_id, token, to=gp, word="booking.notice"):
        number = _number(chat) or ""
        if await _say(city, gp, f"booking.notice {token} ledger_ref={ledger_ref} facility={message.sender} "
                      + (f"prescription_number={number} " if number else "")
                      + "Visita prenotata e confermata per il vostro paziente: vi avvisiamo per il controllo dopo il referto."):
            line += (" I have also informed your GP about this booking myself, so they can follow up after the visit."
                     if _lang(chat) != "it" else
                     " Ho anche avvisato io il suo medico di base della prenotazione, così potrà seguirla dopo la visita.")
    if not await _say(
        city,
        citizen,
        f"booking.receipt booking_id={booking_id} ledger_ref={ledger_ref} {line} "
        + await _zone_route(city, chat, message.sender)
        + _prep_line((_prescription_reply(chat, _number(chat)) or {}).get("procedure", ""), _lang(chat) != "it"),  # P-02
    ):
        return
    _remember_receipt(city.agent_id, message.need_id, booking_id)
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
    if not _expected_confirm_reply(chat, city.agent_id, message.sender, fields):
        await _say(city, message.sender, "cancel.ack status=ignored reason=unexpected_partner")
        return
    await _say(city, message.sender, "cancel.ack status=received")
    offer_id = fields.get("offer_id", "")
    if offer_id.lower() in {"none", "null", "-"}:
        offer_id = ""  # BK-32: "offer_id=none" from a partner means no offer of ours
    citizen = _citizen(chat)
    if (
        offer_id
        and citizen
        and not _we(chat, city.agent_id, f"offer_id={offer_id}", to=citizen, word="cancel")
    ):
        reason = fields.get("reason") or "facility_cancelled"
        await _say(city, citizen, f"cancel offer_id={offer_id} reason={reason}")
    if not offer_id:
        return  # P-francesco-26: a partner with no places changes nothing; no new burst of offers
    await _advance(city, message, chat, fixed=fixed, replacing=True)




# --- X-31: map — how the citizen reaches the facility --------------------------------------
_WHERE_FIELDS = "address,disability,car,car_euro_class"
_BOOKED_AT: OrderedDict[str, str] = OrderedDict()
_DOORS: dict[str, tuple[float, float, str]] = {}
_ANSWERED_WHERE: set[str] = set()
# Fallback doors (Index cards carry the exact coordinates; these are used only if find fails).
_DOOR_FALLBACK = {
    "agent:jdj692g4145e": (45.51774, 9.19626, "Via Arganini Gerolamo 38"),
    "agent:jmjfst55vgjz": (45.50815, 9.19427, "Viale Ca' Granda 28"),
    "agent:mm18nddkfc5w": (45.52628, 9.21068, "Via Giolli Raffaello 23"),
}
_NUM = re.compile(r"-?\d{1,2}\.\d{3,}")

# Milan metro stops (Comune di Milano open data, ds535 ATM fermate metropolitane): lat, lon, name, lines.
_METRO_STOPS: tuple[tuple[float, float, str, str], ...] = (
    (45.40175, 9.14554, 'Assago Milanofiori Forum', '2'),
    (45.40945, 9.15005, 'Assago Milanofiori Nord', '2'),
    (45.42921, 9.25623, 'San Donato', '3'),
    (45.42999, 9.17732, 'Abbiategrasso', '2'),
    (45.43359, 9.23809, 'Rogoredo Fs', '3'),
    (45.4369, 9.16801, 'Famagosta', '2'),
    (45.43713, 9.23031, 'Porto Di Mare', '3'),
    (45.44041, 9.22347, 'Corvetto', '3'),
    (45.44236, 9.12977, 'San Cristoforo', '4'),
    (45.44281, 9.21848, 'Brenta', '3'),
    (45.44373, 9.16768, 'Romolo', '2'),
    (45.44654, 9.13057, 'Segneri', '4'),
    (45.44676, 9.21082, 'Lodi T.I.B.B.', '3'),
    (45.44962, 9.13572, 'Gelsomini', '4'),
    (45.45143, 9.2034, 'Porta Romana', '3'),
    (45.45182, 9.14245, 'Frattini', '4'),
    (45.45238, 9.16961, 'P.Ta Genova F.S.', '2'),
    (45.4536, 9.14802, 'Tolstoj', '4'),
    (45.45532, 9.15315, 'Bolivar', '4'),
    (45.45538, 9.11293, 'Bisceglie', '1'),
    (45.45627, 9.18818, 'Santa Sofia', '4'),
    (45.45655, 9.1951, 'Crocetta', '3'),
    (45.45713, 9.18232, 'Vetra', '4'),
    (45.45755, 9.16006, 'California', '4'),
    (45.45756, 9.12226, 'Inganni', '1'),
    (45.45862, 9.16981, 'S.Agostino', '2'),
    (45.45876, 9.178, 'De Amicis', '4'),
    (45.45909, 9.16491, 'Coni Zugna', '4'),
    (45.45941, 9.12926, 'Primaticcio', '1'),
    (45.45972, 9.19547, 'Sforza-Policlinico', '4'),
    (45.46011, 9.18903, 'Missori', '3'),
    (45.4615, 9.13648, 'Bande Nere', '1'),
    (45.46162, 9.17317, 'S.Ambrogio', '2'),
    (45.46182, 9.17322, 'San Ambrogio', '4'),
    (45.46201, 9.24039, 'Repetti', '4'),
    (45.46285, 9.2779, 'Linate Aeroporto', '4'),
    (45.4639, 9.18861, 'Duomo', '3'),
    (45.46431, 9.23635, 'Stazione Forlanini', '4'),
    (45.46462, 9.1896, 'Duomo', '1'),
    (45.4649, 9.14303, 'Gambara', '1'),
    (45.46553, 9.18624, 'Cordusio', '1'),
    (45.46643, 9.14957, 'De Angeli', '1'),
    (45.46652, 9.19753, 'San Babila', '1,4'),
    (45.46753, 9.16649, 'Conciliazione', '1'),
    (45.4679, 9.20777, 'Tricolore', '4'),
    (45.46795, 9.15591, 'Wagner', '1'),
    (45.46799, 9.21845, 'Dateo', '4'),
    (45.46807, 9.22488, 'Susa', '4'),
    (45.46813, 9.23196, 'Argonne', '4'),
    (45.46816, 9.1771, 'Cadorna Fn', '2'),
    (45.4682, 9.17643, 'Cadorna Fn', '1'),
    (45.46828, 9.1611, 'Pagano', '1'),
    (45.46837, 9.18203, 'Cairoli', '1'),
    (45.47001, 9.19285, 'Montenapoleone', '3'),
    (45.4704, 9.15529, 'Buonarroti', '1'),
    (45.47143, 9.20195, 'Palestro', '1'),
    (45.47223, 9.18255, 'Lanza', '2'),
    (45.47368, 9.15097, 'Amendola', '1'),
    (45.47442, 9.20505, 'P.Ta Venezia', '1'),
    (45.47504, 9.19471, 'Turati', '3'),
    (45.47621, 9.12901, 'San Siro Ippodromo', '5'),
    (45.47626, 9.11832, 'San Siro Stadio', '5'),
    (45.47636, 9.13789, 'Segesta', '5'),
    (45.47744, 9.18448, 'Moscova', '2'),
    (45.47814, 9.15668, 'Tre Torri', '5'),
    (45.47915, 9.14375, 'Lotto Fieramilanocity', '1'),
    (45.47978, 9.14367, 'Lotto', '5'),
    (45.48009, 9.19886, 'Repubblica', '3'),
    (45.48035, 9.21098, 'Lima', '1'),
    (45.4808, 9.1515, 'Portello', '5'),
    (45.48115, 9.22592, 'Piola', '2'),
    (45.48162, 9.16226, 'Domodossola', '5'),
    (45.48364, 9.18674, 'Garibaldi Fs', '2,5'),
    (45.48425, 9.23483, 'Lambrate Fs', '2'),
    (45.48444, 9.20261, 'Centrale Fs', '2,3'),
    (45.48452, 9.16678, 'Gerusalemme', '5'),
    (45.48459, 9.21517, 'Loreto', '2'),
    (45.48481, 9.17979, 'Monumentale', '5'),
    (45.4849, 9.19486, 'Gioia', '2'),
    (45.48532, 9.20941, 'Caiazzo', '2'),
    (45.48596, 9.13718, 'Qt8', '1'),
    (45.48624, 9.21698, 'Loreto', '1'),
    (45.48749, 9.17195, 'Cenisio', '5'),
    (45.48761, 9.19126, 'Isola', '5'),
    (45.4894, 9.12732, 'Lampugnano', '1'),
    (45.48999, 9.20056, 'Sondrio', '3'),
    (45.49107, 9.21818, 'Pasteur', '1'),
    (45.4912, 9.237, 'Udine', '2'),
    (45.49266, 9.1926, 'Zara', '3,5'),
    (45.49372, 9.12055, 'Uruguay', '1'),
    (45.49553, 9.21951, 'Rovereto', '1'),
    (45.49615, 9.19482, 'Marche', '5'),
    (45.497, 9.11015, 'Bonola', '1'),
    (45.4977, 9.18504, 'Maciachini', '3'),
    (45.50004, 9.24143, 'Cimiano', '2'),
    (45.50045, 9.221, 'Turro', '1'),
    (45.50116, 9.10148, 'S.Leonardo', '1'),
    (45.50163, 9.19792, 'Istria', '5'),
    (45.50521, 9.09297, 'Molino Dorino', '1'),
    (45.50525, 9.24819, 'Crescenzago', '2'),
    (45.50554, 9.1796, 'Dergano', '3'),
    (45.50673, 9.22274, 'Gorla', '1'),
    (45.50724, 9.20111, "Ca' Granda", '5'),
    (45.5088, 9.08581, 'Pero', '1'),
    (45.51144, 9.26051, 'Cascina Gobba', '2'),
    (45.51203, 9.2245, 'Precotto', '1'),
    (45.51355, 9.17398, 'Affori Centro', '3'),
    (45.51473, 9.20537, 'Bicocca', '5'),
    (45.51578, 9.28599, 'Vimodrone', '2'),
    (45.51736, 9.29784, 'Cascina Burrona', '2'),
    (45.51745, 9.22613, 'Villa S.G.', '1'),
    (45.51984, 9.08711, 'Rho Fieramilano', '1'),
    (45.52021, 9.27493, 'Cologno Sud', '2'),
    (45.52074, 9.34597, 'Villa Fiorita', '2'),
    (45.52107, 9.33138, 'Cernusco Sul Naviglio', '2'),
    (45.52168, 9.16825, 'Affori Fn', '3'),
    (45.52186, 9.36312, 'Cassina De Pecchi', '2'),
    (45.52199, 9.20947, 'Ponale', '5'),
    (45.52348, 9.22796, 'Sesto Marelli', '1'),
    (45.5253, 9.3759, 'Bussero', '2'),
    (45.52678, 9.21218, 'Bignami', '5'),
    (45.52748, 9.28296, 'Cologno Centro', '2'),
    (45.52785, 9.38497, 'Villa Pompea', '2'),
    (45.52813, 9.16373, 'Comasina', '3'),
    (45.53416, 9.23125, 'Sesto Rondo', '1'),
    (45.5343, 9.29109, 'Cologno Nord', '2'),
    (45.53674, 9.40345, 'Gorgonzola', '2'),
    (45.54169, 9.23833, 'Sesto 1 Maggio Fs', '1'),
    (45.54208, 9.4235, 'Cascina Antonietta', '2'),
    (45.54529, 9.43663, 'Gessate', '2'),
)


def _stop_near(point: tuple[float, float] | None) -> tuple[str, str, float] | None:
    """X-50: nearest metro stop (name, lines, km) from the city open data, or None."""

    if not point:
        return None
    lat, lon = point[0], point[1]
    best = min(_METRO_STOPS, key=lambda r: (r[0] - lat) ** 2 + ((r[1] - lon) * 0.7) ** 2)
    dist = 6371 * 2 * math.asin(math.sqrt(
        math.sin(math.radians(best[0] - lat) / 2) ** 2
        + math.cos(math.radians(lat)) * math.cos(math.radians(best[0])) * math.sin(math.radians(best[1] - lon) / 2) ** 2
    ))
    return best[2], "/".join(f"M{x}" for x in best[3].split(",") if x), dist


def _stop_text(en: bool, stop: tuple[str, str, float] | None) -> str:
    if not stop:
        return "ATM buses" if en else "bus ATM"
    return (f"{stop[1]} metro, {stop[0]} stop" if en else f"metro {stop[1]}, fermata {stop[0]}")


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


def _route_line(en: bool, km: float | None, door: tuple[float, float, str] | None, fields: dict[str, str],
                origin: tuple[float, float] | None = None) -> str:
    street = door[2] if door else ("the facility" if en else "la struttura")
    out: list[str] = []
    at_door = _stop_text(en, _stop_near(door[:2] if door else None))
    mine = _stop_near(origin)
    if km is None:
        out.append(
            f"The visit is at {street}, near the {at_door} and several ATM bus lines."
            if en else
            f"La visita è in {street}, vicino alla {at_door} e a diverse linee ATM."
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
            f"{street} is about {km:.1f} km from you: by public transport "
            + (f"(from the {_stop_text(True, mine)} near you to the {at_door}) " if mine and mine[2] < 1.5 else f"({at_door}, or ATM buses) ")
            + f"it takes about {mins} minutes; please allow some extra time."
            if en else
            f"{street} è a circa {km:.1f} km da lei: con i mezzi pubblici "
            + (f"(dalla {_stop_text(False, mine)} vicino a lei alla {at_door}) " if mine and mine[2] < 1.5 else f"({at_door}, o bus ATM) ")
            + f"servono circa {mins} minuti; tenga un po' di margine."
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
    point = _citizen_point(message.text) or await _zone_point(city, chat)  # X-45
    km = _km(point, door[:2]) if point and door else None
    en = _lang(chat) != "it"
    head = "Thank you." if en else "Grazie."
    if km is None and "address" not in fields_of(message.text):
        head = "No problem." if en else "Nessun problema."
    extra = await _nearest_line(city, point, en, facility) if point else ""
    await _say(city, message.sender, f"{head} {_route_line(en, km, door, fields_of(message.text), point)}{extra}")


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
    # BK-29 (journey 129): stop the offer/cancel loop with a protocol waiting-list offer.
    acks = sum(1 for r in chat if r.sender == city.agent_id and r.recipient == message.sender
               and first_word(r.text) == "cancel.ack")
    await _say(
        city,
        message.sender,
        "cancel.ack " + (f"offer_id={offer_id} " if offer_id else "")
        + (
            "Understood, I have withdrawn that offer."
            if en
            else "Capito, ho ritirato quell'offerta."
        ),
    )
    if acks >= 1:
        number = _number(chat)
        rx = _prescription_reply(chat, number) or _our_offer(chat, city.agent_id, offer_id)
        need_key = message.need_id or message.msg_id
        async with _need_gate(_GATES, need_key):
            _sent(need_key).replacement_page = None
            await _relaxed(city, message, chat, need_key, message.sender, fixed or rx.get("procedure"),
                           number, rx.get("priority"))
        return
    await _advance(city, message, chat, fixed=fixed, replacing=True)


_PREP = {
    "VIS-CARD": ("eventuali ECG e referti cardiologici precedenti, l'elenco dei farmaci che prende",
                 "any previous ECG and heart reports, the list of medicines you take"),
    "VIS-FIS": ("eventuali radiografie o risonanze precedenti e abiti comodi per muoversi",
                "any previous X-rays or MRI scans and comfortable clothes to move in"),
}


def _prep_line(procedure: str, en: bool) -> str:
    """P-02: what to bring and when to arrive, before the citizen asks."""

    it_extra, en_extra = _PREP.get(procedure, ("eventuali referti precedenti", "any previous reports"))
    if en:
        return ("To be ready for the visit: arrive 15 minutes early and bring your health card, the "
                f"prescription number, {en_extra}. I will tell you how to get there right away.")
    return ("Per arrivare pronto alla visita: venga 15 minuti prima e porti la tessera sanitaria, il "
            f"numero della ricetta, {it_extra}. Subito dopo le dico come arrivare.")


# --- X-45: the citizen's zone from the Index (no external map API) ---------------------------
_DISTRICT_RE = re.compile(r"district[^0-9]{0,6}(\d{1,2})")
_ZONES: dict[int, tuple[float, float]] = {}


def _citizen_district(chat: list[Message]) -> int | None:
    for row in reversed(chat):
        if row.sender.startswith("citizen:"):
            m = _DISTRICT_RE.search(row.text)
            if m:
                return int(m.group(1))
    return None


async def _zone_point(city: City, chat: list[Message]) -> tuple[float, float] | None:
    """Centre of the citizen's district: the mean of the Index doors in that district."""

    district = _citizen_district(chat)
    if district is None:
        return None
    if district in _ZONES:
        return _ZONES[district]
    try:
        peers = await asyncio.wait_for(city.find("ospedale medico centro prenotazioni consultorio Milano"), timeout=4.0)
    except Exception:
        peers = []
    pts = []
    for peer in peers or []:
        addr = getattr(peer, "address", None)
        if getattr(peer, "district", None) == district and addr is not None and getattr(addr, "lat", None) is not None:
            pts.append((float(addr.lat), float(addr.lon)))
    if not pts and district == 5:  # our ASST: our own doors
        pts = [(d[0], d[1]) for d in _DOOR_FALLBACK.values()]
    if not pts:
        return None
    _ZONES[district] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return _ZONES[district]


async def _zone_route(city: City, chat: list[Message], facility: str) -> str:
    """X-45: how to get there, inside the receipt (the review reads it), from the citizen's zone."""

    zone = await _zone_point(city, chat)
    door = await _door(city, facility)
    if not door:
        return ""
    km = _km(zone, door[:2]) if zone else None
    line = _route_line(_lang(chat) != "it", km, door, {}, zone)
    line = line.replace("da lei", "dalla sua zona").replace("from you", "from your area")
    return (line + " ") if line else ""
