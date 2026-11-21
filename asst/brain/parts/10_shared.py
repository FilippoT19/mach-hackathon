# PART: 10_shared.py — Funzioni comuni: lettura token, storia del caso, filtro degli slot (fitting)
# Non è un modulo a sé: seats.py unisce i file di parts/ in ordine nel brain finale.
# --- shared ------------------------------------------------------------------------------------


def _card_role(text: str) -> str:
    role = ""
    types: list[str] = []
    in_types = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line[0] in " \t":
            if in_types:
                item = line.strip().removeprefix("-").strip().strip("'\"")
                if item:
                    types.append(item)
            continue
        in_types = False
        key, _, value = line.partition(":")
        value = value.strip().strip("'\"")
        if key.strip() == "role":
            role = value
        elif (
            key.strip() in {"capabilities", "service_types"}
            and value.startswith("[")
            and value.endswith("]")
        ):
            types = [part.strip().strip("'\"") for part in value[1:-1].split(",") if part.strip()]
        elif key.strip() in {"capabilities", "service_types"}:
            in_types = True
    if role in ROLES:
        return role
    for family in ("specialist_care", "family_counseling", "hospital", "booking_centre", "gp"):
        if any(item == family or item.startswith(family + ".") for item in types):
            return family
    return "hospital" if role == "facility" else ""


def words(text: str) -> set[str]:
    return {token.strip(".,;:!?()\"'").lower() for token in text.split() if token.strip()}


def first_word(text: str) -> str:
    parts = text.split()
    return parts[0].strip(".,;:!?()\"'").lower() if parts else ""


