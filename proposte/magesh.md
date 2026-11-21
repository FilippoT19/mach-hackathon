# Proposte di magesh

Scrivi solo in questo file: nessuno lo tocca a parte te (e Claude, che aggiorna lo stato).
Modello e regole: [../PROPOSTE.md](../PROPOSTE.md). Le più nuove in alto.

<!-- aggiungi qui sotto -->

### [~] P-magesh-8 (punto 1 fatto: BK-38; punti 2-3 a Giulia): dopo la contesa (`no_capacity`) il booking salta gli slot locali ancora liberi e chiede subito il consenso cross_asst
- Journey: ID da aggiungere (journey del 21/11, 01:05–01:11, esito Fallito) — ruolo: booking_centre
- Cosa fa il cittadino: riceve l'offerta `slot s2 gio 19 nov 15:30` (01:06:07) e la conferma con il consenso (01:06:28). Lo slot lo prende un'altra squadra: tutte le ASST ricevono lo stesso cittadino nello stesso momento
- Cosa risponde oggi il nostro agente: `cancel reason=no_capacity` (01:07:19), poi "sto controllando tutti i posti liberi…" (01:07:21), poi, senza offrire altri slot, chiede il consenso `purpose=cross_asst` (01:08:41). Il resto del journey è il loop del consenso, già risolto con BK-36 (booking 1.0.11)
- Review / punti persi: −1, "Nessuna prenotazione, anche se dopo la contesa restavano slot accettabili liberi". Il giudice dice che nella nostra ASST c'erano ancora slot validi
- Causa probabile (**da confermare con il log del Centro prenotazioni**, Log → Scarica JSON):
  1. **Limite di 8 pagine** (`_MAX_PAGE` in `00_core.py`, controllo a `30_booking.py:959`): arrivato alla pagina 8, il booking passa al cross-ASST anche se il catalogo ha altre pagine. Il commento subito sotto dice "solo dopo aver esaurito tutto il catalogo locale", ma con più di 8 pagine non è vero. Gli slot da pagina 9 in poi non vengono mai visti
  2. **Pagina 1 vecchia**: la ricerca di sostituzione riparte dalla pagina 1 letta prima della contesa, non da una lettura nuova. Le altre squadre hanno appena preso slot, quindi rischiamo un altro `no_capacity`; e non vediamo gli slot liberati nel frattempo
  3. **Filtri troppo stretti** in `fitting()` (`10_shared.py`), se il log mostra che sono state lette tutte le pagine: medico che manca nella tabella `_DOCTORS`, anticipo di 4 ore, giorni del medico, scadenza della ricetta. Il giudice li considera accettabili, noi no
- Cosa dovrebbe fare: dopo un `no_capacity`, offrire al cittadino un altro slot locale accettabile prima di chiedere il consenso cross_asst.
  1. Passare al cross-ASST solo quando sono state lette **tutte** le pagine (pagina corrente = ultima pagina). Se il limite di pagine resta per velocità, arrivarci vuol dire "continuo a leggere" o lista d'attesa, mai cross-ASST
  2. Dopo `no_capacity`, chiedere di nuovo al Ledger `world … page=1` invece di riusare la lettura vecchia
  3. (Prevenzione) Tra la conferma del cittadino (01:06:28) e il `no_capacity` (01:07:19) passano 51 s: è lì che perdiamo la gara. Mandare il `hold` al Ledger subito dopo la conferma, prima di ogni chiamata a `city.llm` o di altre letture
  4. Se il log mostra un filtro troppo stretto: allinearlo alle regole (`docs/kit/e19-rules.md`)
