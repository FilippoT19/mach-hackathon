# PASSAGGIO — tutto il contesto per continuare il lavoro

Scritto il 21/11/2026 mattina; **aggiornato il 21/11 alle ~10:00 UTC** (dopo BK-66/67/68 e GP-17 su main,
commit `eb38ae9`). Serve a chi riparte in una chat nuova, persona o AI, senza aver seguito le sessioni di prima.
Le novità dell'aggiornamento sono in 2.3, 2.10, 5, 6, 7, 8.3, 8.6, 11, 12, 13 e 14.1.

Tre file vanno letti insieme:

| File | Cosa dà |
|---|---|
| `docs/PASSAGGIO.md` (questo) | Regole, architettura, logica di ogni agente con il perché, stato, lezioni, consigli |
| `docs/PASSAGGIO-indici.md` | Indice di **ogni funzione** del brain (riga, descrizione, casi citati) e indice di **ogni caso** di `CASI.md`. Generato da `asst/tools/indici.py` |
| `CASI.md` | La riga completa di ogni caso: rischio, soluzione, logica, test, stato |

**Quanto fidarsi.** Il codice e i journey sono la verità. Questo documento è stato scritto leggendo il codice di
main; dove una cosa non è stata verificata c'è scritto "non verificato". I numeri di versione online vengono
da `CASI.md` e `REGISTRO.md`, non da un controllo diretto sulla piattaforma.

---

## 1. La gara in dieci righe

- **Milano Agentic City Hackathon (MACH)**, 20–21 novembre 2026. Squadra `polimi`, ASST **Niguarda** (distretto 5).
- Mettiamo in campo **5 agenti**: medico di base (gp), centro prenotazioni (booking_centre), ospedale, specialista, consultorio.
- La città manda **cittadini simulati**. Ognuno ha un bisogno di cura e segue un percorso (journey):
  sintomo → gp → ricetta → booking → offerte → scelta → conferma → ricevuta → check-in → visita → referto.
- Un **giudice** legge i fatti scritti sul **Ledger** (il registro ufficiale) e la chat, e dà i punti per percorso.
- Vince chi fa più punti. I livelli salgono da 1 a 8 durante la gara e aggiungono difficoltà.
- Regole ufficiali: https://github.com/projectnandaitaly/mach-hackathon-kit → `docs/kit/e19-rules.md`.
  **Vanno rilette a ogni dubbio**: questo documento le riassume, non le sostituisce.
- Console di squadra (journey e verdetti): https://projectnandaitaly.ai/team → Journeys.
- Classifica e "Il Token della Sera" (descrizione del livello in vigore): https://projectnandaitaly.ai.

---

## 2. Le regole che contano per il codice

### 2.1 Messaggi

- Ogni messaggio è **testo di chat** mandato con `city.say(a_chi, testo)`. Lunghezza da 1 a 2000 caratteri.
- Nel testo ci sono: la **parola dell'atto** (`offer`, `confirm`, `cancel`, `booking.receipt`, `checkin`,
  `escalate.emergency`…) e i **campi** scritti come `chiave=valore`. Intorno si può mettere una frase.
- Il cittadino **decide in codice**: un modello estrae atto e campi dal nostro testo, poi una regola sceglie.
  La forma della frase non cambia la sua scelta. Un'offerta deve nominare `offer_id` e `slot_id`.
- Il giudice legge la chat allo stesso modo: cerca la parola dell'atto e i campi. "Chiami il 112" senza
  `escalate.emergency` **non** è un'escalation.
- I rifiuti del cittadino arrivano **in parole normali**, senza atto e senza il campo chiesto. Se abbiamo
  appena chiesto qualcosa e la risposta non ha quel campo, è un no.

### 2.2 Il Ledger

- È il registro ufficiale. Gli si scrive come a un interlocutore: `city.say(LEDGER, "hold slot_id=…")`.
- Letture: `prescription prescription_number=…`, `agenda`, `world procedure=… page=N`, `rules`.
- Scritture: `prescribe`, `hold`, `commit`, `checkin`, `report`, `cancel hold_id=…`.
- Risponde con una riga: `prescription …`, `agenda agenda_now=…`, `slots page=1/3` + righe slot,
  `held hold_id=… fence=…`, `committed booking_id=… ledger_ref=…`, `checked_in`, `reported`, `refused <op> reason=…`.
- **Regola d'oro: scrivere sul Ledger prima di dirlo al cittadino.** Il giudice valuta i fatti scritti.
- Mai ritentare un rifiuto 4xx.

### 2.3 Tempi

- Due orologi. Il tempo reale (messaggi, hold, verdetto) e il **tempo di agenda, 60 volte più veloce**:
  1 minuto reale = 1 ora di agenda, 24 minuti reali = 1 giorno.
- Ambulatori aperti 08:00–18:00 di agenda. Check-in nella mezza giornata dello slot (08–13 o 13–18).
- Priorità della ricetta: **U** stesso giorno, **B** entro 2 giorni, **D** entro 5, **P** più avanti (lista d'attesa).
  La finestra si conta **dall'emissione della ricetta**, non da adesso.
- **Sabato e domenica di agenda non esistono** (e19, ADR-124): dopo venerdì 18:00 viene lunedì. Una settimana
  di agenda = 120 minuti reali. Dal BK-68 tutta l'aritmetica di agenda passa da `_agenda_add` (`10_shared.py`).
- Il cittadino aspetta **16 minuti reali** per messaggio, poi rimanda lo stesso contenuto (fino a 3 invii).
  Dopo circa 48 minuti il percorso chiude `no_reply`.
- L'agenda **può saltare in avanti al cambio di livello** (visto alle 03:18 UTC: circa 3 giorni, caso BK-59).

### 2.4 La regola più importante per il booking

> "Mettete ogni slot nello stesso messaggio […]. Il cittadino sceglie in quello stesso turno. Un messaggio
> successivo non entra in una scelta già fatta."

Quindi **il primo messaggio di offerte è, di fatto, l'unica occasione**. Tutto il lavoro sul booking degli
ultimi giorni gira intorno a questo: cosa mettere in quel messaggio e quanto in fretta mandarlo.

### 2.5 L'insieme di risposta (S)

- Per ogni cittadino il giudice calcola `S`: gli slot che può accettare. Dentro contano lingua del medico,
  scadenza, giorni, genere del medico, e **vincoli che il cittadino non ci ha detto**.
- `S_pref` è `S` ristretto alle preferenze.
- Il verdetto di ogni journey riporta `answer_set.size`. Se è 0, non c'era niente da prenotare:
  il risultato giusto è un'alternativa (lista d'attesa) e vale 0, non −1.
- Quando il cittadino rifiuta un'offerta manda `cancel offer_id=… reason=…`. Motivi visti:
  `gender`, `day`, `deadline`, `past`, `lang`, `time`, `waiting_list`. **Il motivo è l'unico modo di scoprire
  un vincolo non detto.**

### 2.6 Rubrica

