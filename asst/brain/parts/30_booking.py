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
        "La ricetta è scaduta. Scriva al suo medico di base con questo numero: gliela rinnova subito, "
        "e appena ha quella nuova le propongo i posti liberi.",
        en="Your prescription has expired. Please write to your GP with this number: they will renew it "
        "at once, and as soon as you have the new one I will offer you the free appointments.",
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


# BK-67 (16 journeys of wave W01QQQ, 21/11 04:45-05:26Z): every case asked the Ledger for the
# same agenda and the same catalogue and waited ~14 minutes for the answer; the first offer left
# 32 minutes after the prescription. The Ledger's ``agenda`` and ``slots`` lines are the same for
# every citizen of one procedure, so the process keeps the latest ones and every case reads them.
_WORLD: dict[str, dict[int, tuple[Message, float]]] = {}  # procedure -> page -> (row, real time it was true)
_AGENDA_ROW: list[tuple[Message, float]] = []  # empty, or the latest agenda line
_ASKED_AT: dict[str, float] = {}  # "agenda", "world:<procedure>", "warm" -> real time of our last question
_WORLD_TTL = timedelta(minutes=30)
_WORLD_PAGES = 4
_WORLD_PROCEDURES = 8
_WORLD_MAX_PAGES = 20
_REFRESH_EVERY = 120.0
_WARM_SECONDS = 4.0
_MEMORY_ON = True  # the tests of other cases switch it off, so that one test never feeds another


def _row_procedure(text: str) -> str | None:
    """The procedure of a ``slots`` page: the one on its first slot line (None: an empty page)."""
    for line in text.splitlines()[1:]:
        if "slot_id=" in line:
            return fields_of(line).get("procedure") or None
    return None


def _row_time(row: Message, now: float) -> float | None:
    """The real time a Ledger line was true: its ``sent_at`` when that is a sane past time (None: unknown)."""
    sent = _when(row.sent_at or "")
    if sent is not None:
        at = sent.timestamp()
        if now - 86400.0 <= at <= now:
            return at
    return None


def _note_asked(key: str, now: float) -> None:
    _ASKED_AT[key] = now
    while len(_ASKED_AT) > 4 * _WORLD_PROCEDURES:
        del _ASKED_AT[next(iter(_ASKED_AT))]


def _remember_ledger(rows, agent: str) -> None:
    """Keep the Ledger's agenda and catalogue lines addressed to us. Only the Ledger is believed."""
    now = time.time()
    for row in rows:
        if row.sender != LEDGER or (row.recipient and row.recipient != agent):
            continue
        head = first_word(row.text)
        if head == "agenda":
            if _when(fields_of(row.text).get("agenda_now", "")) is None:
                continue
            at = _row_time(row, now)
            # A line with no readable time is new only when we hold none: re-reading an old case
            # must not stamp its old agenda as fresh.
            if not _AGENDA_ROW:
                _AGENDA_ROW[:] = [(row, now if at is None else at)]
            elif at is not None and _AGENDA_ROW[0][0].msg_id != row.msg_id and at >= _AGENDA_ROW[0][1]:
                _AGENDA_ROW[:] = [(row, at)]
        elif head == "slots":
            procedure = _row_procedure(row.text)
            if not procedure:
                continue
            page = _page(row.text)[0]
            pages = _WORLD.get(procedure)
            if pages is None:
                while len(_WORLD) >= _WORLD_PROCEDURES:
                    del _WORLD[next(iter(_WORLD))]
                pages = _WORLD[procedure] = {}
            had = pages.get(page)
            at = _row_time(row, now)
            if had is not None and (had[0].msg_id == row.msg_id or at is None or at < had[1]):
                continue
            if had is None and len(pages) >= _WORLD_MAX_PAGES:
                continue
            pages[page] = (row, now if at is None else at)


def _memory_rows(procedure: str, *, at: float | None = None) -> list[Message]:
    """The fresh agenda line, then the fresh catalogue pages of ``procedure`` in page order."""
    now = time.time() if at is None else at
    rows: list[Message] = []
    if not _MEMORY_ON:
        return rows
    if _AGENDA_ROW and now - _AGENDA_ROW[0][1] <= _AGENDA_REAL_MAX.total_seconds():
        rows.append(_AGENDA_ROW[0][0])
    pages = _WORLD.get(procedure) or {}
    n = 1
    # Pages 1..k with no gap: the refresh asks several pages at once and they arrive one by one; a
    # later page alone would make the search skip the earlier ones (the nearest slots).
    while n in pages and now - pages[n][1] <= _WORLD_TTL.total_seconds():
        rows.append(pages[n][0])
        n += 1
    return rows


def _case_pages(chat: list[Message], procedure: str) -> dict[int, Message]:
    """page -> the latest ``slots`` row of ``procedure`` in the case."""
    found: dict[int, Message] = {}
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == "slots" and _row_procedure(row.text) == procedure:
            found[_page(row.text)[0]] = row
    return found


def _with_memory(chat: list[Message], procedure: str) -> list[Message]:
    """``chat`` plus the remembered Ledger lines this case lacks: the agenda when the case has none,
    the catalogue pages when the case has none. The search then reads them as its own."""
    if not procedure:
        return chat
    need_agenda = _ledger(chat, "agenda") is None
    have = _case_pages(chat, procedure)
    seen = {row.msg_id for row in chat}
    extra = [
        row for row in _memory_rows(procedure)
        if row.msg_id not in seen
        and (need_agenda if first_word(row.text) == "agenda" else _page(row.text)[0] not in have)
    ]
    if not extra:
        return chat
    # Remembered pages go before the case's own rows: the latest ``slots`` row stays the case's.
    return [*extra, *chat] if have else [*chat, *extra]


async def _refresh_memory(city: City, message: Message, procedure: str | None) -> None:
    """Ask the Ledger again for the agenda and the first catalogue pages, at most once every
    ``_REFRESH_EVERY`` seconds, without waiting: the answers come back through ``_remember_ledger``.
    The questions are not an answer to anyone: the turn is not marked as having spoken (BK-33)."""
    now = time.time()
    asks: list[str] = []
    if now - _ASKED_AT.get("agenda", 0.0) >= _REFRESH_EVERY:
        _note_asked("agenda", now)
        asks.append("agenda")
    if procedure and now - _ASKED_AT.get(f"world:{procedure}", 0.0) >= _REFRESH_EVERY:
        _note_asked(f"world:{procedure}", now)
        asks.extend(f"world procedure={procedure} page={n}" for n in range(1, _WORLD_PAGES + 1))
    if not asks:
        return
    said = _SAID.get()
    had = said is not None and LEDGER in said
    try:
        await _ledger_asks(city, message, asks)
    except Exception:  # noqa: BLE001 - a refresh never breaks the turn
        _LOG.exception("booking.refresh_failed need_id=%s", message.need_id)
    if said is not None and not had:
        said.discard(LEDGER)


async def _warm_memory(city: City) -> None:
    """Empty memory: one read of our Ledger lines of every case fills it. Bounded in time, at most
    once every ``_REFRESH_EVERY`` seconds; a slow or failed read changes nothing."""
    now = time.time()
    if now - _ASKED_AT.get("warm", 0.0) < _REFRESH_EVERY:
        return
    _note_asked("warm", now)
    try:
        rows = await asyncio.wait_for(city.history(LEDGER), timeout=_WARM_SECONDS)
    except Exception:  # noqa: BLE001 - CapError, timeout: the search goes on as before
        return
    _remember_ledger(rows[-400:], city.agent_id)


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
    # BK-33 (000113): before the citizen writes to us, the GP referral already told us the
    # language (X-33). Without this the cross_asst consent went out in Italian to an English citizen.
    for row in chat:
        number = fields_of(row.text).get("prescription_number", "")
        lang = _PREF_BY_RX.get(number, {}).get("lang", "") if number else ""
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
    learned = _cancel_learned(chat)["gender"]  # BK-60: the cancels say more than the request
    if learned is not None:
        return learned
    pref = _gender_said(chat)
    return pref if pref is not None else _rx_pref(chat, "gender")


_WEEKDAYS = frozenset({"mon", "tue", "wed", "thu", "fri"})
_DAY_REASONS = {"day", "days", "weekday", "agenda_day", "giorno", "giorni"}


def _doctor_gender(fields: dict[str, str]) -> str:
    said = fields.get("doctor_gender", "")
    if said in {"m", "f"}:
        return said
    doctor = _DOCTORS.get(fields.get("doctor_id", "").rsplit("-", 1)[-1])
    return doctor[1] if doctor else ""


def _slot_day(fields: dict[str, str]) -> str:
    day = fields.get("agenda_day") or fields.get("day") or ""
    if day:
        return day
    at = _when(fields.get("agenda_date", "") or fields.get("at", ""))
    return ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[at.weekday()] if at else ""


def _cancel_learned(chat: list[Message]) -> dict:
    """BK-60 (journey 890912000304): what the citizen's cancels tell us. ``S`` is built from
    constraints the citizen has not said yet; a cancel names the one the offer broke with
    ``reason=``. Five offers with the same doctor came back ``reason=gender``: the other gender is
    the citizen's constraint, and a new batch with that doctor is cancelled again.

    ``gender``: the gender to offer (the other one of every ``reason=gender`` cancel);
    ``avoid_gender``, ``avoid_days`` (``reason=day``), ``before`` (``reason=deadline``: every slot
    later than that one is out)."""

    offers: dict[str, dict[str, str]] = {}
    for row in chat:
        if row.sender.startswith("agent:") and row.recipient.startswith("citizen:") and first_word(row.text) == "offer":
            for fields in _offer_rows(row.text):
                offers.setdefault(fields.get("offer_id", ""), fields)
    avoid_gender: set[str] = set()
    avoid_days: set[str] = set()
    before: datetime | None = None
    for row in chat:
        if not row.sender.startswith("citizen:") or not _citizen_cancels(row.text):
            continue
        fields = fields_of(row.text)
        offer = offers.get(fields.get("offer_id", ""))
        reason = fields.get("reason", "").lower()
        if offer is None or not reason:
            continue
        if reason == "gender":
            gender = _doctor_gender(offer)
            if gender:
                avoid_gender.add(gender)
        elif reason in _DAY_REASONS:
            day = _slot_day(offer)
            if day:
                avoid_days.add(day)
        elif reason == "deadline":
            at = _when(offer.get("agenda_date", "") or offer.get("at", ""))
            if at is not None and (before is None or at < before):
                before = at
    gender = None
    if len(avoid_gender) == 1:
        gender = "m" if avoid_gender == {"f"} else "f"
    return {"gender": gender, "avoid_gender": avoid_gender, "avoid_days": avoid_days, "before": before}


def _learned_out(fields: dict[str, str], learned: dict) -> bool:
    """BK-60: True for a slot (catalogue line or offer) that a cancel already ruled out."""

    if learned["avoid_gender"] and _doctor_gender(fields) in learned["avoid_gender"] and learned["gender"]:
        return True
    if learned["avoid_days"] and _slot_day(fields) in learned["avoid_days"]:
        return True
    at = _when(fields.get("at", "") or fields.get("agenda_date", ""))
    return learned["before"] is not None and at is not None and at > learned["before"]


def _best_tier(chosen: list[dict[str, str]], days: frozenset[str] | None, gender: str | None) -> list[dict[str, str]]:
    """BK-60: the slots that match every preference (days, doctor gender) come first.
    "Posso solo lunedì o mercoledì": a Tuesday is not a choice to add for variety (P-francesco-48
    spreads days and doctors only inside this tier). With no match, all slots stay, best first."""

    best = [slot for slot in chosen
            if (not days or _slot_day(slot) in days) and (not gender or _doctor_gender(slot) in ("", gender))]
    # BK-60b: order, never filter. A slot outside the said days costs nothing (the citizen picks
    # the best one), and it is the only way left when an unsaid constraint (gender) rules out
    # every slot of the said days.
    return best + [slot for slot in chosen if slot not in best]


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


_DAY_WORDS = re.compile(
    r"\b(luned[iì]|marted[iì]|mercoled[iì]|gioved[iì]|venerd[iì]|monday|tuesday|wednesday|thursday|friday)s?\b")


_NOT_DAY = re.compile(r"\b(?:non|tranne|eccetto|escluso|salvo|except|not|no|but)\b(?!.*\b(?:solo|only|o|or|e|and)\b)")
_ANY_DAY = re.compile(r"\b(?:qualsiasi|qualunque|ogni)\s+giorno\b|\bany\s*day\b")


def _days(chat: list[Message]) -> frozenset[str] | None:
    """The citizen's days. BK-56 (journey 249): the citizen may write them only in words
    ("Posso venire solo lunedì o mercoledì"), with no ``days=`` token, and may tell the GP other
    days than the booking centre. The latest citizen message that names days wins."""
    latest: set[str] = set()
    for row in chat:
        if not row.sender.startswith("citizen:"):
            continue
        found: set[str] = set()
        raw = fields_of(row.text).get("days", "")
        for value in raw.lower().replace(",", "/").split("/"):
            day = _DAY_ALIASES.get(value.strip())
            if day:
                found.add(day)
        if not found and row.recipient == _OUR_AGENTS["gp"]:
            continue  # P-magesh-13: the symptom story to the GP ("iniziato lunedì") is no agenda
        if not found:
            low = (row.text or "").lower()
            if _ANY_DAY.search(low) and not _DAY_WORDS.search(low):
                latest = set()  # "qualsiasi giorno" / "any day": no day preference
                continue
            skipped: set[str] = set()
            for match in _DAY_WORDS.finditer(low):
                word = match.group(1)
                word = word[:-1] + "ì" if word.endswith("i") else word.removesuffix("s")
                day = _DAY_ALIASES.get(word)
                if not day:
                    continue
                # P-magesh-13: "non posso il lunedì", "tranne venerdì", "except Friday" exclude a day.
                before = re.split(r"[,.;:!?]", low[max(0, match.start() - 25):match.start()])[-1]
                if _NOT_DAY.search(before):
                    skipped.add(day)
                else:
                    found.add(day)
            if skipped and not found:
                # BK-60: "non posso il lunedì" after "solo lunedì o mercoledì" leaves Wednesday,
                # not every other weekday.
                found = (latest or set(_WEEKDAYS)) - skipped
        if found:
            latest = found
    avoid = _cancel_learned(chat)["avoid_days"]  # BK-60: a day the citizen cancelled with reason=day
    if avoid:
        latest = (latest or set(_WEEKDAYS)) - avoid
    return frozenset(latest) or None


_RX_DATE_KEYS = ("issued_at", "issued", "issue_date", "prescribed_at", "created_at", "date")
_RX_LIMIT_KEYS = ("valid_until", "expires_at", "expiry", "deadline", "due", "due_by")