- Test a parole: "dato un catalogo di 10 pagine con un solo slot accettabile a pagina 1 (s2) e uno a pagina 9 (s9), il cittadino conferma s2 e il Ledger risponde `no_capacity`: mi aspetto un `offer` con `slot_id=s9` e nessun `consent purpose=cross_asst`" (oggi fallisce, passa con il punto 1); "dato lo stesso caso con catalogo di 3 pagine e nessun altro slot accettabile, mi aspetto il consenso cross_asst come oggi (nessuna regressione)"
- Priorità secondo te: P1 (la contesa capita in ogni journey con più ASST: ogni slot perso senza sostituzione è −1)

| Caso | Soluzione | Logica | Test |
|---|---|---|---|
| Slot perso nella contesa (`no_capacity`), altri slot locali liberi oltre pagina 8 | Cross-ASST solo con catalogo locale esaurito | La ricerca continua fino all'ultima pagina; il limite di pagine non porta mai al cross-ASST | 10 pagine, s9 a pagina 9 → `offer slot_id=s9`, nessun consenso cross_asst |
| Pagina 1 vecchia dopo la contesa | Rileggere la pagina 1 dopo `no_capacity` | Gli slot presi dagli altri non vengono riofferti; quelli liberati sì | dopo `no_capacity`, il booking manda `world … page=1` al Ledger |
| 51 s tra conferma e hold | `hold` subito dopo la conferma | Meno tempo = meno contese perse | la conferma produce il `hold` prima di ogni altro messaggio |


### [ ] P-magesh-7 (CO-20): "senza ricetta" al consultorio è nel codice ma non in CASI.md e non ha test
- Journey: nessuno (lettura del codice su `main` 69870f8) — ruolo: family_counseling
- Cosa fa il cittadino: chiede una visita al consultorio senza numero di ricetta, es. "vorrei una visita ginecologica"
- Cosa risponde oggi il nostro agente: bene. Offre fino a 3 slot con la ginecologa e la frase "Al consultorio si accede direttamente, senza ricetta… I suoi dati restano riservati al consultorio" (`30_booking.py:784`, commento `CO-20`). Però CO-20 non ha una riga in CASI.md, e in `tests/test_brain.py` compare solo nel commento della sezione 26 (riga 442), senza nessun `check` sul consultorio. Anche CO-01 ha ancora "manca test"
- Review / punti persi: nessuno oggi; il rischio è perderli dopo: se una modifica allo sportello condiviso (`_desk`, usato anche da booking_centre) fa chiedere la ricetta al consultorio, nessun test se ne accorge (−1 secondo CO-01)
- Cosa dovrebbe fare: nessun cambio al comportamento. (1) Aggiungere la riga CO-20 in CASI.md (oppure unirla a CO-01, se è lo stesso caso): caso "il consultorio dice che non serve ricetta e che i dati restano riservati", soluzione "frase fissa CO-20 nell'offerta quando `fixed=CONS-GIN`", test. (2) Aggiungere in `test_brain.py` un `check` per il consultorio, che copre anche il "manca test" di CO-01
- Test a parole: "dato 'vorrei una visita ginecologica' al consultorio, senza `prescription_number`, mi aspetto almeno un `offer` con il medico `c1` e la frase 'senza ricetta', e nessuna richiesta di ricetta (`prescription.note` / `prescription.wait`)"; "dato lo stesso messaggio in inglese, mi aspetto la frase 'needs no prescription'"
- Priorità secondo te: P2 (non perde punti oggi, protegge da regressioni)



