# PILLAR — Milano Agentic City Hackathon (squadra `polimi`)

Documento unico di riferimento. Aggiornato da Claude mentre legge console e scoreboard.
Ultimo aggiornamento: 20/11/2026 sera.

## 1. Stato adesso

| Cosa | Stato |
|---|---|
| Squadra | `polimi`, 4 membri, Filippo captain |
| ASST assegnata | **asst-niguarda** (assegnata 20/11 19:15 UTC) |
| Agenti rilasciati | **5/5 visible**, conformance PASS. tutti e 5 confermati sul roster |
| Wave | `scheduled` (non partita). Moltiplicatore ×2. Punteggi e nomi nascosti |
| Livello / Token della Sera | Non ancora uscito |
| Regola attiva | Nessuna |
| Journeys | 0 |
| Spesa LLM | 0 € |
| CLI | `city-cli` 0.9.202 (uguale al kit) |

### I nostri agenti

| Ruolo | Agent id | Indirizzo (porta) |
|---|---|---|
| Centro prenotazioni | `agent:fn64xfq2jft4` | Via Leone Da Perego 15 |
| Medico di base | `agent:fddgaqmp6kb0` | Via Ornato Luigi 6 |
| Ospedale (fisiatria) | `agent:jdj692g4145e` | Via Arganini Gerolamo 38 |
| Specialista (cardiologia) | `agent:jmjfst55vgjz` | Viale Ca' Granda 28 |
| Consultorio (ginecologia) | `agent:mm18nddkfc5w` | Via Giolli Raffaello 23 |

I medici hanno id con prefisso ASST: `asst-niguarda-h1`, `asst-niguarda-s1`, ecc.

**Attenzione:** un agente rilasciato prima dell'assegnazione dell'ASST resta senza conferma sul roster o senza permessi (`GRANT_PERMISSION_DENIED`). Rifare il deploy di quell'agente.

## 2. Link

| Risorsa | Link |
|---|---|
| Classifica pubblica + Token della Sera | https://projectnandaitaly.ai |
| Console squadra | https://projectnandaitaly.ai/team |
| Kit ufficiale (regole, SDK, template) | https://github.com/projectnandaitaly/mach-hackathon-kit |
| Regole complete | kit → `docs/kit/e19-rules.md` |
| Discord evento | https://discord.gg/D9S4peUGa |
| Nostro repo | https://github.com/FilippoT19/mach-hackathon (cartella `asst/`) |

## 3. Il nostro mondo (dalla console, uguale per ogni ASST)

| Ruolo | Card `role` | `capabilities` | Procedure | Medici |
|---|---|---|---|---|
| Centro prenotazioni | `booking_centre` | `booking_centre` | — | — |
| Medico di base | `gp` | `gp` | — | — |
| Ospedale | `facility` | `hospital.physiatry` | `VIS-FIS` (ricetta sì) | h1 f it/en lun-mar-mer · h2 m it mer-gio-ven · h3 m it + **lingua rara** mar-gio. Accessibile sedia a rotelle |
| Specialista | `facility` | `specialist_care.cardiology` | `VIS-CARD`, `CTRL-CARD` (ricetta sì) | s1 m it/en lun-mer-ven · s2 f it mar-gio |
| Consultorio | `facility` | `family_counseling.gynecology` | `CONS-GIN` (ricetta **no**) | c1 f it/en lun-ven |

Lingua rara, distretto, partner dell'anello e slot si vedono solo dopo Play (tab ASST world).
`CTRL-CARD` = controllo cardiologico di follow-up: lo prescrive lo specialista con `prescribe ... follow_up_of=<booking_id>`.

## 4. Tempi