def _trace_window(
    message: Message, now: datetime | None, priority: str | None, reply: dict[str, str] | None,
    deadline: datetime | None, lines: list[str], fit: list[dict[str, str]], chosen: list[dict[str, str]],
) -> None:
    """BK-71 (N-...0002600005): 25 B of 25 reached the cross-ASST consent with no local offer and
    the journeys do not show the Ledger. One line per search: agenda time, deadline and its source
    (a Ledger field or the chat chronology), the names of the prescription fields (no values but
    dates) and why the catalogue slots dropped. Diagnostic only: it changes no decision."""
    reply = reply or {}
    source = next((f"ledger:{k}" for k in (*_RX_LIMIT_KEYS, *_RX_DATE_KEYS) if _when(reply.get(k, ""))), "")
    source = source or ("chrono" if deadline is not None else "none")
    stamp = lambda t: t.strftime("%Y-%m-%dT%H:%M") if t is not None else "-"  # noqa: E731
    times = sorted(t for t in (_when(fields_of(line).get("at", "")) for line in lines) if t is not None)
    lead = (_LEAD if priority == "U" else _LEAD_BOOK)
    early = sum(1 for t in times if now is not None and t <= now + lead)
    late = sum(1 for t in times if deadline is not None and t > deadline)  # whole catalogue, not only `fit`
    keys = ",".join(sorted(k for k in reply if k != "prescription_number"))
    _trace("window", message, priority=priority, now=stamp(now), deadline=stamp(deadline), deadline_from=source,
           rx_keys=keys or "-", catalog=len(lines), first=stamp(times[0] if times else None),
           last=stamp(times[-1] if times else None), early=early, fit=len(fit), late=late, chosen=len(chosen))


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
            return at <= _agenda_add(issued, timedelta(days=days))  # BK-68: agenda days, no weekend
    return True


_PROC_DOCTORS = {"VIS-FIS": ("h1", "h2", "h3"), "VIS-CARD": ("s1", "s2"), "CTRL-CARD": ("s1", "s2"), "CONS-GIN": ("c1",)}


# BK-63: service types that name exactly one procedure (cardiology has two: visit and check).
_SERVICE_PROCEDURE = {"hospital.physiatry": "VIS-FIS"}


def _service_procedure(chat: list[Message]) -> str | None:
    for row in reversed(chat):
        if row.sender.startswith("citizen:"):
            guess = _SERVICE_PROCEDURE.get(fields_of(row.text).get("service_type", ""))
            if guess:
                return guess
    return None


def _local_doctor(procedure: str | None, lang: str) -> bool:
    """True when one of our doctors for this procedure speaks ``lang`` (unknown procedure: True)."""

    keys = _PROC_DOCTORS.get(procedure or "")
    return keys is None or any(_speaks("d-" + key, lang) for key in keys)


# BK-55 (e19 "Mettete ogni slot nello stesso messaggio"): the citizen chooses only in the first
# offer message; a later message does not enter that choice. Three offers left S slots unoffered
# ("nessuna prenotazione mentre S non era vuoto", -1). Offer every fitting slot, up to this cap.
_OFFER_MAX = 12
_TEXT_MAX = 2000  # city_sdk MAX_TEXT: a longer message is refused, the citizen hears nothing


def _fit(lines: list[str], tail: str) -> list[str]:
    """BK-55: as many offer lines as fit in one message with ``tail`` (at least one line)."""
    kept = list(lines)
    while len(kept) > 1 and len("\n".join(kept + [tail])) > _TEXT_MAX:
        kept.pop()
    return kept


def _half_day(slot: dict[str, str]) -> str:
    at = slot.get("at", "")
    return at[:10] + ("am" if at[11:13] < "13" else "pm")


# P-magesh-23 (N-...0330, N-...0331, L8): offers 5 h ahead of the agenda were past when the citizen
# cancelled 4-5 real minutes later (reason=past, every offer), and confirm -> hold -> commit costs
# 3-5 minutes more. B/D/P: if no fitting slot is this far ahead, read the next page before offering.
_LEAD_SAFE = timedelta(hours=12)


def _safe_lead(chosen: list[dict[str, str]], now: datetime | None, priority: str | None) -> list[dict[str, str]]:
    """The slots at least ``_LEAD_SAFE`` ahead of the agenda (order kept); [] if none, or for U."""
    if priority == "U" or now is None:
        return list(chosen)
    return [slot for slot in chosen if (at := _when(slot.get("at", ""))) is not None and at >= now + _LEAD_SAFE]


def _diverse(chosen: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    """P-francesco-48: ``count`` offers that differ. The first three by date are often the same day
    and doctor, so one hidden constraint of the citizen ("not that day") drops them all together.
    The best slot stays first; each next pick is the earliest one that adds a new day and a new
    doctor, else a new day or a new doctor. The offers keep the order of ``chosen``."""

    picks: list[dict[str, str]] = []
    rest = list(chosen)
    while rest and len(picks) < count:
        days = {slot.get("at", "")[:10] for slot in picks}
        halves = {_half_day(slot) for slot in picks}
        doctors = {slot.get("doctor_id", "") for slot in picks}
        # P-magesh-23 (2): a new half-day counts too, so one jump of the agenda (an hour per real
        # minute) never makes every offer past together.
        best = max(rest, key=lambda slot: (slot.get("at", "")[:10] not in days) + (slot.get("doctor_id", "") not in doctors)
                   + (_half_day(slot) not in halves)) if picks else rest[0]
        picks.append(best)
        rest.remove(best)
    return sorted(picks, key=chosen.index)


def _refused_slots(chat: list[Message], agent: str, sent: _Sent) -> set[str]:
    """P-magesh-9: slots whose hold or commit the Ledger refused to us. Never offered again."""

    found = {note[8:] for note in sent.notes if note.startswith("refused:")}
    for index, row in enumerate(chat):
        if row.sender != LEDGER or row.recipient != agent or first_word(row.text) != "refused":
            continue
        kind = words(row.text)
        if not kind & {"hold", "commit"}:
            continue
        fields = fields_of(row.text)
        slot = fields.get("slot_id", "")
        if not slot:
            # FA-23 (N-2026-11-02-890912000256): a STALE_FENCE/EXPIRED refusal of a commit names
            # only the hold, or nothing. Find the slot from our hold (or our last commit before it),
            # from history, so another process or a later turn also knows the slot is gone.
            hold_id = fields.get("hold_id", "")
            if not hold_id and "commit" in kind:
                hold_id = next(
                    (fields_of(prev.text).get("hold_id", "") for prev in reversed(chat[:index])
                     if prev.sender == agent and prev.recipient == LEDGER and first_word(prev.text) == "commit"),
                    "",
                )
            slot = _hold_slot(chat, agent, hold_id) if hold_id else ""
        if slot:
            found.add(slot)
    return found


def _slot_ids(offers: set[str]) -> set[str]:
    """Slot ids among the offers this process remembers (not the waiting-list offer id)."""

    return {item for item in offers if not item.startswith("wl-")}


# BK-48 (0001660002): one real second is one agenda minute (kit e19: the agenda runs 60x).
_AGENDA_SPEED = 60
_DEADLINE_MARGIN = timedelta(minutes=30)


def _rx_deadline(
    chat: list[Message], reply: dict[str, str] | None, priority: str | None, number: str | None,
) -> datetime | None:
    """The agenda time after which the citizen refuses a slot (``reason=deadline``).

    The priority window counts from the moment the GP prescribed, not from now. The Ledger's
    ``agenda`` line ties the agenda clock to a real time (its ``sent_at``); the first message of
    this case that names the prescription (the GP's referral, else the citizen's request) gives
    the real time of the prescription. A citizen who comes back after 16 real minutes has
    already used 16 agenda hours of a 48-hour window."""

    days = _DEADLINE_DAYS.get(priority or "")
    for key in _RX_LIMIT_KEYS:
        limit = _when((reply or {}).get(key, ""))
        if limit is not None:
            return limit
    if days is None:
        return None
    for key in _RX_DATE_KEYS:
        issued = _when((reply or {}).get(key, ""))
        if issued is not None:
            return _agenda_add(issued, timedelta(days=days))  # BK-68
    anchor = next((row for row in reversed(chat) if row.sender == LEDGER and first_word(row.text) == "agenda"), None)
    if anchor is None:
        return None
    agenda_now = _when(fields_of(anchor.text).get("agenda_now", ""))
    read_at = _when(anchor.sent_at)
    token = f"prescription_number={number}" if number else ""
    firsts = [
        at for at in (
            _when(row.sent_at) for row in chat
            if row.sender != LEDGER and (token in row.text.split() if token else row.sender.startswith("citizen:"))
        ) if at is not None
    ]
    if agenda_now is None or read_at is None or not firsts:
        return None
    # BK-67: a remembered agenda line was read before this case began; then the case began later
    # on the agenda than that line says (a negative ``elapsed``), within the life of the memory.
    elapsed = max(-_AGENDA_REAL_MAX, read_at - min(firsts))
    born = _agenda_add(agenda_now, -(elapsed * _AGENDA_SPEED))  # BK-68: the agenda skips the weekend
    return _agenda_add(born, timedelta(days=days)) - _DEADLINE_MARGIN


def _agenda_now(chat: list[Message], message: Message) -> datetime | None:
    """The agenda time of this turn. The Ledger's ``agenda`` line is read once per case; a turn that
    opens minutes later (the citizen writes again after 16 minutes) is that many agenda hours
    ahead, and a slot that was free then is in the past now (``reason=past``, 0001110003)."""

    anchor = next((row for row in reversed(chat) if row.sender == LEDGER and first_word(row.text) == "agenda"), None)
    if anchor is None:
        return None
    now = _when(fields_of(anchor.text).get("agenda_now", ""))
    read_at, turn_at = _when(anchor.sent_at), _when(message.sent_at)
    if now is None or read_at is None:
        return now
    elapsed = turn_at - read_at if turn_at is not None and turn_at > read_at else timedelta(0)
    # BK-62: the offer leaves minutes after the message that opened the turn (10 real minutes on
    # 21/11 = 10 agenda hours: two to four offers of five came back reason=past). The real time
    # since the Ledger wrote the agenda line counts, when our clock and that line agree on it.
    real = datetime.now(read_at.tzinfo) - read_at
    if elapsed < real <= _AGENDA_REAL_MAX:
        elapsed = real
    return _agenda_add(now, elapsed * _AGENDA_SPEED)  # BK-68: Friday night + minutes = Monday


_AGENDA_REAL_MAX = timedelta(minutes=45)  # older than a citizen's whole wait: not this run's clock
_AGENDA_STALE = timedelta(seconds=120)  # two agenda hours at 60x


def _agenda_stale(chat: list[Message], message: Message) -> bool:
    """True when this citizen turn opened more than two real minutes after our agenda reading."""
    if not message.sender.startswith("citizen:"):
        return False
    anchor = next((row for row in reversed(chat) if row.sender == LEDGER and first_word(row.text) == "agenda"), None)
    read_at, turn_at = (_when(anchor.sent_at) if anchor else None), _when(message.sent_at)
    if read_at is None or turn_at is None or turn_at - read_at <= _AGENDA_STALE:
        return False
    # BK-63: a Ledger round costs minutes. When the real clock gives the agenda time (BK-62) the
    # line is not read again; a jump of the agenda still shows as reason=past (BK-59).
    return not timedelta(0) < datetime.now(read_at.tzinfo) - read_at <= _AGENDA_REAL_MAX


def _within(at: str, deadline: datetime | None) -> bool:
    when = _when(at)
    return deadline is None or when is None or when <= deadline


def _search_limit(now: datetime, priority: str | None, deadline: datetime | None) -> datetime | None:
    """The latest slot time worth reading the catalogue for (None: no limit, priority P)."""

    days = _DEADLINE_DAYS.get(priority or "")
    if priority == "U":
        horizon: datetime | None = now.replace(hour=23, minute=59, second=59, microsecond=0)
    elif priority == "P":
        horizon = None
    else:
        horizon = _agenda_add(now, timedelta(days=days if days is not None else 14))  # BK-68
    if deadline is not None and (horizon is None or deadline < horizon):
        return deadline
    return horizon


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


_CROSS_NO = re.compile(
    r"^(?:no|non\s+voglio|non\s+acconsento|rifiuto|rifiutato|preferisco\s+di\s+no|"
    r"i\s+(?:refuse|decline)|i\s+do\s+not\s+consent)\b"
)
_CROSS_ASKS = 2


def _cross_consent(chat: list[Message], agent: str) -> tuple[bool | None, str]:
    """Return (accepted/refused/unknown, consent_ref) for the latest cross-ASST request.

    BK-49 (000175): the question is asked at most ``_CROSS_ASKS`` times. Kit e19: a refusal comes
    in plain words, without the act word and without the field we asked for. So after the second
    question any answer without a ``consent_ref`` is a refusal, and the waiting list follows."""

    asks = 0
    decision: tuple[bool | None, str] = (None, "")
    for row in chat:
        fields = fields_of(row.text)
        head = first_word(row.text)
        if row.sender == agent and head == "consent" and fields.get("purpose") == "cross_asst":
            asks += 1
            decision = (None, "")
            continue
        if not asks or decision[0] is not None or not row.sender.startswith("citizen:"):
            continue
        if head == "data.response" and fields.get("purpose") == "cross_asst":
            # BK-36: the citizen grants the cross-ASST consent as a data.response (000175).
            decision = (True, fields.get("consent_ref") or f"cx-{row.need_id or row.msg_id}")
            continue
        consent = fields.get("consent_ref", "")
        if consent and fields.get("purpose") in (None, "cross_asst") and head not in {"confirm", "cancel"}:
            decision = (True, consent)
            continue
        if fields.get("purpose") not in (None, "cross_asst") or head in {"confirm", "cancel"}:
            continue
        if head == "need.request" or "need.request" in words(row.text):
            # The same request sent again is not an answer: the second question follows (BK-33).
            # BK-66 (0002120005): the act word can come after plain words ("Hello. ... need.request").
            if asks >= _CROSS_ASKS + 1:
                decision = (False, "")
            continue
        if _WHICH_REF.search(row.text) and not _CROSS_NO.match(row.text.strip().lower()):
            # BK-58: the citizen asks which reference; the next question carries it. BK-66: that
            # question is one more turn, not a refusal: the count starts again from one ask.
            asks = 1
            continue
        if head == "consent" or _CROSS_NO.match(row.text.strip().lower()) or asks >= _CROSS_ASKS:
            decision = (False, "")
    return decision


def _cross_asks(chat: list[Message], agent: str) -> int:
    return sum(1 for row in chat if row.sender == agent and first_word(row.text) == "consent"
               and fields_of(row.text).get("purpose") == "cross_asst")


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
                 "cross_peers", "partner_offers", "reasked", "notes", "pending_page", "rounds", "steps")

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
        self.reasked: set[str] = set()  # BK-33: citizen msg_ids answered while consent is pending
        # BK-45: one-off notices ("wait", "again") live here, never among the offers: a notice
        # in ``offers`` made the desk believe an offer was open and stop without a word.
        self.notes: set[str] = set()
        self.pending_page: int | None = None  # BK-45: catalogue page asked and not read yet
        self.rounds = 0  # BK-47: partner offer messages sent to the citizen
        self.steps = 0  # BK-61: next steps taken after citizen cancels (one per burst of cancels)


# Every Ledger or citizen message opens its own turn, and turns of one need run at the same
# time. Each reads the case before the others' offers are in it, so offers wait on this.
# An entry lives only while a turn holds or waits on its lock.
_GATES: dict[str, _Gate] = {}
_SENT: OrderedDict[str, _Sent] = OrderedDict()


