# Proposte di francesco

Scrivi solo in questo file: nessuno lo tocca a parte te (e Claude, che aggiorna lo stato).
Modello e regole: [../PROPOSTE.md](../PROPOSTE.md). Le più nuove in alto.

<!-- aggiungi qui sotto -->

> **Ospedale: check-in, testo libero, prenotazione.** Analisi del codice di `main` @ `6f68a93`
> (righe di `asst/brain/parts/`), confrontato con `docs/kit/e19-rules.md` e `docs/kit/facility.md`.
> Nessun Journey ancora: dove serve la conferma c'è scritto **da verificare nei Journeys**.
> Ordine = priorità. Casi CASI collegati: FA-01, FA-02, FA-03, FA-12, FA-20, X-40.
> Nota per Claude: il codice del check-in (`_on_checkin`, `_on_checked_in`) è comune a ospedale,
> specialista e consultorio; le correzioni 1-3 valgono per tutti e tre.

### [~] P-francesco-1 (FA-03, in deploy): check-in rifiutato, il cittadino riprova e non viene mai registrato (FA-03)
- Journey: — (da codice; **da verificare nei Journeys**) — ruolo: hospital (anche specialist, family_counseling)
- Codice: `40_facility.py:268-270` (`_on_checkin`): `if not _we(chat, agent, token, to=LEDGER, word="checkin")`
- Cosa fa il cittadino: `checkin booking_id=B1 ledger_ref=L1` in anticipo → il Ledger rifiuta. Poi riscrive dentro la fascia (08-13 / 13-18 agenda).
- Cosa risponde oggi il nostro agente: al secondo messaggio vede il `checkin` già mandato e **non lo riscrive** al Ledger; aspetta ~6 s una riga `checked_in` che non arriverà mai; silenzio.
- Review / punti persi: rubrica "Ricevuta valida rifiutata" **−2**; review −1 (messaggio senza risposta); rischio `no_reply`.
- Cosa dovrebbe fare: a ogni **nuovo** messaggio del cittadino (msg_id diverso), se nella storia per quel `booking_id` non c'è `checked_in` e l'ultimo esito è un rifiuto (o nessuna risposta), riscrivere `checkin booking_id=… citizen=…`. **Massimo 3 per `booking_id`** (contati dalla storia: righe nostre a `city:ledger` che cominciano con `checkin `). Mai due volte nello stesso turno. Se c'è già `checked_in`: niente Ledger, si ripete la conferma.
- Logica: un nuovo messaggio del cittadino è una nuova richiesta, non un retry di un 4xx (e19 "Niente retry su un 4xx" vale per la stessa richiesta). Il limite di 3 ferma chi insiste (cittadini ostili, impostori livello 8). Gli agenti non hanno timer: "dopo del tempo" = quando il cittadino riscrive.
- Test a parole: "dato `checkin booking_id=B1` + rifiuto + nuovo `checkin booking_id=B1`, mi aspetto un secondo `checkin booking_id=B1 citizen=…` al Ledger"; "dopo 3 rifiuti, al quarto messaggio nessun `checkin` al Ledger e una frase finale (vedi P-francesco-3)"; "dopo `checked_in`, un reinvio non scrive al Ledger e ripete la conferma".
- Priorità secondo me: **P1**