### [~] P-magesh-6 (CO-10, in deploy): red flag in gravidanza al consultorio → offerte invece del 112
- Journey: nessuno (lettura del codice su `main` 98d473f) — ruolo: family_counseling
- Cosa fa il cittadino: una cittadina incinta scrive al consultorio, es. "sono incinta e ho perdite di sangue", "ho un dolore forte alla pancia", "ho le contrazioni", "I'm pregnant and bleeding"
- Cosa risponde oggi il nostro agente: X-41 manda al 112 da ogni ruolo, ma il consultorio riconosce la red flag solo per parole fisse (`_RED_FLAGS` + `_RED_FLAGS_MORE`). Coperti: "sanguinamento abbondante", "heavy bleeding", "svenuta", "non riesco a respirare". NON coperti: "perdite di sangue", "sanguino", "bleeding" senza "heavy", "dolore forte", "contrazioni". Il medico di base ha anche il controllo con `city.llm` (`_llm_symptom` → `RED_FLAG`), il consultorio no: il messaggio finisce in `_desk` e la cittadina riceve offerte di slot con la ginecologa
- Review / punti persi: −2 (CO-10 in CASI.md); far prenotare una visita a chi ha un'emergenza è il caso più grave per domain e sicurezza
- Cosa dovrebbe fare: al consultorio, se il testo parla di gravidanza ("incinta", "gravidanza", "pregnant") insieme a sangue, perdite, dolore forte/intenso, contrazioni o perdita di liquido, rispondere `escalate.emergency reason=red_flag` con la stessa frase del 112 ("non si metta alla guida, non resti da sola") e mandare `emergency.notice` all'ospedale, come X-41. Nessuna offerta di slot nello stesso turno. In più (facoltativo): per i messaggi al consultorio che le parole fisse non riconoscono, usare lo stesso controllo `RED_FLAG` con `city.llm` del medico di base, con lo stesso timeout e lo stesso ripiego. Aggiornare la riga CO-10 in CASI.md: X-41 la copre solo in parte
- Test a parole: "dato 'sono incinta di 7 mesi e ho perdite di sangue' al consultorio, mi aspetto `escalate.emergency reason=red_flag` + frase 112 e `emergency.notice` all'ospedale, nessun `offer`"; "dato 'I'm pregnant and have strong contractions', idem in inglese"; "dato 'vorrei una visita ginecologica di controllo in gravidanza', mi aspetto le offerte normali (nessun falso allarme)"
- Priorità secondo te: P0

> Analisi del consultorio (`family_counseling`) fatta su una versione vecchia del brain e
> ricontrollata su `main` (6f68a93). Già risolti su main, quindi NON proposti: lista d'attesa quando
> nessuno slot va bene (BK-10, `_relaxed`), `confirm` senza `consent_ref` (ora chiede il consenso),
> frase umana nelle risposte (`_human`), `cancel` dal cittadino (`_citizen_cancel`), domanda "dove siete"
> (`_on_where`). Restano aperti i 5 casi qui sotto. Il codice dello sportello (`_desk`) è condiviso
> con `booking_centre`, quindi questi fix valgono anche lì.

### [ ] P-magesh-5: le domande del cittadino ricevono offerte invece di una risposta
- Journey: nessuno (lettura del codice) — ruolo: family_counseling (anche booking_centre)
- Cosa fa il cittadino: fa una domanda, es. "serve la ricetta?" o "che orari avete?"
- Cosa risponde oggi il nostro agente: tutto ciò che non è confirm/checkin/cancel/"dove" finisce in `_advance` e il cittadino riceve offerte di slot, non la risposta
- Review / punti persi: domain/proactivity, risposta fuori tema
- Cosa dovrebbe fare: riconoscere che è una domanda e rispondere con una frase (es. "Per il consultorio non serve la ricetta"), poi proporre gli slot solo se il cittadino vuole prenotare. Si può usare una sola chiamata a `city.llm` per dividere il testo in prenotazione / domanda / annullamento e tirare fuori le preferenze (`days`, `gender`, `lang`) come `chiave=valore`; i passi della prenotazione restano a regole
- Test a parole: "dato 'serve la ricetta per il consultorio?', mi aspetto una risposta sì/no con una frase, non una lista di offerte"
- Priorità secondo te: P1

