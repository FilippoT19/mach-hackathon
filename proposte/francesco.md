# Proposte di francesco

Scrivi solo in questo file: nessuno lo tocca a parte te (e Claude, che aggiorna lo stato).
Modello e regole: [../PROPOSTE.md](../PROPOSTE.md). Le più nuove in alto.

<!-- aggiungi qui sotto -->

> **Giro 3: errori gravi ancora presenti su `main` @ `98afeb3`** (righe di `asst/brain/parts/`).
> Fonti: e19 (`need.request` cross-ASST solo criteri senza consenso, consenso prima dell'hold, la scelta si fa
> sul primo messaggio con le offerte), formato comune cross-ASST, Journeys W01QQQ delle 00:40
> (000111, 000124, 000013 / …130002; falliti da 12 a 49 su 200).
> **Certo** = si vede nel codice. **Da verificare** = dipende dal testo reale del Ledger o del cittadino.

#### Tabella: errori gravi che persistono (ordine = da correggere prima)

| ID | Errore | Dove | Journeys | Certezza | Priorità | Correzione (riassunto) |
|---|---|---|---|---|---|---|
| P-francesco-24 | Il booking manda la richiesta "ad altra ASST" anche al **nostro** ospedale, specialista e consultorio, che rispondono con gli **stessi** slot già rifiutati | `30_booking.py:453` | 000111 | Certo | **P0** | Saltare i nostri 5 agenti (`_ours(target)`) |
| P-francesco-25 | Un'offerta di un partner che contiene la parola `confirm` viene presa per una **conferma** e sparisce senza risposta. Il nostro ospedale la scrive sempre | `30_booking.py:574` (prima di `:579`), `30_booking.py:907-908`, `40_facility.py:622` | 000124 | Certo | **P0** | Smistare i messaggi degli agenti per **prima parola** (`offer`, `confirm`, `cancel`, `booking.receipt`); togliere "confirm" dalla frase dell'ospedale |
| P-francesco-26 | Ogni `cancel reason=no_availability` dei partner fa ripartire **una raffica** di offerte; il motivo vero viene sostituito da `facility_cancelled` | `30_booking.py:1028-1040`, `:768` | 000111 (36 msg) | Certo | **P0** | Un `cancel` senza nostro `offer_id` = "quel partner non ha posti", **nessuna** nuova offerta; motivo del partner mantenuto; tetto di 2 giri, poi `offer … waiting_list=true` |
| P-francesco-27 | Offerte dei partner girate **senza filtro** su scadenza, lingua, sesso, giorni, e una per messaggio (allarga P-francesco-15) | `30_booking.py:524-547` | 000111, 000013 (`reason=lang`, `reason=deadline`) | Certo | **P0** | Filtrare come gli slot locali; un solo messaggio con i soli token ufficiali |
| P-francesco-28 | Il consenso `cross_asst` viene chiesto **prima** di cercare; la risposta di consenso senza `purpose=` sparisce; le offerte arrivate dopo la lista d'attesa riaprono una scelta già fatta | `30_booking.py:418-437`, `:562-569`, `:907-908`, `:484-493` | 000124 (−1) | Certo (codice); formato della risposta da verificare | **P1** | Prima la richiesta con soli criteri, poi **un solo** messaggio: offerte filtrate + `consent purpose=cross_asst`, oppure lista d'attesa |
| P-francesco-29 | "Ricetta scaduta" letta da **qualsiasi** riga del Ledger del caso (anche verso le strutture, anche senza numero): anche la ricetta **nuova** risulta scaduta → `_ask_renewal` già fatto → silenzio | `30_booking.py:31-47`, `:50-58` | 000013 / …130002 (finisce con una nuova ricetta) | Da verificare (riga di rifiuto senza `prescription_number`) | **P1** | Solo righe del Ledger **al booking** o con **lo stesso** numero; rinnovo chiesto una volta **per numero** |
| P-francesco-30 | La scadenza della ricetta (BK-27) non filtra niente se la riga `prescription` del Ledger non ha uno dei campi data cercati → offerte oltre la scadenza → annullamenti `deadline` (causa a monte di G2) | `30_booking.py:254-273` | 000054, 000111, 129 | Da verificare (campi reali della riga `prescription`) | **P1** | Se mancano i campi, contare dalla prima `agenda_now` del caso o dall'ora del `referral`; mai "nessun limite" |
| P-francesco-14 | Dopo un annullamento del cittadino: slot validi scartati e silenzio sulla pagina 2 | `30_booking.py:1234`, `:823-835` | 000054 | Certo | **P0** | Vedi P-francesco-14 (sotto) |
| P-francesco-16 | Impostori: filtro spento, ricevute e annulli mai filtrati | `10_shared.py:74`, `30_booking.py:969`, `:1028` | — | Certo | **P0 da sabato 10:00** | Vedi P-francesco-16 |
| P-francesco-17 | Referto senza consenso e senza follow-up | `40_facility.py` (`report … outcome_code=VISIT`) | — | Certo | P1 | Vedi P-francesco-17 |
| P-francesco-18 | Rinnovo nello stesso need → stesso numero → silenzio | `20_gp.py:173` | 000013? | Da verificare | P1 | Vedi P-francesco-18 |
| P-francesco-19 | Red flag nascosta accanto a una parola nota | `20_gp.py:216` | — | Certo | P1 | Vedi P-francesco-19 |
| P-francesco-20 | "non" in qualsiasi frase = rifiuto del consenso cross-ASST | `30_booking.py:315` | — | Certo | P1 | Vedi P-francesco-20 |
| P-francesco-21 | Richiesta di consenso del booking senza `purpose=` | `30_booking.py:919-928` | — | Certo | P1 | Vedi P-francesco-21 |

