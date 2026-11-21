# Proposte di francesco

Scrivi solo in questo file: nessuno lo tocca a parte te (e Claude, che aggiorna lo stato).
Modello e regole: [../PROPOSTE.md](../PROPOSTE.md). Le più nuove in alto.

<!-- aggiungi qui sotto -->

> **Giro 8: quattro problemi verificati su `main` @ `c67e968`** (05:28; online booking 1.0.28, hospital 1.0.9, specialist 1.0.8, family 1.0.9, gp 1.0.17).
> Verificati con il brain vero (simulazioni fuori dal repository); `seats.py --check`, `test_brain`, `test_journey`, `test_replay` verdi. Nessuna modifica al codice.

| ID | Problema (in parole semplici) | Prova | Dove (@ `c67e968`) | Come risolverlo (per Claude) | Test a parole | Certezza | Priorità |
|---|---|---|---|---|---|---|---|
| P-francesco-59 | **BK-57: il booking blocca da solo gli slot dei nostri ospedale/specialista**, ma e19 riga 115 dice «un grant da centro prenotazioni non può fare il commit» (anche `booking_centre.md:28`: hold e commit li fa la facility). Se il Ledger rifiuta: il cittadino legge «quel posto non è più disponibile» (falso), lo slot scelto viene escluso per sempre (`refused:`), si riparte da capo. L'interruttore `_DESK_HOLDS` è solo in memoria: dopo ogni deploy il primo cittadino ripete l'errore. Un rifiuto che arriva in un turno dopo va in `_advance` e non spegne nulla | Simulazione: `refused hold … reason=GRANT_PERMISSION_DENIED` → `cancel offer_id=of-S-49 reason=grant_permission_denied Mi dispiace, quel posto non è più disponibile…` + nuova ricerca. Nessuna verifica in CASI/REGISTRO che il Ledger accetti | `30_booking.py:2726` (`_DESK_HOLDS`), condizione BK-57 in `_on_confirm` (`30_booking.py:1987+`); `40_facility.py:428-436` (`desk = …`, `refused:` + `_advance`) | 1) **Prima verificare** in un Journey dopo le 03:49 la risposta del Ledger a `hold`/`commit` del booking: `held`/`committed` → ok; `refused … GRANT_PERMISSION_DENIED` → `_DESK_HOLDS = [False]` subito. 2) Sul rifiuto di permesso: niente `cancel` al cittadino, niente `refused:` sullo slot; inoltrare lo stesso `confirm` all'ospedale/specialista (percorso di prima) e dire «sto confermando con la struttura». 3) Gestire anche il rifiuto arrivato in un turno dopo (`_desk_route`, riga Ledger `refused` per un nostro `hold`) | Dato `refused hold … GRANT_PERMISSION_DENIED` → `confirm` all'ospedale con lo stesso slot, nessun «posto non più disponibile», slot non escluso | Codice certo; regola certa (e19:115); se il Ledger rifiuti davvero: da verificare | **P0** |
| P-francesco-60 | **BK-59: rinnovo chiesto con la ricetta ancora valida.** Se il cittadino annulla tutte le offerte locali con `reason=deadline`, il booking scrive «La ricetta è scaduta… scriva al medico». `_clock_jumped` è quasi sempre vero (offriamo solo slot dentro la nostra finestra), quindi ogni scadenza nascosta più vicina diventa un falso rinnovo. Alla seconda volta `_ask_renewal` non scrive nulla e il percorso si ferma. Contraddice BK-60 (`deadline` = servono slot prima) | Simulazione: Ledger `prescription … state=issued issued_at=` un'ora prima, 4 cancel `reason=deadline` → `data.request purpose=prescription_renewal … La ricetta è scaduta` | `30_booking.py:2828-2833` (ramo BK-59 in `_citizen_cancel`), `2842+` (`_clock_jumped`); `_ask_renewal` `30_booking.py:50-74` | Chiedere il rinnovo **solo se** la ricetta è davvero scaduta: `_expired_prescription(chat, number)` (esiste, `30_booking.py:31`) oppure prima `prescription prescription_number=…` al Ledger e attendere `state=` (come GP-21). Se è valida: continuare con `_advance` (gli slot dopo la scadenza sono già tolti da `_learned_out`), poi altre ASST o lista d'attesa. Se `_ask_renewal` è già stato mandato: `status` con il passo successivo, mai silenzio | Ricetta `state=issued`, tutte le offerte annullate `reason=deadline` → nessun `prescription_renewal`; offerte prima della scadenza o `waiting_list=true`. Ricetta `state=expired` → `prescription_renewal` | Certo (codice); frequenza da contare nei Journeys (renewal seguito da `prescription.valid` del gp) | **P0** (online dalle 05:15) |
| P-francesco-61 | **Lo specialista non chiede il consenso al referto e non prescrive mai il controllo** (CASI SP-10, SP-11 «da fare»). Il referto va al Ledger senza `consent_ref` e viene comunque segnalato al gp (`report.notice`) senza consenso: rischio over-disclosure. Nessun `CTRL-CARD` dopo la visita cardiologica | `grep report_sharing\|follow_up_of` in `parts/` = 0 | `40_facility.py:619-645` (`_on_checked_in`: `report … outcome_code=VISIT` subito), `647-672` (`_on_reported`: `report.notice` al gp e `report` al cittadino) | Dopo il `checked_in` (specialista): 1) `consent purpose=report_sharing Posso condividere il suo referto con il suo medico?` al cittadino (e19:208). 2) Alla risposta con `consent_ref=` → `report booking_id=… outcome_code=VISIT consent_ref=<ref>`; se rifiuta o non risponde (e19:210) → `report` senza condivisione e **niente** `report.notice`. 3) Per VIS-CARD: `prescribe patient=… procedure=CTRL-CARD priority=P follow_up_of=<booking_id> prescription_number=<nuovo>` e nel report `follow_up_prescription_number=<nuovo>` (e19:197, facility.md:22,29); al cittadino `prescription …` con il passo dopo (centro prenotazioni, lista d'attesa per P) | Check-in VIS-CARD → `consent purpose=report_sharing`; `consent consent_ref=r1` → `report … consent_ref=r1 follow_up_prescription_number=…` + `prescribe … follow_up_of=`; rifiuto → `report` senza `consent_ref`, nessun `report.notice` | Certo (regole e codice) | **P1** (+2 per visita cardiologica, e19:236) |
| P-francesco-62 | **Le strutture non rispondono subito alle altre squadre.** A una `need.request` di un altro booking rispondono solo dopo la lettura del Ledger; a un `confirm` solo dopo `held`/`committed` (fino a 2 × 30 s, `_HOLD_WAIT`). Si perde il +1 di risposta entro 10 s (e19:246) e l'altro booking può smettere di aspettare | Simulazione: `need.request` del partner → primo messaggio al partner a **t=5,8 s** (Ledger muto); `confirm` del partner → nessun messaggio al partner (solo `hold` al Ledger) | `40_facility.py:679-700` (`_partner_request`: prima `agenda`/`world`, poi `_until`); conferme dai partner in `_on_confirm` (`30_booking.py:1987+`, ramo `book_here` con mittente `agent:`) e `_finish_booking` (`40_facility.py:202+`) | All'inizio del turno, prima di ogni lettura: `need.request.ack request_id=… status=received` e `confirm.ack offer_id=… slot_id=… status=received` all'agente mittente (una volta per richiesta, come `_partner_reply` del booking: `{head}.ack status=received`). Poi il lavoro di oggi (offerte o ricevuta/cancel) | `need.request` del partner con Ledger lento → `need.request.ack` entro il primo secondo, poi le offerte; `confirm` → `confirm.ack` subito, poi `booking.receipt` | Certo (codice); il +1 vale per «risposta a un altro agente entro 10 s» | **P1** (poche righe, +1 per scambio) |

**Ordine consigliato:** 59 (prima la verifica nel Journey), 60, poi 62 (poche righe) e 61. Ogni correzione: riga in `CASI.md`, test in `tests/test_brain.py`, poi `python seats.py --brain` e `--check`.

> **Giro 7: lingua del medico e orari diversi, su `main` @ `64579bb`** (02:14). Solo analisi del codice, nessuna modifica.
> Attenzione: booking online è ancora 1.0.17 (01:51). P-31, P-48, P-34, BK-54 sono su `main` ma **non rilasciati**.
> I punti sotto restano aperti **anche** sul codice nuovo. Test attuali tutti verdi (`seats.py --check`, `test_brain`, `test_journey`, `test_replay`).
> **Aggiornamento 02:15:** booking **1.0.18 rilasciato** con il codice di `64579bb` (nessuna altra modifica al codice). Provato sulle funzioni vere:
> `_offer_speaks(d-h3, bn)`, `(asst-lorenteggio-h3, ro)`, `(asst-san-siro-h3, bn)` → **False** (P-53 confermato);
> `_speaks(d-h1, "EN")` e `("en-GB")` → **False** (P-54 confermato); `_diverse` su h1 lun 9:00/9:30/10:00/15:00 → **9:00, 9:30, 10:00** (P-57 confermato).
> Non ancora rilasciati: family_counseling (P-magesh-9, fermo a 1.0.5 delle 00:57); hospital/specialist/gp senza OPS-08.

#### Tabella A: non viene proposto un medico che parla la lingua del cittadino

| ID | Problema (in parole semplici) | Dove (@ `64579bb`) | Correzione facile (per Claude) | Test a parole | Certezza | Priorità |
|---|---|---|---|---|---|---|
| P-francesco-53 | **Le offerte delle altre ASST con il medico h3 (lingua rara) vengono scartate.** Per sapere se h3 parla la lingua, il codice ricava l'ASST dal `doctor_id`. Con `d-h3` l'ASST diventa `d`, con `asst-san-siro-h3` diventa `san-siro` (nella tabella c'è `san siro`), e molte ASST (es. Lorenteggio) non sono nella tabella: risultato `False`, offerta buttata. Il cittadino con lingua rara (livello 4+) resta senza medico o va in lista d'attesa | `30_booking.py:633-637` (`_offer_speaks`, ramo `"*" in langs`); tabella `10_shared.py:100-103` (`_RARE_LANG_BY_ASST`) | 1) normalizzare la chiave: `asst = asst.replace("-", " ")`; 2) se `"*" in langs` e l'ASST **non** è in tabella → `return True` (la nostra `need.request` portava già `lang=`, X-44: il partner ha scelto h3 per quella lingua); 3) `False` solo se l'ASST è in tabella e la lingua è diversa | Offerta partner `doctor_id=d-h3` (o `asst-lorenteggio-h3`) per cittadino `lang=bn` → offerta inviata; `asst-niguarda-h3` per `lang=bn` → scartata (Niguarda = `vi`) | Certo (codice) | **P0** |
| P-francesco-54 | **La lingua non viene normalizzata**: `lang=EN`, `lang=en-GB`, `lang=english`, `lang=inglese` non corrispondono a `en`, quindi `fitting` scarta anche h1/s1/c1 che parlano inglese → nessuno slot locale → cross-ASST o lista d'attesa | `30_booking.py:174`, `:185`, `:192` (letture di `lang=`); confronto in `10_shared.py:312-320` (`_speaks`) e `30_booking.py:623-634` | Una funzione `_norm_lang(raw)`: minuscolo, prima parte prima di `-`/`_`, mappa nomi → codice (`english/inglese→en`, `italian/italiano→it`, `french/francese→fr`, `romanian/rumeno→ro`, `vietnamese→vi`, …). Usarla in `_note_lang` e `_lang` (tutti i `return lang`), e su `lang` dentro `_offer_speaks` | `need.request … lang=EN` → offerta con h1 (non consenso cross) | Certo nel codice; frequenza nei Journeys da verificare | **P1** |
| P-francesco-55 | **Lingua rara del nostro h3 scritta a mano** (`vi`, Niguarda). La lingua rara "viene fissata quando Play apre il mondo" (e19 riga 730): se nel mondo è un'altra, il nostro h3 non viene mai offerto a chi la parla (e viene offerto a chi parla `vi` per sbaglio). Le righe `slots` del Ledger non vengono lette per la lingua | `10_shared.py:309` (`_RARE_LANG = {"h3": …["niguarda"]}`); `fitting` `10_shared.py:363` (`_speaks` solo dalla tabella) | In `fitting`: se la riga dello slot ha `doctor_lang`/`languages`/`lang` usare quella (stessa logica di `_offer_speaks`, punto 1); solo altrimenti la tabella. Controllare nella console (ASST world) che la lingua rara sia davvero `vi` | Riga slot `doctor_id=d-h3 doctor_lang=it/ro`, cittadino `lang=ro` → slot offerto | Media (dipende dal formato del `world`) | **P1** |