def fields_of(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for token in text.replace(",", " ").split():
        key, eq, value = token.partition("=")
        if not eq or not key or not value:
            continue
        value = value.strip(".,;:!?")
        if key not in found and value:
            found[key] = value
    return found


# X-27: our five agents. We write only to a peer that city.find returns AND that is one of ours,
# so a message never goes to another team's agent.
_OUR_AGENTS = {
    "booking_centre": "agent:fn64xfq2jft4",
    "gp": "agent:fddgaqmp6kb0",
    "hospital": "agent:jdj692g4145e",
    "specialist": "agent:jmjfst55vgjz",
    "family_counseling": "agent:mm18nddkfc5w",
}
_PEERS: dict[str, str] = {}
# X-13: impostors. Other teams' agent ids, copied from the shared list in the mods' group. While
# it is empty every partner is accepted (cross-ASST keeps working); once filled, only these.
_TRUSTED_PARTNERS: set[str] = set()
# Ids posted by other ASSTs in the mods' group. Copied into _TRUSTED_PARTNERS when the impostors
# arrive (switching it on now would reject the teams that have not posted yet).
_KNOWN_PARTNERS = {
    # Lorenteggio (Municipio 9), team RASPBERRY
    "agent:qtjne8symjas", "agent:w2qsptc9qqhg", "agent:tmt0bcv0st1f", "agent:n9bf9y6670hp", "agent:mcppmrbjvxag",
    # Nord (Municipio 2), team agentic-paguri — h3 ur
    "agent:psxp8bh1feaa", "agent:wwxaphfb5pfh", "agent:gpr1zqe343gb", "agent:zand0f57ec1j", "agent:ccjzqm7yekwx",
    # Corvetto (Municipio 3), team scuola-di-atene — h3 fr
    "agent:yzcs4p44ep39", "agent:hkrtm1gzjb24", "agent:x0vr9rbwpesr", "agent:h8425ac7btd8", "agent:p0n57t7vtpq0",
    # Lambrate (Municipio 3), team ltf-jecatt — h3 ja
    "agent:gdrf9b9kxxss", "agent:c2ewegr2ea3v", "agent:nanpr5mgm2py", "agent:pky3vqyqbepa", "agent:atp772whjkgd",
    # Giambellino (RED-AGENT, MACH-1) — h3 ka
    "agent:cdc7x6m21nj6", "agent:c32jyk0cyan7", "agent:h6r1v45esk77", "agent:hnpe58epeyh1", "agent:bzs050xacs1m",
    # Greco (tartufi-pazzi) — h3 si
    "agent:h3n6kfd18r3g", "agent:bmrcsmqq6at2", "agent:xtj1dk9x3qej", "agent:q18es2d82f8r", "agent:pxvd2kk2yx5j",
    # Bicocca (p4radigm) — h3 ti
    "agent:ez8cb7j167p2", "agent:rng5wcrzvhsj", "agent:bb01ggxymm05", "agent:sh35cbsy287d", "agent:nkh372rd16yq",
    # Bovisa (prompt-soccorso)
    "agent:vgtmj5nqfkxj", "agent:h82xpx3rkn9e", "agent:gxq3vzgt3h5t", "agent:tty8erdj6t41", "agent:txar5994gbkj",
    # Isola (Diuo), only two ids known — h3 tl
    "agent:etpwrfmfa8hm", "agent:mkfzagfe8jtt",
}
# Rare language of each ASST's h3 physiatrist (shared table in the mods' group).
_RARE_LANG_BY_ASST = {"giambellino": "ka", "toros": "ro", "precotto": "ro", "nord": "ur",
                      "corvetto": "fr", "brera": "fa", "niguarda": "vi",
                      "isola": "tl", "ortica": "wo", "greco": "si", "bicocca": "ti", "lambrate": "ja",
                      "gorla": "sq", "forlanini": "de"}


def _ours(sender: str) -> bool:
    return sender in _OUR_AGENTS.values()


def _trusted(sender: str) -> bool:
    """X-13: our agents always; another team's agent only if it is on the shared list."""

    return _ours(sender) or not _TRUSTED_PARTNERS or sender in _TRUSTED_PARTNERS
# X-29: where our facilities are (their own card addresses) - mobility and accessibility.
_FACILITY_WHERE = {
    "agent:jdj692g4145e": "al nostro ospedale in Via Arganini Gerolamo 38 (accessibile in sedia a rotelle)",
    "agent:jmjfst55vgjz": "dal nostro specialista in Viale Ca' Granda 28",
    "agent:mm18nddkfc5w": "al nostro consultorio in Via Giolli Raffaello 23",
}
_FACILITY_WHERE_EN = {
    "agent:jdj692g4145e": "to our hospital at Via Arganini Gerolamo 38 (wheelchair accessible)",
    "agent:jmjfst55vgjz": "to our specialist at Viale Ca' Granda 28",
    "agent:mm18nddkfc5w": "to our family counselling centre at Via Giolli Raffaello 23",
}


async def _peer(city: City, family: str, query: str) -> str | None:
    """Our agent of that family, as the Index returns it. None if the Index does not show it."""

    if family in _PEERS:
        return _PEERS[family]
    wanted = _OUR_AGENTS.get(family)
    try:
        peers = await asyncio.wait_for(city.find(query), timeout=5.0)
    except Exception:  # Index down or slow: no collaboration message, the journey goes on
        return None
    for peer in peers:
        if peer.agent_id == wanted:
            _PEERS[family] = peer.agent_id
            return peer.agent_id
    return None


def _line_fields(text: str, token: str) -> dict[str, str]:
    """Fields of the one line that carries ``token``. BK-14: one message holds several offers."""

    for line in text.splitlines():
        if token in line.split():
            return fields_of(line)
    return fields_of(text)


def _offer_rows(text: str) -> list[dict[str, str]]:
    """Every offer line of one message (``offer_id=`` on each line)."""

    return [fields_of(line) for line in text.splitlines() if "offer_id=" in line]


def _when(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _citizen(chat: list[Message]) -> str | None:
    for row in chat:
        if row.sender.startswith("citizen:"):
            return row.sender
    for row in chat:
        fields = fields_of(row.text)
        for key in ("patient", "citizen"):
            party = fields.get(key, "")
            if party.startswith("citizen:"):
                return party
    return None


def _we(chat: list[Message], agent: str, token: str, *, to: str, word: str) -> bool:
    for row in chat:
        if row.sender != agent or row.recipient != to:
            continue
        if token in row.text.split() and word in words(row.text):
            return True
    return False


def _exact(chat: list[Message], agent: str, text: str) -> bool:
    return any(row.sender == agent and row.text.strip() == text for row in chat)


# BK-33: who this turn has written to, so the booking desk can tell a silent turn (None = not tracked).
_SAID: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar("_SAID", default=None)


async def _say(city: City, to: str, text: str) -> bool:
    try:
        await city.say(to, text)
    except CapError:
        return False
    said = _SAID.get()
    if said is not None:
        said.add(to)
    return True


def _latest(chat: list[Message], head: str, token: str) -> Message | None:
    found: Message | None = None
    for row in chat:
        if row.sender == LEDGER and first_word(row.text) == head and token in row.text.split():
            found = row
    return found


async def _until(
    city: City,
    need_id: str | None,
    chat: list[Message],
    ready: Callable[[list[Message]], bool],
) -> list[Message]:
    """Re-read the case until ``ready`` or the short wait ends. The push may never arrive."""

    fresh = chat
    for attempt in range(_PULL_TRIES):
        try:
            fresh = await city.history(need_id=need_id)
        except CapError:
            fresh = chat
        fresh = _keep(fresh, chat)
        if ready(fresh):
            return fresh
        if attempt + 1 < _PULL_TRIES:
            await asyncio.sleep(_PULL_PAUSE)
    return fresh


def _keep(fresh: list[Message], chat: list[Message]) -> list[Message]:
    """BK-15: a re-read of the case must not drop rows we already had (the inbound message)."""

    seen = {row.msg_id for row in fresh}
    return list(fresh) + [row for row in chat if row.msg_id not in seen]


async def _await_line(
    city: City,
    need_id: str | None,
    chat: list[Message],
    head: str,
    token: str,
    *,
    op: str,
    refusal_matches: Callable[[Message], bool] | None = None,
) -> tuple[Message, list[Message]] | None:
    """The ledger line for ``token``, or a refusal of ``op`` that was not already in ``chat``."""

    known = {row.msg_id for row in chat}
    fresh = chat
    for attempt in range(_PULL_TRIES):
        try:
            fresh = await city.history(need_id=need_id)
        except CapError:
            fresh = chat
        fresh = _keep(fresh, chat)  # simulator bug 3: keep booking's confirm under BK-15
        hit = _latest(fresh, head, token)
        if hit is not None:
            return hit, fresh
        for row in fresh:
            if row.msg_id in known or row.sender != LEDGER:
                continue
            if first_word(row.text) == "refused" and op in words(row.text) and (
                refusal_matches is None or refusal_matches(row)
            ):
                return row, fresh
        if attempt + 1 < _PULL_TRIES:
            await asyncio.sleep(_PULL_PAUSE)
    return None


def _has_agenda(chat: list[Message]) -> bool:
    agenda = _ledger(chat, "agenda")
    return _when("" if agenda is None else agenda.get("agenda_now", "")) is not None


def _has_procedure(chat: list[Message], number: str | None = None) -> bool:
    reply = _ledger(chat, "prescription")
    if number and reply is not None and reply.get("prescription_number") not in (None, number):
        return False
    return reply is not None and bool(reply.get("procedure"))


def _rx(need_id: str | None, msg_id: str) -> str:
    raw = (need_id or msg_id or "CASE").upper()
    suffix = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in raw).strip("-")
    if len(suffix) < 4:
        suffix = (suffix + "0000")[:4]
    number = "prescription_number-" + suffix[:40]
    return number if _RX.fullmatch(number) else "prescription_number-CASE"


_RARE_LANG = {"h3": _RARE_LANG_BY_ASST["niguarda"]}


def _speaks(doctor_id: str, lang: str) -> bool:
    short = doctor_id.rsplit("-", 1)[-1]
    spec = _DOCTORS.get(short)
    if spec is None:
        return False
    langs = spec[0]
    if lang in langs:
        return True
    return "*" in langs and _RARE_LANG.get(short) == lang


def fitting(
    lines: list[str],
    *,
    now: datetime,
    priority: str | None,
    lang: str,
    gender: str | None = None,
    days: frozenset[str] | None = None,
    facility: str | None = None,
    procedure: str | None = None,
) -> list[dict[str, str]]:
    """Slots a citizen can accept, preferring the citizen's requested agenda days."""

    if priority == "U":
        horizon: datetime | None = now.replace(hour=23, minute=59, second=59, microsecond=0)
    elif priority == "P":
        horizon = None
    else:
        horizon = now + timedelta(days=_DEADLINE_DAYS.get(priority or "", 14))
    earliest = now + _LEAD
    chosen: list[tuple[int, datetime, dict[str, str]]] = []
    for line in lines:
        slot = fields_of(line)
        slot_id = slot.get("slot_id")
        doctor = slot.get("doctor_id")
        at = _when(slot.get("at", ""))
        if not slot_id or not doctor or at is None:
            continue
        if procedure and slot.get("procedure") not in (None, procedure):
            continue
        if facility and slot.get("facility") != facility:
            continue
        free = slot.get("free")
        if free is not None and free.isdigit() and int(free) <= 0:
            continue
        reserve = slot.get("urgent_reserve", "").lower() == "true"
        if reserve and priority != "U":
            continue
        if not earliest < at or (horizon is not None and at >= horizon):
            continue
        if not _speaks(doctor, lang):
            continue
        spec = _DOCTORS.get(doctor.rsplit("-", 1)[-1])
        if spec is None:
            continue
        day = slot.get("day", "")
        if day and day not in spec[2]:
            continue
        # P-francesco-31: the doctor's gender is a preference like the days (S_pref), not a wall.
        # Discarding the other gender left "no local slot" while S still had some (no_booking -1).
        preferred = (0 if days and day in days else 1) + (1 if gender and spec[1] != gender else 0)
        chosen.append((preferred, at, slot))
    chosen.sort(key=lambda item: (item[0], item[1], item[2].get("slot_id", "")))
    return [slot for _, _, slot in chosen]