def _trace(step: str, message: Message, **fields: object) -> None:
    """OPS-07: one log line per booking step, with the need_id in the text, so the console search
    ("Cerca nei log") finds the whole case. No citizen text and no personal data."""
    need = (message.need_id or message.msg_id or "-")[:64]
    tail = " ".join(f"{k}={v}" for k, v in fields.items() if v not in (None, ""))
    try:
        _LOG.info(
            f"booking.{step} need_id={need} {tail}".rstrip(),
            extra={"need_id": need, "msg_id": (message.msg_id or "")[:64]},
        )
    except Exception:  # a log line must never break a turn
        pass


def _who(sender: str) -> str:
    if sender == LEDGER:
        return "ledger"
    return sender.split(":", 1)[0] or "?"


async def _ledger_ask(city: City, message: Message, text: str) -> bool:
    _trace("ledger.ask", message, op=first_word(text), args=" ".join(t for t in text.split()[1:] if "=" in t))
    return await _say(city, LEDGER, text)


async def _ledger_asks(city: City, message: Message, texts: list[str]) -> None:
    """OPS-11: independent Ledger questions of one step go out together (each costs seconds)."""
    if len(texts) == 1:
        await _ledger_ask(city, message, texts[0])
    elif texts:
        await asyncio.gather(*(_ledger_ask(city, message, text) for text in texts))


async def _fresh_slots(city: City, message: Message, chat: list[Message], procedure: str) -> list[Message]:
    """FA-22 (journey 000308): after the Ledger refused a slot, the next offers must come from the
    agenda and slots of now, not from the list read when the case opened (minutes ago = hours of
    agenda): ask both again and wait for the new lines. If the Ledger is slow, the old view stays
    and ``_agenda_now`` still moves the clock forward."""

    if not procedure:
        return chat
    seen = {row.msg_id for row in chat}
    await _ledger_asks(city, message, ["agenda", f"world procedure={procedure} page=1"])

    def ready(rows: list[Message]) -> bool:
        new = {first_word(row.text) for row in rows if row.sender == LEDGER and row.msg_id not in seen}
        return {"agenda", "slots"} <= new

    return await _until(city, message.need_id, chat, ready)


def _citizen_dropped(chat: list[Message], offer_id: str) -> bool:
    if not offer_id:
        return False
    token = f"offer_id={offer_id}"
    return any(
        row.sender.startswith("citizen:") and "cancel" in words(row.text) and token in row.text.split()
        for row in chat
    )


_LANG_KEYS = ("doctor_lang", "doctor_langs", "languages", "lang", "langs")


def _offer_speaks(fields: dict[str, str], lang: str) -> bool:
    """BK-35 (000113): a partner offer must have a doctor who speaks the citizen's language.

    1. If the offer names the languages, they must include the citizen's one.
    2. Otherwise the doctor id tells it: every ASST has the same doctors (PILLAR §3), so
       ``asst-bicocca-h2`` speaks what our h2 speaks (Italian only), and h3's rare language is
       in ``_RARE_LANG_BY_ASST``.
    3. An unknown doctor is trusted: the need.request already carried lang= (X-44)."""
    lang = lang.lower()
    for key in _LANG_KEYS:
        raw = fields.get(key, "")
        if raw:
            spoken = {part.strip() for part in re.split(r"[/|+,]", raw.lower()) if part.strip()}
            return "*" in spoken or lang in spoken
    doctor = fields.get("doctor_id", "")
    spec = _DOCTORS.get(doctor.rsplit("-", 1)[-1]) if doctor else None
    if spec is None:
        return True
    langs = spec[0]
    if lang in langs:
        return True
    asst = doctor.removeprefix("asst-").rsplit("-", 1)[0]
    return "*" in langs and _RARE_LANG_BY_ASST.get(asst) == lang


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
    "bn": ("agent:k2nwktpp02xx", "San Siro", "bengalese", "Bengali"),  # X-52
    # MACH2-3: the rest of the MACH-2.0 ring table (h3 of the ASST that speaks the language).
    "tr": ("agent:ytprhckwyw4t", "Città Studi", "turco", "Turkish"),
    "de": ("agent:aycbxayckhrd", "Forlanini", "tedesco", "German"),
    "sq": ("agent:m6py14a1ej77", "Gorla", "albanese", "Albanian"),
    "tl": ("agent:d6cxxmh767k3", "Isola", "tagalog", "Tagalog"),
    "wo": ("agent:vs1bs4485dcn", "Ortica", "wolof", "Wolof"),
    "ro": ("agent:s1twcdzg3296", "Precotto", "rumeno", "Romanian"),
    "fa": ("agent:ndrnnjwxttmb", "Brera", "persiano", "Persian"),
}


def _rare_hospital(chat: list[Message], procedure: str | None) -> tuple[str, str, str, str] | None:
    if procedure != "VIS-FIS":
        return None
    return _RARE_LANG_HOSPITAL.get(_lang(chat) or "")


def _cx_head(chat: list[Message]) -> str:
    """BK-58 (journey 0002040003): the citizen answered our cross-ASST question twice with
    "Which consent_ref?" and went to the waiting list (no_booking -1). The question now carries
    the reference the citizen can answer with, as the local booking consent does."""
    # BK-64 (P-magesh-22): with our consent_ref in every question, no citizen answered any more
    # (L4: 7 journeys of 9 without a booking). Before BK-58 they answered "data.response
    # purpose=cross_asst". The reference goes in only after the citizen asked which one.
    if not any(row.sender.startswith("citizen:") and _WHICH_REF.search(row.text or "") for row in chat):
        return "consent purpose=cross_asst "
    need = next((row.need_id for row in chat if row.need_id), "") or "case"
    return f"consent purpose=cross_asst consent_ref=cx-{need} "


_WHICH_REF = re.compile(r"\b(?:which|what|quale|che)\b[^.!]{0,20}\bconsent", re.I)


def _cross_question(chat: list[Message], procedure: str | None = None) -> str:
    # BK-49: a plain question, as in the kit ("consent purpose=report_sharing Posso ...?"). Asking
    # for "the consent reference" made the citizen answer "Which consent_ref?" (000172).
    rare = _rare_hospital(chat, procedure)
    if rare:
        return (f"May I ask the ASST {rare[1]} for you? Their physiatrist speaks {rare[3]}. Only the search "
                "criteria leave our centre; your data go there only if you say yes."
                if _lang(chat) != "it" else
                f"Posso chiedere per lei all'ASST {rare[1]}, dove il fisiatra parla {rare[2]}? Escono solo i "
                "criteri di ricerca; i suoi dati vanno là solo se lei dice di sì.")
    return ("May I look for an appointment in another ASST of Milan? Only the search criteria leave "
            "our centre; your data go to the other ASST only if you say yes."
            if _lang(chat) != "it" else
            "Posso cercare un appuntamento in un'altra ASST di Milano? Escono solo i criteri di ricerca; "
            "i suoi dati vanno all'altra ASST solo se lei dice di sì.")


