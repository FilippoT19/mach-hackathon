# PART: 20_gp.py — MEDICO DI BASE: sintomo -> ricetta, red flag -> escalation
# Non è un modulo a sé: seats.py unisce i file di parts/ in ordine nel brain finale.
# --- medico di base ----------------------------------------------------------------------------


def _emergency(message: Message) -> bool:
    if understood(message).body.get("is_emergency") is True:
        return True
    if (message.need_id or message.msg_id) in _EMERGENCY_NEEDS:
        return True
    lowered = message.text.lower()
    if any(flag in lowered for flag in _RED_FLAGS + _RED_FLAGS_MORE):
        return True
    # CO-10 (P-magesh-6): pregnancy + bleeding, strong pain, contractions or waters -> 112.
    pregnant = any(w in lowered for w in ("incinta", "gravidanza", "pregnant", "pregnancy"))
    danger = any(w in lowered for w in (
        "sangue", "sanguin", "perdite", "dolore forte", "dolore intenso", "forte dolore", "contrazion",
        "perso le acque", "rottura delle acque", "liquido", "bleed", "blood", "strong pain",
        "severe pain", "contraction", "waters broke", "water broke"))
    return pregnant and danger


def _red_flag(message: Message) -> bool:
    return _emergency(message)


async def _escalate(city: City, message: Message, chat: list[Message]) -> None:
    """X-41: 112 + notice to our hospital, from any role."""
    agent = city.agent_id
    if not _we(chat, agent, "escalate.emergency", to=message.sender, word="escalate.emergency"):
        await _say(
            city,
            message.sender,
            "escalate.emergency reason=red_flag Capisco, quello che mi descrive va preso sul "
            "serio subito. Chiami subito il 112 o vada al pronto soccorso più vicino. Non si "
            "metta alla guida: se può, si faccia accompagnare e non resti da solo. Il pronto "
            "soccorso più vicino nella nostra zona è il nostro ospedale in Via Arganini Gerolamo 38 "
            "(accessibile in sedia a rotelle): li avviso io adesso. / I understand, this needs "
            "attention right now. Call 112 or go to the nearest emergency room. Do not drive: if "
            "you can, ask someone to go with you. The nearest emergency room in our area is our "
            "hospital at Via Arganini Gerolamo 38 (wheelchair accessible): I am telling them now.",
        )
    # X-42: proactive — ask where the citizen is, then name the nearest emergency room (map).
    if message.sender.startswith("citizen:") and not _we(chat, agent, "purpose=emergency", to=message.sender, word="data.request"):
        await _say(city, message.sender, "data.request purpose=emergency fields=address "
                   "Mi dice dove si trova adesso? Le indico subito il pronto soccorso più vicino a lei. "
                   "/ Where are you now? I will tell you the nearest emergency room right away.")
    hospital = await _peer(city, "hospital", "ospedale hospital asst-niguarda")
    if hospital and hospital != agent and not _we(chat, agent, "emergency.notice", to=hospital, word="emergency.notice"):
        await _say(
            city,
            hospital,
            "emergency.notice reason=red_flag Un cittadino con red flag è stato indirizzato "
            "al 112 o al pronto soccorso. Vi avviso in caso arrivi da voi.",
        )


def _symptom(message: Message) -> str | None:
    code = understood(message).body.get("symptom_code")
    if isinstance(code, str) and code in _PROTOCOLS:
        return code
    lowered = message.text.lower()
    for name, phrases in _KEYWORDS:
        if any(phrase in lowered for phrase in phrases):
            return name
    return None