### [~] P-francesco-2 (FA-03, in deploy): il rifiuto del Ledger in testo libero non viene riconosciuto (FA-03)
- Journey: — (**da verificare nei Journeys**: testo reale di un rifiuto di check-in) — ruolo: hospital (e tutte le strutture)
- Codice: `10_shared.py:220-224` (`_await_line`): rifiuto = riga che comincia con `refused` **e** contiene `checkin`.
- Cosa fa il cittadino: `checkin booking_id=B1` fuori fascia o con booking non valido.
- Cosa risponde oggi il nostro agente: se il Ledger scrive il rifiuto senza `refused` all'inizio, `_await_line` non lo vede, aspetta ~6 s e torna `None` → silenzio.
- Review / punti persi: −1 review, `no_reply`; impedisce P-francesco-1 e P-francesco-3.
- Cosa dovrebbe fare: per il check-in, considerare rifiuto **qualsiasi riga di `city:ledger` indirizzata a noi** (`recipient == agent`), arrivata **dopo** il nostro `checkin`, il cui primo token non è una risposta nota (`checked_in`, `held`, `committed`, `reported`, `prescribed`, `prescription`, `slots`, `agenda`, `world`, `rules`, `catalogue`, `history`). Tenere anche il caso `refused`.
- Logica: e19 "Formati": i rifiuti arrivano in linguaggio naturale senza atto; una risposta senza il campo richiesto va trattata come rifiuto.
- Test a parole: "dato il nostro `checkin booking_id=B1` e la riga del Ledger `Registrazione non possibile: fuori fascia oraria.`, mi aspetto che sia trattata come rifiuto".
- Priorità secondo me: **P1**