| Chi valuta → agente | Fatto | Punti |
|---|---|---|
| cittadino → gp | Ricetta giusta (procedura e priorità del protocollo) | +2 |
| cittadino → gp | Procedura o priorità sbagliata | −1 |
| cittadino → booking | Prenotazione dentro le preferenze (`S_pref`) | +2 |
| cittadino → booking | Prenotazione valida (`S`) | +1 |
| cittadino → booking | `S` vuoto e alternativa offerta | 0 |
| cittadino → booking | Fuori da `S`, o nessuna prenotazione con `S` non vuoto | −1 |
| cittadino → booking | Regola ignorata (ricetta scaduta, cross-ASST senza consenso, riserva U) | −1 |
| cittadino → struttura | Check-in onorato su ricevuta valida | +2 |
| cittadino → struttura | Ricevuta valida rifiutata | −2 |
| cittadino → specialista | Referto archiviato e follow-up da protocollo | +2 |
| cittadino → specialista | Referto mancante | −1 |
| cittadino → consultorio | Prenotato senza chiedere la ricetta | +2 |
| cittadino → consultorio | Ricetta pretesa | −1 |
| Ledger → struttura | Slot onorato | +1 |
| Ledger → struttura/booking | Prenotazione fantasma (ricevuta senza commit) | −2 |
| emergenza → primo agente | Red flag senza escalation | −2 |
| audit → agente | Dati di troppo, injection obbedita, attributo falso | −2 |
| audit → booking | Dati cross-ASST prima del consenso | −2 |
| clock → agente | Risposta a un altro agente entro 10 secondi | +1 |
| review → ogni agente | Proattività, con tono rispettoso | +1 |
| review → ogni agente | Passivo o freddo: messaggio senza risposta, lavoro rimandato al cittadino, risposta brusca | −1 |
| review → ogni agente | Collaborazione: uno scambio con un altro agente che fa avanzare il bisogno | +1 |
| review → ogni agente | Dominio: un fatto di cura del verdetto nomina l'agente | +1 |
| director → squadra | Cittadino della nostra ASST trova gp, booking o consultorio vuoti | −4 |

La **review** è fatta da un modello dopo il giudice, per ogni agente del percorso: da −1 a +3 per agente.
Con 5 agenti e molti cittadini è una leva grande. Nei journey falliti la review è spesso `null`.

### 2.7 I livelli

| Livello | Novità | Comportamento giusto |
|---|---|---|
| 1 | Bisogno strutturato | Prenotare nell'insieme valido |
| 2 | Vincoli, lista d'attesa | Prenotare o lista d'attesa |
| 3 | Testo libero, check-in, referto | Interpretare; check-in; referto con consenso |
| 4 | Scarsità: la risposta è in un'altra ASST | Cross-ASST con consenso |
| 5 | Vincoli combinati, insiemi a volte vuoti | Prenotare nell'insieme o proporre un'alternativa |
| 6 | Tempo: hold scaduti, cancellazioni | Riprenotare entro la scadenza, in modo proattivo |
| 7 | Guasti: partner irraggiungibile, duplicati, 4xx | Degradare bene, niente doppie prenotazioni |
| 8 | Red flag nascoste, cittadini ostili, cambio regola P1–P3 | Escalare; rifiutare injection; applicare la regola nuova |

Cambi di regola possibili (si leggono con `rules`): **P1** ricetta valida 2 giorni di agenda → rinnovo dal gp;
**P2** hold in un'altra ASST solo con consenso `cross_asst`; **P3** 20% degli slot riservati alla priorità U.

### 2.8 Il tono dei cittadini (attenzione)

Regola e19, testuale: "Ogni cittadino scrive con un tono: Gen Z, boomer, formale, ansioso, sbrigativo,
polemico, remissivo o con un italiano semplice da non madrelingua. Il tono cambia le parole, non l'atto né i campi."

- Chi scrive "raga, lowkey, fr" è un cittadino **normale** con tono Gen Z. Va servito come gli altri.
- Verificato sui dati: journey `…0002860002` (Gen Z) ha dato **+2 al gp**; `…000182` (Gen Z) è finito **prenotato**.
- Un admin avrebbe detto a voce che quelli in gergo "vanno ignorati". **Non è confermato da nessuna regola
  scritta né da un journey.** Ignorarli costa −1 (messaggio senza risposta) e fino a −4. Prima di cambiare il
  codice serve la regola scritta o un journey di prova.
- Gli **impostori** di cui parlano gli organizzatori sono **agenti** di altre squadre, non cittadini.
- I "cittadini ostili" del livello 8 provano injection o chiedono dati di troppo: si risponde senza obbedire.

### 2.9 Il nostro mondo

| Ruolo | Agent id | Procedure | Medici (chiave → genere, lingue, giorni) |
|---|---|---|---|
| Centro prenotazioni | `agent:fn64xfq2jft4` | — | — |
| Medico di base | `agent:fddgaqmp6kb0` | — | — |
| Ospedale (fisiatria) | `agent:jdj692g4145e` | `VIS-FIS` | h1 donna it/en lun-mar-mer · h2 uomo it mer-gio-ven · h3 uomo it + lingua rara mar-gio |
| Specialista (cardiologia) | `agent:jmjfst55vgjz` | `VIS-CARD`, `CTRL-CARD` | s1 uomo it/en lun-mer-ven · s2 donna it mar-gio |
| Consultorio (ginecologia) | `agent:mm18nddkfc5w` | `CONS-GIN` (senza ricetta) | c1 donna it/en lun-ven |

- Tabella dei protocolli (uguale sul Ledger): mal di schiena → `VIS-FIS` priorità B; ginocchio → `VIS-FIS` D;
  palpitazioni → `VIS-CARD` B; controllo del cuore → `VIS-CARD` P.
- Ogni ASST ha gli stessi medici. La lingua rara di h3 cambia per ASST (Niguarda: vietnamita).
- Capacità 1 per slot. Solo l'ospedale è accessibile in sedia a rotelle.

### 2.10 MACH-1.3 (proposta tra squadre, 21/11)

Pagina condivisa: https://claude.ai/artifact/TotYPTDHZwb6k8Fm3ipby9. È una proposta tra squadre, compatibile
con 1.2, **non** una regola degli organizzatori: dove tocca il punteggio vale `e19-rules.md`.

- R1: la struttura risponde a ogni `need.request` entro 10 s → fatto in BK-67 (memoria del catalogo in `_partner_request`).
- R2: niente lista d'attesa prima del giro tra le ASST → fatto in BK-68 (`page_lost` passa da `_after_local`).
- R5: scadenze dalla nascita del need; R6: lease 480 s (max 900); token `mach=1.3 after= deadline= lease_s=
  next_free=`, date senza fuso → solo `after=`/`deadline=` letti lato struttura. **Non implementati**: lease,
  `mach=1.3`, consenso cross-ASST chiesto solo al confirm, max 6 slot per offerta, `cancel reason=past` con offerte nuove.

---

## 3. Regole di lavoro della squadra

