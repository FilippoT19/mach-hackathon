# PART: 20_gp.py — MEDICO DI BASE: sintomo -> ricetta, red flag -> escalation
# Non è un modulo a sé: seats.py unisce i file di parts/ in ordine nel brain finale.
# --- medico di base ----------------------------------------------------------------------------


def _emergency(message: Message) -> bool:
    if understood(message).body.get("is_emergency") is True:
        return True
    if (message.need_id or message.msg_id) in _EMERGENCY_NEEDS:
        return True
    lowered = message.text.lower()
    if any(flag in lowered for flag in _RED_FLAGS + _RED_FLAGS_MORE + (
        "non sento più le gambe", "non riesco a muovere le gambe",
        "can't feel my legs", "cannot feel my legs", "can't move my legs",
    )):
        return True
    # P-magesh-11: red flags in other words never depend on the model (slow or down).
    if _RF_CHEST.search(lowered) or _RF_LEGS.search(lowered):
        return True
    # CO-10 (P-magesh-6): pregnancy + bleeding, strong pain, contractions or waters -> 112.
    pregnant = any(w in lowered for w in ("incinta", "gravidanza", "pregnant", "pregnancy"))
    # P-magesh-16: danger is a phrase, not a lone word ("esami del sangue" is a normal visit).
    danger = _RF_PREGNANT.search(lowered) is not None
    return pregnant and danger


_RF_PREGNANT = re.compile(
    r"sanguin\w*|perdit\w* di sangue|perd\w* (?:\w+ )?sangue|sangue (?:dalla vagina|vaginale)"
    r"|contrazion\w*|perso le acque|rott\w* (?:delle |le )?acque|acque rotte"
    r"|perd\w* (?:\w+ )?liquido|perdita di liquido"
    r"|(?:dolor\w*|male)[^.!?]{0,25}\b(?:pancia|addome|addominal\w*|ventre|basso ventre)"
    r"|(?:pancia|addome|ventre)[^.!?]{0,20}\b(?:dolor\w*|male)"
    r"|\bbleed\w*|losing blood|\bcontraction\w*|water(?:s)? (?:broke|break\w*)"
    r"|(?:pain|cramp\w*)[^.!?]{0,20}\b(?:belly|abdom\w*|stomach|tummy)"
    r"|(?:belly|abdom\w*|stomach|tummy)[^.!?]{0,20}\b(?:pain|hurt\w*|cramp\w*)")
_RF_CHEST = re.compile(
    r"(?:\b(?:dolor\w*|male|fa(?:nno)? male|stretta|oppression\w*|peso|pressione|bruciore)\b[^.!?]{0,30}\b(?:petto|torac\w*)\b)"
    r"|(?:\b(?:petto|torac\w*)\b[^.!?]{0,20}\b(?:dolor\w*|male|stretta|oppression\w*|peso)\b)"
    r"|(?:\bchest\b[^.!?]{0,25}\b(?:pain\w*|tight\w*|pressure|hurt\w*|ache\w*)\b)"
    r"|(?:\b(?:pain|tightness|pressure)\b[^.!?]{0,15}\bchest\b)"
    r"|(?:\bmy chest hurts\b)")
_RF_LEGS = re.compile(
    r"(?:\b(?:non sento|non riesco a muovere|perso (?:la )?forza|perdita di forza|senza forza)\b[^.!?]{0,25}\bgamb[ae]\b)"
    r"|(?:\bgamb[ae]\b[^.!?]{0,20}\b(?:non la sento|non le sento|senza forza|paralizzat\w*|non si muov\w*)\b)"
    r"|(?:\b(?:can'?t|cannot|can not) (?:feel|move)\b[^.!?]{0,15}\blegs?\b)"
    r"|(?:\blost (?:the )?strength\b[^.!?]{0,15}\blegs?\b)"
    r"|(?:\blegs?\b[^.!?]{0,15}\b(?:numb|gave way|went weak)\b)")