### [~] P-magesh-4 (porta di riserva, in deploy): indirizzo del consultorio forse mancante
- Journey: nessuno (lettura del codice) — ruolo: family_counseling
- Cosa fa il cittadino / agente: manda `data.request fields=address`
- Cosa risponde oggi il nostro agente: da verificare. `_own_street` legge `city.address`, poi `CITY_ADDRESS`, poi `door.txt`, ma in `family_counseling/agent/` non c'è `door.txt`. Se la piattaforma non fornisce l'indirizzo, la risposta è vuota
- Review / punti persi: risposta vuota = −4
- Cosa dovrebbe fare: rispondere `address=Via Giolli Raffaello 23` (PILLAR.md §1). Verificare con `city run family_counseling`; se manca, capire dal kit come va fornito l'indirizzo (niente file di dati nell'immagine senza controllare le regole)
- Test a parole: "dato `data.request fields=address`, mi aspetto `address=Via Giolli Raffaello 23`"
- Priorità secondo te: P1 (P0 se la verifica conferma che è vuoto)

### [x] P-magesh-3 (FA-03: la struttura chiede il numero di prenotazione): `checkin` senza `booking_id` → silenzio
- Journey: nessuno (lettura del codice) — ruolo: family_counseling (anche booking_centre)
- Cosa fa il cittadino: scrive `checkin` senza `booking_id`
- Cosa risponde oggi il nostro agente: niente (`_on_checkin` esce se manca `booking_id`)
- Review / punti persi: cittadino senza risposta = −4
- Cosa dovrebbe fare: se nel caso c'è una sola prenotazione, usare quel `booking_id`; altrimenti chiedere al cittadino il codice della prenotazione con una frase
- Test a parole: "dato `checkin` senza booking_id dopo una prenotazione andata a buon fine, mi aspetto il check-in fatto su quella prenotazione"
- Priorità secondo te: P1

### [ ] P-magesh-2: il Ledger non risponde a hold/commit/checkin → cittadino senza notizie
- Journey: nessuno (lettura del codice) — ruolo: family_counseling (anche booking_centre)
- Cosa fa il cittadino: conferma l'offerta (o fa il check-in)
- Cosa risponde oggi il nostro agente: se `held` / `committed` / `checked_in` non arriva in tempo, scrive solo un log (`care.held.missing`, `care.commit.missing`, `care.checkin.missing`) e al cittadino non dice niente
- Review / punti persi: cittadino senza risposta = −4
- Cosa dovrebbe fare: dire al cittadino che la prenotazione è in corso e che riceverà la conferma appena il sistema risponde. Non ripetere una richiesta che ha preso un 4xx
- Test a parole: "dato `confirm` valido e nessuna risposta `held` dal Ledger, mi aspetto un messaggio al cittadino 'prenotazione in corso'"
- Priorità secondo te: P0

### [ ] P-magesh-1: conferma di un'offerta di lista d'attesa → silenzio
- Journey: nessuno (lettura del codice) — ruolo: family_counseling (anche booking_centre, e la lista d'attesa per priorità `P`)
- Cosa fa il cittadino: riceve `offer offer_id=wl-<need_id> waiting_list=true ...` e risponde `confirm offer_id=wl-...`
- Cosa risponde oggi il nostro agente: niente. L'offerta di lista d'attesa non ha `slot_id`, e `_on_confirm` esce subito se manca lo slot
- Review / punti persi: cittadino senza risposta = −4; succede facilmente al consultorio perché c'è un solo medico (`c1`, donna, it/en, lun–ven), quindi con `gender=m` o un'altra lingua si finisce sempre in lista d'attesa
- Cosa dovrebbe fare: riconoscere `offer_id=wl-...` e rispondere al cittadino `waiting_list offer_id=wl-... status=registered` con una frase ("È in lista d'attesa, la contattiamo appena si libera un posto"). Controllare in `docs/kit/e19-rules.md` se il Ledger ha un'operazione per la lista d'attesa e, se sì, scriverla prima di avvisare il cittadino
- Test a parole: "dato `confirm offer_id=wl-N-123`, mi aspetto `waiting_list offer_id=wl-N-123 status=registered` più una frase"
- Priorità secondo te: P0