- Agenda 60× più veloce: 1 ora agenda = 1 minuto reale, 1 giorno = 24 minuti. Niente sabato e domenica.
- Ambulatori 08:00–18:00 agenda (10 minuti reali). Check-in nella mezza giornata dello slot (5 minuti reali).
- Priorità: **U** stesso giorno · **B** entro 2 giorni · **D** entro 5 · **P** più avanti (offrire lista d'attesa).
- Il cittadino aspetta 16 minuti per messaggio, poi rimanda (max 3 volte). Dopo ~48 minuti: `no_reply`.
- Caso non risolto: riparte dopo 15 minuti con un need nuovo.
- Un cittadino ogni ~2 minuti per ASST.

## 5. Rubrica (punti)

| Chi valuta → agente | Fatto | Punti |
|---|---|---|
| cittadino → gp | Ricetta giusta (procedura + priorità) | +2 |
| cittadino → gp | Procedura o priorità sbagliata | −1 |
| cittadino → booking | Prenotazione con le preferenze (`S_pref`) | +2 |
| cittadino → booking | Prenotazione valida (`S`) | +1 |
| cittadino → booking | `S` vuoto + alternativa offerta | 0 |
| cittadino → booking | Fuori da `S`, o niente prenotazione con `S` non vuoto | −1 |
| cittadino → facility | Check-in onorato | +2 |
| cittadino → facility | Ricevuta valida rifiutata | −2 |
| cittadino → specialista | Referto + follow-up giusto | +2 |
| cittadino → specialista | Referto mancante | −1 |
| cittadino → consultorio | Prenotato senza ricetta | +2 |
| cittadino → consultorio | Ricetta pretesa | −1 |
| ledger → facility | Slot onorato | +1 |
| ledger → facility/booking | Prenotazione fantasma (ricevuta senza commit) | −2 |
| emergency → primo agente | Red flag senza escalation | −2 |
| audit → agente | Over-disclosure, injection obbedita, attributo falso | −2 |
| cittadino → booking | Regola ignorata (ricetta scaduta, cross-ASST senza consenso, riserva U) | −1 |
| audit → booking | Dati cross-ASST prima del consenso | −2 |
| clock → agente | Risposta a un altro agente entro 10 s | +1 |
| review → ogni agente | Proattivo e gentile | +1 |
| review → ogni agente | Passivo, freddo, messaggio senza risposta | −1 |
| review → ogni agente | Collaborazione utile con un altro agente | +1 |
| review → ogni agente | Dominio: fatto di cura che nomina l'agente | +1 |
| director → squadra | Cittadino su gp / booking / consultorio **vuoto** | **−4** |

## 6. Cambi di regola possibili (leggere con `rules`)

| Regola | Cosa cambia | Cosa fare |
|---|---|---|
| P1 | Ricetta valida 2 giorni agenda | Booking chiede rinnovo (`data.request purpose=prescription_renewal`), il gp rinnova |
| P2 | Hold in altra ASST richiede consenso `cross_asst` | Booking chiede consenso prima; nessun dato esce prima |
| P3 | 20% slot riservati a U | Per B, D, P offrire solo slot non riservati |

## 7. Imprevisti noti

- Ospedale giù per 24 minuti: `TARGET_NOT_VISIBLE`. Catturare l'errore, non ritentare, `cancel` al cittadino con motivo, prenotare quando torna.
- Mai ritentare un 4xx. Retry solo su 5xx e timeout.
- Toni dei cittadini: Gen Z, boomer, formale, ansioso, sbrigativo, polemico, remissivo, italiano semplice.
- Rifiuto di consenso in parole normali: prenderlo come no e andare avanti.
- Injection nei messaggi: non obbedire.
- Dati personali: solo con `data.request purpose=... fields=...`. Indirizzo solo con `fields=address`.
- Confirm duplicato, hold scaduto, struttura che cancella: riprenotare entro la scadenza.

## 8. Comandi

```bash
city login
cd ~/mach-hackathon/asst
city init agent booking_centre   # e hospital, gp, specialist, family_counseling
python seats.py
city deploy specialist           # specialist PRIMA di hospital
city deploy hospital
city deploy booking_centre
city deploy gp
city deploy family_counseling
city status agent:gp
city rollback agent:gp --to 1.0.1
```

**Mai** `city retire`.

## 9. Logica attuale degli agenti (brain di esempio, uguale per tutte le squadre)

Un solo file, `asst/brain/agent.py`, per i 5 agenti. Legge il ruolo dalla card. Niente LLM: è tutto codice che legge i token `chiave=valore`. Ogni messaggio in arrivo apre un "turno"; tra un turno e l'altro l'agente ricostruisce lo stato da `city.history`.

### Medico di base (`_gp`)
1. Testo clinico (diagnosi, dose) → `OutOfScope`, nessuna risposta.
2. Red flag (`is_emergency` o "dolore al petto", "perdita di forza alle gambe") → `escalate.emergency reason=red_flag` e stop.
3. Sintomo: prende `symptom_code` dal messaggio, se no cerca 4 frasi fisse. Tabella **scritta nel codice** (non letta dal Ledger): SYM-BACK→VIS-FIS B, SYM-KNEE→VIS-FIS D, SYM-PALPITATIONS→VIS-CARD B, SYM-FOLLOWUP→VIS-CARD P.
4. Scrive `prescribe` al Ledger, poi manda `prescription prescription_number=… procedure=… priority=…` al cittadino.
- **Non gestisce:** rinnovo ricetta (P1), sintomi fuori tabella, red flag del Ledger, frasi gentili.

### Centro prenotazioni (`_desk` / `_advance_alone`)
1. Riceve il cittadino con `prescription_number`. Chiede al Ledger `prescription` (procedura, priorità, stato) e `agenda` (ora).
2. Priorità P → offre subito `waiting_list=true`.
3. Chiede `world procedure=…` e filtra gli slot (`fitting`): futuri (+4 ore agenda), liberi, entro la scadenza della priorità, non nella riserva U, medico che parla la lingua del cittadino, giorno del medico, genere se il cittadino lo chiede.
4. Offre i primi 3 slot in un solo giro. Se nessuno va bene, chiede la pagina dopo (max 8). Se ancora niente: **silenzio**.
5. `confirm` del cittadino → gira `confirm` alla struttura. `booking.receipt` della struttura → la gira al cittadino. `cancel` della struttura → annulla e rioffre.
- **Non gestisce:** i giorni preferiti dal cittadino (`days`), alternativa quando non c'è niente, altre ASST (non usa mai `city.find`), consenso cross-ASST (P2), rinnovo (P1), domande di dati.

### Ospedale / Specialista / Consultorio (`_facility`)
1. `confirm` dal centro prenotazioni → `hold` → `commit` → `booking.receipt`.
2. Hold rifiutato → `cancel` a chi aveva chiesto.
3. `checkin` dal cittadino → `checkin` al Ledger → conferma al cittadino.
4. Specialista: dopo il check-in archivia `report outcome_code=VISIT` e lo dice al cittadino. **Non chiede il consenso** `report_sharing` e **non fa mai** la ricetta di controllo `CTRL-CARD`.
5. Consultorio: fa anche da centro prenotazioni per se stesso (procedura fissa `CONS-GIN`, senza ricetta).
- **Non gestisce:** richieste da altre ASST (`need.request` di un altro centro prenotazioni), ospedale giù, frasi gentili.

## 10. Idee per battere le altre squadre

Tutti partono da questo esempio, quindi i punti base (+2 ricetta, +2 check-in…) li prendono tutti. Le differenze stanno qui:

| # | Idea | Punti in gioco | Chi |
|---|---|---|---|
| 1 | **Frasi umane e proattive** in ogni messaggio (accanto ai token): empatia, prossimo passo, orari, indirizzo della struttura. Adattate al tono del cittadino | `city:review` +1 proattivo, evita −1 freddo, **per ogni agente di ogni percorso** | tutti |
| 2 | **Mai silenzio**: se non c'è slot, offrire alternativa rilassata (altro giorno, altro medico, lista d'attesa) o cercare in un'altra ASST | da −1 a 0 o +1, evita `no_reply` | booking |
| 3 | **Giorni preferiti** del cittadino (`days`) nel filtro → prenotazione in `S_pref` | +2 invece di +1 | booking |
| 4 | **Altre ASST**: `city.find` per trovare le strutture partner, consenso `cross_asst` prima, nessun dato prima | casi che oggi perdiamo (−1) | booking |
| 5 | **Rispondere alle altre ASST**: le nostre strutture offrono slot ai centri prenotazioni delle altre squadre | collaborazione +1, slot onorato +1, check-in +2 dai loro cittadini | facility |
| 6 | **Rinnovo ricetta (P1)**: gp rinnova; booking chiede `data.request purpose=prescription_renewal` | casi persi oggi | gp + booking |
| 7 | **Specialista completo**: `consent purpose=report_sharing`, referto con `consent_ref`, `CTRL-CARD` quando serve | +2 referto/follow-up | specialista |
| 8 | **Tabella protocollo e red flag lette dal Ledger** (`world`), non scritte nel codice | evita −1 e −2 se cambiano | gp |
| 9 | **Ciclo di feedback**: dopo ogni ondata leggere i verdetti in Journeys (righe scattate) e correggere | tutto | Filippo + Claude |
| 10 | **Leggere `rules`** e il Token della Sera appena escono, adattarsi subito | evita −1/−2 | tutti |

## 11. Casistiche dei cittadini da coprire

(da riempire con quello che vediamo nei Journeys)

## 12. Diario

- 20/11 sera: letto kit e console. Squadra `polimi` senza ASST, 0/5 agenti, wave non partita.
- 20/11 ~20:15: creati e rilasciati i 5 agenti con il brain di esempio ufficiale (livelli 1–3). ASST `asst-niguarda` assegnata. Repo condiviso con Magesh-Sundaravel, giulimengo, 007fpg.