async def _gp_again(city: City, message: Message, chat: list[Message]) -> None:
    """P-magesh-10: a later citizen message the table still does not match is never left
    without an answer (no_reply). After a prescription: repeat it with the next step. Before:
    one closed question with the protocol choices, then a short safety line."""
    agent, citizen = city.agent_id, message.sender
    en = _lang([*chat, message]) != "it"
    rx = [row for row in chat if row.sender == agent and row.recipient == citizen
          and first_word(row.text) == "prescription" and "prescription_number=" in row.text]
    if rx:
        f = fields_of(rx[-1].text)
        tokens = " ".join(f"{k}={f[k]}" for k in ("prescription_number", "procedure", "priority") if f.get(k))
        await _say(city, citizen, f"prescription {tokens} " + (
            "Your prescription is ready: contact the booking centre with this number to book the visit."
            if en else
            "La sua ricetta è pronta: contatti il centro prenotazioni con questo numero per prenotare la visita."))
        return
    if not _we(chat, agent, "", to=citizen, word="gp.choices"):
        await _say(city, citizen, "gp.choices " + (
            "So I can prepare the right prescription: is it your back, your knee, your heart "
            "racing, or a routine heart check?" if en else
            "Per prepararle la ricetta giusta mi aiuta a capire: si tratta della schiena, del "
            "ginocchio, del cuore che batte forte, o di un controllo del cuore?"))
        return
    await _say(city, citizen, "gp.note " + (
        "I am sorry, I still cannot match your problem. If it gets worse, or you feel chest "
        "pain, call 112 straight away." if en else
        "Mi dispiace, non riesco ancora a capire il disturbo. Se peggiora o compare dolore al "
        "petto chiami subito il 112."))


def _red_flag(message: Message) -> bool:
    return _emergency(message)


async def _escalate(city: City, message: Message, chat: list[Message]) -> None:
    """X-41: 112 + notice to our hospital, from any role.

    X-55: the notice to our hospital and the nearest-ER lookup run together, before the 112
    message (which therefore does not wait longer than before); the citizen reads "I have already
    told them" only when the notice really left (the review reads only the citizen chat)."""
    agent = city.agent_id
    en = _lang([*chat, message]) != "it"
    # X-56 (journey 0000540007): the Index search (up to 5 s) timed out under load, so no notice
    # left and the 112 waited for nothing ("li avviso io adesso"). Our hospital id is fixed.
    hospital = _OUR_AGENTS["hospital"]

    async def _notice() -> bool:
        if not hospital or hospital == agent:
            return False
        if _we(chat, agent, "emergency.notice", to=hospital, word="emergency.notice"):
            return True
        return await _say(
            city,
            hospital,
            "emergency.notice reason=red_flag Un cittadino con red flag è stato indirizzato "
            "al 112 o al pronto soccorso. Vi avviso in caso arrivi da voi.",
        )

    async def _near() -> str:
        # X-45: nearest hospital to the citizen's zone (Index doors), inside the 112 message.
        zone = await _zone_point(city, [*chat, message])
        return await _nearest_line(city, zone, en, "") if zone else ""

    near = ""
    early = (message.need_id or message.msg_id) in _EARLY_112  # GP-17: the 112 already left
    if not early and not _we(chat, agent, "escalate.emergency", to=message.sender, word="escalate.emergency"):
        noticed, near = await asyncio.gather(_notice(), _near())
        if await _say(city, message.sender, _escalate_text(message, en, told=noticed) + (" " + near.strip() if near else "")):
            key = message.need_id or message.msg_id
            if key in _EARLY_112_FAILED:  # GP-18: the early 112 failed, this one left
                _EARLY_112_FAILED.discard(key)
                _EARLY_112.add(key)
        near = ""
    elif early and message.sender.startswith("citizen:") and not _we(
            chat, agent, "purpose=emergency", to=message.sender, word="data.request"):
        _, near = await asyncio.gather(_notice(), _near())  # GP-17: the rest of the first 112
    else:
        await _notice()
    # X-42: proactive — ask where the citizen is, then name the nearest emergency room (map).
    if message.sender.startswith("citizen:") and not _we(chat, agent, "purpose=emergency", to=message.sender, word="data.request"):
        await _say(city, message.sender, "data.request purpose=emergency fields=address " + (
                   (near.strip() + " ") if near else "") + (
                   "Where are you now? I will tell you the nearest emergency room right away." if en else
                   "Mi dice dove si trova adesso? Le indico subito il pronto soccorso più vicino a lei."))