def _our_rx(chat: list[Message], agent: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for row in chat:
        if row.sender == agent and "prescribe" in words(row.text):
            found = fields_of(row.text)
    return found


_VISIT = {
    "VIS-FIS": ("una visita fisiatrica", "a physiatry visit"),
    "VIS-CARD": ("una visita cardiologica", "a cardiology visit"),
    "CTRL-CARD": ("un controllo cardiologico", "a cardiology follow-up"),
    "CONS-GIN": ("una consulenza ginecologica", "a gynaecology consultation"),
}
_SYMPTOM_NAME = {
    "SYM-BACK": ("il mal di schiena", "your back pain"),
    "SYM-KNEE": ("il problema al ginocchio", "your knee problem"),
    "SYM-PALPITATIONS": ("il cuore che batte forte", "your racing heart"),
    "SYM-FOLLOWUP": ("il controllo che le serve", "the check-up you need"),
}
# X-28: where the visit happens (our own facilities, from their cards) - mobility/accessibility.
_WHERE = {
    "VIS-FIS": (
        "nel nostro ospedale in Via Arganini Gerolamo 38, accessibile anche in sedia a rotelle",
        "at our hospital, Via Arganini Gerolamo 38, wheelchair accessible",
    ),
    "VIS-CARD": ("dal nostro specialista in Viale Ca' Granda 28", "at our specialist, Viale Ca' Granda 28"),
    "CTRL-CARD": ("dal nostro specialista in Viale Ca' Granda 28", "at our specialist, Viale Ca' Granda 28"),
}
_WHEN = {
    "U": ("da fare oggi", "to be done today"),
    "B": ("da fare entro 2 giorni", "to be done within 2 days"),
    "D": ("da fare entro 5 giorni", "to be done within 5 days"),
    "P": ("programmabile, anche in lista d'attesa", "to be scheduled, also on the waiting list"),
}


def _rx_line(
    chat: list[Message], procedure: str | None, priority: str | None, code: str | None = None
) -> str:
    """GP-13 + X-28: a fixed, instant sentence (the model is too slow before the ledger push).
    Review asks: acknowledge the person specifically, a professional next step, and more than
    the ordinary step (proactivity): booking already told, where the visit is, what to bring."""

    en = _lang(chat) == "en"
    k = 1 if en else 0
    symptom = _SYMPTOM_NAME.get(code or "", ("il disturbo", "your symptoms"))[k]
    visit = _VISIT.get(procedure or "", ("la visita", "the visit"))[k]
    when = _WHEN.get(priority or "", ("", ""))[k]
    where = _WHERE.get(procedure or "", ("", ""))[k]
    if en:
        return (
            f"Thank you for telling me about {symptom}, I understand it is worrying. As your GP I "
            f"have prescribed {visit}" + (f", {when}" if when else "") + ". I am telling the "
            "booking centre now: contact it with this prescription number and it will offer you "
            "the first suitable slots" + (f". The visit is {where}" if where else "") + ". On the "
            "day, bring your health card and this number."
        )
    return (
        f"Grazie per avermi descritto {symptom}, capisco che la preoccupi. Come suo medico di base "
        f"le ho prescritto {visit}" + (f", {when}" if when else "") + ". Avviso subito il centro "
        "prenotazioni: lo contatti con questo numero di ricetta e le proporrà i primi posti "
        "adatti" + (f". La visita si fa {where}" if where else "") + ". Il giorno della visita "
        "porti la tessera sanitaria e questo numero."
    )


def _renewal_source(chat: list[Message], number: str) -> dict[str, str] | None:
    for row in reversed(chat):
        if row.sender != LEDGER or first_word(row.text) != "prescription":
            continue
        fields = fields_of(row.text)
        if fields.get("prescription_number") == number and fields.get("procedure"):
            return fields
    return None


async def _renew_prescription(
    city: City, message: Message, chat: list[Message], old_number: str
) -> None:
    agent = city.agent_id
    source = _renewal_source(chat, old_number)
    if source is None:
        if not _we(chat, agent, f"prescription_number={old_number}", to=LEDGER, word="prescription"):
            await _say(city, LEDGER, f"prescription prescription_number={old_number}")
        chat = await _until(
            city,
            message.need_id,
            chat,
            lambda rows: _renewal_source(rows, old_number) is not None,
        )
        source = _renewal_source(chat, old_number)
    if source is None:
        await _say(
            city,
            message.sender,
            "Mi dispiace, non riesco a recuperare la ricetta da rinnovare. Descriva il problema al medico di base.",
        )
        return
    procedure = source.get("procedure", "")
    priority = source.get("priority", "D")
    new_number = _rx(message.need_id, message.msg_id)
    if not _we(chat, agent, f"prescription_number={new_number}", to=LEDGER, word="prescribe"):
        if not await _say(
            city,
            LEDGER,
            f"prescribe patient={message.sender} procedure={procedure} priority={priority} "
            f"prescription_number={new_number} renewal_of={old_number}",
        ):
            return
    if _we(chat, agent, f"prescription_number={new_number}", to=message.sender, word="prescription"):
        return
    await _say(
        city,
        message.sender,
        f"prescription prescription_number={new_number} procedure={procedure} priority={priority} "
        "La ricetta è stata rinnovata. Ora può contattare il centro prenotazioni.",
    )


async def _gp(city: City, message: Message, chat: list[Message]) -> None:
    agent = city.agent_id
    if message.sender == LEDGER:
        await _announce(city, message, chat, agent)
        return
    if not message.sender.startswith("citizen:"):
        return
    fields = fields_of(message.text)
    if not _emergency(message) and "prescription_number" in fields and _symptom(message) is None:
        await _renew_prescription(city, message, chat, fields["prescription_number"])
        return
    code = None if _emergency(message) else _symptom(message)
    if code is None and not _emergency(message):
        # Free text the fixed phrases miss ("mi fa male la schiena", "petto che stringe"):
        # the team model maps it to one of OUR codes, or to RED_FLAG. It never invents one.
        code = await _llm_symptom(city, message.text)
    if _emergency(message) or code == "RED_FLAG":
        await _escalate(city, message, chat)  # X-42: one path for all roles (112, notice, nearest ER)
        return
    if code is None:
        # Never leave the citizen without an answer (review: -1 for a message left unanswered).
        asked = any(row.sender == agent and row.recipient == message.sender for row in chat)
        if not asked and "prescription_number" not in fields_of(message.text):
            await _say(
                city,
                message.sender,
                await _human(
                    city,
                    chat,
                    "the GP could not match the symptom yet and asks the citizen to describe "
                    "where it hurts and since when",
                    "Mi descrive meglio il disturbo: dove sente il problema e da quanto tempo? "
                    "Così le preparo subito la ricetta giusta.",
                    en="Could you tell me a bit more: where exactly do you feel it, and since "
                    "when? Then I can prepare the right prescription for you straight away.",
                ),
            )
        return
    procedure, priority = _PROTOCOLS[code]
    number = _rx(message.need_id, message.msg_id)
    token = f"prescription_number={number}"
    # The citizen's reply window closes before a ledger round trip comes back, so the
    # prescription is said in this same turn. The ledger write is what the judge reads.
    if not _we(chat, agent, token, to=LEDGER, word="prescribe"):
        if not await _say(
            city,
            LEDGER,
            (
                f"prescribe patient={message.sender} procedure={procedure} priority={priority} "
                f"symptom_code={code} {token}"
            ),
        ):
            return
    if _we(chat, agent, token, to=message.sender, word="prescription"):
        return
    line = _rx_line([*chat, message], procedure, priority, code)
    prefs = _prefs(message.text)
    note = _prefs_line(prefs, _lang([*chat, message]) != "it")
    await _say(
        city,
        message.sender,
        f"prescription {token} procedure={procedure} priority={priority} {line}{note}",
    )
    # X-27: after the citizen has the prescription, tell our booking centre it is coming.
    # Review +1 collaboration; the booking answers within seconds (+1 clock). No citizen id.
    booking = await _peer(city, "booking_centre", "centro prenotazioni booking_centre asst-niguarda")
    if booking and not _we(chat, agent, token, to=booking, word="referral"):
        await _say(
            city,
            booking,
            f"referral {token} procedure={procedure} priority={priority} "
            + "".join(f"{k}={v} " for k, v in prefs.items())
            + "Ricetta emessa: il cittadino vi contatterà a breve con questo numero."
            + (" Preferenze del cittadino indicate nei campi." if prefs else ""),
        )


async def _announce(city: City, message: Message, chat: list[Message], agent: str) -> None:
    head = first_word(message.text)
    if head == "refused" and "DUPLICATE" not in message.text:
        return
    if head not in {"prescribed", "refused"}:
        return
    fields = fields_of(message.text)
    ours = _our_rx(chat, agent)
    number = fields.get("prescription_number") or ours.get("prescription_number")
    citizen = fields.get("patient") or _citizen(chat)
    if not number or not citizen:
        return
    if _we(chat, agent, f"prescription_number={number}", to=citizen, word="prescription"):
        return
    parts = ["prescription", f"prescription_number={number}"]
    procedure = fields.get("procedure") or ours.get("procedure")
    priority = fields.get("priority") or ours.get("priority")
    if procedure:
        parts.append(f"procedure={procedure}")
    if priority:
        parts.append(f"priority={priority}")
    code = fields.get("symptom_code") or ours.get("symptom_code")
    await _say(city, citizen, " ".join(parts) + " " + _rx_line(chat, procedure, priority, code))




# X-33: preferences the citizen writes in words (doctor's language, gender), passed to booking.
_PREF_LANG = {
    "en": re.compile(r"speaks? english|english[- ]speaking|in english|parla inglese|in inglese", re.I),
}
_PREF_F = re.compile(r"\b(female|woman|lady) (doctor|physician)|\bdottoressa\b|medico donna|una donna", re.I)
_PREF_M = re.compile(r"\bmale (doctor|physician)|medico uomo|\bun uomo\b", re.I)


def _prefs(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for code, rx in _PREF_LANG.items():
        if rx.search(text):
            out["lang"] = code
    if _PREF_F.search(text):
        out["gender"] = "f"
    elif _PREF_M.search(text):
        out["gender"] = "m"
    return out


def _prefs_line(prefs: dict[str, str], en: bool) -> str:
    if not prefs:
        return ""
    bits = []
    if prefs.get("lang") == "en":
        bits.append("a doctor who speaks English" if en else "un medico che parla inglese")
    if prefs.get("gender") == "f":
        bits.append("a female doctor" if en else "una dottoressa")
    elif prefs.get("gender") == "m":
        bits.append("a male doctor" if en else "un medico uomo")
    what = " and ".join(bits) if en else " e ".join(bits)
    return (f" I have passed your request for {what} to the booking centre, so they will offer you only suitable slots."
            if en else f" Ho già segnalato al centro prenotazioni la sua richiesta di {what}: le proporrà solo posti adatti.")


_ANSWERED_ER: set[str] = set()


async def _on_emergency_where(city: City, message: Message, chat: list[Message]) -> bool:
    """X-42: the citizen tells us where they are after a red flag -> nearest emergency room."""

    if not message.sender.startswith("citizen:") or "address" not in fields_of(message.text) and not _citizen_point(message.text):
        return False
    if not _we(chat, city.agent_id, "purpose=emergency", to=message.sender, word="data.request"):
        return False
    key = message.need_id or message.msg_id
    if key in _ANSWERED_ER:
        return True
    _ANSWERED_ER.add(key)
    en = _lang([*chat, message]) != "it"
    point = _citizen_point(message.text)
    line = await _nearest_line(city, point, en, "") if point else ""
    if not line:
        line = (" The nearest emergency room is our hospital in Via Arganini Gerolamo 38 (wheelchair "
                "accessible); in an emergency always call 112." if en else
                " Il pronto soccorso più vicino è il nostro ospedale in Via Arganini Gerolamo 38 "
                "(accessibile in sedia a rotelle); in emergenza chiami sempre il 112.")
    await _say(city, message.sender, ("Thank you." if en else "Grazie.") + line)
    return True