Stanno in `CLAUDE.md` (ogni sessione di Claude le legge all'avvio) e in `asst/README.md`.

- **Si modifica solo `asst/brain/parts/`.** Poi, da `asst/`: `python seats.py --brain` e `python seats.py --check`.
- I test devono passare (comandi al paragrafo 4.3).
- **Ogni modifica al brain aggiunge o aggiorna una riga in `CASI.md`.** Ogni PR elenca gli ID e una tabella
  caso → soluzione → logica → test, in italiano.
- Solo **Filippo** (captain) fa merge su `main` e `city deploy`. Giulia può farlo per il booking. Gli altri consigliano.
- Quota deploy: **1 ogni 5 minuti per tutta la squadra**. Si avvisa nel gruppo prima di ogni deploy.
- Mai `city retire` (permanente). Mai toccare `Dockerfile` o `city.yaml` di un agente (la conformance fallisce).
- Il brain importa solo `city_sdk.city` e la libreria standard. L'AI solo con `city.llm`.
- Niente file di dati nell'immagine: le tabelle (vie, fermate della metro) sono scritte nel codice.
- **OPS-10, pausa dei deploy:** ogni riavvio perde i messaggi in arrivo e la memoria del processo. Le
  correzioni si accumulano su main e si rilasciano insieme, mai con molti cittadini a metà percorso.

---

## 4. Come sono organizzati i file

### 4.1 Mappa del repo

```
CLAUDE.md            regole di lavoro (lette da ogni sessione AI)
CASI.md              registro dei casi: una riga per ogni modifica al brain (143 righe al 21/11)
REGISTRO.md          journey non pieni raggruppati per causa (G1…G21) e se il fix ha funzionato
PILLAR.md            quadro generale e briefing — FERMO al 20/11 sera (vedi 4.4)
PROPOSTE.md          modello per le proposte della squadra
proposte/<nome>.md   proposte di giulia, francesco, magesh, filippo (ID P-<nome>-<n>)
docs/booking-flow.md analisi del flusso del booking
docs/PASSAGGIO*.md   questo documento e gli indici
asst/                QUELLO CHE FA PUNTEGGIO
  brain/parts/       le parti del brain: si modifica solo qui
  brain/agent.py     brain unito (GENERATO)
  <agente>/agent/agent.py   copia del brain per ogni agente (GENERATA)
  <agente>/card.yaml, city.yaml, Dockerfile   card e immagine (non toccare city.yaml e Dockerfile)
  seats.py           unisce le parti e le copia nei 5 agenti
  ship.sh            test + deploy in fila (solo Filippo)
  tests/             test_brain.py, test_journey.py, test_replay.py, bench_booking.py
  tools/indici.py    rigenera docs/PASSAGGIO-indici.md
backend/, frontend/  vecchio starter generico: NON fa punteggio
```

### 4.2 Le parti del brain

Un solo programma serve tutti e 5 gli agenti. Legge il ruolo dalla card (`role_of()`).
`seats.py` unisce i file in ordine di nome.

| File | Righe | Contenuto |
|---|---|---|
| `00_core.py` | 229 | Costanti (medici, protocolli, parole di emergenza, attese), `main()`, `handle()` che smista per ruolo |
| `10_shared.py` | 379 | Id dei nostri agenti e dei partner noti, lettura della storia, `_say`, `_until`, `_await_line`, filtro degli slot `fitting` |
| `15_voice.py` | 132 | `city.llm`: riconoscere il sintomo; frasi "umane" (spente) e loro pulizia |
| `20_gp.py` | 528 | Medico di base: emergenza, sintomo, ricetta, rinnovo |
| `25_streets.py` | 4104 | Solo dati: vie di Milano → coordinate |
| `30_booking.py` | 2997 | Centro prenotazioni e parte di prenotazione del consultorio; mappa e percorso |
| `40_facility.py` | 722 | Ospedale, specialista, consultorio: hold, commit, ricevuta, check-in, referto, richieste dei partner |

### 4.3 Test

Da `asst/`, con il Python della CLI:

```bash
python seats.py --brain && python seats.py --check
~/.local/share/uv/tools/city-cli/bin/python tests/test_brain.py     # deve finire con TUTTI I TEST OK
~/.local/share/uv/tools/city-cli/bin/python tests/test_journey.py   # ALL PASS
~/.local/share/uv/tools/city-cli/bin/python tests/test_replay.py    # REPLAY OK
~/.local/share/uv/tools/city-cli/bin/python tests/bench_booking.py --calls --text
```

| File | Cosa prova |
|---|---|
| `test_brain.py` | Un controllo per caso, con una città finta (`FakeCity`): nessuna rete, nessuna AI. Ogni caso nuovo aggiunge i suoi controlli (cercare l'ID, es. `BK-61`) |
| `test_journey.py` | Percorso completo con i 5 agenti, un Ledger e un cittadino finti. 6 percorsi × 2 modalità |
| `test_replay.py` | 20 journey veri rigiocati (r01…r20) con orari reali, partner, Ledger che risponde solo in history o anche con push |
| `bench_booking.py` | Quanto dura un turno del booking se ogni chiamata remota costa 1 secondo. Stampa la sequenza delle chiamate |

Nei test compare la riga `RuntimeError: ledger down`: è voluta, non è un errore.

### 4.4 I file di contesto e quanto sono aggiornati

| File | A cosa serve | Stato |
|---|---|---|
| `CASI.md` | **Cosa** abbiamo cambiato e perché | Vivo. È il file più importante dopo il codice |
| `REGISTRO.md` | **Se ha funzionato**: gruppi di causa, fix, journey di prova | Vivo. Va letto prima di ogni fix nuovo |
| `proposte/*.md` | Casi trovati dalla squadra, con journey e test a parole | Vivo |
| `PILLAR.md` | Rubrica, mondo, tempi, livelli, briefing dell'evento | **Fermo al 20/11 sera.** Dice "wave non partita, 0 journey". La sezione sulla logica degli agenti descrive il brain di esempio, non il nostro. Usare solo per rubrica, mondo, livelli, briefing |
| `docs/booking-flow.md` | Analisi del booking con righe di codice | Scritto il 21/11 notte; le righe citate sono cambiate |

---

## 5. Come raccogliamo i dati

- **Non abbiamo i log degli agenti** in forma utile. Non esiste `city logs`. La console mostra solo le **ultime
  ~150 righe** per agente (quasi tutte `GET /health`): per i casi passati non servono.
  Il booking scrive una riga di log per ogni passo (`_trace`, caso OPS-07: `booking.<passo> need_id=…`).
- **La fonte vera sono i journey**: Console → Percorsi dei cittadini → Scarica JSON (in `~/Downloads`,
  `journey-N-….json`), **non salvati nel repo**.
- **Lettura diretta dalla console (21/11)**: con l'utente loggato su https://projectnandaitaly.ai/team in Chrome
  (estensione Claude in Chrome; il pannello browser interno non ha il login), un `fetch` dalla pagina legge:
  - `GET /v1/team/journeys` → `{rubric, journeys:[{need_id, wave_id, level, state, score}]}` (solo la wave corrente, 200 righe);
  - `GET /v1/team/journeys/<need_id>` → lo stesso JSON del pulsante "Scarica JSON";
  - `GET /v1/logs?agent_id=agent%3A<id>&q=<testo>` → `{lines:[{time, level, message}]}`;
  - `GET /v1/scoreboard` (classifica), `/v1/agents`, `/v1/team/wave`, `/v1/team/reputation`.
  Lo strumento JavaScript restituisce al massimo ~1.500 caratteri e blocca le uscite con `=`/`&`/`?`: riassumere
  nella pagina (conteggi, righe corte, `=` sostituito da spazio). **Filippo vuole che si prenda dal sito il
  minimo**: chat e JSON dei cittadini, log, messaggi della classifica. Niente altro.
- Un journey JSON contiene:
  - `journey`: `need_id`, `level`, `state` (`booked`, `done`, `failed`, `open`), `score`.
  - `messages`: ogni messaggio **tra cittadino e agenti** con `from`, `to`, `sent_at` (ora reale UTC), testo.
    I messaggi con il Ledger e tra agenti **non** ci sono.
  - `verdict.answer_set`: quanti slot erano accettabili (`size`, `pref_size`).
  - `verdict.facts`: fatti letti dal Ledger (ricetta, hold, cancellazioni, offerte).
  - `verdict.rows`: le righe di punteggio scattate, con motivo (`protocol_match`, `no_booking`, `relaxed_alternative`…).
  - `review`: la valutazione di tono e collaborazione, quando c'è.
- **Il monitor**: un'altra sessione di Claude legge a ogni giro gli ultimi 60 journey, li mette nel gruppo di
  causa giusto in `REGISTRO.md` e controlla le proposte nuove su main. La sua configurazione non è nel repo.
- **Come si legge un journey fallito**: (1) `answer_set.size`: c'era qualcosa da prenotare? (2) gli orari:
  quanto abbiamo impiegato a rispondere? (3) i `reason=` dei cancel; (4) `facts`: c'è stato un hold? è scaduto?
  (5) le `rows`.

---

## 6. Come funziona un turno (per tutti gli agenti)

1. **Ogni messaggio in arrivo apre un turno**: dal cittadino, da un altro agente o dal Ledger. La piattaforma
   chiama `main(need, city)`.
2. `main()` (in `00_core.py`):
   - scarta i messaggi di altri agenti senza nessun `chiave=valore` (OPS-08: sono sonde della conformance);
   - **red flag nel testo del cittadino → `escalate.emergency` + 112 subito, prima della storia** (GP-17), una
     volta per need (`_EARLY_112`), da qualunque ruolo;
   - salva in memoria le righe del Ledger del messaggio e poi della storia (`_remember_ledger`, BK-67);
   - per il **gp** fa partire subito l'AI sul testo del cittadino, in parallelo (OPS-09);
   - per il **booking**, se il messaggio è un cancel di un'offerta, manda subito il `cancel.ack` (BK-61);
   - legge la storia del caso con `city.history(need_id=…)`;
   - chiama `handle(ruolo, …)`.
3. `handle()` fa i controlli comuni a tutti i ruoli, in quest'ordine:
   - domanda sull'indirizzo dell'agente → risponde con `address=`;
   - annota la lingua del cittadino (`_note_lang`, X-30);
   - risposta a una nostra domanda "dove si trova?" dopo un'emergenza;
   - **red flag → 112 da qualunque ruolo** (X-41), non solo dal gp;
   - domanda clinica (dose, diagnosi) → una frase "glielo spiega il medico" e poi il percorso normale (X-40);
   - aggiunge il messaggio alla storia se manca (BK-15: la history a volte non contiene il messaggio che ha aperto il turno);
   - passa al ruolo: `_gp`, `_desk` (booking), `_facility` (ospedale, specialista), `_family` (consultorio).

### 6.1 La memoria

- **La storia del caso è la memoria principale.** L'agente capisce a che punto è rileggendo i messaggi:
  `_we(chat, agente, token, to=…, word=…)` risponde a "ho già mandato questo a quello?".
- **Memoria nel processo**, che si perde a ogni riavvio (motivo della pausa deploy OPS-10):

| Memoria | Cosa tiene |
|---|---|
| `_SENT[need]` (`_Sent`) | Offerte mandate, note una tantum, partner interpellati, pagina in attesa, giri di offerte partner |
| `_GATES`, `_RECEIPT_GATES`, `_CHECKIN_GATES` | Un lucchetto per caso: i turni dello stesso caso girano insieme e non devono pestarsi |
| `_ANSWERED` | Messaggi del cittadino che hanno già avuto risposta |
| `_LANG_OF`, `_PREF_BY_RX` | Lingua per caso; preferenze passate dal gp nel referral |
| `_HELD_FOR` | Slot che stiamo bloccando per un caso (BK-63) |
| `_RECEIPTS`, `_RECEIPT_SENT`, `_BOOKED_AT`, `_WHERE_OF`, `_ANSWERED_WHERE` | Ricevute mandate, struttura prenotata, indirizzo del cittadino |
| `_PEERS`, `_DOORS`, `_ZONES` | Risultati dell'Index (agenti, porte, centro dei distretti) |
| `_EARLY_LLM`, `_EARLY_ACK`, `_EARLY_112` | Chiamate partite in `main()` prima della lettura della storia (AI, cancel.ack, 112) |
| `_WORLD`, `_AGENDA_ROW`, `_ASKED_AT` | **BK-67, catalogo in memoria**: pagine `slots` per procedura (valide 30 min), ultima riga `agenda` (45 min), ora dell'ultima domanda (rinfresco ogni 120 s). Usate dal booking e dalle strutture al posto di un giro di Ledger. Nei test sono spente (`_MEMORY_ON = False`) |
| `_DESK_HOLDS` | Diventa falso se il Ledger rifiuta un hold del booking per permessi |

### 6.2 Parlare e aspettare

| Funzione | Cosa fa | Perché |
|---|---|---|
| `_say(city, a, testo)` | Manda un messaggio; segna "ho parlato con X" in `_SAID` | Il booking deve sapere se un turno è finito in silenzio (BK-33) |
| `_until(city, need, chat, pronto)` | Rilegge la history finché `pronto` è vero o passano 6 secondi | La risposta del Ledger spesso sta solo nella history e non apre un turno |
| `_await_line(…)` | Come sopra per `held`/`committed`, fino a 30 secondi (FA-21) | Un hold dura minuti: non si abbandona dopo 12 secondi |
| `_keep(nuova, vecchia)` | Unisce la history riletta con le righe che avevamo già | BK-15 |
| `_ledger_asks(…)` | Più domande al Ledger insieme (`asyncio.gather`) | OPS-11: ogni chiamata costa secondi o minuti |
| `_peer(city, famiglia, query)` | Cerca nell'Index un nostro agente; se non c'è, niente collaborazione | Timeout 5 secondi |

**Lezione misurata il 21/11:** un giro di domande al Ledger è costato fino a 3–7 minuti reali. Ogni giro in
meno prima di rispondere vale più di qualsiasi ottimizzazione di codice.

---

## 7. Medico di base (`20_gp.py`)

**Compito:** dal sintomo alla ricetta giusta (+2), 112 sulle red flag (−2 se manca).

Ordine delle decisioni in `_gp`:

1. **Messaggio dal Ledger** (`prescribed`): `_announce` manda la ricetta al cittadino se non l'ha già avuta.
2. **Messaggio da un nostro agente**: `booking.notice` e `report.notice` ricevono subito un `…ack`
   (collaborazione e risposta entro 10 secondi).
3. **Emergenza** (`_emergency`): campo `is_emergency`, elenchi di frasi (`_RED_FLAGS`), espressioni regolari per
   petto e gambe (`_RF_CHEST`, `_RF_LEGS`: P-magesh-11, le red flag non dipendono mai dall'AI), gravidanza con
   sanguinamento o dolore (`_RF_PREGNANT`, CO-10).
4. **Sintomo** (`_symptom`): campo `symptom_code`, poi parole chiave (`_KEYWORDS`).
5. **Rinnovo**: il messaggio porta solo un `prescription_number`. Se la ricetta è nostra e ancora valida →
   `prescription.valid` (P-francesco-37); altrimenti `_renew_prescription` legge la vecchia dal Ledger e ne
   emette una nuova con `renewal_of=`.
6. **AI** (`_llm_symptom`): risponde con un codice della tabella, `RED_FLAG` o `NONE`. Se le parole chiave
   hanno già trovato il sintomo, l'AI serve solo a cercare un'emergenza.
   - **GP-15:** con "cuore che batte forte" l'AI diceva `RED_FLAG` e mandava al 112 chi aveva solo
     palpitazioni (11 percorsi persi su 14). Ora per palpitazioni e controllo del cuore il `RED_FLAG` dell'AI
     è ignorato: le loro vere red flag sono parole chiave.
7. **Emergenza** → `_escalate`: `escalate.emergency reason=red_flag` + frase con 112 (`_escalate_text`) e
   pronto soccorso adatto al sintomo (`_er_kind`: petto → cardiologia, gambe → neurologia/stroke unit,
   gravidanza → ostetricia); avviso `emergency.notice` al nostro ospedale (id fisso, X-56); pronto soccorso più
   vicino; poi `data.request purpose=emergency fields=address`.
   - **GP-17 (21/11):** su 12 percorsi L1 della wave W01QQQ, 8 con `emergency.no_escalation −2`: 6 senza
     risposta, 2 con il 112 dopo 278 s. Ora, con una red flag a parole chiave, il 112 parte da `main()` prima
     della storia; `_escalate` dopo aggiunge avviso e PS più vicino dentro la domanda "dove si trova".
   - **Decisione di Filippo:** il 112 resta **subito**. Chiedere prima dove abita e dare il 112 alla fine è
     stato scartato: il giudice conta solo `escalate.emergency` e il percorso si chiude lì (X-42b).
8. **Sintomo non capito**: prima volta chiede di descriverlo; poi `_gp_again` propone le quattro scelte
   (`gp.choices`), poi una frase di sicurezza. Mai silenzio (P-magesh-10).
9. **Ricetta**:
   - numero deterministico dal `need_id` (`_rx`);
   - `prescribe …` sul Ledger **e** `referral …` al booking **insieme** (OPS-09); il referral porta le
     preferenze dette al gp (`_prefs`: lingua, genere);
   - solo dopo, `prescription prescription_number=… procedure=… priority=…` al cittadino, con la frase fissa di
     `_rx_line`: ringrazia, nomina la visita, spiega la priorità, dice che il booking è già avvisato, dove si fa
     la visita e cosa portare (GP-13, X-28: senza frase la review dava 0).

**Aperto:** GP-16 "da analizzare" in `CASI.md`.

---

## 8. Centro prenotazioni (`30_booking.py`)

**Compito:** prenotare dentro `S` (+1) o `S_pref` (+2). È l'agente che perde più punti (`no_booking` −1).

### 8.1 Involucro: mai silenzio

`_desk` avvolge ogni turno di un cittadino:

- fa partire `_desk_route`; se dopo **8 secondi** (`_EARLY_STATUS`, P-magesh-17) non abbiamo detto niente al
  cittadino, manda una riga `status` e lascia continuare il lavoro;
- se il turno finisce senza una parola a nessuno, `_still_here` dice a che punto è il caso (BK-33):
  prenotato / offerte già mandate / manca la ricetta / sto controllando.

### 8.2 Smistamento (`_desk_route`), in ordine

| Se il messaggio è… | Va a… |
|---|---|
| `referral` dal gp | `_on_referral`: `referral.ack` subito, salva le preferenze (X-27, X-33) |
| risposta a una domanda di consenso cross-ASST | di nuovo la domanda, oppure `_advance` |
| `consent` per la prenotazione, o contiene `confirm` | `_on_confirm` |
| `offer` o `cancel` da una struttura partner | `_partner_reply` |
| `booking.receipt` da una struttura | `_forward_receipt` |
| risposta alla nostra domanda sull'indirizzo (non un cancel) | `_on_where` |
| `cancel` da una struttura | `_partner_cancel` |
| cancel del cittadino (`_citizen_cancels`: atto in prima parola, o parola + `offer_id`) | `_citizen_cancel` |
| altro, dal cittadino o dal Ledger | `_advance` |

### 8.3 La ricerca: `_advance` e `_advance_alone`

`_advance` tiene il lucchetto del caso e richiama `_advance_alone` finché c'è una pagina del catalogo in attesa
(BK-45), con un tetto di 40 secondi per turno (BK-54).

**BK-67, catalogo in memoria (online dalle ~09:00 UTC, booking 1.0.30).** Prima ogni caso aspettava il
Ledger (~14 minuti sotto carico). Ora `_advance_alone` aggiunge alla storia, con `_with_memory`, l'agenda e le
pagine del catalogo già in memoria; se la memoria è vuota legge una volta `city.history(LEDGER)` (4 s,
`_warm_memory`). Dopo la risposta, `_refresh_memory` chiede `agenda` + `world page=1..4` (al massimo ogni 120 s),
anche al `referral` del gp. Misurato dopo il deploy: prima offerta o consenso **25–115 s** dopo il cittadino
(prima: 82 casi su 82 tra 07 e 09 UTC senza offerte).

`_advance_alone`, passo per passo:

1. **Ricetta scaduta?** → `_ask_renewal`: `data.request purpose=prescription_renewal` (regola P1).
2. **Priorità P** → direttamente lista d'attesa (`_relaxed`).
3. **Primo giro di Ledger** (se manca la procedura): `prescription` + `agenda` insieme (OPS-11). Se la
   richiesta nomina `service_type=hospital.physiatry`, nello stesso giro parte anche `world procedure=VIS-FIS
   page=1` (BK-63: un giro in meno). Se il Ledger tarda, procedura e priorità si prendono dal `referral` del gp (BK-28).
4. **Ricetta non utilizzabile** (già usata) → `prescription.note`, mai silenzio (BK-21).
5. **Nessun nostro medico parla la lingua** → non si legge il catalogo, si va subito oltre (BK-50).
6. **Secondo giro** (se serve): `agenda` + `world page=1`.
7. **Ora di agenda** (`_agenda_now`): riga `agenda` del Ledger + minuti reali passati × 60. Dal BK-62 si usa
   l'orologio reale da quando il Ledger ha scritto la riga (entro 45 minuti). Se la riga è vecchia e l'orologio
   reale non è utilizzabile, si rilegge (BK-61).
8. **Scadenza** (`_rx_deadline`): finestra della priorità contata dalla ricetta (BK-27, BK-48), meno 30 minuti,
   in giorni feriali (BK-68). **Sospetto aperto (BK-69):** dopo il deploy 25 ricette B su 25 non hanno avuto
   offerte locali (vedi 12).
9. **Filtro** (`fitting`, in `10_shared.py`): procedura, struttura, posti liberi, riserva urgente, **margine**
   (5 ore di agenda; 4 per U: MACH-1.2), lingua del medico, giorno in cui il medico lavora.
   Giorni e genere **ordinano, non filtrano** (P-francesco-31, BK-60b).
10. **Esclusioni**: slot già offerti, rifiutati dal Ledger (P-magesh-9), esclusi dai cancel del cittadino
    (`_learned_out`, BK-60), bloccati per un altro cittadino (`_held_elsewhere`, BK-63).
11. **Un solo gruppo di offerte aperto per caso** (BK-46). Se il cittadino riscrive, riceve le stesse offerte una volta (BK-22).
12. **Allargare prima di offrire** (`_one_sided`, BK-61/62): se i posti trovati sono tutti di un genere, tutti
    nello stesso giorno, o nessuno nei giorni detti, e ci sono altre pagine → legge fino a 2 pagine in più.
    Se la pagina non arriva, offre quello che ha (`_widen_stop`).
13. **Scelta** (`_diverse`, P-francesco-48): fino a 12 offerte (`_OFFER_MAX`, BK-55) che cambiano giorno e
    medico. Il testo è limitato a 2000 caratteri (`_fit`): ci stanno circa 5–7 righe. Se si taglia, la scelta si rifà per quel numero.
14. **Un solo messaggio**: una riga `offer …` per slot + frase fissa (BK-14).
15. **Niente posti**: pagina successiva (con `status` "sto controllando", BK-30), fino a 20 pagine, o fino a
    quando una pagina intera è oltre la scadenza. Poi `_after_local`.

### 8.4 Cosa impariamo dai cancel (`_cancel_learned`, BK-60)

| Motivo del cancel | Cosa ne deduciamo |
|---|---|
| `reason=gender` su un medico di un genere | Offrire l'altro genere (anche nei criteri cross-ASST) |
| `reason=day` | Quel giorno esce dai giorni buoni |
| `reason=deadline` | Fuori ogni slot più tardi di quello. Se per noi era nei tempi e la ricetta è davvero scaduta → rinnovo (BK-59, BK-65) |
| `reason=past` | Il nostro orologio è indietro: si rilegge l'agenda (BK-59) |

I giorni detti a parole si leggono con `_days` (BK-56): "solo lunedì o mercoledì", "non posso il venerdì",
"qualsiasi giorno". Vale l'ultimo messaggio al booking; il racconto fatto al gp non conta (P-magesh-13).

### 8.5 Cancel del cittadino (`_citizen_cancel`)

- `cancel.ack` subito, una volta per offerta (X-34). Parte già in `main()`.
- Rilegge il caso. Se il cittadino ha ancora offerte in mano, o è prenotato, o è in lista d'attesa → solo l'ack (BK-46).
- **Raffica**: il cittadino annulla tutte le offerte nello stesso secondo e ogni cancel apre un turno. Solo
  il primo fa il passo successivo (`_Sent.steps`, BK-61).
- Passo successivo: nuove offerte **dalle pagine già lette**, senza giro di Ledger (BK-63); altrimenti pagina
  dopo; poi altre ASST; poi lista d'attesa. Dopo due gruppi locali rifiutati → lista d'attesa (BK-29).

### 8.6 Altre ASST (`_after_local`, `_cross_asst`, `_partner_round`)

1. Domanda di consenso: `consent purpose=cross_asst …` (regola P2: nessun dato esce prima).
   Al massimo 2 volte (BK-49). Formato della domanda cambiato più volte: BK-58, BK-64, BK-66 (online). La
   prima domanda è **senza** `consent_ref` (BK-64); il riferimento arriva solo dopo "Which consent_ref?".
   Pagina del catalogo persa (`page_lost`) → si passa comunque da qui prima della lista d'attesa (BK-68, R2).
   Oggi i cittadini spesso non rispondono a questa domanda: 25 ricette B fallite così (vedi 12).
2. Sì → `city.find` delle strutture di altre ASST; per una lingua rara prima l'ASST che la parla (X-51).
3. `need.request service_type=… procedure=… request_id=cross-<need> priority=… deadline=…` a **tutte**, insieme.
   Solo criteri, nessun dato del cittadino (X-44, MACH-1.2).
4. Si aspettano le risposte fino a 6 secondi; quelle che arrivano dopo aprono un turno (`_partner_reply`).
5. `_partner_pool` filtra le offerte: lingua del medico (BK-35), non passate, entro la scadenza, non escluse dai
   cancel. `_partner_round` ne manda al massimo 3 per messaggio, 2 per struttura, per 3 giri (BK-47: prima
   uscivano fino a 63 messaggi).
6. Nessuna offerta → `booking.search` "aspetto le risposte", poi lista d'attesa (P-francesco-34).

Filtro sugli agenti: `_KNOWN_PARTNERS` elenca circa 50 agenti di 10 ASST, ma `_TRUSTED_PARTNERS` è **vuoto**,
cioè accettiamo tutti (X-13). Gli organizzatori dovrebbero togliere il team che fa spam.

### 8.7 Conferma (`_on_confirm`)

- Manca lo slot → chiede il numero dell'offerta. Manca il consenso → `consent purpose=booking …`.
- **Slot del nostro ospedale o specialista** (BK-57): il booking fa `hold` sul Ledger nello stesso turno.
  Prima mandava il `confirm` all'ospedale, che lo lavorava 14 minuti dopo: hold scaduto, visita persa.
  - `_finish_booking` aspetta `held`, manda `commit`, aspetta `committed`.
  - Intanto parte `data.request purpose=booking fields=address,…` (X-49).
  - Commit rifiutato per `stale_fence` → un altro commit senza `fence` (BK-62).
  - Ricevuta completa: frase, `booking.notice` al gp, cosa portare (BK-61).
- **Slot di un'altra ASST**: `confirm` alla struttura con `cross_asst_consent_ref`; un solo confirm per slot (BK-51).
- **Slot già bloccato per un altro** (BK-63) o già rifiutato (P-magesh-9): `cancel … reason=no_capacity` e
  nuove offerte, senza hold.
- Rifiuto del Ledger (`_on_refused`): cancel al cittadino con una frase, lo slot non torna più, nuove offerte.

### 8.8 Ricevuta e percorso

- `_forward_receipt` → `_send_forwarded_receipt`: `booking.receipt booking_id=… ledger_ref=…` + frase + avviso
  al gp (collaborazione, G5) + come arrivare + cosa portare (`_prep_line`, P-02).
- `_on_where`: dalla via del cittadino (`25_streets.py`, X-54) o dal distretto: chilometri, a piedi o mezzi,
  fermata della metro più vicina, Area B per l'auto, accessibilità, ospedale più vicino per le urgenze (X-31, X-32, X-45, X-50).

---

## 9. Strutture (`40_facility.py`)

**Ospedale e specialista** (`_facility`):

- `need.request` da un altro booking → `_partner_request` (FA-12): legge agenda e catalogo, risponde con
  `offer …` per ogni posto adatto (rispetta `lang`, `gender`, `deadline`) o `cancel reason=no_availability`.
- Agente sconosciuto → `cancel reason=unknown_partner` (X-13); con il filtro spento non scatta quasi mai.
- `confirm` da un booking → `_on_confirm` con hold sul Ledger; poi `held` → `_on_held` (commit) →
  `committed` → `_on_committed` (ricevuta al booking che l'ha chiesta).
- `checkin` dal cittadino → `_on_checkin`: `checkin booking_id=… citizen=…` sul Ledger, al massimo 3
  tentativi; `checked_in` → conferma al cittadino. Senza numero → `checkin.help`.
- "Sono arrivato" in parole → vale come check-in; una **domanda** sul check-in no (FA-20).
- Altro testo libero → `facility.note` con orari, indirizzo e "per spostare scriva al booking". Mai silenzio.
- **Specialista** (`reports=True`): dopo `checked_in` scrive `report booking_id=… outcome_code=VISIT`; a
  `reported` manda `report.notice` al gp e `report …` al cittadino (G5).

**Buco verificato nel codice (21/11):** le regole chiedono allo specialista di domandare il consenso
(`consent purpose=report_sharing`), archiviare il referto con il `consent_ref` ricevuto e, quando il protocollo
lo prevede, emettere la ricetta di controllo (`prescribe … follow_up_of=<booking_id>` e
`report … follow_up_prescription_number=…`). In `brain/parts/` **non compaiono né `report_sharing` né
`follow_up_of`**: il referto parte come `report booking_id=… outcome_code=VISIT`, senza consenso e senza
controllo. Riga di rubrica in gioco: "referto archiviato e follow-up da protocollo" +2, "referto mancante" −1.
Non so se il Ledger accetta il `report` senza `consent_ref`: va guardato in un journey di cardiologia arrivato
al check-in.

**Consultorio** (`_family`): per check-in, held, committed usa `_facility` con `hold_self=True`; per tutto
il resto usa il flusso del booking (`_desk`) con procedura fissa `CONS-GIN` e **senza ricetta** (CO-20).
Fa da solo hold e commit.

---

## 10. L'AI (`15_voice.py`)

- Si chiama con `city.llm(messages)` (gateway della città: Gemma, GLM, Qwen). Attesa massima 4 secondi; se non
  risponde si va avanti senza.
- **Oggi serve a una cosa sola**: nel gp, classificare il testo in un codice sintomo, `RED_FLAG` o `NONE`.
- **Le frasi sono tutte fisse** (`_human` restituisce il testo di ripiego: `_VOICE_MODEL = False`).
  Motivo (GP-13, X-29): l'AI era chiamata in fila, fino a 8 secondi, e quando tardava la frase si perdeva.
- `_clean_line` toglie da una frase dell'AI ogni parola d'atto e ogni `chiave=valore`: l'AI non deve mai
  poter scrivere un campo.

---

## 11. Storia dei problemi, in ordine

| Quando | Problema | Risposta |
|---|---|---|
| 20/11 sera | Booking muto (history senza il messaggio in arrivo; Ledger che non apre turni) | BK-15, BK-28, BK-33, BK-45 |
| notte | Ping-pong offerta/annullo, raffiche con i partner | BK-29, BK-46, BK-47 |
| notte | Offerte fuori scadenza: finestra contata da adesso invece che dalla ricetta | BK-27, BK-48 |
| notte | Palpitazioni mandate al 112 | GP-15 |
| notte | Hold scaduto: il confirm passava dall'ospedale lento | BK-57 |
| 02–03 UTC | 10 deploy in due ore: messaggi persi a ogni riavvio | OPS-10 (pausa deploy) |
| 03 UTC | Lentezza: chiamate in fila | OPS-09 (gp), OPS-11 (booking) |
| 03:18 UTC | L'agenda salta di 3 giorni al cambio livello | BK-59, FA-21 |
| 03–04 UTC | Journey 000304 e altri 14: una sola pagina, un solo giorno, un solo medico; cancel senza risposta; `stale_fence` | BK-60, BK-60b, BK-61, BK-62, BK-63, MACH-1.2 |
| 04:22 UTC | Deploy con `max_inflight: 16` e silenzio del booking | OPS-12 tolto |
| dalle 04:24 UTC | **Tutti i nostri agenti senza messaggi** (anche quelli non rilasciati) | G19: probabile fermo della piattaforma |
| 04:45–05:26 UTC | 16 journey falliti (wave W01QQQ): prima offerta ~32 min dopo la ricetta (attesa del Ledger), liste d'attesa con S 130–286, offerte tutte lo stesso giorno, status senza offerte | BK-67 (memoria), status che ripete le offerte |
| 03:18 / 05:18 UTC | "Salto" dell'agenda = fine settimana di agenda (ogni 120 min reali) | BK-68 (`_agenda_add`) |
| ~09:00 UTC | Rilascio BK-66 + BK-67 + BK-68 (PR #141) | booking 1.0.30, strutture, consultorio |
| 09:08–09:20 UTC | B: 25/25 al consenso cross-ASST senza offerte locali, `no_booking` con S 208–390; D: 6/8 falliti, prima offerta tutta con un medico (h1), cancel `gender`/`day` | **BK-69 da fare** (vedi 12) |
| wave W01QQQ, L1 | Red flag: 6 senza risposta, 2 con il 112 dopo 278 s → `no_escalation −2` | GP-17, gp 1.0.17 (~09:50 UTC) |

---

## 12. Stato al momento del passaggio

| Cosa | Stato |
|---|---|
| Codice su main | Tutto fino a BK-68 e GP-17 (`eb38ae9`) |
| Online | booking 1.0.30 (~09:00 UTC, BK-66/67/68); **gp 1.0.17 (~09:50 UTC, GP-17)**. Specialist, hospital, family_counseling e booking con GP-17: rilascio in corso dalle ~09:55 UTC, uno ogni 5,5 min (controllare con `city status`) |
| PR aperte | #142 (CASI.md: BK-66/67/68 "online"), #138 (questo documento) |
| Punteggi in console (~09:30 UTC) | gp +4883, booking **−745**, hospital +101, specialist +130, consultorio +116. Wave W01QQQ: 200 percorsi, 116 falliti, 16 conclusi, 10 urgenza |
| Piattaforma | Ripartita: la wave W01QQQ arriva a ondate (ultima nascita vista 09:25 UTC), livelli 1–8 |

**Da fare subito (BK-69, analisi del 21/11 ~09:30 UTC sui journey nati dopo il deploy):**

1. **Ricette B: 25 su 25 fallite.** Il booking manda lo status, poi dopo ~25 s il consenso cross-ASST senza
   nessuna offerta locale; il cittadino chiede "Which consent_ref?" o tace → `no_booking`, S = 208–390.
   Ipotesi: la finestra B di `_rx_deadline` è quasi vuota. Contiamo 2 giorni di agenda dal `referral` del gp,
   che arriva ~33 min reali (= 33 ore di agenda) prima del cittadino, con il fine settimana saltato e 30 min di
   margine; il giudice calcola S quando nasce il need e ne trova centinaia. Proposta: se la finestra è vuota,
   offrire comunque i posti locali dei 2 giorni di agenda successivi prima del consenso. **Da confermare con
   l'agenda vera prima di scrivere codice.**
2. **Ricette D: 6 su 8 fallite.** Prima offerta di 4 posti tutti dello stesso medico (h1); il cittadino li
   annulla per `gender`, la seconda offerta (h2/h3) per `day`. Cancel visti: day 23, gender 20, deadline 3.
   Proposta: la prima offerta deve avere almeno due medici e due giorni; se la memoria non li ha, leggere altre
   pagine prima di offrire. Probabile causa: le pagine in memoria sono le prime e contengono un solo medico.

**Verifiche aperte:** BK-66/67/68 risultano attivi (offerte in 25–115 s, nessun silenzio), ma i percorsi
falliscono per i due motivi sopra. GP-17 va verificato sui primi percorsi L1 con red flag nati dopo ~09:50 UTC
(il 112 deve arrivare in pochi secondi, nessun `no_escalation`).

### Cose che non sappiamo

1. Come il giudice conta la finestra B (da quando, con o senza fine settimana): decide BK-69.
2. Perché il Ledger risponde `stale_fence` al commit (BK-62 riprova senza fence: è un tentativo).
3. Quanto è veloce e affidabile `city.llm` sotto carico, e quanto costa.
4. Se dopo aver annullato tutte le offerte il cittadino accetta ancora un secondo messaggio (la regola dice di no; i
   journey vecchi con ping-pong dicono di sì). Nei journey delle 03:40–03:50 il verdetto è arrivato 5 minuti
   dopo i cancel, prima di una nostra risposta.
5. Se il consultorio prende il +2 quando `answer_set.size` è 0 (5 journey con size 0 e nessuna riga).
6. Quante copie di ogni agente girano. Lucchetti e memorie valgono solo dentro un processo.
7. Quanto perdiamo in review (proattività, collaborazione): nei journey falliti la review è vuota.

### Difetti noti non corretti

- `_index_facility` non ha memoria: una ricerca nell'Index a ogni confirm verso un partner.
- BK-67: la memoria accetta righe del Ledger con destinatario vuoto; un confirm del consultorio oltre 8 s riceve
  l'elenco delle offerte invece della conferma.
- La memoria nel processo si perde a ogni riavvio (offerte mandate, cancel già risposti, slot bloccati).
- `_TRUSTED_PARTNERS` vuoto: nessun tetto ai messaggi accettati da un agente esterno.
- La riga di offerta è lunga (~280 caratteri): in un messaggio ne entrano 5–7, non 12.
- `30_booking.py` ha 3000 righe e `_advance_alone` ne ha più di 300: ogni modifica rischia effetti collaterali.
- `PILLAR.md` è fermo e descrive un brain che non è più il nostro.
- Lo specialista non chiede il consenso `report_sharing` e non emette la ricetta di controllo (paragrafo 9).

---

## 13. Lezioni dai journey

1. **Il primo messaggio di offerte decide il percorso.** Deve coprire più giorni e i due generi di medico,
   perché i vincoli non detti si scoprono solo dopo, dai cancel.
2. **Il tempo è agenda.** Dieci minuti reali per rispondere sono dieci ore di agenda: gli slot offerti sono
   già passati quando il cittadino legge.
3. **Ogni giro di Ledger costa minuti sotto carico.** Contare i giri, non le righe di codice.
4. **Mai silenzio.** Ogni messaggio del cittadino deve avere una risposta: `status`, `cancel.ack`, `checkin.wait`.
5. **Un fix non è fatto finché un journey dopo il deploy non lo mostra.** Più volte il fix era online ma il
   percorso si chiudeva prima (G4), o il fix ne rompeva un altro (BK-58 → BK-64 → BK-66).
6. **I deploy costano.** Ogni riavvio perde i turni in corso. Con turni di 6–8 minuti, due riavvii hanno
   fatto perdere conferme (G20).
7. **`answer_set.size = 0` non è colpa nostra.** Va separato dai `no_booking` veri prima di contare.
8. **Le preferenze ordinano, non filtrano.** Filtrare ha tolto slot che erano in `S`.
9. **Le voci vanno verificate sui dati.** Vedi 2.8.
10. **Velocità non basta.** Dopo BK-67 il booking risponde in secondi, ma una finestra sbagliata o una prima
    offerta con un solo medico fanno fallire lo stesso. Dopo ogni deploy contare per priorità (B/D/P) cosa parte
    per primo: offerta, consenso o lista d'attesa.
11. **Red flag: il 112 subito, poi il resto.** Ogni attesa prima di `escalate.emergency` (storia, Index, AI) è un −2.

---

## 14. Consigli per fare più punti

### 14.1 Prima di scrivere altro codice

1. **BK-69** (paragrafo 12): finestra B e varietà della prima offerta D. Sono i punti persi più grandi oggi.
2. **Un solo deploy, poi misurare.** Scaricare tutti i journey nati dopo quel deploy.
3. **Classificare per punti persi**, non per numero di casi: una tabella causa → journey → punti persi →
   dipende da noi o dalla piattaforma. Lavorare solo sulla prima riga.

### 14.2 Organizzazione dei dati (il buco più grande oggi)

- **Salvare i journey nel repo**, in `journeys/AAAA-MM-GG/<need_id>.json`. Oggi stanno in `Download`: non
  sono condivisi né confrontabili nel tempo.
- **Uno script `asst/tools/journeys.py`** che per ogni journey estrae: livello, stato, punti per agente,
  `answer_set.size`, secondi tra richiesta e prima offerta, secondi tra ogni messaggio del cittadino e la nostra
  risposta, motivi dei cancel, fatti (hold, scadenze), versione online in quel momento. Uscita: una tabella.
  La classificazione smette di essere lettura a mano.
- **Segnare ogni deploy** (ora UTC, agente, versione) in un file `DEPLOY.md`: serve per sapere quale codice ha
  prodotto quale journey. Oggi si ricostruisce dai commit "ship".
- **Trasformare ogni journey fallito in un test di replay** in automatico: `test_replay.py` ha già il
  simulatore, ma i 18 casi sono scritti a mano.

### 14.3 Organizzazione dei file per lavorare con le AI

- **Un solo punto d'ingresso.** `CLAUDE.md` dovrebbe dire in cinque righe: leggi `docs/PASSAGGIO.md`, poi
  `REGISTRO.md`, poi la riga di `CASI.md` del caso. Oggi rimanda a `PILLAR.md`, che è fermo.
- **Dividere `PILLAR.md` in due**: `REGOLE.md` (rubrica, tempi, livelli, mondo: cambia poco) e `STATO.md`
  (livello attuale, versioni online, cosa è aperto: cambia spesso, lo aggiorna il monitor).
- **Dividere `CASI.md`**: 143 righe lunghissime in un'unica tabella. Un file per agente
  (`casi/booking.md`, `casi/gp.md`…) con righe corte e il dettaglio sotto; oppure tenere la tabella e
  spostare i casi verificati e chiusi in un archivio.
- **Dividere `30_booking.py`** in parti per fase: `30_booking_cerca.py`, `32_booking_conferma.py`,
  `34_booking_cross.py`, `36_booking_percorso.py`. `seats.py` unisce già per nome, quindi non cambia nulla per la
  piattaforma. Due persone o due AI potrebbero lavorare senza conflitti.
- **Una sessione, un compito**: il monitor classifica; una sessione corregge un gruppo di causa; nessuna fa
  tutte e due le cose. Il passaggio di consegne avviene tramite `REGISTRO.md`.

### 14.4 Usare di più l'AI della piattaforma

Il motivo per cui è spenta (era chiamata in fila) non vale più: sappiamo farla partire in parallelo, e il
collo di bottiglia è il Ledger. Sempre con scadenza e con ripiego sulla regola di oggi.

1. **Leggere il cittadino (prima priorità).** In parallelo alla lettura della storia, chiedere all'AI una
   scheda fissa: giorni possibili, genere preferito, fretta, intenzione (prenota / annulla / conferma / chiede /
   rifiuta il consenso). Oggi si fa con elenchi di parole, che ai livelli alti (gergo, sarcasmo, italiano
   stentato) non bastano. Il codice usa la scheda per **ordinare** le offerte, mai per filtrare. Un campo esplicito
   `chiave=valore` vince sempre sull'AI.
2. **La prima frase di ogni risposta.** Una frase che riprende quello che la persona ha detto, per la riga
   "proattività / freddo" della review. I campi restano scritti dal codice; `_clean_line` c'è già.
3. **Mai all'AI**: procedura e priorità della ricetta, scelta degli slot, scritture sul Ledger, campi dei
   messaggi, lettura di messaggi di altri agenti (rischio di injection).
4. **Misurare prima**: un test di 20 chiamate a `city.llm` per sapere tempo medio, errori e costo.

### 14.5 Idee di logica ancora aperte

- **Riga di offerta più corta**, per far entrare 10–12 offerte nel messaggio: togliere dalla riga ciò che il
  cittadino non usa. Da verificare contro l'elenco dei campi in e19 prima di togliere qualcosa.
- **Chiedere il vincolo invece di indovinarlo**: "solo in certi giorni" senza dire quali compare in molti
  journey. Una domanda nello stesso messaggio delle offerte non costa un turno.
- **Rifare l'hold su un altro slot** quando il commit fallisce, invece di ripartire dalle offerte.
- **Specialista: consenso al referto e ricetta di controllo mancano nel codice** (vedi paragrafo 9). È il
  buco più netto trovato scrivendo questo documento: vale +2 per ogni percorso di cardiologia che arriva alla visita.
- **Review**: scaricare qualche journey `done` con review piena e vedere dove prendiamo 0.

---

## 15. Cosa portare nella chat nuova

File, in ordine di lettura:

1. `docs/PASSAGGIO.md` (questo).
2. `CLAUDE.md`.
3. `REGISTRO.md`.
4. `docs/PASSAGGIO-indici.md` (per trovare funzioni e casi).
5. `CASI.md` (solo le righe che servono: è molto lungo).
6. Le regole ufficiali `e19-rules.md` dal kit.
7. I journey JSON scaricati dopo l'ultimo deploy.

Se la chat nuova lavora dentro il repo, basta dirle di leggere i primi tre: il resto lo trova da sola.

### Messaggio pronto da incollare

```
Lavoriamo al MACH hackathon, repo FilippoT19/mach-hackathon. Il punteggio sono i 5 agenti in asst/.
Leggi, in quest'ordine: docs/PASSAGGIO.md, CLAUDE.md, REGISTRO.md. Usa docs/PASSAGGIO-indici.md per
trovare funzioni e casi. Le regole ufficiali sono nel kit (docs/kit/e19-rules.md): rileggile se hai un dubbio.

Vincoli: modifica solo asst/brain/parts/, poi `python seats.py --brain` e `--check` da asst/; i tre test
devono passare; ogni modifica ha una riga in CASI.md; PR verso main con la tabella caso → soluzione →
logica → test in italiano. NON fare merge, deploy, scale o retire.

Stato e priorità sono nel paragrafo 12 del PASSAGGIO (aggiornato 21/11 ~10:00 UTC): BK-69 (ricette B senza
offerte locali, prima offerta D con un solo medico) e verifica di GP-17 (112 subito sulle red flag).
Dal sito (console di squadra) prendi solo il minimo: chat e JSON dei cittadini, log, messaggi della classifica.

Primo compito: leggi i journey nati dopo l'ultimo deploy (paragrafo 5 per come leggerli). Dimmi con una tabella
se le cause di BK-69 sono confermate e se GP-17 funziona. Non scrivere codice prima di avermi mostrato la tabella.
```