def _er_kind(message: Message, en: bool) -> str:
    """GP-17: the emergency room that suits the red flag, named for the 112 call."""
    lowered = (message.text or "").lower()
    if any(w in lowered for w in ("incinta", "gravidanza", "pregnant", "pregnancy")):
        return ("Tell 112 you are pregnant: you need an emergency room with obstetrics and "
                "gynaecology." if en else
                "Al 112 dica che è incinta: serve un pronto soccorso con ostetricia e ginecologia.")
    if _RF_CHEST.search(lowered) or "petto" in lowered or "chest" in lowered:
        return ("Tell 112 you have chest pain: you need an emergency room with cardiology." if en else
                "Al 112 dica subito che ha dolore al petto: serve un pronto soccorso con cardiologia.")
    if _RF_LEGS.search(lowered) or "gambe" in lowered or "legs" in lowered:
        return ("Tell 112 you cannot feel or move your legs: you need an emergency room with "
                "neurology (stroke unit)." if en else
                "Al 112 dica che non sente o non muove le gambe: serve un pronto soccorso con "
                "neurologia (stroke unit).")
    return ("Tell 112 exactly what you feel and since when." if en else
            "Al 112 dica esattamente cosa sente e da quando.")


def _escalate_text(message: Message, en: bool, *, told: bool | None) -> str:
    """GP-17: the 112 message, the same with or without the history (``told``: the notice to
    our hospital already left, will leave now, or there is no hospital to notice)."""
    if en:
        about = "" if told is None else (
            " About the emergency room of our hospital (Via Arganini Gerolamo 38, wheelchair "
            "accessible): " + ("I have already told them myself." if told else "I am telling them now."))
        return ("escalate.emergency reason=red_flag I understand, this needs attention right now. "
                "Call 112 or go to the emergency room nearest to you. " + _er_kind(message, en)
                + " Do not drive: if you can, ask someone to go with you." + about)
    about = "" if told is None else (
        " Il pronto soccorso del nostro ospedale (Via Arganini Gerolamo 38, accessibile in sedia a "
        "rotelle): " + ("li ho già avvisati io." if told else "li avviso io adesso."))
    return ("escalate.emergency reason=red_flag Capisco, quello che mi descrive va preso sul serio "
            "subito. Chiami subito il 112 o vada al pronto soccorso più vicino a lei. "
            + _er_kind(message, en) + " Non si metta alla guida: se può, si faccia accompagnare "
            "e non resti da solo." + about)


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

    en = _lang(chat) != "it"
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
    en = _lang([*chat, message]) != "it"
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
            "I could not retrieve the prescription to renew. Please describe your symptoms to your GP."
            if en else
            "Mi dispiace, non riesco a recuperare la ricetta da rinnovare. Descriva il problema al medico di base.",
        )
        return
    procedure = source.get("procedure", "")
    priority = source.get("priority", "D")
    # A predecessor always maps to the same renewal, even on replay with incomplete history.
    base = _rx(message.need_id, old_number)[len("prescription_number-"):]
    suffix = sha256(old_number.encode()).hexdigest()[:16].upper()
    new_number = f"prescription_number-{base[:22]}-R{suffix}"
    if new_number == old_number:
        new_number = f"prescription_number-{base[:22]}-S{suffix}"
    if not _we(chat, agent, f"prescription_number={new_number}", to=LEDGER, word="prescribe"):
        if not await _say(
            city,
            LEDGER,
            f"prescribe patient={message.sender} procedure={procedure} priority={priority} "
            f"prescription_number={new_number} renewal_of={old_number}",
        ):
            await _say(city, message.sender, "Please try requesting the renewal again." if en else
                       "Può riprovare a chiedere il rinnovo della ricetta?")
            return
    await _say(
        city,
        message.sender,
        f"prescription prescription_number={new_number} procedure={procedure} priority={priority} "
        + ("Your prescription has been renewed. You can now contact the booking centre." if en else
           "La ricetta è stata rinnovata. Ora può contattare il centro prenotazioni."),
    )