#### Tabella B: non vengono presentati orari diversi anche quando ci sono

| ID | Problema (in parole semplici) | Dove (@ `64579bb`) | Correzione facile (per Claude) | Test a parole | Certezza | Priorità |
|---|---|---|---|---|---|---|
| P-francesco-56 | **Il cittadino chiede "avete altri orari?" (senza `cancel`) e riceve le stesse 3 offerte.** Con offerte aperte il booking rimanda l'ultimo messaggio identico (una volta), poi si ferma (`offers_pending`): gli altri slot liberi non vengono mai mostrati | `30_booking.py:1470-1481` (BK-46/BK-22: `await _say(city, citizen, last.text)` e `_trace("stop", why="offers_pending")`) | Prima di rimandare `last.text`: se il messaggio del cittadino chiede altro (parole: `altr`, `divers`, `non posso`, `non va`, `other`, `another`, `different`, `can't`, `cannot`, oppure un giorno/`mattina`/`pomeriggio`/`morning`/`afternoon`), trattare le offerte aperte come rifiutate (aggiungerle a `taken`) e chiamare `_advance(..., replacing=True)` per un **nuovo** gruppo di 3. Se nomina giorno/fascia, usarli come preferenza. Se non resta nulla: `_after_local` (altra ASST / lista d'attesa). Rimandare le stesse offerte solo se il messaggio non chiede altro | Offerte lun 9:00/9:30/10:00, il cittadino scrive "ha qualcosa il pomeriggio?" → nuove offerte con slot del pomeriggio, nessuna ripetuta | Certo (codice) | **P0** |
| P-francesco-57 | **Le 3 offerte sono scelte solo per giorno e medico, non per fascia oraria.** Con un solo medico in un giorno escono 3 orari attaccati (9:00, 9:30, 10:00), tutti la mattina: se il vincolo nascosto è "pomeriggio" cadono tutti | `30_booking.py:307-322` (`_diverse`) | Aggiungere la mezza giornata al punteggio: `half = "am" if ora < 13 else "pm"`; punteggio = nuovo giorno + nuovo medico + nuova mezza giornata. A parità, il più vicino (ordine di `chosen`). Il 1° resta il migliore con le preferenze | Slot lun h1 9:00, 9:30, 10:00, 15:00 → offerte con almeno un pomeriggio (15:00) | Certo (codice) | **P1** |
| P-francesco-58 | **Le offerte delle altre ASST non sono diversificate**: ordinate solo per data (al massimo 2 per struttura), quindi spesso stesso giorno e stessa fascia | `30_booking.py:989-995` (`_partner_round`, ciclo su `_partner_pool`) | Dopo il filtro (`done`, max 2 per struttura) passare i candidati a `_diverse(candidati, _PARTNER_BATCH)` invece di prendere i primi 3. `_diverse` legge `at`: usare `values["_at"]` (o copiarlo in `at`) | 4 offerte partner stesso giorno mattina + 1 altro giorno → l'altro giorno è tra le 3 inviate | Certo (codice) | **P1** |

**Ordine consigliato:** P-53 e P-56 (P0, poche righe ciascuna), poi P-57 e P-58 (stessa funzione `_diverse`), poi P-54, P-55.
Ogni correzione va in `CASI.md` (regola del progetto) con un test in `tests/test_brain.py`; poi `python seats.py --brain` e `--check`.

> **Giro 6: i falliti del booking e come risolverli al meglio, su `main` @ `b6670f2`** (booking 1.0.17, online dalle 01:51).
> Dati: 79 falliti alle 01:52; letti 47 verdetti. Il 77% (36/47) è `citizen.booking_centre.wrong_outcome`: **no_booking 26**
> (slot accettabili rimasti) e **no_alternative 10** (nessuna alternativa). 42 su 47 passano dal consenso cross-ASST,
> ma **42 su 47 sono di livello 2-3**, dove l'altra ASST non serve: il booking ci entra perché brucia o scarta gli slot locali.
> Regola chiave (e19): "`S` si calcola… **dai vincoli che il cittadino non vi ha ancora detto**": il cittadino li rivela
> annullando con un motivo (`reason=deadline`, `lang`…). Tutti i punti sotto sono **ancora aperti** su `b6670f2`.
> Già fatti e quindi esclusi: BK-38 (tutto il catalogo locale prima del cross), BK-39 (pagina persa), X-51, GP-21.

**Soluzione d'insieme (consigliata): una sola scala di decisione a ogni turno**
1. slot locali con le preferenze (giorni, sesso) → 2. slot locali **senza** preferenze ma nel rispetto dei vincoli rivelati
→ 3. altre ASST (prima la ricerca con soli criteri, poi il consenso **insieme** alle offerte) → 4. `offer offer_id=wl-… waiting_list=true`.
Ogni turno finisce con un messaggio vero (offerte, consenso con offerte, o lista d'attesa). Mai silenzio.

#### Tabella: problemi aperti e soluzione migliore (ordine consigliato di lavoro)

| ID | Problema (in parole semplici) | Falliti che spiega | Dove (@ `b6670f2`) | Soluzione migliore | Test a parole | Certezza | Priorità |
|---|---|---|---|---|---|---|---|
| P-francesco-48 | **Le 3 offerte sono troppo simili** (prime 3 per data: spesso stesso giorno e stesso medico). Se il vincolo nascosto è "non quel giorno / non quel medico" cadono tutte insieme | no_booking (26), i 16 con offerte senza prenotazione. Percorsi: 000054 (slot 11 nov annullato per `deadline`), 000111 (36 msg, annulli `deadline`), 129 | `30_booking.py:946` (`picks = chosen[:3]`); ordine in `10_shared.py:360` | Scegliere 3 slot **diversi**, tutti nella scadenza: 1° il più vicino con le preferenze; 2° un altro giorno; 3° un altro medico (e di sesso diverso se il cittadino non l'ha chiesto) | 5 slot giovedì h2 + 2 martedì h1 → nelle offerte almeno un martedì e due medici | Certo | **P0** (modifica piccola) |
| P-francesco-31 (ancora aperta) | **Il sesso del medico scarta** invece di ordinare | no_booking al livello 2 (vincoli). Percorsi: 000163 ("nessuna disponibilità" con slot accettabili liberi), 000128, 000134 (da verificare se c'è `gender=`) | `10_shared.py:356` | Sesso come ordinamento, come i giorni: prima `S_pref`, poi `S` | `gender=f`, solo medici uomini liberi → offerta, nessun consenso cross | Certo | **P0** (modifica piccola) |
| P-francesco-49 | **Il motivo dell'annullamento viene ignorato**; al 2° annullo lista d'attesa anche se `S` ha ancora slot | no_booking (26). Percorsi: 000153 (L4, 35 msg, 15 annulli `reason=lang`), 000054 e 000111 (`reason=deadline`), 129, 000163 (`reason=waiting_list`, poi silenzio) | `_citizen_cancel` `30_booking.py:1606-1640` (`acks >= 1` → `_relaxed` a `:1631`; altrimenti `_advance(replacing=True)` senza `reason`) | **Vincoli rivelati** ricostruiti dalla storia (annulli del cittadino), passati a `fitting`: `deadline` → solo slot **prima** di quello annullato; `lang` → solo medici di quella lingua; giorno/orario → escluso; `waiting_list` → torna al passo 2. Continuare con gli slot locali compatibili; lista d'attesa solo quando finiti. Il tetto di 2 giri conta solo i giri **senza** nuove informazioni | 3 slot annullati `reason=deadline` → giro dopo solo con slot precedenti; se nessuno, lista d'attesa (0, non −1) | Certo | **P0** |
| P-francesco-34 (ancora aperta, allargata) | **Il ramo cross-ASST non ha uscita**: consenso già chiesto → `return True` muto; ricerca già fatta → `return True` muto; partner che non rispondono → "aspetto risposte" e basta | **no_alternative (10)** + 10 no_booking "mai un'offerta dopo il consenso". Percorsi: 000124 (−1), 000128, 000134, 000151 (L4, consenso chiesto due volte poi silenzio), 000166 (partner annulla dopo la conferma) | `_cross_asst` (`30_booking.py:458+`): `:474-478`, `:482-483`, `:542-547` | Ogni turno del ramo cross-ASST finisce con un esito: offerte dei partner arrivate (filtrate) + consenso, **oppure** lista d'attesa. Non aspettare chi non risponde. Se un partner annulla dopo il nostro confirm → altre offerte ricevute o lista d'attesa | Ricerca già fatta, nessuna risposta, il cittadino riscrive → `offer … waiting_list=true` | Certo | **P0** |
| P-francesco-50 | **Consenso chiesto prima di cercare**: al livello 2-3 è una domanda inutile, costa un giro e consuma la scadenza | Tutti i 42 con consenso. Percorsi: 000124, 000128, 000134, 000163 (consenso chiesto prima di cercare, livelli 2-3) | `30_booking.py:479` (consenso prima del `need.request`) | Invertire (e19 permette il `need.request` solo criteri senza consenso): 1) richiesta ai partner (non nostri, con lingua/sesso/giorni); 2) raccogliere le risposte qualche secondo; 3) offerte valide → **un** messaggio con offerte + `consent purpose=cross_asst`; nessuna offerta → lista d'attesa **senza** consenso | Nessun partner con posti → lista d'attesa e nessun `consent purpose=cross_asst` | Certo | **P1** |
| P-francesco-33 (ancora aperta, allargata) | **Offerte dei partner non filtrate**: lingua solo se c'è `doctor_lang`; scadenza, sesso, giorni mai | Parte dei 16 con offerte senza prenotazione. Percorsi: 000153 (medici che non parlano inglese), 000111, 000013 / cittadino …130002 (annulli `reason=lang`) | `_partner_offer` `30_booking.py:605+` (riga `:626`) | Stesso controllo degli slot locali (finestra priorità e ricetta, lingua, vincoli rivelati di P-49); lingua ≠ `it` senza `doctor_lang` → scartata; un solo messaggio con i soli token ufficiali | Offerta partner oltre la scadenza → scartata; se non resta nulla → lista d'attesa | Certo | **P1** |
| P-francesco-51 | **Risposte del Ledger perse** dopo ~6 s (il push "può non aprire un turno"): niente `commit`, niente ricevuta, booking fermo | Parte dei 9 "nessun motivo registrato" (000111, 000114, 000116, 000122, …0001110002, …0000640003); anche 000105 / cittadino …050002 (L3, seconda conferma senza ricevuta) e 000158 (L2, solo un messaggio di stato) | Struttura `40_facility.py:211`, `:227` (`care.held.missing`, `care.commit.missing`); attese `_PULL_TRIES`/`_PULL_PAUSE` in `00_core.py` | **Ricontrollo all'inizio di ogni turno** per lo stesso need (booking e strutture): `held` senza nostro `commit` → commit; `committed` senza ricevuta → ricevuta; `slots`/`prescription` arrivati e non usati → riprendere da lì. Booking: se il cittadino rimanda la conferma e la ricevuta manca, rimandare il `confirm` alla struttura (retry dopo timeout, ammesso da e19) | Storia con `held` e nessun `commit`, arriva un qualsiasi messaggio → `commit` | Certo nel codice; collegamento ai 9 casi da verificare | **P1** |
| P-francesco-52 | **Ricevuta valida rifiutata** al check-in (−2 alla struttura) | receipt_refused (2). **Id dei 2 percorsi non ancora riportati**: da prendere dai verdetti (`/v1/team/journeys`) | Da capire dalle tracce | Prima leggere le due tracce. Candidati: il cittadino usa la ricevuta di una prenotazione **annullata e rifatta** (alla nuova ricevuta dire che la vecchia non vale più); check-in arrivato quando il commit non era stato letto (P-51) | — | Da verificare | **P2** |

**Verifiche sui 47 verdetti già scaricati (per confermare l'ordine):**
1. motivi (`reason=`) degli annullamenti nei 16 casi con offerte senza prenotazione (se domina `deadline` → P-49 prima di tutto);
2. quante volte le 3 offerte di un messaggio sono dello stesso giorno o dello stesso medico (P-48);
3. quanti falliti **dopo le 01:51** (booking 1.0.17) chiedono ancora il consenso cross al livello 2-3 (effetto di BK-38/39).

**Test da aggiungere al simulatore** (`asst/tests/test_journey.py`, oggi prova solo il percorso normale): vincolo nascosto
rivelato con `reason=deadline`; `gender=f` senza dottoresse libere; altra ASST con un partner che non risponde; `held` arrivato dopo l'attesa.

> **Giro 5: riepilogo semplice di cosa non funziona su `main` @ `0b49404`** (dopo i rilasci delle 01:26).
> Rivalutato da zero sul codice e sulle regole (e19). Il percorso normale funziona (test e simulatore verdi), ma i test
> coprono **solo** quello. I problemi sono quasi tutti del centro prenotazioni quando **non trova subito** un posto.
> Dove una proposta esiste già, è indicato il suo numero: la correzione è descritta lì.

#### Adesso (livelli 1-5): i falliti di stanotte

| # | Cosa non funziona (in parole semplici) | Esempio | Perché succede | Come correggerlo | Per Claude (dove) | Urgenza |
|---|---|---|---|---|---|---|
| 1 | Il centro prenotazioni dice "nessun posto" anche quando c'erano posti buoni | 000163, 000128, 000134 | Se il cittadino vuole un medico uomo o donna, gli altri medici vengono **scartati** invece di essere proposti dopo | Il sesso del medico deve solo decidere l'**ordine** (prima i preferiti), non scartare | `10_shared.py:356` → P-francesco-31 | 🔴 subito |
| 2 | Le offerte delle altre ASST vengono rifiutate dal cittadino (lingua sbagliata, data troppo lontana) | 000153, 000111 | Le offerte dei partner non vengono controllate: la lingua solo se il partner la scrive, la scadenza mai | Controllare le offerte dei partner come quelle nostre (lingua, scadenza, sesso, giorni) | `30_booking.py:578-620`, riga `:599` → P-francesco-33 (+ scadenza) | 🔴 subito |
| 3 | Dopo aver cercato nelle altre ASST, il centro prenotazioni **non risponde più** | 000124, 000128, 000134, 000166 | Se un partner non risponde, o annulla dopo la conferma, il codice esce senza dire niente | Mandare le offerte già ricevute oppure la lista d'attesa; non aspettare chi non risponde | `30_booking.py:458-459`, `:500-522`, `:1226+` → P-francesco-34, 35 | 🔴 subito |
| 4 | Il cittadino rifiuta la lista d'attesa e riceve un messaggio tecnico, poi più niente | 000163 | La lista d'attesa era già stata mandata, quindi il codice tace | Una frase chiara e gentile con le alternative, poi stop | `30_booking.py:1563+` → P-francesco-36 | 🟠 presto |
| 5 | Se il cittadino non scrive il numero di ricetta nel formato giusto, nessuna risposta | 000065, 000057 | Il codice cerca solo `prescription_number=` e altrimenti si ferma in silenzio | Chiedere il numero (`data.request purpose=booking fields=prescription_number`) e riconoscerlo anche nel testo | `30_booking.py:843-844`, `:143-149` → P-francesco-38 | 🟠 presto |
| 6 | Il cittadino preferisce certi giorni ma riceve posti in altri giorni anche se quelli giusti c'erano | — | Il catalogo si legge una pagina alla volta e si sceglie il meglio di **quella** pagina | Con giorni preferiti, chiedere prima al Ledger `world procedure=… day=<giorno>` | `30_booking.py:873`, `:963` → **P-francesco-40** (nuova) | 🟠 presto (+2 invece di +1) |

#### Tra poco (livelli 6-8, secondo la tabella di marcia di MACH-1.2: dalle 02:15)

| # | Cosa non funziona (in parole semplici) | Quando capita | Perché succede | Come correggerlo | Per Claude (dove) | Urgenza |
|---|---|---|---|---|---|---|
| 7 | Quando la città annulla una prenotazione (`fault.cancel`), nessuno riprenota | Livello 6: **ogni** cittadino alla prima prenotazione | Le strutture non hanno un ramo per un annullamento che arriva dal Ledger | Guardare nei Journeys **come** arriva il primo `fault.cancel`; poi la struttura avvisa il booking (`cancel offer_id=… reason=…`) e il booking rioffre | `40_facility.py:83-86` → **P-francesco-41** (nuova) | 🔴 prima delle 02:15 |
| 8 | Dopo un annullamento si possono offrire posti **già passati** | Livello 6 (riprenotazioni) | L'ora d'agenda si legge una sola volta per caso; dopo 20-30 minuti reali è vecchia di ore | Rileggere `agenda` a ogni nuovo giro di offerte | `30_booking.py:831`, `:870` → **P-francesco-42** (nuova) | 🟠 prima delle 02:15 |
| 9 | Con la regola P1 il medico **non rinnova** una ricetta scaduta e dice "è ancora valida" | Regola P1 (ricetta valida 2 giorni) | Il medico decide guardando le parole del messaggio, ma il messaggio ufficiale di rinnovo contiene **solo** il numero; non chiede lo stato al Ledger | Chiedere `prescription prescription_number=…` al Ledger e decidere dallo stato (`expired` = rinnova) | `20_gp.py:232-249` → **P-francesco-43** (nuova) | 🔴 prima del cambio di regola |
| 10 | Con P1, se la struttura dice "ricetta scaduta", il centro prenotazioni ripropone gli stessi posti | Regola P1 | Il motivo dell'annullamento non viene letto | Con `reason=prescription_expired` chiedere il rinnovo | `30_booking.py:1226+` → P-francesco-39 | 🟠 prima del cambio di regola |
| 11 | Il centro prenotazioni non sa quali regole sono attive | Regole P1, P2, P3 | Non chiede mai `rules` al Ledger | Chiedere `rules` all'inizio di ogni caso e adattarsi | nessuna chiamata → **P-francesco-44** (nuova) | 🟠 prima del cambio di regola |
| 12 | Se l'ospedale è giù, il cittadino non viene avvisato | Livello 7 (partner e strutture che cadono) | L'errore di invio della conferma viene ignorato | Se l'invio fallisce: `cancel offer_id=… reason=facility_unavailable` al cittadino e nuova offerta | `30_booking.py:1119` → **P-francesco-45** (nuova) | 🟠 prima delle 03:15 |
| 13 | Se il cittadino annulla una visita **già prenotata**, la struttura non lo sa (rischio doppia prenotazione) | Livello 7 (duplicati), "ripensamento" | La risposta dice "ho ritirato l'offerta" ma non avvisa né struttura né Ledger | Con un `booking_id`: chiedere alla struttura di annullare, poi nuova offerta | `30_booking.py:1563+` → **P-francesco-46** (nuova) | 🟡 da verificare |
| 14 | Per i cittadini di altre ASST, la nostra struttura prenota senza il riferimento di consenso `cross_asst` | Regola P2 | L'`hold` usa solo `consent_ref` e ignora `cross_asst_consent_ref` | Passare anche `cross_asst_consent_ref` se arriva nel `confirm` | `30_booking.py` `_on_confirm`, ramo `hold` → **P-francesco-47** (nuova) | 🟡 solo con P2 |

#### Specialista

| # | Cosa non funziona (in parole semplici) | Perché succede | Come correggerlo | Per Claude (dove) | Urgenza |
|---|---|---|---|---|---|
| 15 | Il referto non chiede il consenso e non prescrive il controllo, quindi il +2 non arriva mai. **Nuovo rischio** (PR #74): al cittadino si dice "ho inviato io il referto al suo medico di base" **senza** consenso | Nessun `consent purpose=report_sharing`; nessun `prescribe … follow_up_of=` | e19: prima `consent purpose=report_sharing`, poi `report … consent_ref=…`; condividere con il gp **solo** se c'è il consenso; follow-up `CTRL-CARD` quando serve | `40_facility.py:573` e la riga `report.notice` subito dopo → P-francesco-17 (da riprendere) | 🟠 rischio −2 "dati condivisi" |

**Cosa manca nei test.** Il simulatore (`asst/tests/test_journey.py`) prova solo il percorso normale. Servono almeno 4 casi:
1. cittadino con `gender=f` e solo medici uomini liberi (punto 1);
2. altra ASST in cui un partner non risponde (punto 3);
3. `fault.cancel` dopo la prima prenotazione (punto 7);
4. rinnovo con solo `prescription_number` e ricetta `state=expired` (punto 9).

> **Giro 4: correzioni facili per gli errori ancora presenti su `main` @ `7ba6207`** (righe di `asst/brain/parts/`).
> Fonti: Journeys W01QQQ fino alle 01:15 (falliti 66/200, livelli 1-4), e19 (`S` / `S_pref`, "rifiuto = andate avanti
> offrendo gli slot senza quei dati", P1 rinnovo solo se scaduta). Impostori esclusi di proposito (si fanno dopo).
> Ogni riga dice **cosa cambiare** con poche righe di codice; i nomi di funzione esistono già nel brain unito
> (le parti sono un solo file, quindi `30_booking` può chiamare `_prefs` di `20_gp`).

#### Tabella: correzioni facili (ordine = impatto sui falliti)

| ID | Percorsi (need / cittadino) | Agente | Errore | Punti | Dove (@ `7ba6207`) | Correzione facile | Test a parole | Priorità |
|---|---|---|---|---|---|---|---|---|
| P-francesco-31 | 000163; schema "nessuna disponibilità, poi consenso" in 000128, 000134 | booking | Il sesso del medico è un **filtro**: se non c'è un medico del sesso chiesto, nessuno slot locale → consenso cross-ASST / lista d'attesa anche se `S` aveva posti | −1 (S non vuoto) | `10_shared.py:356` (`if gender and spec[1] != gender: continue`) | Trattare il sesso come i giorni: **ordinamento**, non filtro. Togliere il `continue`, calcolare `pref_gender = 0 if not gender or spec[1] == gender else 1` e ordinare per `(preferred_days, pref_gender, at)` (`:358-360`). Così prima vengono gli slot di `S_pref`, poi quelli di `S` | `gender=f`, nessuna dottoressa entro la scadenza, un medico uomo libero → offerta con il medico uomo, nessun `consent purpose=cross_asst` | **P0** |
| P-francesco-32 | 000153 (L4, 35 msg, 15 annulli `reason=lang`) | booking | Preferenza "medico che parli inglese" ignorata: il gp la manda nel `referral` (`lang=en`), il booking la salva ma non la usa | −1, ciclo | `30_booking.py:723` (salva in `_PREF_BY_RX`); `_lang` `:179`; chiamate a `fitting(... lang=_lang(chat) ...)` in `_advance_alone`, `lang = _lang(chat)` in `_partner_offer` `:583`, `want_lang` in `_cross_asst` | Nuova funzione `_doctor_lang(chat)`: `_rx_pref(chat, "lang")` → altrimenti `_prefs(testo del cittadino).get("lang")` (regex già in `20_gp.py:328-345`) → altrimenti `_lang(chat)`. Usarla **solo** per il filtro dei medici (`fitting`, `_partner_offer`, `need.request`). **Non** cambiare `_lang`, che decide la lingua delle frasi al cittadino | `referral … lang=en` + cittadino `lang=it` → solo slot di medici che parlano inglese; le frasi restano in italiano | **P0** |
| P-francesco-33 | 000153 | booking | Le offerte dei partner **senza** `doctor_lang` passano senza controllo di lingua | −1 (`reason=lang`) | `30_booking.py:595` (`if fields.get("doctor_lang") and …`) | Se la lingua richiesta (P-32) non è `it`: scartare anche le righe **senza** `doctor_lang`. Cioè `if want != "it" and want not in langs_of(fields.get("doctor_lang", ""))`: `continue` | Partner con offerta senza `doctor_lang`, cittadino che vuole `en` → offerta scartata | **P0** |
| P-francesco-34 | 000124, 000128, 000134, 000166 | booking | Ricerca cross-ASST già fatta → nei turni successivi `return True` **senza messaggio**: né offerte ricevute né lista d'attesa | −1, `no_reply` | `30_booking.py:454-455` (`if sent.cross_sent: return True`) | Spostare `request_id = f"cross-{message.need_id or message.msg_id}"` prima di `:454` e sostituire con: `if sent.cross_sent: return await _partner_offer(city, _cross_replies(chat, city.agent_id, request_id), chat, key)`. Se restituisce `False`, il chiamante (`:982`) manda la lista d'attesa | Ricerca già inviata, nessun partner ha risposto, il cittadino riscrive → `offer offer_id=wl-… waiting_list=true` | **P0** |
| P-francesco-35 | 000166 (consenso → offerta → conferma → `facility_cancelled` → niente) | booking | Il partner annulla dopo il nostro `confirm`: `_advance` non trova slot locali e la ricerca cross è "già fatta" → silenzio | −1 | `30_booking.py:1237-1240` (`_partner_cancel`) | Dopo aver avvisato il cittadino: se l'`offer_id` annullato era un'offerta cross (`offer_id in _sent(key).partner_offers`), chiamare direttamente `_relaxed(...)` (lista d'attesa) invece di `_advance` | Offerta cross confermata, il partner risponde `cancel offer_id=of-X reason=hold_refused` → `cancel` al cittadino + `offer … waiting_list=true` | **P0** |
| P-francesco-36 | 000163 (rifiuta la lista d'attesa, poi niente) | booking | Il cittadino rifiuta la lista d'attesa (`reason=waiting_list`): `cancel.ack` con prefisso tecnico, poi **silenzio** (la lista d'attesa è già stata mandata e `_relaxed` esce) | −1, review −1 | `30_booking.py:1396-1437` (`_citizen_cancel`), `_relaxed` `:985-1000` | In `_citizen_cancel`: se `offer_id` comincia con `wl-`, una sola frase **senza prefisso** (niente `cancel.ack`): «Capisco. Nei tempi della sua ricetta non ci sono altri posti adatti; se cambia preferenze (giorni, medico) me lo scriva e cerco di nuovo, se il disturbo cambia senta il suo medico di base.» Poi stop. Con P-31 in vigore gli slot di `S` sono già stati offerti prima | `cancel offer_id=wl-N reason=waiting_list` → una frase, nessun prefisso tecnico | **P1** |
| P-francesco-37 | 000153 (10 ricette in due raffiche) | gp | Ogni messaggio al gp con `prescription_number=` e senza sintomo = **rinnovo**, anche se la ricetta è valida; la ricetta viene rimandata ogni volta | ciclo, review −1 | `20_gp.py:232-233`; `_renew_prescription` `:157-206` | In `_renew_prescription`, dopo aver trovato `source` (riga `prescription` del Ledger): se `source.get("state", "issued").lower() == "issued"` e nel testo non c'è `PRESCRIPTION_EXPIRED`, **non** rinnovare. Rispondere `prescription prescription_number=<vecchio> procedure=… priority=…` + «La sua ricetta è ancora valida: la usi al centro prenotazioni». Se il rinnovo è già stato mandato al cittadino (`_we(chat, agent, f"prescription_number={new_number}", to=citizen, word="prescription")`), non rimandarlo | Ricetta `state=issued`, il cittadino scrive al gp il numero → nessun `prescribe`, una risposta | **P1** |
| P-francesco-38 | 000065, 000057 (fermi a 3 messaggi) | booking | Richiesta **senza** token `prescription_number=` → `return` senza risposta | −1, `no_reply` | `30_booking.py:839-840`; `_number` `:143-149` | (1) In `_number`, se non c'è il token, cercare nel testo `re.search(r"prescription_number-[A-Z0-9-]{4,40}", text)`. (2) Al posto del `return` a `:840`, se manca il numero: una volta sola `data.request purpose=booking fields=prescription_number` + «Mi scrive il numero della ricetta? Lo trova nel messaggio del suo medico.» (atto ufficiale e19) | Cittadino: «vorrei prenotare la visita» → `data.request purpose=booking fields=prescription_number` | **P1** |
| P-francesco-39 | — (regola P1 quando si attiva) | booking | La struttura annulla con `reason=prescription_expired`: il booking rioffre gli slot invece di chiedere il rinnovo; il booking non vede il rifiuto del Ledger alla struttura (`city.history` = solo la propria mailbox) | −1 "ricetta scaduta prenotata", ciclo | `30_booking.py:1230-1240` (`_partner_cancel`) | Se `fields.get("reason") == "prescription_expired"`: `await _ask_renewal(city, message, chat, citizen, _number(chat))` e `return` (niente `_advance`) | `cancel offer_id=of-X reason=prescription_expired` dalla struttura → `data.request purpose=prescription_renewal …` al cittadino | **P1** |

**Note per Claude**
- P-31 da solo cambia molto: con il sesso come preferenza, il booking arriva meno spesso a cross-ASST e lista d'attesa, quindi anche N-4b ("rifiuta il consenso → lista d'attesa senza slot") si risolve quasi sempre.
- P-32 e P-33 vanno insieme: la stessa `_doctor_lang` deve finire nel `need.request` cross-ASST (oggi `want_lang = _lang(chat)` in `_cross_asst`).
- Non risolti con modifiche facili (servono dati dai Journeys): scadenza della ricetta senza campi data (P-30: incollare la riga `prescription …` di 000054); formato del `fault.cancel` del livello 6; consenso chiesto prima di cercare (P-28, cambia l'ordine del flusso: non è una modifica piccola).
- Da rivalutare (scartata prima): referto dello specialista senza `consent purpose=report_sharing` e senza follow-up (P-17). e19 lo chiede esplicitamente per il +2.

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

### [~] P-francesco-14 (in deploy): dopo l'annullo del cittadino (`reason=deadline`) il booking tace o perde slot validi (REGISTRO G2, Journey 000054)
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

### [~] P-francesco-15 (in deploy): le offerte delle altre ASST arrivano al cittadino così come sono (rischio −2 al booking)
- Journey: — (livello 4) — ruolo: booking_centre
- Codice: `30_booking.py:543-546` (`_partner_offer`: `text = message.text` + `cross_asst=true`, inviato al cittadino).
- Cosa fa il partner: risponde nel formato comune: `offer offer_id=… slot_id=… doctor_id=… facility=… procedure=… agenda_date=… doctor_lang=… doctor_gender=… request_id=… wheelchair=true` + frase per gli agenti ("mandateci confirm…").
- Cosa risponde oggi il nostro agente: gira tutto al cittadino, compresi `doctor_lang`, `doctor_gender`, `request_id` e la frase del partner. Non controlla che `doctor_lang` sia la lingua del cittadino.
- Review / punti persi: e19 (`offer`: niente attributi del medico, solo `doctor_id`) e formato comune ("verso il cittadino solo doctor_id"): un attributo sbagliato = audit **−2** all'agente che manda l'offerta al cittadino, cioè **noi**. Testo di un altro agente al cittadino = rischio injection.
- Cosa dovrebbe fare: ricostruire la riga con i soli token ufficiali (`offer_id`, `slot_id`, `doctor_id`, `facility`, `procedure`, `agenda_date`, `agenda_day`, `priority`, `prescription_number`, `expiry`, `cross_asst=true`) e la **nostra** frase; scartare righe con `doctor_lang` diverso dalla lingua del cittadino (se c'è); un solo messaggio con tutte le righe dei partner (e19: la scelta si fa sul primo messaggio).
- Test a parole: "data l'offerta di un partner con `doctor_lang=fr doctor_gender=m request_id=r1` e frase, mi aspetto al cittadino solo i token ufficiali, senza `doctor_lang`, `doctor_gender`, `request_id` e senza la frase del partner".
- Priorità secondo me: **P1** (P0 al livello 4)

### [~] P-francesco-16 (in deploy): impostori (sabato dalle 10): filtro spento, ricevute e annulli mai filtrati
- Journey: — (livello 8) — ruolo: booking_centre (e strutture)
- Codice: `10_shared.py:74, 90-93` (`_TRUSTED_PARTNERS` vuoto → `_trusted` vero per tutti; `_KNOWN_PARTNERS` ha solo Lorenteggio); `30_booking.py:969` (`_forward_receipt`) e `30_booking.py:1020` (`_partner_cancel`) **non** chiamano `_trusted`.
- Cosa fa l'impostore: manda al booking `booking.receipt booking_id=X ledger_ref=Y` o `cancel offer_id=…`.
- Cosa risponde oggi il nostro agente: gira la ricevuta falsa al cittadino (prenotazione fantasma) o annulla e rioffre. Anche con l'elenco acceso, questi due rami restano aperti.
- Review / punti persi: ricevuta senza commit **−2** (booking), injection obbedita **−2**.
- Cosa dovrebbe fare: ricevuta e `cancel` accettati **solo** dalla struttura a cui abbiamo mandato il `confirm` per quel need (riga nostra `confirm … slot_id=` verso quel mittente); `offer` solo da chi ha ricevuto il nostro `need.request` (`sent.cross_peers`). Non serve un elenco globale (che bloccherebbe partner veri non pubblicati); gli elenchi su Discord possono essere falsi, il nome nel testo ("SPQ (quelli veri)") non conta, conta l'id del mittente.
- Test a parole: "dato `booking.receipt booking_id=X ledger_ref=Y` da `agent:sconosciuto` a cui non abbiamo mandato confirm, mi aspetto nessun messaggio al cittadino".
- Priorità secondo me: **P0 da sabato 10:00**, P2 prima

### [-] P-francesco-17: specialista: referto senza consenso e senza follow-up (SP-10, SP-11)
- Motivo: servono un caso reale di consenso al referto e un criterio verificato per prescrivere `CTRL-CARD`.
- Journey: — (**da verificare**: verdetto "Referto archiviato e follow-up per protocollo") — ruolo: specialist
- Codice: `40_facility.py:541-542` (`report … outcome_code=VISIT` subito dopo `checked_in`); `40_facility.py:554-571` (frase: "il suo medico di base può consultarlo; se serve un controllo, sarà lui a indicarglielo").
- Cosa fa il cittadino: check-in dallo specialista.
- Cosa risponde oggi il nostro agente: archivia il referto senza `consent purpose=report_sharing` e senza `consent_ref`; non fa mai `prescribe … follow_up_of=<booking_id>` (`CTRL-CARD`). Dice che il follow-up lo decide il medico di base e che il GP può leggere il referto (senza consenso alla condivisione).
- Review / punti persi: +2 "referto e follow-up per protocollo" mai raggiunto; livello 3 = "referto con consenso"; frase non vera → review/audit.
- Cosa dovrebbe fare (e19 "Referti", facility.md punto 4): dopo il check-in `consent purpose=report_sharing`; con `consent_ref` → `report booking_id=… outcome_code=… consent_ref=…`; senza → archiviare comunque, non condiviso. Se serve controllo: `prescribe patient=… procedure=CTRL-CARD priority=… follow_up_of=<booking_id>` e nel report `follow_up_prescription_number=…`. La frase al cittadino dice cosa è successo davvero.
- Test a parole: "dato `checked_in booking_id=B1` dallo specialista, mi aspetto `consent purpose=report_sharing` al cittadino prima del `report`".
- Priorità secondo me: **P1**

### [~] P-francesco-18 (in deploy): rinnovo nello stesso need → stesso numero → nessun rinnovo e silenzio (GP-10)
- Journey: — (**da verificare**: il cittadino torna dal GP per il rinnovo con lo stesso `need_id`?) — ruolo: gp
- Codice: `20_gp.py:170` (`new_number = _rx(message.need_id, message.msg_id)`) con `10_shared.py` `_rx` (il numero dipende solo dal `need_id`); `20_gp.py:171-181` (controlli `_we`).
- Cosa fa il cittadino: con P1 attiva, `need.request prescription_number=prescription_number-N-…` al GP.
- Cosa risponde oggi il nostro agente: se il `need_id` è quello della prima ricetta, `new_number` = vecchio numero; `_we` trova già `prescribe` e `prescription` → nessun `prescribe` al Ledger e `return` **muto**.
- Review / punti persi: ricetta scaduta mai rinnovata → booking −1 (regola ignorata) o nessuna prenotazione; review −1.
- Cosa dovrebbe fare: numero del rinnovo diverso dal vecchio (per esempio suffisso `-R1`, `-R2` contando i rinnovi nella storia); se resta uguale, mai silenzio.
- Test a parole: "storia con `prescribe … prescription_number=prescription_number-N-1` e messaggio del cittadino con quel numero nello stesso need → mi aspetto un `prescribe … renewal_of=prescription_number-N-1` con un numero nuovo".
- Priorità secondo me: **P1 se P1 è attiva**, altrimenti P2

### [~] P-francesco-19 (in deploy): red flag nascosta accanto a una parola nota → ricetta invece del 112 (GP-03)
- Journey: — (livello 8, "red flag nascoste") — ruolo: gp
- Codice: `20_gp.py:200-204`: se `_symptom` trova una parola nota ("schiena", "ginocchio"), il modello (che sa riconoscere `RED_FLAG`) non viene chiamato.
- Cosa fa il cittadino: "Ho mal di schiena e da ieri non sento più le gambe" (non contiene la frase fissa "perdita di forza alle gambe").
- Cosa risponde oggi il nostro agente: `prescribe … VIS-FIS B` e ricetta.
- Review / punti persi: "Red flag senza escalation" **−2** (primo agente).
- Cosa dovrebbe fare: chiedere al modello solo "red flag sì/no" anche quando la parola nota c'è (con il ripiego attuale se il modello non risponde); oppure ampliare le frasi fisse per sintomo (SYM-BACK: gambe deboli/che non si muovono/formicolio, controllo di vescica; SYM-PALPITATIONS: dolore/peso al petto, svenimento).
- Test a parole: "dato 'mal di schiena e non sento più le gambe' e il modello che risponde RED_FLAG, mi aspetto `escalate.emergency` e nessun `prescribe`".
- Priorità secondo me: **P1**

### [~] P-francesco-20 (in deploy): consenso cross-ASST: "non" in qualsiasi frase = rifiuto
- Journey: — (livello 4) — ruolo: booking_centre
- Codice: `30_booking.py:315` (`if any(word in lowered.split() for word in {"no", "non", "rifiuto", "rifiutato"})`).
- Cosa fa il cittadino: dopo `consent purpose=cross_asst`, risponde "Va bene, non ho problemi" o "Sì, non c'è problema".
- Cosa risponde oggi il nostro agente: lo legge come rifiuto → niente ricerca nelle altre ASST → lista d'attesa.
- Review / punti persi: con S non vuoto nell'ASST partner (livello 4) **−1**.
- Cosa dovrebbe fare: consenso = `consent_ref=` presente; rifiuto = `consent` senza ref o parole di rifiuto chiare all'inizio ("no", "non voglio", "rifiuto", "preferisco di no"); se ambiguo, una domanda.
- Test a parole: "dato 'sì, non ho problemi' dopo la richiesta cross_asst, mi aspetto che la ricerca parta (o una domanda), non la lista d'attesa".
- Priorità secondo me: **P1** dal livello 4

### [~] P-francesco-21 (in deploy): richiesta di consenso del booking senza `purpose=` e con un riferimento inventato
- Journey: — (**da verificare**: risposta del cittadino a `consent consent_required=true …`) — ruolo: booking_centre (e consultorio)
- Codice: `30_booking.py:919-928`: `consent consent_required=true offer_id=… slot_id=… consent_ref_required=cons-<need>-booking`.
- Cosa fa il cittadino: conferma un'offerta senza `consent_ref`.
- Cosa risponde oggi il nostro agente: chiede il consenso **senza** `purpose=` e propone lui il riferimento.
- Review / punti persi: e19: "il cittadino risponde solo per gli scopi che accetta" (`consent purpose=…`); senza `purpose` può non rispondere → prenotazione bloccata (−1). Riferimento inventato = identificativo indovinato.
- Cosa dovrebbe fare: `consent purpose=booking offer_id=… slot_id=…` + frase; il `consent_ref` lo dà il cittadino.
- Test a parole: "dato `confirm offer_id=of-S1` senza `consent_ref`, mi aspetto `consent purpose=booking offer_id=of-S1 …` senza `consent_ref_required`".
- Priorità secondo me: **P1**

### [~] P-francesco-22 (in deploy): ricevuta doppia al cittadino (Journey 000123)
- Journey: 000123 — ruolo: booking_centre + strutture
- Codice: `40_facility.py:269-283` (`_on_committed` chiamato sia nel turno del confirm, `_finish_booking`, sia nel turno della riga `committed`; nessun lock, controllo `_we` su storia vecchia); `30_booking.py:969` (`_forward_receipt` senza lock); `40_facility.py:277` (se la struttura non trova il `confirm` nella storia manda la ricevuta **direttamente** al cittadino, e il booking la gira di nuovo).
- Cosa fa il cittadino: niente (succede dopo il commit).
- Cosa risponde oggi il nostro agente: due `booking.receipt` con lo stesso `booking_id`.
- Review / punti persi: cittadino confuso (review −1); nessun punto di rubrica diretto.
- Cosa dovrebbe fare: un turno alla volta per need sulla ricevuta (come `_CHECKIN_GATES`) e ricontrollo della storia dentro il lock; la struttura manda la ricevuta al cittadino solo se nessun booking ha chiesto la prenotazione.
- Test a parole: "due turni `committed booking_id=B1` quasi insieme → una sola `booking.receipt` al booking e una sola al cittadino".
- Priorità secondo me: **P2**

### [~] P-francesco-23 (in deploy): la lista d'attesa promette un ricontatto che nessuno fa
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