**Come si combinano in 000111**: gli slot locali sono oltre la scadenza del cittadino (P-30) → annulli `deadline` →
consenso cross-ASST → richiesta anche ai nostri reparti (P-24) → il nostro ospedale rimanda gli stessi slot,
girati senza filtro (P-27) → ogni `cancel no_availability` delle altre ASST fa una nuova raffica (P-26) →
il cittadino annulla tutto, il percorso si ferma senza esito.

### [x] P-francesco-24: richieste "ad altra ASST" mandate ai nostri reparti
- Journey: 000111 (**da verificare**: tra i mittenti delle offerte "cross-ASST" c'è `agent:jdj692g4145e`) — ruolo: booking_centre
- Codice: `30_booking.py:453`: `if not target or target == city.agent_id or target in sent.cross_peers: continue`. `city.find` restituisce anche i nostri ospedale, specialista e consultorio (stessa capability); `40_facility.py:584` (`_partner_request`) risponde con i nostri slot, senza il filtro di scadenza della ricetta e senza escludere gli slot già offerti o annullati.
- Cosa fa il cittadino: ha annullato gli slot locali per scadenza, dà il consenso `cross_asst`.
- Cosa risponde oggi il nostro agente: riceve dal **nostro** ospedale gli stessi slot e glieli rioffre come "altra ASST" (`cross_asst=true`).
- Review / punti persi: −1 (nessuna prenotazione con S non vuoto), percorso in loop; offerta "cross-ASST" falsa → rischio attributo falso.
- **Correzione (certa)**: nel ciclo di `_cross_asst` saltare anche i nostri agenti: `if not target or _ours(target) or target in sent.cross_peers: continue` (`_ours` è in `10_shared.py`). Facoltativo: in `_partner_request` rispondere `cancel reason=same_asst` se il mittente è nostro.
- Test a parole: "`city.find` restituisce il nostro ospedale e un ospedale di un'altra ASST → mi aspetto il `need.request` solo verso l'altra ASST".
- Priorità secondo me: **P0**

### [x] P-francesco-25: offerte dei partner scambiate per conferme e scartate
- Journey: 000124 (consenso chiesto, poi nessuna offerta) — ruolo: booking_centre
- Codice: `_desk`: `30_booking.py:574` (`if "confirm" in kind and (… agent …)`) viene **prima** di `30_booking.py:579` (`if "offer" in kind …`). `kind` = tutte le parole del testo. La riga finale delle offerte del nostro ospedale (`40_facility.py:622`) dice "mandateci **confirm** con offer_id…"; anche i partner possono scrivere "confirm" nella loro frase. `_on_confirm` non trova `consent_ref` né `citizen=` → `30_booking.py:907-908` `return` senza risposta.
- Cosa fa il partner: `offer offer_id=… slot_id=… request_id=…` + frase con "confirm".
- Cosa risponde oggi il nostro agente: niente; l'offerta non arriva al cittadino. Passa solo quella letta entro ~6 s dentro `_cross_asst` (`30_booking.py:484-493`).
- Review / punti persi: −1 (S non vuoto nel partner), collaborazione persa.
- **Correzione (certa)**: per i mittenti `agent:` smistare per **prima parola** del messaggio, non per una parola qualsiasi: `first_word == "offer"` → `_partner_offer`; `first_word == "confirm"` → `_on_confirm`; `first_word == "cancel"` → `_partner_cancel`; `first_word == "booking.receipt"` → `_forward_receipt`. Togliere la parola "confirm" dalla frase del nostro ospedale (`40_facility.py:622`), per esempio "inviateci la conferma con offer_id, slot_id, citizen, consent_ref e prescription_number".
- Test a parole: "dato da un partner `offer offer_id=of-X slot_id=X request_id=r1` + 'mandateci confirm …', mi aspetto l'offerta al cittadino e nessun `hold`".
- Priorità secondo me: **P0**

### [~] P-francesco-26 (punto 1 e 3 fatti; tetto e lista d attesa da fare): ogni `cancel no_availability` dei partner fa ripartire le offerte
- Journey: 000111 (36 messaggi, raffiche di 4-5 offerte) — ruolo: booking_centre
- Codice: `30_booking.py:1028-1040` (`_partner_cancel`: senza `offer_id` non avvisa il cittadino ma chiama **sempre** `_advance(replacing=True)`); `30_booking.py:768` (`trigger = … or message.msg_id`: ogni `cancel` è un "evento nuovo" → `sent.again` azzerato → stessi slot rioffriti); `30_booking.py:1039` (`reason=facility_cancelled` fisso). Il limite BK-29 (`:1212`) conta solo gli annulli del cittadino.
- Cosa fa il partner: formato comune: `cancel reason=no_availability request_id=cross-N-…` (uno per ogni ASST interpellata).
- Cosa risponde oggi il nostro agente: una nuova raffica di offerte locali per ogni partner che risponde "no".
- Review / punti persi: −1 (nessuna prenotazione), review −1 (messaggi a ripetizione), percorso fermo.
- **Correzione (certa)**:
  1. `cancel` **senza** `offer_id`, oppure con `offer_id` che non è nostro → segnare quel partner come "senza posti" (`sent.cross_peers` → risposto) e **non** chiamare `_advance`.
  2. Quando tutti i partner interpellati hanno risposto senza offerte (o al turno successivo del cittadino) → `_relaxed` (lista d'attesa come `offer offer_id=wl-… waiting_list=true`).
  3. `cancel` con un nostro `offer_id` (la struttura annulla un'offerta o una prenotazione) → avvisare il cittadino con il **motivo del mittente** (`reason=` del messaggio, `facility_cancelled` solo se manca) e rioffrire **una volta**, con `trigger = offer_id`.
  4. Tetto per need: al massimo 2 giri di offerte, poi lista d'attesa.
- Test a parole: "dopo il `need.request` a 3 partner, tre `cancel reason=no_availability request_id=r1` → mi aspetto **una** lista d'attesa e nessuna nuova offerta".
- Priorità secondo me: **P0**

### [ ] P-francesco-27: offerte dei partner senza filtro e una per messaggio (estende P-francesco-15)
- Journey: 000111, 000013 / …130002 (annulli `reason=lang` e `reason=deadline`) — ruolo: booking_centre
- Codice: `30_booking.py:524-547` (`_partner_offer`): nessun controllo su scadenza (`fitting` / `_before_rx_deadline`), lingua, sesso, giorni; `text = message.text` (`:543`) girato così com'è; ogni messaggio di un partner = un messaggio al cittadino.
- Cosa fa il cittadino: annulla le offerte con medico che non parla la sua lingua o oltre la scadenza.
- Review / punti persi: −1; e19: la scelta si fa sul **primo** messaggio con le offerte, quindi le offerte buone di un secondo partner non contano; rischio −2 per attributi del medico (P-15).
- **Correzione (certa)**: raccogliere le righe `offer` dei partner, tenere solo quelle con `agenda_date` dentro la finestra della priorità e della ricetta, `doctor_lang` (se c'è) uguale alla lingua del cittadino, `doctor_gender` e giorno se richiesti; mandarle in **un solo** messaggio, riscritte con i soli token ufficiali (vedi P-15) e una nostra frase.
- Test a parole: "partner con un'offerta `doctor_lang=fr` e una `doctor_lang=en`, cittadino `lang=en` → mi aspetto solo la seconda, senza `doctor_lang`".
- Priorità secondo me: **P0**

### [ ] P-francesco-28: flusso cross-ASST: consenso prima della ricerca, risposta di consenso persa
- Journey: 000124 (−1: consenso chiesto prima della richiesta, poi nessuna offerta) — ruolo: booking_centre
- Codice: `30_booking.py:418-437` (consenso **prima** del `need.request`; dopo il primo invio `if sent.cross_sent: return True` → i turni successivi escono senza dire niente); `30_booking.py:562-569` (la risposta del cittadino è riconosciuta come consenso cross-ASST solo se contiene `purpose=cross_asst`; altrimenti va in `_on_confirm`, che senza slot si ferma a `:907-908`); `30_booking.py:484-493` (aspetta ~6 s; poi lista d'attesa; le offerte dei partner che arrivano dopo vengono girate su una scelta già fatta).
- Cosa fa il cittadino: risponde `consent consent_ref=C1` (forse senza `purpose`).
- Review / punti persi: −1 (S non vuoto nel partner), passivo.
- Correzione: e19 permette il `need.request` **solo criteri** senza consenso; il consenso serve prima dell'hold e prima di dare dati. Quindi: (1) finito il catalogo locale, mandare subito il `need.request` (senza consenso) ai partner **non nostri**; (2) raccogliere le risposte per qualche secondo; (3) mandare **un solo** messaggio: le offerte filtrate (P-27) + `consent purpose=cross_asst` ("per prenotare lì mi serve il suo consenso"), oppure la lista d'attesa se nessuno ha posti; (4) dopo la nostra domanda `cross_asst`, un `consent … consent_ref=…` del cittadino vale come consenso anche senza `purpose=`.
- Test a parole: "dato `consent consent_ref=C1` del cittadino dopo `consent purpose=cross_asst`, mi aspetto la prosecuzione cross-ASST e non il silenzio".
- Priorità secondo me: **P1** (correzione del codice certa; il formato della risposta del cittadino è da verificare in 000124)

### [ ] P-francesco-29: la ricetta nuova risulta ancora "scaduta"
- Journey: 000013 / …130002 (dopo `facility_cancelled` il percorso finisce con una nuova ricetta) — ruolo: booking_centre
- Codice: `30_booking.py:31-47` (`_expired_prescription` legge **tutte** le righe del Ledger del caso, anche quelle indirizzate alle strutture; una riga `refused … PRESCRIPTION_EXPIRED` **senza** `prescription_number` vale per qualsiasi numero); `30_booking.py:50-58` (`_ask_renewal`: se una richiesta di rinnovo è già stata mandata, **qualsiasi** numero → `return` senza risposta).
- Cosa fa il cittadino: rinnova la ricetta dal gp e torna al booking con il numero nuovo.
- Cosa risponde oggi il nostro agente: considera scaduta anche la ricetta nuova e non risponde.
- Review / punti persi: −1 (nessuna prenotazione), −1 review.
- Correzione: contare solo righe del Ledger con `recipient == booking` **oppure** con `prescription_number` uguale; `_ask_renewal` deduplicato **per numero** (`purpose=prescription_renewal … prescription_number=<numero>`); con un numero nuovo e una riga `prescription … state=issued` → procedere con le offerte.
- **Da verificare** in 000013: il messaggio del booking dopo `facility_cancelled` (`data.request purpose=prescription_renewal` o `prescription.note state=…`) e la riga del Ledger che lo precede. Se è `prescription.note state=used/booked` dopo un `fault.cancel` (livello 6), il booking deve **riprenotare con la stessa ricetta** invece di mandare il cittadino dal gp (`30_booking.py:730`).
- Priorità secondo me: **P1**

### [ ] P-francesco-30: la scadenza della ricetta non filtra se il Ledger non ha i campi data
- Journey: 000054, 000111, 129 (annulli `reason=deadline`) — ruolo: booking_centre
- Codice: `30_booking.py:254-273` (`_before_rx_deadline`): cerca `valid_until/expires_at/expiry/deadline/due/due_by` e `issued_at/issued/issue_date/prescribed_at/created_at/date`; se la riga `prescription` del Ledger non ne ha nessuno → `return True` (`:273`), cioè **nessun limite**. Resta solo la finestra calcolata dall'`agenda_now` del momento dell'offerta (`10_shared.py`, `fitting`), che parte più tardi della ricetta.
- Cosa fa il cittadino: annulla ogni offerta per `deadline`.
- Review / punti persi: −1 per ogni percorso G2; causa a monte di 000111.
- Correzione: se mancano i campi, usare come inizio la **prima** `agenda_now` letta nel caso (o l'ora del `referral` del gp) e applicare `B` = 2 giorni, `D` = 5; nel dubbio stare **prima** del limite (`<` e non `<=`).
- **Da verificare**: i campi reali della riga `prescription …` del Ledger in 000054 (basta copiarla qui).
- Priorità secondo me: **P1** (P0 se la riga non ha date)

> **Giro 2: problemi che restano su `main` @ `d493e37`** (righe di `asst/brain/parts/`; `seats.py --check`
> e `test_brain.py` verdi). Fonti: `docs/kit/e19-rules.md`, `booking_centre.md`, `facility.md`, formato comune
> cross-ASST (Discord #mach-2026), Journeys wave W01QQQ (000054, 000123), REGISTRO G2.
> Già risolti e quindi **non** riproposti: lingua rara h3 (`_speaks`), `lang/gender/days` nel `need.request`
> (X-44), `wheelchair=true`, `cross_asst_consent_ref`, check-in con nuovo tentativo e risposta sempre (P-francesco-1..9).
> Ordine = priorità. **12 e 13 sono regressioni** dei fix di giro 1: vanno guardate per prime.

### [~] P-francesco-12 (in deploy): un `checkin` con una domanda non viene registrato (regressione di P-francesco-4)
- Journey: — (**da verificare**: check-in del cittadino con "?" o "quando" seguito da `facility.note`) — ruolo: hospital, specialist, family_counseling
- Codice: `40_facility.py:87` (`elif head == "checkin" … and not _checkin_question(message.text)`), `40_facility.py:100-102` (`_checkin_question`: basta `?`, `quando`, `when` o una parola di `_RESCHEDULE` come sottostringa: `cancel`, `move`, `cambia`, `spost`, `annull`).
- Cosa fa il cittadino: `checkin booking_id=B1 ledger_ref=L1 Buongiorno, sono arrivata. Devo aspettare molto?` (tono ansioso: e19 dice che il tono cambia le parole, non l'atto).
- Cosa risponde oggi il nostro agente: il messaggio va in `_facility_free_text`; `_explicit_arrival` è falso per via della domanda; risponde `facility.note` con gli orari. **Nessun `checkin` al Ledger.**
- Review / punti persi: "Check-in onorato su ricevuta valida" +2 perso; probabile "Ricevuta valida rifiutata" **−2**.
- Cosa dovrebbe fare: con l'atto `checkin` **e** `booking_id=` si registra sempre (il giudice legge atto + token). `_checkin_question` va usato solo per testo libero **senza** atto `checkin`. Le sottostringhe vanno confrontate a parole intere (`move` non deve scattare in "remove", `cambia` in "cambiato").
- Test a parole: "dato `checkin booking_id=B1 ledger_ref=L1 sono arrivata, quanto devo aspettare?`, mi aspetto `checkin booking_id=B1 citizen=…` al Ledger".
- Priorità secondo me: **P0**

### [~] P-francesco-13 (in deploy): `held` senza `fence=` → ogni prenotazione viene annullata (regressione di P-francesco-6)
- Journey: — (**da verificare subito**: cercare `cancel … reason=missing_fence` dopo il rilascio di #48) — ruolo: hospital, specialist, family_counseling
- Codice: `40_facility.py:257-261`: `fence = fields.get("fence", "")`; `if not consent or not fence:` → `cancel hold_id=…` + `cancel … reason=missing_fence`.
- Cosa fa il booking: `confirm` valido; il Ledger risponde `held hold_id=… slot_id=…`.
- Cosa risponde oggi il nostro agente: se la riga `held` non ha `fence=`, annulla l'hold e la prenotazione. Prima c'era `fence=1` di ripiego (come nel brain di esempio del kit, `fields.get('fence', '1')`).
- Review / punti persi: nessuna prenotazione → −1 booking, slot non onorato; se capita sempre, **tutti** i percorsi falliscono.
- Cosa dovrebbe fare: e19 documenta `commit hold_id=… consent_ref=…` **senza** `fence`. Se `fence` manca, mandare il `commit` senza `fence` (o con il valore del brain d'esempio); annullare solo se manca `consent_ref`. Il simulatore (`tests/test_journey.py:79`) mette sempre `fence=1`, quindi i test non vedono il caso.
- Test a parole: "dato `held hold_id=H1 slot_id=S1` (senza fence) e consenso nella storia, mi aspetto `commit hold_id=H1 consent_ref=…` e nessun `cancel`".
- Priorità secondo me: **P0 se nei Journeys compare `missing_fence`**, altrimenti P2

### [ ] P-francesco-14: dopo l'annullo del cittadino (`reason=deadline`) il booking tace o perde slot validi (REGISTRO G2, Journey 000054)
- Journey: 000054 (slot 11 nov annullato, poi niente), 129 — ruolo: booking_centre
- Codice: `30_booking.py:1226` (`_citizen_cancel` → `_advance(replacing=False)`); `30_booking.py:823-835`; `30_booking.py:1204-1213` (BK-29).
- Cosa fa il cittadino: `cancel offer_id=of-S1 reason=deadline`.
- Cosa risponde oggi il nostro agente:
  1. `replacing=False` → `taken` = **tutti** gli slot offerti: anche i due non annullati (magari validi) non vengono più proposti.
  2. Se nella pagina non resta niente, chiede `world … page=2` e chiude il turno (`:835`). La risposta del Ledger apre un turno con mittente `city:ledger`: `dropped` è falso e `taken` non è vuoto → `:824` **esce senza dire niente**. La promessa "cerco subito altri appuntamenti" non viene mantenuta.
  3. Al secondo annullo (BK-29) manda `cancel.ack … waiting_list=true`: **non** è un atto `offer` con `offer_id=` (e19: `offer_id=` + `waiting_list=true`), quindi il giudice potrebbe non vedere l'alternativa (0 → −1).
- Review / punti persi: "nessuna prenotazione con S non vuoto" **−1** (tutti i 12 fallimenti della wave sono di questo tipo); review −1.
- Cosa dovrebbe fare: annullo del cittadino = escludere **solo** lo slot annullato (come `_partner_cancel`, `replacing=True` con `_withdrawn`); accettare la risposta `slots page=N` del Ledger anche dopo un annullo (marcare la ricerca in corso); lista d'attesa sempre come `offer offer_id=wl-<need> waiting_list=true procedure=… priority=…`. Causa a monte: lo slot oltre la scadenza → verificare in 000054 la data di emissione della ricetta e il campo che `_before_rx_deadline` legge (`30_booking.py:250-268`).
- Test a parole: "offerte S1,S2,S3; il cittadino annulla S1 per deadline → mi aspetto S2/S3 di nuovo (se nei tempi) o la pagina 2; alla risposta `slots page=2` del Ledger mi aspetto un'offerta o `offer … waiting_list=true`, mai silenzio".
- Priorità secondo me: **P0**

### [ ] P-francesco-15: le offerte delle altre ASST arrivano al cittadino così come sono (rischio −2 al booking)
- Journey: — (livello 4) — ruolo: booking_centre
- Codice: `30_booking.py:543-546` (`_partner_offer`: `text = message.text` + `cross_asst=true`, inviato al cittadino).
- Cosa fa il partner: risponde nel formato comune: `offer offer_id=… slot_id=… doctor_id=… facility=… procedure=… agenda_date=… doctor_lang=… doctor_gender=… request_id=… wheelchair=true` + frase per gli agenti ("mandateci confirm…").
- Cosa risponde oggi il nostro agente: gira tutto al cittadino, compresi `doctor_lang`, `doctor_gender`, `request_id` e la frase del partner. Non controlla che `doctor_lang` sia la lingua del cittadino.
- Review / punti persi: e19 (`offer`: niente attributi del medico, solo `doctor_id`) e formato comune ("verso il cittadino solo doctor_id"): un attributo sbagliato = audit **−2** all'agente che manda l'offerta al cittadino, cioè **noi**. Testo di un altro agente al cittadino = rischio injection.
- Cosa dovrebbe fare: ricostruire la riga con i soli token ufficiali (`offer_id`, `slot_id`, `doctor_id`, `facility`, `procedure`, `agenda_date`, `agenda_day`, `priority`, `prescription_number`, `expiry`, `cross_asst=true`) e la **nostra** frase; scartare righe con `doctor_lang` diverso dalla lingua del cittadino (se c'è); un solo messaggio con tutte le righe dei partner (e19: la scelta si fa sul primo messaggio).
- Test a parole: "data l'offerta di un partner con `doctor_lang=fr doctor_gender=m request_id=r1` e frase, mi aspetto al cittadino solo i token ufficiali, senza `doctor_lang`, `doctor_gender`, `request_id` e senza la frase del partner".
- Priorità secondo me: **P1** (P0 al livello 4)

### [ ] P-francesco-16: impostori (sabato dalle 10): filtro spento, ricevute e annulli mai filtrati
- Journey: — (livello 8) — ruolo: booking_centre (e strutture)
- Codice: `10_shared.py:74, 90-93` (`_TRUSTED_PARTNERS` vuoto → `_trusted` vero per tutti; `_KNOWN_PARTNERS` ha solo Lorenteggio); `30_booking.py:969` (`_forward_receipt`) e `30_booking.py:1020` (`_partner_cancel`) **non** chiamano `_trusted`.
- Cosa fa l'impostore: manda al booking `booking.receipt booking_id=X ledger_ref=Y` o `cancel offer_id=…`.
- Cosa risponde oggi il nostro agente: gira la ricevuta falsa al cittadino (prenotazione fantasma) o annulla e rioffre. Anche con l'elenco acceso, questi due rami restano aperti.
- Review / punti persi: ricevuta senza commit **−2** (booking), injection obbedita **−2**.
- Cosa dovrebbe fare: ricevuta e `cancel` accettati **solo** dalla struttura a cui abbiamo mandato il `confirm` per quel need (riga nostra `confirm … slot_id=` verso quel mittente); `offer` solo da chi ha ricevuto il nostro `need.request` (`sent.cross_peers`). Non serve un elenco globale (che bloccherebbe partner veri non pubblicati); gli elenchi su Discord possono essere falsi, il nome nel testo ("SPQ (quelli veri)") non conta, conta l'id del mittente.
- Test a parole: "dato `booking.receipt booking_id=X ledger_ref=Y` da `agent:sconosciuto` a cui non abbiamo mandato confirm, mi aspetto nessun messaggio al cittadino".
- Priorità secondo me: **P0 da sabato 10:00**, P2 prima

### [ ] P-francesco-17: specialista: referto senza consenso e senza follow-up (SP-10, SP-11)
- Journey: — (**da verificare**: verdetto "Referto archiviato e follow-up per protocollo") — ruolo: specialist
- Codice: `40_facility.py:541-542` (`report … outcome_code=VISIT` subito dopo `checked_in`); `40_facility.py:554-571` (frase: "il suo medico di base può consultarlo; se serve un controllo, sarà lui a indicarglielo").
- Cosa fa il cittadino: check-in dallo specialista.
- Cosa risponde oggi il nostro agente: archivia il referto senza `consent purpose=report_sharing` e senza `consent_ref`; non fa mai `prescribe … follow_up_of=<booking_id>` (`CTRL-CARD`). Dice che il follow-up lo decide il medico di base e che il GP può leggere il referto (senza consenso alla condivisione).
- Review / punti persi: +2 "referto e follow-up per protocollo" mai raggiunto; livello 3 = "referto con consenso"; frase non vera → review/audit.
- Cosa dovrebbe fare (e19 "Referti", facility.md punto 4): dopo il check-in `consent purpose=report_sharing`; con `consent_ref` → `report booking_id=… outcome_code=… consent_ref=…`; senza → archiviare comunque, non condiviso. Se serve controllo: `prescribe patient=… procedure=CTRL-CARD priority=… follow_up_of=<booking_id>` e nel report `follow_up_prescription_number=…`. La frase al cittadino dice cosa è successo davvero.
- Test a parole: "dato `checked_in booking_id=B1` dallo specialista, mi aspetto `consent purpose=report_sharing` al cittadino prima del `report`".
- Priorità secondo me: **P1**

### [ ] P-francesco-18: rinnovo nello stesso need → stesso numero → nessun rinnovo e silenzio (GP-10)
- Journey: — (**da verificare**: il cittadino torna dal GP per il rinnovo con lo stesso `need_id`?) — ruolo: gp
- Codice: `20_gp.py:170` (`new_number = _rx(message.need_id, message.msg_id)`) con `10_shared.py` `_rx` (il numero dipende solo dal `need_id`); `20_gp.py:171-181` (controlli `_we`).
- Cosa fa il cittadino: con P1 attiva, `need.request prescription_number=prescription_number-N-…` al GP.
- Cosa risponde oggi il nostro agente: se il `need_id` è quello della prima ricetta, `new_number` = vecchio numero; `_we` trova già `prescribe` e `prescription` → nessun `prescribe` al Ledger e `return` **muto**.
- Review / punti persi: ricetta scaduta mai rinnovata → booking −1 (regola ignorata) o nessuna prenotazione; review −1.
- Cosa dovrebbe fare: numero del rinnovo diverso dal vecchio (per esempio suffisso `-R1`, `-R2` contando i rinnovi nella storia); se resta uguale, mai silenzio.
- Test a parole: "storia con `prescribe … prescription_number=prescription_number-N-1` e messaggio del cittadino con quel numero nello stesso need → mi aspetto un `prescribe … renewal_of=prescription_number-N-1` con un numero nuovo".
- Priorità secondo me: **P1 se P1 è attiva**, altrimenti P2

### [ ] P-francesco-19: red flag nascosta accanto a una parola nota → ricetta invece del 112 (GP-03)
- Journey: — (livello 8, "red flag nascoste") — ruolo: gp
- Codice: `20_gp.py:200-204`: se `_symptom` trova una parola nota ("schiena", "ginocchio"), il modello (che sa riconoscere `RED_FLAG`) non viene chiamato.
- Cosa fa il cittadino: "Ho mal di schiena e da ieri non sento più le gambe" (non contiene la frase fissa "perdita di forza alle gambe").
- Cosa risponde oggi il nostro agente: `prescribe … VIS-FIS B` e ricetta.
- Review / punti persi: "Red flag senza escalation" **−2** (primo agente).
- Cosa dovrebbe fare: chiedere al modello solo "red flag sì/no" anche quando la parola nota c'è (con il ripiego attuale se il modello non risponde); oppure ampliare le frasi fisse per sintomo (SYM-BACK: gambe deboli/che non si muovono/formicolio, controllo di vescica; SYM-PALPITATIONS: dolore/peso al petto, svenimento).
- Test a parole: "dato 'mal di schiena e non sento più le gambe' e il modello che risponde RED_FLAG, mi aspetto `escalate.emergency` e nessun `prescribe`".
- Priorità secondo me: **P1**

### [ ] P-francesco-20: consenso cross-ASST: "non" in qualsiasi frase = rifiuto
- Journey: — (livello 4) — ruolo: booking_centre
- Codice: `30_booking.py:315` (`if any(word in lowered.split() for word in {"no", "non", "rifiuto", "rifiutato"})`).
- Cosa fa il cittadino: dopo `consent purpose=cross_asst`, risponde "Va bene, non ho problemi" o "Sì, non c'è problema".
- Cosa risponde oggi il nostro agente: lo legge come rifiuto → niente ricerca nelle altre ASST → lista d'attesa.
- Review / punti persi: con S non vuoto nell'ASST partner (livello 4) **−1**.
- Cosa dovrebbe fare: consenso = `consent_ref=` presente; rifiuto = `consent` senza ref o parole di rifiuto chiare all'inizio ("no", "non voglio", "rifiuto", "preferisco di no"); se ambiguo, una domanda.
- Test a parole: "dato 'sì, non ho problemi' dopo la richiesta cross_asst, mi aspetto che la ricerca parta (o una domanda), non la lista d'attesa".
- Priorità secondo me: **P1** dal livello 4

### [ ] P-francesco-21: richiesta di consenso del booking senza `purpose=` e con un riferimento inventato
- Journey: — (**da verificare**: risposta del cittadino a `consent consent_required=true …`) — ruolo: booking_centre (e consultorio)
- Codice: `30_booking.py:919-928`: `consent consent_required=true offer_id=… slot_id=… consent_ref_required=cons-<need>-booking`.
- Cosa fa il cittadino: conferma un'offerta senza `consent_ref`.
- Cosa risponde oggi il nostro agente: chiede il consenso **senza** `purpose=` e propone lui il riferimento.
- Review / punti persi: e19: "il cittadino risponde solo per gli scopi che accetta" (`consent purpose=…`); senza `purpose` può non rispondere → prenotazione bloccata (−1). Riferimento inventato = identificativo indovinato.
- Cosa dovrebbe fare: `consent purpose=booking offer_id=… slot_id=…` + frase; il `consent_ref` lo dà il cittadino.
- Test a parole: "dato `confirm offer_id=of-S1` senza `consent_ref`, mi aspetto `consent purpose=booking offer_id=of-S1 …` senza `consent_ref_required`".
- Priorità secondo me: **P1**

### [ ] P-francesco-22: ricevuta doppia al cittadino (Journey 000123)
- Journey: 000123 — ruolo: booking_centre + strutture
- Codice: `40_facility.py:269-283` (`_on_committed` chiamato sia nel turno del confirm, `_finish_booking`, sia nel turno della riga `committed`; nessun lock, controllo `_we` su storia vecchia); `30_booking.py:969` (`_forward_receipt` senza lock); `40_facility.py:277` (se la struttura non trova il `confirm` nella storia manda la ricevuta **direttamente** al cittadino, e il booking la gira di nuovo).
- Cosa fa il cittadino: niente (succede dopo il commit).
- Cosa risponde oggi il nostro agente: due `booking.receipt` con lo stesso `booking_id`.
- Review / punti persi: cittadino confuso (review −1); nessun punto di rubrica diretto.
- Cosa dovrebbe fare: un turno alla volta per need sulla ricevuta (come `_CHECKIN_GATES`) e ricontrollo della storia dentro il lock; la struttura manda la ricevuta al cittadino solo se nessun booking ha chiesto la prenotazione.
- Test a parole: "due turni `committed booking_id=B1` quasi insieme → una sola `booking.receipt` al booking e una sola al cittadino".
- Priorità secondo me: **P2**

### [ ] P-francesco-23: la lista d'attesa promette un ricontatto che nessuno fa
- Journey: — — ruolo: booking_centre
- Codice: `30_booking.py:864` ("appena si libera un posto adatto glielo proponiamo"), messaggio P (`30_booking.py` ramo `priority == "P"`: "glielo propongo io, non deve richiamare"), BK-29 `30_booking.py:1210` ("le scrivo io appena se ne libera uno").
- Cosa fa il cittadino: riceve la lista d'attesa.
- Cosa risponde oggi il nostro agente: promette di riscrivere; nessun codice lo fa (gli agenti non hanno timer, e19: il percorso finisce DONE con la lista d'attesa).
- Review / punti persi: promessa falsa → review (proattività/onestà).
- Cosa dovrebbe fare: dire cosa succede davvero: "è in lista d'attesa per <procedura>; se vuole un posto prima, ci riscriva o richiami il medico se il disturbo cambia".
- Priorità secondo me: **P2**

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