async def _gp(city: City, message: Message, chat: list[Message]) -> None:
    agent = city.agent_id
    if message.sender == LEDGER:
        await _announce(city, message, chat, agent)
        return
    if (message.sender.startswith("agent:") and not _trusted(message.sender)
            and first_word(message.text) in {"report.notice", "booking.notice"}):
        # MACH2-1 (R17) on the gp too: a notice from an agent outside the ring is not noted in the
        # patient's file (impostor, level 8). One line back, never an instruction followed.
        await _say(city, message.sender, f"{first_word(message.text)}.ack status=ignored reason=not_listed")
        return
    if first_word(message.text) == "report.notice" and message.sender.startswith("agent:"):
        bid = fields_of(message.text).get("booking_id", "")
        if not _we(chat, agent, f"booking_id={bid}", to=message.sender, word="report.notice.ack"):
            await _say(city, message.sender, f"report.notice.ack booking_id={bid} Grazie, leggo il referto "
                       "e richiamo io il paziente se serve un controllo.")
        return
    if first_word(message.text) == "booking.notice" and message.sender.startswith("agent:"):
        # G5: the booking tells us the visit is booked; we close the loop for the follow-up.
        bid = fields_of(message.text).get("booking_id", "")
        if not _we(chat, agent, f"booking_id={bid}", to=message.sender, word="booking.notice.ack"):
            await _say(city, message.sender, f"booking.notice.ack booking_id={bid} Grazie: annoto la visita "
                       "nel fascicolo del paziente. Dopo la visita leggo il referto e propongo io il controllo.")
        return
    if not message.sender.startswith("citizen:"):
        return
    fields = fields_of(message.text)
    emergency = _emergency(message)
    code = None if emergency else _symptom(message)
    if not emergency and code is None and "prescription_number" in fields:
        number = fields["prescription_number"]
        wants = re.search(r"rinnov|scadut|renew|expired|nuova ricetta|new prescription", message.text.lower())
        wants = wants or any(
            row.sender == LEDGER and number in row.text
            and re.search(r"expired|scadut|used|PRESCRIPTION_EXPIRED", row.text) for row in chat
        )
        ours = _we(chat, agent, f"prescription_number={number}", to=message.sender, word="prescription")
        if ours and not wants:
            # P-francesco-43: the official renewal message carries only the number. Ask the Ledger
            # for the state before saying "valid"; expired or used means renew.
            def _state(rows: list[Message]) -> bool:
                return any(r.sender == LEDGER and number in r.text and first_word(r.text) == "prescription"
                           and "state=" in r.text for r in rows)
            if not _state(chat):
                await _say(city, LEDGER, f"prescription prescription_number={number}")
                chat = await _until(city, message.need_id, chat, _state)
            wants = any(r.sender == LEDGER and number in r.text
                        and re.search(r"state=(?!issued|valid|active)", r.text) for r in chat)
        if ours and not wants:
            # P-francesco-37: a valid prescription we just issued is not a renewal request.
            if not _we(chat, agent, "", to=message.sender, word="prescription.valid"):
                en = _lang([*chat, message]) != "it"
                await _say(city, message.sender, f"prescription.valid prescription_number={number} " + (
                    "Your prescription is valid: please use it with the booking centre to book your visit."
                    if en else
                    "La sua ricetta è valida: la usi con il centro prenotazioni per prenotare la visita."))
            return
        await _renew_prescription(city, message, chat, number)
        return
    assessed, keyword, asked = None, code, time.monotonic()  # OPS-13
    if not emergency:
        early = _EARLY_LLM.pop(message.msg_id, None)  # OPS-09: started in main() with the history read
        try:
            assessed = await early if early is not None else await _llm_symptom(city, message.text, emergency_only=code is not None)
        except Exception:
            assessed = None
        # GP-15 (journey 183): "sento il cuore che batte un po' troppo" matched SYM-PALPITATIONS
        # by keyword, then the model said RED_FLAG and the citizen got 112 instead of a visit
        # (no_booking -1). Heart racing alone is the VIS-CARD B protocol; its real red flags
        # (chest pain, fainting, no breath) are keywords. Back pain keeps the model check
        # (P-francesco-19: "non riesco più a stare in piedi").
        emergency = assessed == "RED_FLAG" and code not in ("SYM-PALPITATIONS", "SYM-FOLLOWUP")
        code = code or (assessed if assessed != "RED_FLAG" else None)
    _event("gp.triage", message.need_id, keyword=keyword or "none", llm=assessed or "none",
           code=code or "none", emergency=str(bool(emergency)).lower(),
           wait_ms=int((time.monotonic() - asked) * 1000))  # OPS-13
    if emergency:
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
        elif (asked and message.sender.startswith("citizen:")
              and not _we(chat, agent, "", to=message.sender, word="escalate.emergency")):
            await _gp_again(city, message, chat)
        return
    procedure, priority = _PROTOCOLS[code]
    number = _rx(message.need_id, message.msg_id)
    token = f"prescription_number={number}"
    # The citizen's reply window closes before a ledger round trip comes back, so the
    # prescription is said in this same turn. The ledger write is what the judge reads.
    if _we(chat, agent, token, to=message.sender, word="prescription"):
        return
    line = _rx_line([*chat, message], procedure, priority, code)
    prefs = _prefs(message.text)
    note = _prefs_line(prefs, _lang([*chat, message]) != "it")
    # X-27 / G10: tell our booking centre first, then say it to the citizen. The review only
    # reads the citizen chat, so the agent-to-agent step must be visible there (collaboration).
    en = _lang([*chat, message]) != "it"
    booking = await _peer(city, "booking_centre", "centro prenotazioni booking_centre asst-niguarda")
    # OPS-09: the Ledger write and the referral do not depend on each other: send them together
    # (one slow round trip instead of two). The citizen hears the prescription only after both.
    async def _prescribe() -> bool:
        if _we(chat, agent, token, to=LEDGER, word="prescribe"):
            return True
        return await _say(
            city,
            LEDGER,
            (
                f"prescribe patient={message.sender} procedure={procedure} priority={priority} "
                f"symptom_code={code} {token}"
            ),
        )

    async def _refer() -> bool:
        if not booking or _we(chat, agent, token, to=booking, word="referral"):
            return False
        return await _say(
            city,
            booking,
            f"referral {token} procedure={procedure} priority={priority} "
            + "".join(f"{k}={v} " for k, v in prefs.items())
            + "Ricetta emessa: il cittadino vi contatterà a breve con questo numero."
            + (" Preferenze del cittadino indicate nei campi." if prefs else ""),
        )

    written, referred = await asyncio.gather(_prescribe(), _refer())
    if not written:
        return
    if booking:
        if referred:
            line = line.replace(
                "I am telling the booking centre now: contact it",
                "I have already sent your prescription" + (" and your preferences" if prefs else "")
                + " to our booking centre myself: contact it",
            ).replace(
                "Avviso subito il centro prenotazioni: lo contatti",
                "Ho già passato io la sua ricetta" + (" e le sue preferenze" if prefs else "")
                + " al nostro centro prenotazioni: lo contatti",
            )
    await _say(
        city,
        message.sender,
        f"prescription {token} procedure={procedure} priority={priority} {line}{note}",
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
    best = await _nearest_hospital(city, point) if point else None
    line = _nearest_words(best, en)
    # X-55: the nearest ER belongs to another ASST: warn it too (no personal data, no consent
    # needed) and say so to the citizen. Collaboration across teams, visible in the citizen chat.
    ours = _OUR_AGENTS["hospital"]  # X-56
    if best and best[0] not in (ours, city.agent_id) and best[0].startswith("agent:"):
        if await _say(city, best[0], "emergency.notice reason=red_flag Un cittadino con red flag si trova "
                      f"vicino a voi (circa {best[2]:.1f} km) ed è stato indirizzato al 112 o al pronto "
                      "soccorso più vicino: potrebbe arrivare da voi."):
            line += (" I have also warned that hospital's emergency room myself." if en else
                     " Ho avvisato io anche il pronto soccorso di quell'ospedale.")
    if not line:
        line = (" The nearest emergency room is our hospital in Via Arganini Gerolamo 38 (wheelchair "
                "accessible); in an emergency always call 112." if en else
                " Il pronto soccorso più vicino è il nostro ospedale in Via Arganini Gerolamo 38 "
                "(accessibile in sedia a rotelle); in emergenza chiami sempre il 112.")
    await _say(city, message.sender, ("Thank you." if en else "Grazie.") + line)
    return True