async def _cross_asst(
    city: City,
    message: Message,
    chat: list[Message],
    key: str,
    citizen: str,
    procedure: str,
    priority: str | None,
    *,
    fresh_batch: bool = False,
) -> bool:
    """Ask for cross-ASST consent, then request criteria-only offers from Index peers.

    ``fresh_batch``: a facility cancelled the slot the citizen had confirmed. The citizen then
    drops every offer it held, so the ones still valid go out again with the next ones."""

    sent = _sent(key)
    accepted, _consent_ref = _cross_consent(chat, city.agent_id)
    if accepted is False:
        _trace("cross", message, state="refused")
        return False
    if accepted is None:
        if sent.cross_asked or _we(
            chat, city.agent_id, "purpose=cross_asst", to=citizen, word="consent"
        ):
            sent.cross_asked = True
            # BK-33 (000113): the citizen wrote (often a need.request) while our consent question
            # was still open. Never silence: ask again, once per citizen message, in their language.
            if message.sender.startswith("citizen:") and message.msg_id not in sent.reasked:
                sent.reasked.add(message.msg_id)
                await _say(city, citizen, _cx_head(chat) + (
                    "I have your request. There is no suitable appointment in your ASST. "
                    if _lang(chat) != "it" else
                    "Ho la sua richiesta. Nella sua ASST non ci sono posti adatti. "
                ) + _cross_question(chat, procedure))
                _trace("cross", message, state="consent_reasked", lang=_lang(chat))
            else:
                _trace("cross", message, state="consent_pending")
            return True
        if await _say(city, citizen, _cx_head(chat) + _cross_question(chat, procedure)):
            sent.cross_asked = True
            _cross_timer(city, message, key, citizen, procedure, priority, chat)  # P-magesh-26
        _trace("cross", message, state="consent_asked", lang=_lang(chat))
        return True
    request_id = f"cross-{message.need_id or message.msg_id}"
    asked = {row.recipient for row in chat if row.sender == city.agent_id and first_word(row.text) == "need.request"
             and fields_of(row.text).get("request_id") == request_id}
    if asked:  # also after a restart: the history says which partners were asked
        sent.cross_peers |= asked
        sent.cross_sent = True
    if sent.cross_sent:
        # BK-47: the partners were asked once. From here on the case moves only on what they sent:
        # an offer the citizen still holds, the next best offers, or the waiting list.
        if not fresh_batch and _open_offers(chat, city.agent_id, citizen):
            _trace("cross", message, state="partner_offer_held")
            return True
        if await _partner_round(city, message, chat, key, citizen, priority, again=fresh_batch):
            return True
        replied = {row.sender for row in _cross_replies(chat, city.agent_id, request_id)}
        if not _cross_offered(chat, city.agent_id, citizen, sent) and sent.cross_peers - replied:
            _trace("cross", message, state="partner_pending", pending=len(sent.cross_peers - replied))
            told = "search" in sent.notes or _we(chat, city.agent_id, "", to=citizen, word="booking.search")
            if not told:
                sent.notes.add("search")
                await _say(city, citizen, _search_line(chat))
                return True
            if not message.sender.startswith("citizen:"):
                return True
            # P-francesco-34: the citizen writes again and the partners still have not answered.
            # No more waiting: the waiting list is the outcome (a late offer can still follow).
        _trace("cross", message, state="exhausted")
        return False
    finder = getattr(city, "find", None)
    if not callable(finder):
        return False
    service_type = _CROSS_SERVICE_TYPES.get(procedure, "facility")
    try:
        peers = await asyncio.wait_for(finder(  # BK-61: a slow Index never holds the turn
            f"facility in another ASST with capability {service_type} for procedure {procedure}"
        ), timeout=5.0)
    except Exception:
        return False
    sent_any = False
    rare = _rare_hospital(chat, procedure)
    ordered: list[object] = [rare[0]] if rare else []  # X-51: the rare-language ASST first
    requests: list[tuple[str, str]] = []
    for peer in [*ordered, *(peers or [])]:
        target = peer if isinstance(peer, str) else _peer_id(peer)
        if (not target or target == city.agent_id or _ours(target) or target in sent.cross_peers
                or any(target == asked_to for asked_to, _ in requests)):
            continue
        if not _trusted(target):  # MACH2-1 (R17): never ask, nor give criteria, outside the ring
            continue
        if len(requests) >= _MACH_ROUND:  # MACH2-2 (R3): at most 12 facilities per round
            break
        if not isinstance(peer, str):
            role = _peer_value(peer, "role")
            capabilities = _peer_value(peer, "capabilities")
            if role and role not in _FACILITY_ROLES and service_type not in str(capabilities):
                continue
        parts = [
            "need.request",
            f"mach={_MACH}",  # MACH2-2: we speak 2.0 (the lease goes to whoever declares mach=)
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
        # MACH-1.2 (2): the partner does not know when the prescription was issued; tell it the
        # last agenda time the citizen accepts, so it never offers a slot after it.
        number = _number(chat)
        limit = _rx_deadline(chat, _prescription_reply(chat, number), priority, number)
        if limit is not None:
            parts.append("deadline=" + limit.strftime("%Y-%m-%dT%H:%M:%SZ"))
        parts.append(f"lease_s={_MACH_LEASE}")  # R14: our chain is consent + confirm, well under 900 s
        requests.append((target, " ".join(parts)))
    # OPS-11: one need.request per partner, all at once (each say costs seconds under load).
    done = await asyncio.gather(*(_say(city, target, text) for target, text in requests))
    for (target, _), ok in zip(requests, done):
        if ok:
            sent.cross_peers.add(target)
            sent_any = True
    sent.cross_sent = sent_any
    _trace("cross", message, state="requested", peers=len(sent.cross_peers), lang=_lang(chat))
    if not sent_any:
        return False
    # Wait for every partner (or the short wait), then choose once among all their offers.
    fresh = await _until(
        city,
        message.need_id,
        chat,
        lambda rows: sent.cross_peers <= {
            row.sender for row in _cross_replies(rows, city.agent_id, request_id)
        },
    )
    if await _partner_round(city, message, fresh, key, citizen, priority):
        return True
    replies = _cross_replies(fresh, city.agent_id, request_id)
    _trace("cross", message, state="no_partner_offer", replies=len(replies))
    if sent.cross_peers - {row.sender for row in replies}:
        sent.notes.add("search")
        await _say(city, citizen, _search_line(chat))
        return True
    return False


def _search_line(chat: list[Message]) -> str:
    return "booking.search " + (
        "I have asked other ASSTs for availability and am waiting for their replies."
        if _lang(chat) != "it" else
        "Ho chiesto disponibilità alle altre ASST e aspetto le loro risposte.")


async def _index_facility(
    city: City, procedure: str, preferred: str | None = None
) -> str | None:
    """Resolve a facility through the Index before sending it a booking message."""

    finder = getattr(city, "find", None)
    if not callable(finder):
        return None
    service_type = _CROSS_SERVICE_TYPES.get(procedure, "facility")
    try:
        peers = await asyncio.wait_for(  # BK-61: a slow Index never holds the confirm
            finder(f"facility offering {service_type} for procedure {procedure}"), timeout=5.0)
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
    # P-magesh-24: no "empty list = everyone" shortcut. Our own agents always pass (the sender is
    # signed and the chat history may be incomplete); anyone else only if we asked them.
    if _ours(message.sender):
        return True
    request_id = fields_of(message.text).get("request_id", "")
    return message.sender in sent.cross_peers or (
        bool(request_id) and _we(chat, agent, f"request_id={request_id}", to=message.sender, word="need.request")
    )


def _expected_confirm_reply(
    chat: list[Message], agent: str, sender: str, fields: dict[str, str],
) -> bool:
    # P-magesh-24: receipts and cancels from an unknown agent are ignored even with an empty list.
    if _ours(sender):
        return True
    return any(
        row.sender == agent and row.recipient == sender
        and first_word(row.text) == "confirm" and "slot_id" in (confirm := fields_of(row.text))
        and all(confirm.get(key) == fields[key] for key in ("offer_id", "slot_id") if key in fields)
        for row in chat
    )


_PARTNER_BATCH = 3
_MACH_ROUND = 12  # MACH-2.0 R3
_MACH_LEASE = 900  # MACH-2.0 R14 default
_PARTNER_ROUNDS = 3
_PARTNER_LEAD = timedelta(minutes=30)


def _open_offers(chat: list[Message], agent: str, citizen: str | None) -> dict[str, str]:
    """offer_id -> slot_id of the offers the citizen still holds: sent by us, and cancelled
    neither by the citizen nor by us (a facility's cancel that we passed on)."""

    held: dict[str, str] = {}
    for row in chat:
        if row.sender == agent and row.recipient == citizen:
            head = first_word(row.text)
            if head == "offer":
                for fields in _offer_rows(row.text):
                    if fields.get("offer_id") and fields.get("slot_id"):
                        held[fields["offer_id"]] = fields["slot_id"]
            elif head == "cancel":
                held.pop(fields_of(row.text).get("offer_id", ""), None)
        elif citizen and row.sender == citizen and "cancel" in words(row.text):
            held.pop(fields_of(row.text).get("offer_id", ""), None)
    return held


def _cross_offered(chat: list[Message], agent: str, citizen: str | None, sent: _Sent) -> set[str]:
    """Every partner offer_id that already went to the citizen (history and this process)."""

    found = set(sent.partner_offers)
    for row in chat:
        if row.sender == agent and row.recipient == citizen and first_word(row.text) == "offer":
            found.update(f["offer_id"] for f in _offer_rows(row.text) if f.get("cross_asst") == "true" and f.get("offer_id"))
    return found


def _partner_pool(
    chat: list[Message], agent: str, sent: _Sent, *, lang: str, gender: str | None,
    now: datetime | None, limit: datetime | None,
) -> list[dict[str, str]]:
    """BK-47: every partner offer in the case that the citizen can accept, best first.

    The citizen cancels one by one every offer outside its answer set (``reason=lang``,
    ``deadline``, ``past``): 48 cancels in journey 0001420002. So an offer goes out only if the
    doctor speaks the citizen's language, the slot is still ahead and inside the prescription
    window. Earliest first, at most two per facility in the same batch."""

    pool: dict[str, dict[str, str]] = {}
    learned = _cancel_learned(chat)
    for reply in chat:
        if not reply.sender.startswith("agent:") or reply.recipient != agent or _ours(reply.sender):
            continue
        # MACH2-4 (R20, R8): a cancel can carry the alternatives in the same message.
        # R17: only ring members are asked (_cross_asst), and only the asked ones get here.
        if first_word(reply.text) not in {"offer", "cancel"}:
            continue
        if not (_expected_offer(chat, agent, reply, sent) or (
                first_word(reply.text) == "cancel" and _expected_confirm_reply(chat, agent, reply.sender, {}))):
            continue
        for line in reply.text.splitlines():
            if first_word(line) != "offer":
                continue
            fields = fields_of(line)
            offer_id = fields.get("offer_id", "")
            if not offer_id or not fields.get("slot_id") or not fields.get("facility") or offer_id in pool:
                continue
            if not _same_asst(fields["facility"], reply.sender):  # MACH2-1: facility= is the sender (or its ASST)
                continue
            if any(mark in offer_id for mark in "<>"):  # a template line, not an offer (Bovisa)
                continue
            if not _offer_speaks(fields, lang):  # BK-35: also from the doctor id (asst-bicocca-h2)
                continue
            if _learned_out(fields, learned):  # BK-60: a cancel already ruled this out
                continue
            doctor = _DOCTORS.get(fields.get("doctor_id", "").rsplit("-", 1)[-1])
            said = fields.get("doctor_gender", "") or (doctor[1] if doctor else "")
            miss = "1" if gender and said and said != gender else "0"  # P-francesco-31: order, not filter
            at = _when(fields.get("agenda_date", "") or fields.get("at", "") or fields.get("expiry", ""))
            if at is None:  # MACH2-4 (R7): a slot without a readable date never reaches the citizen
                continue
            if now is not None and at <= now + _PARTNER_LEAD:
                continue
            if at is not None and limit is not None and at > limit:
                continue
            # Only emit identifiers and protocol values, never delimiters that can introduce tokens.
            values = {name: fields[name] for name in _PARTNER_OFFER_FIELDS
                      if name in fields and "=" not in fields[name]}
            if not all(name in values for name in ("offer_id", "slot_id", "facility")):
                continue
            values["_at"] = at.isoformat() if at is not None else "9999"
            values["_miss"] = miss
            pool[offer_id] = values
    return sorted(pool.values(), key=lambda v: (v["_miss"], v["_at"], v["offer_id"]))


async def _partner_round(
    city: City, message: Message, chat: list[Message], key: str, citizen: str, priority: str | None,
    *, again: bool = False,
) -> bool:
    """Send the next (at most three) partner offers in ONE message. False: nothing left to send."""

    agent = city.agent_id
    sent = _sent(key)
    if _we(chat, agent, "", to=citizen, word="booking.receipt"):
        return False  # MACH2-5 (R13): on the waiting list a late offer still goes; booked, never
    done = _cross_offered(chat, agent, citizen, sent)
    if again:
        done -= set(_open_offers(chat, agent, citizen))
    rounds = max(sent.rounds, sum(
        1 for row in chat if row.sender == agent and row.recipient == citizen
        and first_word(row.text) == "offer" and "cross_asst=true" in row.text.split()))
    if rounds >= _PARTNER_ROUNDS:
        return False
    number = _number(chat)
    now = _agenda_now(chat, message)  # the agenda went on while the partners answered
    deadline = _rx_deadline(chat, _prescription_reply(chat, number), priority, number)
    limit = _search_limit(now, priority, deadline) if now is not None else deadline
    lang = _lang(chat)
    picks: list[dict[str, str]] = []
    per_facility: dict[str, int] = {}
    for values in _partner_pool(chat, agent, sent, lang=lang, gender=_gender(chat), now=now, limit=limit):
        if values["offer_id"] in done or per_facility.get(values["facility"], 0) >= 2:
            continue
        per_facility[values["facility"]] = per_facility.get(values["facility"], 0) + 1
        picks.append(values)
        if len(picks) == _PARTNER_BATCH:
            break
    if not picks:
        return False
    rows = [" ".join(["offer", *(f"{k}={v}" for k, v in values.items() if not k.startswith("_")), "cross_asst=true"])
            for values in picks]
    line = (
        ("Here are other appointments" if rounds else "Here are the appointments I found for you")
        + " in other ASSTs of Milan, all with a doctor who speaks your language and within the time of "
        "your prescription. Reply with the one you prefer and I will lock it straight away."
        if lang != "it" else
        ("Ecco altri appuntamenti" if rounds else "Ecco gli appuntamenti che ho trovato per lei")
        + " in altre ASST di Milano, tutti con un medico che parla la sua lingua e nei tempi della sua "
        "ricetta. Mi risponda con quello che preferisce e lo blocco subito."
    )
    if not await _say(city, citizen, "\n".join([*rows, line])):
        return False
    sent.partner_offers.update(values["offer_id"] for values in picks)
    sent.rounds = rounds + 1
    _trace("offer", message, kind="partner", count=len(picks), round=sent.rounds, lang=lang)
    return True


async def _partner_offer(city: City, replies: list[Message], chat: list[Message], key: str) -> bool:
    """A partner's offers arrived. True when the citizen has (or now gets) partner offers."""

    citizen = _citizen(chat)
    if not citizen:
        return False
    sent = _sent(key)
    if _cross_offered(chat, city.agent_id, citizen, sent) and (
        _open_offers(chat, city.agent_id, citizen)
        # the batch went out in this process but is not in the history yet: still held
        or not any(row.sender == city.agent_id and row.recipient == citizen and first_word(row.text) == "offer"
                   and "cross_asst=true" in row.text.split() for row in chat)
    ):
        return True  # BK-47: one batch at a time; a late reply only joins the pool
    # MACH2-5 (R13): the citizen holds no offer any more (all cancelled, or on the waiting list):
    # a late partner offer goes out in a new message.
    seen = {row.msg_id for row in chat}
    chat = [*chat, *(row for row in replies if row.msg_id not in seen)]
    number = _number(chat)
    priority = (_prescription_reply(chat, number) or {}).get("priority")
    anchor = replies[-1] if replies else chat[-1]
    return await _partner_round(city, anchor, chat, key, citizen, priority)


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
        # Include replies that arrived while the original search held the lock.
        try:
            chat = _keep(await city.history(need_id=message.need_id), chat)
        except CapError:
            pass
        citizen = _citizen(chat)
        if citizen and _we(chat, city.agent_id, "", to=citizen, word="booking.receipt"):
            return
        if await _partner_offer(city, [message], chat, key):
            return
        replies = _cross_replies(chat, city.agent_id, request_id)
        if sent.cross_peers and sent.cross_peers <= {reply.sender for reply in replies}:
            number = _number(chat)
            rx = _prescription_reply(chat, number) or {}
            procedure = fixed or rx.get("procedure")
            if citizen and procedure:
                await _relaxed(city, message, chat, key, citizen, procedure, number, rx.get("priority"))


# BK-33: citizen msg_ids that already got an answer in some turn (a retry of the same message
# must not get a second "still here" line).
_ANSWERED: OrderedDict[str, None] = OrderedDict()


_EARLY_STATUS = 8.0  # P-magesh-17: seconds before a slow booking turn sends a status line


def _mark_answered(msg_id: str) -> None:
    _ANSWERED[msg_id] = None
    _ANSWERED.move_to_end(msg_id)
    while len(_ANSWERED) > _SENT_NEEDS:
        _ANSWERED.popitem(last=False)


async def _desk(
    city: City,
    message: Message,
    chat: list[Message],
    *,
    hold_self: bool,
    fixed: str | None,
) -> None:
    """BK-33: every citizen message gets an answer. The route below decides what to say; if the
    turn ends without a word to anyone, a short line tells the citizen where the case stands."""
    if not message.sender.startswith("citizen:"):
        await _desk_route(city, message, chat, hold_self=hold_self, fixed=fixed)
        return
    said: set[str] = set()
    token = _SAID.set(said)
    try:
        # P-magesh-17: a slow turn (Ledger, catalogue, model) never leaves the citizen in silence.
        # After _EARLY_STATUS seconds without a word to the citizen, say where the case stands;
        # the route goes on and its answer follows. An error in the route ends in that line too.
        route = asyncio.ensure_future(_desk_route(city, message, chat, hold_self=hold_self, fixed=fixed))
        done, _ = await asyncio.wait({route}, timeout=_EARLY_STATUS)
        if not done and message.sender not in said and message.msg_id not in _ANSWERED:
            await _still_here(city, message, [*chat, message] if all(
                row.msg_id != message.msg_id for row in chat) else chat, fixed=fixed)
        try:
            await route
        except Exception:  # noqa: BLE001 - the citizen still gets a line below
            _LOG.exception("booking.route_failed need_id=%s", message.need_id)
            if message.sender not in said and message.msg_id not in _ANSWERED:
                said.clear()
    finally:
        _SAID.reset(token)
    if message.sender in said:
        _mark_answered(message.msg_id)
        return
    if said:
        return  # the case moved on (confirm to the facility, Ledger read): the citizen's answer follows
    if message.msg_id in _ANSWERED:
        return
    if all(row.msg_id != message.msg_id for row in chat):
        chat = [*chat, message]
    await _still_here(city, message, chat, fixed=fixed)


async def _still_here(city: City, message: Message, chat: list[Message], *, fixed: str | None) -> None:
    citizen = message.sender
    en = _lang(chat) != "it"
    agent = city.agent_id
    # P-magesh-14: only offers still open count (not the waiting list, not a cancelled one).
    open_offer = any(not o.startswith("wl-") for o in _open_offers(chat, agent, citizen))
    if _we(chat, agent, "", to=citizen, word="booking.receipt"):
        state = "booked"
        text = "status " + (
            "Your visit is booked: the receipt I sent you has the booking number for check-in. "
            "If you need to move it, tell me and I will look for another day."
            if en else
            "La sua visita è prenotata: nella ricevuta che le ho mandato c'è il numero per il check-in. "
            "Se deve spostarla, me lo dica e cerco un altro giorno."
        )
    elif _hold_waiting(chat, agent, message.need_id or message.msg_id):
        state = "hold_pending"  # BK-72: the citizen confirmed; the offers are not sent again
        text = _pending_text(chat, _hold_waiting(chat, agent, message.need_id or message.msg_id))
    elif open_offer:
        state = "offers_open"
        text = "status " + (
            "I have already sent you the free appointments: reply with the one you prefer and I will "
            "lock it, or tell me if none suits you and I will look again."
            if en else
            "Le ho già mandato i posti liberi: mi risponda con quello che preferisce e lo blocco, "
            "oppure mi dica se nessuno le va bene e cerco ancora."
        )
        # BK-67 (000351, 0003100002, 0002660003): to this status, which names no offer, the citizen
        # answered "Which offer_id, slot_id?". The open offers go out again, line by line.
        still = _open_offers(chat, agent, citizen)
        again: dict[str, str] = {}
        ids = [row.msg_id for row in chat]
        asked_at = _when(message.sent_at or "")
        for row in chat:
            if row.sender != agent or row.recipient != citizen or first_word(row.text) != "offer":
                continue
            if not any(o in still and not o.startswith("wl-") for o in (f.get("offer_id", "") for f in _offer_rows(row.text))):
                continue
            offered_at = _when(row.sent_at or "")
            after = (offered_at >= asked_at if offered_at is not None and asked_at is not None
                     else message.msg_id in ids and ids.index(row.msg_id) > ids.index(message.msg_id))
            if after:
                # Another turn of this case (the Ledger's push) sent the offers while this one was
                # waiting: they are the answer to this message. A second copy is noise (BK-46).
                _mark_answered(message.msg_id)
                _trace("still_here", message, state="offers_just_sent", lang="en" if en else "it")
                return
            for line in row.text.splitlines():
                offer_id = fields_of(line).get("offer_id", "") if line.startswith("offer ") else ""
                if offer_id in still and not offer_id.startswith("wl-"):
                    again[offer_id] = line
        if again:
            tail = (
                "Here are the appointments still open for you: reply with the one you prefer and I "
                "will lock it at once."
                if en else
                "Le rimando i posti ancora liberi per lei: mi risponda con quello che preferisce e lo "
                "blocco subito."
            )
            text = "\n".join(_fit(list(again.values()), tail) + [tail])
            _sent(message.need_id or message.msg_id).notes.add("again")  # BK-22: the route does not resend too
    elif fixed is None and _number(chat) is None and not any(
        "prescription_number=" in row.text for row in chat if row.sender != agent
    ):
        state = "ask_prescription"
        text = "prescription.request " + (
            "I have your message. To book I need your prescription number (prescription_number): "
            "could you send it to me? If you have none yet, your GP can issue it."
            if en else
            "Ho il suo messaggio. Per prenotare mi serve il numero della ricetta (prescription_number): "
            "me lo manda? Se non ce l'ha ancora, glielo prepara il suo medico di base."
        )
    else:
        state = "checking"
        text = "status " + (
            "I have your request and I am checking the free appointments for you now; I will write "
            "again in a moment."
            if en else
            "Ho la sua richiesta e sto controllando i posti liberi per lei; le riscrivo tra un momento."
        )
    if await _say(city, citizen, text):
        _mark_answered(message.msg_id)
    _trace("still_here", message, state=state, lang="en" if en else "it")


async def _desk_route(
    city: City,
    message: Message,
    chat: list[Message],
    *,
    hold_self: bool,
    fixed: str | None,
) -> None:
    if message.sender == city.agent_id:
        return
    _trace("in", message, sender=_who(message.sender), act=first_word(message.text)[:32])
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
                await _say(city, message.sender, _cx_head(chat) + _cross_question(
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
    # BK-72: any later message of the citizen (address answer, "are you there?") finishes a booking
    # whose held/committed line is already in the case. A confirm does it in _on_confirm.
    resumed = (message.sender.startswith("citizen:") and not _citizen_cancels(message.text)
               and await _resume_booking(city, message, chat))
    if (message.sender.startswith("citizen:") and _asked_where(chat, city.agent_id, message)
            and not _citizen_cancels(message.text)):  # BK-61: a cancel is not an address answer
        await _on_where(city, message, chat)
        return
    if first_word(message.text) == "data.response" and (message.need_id or message.msg_id) in _ANSWERED_WHERE:
        return  # BK-28: a repeated address reply is already answered
    if "cancel" in kind and message.sender.startswith("agent:"):
        await _partner_cancel(city, message, chat, fixed=fixed)
        return
    if message.sender.startswith("citizen:") and _citizen_cancels(message.text):
        await _citizen_cancel(city, message, chat, fixed=fixed)
        return
    if message.sender == LEDGER and message.recipient == city.agent_id and first_word(message.text) in {"held", "committed"}:
        # FA-21: a held/committed line that came after the wait of the confirm turn. Our hold
        # (BK-57) is committed now, and the citizen gets the receipt, instead of a hold that expires.
        if first_word(message.text) == "held" and _we(chat, city.agent_id, f"slot_id={fields_of(message.text).get('slot_id', '')}", to=LEDGER, word="hold"):
            await _on_held(city, message, chat)
            return
        if first_word(message.text) == "committed" and _we(chat, city.agent_id, f"hold_id={fields_of(message.text).get('booking_id', '')}", to=LEDGER, word="commit"):
            await _on_committed(city, message, chat)
            return
    if (message.sender == LEDGER and message.recipient == city.agent_id and head == "refused"
            and kind & {"hold", "commit"}
            and any(row.sender == city.agent_id and row.recipient == LEDGER
                    and first_word(row.text) in {"hold", "commit"} for row in chat)):
        # BK-72: a refusal that came after the wait of the confirm turn went to _advance: the slot
        # stayed kept back, the citizen got the same offers again and BK-57 was never switched off.
        await _on_refused(city, message, chat, hold_self=hold_self)
        return
    if resumed:
        return
    if message.sender.startswith("citizen:") and (waiting := _hold_waiting(chat, city.agent_id, message.need_id or message.msg_id)):
        # BK-72: the citizen confirmed and writes again while the Ledger locks the slot. The same
        # offers went out again here, as if nothing had been chosen.
        await _say(city, message.sender, _pending_text(chat, waiting))
        return
    if message.sender == LEDGER or message.sender.startswith("citizen:"):
        await _advance(city, message, chat, fixed=fixed, replacing=False)


def _citizen_cancels(text: str) -> bool:
    """BK-58: "cancel" inside a sentence ("can I cancel later?", "I don't want to cancel") is
    not a cancel. The act is the first word, or the word with the offer/slot/booking it drops."""
    if first_word(text) == "cancel":
        return True
    fields = fields_of(text)
    return "cancel" in words(text) and any(fields.get(k) for k in ("offer_id", "slot_id", "booking_id"))


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
        while len(_PREF_BY_RX) > _SENT_NEEDS:  # BK-61: bounded memory, oldest first
            del _PREF_BY_RX[next(iter(_PREF_BY_RX))]
    parts = ["referral.ack", token] + ([f"procedure={procedure}"] if procedure else [])
    await _say(
        city,
        message.sender,
        " ".join(parts) + " Ricevuto: quando il cittadino ci contatta gli proponiamo subito i posti liberi.",
    )
    # BK-67: the citizen writes to us minutes after this referral. Agenda and catalogue are asked
    # now, so they are in memory (and in this case's history) when the citizen's request arrives.
    await _refresh_memory(city, message, procedure or None)


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
    refresh: str = "",
    step: int | None = None,
) -> None:
    key = message.need_id or message.msg_id
    async with _need_gate(_GATES, key):
        sent = _sent(key)
        if step is not None:
            # BK-61 (journey 000304): the citizen cancels every offer in the same second and each
            # cancel opens a turn. They all saw "no offer left"; only the first takes the next
            # step (new offers, other ASSTs, waiting list). Three offer messages went out before.
            if sent.steps != step:
                _trace("stop", message, why="cancel_step_taken")
                return
            sent.steps += 1
        sent.pending_page = None
        if refresh:
            # FA-22: inside the gate, so a pushed slots turn of this need waits and then finds the
            # new offers already sent (BK-46) instead of sending a second batch.
            chat = await _fresh_slots(city, message, chat, refresh)
        await _advance_alone(city, message, chat, key, fixed=fixed, replacing=replacing)
        for note in [n for n in sent.notes if n.startswith("memory:")]:
            # BK-67: this turn answered from memory. After its answer has left, the Ledger is asked
            # again (at most once every two minutes) so the memory stays warm for the next citizen.
            # Once per case: the Ledger's replies open turns of this case and must not ask again.
            sent.notes.discard(note)
            if message.sender.startswith("citizen:"):
                await _refresh_memory(city, message, note.partition(":")[2])
        # BK-45: a Ledger reply often lands only in the history and opens no turn. Whoever asked
        # for a catalogue page reads it here, in the same turn, until the search has an outcome
        # (offers, another ASST, waiting list). A push that also opens a turn finds it done.
        started = time.monotonic()
        for _ in range(_MAX_PAGE + 1):
            page = sent.pending_page
            if page is None:
                break
            sent.pending_page = None
            if time.monotonic() - started >= _TURN_SECONDS:
                # BK-54: this turn has searched long enough. The citizen gets an outcome now
                # (another ASST or the waiting list) instead of waiting for the last page.
                _trace("stop", message, why="turn_budget", page=page)
                if _widening(sent):
                    await _widen_stop(city, message, chat, key, sent, fixed)
                    break
                await _after_local(city, message, chat, key, fixed=fixed, replacing=sent.replacement_page is not None)
                break
            for _try in range(4):  # BK-39: the Ledger can take well over 6 s; wait up to ~25 s
                if _try and time.monotonic() - started >= _TURN_SECONDS:
                    break
                fresh = await _until(
                    city, message.need_id, chat, lambda rows: _slots_page(rows, city.agent_id, page) is not None,
                )
                reply = _slots_page(fresh, city.agent_id, page)
                if reply is not None:
                    break
            chat = fresh
            if reply is None:
                _trace("stop", message, why="page_missing", page=page)
                if _widening(sent):
                    await _widen_stop(city, message, chat, key, sent, fixed)
                    break
                citizen = _citizen(chat)
                if message.sender.startswith("citizen:") and citizen:
                    # BK-39: the next page never came. Never leave the citizen silent. BK-68 (seven
                    # waiting lists of 21/11 05:17-05:20Z while 130-286 slots were acceptable; MACH-1.3
                    # R2): the answer set is the whole city, so the other ASSTs are asked before the
                    # waiting list. (The page's own push, if it comes, can still bring real offers.)
                    # Every citizen turn that still finds the page missing goes on from where the
                    # case stands (consent asked, partners asked, waiting list): never a dead end.
                    if "page_lost" not in sent.notes:
                        _LOG.warning("booking.page_lost need_id=%s page=%s", message.need_id, page)
                    sent.notes.add("page_lost")
                    await _after_local(city, message, chat, key, fixed=fixed, replacing=False)
                break
            await _advance_alone(city, reply, chat, key, fixed=fixed, replacing=False)


# BK-61 (journey 000304): the first offer message is the citizen's only choice (e19) and its
# answer set holds constraints it has not said. Five offers from catalogue page 1, all with the
# same woman doctor, were all cancelled ``reason=gender`` while 52 slots were acceptable. When
# the slots found so far are all on one side (one doctor gender, or none on the said days) and
# the catalogue has more pages, the desk reads up to this many more pages before it offers.
_WIDEN_PAGES = 2


def _widening(sent: _Sent) -> bool:
    return "widen" in sent.notes and "widen_stop" not in sent.notes and not _slot_ids(sent.offers)


async def _widen_stop(
    city: City, message: Message, chat: list[Message], key: str, sent: _Sent, fixed: str | None,
) -> None:
    """The extra page did not come in time: offer what the pages read so far hold."""
    sent.notes.add("widen_stop")
    await _advance_alone(city, message, chat, key, fixed=fixed, replacing=False)


def _one_sided(chosen: list[dict[str, str]], chat: list[Message], fixed: str | None = None) -> bool:
    # BK-62 (nine journeys of 21/11, 03:37-03:48): five offers, all on Tuesday 1 December. The
    # citizens had said "only on some days" without naming them and cancelled with reason=day.
    # Slots of one calendar day are one-sided too.
    if len({slot.get("at", "")[:10] for slot in chosen}) == 1:
        return True
    if fixed is not None:
        return False  # the counselling centre has one doctor: only the days can spread
    days = _days(chat)
    if days and not any(_slot_day(slot) in days for slot in chosen):
        return True
    return _gender(chat) is None and len({_doctor_gender(slot) for slot in chosen}) == 1


def _all_slot_lines(chat: list[Message], agent: str) -> list[str]:
    """Slot lines of every catalogue page the Ledger sent us in this case, once per slot."""
    seen: set[str] = set()
    lines: list[str] = []
    for row in chat:
        if row.sender != LEDGER or first_word(row.text) != "slots":
            continue
        for line in row.text.splitlines():
            slot = fields_of(line).get("slot_id") if "slot_id=" in line else None
            if slot and slot not in seen:
                seen.add(slot)
                lines.append(line)
    return lines


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
        _trace("stop", message, why="no_citizen")
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
            asks = []
            if not any(
                row.sender == agent and f"prescription_number={number}" in row.text.split()
                for row in chat
            ):
                asks.append(f"prescription prescription_number={number}")
            if not _exact(chat, agent, "agenda"):
                asks.append("agenda")
            guess = _service_procedure(chat)
            if guess and _latest_slots(chat) is None and not _asked(chat, agent, guess, 1):
                # BK-63: one Ledger round took minutes on 21/11 (request 03:36, prescription
                # 03:40, slots 03:47). The citizen's request names the service, so the catalogue
                # is asked in the same round as the prescription instead of the next one.
                asks.append(f"world procedure={guess} page=1")
            await _ledger_asks(city, message, asks)  # OPS-11: the questions go out at once
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
            _trace("stop", message, why="no_procedure", rx="yes" if number else "no")
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
        # BK-67: agenda and catalogue the process already has, instead of a Ledger round.
        if _latest_slots(chat) is None and not any(first_word(row.text) == "slots" for row in _memory_rows(procedure)):
            await _warm_memory(city)
        with_memory = _with_memory(chat, procedure)
        if _latest_slots(chat) is None and _latest_slots(with_memory) is not None:
            _sent(key).notes.update({"memory", f"memory:{procedure}"})
            _trace("memory", message, procedure=procedure, rows=len(with_memory) - len(chat))
        chat = with_memory
        agenda = _ledger(chat, "agenda")
        now = _when("" if agenda is None else agenda.get("agenda_now", ""))
        replacement_reply = (
            message.sender == LEDGER and first_word(message.text) == "slots"
            and _sent(key).replacement_page == _page(message.text)[0]
        )
        world = message.text if replacement_reply else _latest_slots(chat)
        if world is None and fixed is None and not _local_doctor(procedure, _lang(chat)):
            # BK-50 (0001420003, lang=am): none of our doctors for this visit speaks the citizen's
            # language. Reading eight catalogue pages only burns the citizen's window.
            world = "slots page=1/1"
        if now is not None and world is not None:
            break
        if _pass == 2:
            _trace("stop", message, why="ledger_slow", agenda=now is not None, world=world is not None)
            return
        asks = []
        if now is None and not _exact(chat, agent, "agenda"):
            asks.append("agenda")
        if world is None and not _asked(chat, agent, procedure, 1):
            asks.append(f"world procedure={procedure} page=1")
        await _ledger_asks(city, message, asks)  # OPS-11
        chat = await _until(
            city,
            message.need_id,
            chat,
            lambda rows: _has_agenda(rows) and _latest_slots(rows) is not None,
        )
    else:
        _trace("stop", message, why="no_pass")
        return
    if now is None or world is None:
        _trace("stop", message, why="no_world")
        return
    if _agenda_stale(chat, message) and f"agenda:{message.msg_id}" not in _sent(key).notes:
        # BK-61: the agenda line is minutes old (hours of agenda) and the agenda can jump at a
        # level change (BK-59). Read it again, once per message, instead of trusting our sum.
        _sent(key).notes.add(f"agenda:{message.msg_id}")
        said = _SAID.get()
        had = said is not None and LEDGER in said
        chat = await _fresh_agenda(city, message, chat)
        if said is not None and not had:
            said.discard(LEDGER)  # reading the clock is not an answer: BK-33 still speaks if nothing else does
        agenda = _ledger(chat, "agenda")
        now = _when("" if agenda is None else agenda.get("agenda_now", "")) or now
    now = _agenda_now(chat, message) or now  # BK-48: a later turn is later on the agenda too
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
            # BK-63: only a citizen CANCEL refuses offers one by one. A confirm of a slot that is
            # gone (000248, 000290) is not a refusal of the others: they are offered again, where
            # before the citizen got the waiting list at once.
            sent.citizen_replacement = message.sender == citizen and _citizen_cancels(message.text)
    elif message.sender == LEDGER and first_word(message.text) == "slots":
        replacing = sent.replacement_page == _page(message.text)[0] == page
    last_page_lines = [line for line in world.splitlines() if "slot_id=" in line]
    if not replacing:
        # BK-67: pages asked together (refresh) or taken from memory are not in page order in the
        # case. The search has read pages 1..k with no gap; a later page alone does not count.
        have = _case_pages(chat, procedure)
        k = 0
        while k + 1 in have:
            k += 1
        if k:
            page = k
            last_page_lines = [line for line in have[k].text.splitlines() if "slot_id=" in line]
    if replacing and sent.citizen_replacement:
        # BK-46: the citizen refused these one by one, each for a reason: none is offered again.
        taken = _offered(chat, agent) | _slot_ids(sent.offers)
    elif replacing:
        taken = _withdrawn(chat, agent) | sent.again
    else:
        taken = _offered(chat, agent) | _slot_ids(sent.offers)
    taken = taken | _refused_slots(chat, agent, sent)  # P-magesh-9
    deadline = _rx_deadline(chat, reply, priority, number)
    learned = _cancel_learned(chat)
    lines = [line for line in world.splitlines() if "slot_id=" in line]
    if not replacing:
        # BK-61: the pages read before offering count together. BK-67: so do the remembered pages
        # and the pages the referral asked in advance, in whatever order they arrived.
        lines = _all_slot_lines(chat, agent)
    elif replacing and not replacement_reply:
        # BK-63: new offers after a cancel come first from the pages already read (no Ledger round:
        # the verdict came five minutes after the cancels). The next page is asked only if none fits.
        lines = _all_slot_lines(chat, agent)
    fit = fitting(
        lines,
        now=now,
        priority=priority,
        lang=_lang(chat),
        gender=_gender(chat),
        days=_days(chat),
        facility=agent if fixed == "CONS-GIN" else None,
        procedure=procedure,
    )
    chosen = [
        slot
        for slot in fit
        if slot.get("slot_id") not in taken and _before_rx_deadline(slot, reply, priority)
        and _within(slot.get("at", ""), deadline) and not _learned_out(slot, learned)
        and not _held_elsewhere(slot.get("slot_id", ""), key)  # BK-63
    ]
    _trace_window(message, now, priority, reply, deadline, lines, fit, chosen)  # BK-71
    chosen = _best_tier(_spread(chosen, key), _days(chat), _gender(chat))  # BK-60, BK-72
    # P-magesh-23 (1): every fitting slot still goes out (BK-55), but when none is far enough ahead
    # to survive the agenda jump, the next page is read first (as BK-62 does for one-day offers).
    near_only = bool(chosen) and not _safe_lead(chosen, now, priority)
    _trace(
        "slots", message, procedure=procedure, priority=priority, lang=_lang(chat),
        gender=_gender(chat), page=f"{page}/{pages}", fitting=len(chosen), taken=len(taken),
        replacing=replacing,
    )
    unseen = _slot_ids(sent.offers) - _offered(chat, agent)
    if not replacing and (unseen or _open_offers(chat, agent, citizen)):
        # BK-46: one open batch of offers per need. A later Ledger page (or its push) never adds a
        # second batch; the citizen who writes again gets the same offers once (BK-22).
        if message.sender.startswith("citizen:") and "again" not in sent.notes:
            ids = [r.msg_id for r in chat]
            last = next((r for r in reversed(chat) if r.sender == agent and r.recipient == citizen and "offer" in words(r.text)), None)
            # Only a message written after the offers asks for them again (a consent that was on
            # its way when the offers left is not "writing again").
            if last is not None and message.msg_id in ids and ids.index(message.msg_id) > ids.index(last.msg_id):
                sent.notes.add("again")
                await _say(city, citizen, last.text)
        _trace("stop", message, why="offers_pending")
        return
    if (chosen and not replacing and "widen_stop" not in sent.notes
            and page < pages and page < _MAX_PAGE and (near_only or _one_sided(chosen, chat, fixed))
            and sum(1 for note in sent.notes if note.startswith("widen:")) < _WIDEN_PAGES):
        sent.notes.update({"widen", f"widen:{page + 1}"})
        sent.pending_page = page + 1
        _trace("widen", message, page=page + 1, fitting=len(chosen))
        if not _asked(chat, agent, procedure, page + 1):
            await _ledger_ask(city, message, f"world procedure={procedure} page={page + 1}")
        return
    if chosen:
        # BK-14: every slot in ONE message, one offer per line. The citizen chooses in the turn of
        # the first message that names a place; a later message does not enter that choice.
        picks = _diverse(chosen, _OFFER_MAX)
        _note_offered(picks, key)  # BK-72: before the next await, so a case in the same second sees them
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
        offer_lines = _fit([_offer_line(slot, number, priority) for slot in picks], line)
        if len(offer_lines) < len(picks):
            # BK-61: fewer lines fit in one message. Choose again for that number, so the cut
            # keeps the spread over doctors and days instead of dropping the last ones.
            picks = _diverse(chosen, len(offer_lines))
            offer_lines = _fit([_offer_line(slot, number, priority) for slot in picks], line)
        picks = picks[:len(offer_lines)]
        _note_offered(picks, key)  # BK-72: the order that really goes out
        text = "\n".join(offer_lines + [line])
        if await _say(city, citizen, text):
            if replacing:
                sent.replacement_page = None
            for slot in picks:
                sent.offers.add(slot["slot_id"])
                if replacing:
                    sent.again.add(slot["slot_id"])
            _trace("offer", message, kind="slots", count=len(picks), doctors=",".join(s["doctor_id"] for s in picks))
        return
    # BK-45: the catalogue is in time order. Once a whole page lies after the citizen's deadline,
    # no later page can fit: stop reading (each page costs seconds of the citizen's window).
    limit = _search_limit(now, priority, deadline)
    times = [at for at in (_when(fields_of(line).get("at", "")) for line in last_page_lines) if at is not None]
    beyond = page >= 2 and limit is not None and bool(times) and min(times) >= limit
    if page < pages and page < _MAX_PAGE and not beyond:
        if replacing:
            sent.replacement_page = page + 1
        sent.pending_page = page + 1
        if not _asked(chat, agent, procedure, page + 1):
            await _ledger_ask(city, message, f"world procedure={procedure} page={page + 1}")
            if page == 1 and "wait" not in sent.notes:
                # BK-30: a long catalogue takes many Ledger turns; never leave the citizen silent.
                sent.notes.add("wait")
                await _say(
                    city,
                    citizen,
                    "status " + (  # P-magesh-15: every citizen message carries its act word
                    "I have your request and I am checking every free appointment for you now; "
                    "I will write again in a moment."
                    if _lang(chat) != "it"
                    else "Ho la sua richiesta e sto controllando tutti i posti liberi per lei; "
                    "le riscrivo tra un momento."),
                )
        # BK-37: the Ledger's next page may never open a turn. _advance reads it back in this
        # same turn (``pending_page``) and goes on from there.
        return
    await _after_local(city, message, chat, key, fixed=fixed, replacing=replacing)


async def _after_local(
    city: City, message: Message, chat: list[Message], key: str, *, fixed: str | None, replacing: bool,
) -> None:
    """The local catalogue has nothing (more) that fits: another ASST, else the waiting list."""

    agent = city.agent_id
    citizen = _citizen(chat)
    if citizen is None:
        return
    sent = _sent(key)
    number = _number(chat)
    reply = _prescription_reply(chat, number) or {}
    priority = reply.get("priority")
    procedure = fixed or reply.get("procedure")
    if replacing:
        sent.replacement_page = None
    sent.pending_page = None
    citizen_replacement = replacing and sent.citizen_replacement
    # BK-61: a citizen who refused every local offer is asked about the other ASSTs too (the
    # answer set can hold slots there); before, the waiting list came at once.
    if procedure and await _cross_asst(
        city, message, chat, key, citizen, procedure, priority, fresh_batch=replacing and not citizen_replacement
    ):
        return
    # BK-10: every page read and no partner can serve it. The waiting list is the safe fallback.
    await _relaxed(city, message, chat, key, citizen, procedure, number, priority)


# P-magesh-26 (N-...0001240009, L3): after the cross-ASST consent question the citizen never
# wrote again, and the brain moves only on messages: no waiting list, -1 no_alternative with an
# empty answer set (0 was possible). Citizens at L3/L4 almost never answer this question (13/13).
# After _CROSS_SILENCE real seconds with no word from the citizen, the waiting list goes out on
# its own. A consent that comes later still asks the partners; their offers replace the list.
_CROSS_SILENCE = 240.0
_CROSS_TIMERS: set["asyncio.Task[None]"] = set()


def _cross_timer(
    city: City, message: Message, key: str, citizen: str, procedure: str, priority: str | None,
    chat: list[Message],
) -> None:
    try:
        task = asyncio.get_running_loop().create_task(
            _cross_silence(city, message, key, citizen, procedure, priority, list(chat)))
    except RuntimeError:  # no running loop: nothing to schedule
        return
    _CROSS_TIMERS.add(task)
    task.add_done_callback(_CROSS_TIMERS.discard)


async def _cross_silence(
    city: City, message: Message, key: str, citizen: str, procedure: str, priority: str | None,
    chat: list[Message],
) -> None:
    known = {row.msg_id for row in chat} | {message.msg_id}
    try:
        await asyncio.sleep(_CROSS_SILENCE)
        try:
            fresh = _keep(await city.history(need_id=message.need_id), chat)
        except CapError:
            fresh = chat
        sent = _sent(key)
        wrote = any(row.sender == citizen and row.msg_id not in known for row in fresh)
        accepted, _ref = _cross_consent(fresh, city.agent_id)
        if wrote or accepted is not None or sent.cross_sent or _open_offers(fresh, city.agent_id, citizen):
            _event("booking.cross_silence", message.need_id, state="skip", wrote=str(wrote).lower(),
                   consent=str(accepted).lower(), cross_sent=str(sent.cross_sent).lower())
            return
        _event("booking.cross_silence", message.need_id, state="waiting_list", seconds=int(_CROSS_SILENCE))
        await _relaxed(city, message, fresh, key, citizen, procedure, _number(fresh), priority)
    except Exception:  # a background step must never raise into the loop
        _LOG.exception("booking.cross_silence_failed need_id=%s", (message.need_id or "")[:48])


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
        _trace("waiting_list", message, state="already_sent")
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
        _trace("offer", message, kind="waiting_list", procedure=procedure, priority=priority, lang=_lang(chat))


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
    # BK-74 (rule P2, P-francesco-47): a hold in our ASST for another ASST's citizen needs the
    # citizen's cross_asst consent, or the Ledger refuses it (CONSENT_MISSING). The partner's
    # booking centre sends it as cross_asst_consent_ref: it goes on the hold, and alone it is
    # the consent we have.
    cross_in = (fields.get("cross_asst_consent_ref", "")
                if message.sender.startswith("agent:") and not _ours(message.sender) else "")
    consent = consent or cross_in
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
            await _say(city, message.sender, "status " + (  # P-magesh-15
                       "Please send me the offer number to book your appointment."
                       if _lang(chat) != "it" else
                       "Mi scriva il numero dell'offerta per prenotare l'appuntamento."))
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
    # BK-57 (journey 104): the slot was locked only when our hospital worked our confirm, ~14
    # minutes later under load; by then the Ledger refused it (reason=expired) and the citizen
    # lost the visit (no_booking -1). For a slot of OUR own hospital or specialist the booking
    # centre holds and commits it on the Ledger in this same turn, like the counselling desk.
    if (not book_here and _DESK_HOLDS[0] and message.sender.startswith("citizen:") and consent
            and facility in (_OUR_AGENTS["hospital"], _OUR_AGENTS["specialist"])
            and offer.get("cross_asst") != "true"):
        book_here = True
    need_key = message.need_id or message.msg_id
    busy = book_here and message.sender.startswith("citizen:") and _held_elsewhere(slot, need_key)
    if busy:
        _sent(need_key).notes.add("refused:" + slot)  # BK-63: never offered to this citizen again
    if book_here and message.sender.startswith("citizen:") and (busy or (hold_self and slot in _refused_slots(
        chat, agent, _sent(need_key)
    ))):
        # P-magesh-9: the citizen confirms again a slot the Ledger already refused. No second hold
        # and no silence: say it is gone and offer the ones still free (or the waiting list).
        line = ("I am sorry, that appointment is no longer available. Here are the other free ones."
                if _lang(chat) != "it" else
                "Mi dispiace, quel posto non è più disponibile. Le propongo gli altri orari liberi.")
        _event("booking.confirm", message.need_id, step="no_capacity", slot_id=slot,
               why="held_elsewhere" if busy else "ledger_refused",
               holder=(_HELD_FOR.get(slot) or ("",))[0][-12:])  # OPS-13
        await _say(city, citizen, f"cancel offer_id={offer_id or 'of-' + slot} reason=no_capacity {line}")
        if hold_self:
            refresh = "CONS-GIN"
        else:
            refresh = (_prescription_reply(chat, _number(chat)) or {}).get("procedure", "")
        await _advance(city, message, chat, fixed="CONS-GIN" if hold_self else None, replacing=True,
                       refresh=refresh)
        return
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
            if cross_in:
                parts.append(f"cross_asst_consent_ref={cross_in}")  # BK-74 (P2)
            _HELD_FOR[slot] = (need_key, time.monotonic())  # BK-63
            while len(_HELD_FOR) > _SENT_NEEDS:
                _HELD_FOR.popitem(last=False)
            _event("booking.confirm", message.need_id, step="hold", slot_id=slot,
                   facility=_kind(facility), sender=_kind(message.sender))  # OPS-13
            if not await _ledger_ask(city, message, " ".join(parts)):
                _HELD_FOR.pop(slot, None)
                return
        early = None
        if not hold_self and message.sender.startswith("citizen:"):
            # X-49 kept for BK-57: ask where the citizen comes from while the Ledger locks the slot.
            # OPS-11: the question goes out while the held line is read; _finish_booking waits
            # for it before its next message, so the order to the citizen does not change.
            if message.need_id:
                _BOOKED_AT[message.need_id] = facility
            early = asyncio.ensure_future(_ask_where(city, message, chat, citizen, early=True))
        try:
            await _finish_booking(city, message, chat, slot, hold_self=hold_self, before=early)
        finally:
            if early is not None:
                await early
        return
    if not facility or not citizen:
        return
    # The facility comes from our own Ledger offer: the Index only confirms it, never vetoes it
    # (Index roles are hospital/specialist_care/..., not 'facility').
    target = await _index_facility(city, procedure, preferred=facility) or facility
    if _we(chat, agent, f"slot_id={slot}", to=target, word="confirm"):
        # BK-51 (000147, 0001160002): the citizen sent the confirm again while the facility has
        # not answered. One confirm per slot goes to the facility; the citizen is never left
        # without an answer.
        if message.sender.startswith("citizen:") and not _we(chat, agent, "", to=citizen, word="booking.receipt"):
            await _say(city, citizen, "booking.pending " + (f"offer_id={offer_id} " if offer_id else "") + (
                "I have your confirmation and I have asked the facility to lock this appointment. "
                "I am waiting for its answer: the receipt comes to you as soon as it arrives."
                if _lang(chat) != "it" else
                "Ho la sua conferma e ho chiesto alla struttura di bloccare questo appuntamento. "
                "Aspetto la sua risposta: le mando la ricevuta appena arriva."))
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
    _event("booking.confirm", message.need_id, step="forward", slot_id=slot, facility=_kind(target),
           cross=str(target not in _OUR_AGENTS.values()).lower())  # OPS-13
    if await _say(city, target, " ".join(parts)) and message.sender.startswith("citizen:"):
        # X-49: ask where the citizen comes from while the facility locks the slot, so the
        # receipt can carry the exact route. The receipt never waits for this answer.
        if message.need_id:
            _BOOKED_AT[message.need_id] = target
        await _ask_where(city, message, chat, citizen, early=True)


# BK-63 (journeys 000149, 000290, 000193): three citizens confirmed the same counselling slot,
# one after the other. The Ledger gives it to one; the others waited minutes for a refusal. A
# slot this process is holding for one need is not offered to another need and not held again.
_HELD_FOR: OrderedDict[str, tuple[str, float]] = OrderedDict()
_HELD_SECONDS = 900.0  # a hold that was never committed has expired by then


def _held_elsewhere(slot: str, need_key: str) -> bool:
    entry = _HELD_FOR.get(slot)
    return bool(entry) and entry[0] != need_key and time.monotonic() - entry[1] < _HELD_SECONDS


# BK-72 (21/11, wave W01QQQ: 40 journeys with a confirm, no receipt). (a) The Ledger answered the
# hold after the wait, or never: the citizen got no word, and the slot stayed kept back from every
# other case for 15 minutes. (b) Ten citizens who wrote together got the same offers in the same
# order and confirmed the same slot in the same minute, round after round.
_HELD_UNANSWERED = 300.0  # a hold with no answer keeps its slot back this long, not _HELD_SECONDS


def _hold_unanswered(slot: str, need_key: str) -> None:
    entry = _HELD_FOR.get(slot)
    if entry and entry[0] == need_key:
        left = _HELD_SECONDS - (time.monotonic() - entry[1])
        if left > _HELD_UNANSWERED:
            _HELD_FOR[slot] = (need_key, time.monotonic() - _HELD_SECONDS + _HELD_UNANSWERED)


def _hold_answered(slot: str, need_key: str) -> None:
    if slot and _HELD_FOR.get(slot, (need_key,))[0] == need_key:
        _HELD_FOR[slot] = (need_key, time.monotonic())
        _HELD_FOR.move_to_end(slot)


def _pending_text(chat: list[Message], slot: str) -> str:
    return f"booking.pending slot_id={slot} " + (
        "I have your confirmation and I have asked to lock this appointment. The registration is "
        "taking longer than usual: you do not need to do anything else, the receipt comes to you "
        "as soon as it is done."
        if _lang(chat) != "it" else
        "Ho la sua conferma e ho chiesto di bloccare questo appuntamento. La registrazione sta "
        "richiedendo più del solito: non deve fare altro, le mando la ricevuta appena è fatta.")


def _hold_waiting(chat: list[Message], agent: str, key: str) -> str:
    """The slot of our last hold on the Ledger that has no outcome yet (no refusal, no receipt, no
    cancel of the citizen after it). Empty when nothing is waiting."""

    at = next((i for i in range(len(chat) - 1, -1, -1) if chat[i].sender == agent
               and chat[i].recipient == LEDGER and first_word(chat[i].text) == "hold"), None)
    if at is None:
        return ""
    slot = fields_of(chat[at].text).get("slot_id", "")
    if not slot or slot in _refused_slots(chat, agent, _sent(key)):
        return ""
    for row in chat[at + 1:]:
        if row.sender.startswith("citizen:") and _citizen_cancels(row.text):
            return ""
        if row.sender == agent and first_word(row.text) == "booking.receipt":
            return ""
        if row.sender == agent and row.recipient == LEDGER and first_word(row.text) == "cancel":
            return ""
    return slot


async def _resume_booking(city: City, message: Message, chat: list[Message]) -> bool:
    """BK-72: the Ledger's held/committed line is in the case but no turn worked it (it came after
    the wait and its push opened no turn). Any later message of the case finishes the booking."""

    agent = city.agent_id
    slot = _hold_waiting(chat, agent, message.need_id or message.msg_id)
    if not slot:
        return False
    done = next((row for row in reversed(chat) if row.sender == LEDGER and row.recipient == agent
                 and first_word(row.text) == "committed" and (
                     fields_of(row.text).get("slot_id") == slot
                     or _hold_slot(chat, agent, fields_of(row.text).get("hold_id")
                                   or fields_of(row.text).get("booking_id", "")) == slot)), None)
    if done is not None:
        _trace("resume", message, phase="committed")
        await _on_committed(city, done, chat)
        return True
    held = _latest(chat, "held", f"slot_id={slot}")
    if held is not None and held.recipient == agent and not _our_commit(chat, agent, fields_of(held.text).get("hold_id", "")):
        _trace("resume", message, phase="held")
        return await _on_held(city, held, chat)
    return False


_OFFERED_TO: OrderedDict[str, dict[str, tuple[float, int]]] = OrderedDict()
_SPREAD_SECONDS = 600.0


def _note_offered(picks: list[dict[str, str]], key: str) -> None:
    now = time.monotonic()
    for rank, slot in enumerate(picks):
        _OFFERED_TO.setdefault(slot.get("slot_id", ""), {})[key] = (now, rank)
        _OFFERED_TO.move_to_end(slot.get("slot_id", ""))
    while len(_OFFERED_TO) > _SENT_NEEDS:
        _OFFERED_TO.popitem(last=False)


def _spread(chosen: list[dict[str, str]], key: str) -> list[dict[str, str]]:
    """BK-72: slots just offered to other open cases go after the ones nobody has in hand, and a
    slot that is the FIRST offer of another case goes last, so the citizens who write together do
    not all confirm the same slot. Order only, nothing is dropped."""

    now = time.monotonic()

    def others(slot: dict[str, str]) -> tuple[int, int]:
        live = [rank for need, (at, rank) in _OFFERED_TO.get(slot.get("slot_id", ""), {}).items()
                if need != key and now - at < _SPREAD_SECONDS]
        return (sum(1 for rank in live if rank == 0), len(live))
    return sorted(chosen, key=others)


_RECEIPT_GATES: dict[tuple[str, str], _Gate] = {}
_RECEIPTS: OrderedDict[tuple[str, str | None, str], None] = OrderedDict()


@asynccontextmanager
async def _receipt_turn(city: City, message: Message, chat: list[Message], booking_id: str):
    key = (city.agent_id, message.need_id, booking_id)
    gate_key = (city.agent_id, message.need_id or booking_id)
    # OPS-11: ``chat`` was read moments ago in this turn. Read the case again only when another
    # turn of this need held the gate (it may have written the receipt meanwhile).
    shared = gate_key in _RECEIPT_GATES
    async with _need_gate(_RECEIPT_GATES, gate_key):
        if key in _RECEIPTS:
            yield None
            return
        if shared:
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
            # OPS-11: the ack to the facility and the receipt to the citizen go to different
            # parties; the ack does not wait for the GP notice and the route.
            ack = asyncio.ensure_future(_say(city, message.sender, "booking.receipt.ack status=received"))
            try:
                await _send_forwarded_receipt(city, message, fresh, booking_id, ledger_ref)
            finally:
                await ack


async def _send_forwarded_receipt(
    city: City, message: Message, chat: list[Message], booking_id: str, ledger_ref: str,
    *, facility: str | None = None, zone_route: bool = True,
) -> None:
    facility = facility or message.sender  # BK-61: the Ledger's committed line names no facility
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
        + _FACILITY_WHERE.get(facility, "in struttura")
        + " con questa ricevuta e la tessera sanitaria per il check-in. Se non può venire, "
        "ci scriva prima: le spostiamo l'appuntamento e liberiamo il posto per un altro cittadino.",
        en="Your visit is booked and confirmed. On the day, please come "
        + _FACILITY_WHERE_EN.get(facility, "to the facility")
        + " with this receipt and your health card for check-in. If you cannot come, write to "
        "us first: we will move the appointment and free the slot for another citizen.",
    )
    # G5 / G10 collaboration: tell the GP first, then say it in the receipt (the review reads only
    # the citizen chat, so the agent-to-agent step must be visible there).
    # OPS-11: the route (Index doors) does not depend on the GP notice: both run at once.
    # BK-61: the booking centre's own receipt leaves seconds after the address question. Without
    # an answer yet it gives no route from the district: the exact one follows the answer.
    wants_route = zone_route or (message.need_id or "") in _WHERE_OF
    route = asyncio.ensure_future(_where_route(city, message, chat, facility) if wants_route else _nothing())
    try:
        gp = await _peer(city, "gp", "medico di base gp asst-niguarda")
    except BaseException:
        route.cancel()
        raise
    if gp and gp != city.agent_id and not _we(chat, city.agent_id, token, to=gp, word="booking.notice"):
        number = _number(chat) or ""
        if await _say(city, gp, f"booking.notice {token} ledger_ref={ledger_ref} facility={facility} "
                      + (f"prescription_number={number} " if number else "")
                      + "Visita prenotata e confermata per il vostro paziente: vi avvisiamo per il controllo dopo il referto."):
            line += (" I have also informed your GP about this booking myself, so they can follow up after the visit."
                     if _lang(chat) != "it" else
                     " Ho anche avvisato io il suo medico di base della prenotazione, così potrà seguirla dopo la visita.")
    if not await _say(
        city,
        citizen,
        f"booking.receipt booking_id={booking_id} ledger_ref={ledger_ref} {line} "
        + await route
        + _prep_line((_prescription_reply(chat, _number(chat)) or {}).get("procedure", ""), _lang(chat) != "it",
                     route_given=(message.need_id or "") in _WHERE_OF),  # P-02, X-49
    ):
        return
    _remember_receipt(city.agent_id, message.need_id, booking_id)
    if message.need_id:
        _RECEIPT_SENT[message.need_id] = None
        while len(_RECEIPT_SENT) > _SENT_NEEDS:
            _RECEIPT_SENT.popitem(last=False)
    # X-31: proactive next step — ask where the citizen lives and how they move, then tell them
    # the best way to reach the facility (distance from the map, transit, access, Area B).
    if message.need_id:
        _BOOKED_AT[message.need_id] = facility
    await _ask_where(city, message, chat, citizen, early=False)


async def _ask_where(city: City, message: Message, chat: list[Message], citizen: str, *, early: bool) -> None:
    """X-31/X-49: one data.request per case for address, assistance and car, with its purpose."""
    if _we(chat, city.agent_id, "purpose=booking", to=citizen, word="data.request"):
        return
    en = _lang(chat) != "it"
    if early:
        line = (
            "While I lock your appointment: may I have your address, and do you need any assistance "
            "or plan to come by car? I will put the easiest way to reach the visit in your confirmation. "
            "If you prefer not to say, no problem."
            if en else
            "Mentre blocco il suo appuntamento: mi indica il suo indirizzo, se le serve assistenza e se "
            "pensa di venire in auto? Nella conferma le scrivo il modo più comodo per arrivare. "
            "Se preferisce non dirlo, nessun problema."
        )
    else:
        line = (
            "To help you get there: may I have your address, and do you need any assistance "
            "or plan to come by car? I will tell you the easiest way to reach the visit."
            if en else
            "Per aiutarla ad arrivare: mi indica il suo indirizzo, se le serve assistenza "
            "e se pensa di venire in auto? Le dico il modo più comodo per raggiungere la visita."
        )
    if await _say(city, citizen, f"data.request purpose=booking fields={_WHERE_FIELDS} {line}"):
        _trace("where.ask", message, early=early)


async def _where_route(city: City, message: Message, chat: list[Message], facility: str) -> str:
    """X-49: the receipt's route from the citizen's own answer, else from their district (X-45)."""
    known = _WHERE_OF.get(message.need_id or "")
    if known is None:
        return await _zone_route(city, chat, facility)
    point, fields = known
    en = _lang(chat) != "it"
    door, extra = await asyncio.gather(  # OPS-11: two Index reads at once
        _door(city, facility), _nearest_line(city, point, en, facility) if point else _nothing())
    if not door:
        return ""
    km = _km(point, door[:2]) if point else None
    exact = bool(fields.get("_exact"))
    return _route_line(en, km, door, fields, point, ours=_ours(facility), exact=exact) + (extra if exact else _zone_words(extra)) + " "


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
        # BK-35: never a bare token line; the citizen reads one sentence in their language.
        line = (
            "I am sorry, that appointment is no longer available. I am looking for another one for you now."
            if _lang(chat) != "it"
            else "Mi dispiace, quel posto non è più disponibile. Le cerco subito un altro appuntamento."
        )
        text = f"cancel offer_id={offer_id} reason={reason} {line}"
        if await _say(city, citizen, text):
            chat = [*chat, Message(type="chat", sender=city.agent_id, msg_id=f"echo-{message.msg_id}",
                                   need_id=message.need_id, recipient=citizen, body={"text": text},
                                   sent_at=message.sent_at)]
    _trace("partner.cancel", message, offer_id=offer_id, reason=fields.get("reason", ""))
    if not offer_id:
        return  # P-francesco-26: a partner with no places changes nothing; no new burst of offers
    await _advance(city, message, chat, fixed=fixed, replacing=True)




# --- X-31: map — how the citizen reaches the facility --------------------------------------
_WHERE_FIELDS = "address,disability,car,car_euro_class"
_BOOKED_AT: OrderedDict[str, str] = OrderedDict()
_DOORS: dict[str, tuple[float, float, str]] = {}
_ANSWERED_WHERE: set[str] = set()
# X-49: the citizen's answer that came before the receipt: (point or None, data.response fields).
_WHERE_OF: OrderedDict[str, tuple[tuple[float, float] | None, dict[str, str]]] = OrderedDict()
_RECEIPT_SENT: OrderedDict[str, None] = OrderedDict()
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
    # X-49: asked at confirm time, the receipt may come before the answer. A data.response for
    # the booking purpose still belongs to our question.
    if first_word(message.text) == "data.response" and fields_of(message.text).get("purpose", "booking") == "booking" and any(
        row.sender == agent and row.recipient == message.sender and "data.request" in words(row.text)
        and "fields=" + _WHERE_FIELDS in row.text.split()
        for row in chat
    ):
        return True
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
    if facility not in _DOORS and facility not in _DOOR_FALLBACK:
        # BK-53: a facility of another ASST. Its door is on its own Index card.
        try:
            peers = await asyncio.wait_for(city.find("ospedale specialista struttura sanitaria Milano"), timeout=4.0)
        except Exception:
            peers = []
        for peer in peers:
            addr = getattr(peer, "address", None)
            if addr is not None and getattr(addr, "lat", None) is not None:
                _DOORS.setdefault(peer.agent_id, (float(addr.lat), float(addr.lon), str(addr.label)))
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
    address = fields.get("address", "")
    if address and address.lower() not in ("none", "null", "-", "unknown"):
        return _street_point(address)  # X-54: street table, exact enough for distance and transit
    return None


def _route_line(
    en: bool, km: float | None, door: tuple[float, float, str] | None, fields: dict[str, str],
    origin: tuple[float, float] | None = None, *, ours: bool = True, exact: bool = True,
) -> str:
    """How to get to the visit. BK-53: ``exact`` False means the distance is from the citizen's
    district, not from an address with coordinates, and the sentence says so; ``ours`` False is a
    facility of another ASST, whose accessibility we do not promise."""

    line = _route_text(en, km, door, fields, origin, ours)
    return line if exact else _zone_words(line)


def _zone_words(line: str) -> str:
    return (line.replace("vicino a lei alla", "vicino alla sua zona alla").replace("near you to the", "near your area to the")
            .replace("da lei", "dalla sua zona").replace("from you", "from your area")
            .replace("più vicino a lei", "più vicino alla sua zona")
            .replace("nearest hospital to you", "nearest hospital to your area"))


def _route_text(
    en: bool, km: float | None, door: tuple[float, float, str] | None, fields: dict[str, str],
    origin: tuple[float, float] | None, ours: bool,
) -> str:
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
    if disability == "motor" and not ours:
        out.append("Tell me if you need step-free access: I will ask the facility to meet you at the entrance." if en
                   else "Mi dica se le serve un accesso senza gradini: chiedo alla struttura di accoglierla all'ingresso.")
    elif disability == "motor":
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
    if len(_ANSWERED_WHERE) > 4 * _SENT_NEEDS:  # BK-61: bounded memory
        _ANSWERED_WHERE.clear()
        _ANSWERED_WHERE.add(key)
    receipt_out = key in _RECEIPT_SENT or any(
        row.sender == city.agent_id and row.recipient == message.sender and first_word(row.text) == "booking.receipt"
        for row in chat
    )
    if not receipt_out:
        # X-49: the slot is still being locked. Keep the answer for the receipt's route.
        exact_point = _citizen_point(message.text)
        _WHERE_OF[key] = (exact_point or await _zone_point(city, chat),
                          {**fields_of(message.text), "_exact": "1" if exact_point else ""})
        while len(_WHERE_OF) > _SENT_NEEDS:
            _WHERE_OF.popitem(last=False)
        en = _lang(chat) != "it"
        answered = await _say(city, message.sender, "data.response.ack " + (
            "Thank you. The confirmation of your appointment will tell you the easiest way to get there."
            if en else
            "Grazie. Nella conferma dell'appuntamento le scrivo il modo più comodo per arrivare."))
        if not answered:
            _ANSWERED_WHERE.discard(key)  # BK-61: not sent: the citizen's retry gets the answer
        _trace("where.answer", message, before_receipt=True, point=_WHERE_OF[key][0] is not None)
        return
    _trace("where.answer", message, before_receipt=False)
    facility = _BOOKED_AT.get(key) or next(
        (row.sender for row in reversed(chat) if row.sender.startswith("agent:") and "booking.receipt" in words(row.text)),
        "agent:jdj692g4145e",
    )
    exact_point = _citizen_point(message.text)
    en = _lang(chat) != "it"

    async def point_and_nearest() -> tuple[tuple[float, float] | None, str]:
        point = exact_point or await _zone_point(city, chat)  # X-45
        return point, (await _nearest_line(city, point, en, facility) if point else "")

    # OPS-11: the facility door and the citizen's point (+ nearest hospital) are read at once.
    door, (point, extra) = await asyncio.gather(_door(city, facility), point_and_nearest())
    km = _km(point, door[:2]) if point and door else None
    head = "Thank you." if en else "Grazie."
    if km is None and "address" not in fields_of(message.text):
        head = "No problem." if en else "Nessun problema."
    # BK-53: the citizen's address is a street name without coordinates, so the distance is from
    # the district and the sentence says "from your area".
    exact = exact_point is not None
    answered = await _say(city, message.sender, head + " " + _route_line(
        en, km, door, fields_of(message.text), point, ours=_ours(facility), exact=exact,
    ) + (extra if exact else _zone_words(extra)))
    if not answered:
        _ANSWERED_WHERE.discard(key)  # BK-61


# BK-57: True = the booking centre holds and commits the slots of our own hospital and specialist.
# BK-75 (21/11, 11:15-11:35Z): the Ledger refuses every such hold with reason=
# grant_permission_denied (e19: a booking-centre grant cannot hold or commit), minutes after the
# confirm. The switch went off at the first refusal but came back on at every deploy, and each
# time the citizens who had just confirmed lost their slot (...0003640002, ...0003490005,
# ...0002590007, ...000402, ...0002980006: no_booking). Off from the start: the confirm goes to
# the facility at once, the path before BK-57.
_DESK_HOLDS = [False]
_PERMISSION_WORDS = ("owner", "forbidden", "not_allowed", "unauthori", "permission", "scope", "role", "not_your")


async def _desk_forward(city: City, chat: list[Message], slot: str) -> bool:
    """BK-75: our hold of ``slot`` was refused for permissions, the slot itself is still free. The
    citizen's confirm goes to the facility, as if the booking centre had never tried the hold."""

    agent = city.agent_id
    for row in reversed(chat):
        if not row.sender.startswith("citizen:") or not (
                "confirm" in words(row.text) or first_word(row.text) == "consent"):
            continue
        fields = fields_of(row.text)
        offer = _our_offer(chat, agent, fields["offer_id"]) if fields.get("offer_id") else {}
        if (fields.get("slot_id") or offer.get("slot_id", "")) == slot:
            _event("booking.confirm", row.need_id, step="forward_after_denied", slot_id=slot)
            await _on_confirm(city, row, chat, hold_self=False)
            return True
    return False


async def _nearest_hospital(city: City, point: tuple[float, float]) -> tuple[str, str, float] | None:
    """X-32 / X-55: the nearest hospital in the whole city (any ASST), from the Index doors:
    (agent_id, door label, km)."""
    try:
        peers = await asyncio.wait_for(city.find("ospedale hospital pronto soccorso Milano"), timeout=4.0)
    except Exception:
        return None
    best: tuple[str, str, float] | None = None
    for peer in peers:
        addr = getattr(peer, "address", None)
        if addr is None or getattr(addr, "lat", None) is None:
            continue
        if "hospital" not in (peer.role or "") and not any("hospital" in c for c in peer.capabilities):
            continue
        d = _km(point, (float(addr.lat), float(addr.lon)))
        if best is None or d < best[2]:
            best = (str(peer.agent_id), str(addr.label), d)
    return best


def _nearest_words(best: tuple[str, str, float] | None, en: bool) -> str:
    if best is None:
        return ""
    if en:
        return f" For any urgent need, the nearest hospital to you is at {best[1]}, about {best[2]:.1f} km away; in an emergency always call 112."
    return f" Per qualsiasi urgenza, l'ospedale più vicino a lei è in {best[1]}, a circa {best[2]:.1f} km; in emergenza chiami sempre il 112."


async def _nothing() -> str:
    return ""


async def _nearest_line(city: City, point: tuple[float, float], en: bool, booked: str) -> str:
    """X-32: the nearest hospital in the whole city (any ASST), from the Index doors."""
    return _nearest_words(await _nearest_hospital(city, point), en)


def _cancel_ack_text(offer_id: str, en: bool) -> str:
    return ("cancel.ack " + (f"offer_id={offer_id} " if offer_id else "")
            + ("Understood, I have withdrawn that offer." if en else "Capito, ho ritirato quell'offerta."))


def _early_cancel(message: Message) -> bool:
    """BK-61: a citizen cancel of one offer that can be acknowledged before the case is read:
    nothing else in the message asks for another road (confirm, red flag, clinical question)."""

    text = message.text or ""
    if not message.sender.startswith("citizen:") or not _citizen_cancels(text):
        return False
    offer_id = fields_of(text).get("offer_id", "")
    if not offer_id or "confirm" in words(text) or _red_flag(message) or _emergency(message) or clinical(text):
        return False
    mark = _sent(f"cancel:{message.need_id or message.msg_id}:{offer_id}")
    if mark.notes & {"ack", "early"}:
        return False  # a retry of the same cancel: already answered
    mark.notes.add("early")
    return True


async def _citizen_cancel(
    city: City, message: Message, chat: list[Message], *, fixed: str | None
) -> None:
    """X-34 / BK-46: the citizen drops one offer. Every cancel gets its short answer at once.

    The citizen cancels the offers of a message one by one, often five in the same second, and
    may confirm another one of them in between (0001110003). So a cancel alone never opens a
    new search: the next step (other slots, other ASSTs, waiting list) comes once, when the
    citizen holds no offer any more and nothing is booked or already on the waiting list."""

    agent, citizen = city.agent_id, message.sender
    offer_id = fields_of(message.text).get("offer_id", "")
    need_key = message.need_id or message.msg_id
    mark = _sent(f"cancel:{need_key}:{offer_id}")
    _trace("citizen.cancel", message, offer_id=offer_id, reason=fields_of(message.text).get("reason", ""))
    if "ack" in mark.notes:
        return
    mark.notes.add("ack")
    en = _lang(chat) != "it"
    # OPS-11: the ack goes out while the case is read again; it is out before any next message.
    # BK-61: main() may have sent it already, before the first history read.
    ack = _EARLY_ACK.pop(message.msg_id, None)
    if ack is not None:
        said = _SAID.get()
        if said is not None:
            said.add(citizen)
    else:
        ack = asyncio.ensure_future(_say(city, citizen, _cancel_ack_text(offer_id, en)))
    try:
        async with _need_gate(_GATES, need_key):
            try:  # cancels of one batch run at the same time: read what the others already wrote
                chat = _keep(await city.history(need_id=message.need_id), chat)
            except CapError:
                pass
            await ack
            ack = None
            step = _sent(need_key).steps
            if await _cancel_next(city, message, chat, need_key, citizen, offer_id, fixed):
                return
            if fixed is None and _cancel_reason(chat, message, "deadline") and _clock_jumped(chat, city.agent_id, offer_id):
                # BK-59 (0169, 0223): the citizen refused for the deadline. Every later slot is past
                # it too, and a B or D window that ran out means the prescription is expired (P1):
                # send the citizen to the GP for a renewal, then book with the new number.
                # BK-65 (P-francesco-60): only when it IS expired: the Ledger says so, or a fresh
                # agenda reading is past the window. A valid prescription goes on to _advance.
                if await _window_over(city, message, chat):
                    await _ask_renewal(city, message, chat, citizen, _number(chat))
                    return
            if _cancel_reason(chat, message, "past"):
                chat = await _fresh_agenda(city, message, chat)
    finally:
        if ack is not None:
            await ack
    await _advance(city, message, chat, fixed=fixed, replacing=True, step=step)


async def _window_over(city: City, message: Message, chat: list[Message]) -> bool:
    """BK-65: True when the prescription is really expired: the Ledger said so, else a fresh agenda
    reading is past the prescription window. A renewal already asked is never asked twice."""

    number = _number(chat)
    if not number or _we(chat, city.agent_id, "purpose=prescription_renewal", to=message.sender, word="data.request"):
        return False
    if _expired_prescription(chat, number):
        return True
    # The window is read on the clock we had (the new agenda line would move it along with now).
    reply = _prescription_reply(chat, number)
    deadline = _rx_deadline(chat, reply, (reply or {}).get("priority"), number)
    fresh = await _fresh_agenda(city, message, chat)
    anchor = next((row for row in reversed(fresh) if row.sender == LEDGER and first_word(row.text) == "agenda"), None)
    now = _when(fields_of(anchor.text).get("agenda_now", "")) if anchor is not None else None
    return _expired_prescription(fresh, number) or (now is not None and deadline is not None and now > deadline)


def _clock_jumped(chat: list[Message], agent: str, offer_id: str) -> bool:
    """BK-59: our clock put the refused slot inside the prescription window, the citizen says it is
    past the deadline. So the agenda ran ahead of our reading and the window is really over."""
    offer = _our_offer(chat, agent, offer_id) if offer_id else {}
    at = _when(offer.get("agenda_date") or offer.get("at") or "")
    number = _number(chat)
    reply = _prescription_reply(chat, number)
    priority = (reply or {}).get("priority") or offer.get("priority")
    deadline = _rx_deadline(chat, reply, priority, number)
    return at is not None and deadline is not None and at <= deadline


def _cancel_reason(chat: list[Message], message: Message, reason: str) -> bool:
    """True when the citizen cancelled an offer with ``reason`` after our latest agenda reading."""
    rows = [*chat, message] if all(row.msg_id != message.msg_id for row in chat) else chat
    last_agenda = max((i for i, row in enumerate(rows) if row.sender == LEDGER and first_word(row.text) == "agenda"), default=-1)
    return any(
        row.sender.startswith("citizen:") and _citizen_cancels(row.text) and fields_of(row.text).get("reason") == reason
        for row in rows[last_agenda + 1:]
    )


async def _fresh_agenda(city: City, message: Message, chat: list[Message]) -> list[Message]:
    """BK-59 (0308): the citizen says a slot is in the past, so our agenda clock is behind (the
    agenda jumps at a level change). Read the agenda again before the next offers."""
    before = {row.msg_id for row in chat if row.sender == LEDGER and first_word(row.text) == "agenda"}
    await _ledger_ask(city, message, "agenda")
    return await _until(city, message.need_id, chat, lambda rows: any(
        row.sender == LEDGER and first_word(row.text) == "agenda" and row.msg_id not in before for row in rows))


async def _cancel_next(
    city: City, message: Message, chat: list[Message], need_key: str, citizen: str, offer_id: str,
    fixed: str | None,
) -> bool:
    """The next step after a citizen cancel, inside its gate. True: done (no new search)."""

    agent = city.agent_id
    sent = _sent(need_key)
    unseen = _slot_ids(sent.offers) - _offered(chat, agent) - set(sent.partner_offers)
    if (
        unseen
        or _open_offers(chat, agent, citizen)
        or _we(chat, agent, "", to=citizen, word="booking.receipt")
        or _we(chat, agent, "waiting_list=true", to=citizen, word="offer")
    ):
        _trace("stop", message, why="cancel_ack_only")
        return True
    number = _number(chat)
    rx = _prescription_reply(chat, number) or _our_offer(chat, agent, offer_id)
    procedure, priority = fixed or rx.get("procedure"), rx.get("priority")
    batches = [row for row in chat if row.sender == agent and row.recipient == citizen
               and first_word(row.text) == "offer" and "slot_id=" in row.text]
    last_cross = bool(batches) and "cross_asst=true" in batches[-1].text.split()
    if last_cross:
        if not await _partner_round(city, message, chat, need_key, citizen, priority):
            await _relaxed(city, message, chat, need_key, citizen, procedure, number, priority)
        return True
    local = sum(1 for row in batches if "cross_asst=true" not in row.text.split())
    if local >= 2:
        # BK-29 (journey 129): two local batches refused end the ping-pong with the waiting list.
        sent.replacement_page = None
        await _relaxed(city, message, chat, need_key, citizen, procedure, number, priority)
        return True
    return False


_PREP = {
    "VIS-CARD": ("eventuali ECG e referti cardiologici precedenti, l'elenco dei farmaci che prende",
                 "any previous ECG and heart reports, the list of medicines you take"),
    "VIS-FIS": ("eventuali radiografie o risonanze precedenti e abiti comodi per muoversi",
                "any previous X-rays or MRI scans and comfortable clothes to move in"),
}


def _prep_line(procedure: str, en: bool, *, route_given: bool = False) -> str:
    """P-02: what to bring and when to arrive, before the citizen asks."""

    it_extra, en_extra = _PREP.get(procedure, ("eventuali referti precedenti", "any previous reports"))
    if en:
        return ("To be ready for the visit: arrive 15 minutes early and bring your health card, the "
                f"prescription number, {en_extra}."
                + ("" if route_given else " I will tell you how to get there right away."))
    return ("Per arrivare pronto alla visita: venga 15 minuti prima e porti la tessera sanitaria, il "
            f"numero della ricetta, {it_extra}." + ("" if route_given else " Subito dopo le dico come arrivare."))


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

    zone, door = await asyncio.gather(_zone_point(city, chat), _door(city, facility))  # OPS-11
    if not door:
        return ""
    km = _km(zone, door[:2]) if zone else None
    line = _route_line(_lang(chat) != "it", km, door, {}, zone, ours=_ours(facility), exact=False)
    return (line + " ") if line else ""