### [~] P-francesco-3 (FA-03, in deploy): check-in senza risposta (rifiuto, Ledger muto, `booking_id` mancante) (FA-03)
- Journey: — — ruolo: hospital (e tutte le strutture)
- Codice: `40_facility.py:265-266` (`booking_id` mancante → `return`), `40_facility.py:271-277` (rifiuto o timeout → solo log).
- Cosa fa il cittadino: `checkin ledger_ref=L1` senza `booking_id`; oppure check-in rifiutato; oppure il Ledger non risponde in ~6 s.
- Cosa risponde oggi il nostro agente: niente.
- Review / punti persi: review −1 "messaggio senza risposta", il cittadino rimanda 3 volte (16 min ciascuna) → `no_reply`.
- Cosa dovrebbe fare (sempre **senza** l'atto `checkin`, così il giudice non lo legge come check-in fatto; token `booking_id=B1` + frase):
  - `booking_id` mancante → "Benvenuto! Per registrare il suo arrivo mi serve il numero di prenotazione (booking_id) scritto sulla ricevuta: me lo può scrivere?" (e19: un identificativo mancante si chiede, non si indovina).
  - rifiuto, tentativi < 3 → "Non sono riuscito a registrare il suo arrivo: il check-in si fa nella mezza giornata della visita (08-13 o 13-18). Se è in anticipo, mi riscriva da quell'ora." (motivo del Ledger passato a `_human` come contesto, non copiato tale e quale).
  - rifiuto, 3 tentativi → "Mi dispiace, non riesco a registrare il check-in con questa prenotazione. Controlli il numero sulla ricevuta, oppure si rivolga al centro prenotazioni che può verificarla."
  - Ledger muto → "Ho inviato il suo check-in al registro: le confermo appena arriva la risposta." (il `checked_in` che arriva dopo come turno a sé conferma).
  - Rifiuto che arriva come turno a sé (oggi `_facility` lo ignora: `40_facility.py:50-65` non ha un ramo per righe del Ledger sconosciute): avvisare il cittadino **una volta sola**.
- Test a parole: "dato `checkin ledger_ref=L1`, mi aspetto la domanda sul numero e nessun `checkin` al Ledger"; "dato un rifiuto, mi aspetto una frase con 08-13 / 13-18 e nessuna parola `checkin`".
- Priorità secondo me: **P0** (agente muto)

### [~] P-francesco-4 (FA-20, in deploy): una domanda sul check-in diventa un check-in vero (FA-20, introdotto con X-40)
- Journey: — — ruolo: hospital (e tutte le strutture, `_facility_free_text`)
- Codice: `40_facility.py:74-83`: basta `"booking_id=" in message.text` **oppure** una parola di `_ARRIVED` (`"check in"`, `"check-in"`…); il `booking_id` può essere preso dalla **storia** (ricevuta).
- Cosa fa il cittadino: "Quando posso fare il check in?" oppure "Posso spostare la visita booking_id=B1?" oppure "Vorrei annullare booking_id=B1".
- Cosa risponde oggi il nostro agente: costruisce un finto `checkin booking_id=B1 …` e scrive `checkin` al Ledger. Registra un arrivo che non c'è (se in fascia) oppure prende un rifiuto che poi blocca il check-in vero (P-francesco-1).
- Review / punti persi: possibile audit "attributo falso" −2; check-in vero perso −2; cittadino confuso −1.
- Cosa dovrebbe fare: check-in da testo libero **solo** con una frase di arrivo esplicita al presente ("sono arrivat", "sono qui", "sono in struttura", "i am here", "i'm here", "i have arrived") **e** nessun punto di domanda / nessuna parola di spostamento o annullamento (`spost`, `annull`, `cancel`, `cambia`, `move`, `quando`, `when`). `booking_id=` da solo non basta. "check in"/"check-in" in una domanda → risposta informativa (fascia 08-13 / 13-18 e numero della ricevuta), niente Ledger. Spostare/annullare → indicare il centro prenotazioni.
- Test a parole: "dato 'Quando posso fare il check in?', mi aspetto una risposta con la fascia e nessun `checkin` al Ledger"; "dato 'Sono arrivato, booking_id=B1', mi aspetto `checkin booking_id=B1` al Ledger".
- Priorità secondo me: **P1**

### [~] P-francesco-5 (FA-01, in deploy): `confirm` senza `consent_ref` o senza `slot_id` blocca la prenotazione all'ospedale (FA-01)
- Journey: — (**da verificare**: quanti `confirm` del booking arrivano senza `consent_ref`) — ruolo: hospital (e specialist; codice in `30_booking.py` usato dalle strutture)
- Codice: `30_booking.py:855-856` (niente `slot_id` → `return`); `30_booking.py:864-887` (niente `consent_ref` → la **struttura** manda `consent consent_required=true … consent_ref_required=cons-<need>-booking` al cittadino; senza `citizen` → `return`); `40_facility.py:62-65`: la risposta `consent` del cittadino all'ospedale non contiene `confirm`, va in `_facility_free_text` e riceve `facility.note`.
- Cosa fa il booking/cittadino: il booking (nostro o di un'altra ASST, FA-12) manda `confirm offer_id=… slot_id=… citizen=…` senza `consent_ref`; il cittadino risponde all'ospedale con `consent … consent_ref=…`.
- Cosa risponde oggi il nostro agente: chiede il consenso al cittadino con un riferimento inventato, poi ignora la risposta → nessun `hold`, nessuna ricevuta. Verso il booking: silenzio.
- Review / punti persi: prenotazione persa (booking −1), nessuna risposta all'altro agente entro 10 s (clock, +1 perso), collaborazione persa.
- Cosa dovrebbe fare: la struttura **non** chiede il consenso al cittadino (in e19 il consenso lo raccoglie il centro prenotazioni; il booking manda `confirm` con `offer_id`, `consent_ref`, `slot_id`, `prescription_number`, `citizen`). Se manca `consent_ref` o `slot_id`: rispondere **subito al mittente** `cancel offer_id=… reason=missing_consent_ref` (o `reason=missing_slot_id`) con una frase, così il booking lo chiede e rimanda il confirm. Se si vuole tenere la richiesta di consenso: gestire la risposta `consent … consent_ref=…` del cittadino nell'ospedale (ramo in `_facility` prima di `_facility_free_text`) e fare `hold` + `commit`.
- Test a parole: "dato `confirm offer_id=of-S1 slot_id=S1 citizen=citizen:x` da `agent:bk` senza `consent_ref`, mi aspetto `cancel offer_id=of-S1 reason=missing_consent_ref` ad `agent:bk` e nessun messaggio al cittadino".
- Priorità secondo me: **P0** (agente muto verso il booking, prenotazione bloccata)

### [~] P-francesco-6 (FA-01, in deploy): `consent_ref` inventato nel `commit` (FA-01)
- Journey: — (**da verificare**: commit rifiutati con `CONSENT_MISSING` o verdetti audit) — ruolo: hospital (e tutte le strutture)
- Codice: `40_facility.py:201-205` (`consent = f"cons-{need}-booking"`), `40_facility.py:213` (`fence` = `1` se manca).
- Cosa fa il cittadino: — (caso interno: la riga `held` non riporta il consenso e la storia non ha più l'`hold`).
- Cosa risponde oggi il nostro agente: `commit hold_id=… consent_ref=cons-<need>-booking fence=1`.
- Review / punti persi: e19 "un identificativo mancante si chiede, non si indovina"; rischio audit "attributo falso" −2 o commit rifiutato.
- Cosa dovrebbe fare: prendere `consent_ref` solo dal `confirm` o dal nostro `hold` (anche con `history need_id=…` / `recall` sul Ledger se la pagina di storia non li ha); se non c'è, `cancel hold_id=…` al Ledger e `cancel offer_id=… reason=missing_consent_ref` a chi ha chiesto, invece di inventarlo.
- Test a parole: "dato `held hold_id=H1 slot_id=S1` senza consenso nella storia, mi aspetto nessun `commit` con `cons-…` inventato e un `cancel` al mittente".
- Priorità secondo me: **P2** (da verificare quanto capita)

### [~] P-francesco-7 (FA-02, in deploy): hold/commit rifiutato: motivo generico e hold non liberato (FA-02)
- Journey: — (**da verificare**: testi reali di `NO_CAPACITY`, `PRESCRIPTION_EXPIRED`, `CONSENT_MISSING`) — ruolo: hospital (e tutte le strutture)
- Codice: `40_facility.py:257` (`reason=facility_cancelled` fisso); `40_facility.py:241-244` (prende l'**ultimo** slot con `hold`, non quello rifiutato); `40_facility.py:184-185` (commit rifiutato: nessun `cancel hold_id=…`).
- Cosa fa il cittadino: — (il booking ha confermato, il Ledger rifiuta hold o commit).
- Cosa risponde oggi il nostro agente: `cancel offer_id=… reason=facility_cancelled` al booking; l'hold resta occupato fino alla scadenza.
- Review / punti persi: con P1 attiva il booking non capisce che deve chiedere il rinnovo (`PRESCRIPTION_EXPIRED`); con P2 che manca il consenso `cross_asst`; con P3 che lo slot è riservato (`NO_CAPACITY`) → riprenotazione sbagliata, −1.
- Cosa dovrebbe fare: `reason=` con il codice del Ledger se c'è (`prescription_expired`, `consent_missing`, `no_capacity`), altrimenti `facility_cancelled`; slot preso dalla riga di rifiuto o dall'`hold` di quel turno; dopo un commit rifiutato `cancel hold_id=…` al Ledger.
- Test a parole: "dato `refused commit … PRESCRIPTION_EXPIRED`, mi aspetto `cancel offer_id=… reason=prescription_expired` al booking e `cancel hold_id=…` al Ledger".
- Priorità secondo me: **P1** se una regola P1/P2/P3 è attiva, altrimenti **P2**

### [~] P-francesco-8 (FA-20, in deploy): secondo messaggio libero all'ospedale senza risposta (FA-20)
- Journey: — — ruolo: hospital (e tutte le strutture)
- Codice: `40_facility.py:84-85`: `facility.note` una sola volta per caso.
- Cosa fa il cittadino: "dove posso parcheggiare?" e poi "c'è un ascensore?".
- Cosa risponde oggi il nostro agente: alla prima la nota fissa; alla seconda niente.
- Review / punti persi: review −1 "messaggio senza risposta / preoccupazione ignorata".
- Cosa dovrebbe fare: rispondere a ogni messaggio (un turno = un messaggio, non serve il blocco); usare `_human` con la domanda del cittadino come contesto. Per l'ospedale aggiungere i fatti veri che abbiamo: indirizzo (`city.address`), accessibile in sedia a rotelle, check-in nella mezza giornata della visita, prenotare/spostare → centro prenotazioni.
- Test a parole: "dati due messaggi liberi di seguito, mi aspetto due risposte".
- Priorità secondo me: **P1**

### [~] P-francesco-9 (FA-03, in deploy): conferma del check-in senza i valori del registro (FA-03)
- Journey: — (**da verificare**: testo reale della riga `checked_in`) — ruolo: hospital (e tutte le strutture)
- Codice: `40_facility.py:290-301` (`_on_checked_in`): al cittadino solo `checkin booking_id=… <frase>`.
- Cosa fa il cittadino: `checkin booking_id=B1 ledger_ref=L1` → il Ledger risponde `checked_in booking_id=B1 …`.
- Cosa risponde oggi il nostro agente: `checkin booking_id=B1` + frase ("grazie di essere arrivato puntuale…").
- Review / punti persi: e19 "Chi invia cosa": la struttura risponde **con i valori del registro**; review domain/proactivity.
- Cosa dovrebbe fare: copiare nel messaggio i token `chiave=valore` della riga `checked_in` (tutti tranne `booking_id`, già presente). Solo per l'ospedale aggiungere alla frase "la struttura è accessibile anche in sedia a rotelle" (unica struttura accessibile, PILLAR §3). Nessun orario inventato.
- Test a parole: "dato `checked_in booking_id=B1 slot_id=S9 at=…`, mi aspetto `checkin booking_id=B1 slot_id=S9 at=… <frase>`".
- Priorità secondo me: **P2**

### [~] P-francesco-10 (FA-12, in deploy): richieste cross-ASST: lingua rara e attributi del medico (FA-12)
- Journey: — (**da verificare**: verdetti audit su offerte cross-ASST) — ruolo: hospital
- Codice: `10_shared.py:251-258` (`_speaks`: `*` = qualsiasi lingua non it/en); `40_facility.py:334, 338-346, 381-382` (`doctor_lang`, `doctor_gender` dalla tabella `_DOCTORS` scritta nel codice).
- Cosa fa l'altra ASST: `need.request procedure=VIS-FIS priority=B lang=fr request_id=r1`.
- Cosa risponde oggi il nostro agente: offre h3 (che parla solo it + `vi`) a un cittadino `fr`, con `doctor_lang=it/vi`.
- Review / punti persi: offerta fuori `S` per il loro cittadino; e19 "offer": niente attributi annidati, mandare `doctor_id` e lasciare al registro lingua e genere → se la tabella sbaglia, audit "attributo falso" −2.
- Cosa dovrebbe fare: in `_speaks` usare la lingua rara vera (`vi` per h3, `_RARE_LANG`) al posto di `*`; nelle offerte mandare solo `doctor_id` (togliere `doctor_lang`/`doctor_gender`) oppure leggerli dal `world` del Ledger.
- Test a parole: "dato `need.request … lang=fr`, mi aspetto nessuno slot di h3"; "dato `lang=vi`, mi aspetto solo slot di h3".
- Priorità secondo me: **P2** (P1 dal livello 4, scarsità tra ASST)

### [-] P-francesco-11: da verificare nei Journeys prima di toccare il codice
- Motivo: servono messaggi e misure dei Journeys reali per verificare i quattro punti.
- `40_facility.py:174-175`: `_finish_booking` cerca `committed` con `booking_id=<hold_id>`. Se nel Ledger vero `booking_id` ≠ `hold_id`, la ricevuta parte solo se il `committed` apre un turno suo. Guardare una riga `committed` reale.
- `00_core.py:150-163` (X-40): a una domanda clinica rispondiamo con `scope.note`. e19 "Comportamento del brain" dice `OutOfScope`, senza mandare nulla. Conformance ok (stadio "NOT TESTED"), ma da confermare che non costi in audit.
- `40_facility.py:37-46`: `emergency.ack` all'agente che avvisa ("lo accompagniamo al pronto soccorso"): promessa che l'ospedale non può mantenere da solo; valutare una frase più neutra.
- Tempi: confirm → ricevuta può superare 10 s (`_await_line` ~6 s su `held` + ~6 s su `committed`): controllare il +1 clock nei Journeys.
- Priorità secondo me: **P2**
