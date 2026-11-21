# Proposte di magesh

Scrivi solo in questo file: nessuno lo tocca a parte te (e Claude, che aggiorna lo stato).
Modello e regole: [../PROPOSTE.md](../PROPOSTE.md). Le più nuove in alto.

<!-- aggiungi qui sotto -->

### [x] P-magesh-17: centro prenotazioni muto dopo le 03:00 UTC (deploy in pausa): nessuna risposta alla need.request e ai cancel
- Journey: N-2026-11-02-8909120001310003 (L3), N-2026-11-02-8909120002280005 (L5), N-2026-11-02-890912000278 (L6), ondata W01QQQ — ruolo: booking_centre
- Cosa fa il cittadino:
  - 0131 (L3): manda `need.request … prescription_number=… service_type=hospital.physiatry` alle 03:03:53 UTC.
  - 0228 (L5): riceve 4 offerte e le annulla tutte e 4 alle 03:12:52 UTC (`cancel offer_id=… reason=gender`).
  - 278 (L6): riceve 1 offerta e la annulla alle 03:08:00 UTC (`cancel offer_id=… reason=past`).
- Cosa risponde oggi il nostro agente: **niente**. 0131: nessuna risposta in 13 minuti, fino al verdetto. 0228 e 278: nessuna risposta dopo i cancel fino al verdetto (4–5 minuti dopo). Anche quando risponde, il booking è lento: in 0228 le offerte sono arrivate dopo **7 minuti** (03:01:28 → 03:08:35).
- Perché conta: il cittadino molla circa 48 minuti dopo il primo messaggio (0131: 02:26 → verdetto 03:17; 278: 02:25 → verdetto 03:13). Ne passano già circa 35 tra il medico e il primo messaggio al booking, quindi al booking restano circa 10 minuti: un silenzio o una risposta lenta bastano a perdere il percorso. Non è un deploy: OPS-10 ha fermato i deploy dalle 03:00 UTC (l'ultimo ship è delle 02:58). Il codice dopo un cancel dovrebbe rimandare i posti ancora liberi (`30_booking.py:1457`), quindi il turno o non parte o non finisce. La causa vera va letta nei log del booking tra le 03:03 e le 03:18 UTC (`city logs booking_centre`). Casi simili già visti: BK-28, BK-39.
- Review / punti persi: `citizen.booking_centre.wrong_outcome reason=no_booking` **−1 in tutti e 3**, con 520, 130 e 208 posti accettabili liberi. Si perdono anche il +2/+1 della prenotazione, il +2 del check-in e il +1 del Ledger. Ogni percorso torna dopo 15 minuti e può fallire di nuovo.
- Cosa dovrebbe fare: ogni messaggio del cittadino riceve un messaggio con atto entro pochi secondi, sempre:
  1. alla `need.request`, subito `status` + "Ho la sua richiesta, sto cercando i posti liberi per lei", poi le offerte;
  2. dopo uno o più `cancel`, in un solo messaggio le altre offerte ancora libere oppure, solo se non ce ne sono, la lista d'attesa (BK-10);
  3. se il turno sta durando troppo (Ledger lento), mandare comunque al cittadino quello che si ha, mai silenzio.
  Il motivo del cancel (`reason=gender`, `reason=past`) è già in P-francesco-49: qui conta solo che arrivi una risposta.
- Test a parole: "data una need.request valida, mi aspetto un messaggio al cittadino che comincia con `status` o `offer`"; "dati 4 cancel di fila con 130 posti ancora liberi, mi aspetto un messaggio con nuove `offer` diverse da quelle annullate"
- Priorità secondo te: P0 (agente muto)

| Caso | Soluzione | Logica | Test |
|---|---|---|---|
| need.request senza risposta (0131) | `status` subito, poi offerte | Il cittadino ha solo ~10 minuti per il booking | need.request → `status`/`offer` |
| Cancel senza risposta (0228, 278) | Nuove offerte o lista d'attesa, in un messaggio | Mai silenzio: −1 `no_booking` con posti liberi | 4 cancel → nuove `offer` |
| Causa del silenzio | Leggere i log booking 03:03–03:18 UTC | Non è un deploy (OPS-10) | — |

### [x] P-magesh-16: consultorio, la red flag in gravidanza (CO-10b) scatta su domande normali → 112 invece della visita
- Journey: N-2026-11-02-8909120002290002 (livello 3, ondata W01QQQ) — ruolo: family_counseling. Ricontrollato leggendo il codice su `main` 1ae5051.
- Cosa fa il cittadino: chiede una visita al consultorio, riceve le offerte, conferma (sul Ledger c'è un hold `bk-edbbfafc-…`). Il testo esatto del cittadino non l'ho letto: va aperto nel trace per vedere quale parola ha fatto scattare l'allarme.
- Cosa risponde oggi il nostro agente: annulla l'hold e manda **3 volte** `escalate.emergency reason=red_flag` "Capisco, quello che mi descrive va preso sul serio subito. Chiami subito il 112…". Percorso **Failed**: 208 posti accettabili, 208 ancora liberi a fine percorso.
- Perché succede: `20_gp.py:20-23` (CO-10b, P-magesh-6) dà red flag quando c'è **una qualsiasi** parola di gravidanza insieme a **una qualsiasi** parola di pericolo, cercata come pezzo di parola ("sangue", "perdite", "dolore forte", "blood"…). `handle()` (`00_core.py`, X-41) fa questo controllo per tutti i ruoli, quindi anche il consultorio. Ho provato la funzione `_emergency()` del brain su frasi di tutti i giorni al consultorio, e tutte danno red flag:
  - "sono incinta e vorrei fare gli esami del sangue"
  - "I'm pregnant and need a blood test"
  - "sono in gravidanza, ho delle perdite bianche, è normale?"
  - "incinta di 10 settimane, ho un dolore forte alla schiena"
  Al consultorio scrivono molte donne in gravidanza, e gli esami del sangue e le perdite sono argomenti normali: il caso tornerà spesso, e ogni volta torna dopo 15 minuti e fallisce di nuovo.
- Review / punti persi: −2 check-in mancato, −2 consulenza senza prescrizione mancata, −1 posto prenotato non onorato sul Ledger, −1 review ("lavoro rimandato al cittadino", lo mandiamo via senza motivo). Il test CO-10 attuale (`tests/test_brain.py`, `test_co10_pregnancy`) ha un solo caso negativo, senza parole di pericolo, quindi non vede il problema.
- Cosa dovrebbe fare: la red flag in gravidanza scatta solo su **frasi** di pericolo, non su parole isolate: "perdite di sangue", "perdo sangue", "sanguinamento", "contrazioni forti/frequenti", "perso le acque", "rottura delle acque", "dolore forte/intenso alla pancia/all'addome/al basso ventre"; in inglese "bleeding", "losing blood", "strong contractions", "waters broke", "severe abdominal pain". Frasi come "esami del sangue", "analisi del sangue", "blood test" non contano mai come pericolo. Tutto il resto segue il percorso normale del consultorio: offerte, hold, commit, nessuna prescrizione richiesta. I casi positivi di oggi devono restare red flag ("sono incinta di 7 mesi e ho perdite di sangue", "I'm pregnant and have strong contractions"). Aggiornare la riga CO-10b in CASI.md.
- Test a parole: "date le 4 frasi sopra al consultorio, mi aspetto `offer …` e nessun `escalate.emergency`"; "dato 'sono incinta di 7 mesi e ho perdite di sangue', mi aspetto `escalate.emergency reason=red_flag` e nessuna offerta"
- Priorità secondo te: P1 (punti persi spesso al consultorio; la sicurezza resta perché le vere red flag continuano a scattare)

| Caso | Soluzione | Logica | Test |
|---|---|---|---|
| Domanda normale in gravidanza con "sangue/perdite/dolore forte" → 112 | Pericolo solo su frasi precise; "esami del sangue"/"blood test" esclusi | Una parola isolata non è un'emergenza; il consultorio deve prenotare | 4 frasi normali → offerte, nessun 112 |
| Vera red flag in gravidanza | Resta `escalate.emergency` | Sicurezza prima di tutto | "incinta + perdite di sangue" → 112, nessuna offerta |

### [x] P-magesh-15: centro prenotazioni, due messaggi al cittadino senza atto
- Journey: nessuno (lettura del codice su `main` 15c6524) — ruolo: booking_centre
- Cosa fa il cittadino: (a) chiede una visita e il catalogo del Ledger ha più pagine; (b) manda un `confirm` senza `offer_id` né `slot_id` (es. "va bene il primo").
- Cosa risponde oggi il nostro agente: (a) `30_booking.py:1567` "Ho la sua richiesta e sto controllando tutti i posti liberi per lei; le riscrivo tra un momento." (b) `30_booking.py:1675` "Mi scriva il numero dell'offerta per prenotare l'appuntamento." Tutte e due **solo testo, senza atto** e senza token.
- Review / punti persi: il cittadino legge prima l'atto e poi i token `chiave=valore`; il testo libero non conta per le decisioni (Rule 5.1.2). Nel caso (b) il cittadino non capisce cosa mandare: rimanda lo stesso messaggio fino a `no_reply`, percorso fallito, niente +2/+1 della prenotazione, −1 review ("lavoro rimandato al cittadino").
- Cosa dovrebbe fare: stessa frase, con l'atto davanti, come gli altri messaggi del file:
  1. (a) `status` + la frase (come `_still_here`, `30_booking.py:1147`).
  2. (b) `data.request purpose=booking_choice fields=offer_id` + la frase. Ancora meglio, se il cittadino ha **una sola** offerta aperta, prenotare quella senza chiedere niente (Rule 5.1.5); se ne ha più di una, ripetere le offerte aperte nello stesso messaggio.
- Test a parole: "dato un catalogo di 2 pagine, mi aspetto che il messaggio di attesa al cittadino cominci con `status`"; "dato `confirm` senza `offer_id` e due offerte aperte, mi aspetto `data.request … fields=offer_id` con le due offerte"
- Priorità secondo te: P1

| Caso | Soluzione | Logica | Test |
|---|---|---|---|
| Messaggio di attesa senza atto | `status` davanti alla frase | Il cittadino legge l'atto prima del testo | catalogo 2 pagine → `status …` |
| Conferma senza numero d'offerta | `data.request fields=offer_id` (o prenota l'unica offerta aperta) | Una domanda leggibile evita `no_reply` | `confirm` senza id → `data.request` |

### [x] P-magesh-14: centro prenotazioni, "le ho già mandato i posti liberi" quando nessuna offerta è aperta
- Journey: nessuno (lettura del codice su `main` 15c6524) — ruolo: booking_centre
- Cosa fa il cittadino: ha ricevuto solo la lista d'attesa (`offer … waiting_list=true`), oppure ha annullato una a una tutte le offerte; poi riscrive ("ci sono novità?", "quindi?").
- Cosa risponde oggi il nostro agente: `status Le ho già mandato i posti liberi: mi risponda con quello che preferisce e lo blocco, oppure mi dica se nessuno le va bene e cerco ancora.` In `_still_here` (`30_booking.py:1141`) basta **un qualsiasi** `offer` mandato in passato, anche la lista d'attesa o un'offerta già annullata.
- Review / punti persi: −1 review (passivo: rimanda il cittadino a posti che non ha più); la frase descrive un'offerta che non esiste, rischio audit "offerta descritta in modo falso" (−2).
- Cosa dovrebbe fare: guardare solo le offerte **ancora aperte** (quelle che `_open_offers` già calcola, senza la lista d'attesa):
  1. Offerte aperte → la frase di oggi.
  2. Solo lista d'attesa → `status waiting_list=true` + "È in lista d'attesa per <procedura>: appena si libera un posto adatto glielo propongo io. Se il disturbo cambia, contatti il suo medico di base."
  3. Tutte annullate, nessuna lista → "sto controllando" e una nuova ricerca, non "le ho già mandato".
- Test a parole: "dato solo `offer … waiting_list=true` e poi `ci sono novità?`, mi aspetto `status waiting_list=true …` e **non** 'Le ho già mandato i posti liberi'"; "dato 3 offerte tutte annullate e poi un nuovo messaggio, mi aspetto una nuova ricerca o la lista d'attesa"
- Priorità secondo te: P1

| Caso | Soluzione | Logica | Test |
|---|---|---|---|
| Solo lista d'attesa, il cittadino riscrive | Frase "è in lista d'attesa" con `waiting_list=true` | Dire solo ciò che il Ledger/le offerte mostrano | lista d'attesa + "novità?" → `status waiting_list=true` |
| Offerte tutte annullate | Nuova ricerca invece di "le ho già mandato" | Nessuna offerta aperta = niente da scegliere | 3 cancel + messaggio → nuova ricerca |

### [x] P-magesh-13: centro prenotazioni, i giorni a parole leggono anche "non posso il lunedì" (seguito di BK-56)
- Journey: nessuno (lettura del codice su `main` 15c6524) — ruolo: booking_centre. Seguito di BK-56 (`CASI.md`, journey 249).
- Cosa fa il cittadino: nomina un giorno che **non** vuole, o che non c'entra con l'appuntamento. Es. "Non posso il lunedì, va bene qualsiasi altro giorno", "I can come any day except Friday", oppure al medico: "Il dolore al ginocchio è iniziato lunedì scorso".
- Cosa risponde oggi il nostro agente: `_days` (`30_booking.py:262`) prende ogni nome di giorno nei messaggi del cittadino, anche quelli scritti al medico. Provato sul codice: le tre frasi danno `{mon}`, `{fri}`, `{mon}`. Il giorno sbagliato diventa il giorno preferito: la prima offerta è proprio il giorno escluso, e la richiesta alle altre ASST porta `days=mon` (`30_booking.py:825`), quindi il partner può cercare solo quel giorno.
- Review / punti persi: +2 (slot preferito) che scende a +1, o rifiuti in serie; −1 "nessuna prenotazione con S non vuoto" se il partner, filtrando sul giorno sbagliato, non offre niente.
- Cosa dovrebbe fare:
  1. Un giorno preceduto da "non", "tranne", "eccetto", "except", "not", "no" è un giorno **escluso**: non entra fra i preferiti (meglio ancora: va in fondo all'ordine).
  2. Contano solo i messaggi del cittadino **al centro prenotazioni** (e il token `days=` passato dal medico), non il racconto del sintomo al medico ("iniziato lunedì", "da venerdì").
  3. "qualsiasi giorno" / "any day" → nessuna preferenza di giorno.
- Test a parole: "dato `Non posso il lunedì, va bene qualsiasi altro giorno`, mi aspetto nessun `days=mon` e il lunedì non come prima offerta"; "dato al medico `il dolore è iniziato lunedì scorso` e al booking nessun giorno, mi aspetto nessuna preferenza di giorno"; "dato `Posso venire solo lunedì o mercoledì` (journey 249), mi aspetto ancora `{mon, wed}`"
- Priorità secondo te: P1

| Caso | Soluzione | Logica | Test |
|---|---|---|---|
| Giorno negato letto come preferito | "non/tranne/except" + giorno = giorno escluso | Il cittadino rifiuta lo slot nel giorno che ha escluso | "non posso il lunedì" → niente `days=mon` |
| Giorno del sintomo letto come preferito | Solo i messaggi al booking contano | La data del sintomo non è un vincolo d'agenda | "iniziato lunedì" al gp → nessun giorno |
| BK-56 resta valido | Frase positiva invariata | Non rompere il fix del 249 | "solo lunedì o mercoledì" → `{mon, wed}` |

> **⚠️ DA FARE PER PRIME: P-magesh-10, P-magesh-11, P-magesh-12 (medico di base).**
> Implementarle **prima di tutte le altre proposte aperte** di questo file. Proteggono le perdite più grandi
> del medico di base: −2 per una red flag persa e i percorsi falliti per `no_reply`. Sono modifiche piccole
> in `asst/brain/parts/20_gp.py` e `asst/brain/parts/00_core.py`. Ordine consigliato: 11 → 12 → 10.

### [x] P-magesh-10: medico di base, secondo messaggio con sintomo non riconosciuto → silenzio
- Journey: nessuno (lettura del codice su `main` 77b907a) — ruolo: gp
- Cosa fa il cittadino: scrive un disturbo che la tabella non riconosce ("non mi sento bene"); il medico gli chiede dove e da quando; il cittadino risponde con parole sue che la tabella e il modello ancora non riconoscono ("mi fa male qui sul fianco da tre giorni"). Oppure, dopo aver ricevuto la ricetta, scrive "grazie, e adesso?"
- Cosa risponde oggi il nostro agente: al primo messaggio la domanda di GP-05 ("Mi descrive meglio il disturbo: dove sente il problema e da quanto tempo?…"). Al secondo: **niente**. In `20_gp.py:292` la risposta parte solo se il medico non ha mai scritto prima a quel cittadino (`asked`); se ha già scritto anche una sola volta, nessuna risposta
- Review / punti persi: −1 review ("messaggio senza risposta", passivo); il cittadino aspetta 16 minuti, rimanda e dopo 3 tentativi abbandona → `no_reply`, percorso fallito e nessun +2 per la ricetta
- Cosa dovrebbe fare: **non lasciare mai un messaggio del cittadino senza risposta**. GP-05 resta ("una sola domanda, niente interrogatorio"), ma il secondo messaggio non riconosciuto riceve una risposta diversa e più stretta:
  1. Se il medico ha già chiesto dettagli e non c'è ancora una ricetta: una domanda chiusa con le scelte che conosciamo, nella lingua del cittadino. Es. "Per prepararle la ricetta giusta mi aiuta a capire: si tratta della schiena, del ginocchio, del cuore che batte forte, o di un controllo del cuore?" / "So I can prepare the right prescription: is it your back, your knee, your heart racing, or a heart check-up?"
  2. Se il medico ha già mandato una ricetta a questo cittadino: ripetere `prescription prescription_number=… procedure=… priority=…` con una frase breve sul prossimo passo ("La sua ricetta è pronta: contatti il centro prenotazioni con questo numero").
  3. Dal terzo messaggio non riconosciuto in poi: una frase gentile che non ripete la stessa domanda (per non sembrare un robot), es. "Mi dispiace, non riesco ancora a capire il disturbo. Se peggiora o compare dolore al petto chiami il 112."
- Test a parole: "dato `non mi sento bene` e poi `mi fa male qui sul fianco da tre giorni` (nessuna parola nota, modello `NONE`), mi aspetto al secondo messaggio una risposta con le quattro scelte, non il silenzio"; "dato una ricetta già mandata e poi `grazie, e adesso?`, mi aspetto di nuovo `prescription prescription_number=…` con il prossimo passo"
- Priorità secondo te: **P0** (agente muto)

| Caso | Soluzione | Logica | Test |
|---|---|---|---|
| Secondo messaggio non riconosciuto → silenzio | Domanda chiusa con le 4 scelte del protocollo | GP-05 vieta l'interrogatorio, non la risposta: ogni messaggio del cittadino ha una risposta | 2 messaggi ignoti → 2 risposte diverse |
| Messaggio dopo la ricetta → silenzio | Ripetere i token della ricetta + prossimo passo | Il cittadino ha la ricetta ma non sa cosa fare: proattività invece di silenzio | ricetta + "grazie, e adesso?" → `prescription prescription_number=…` |

### [x] P-magesh-11: medico di base, red flag scritte in altro modo riconosciute solo dal modello
- Journey: nessuno (lettura del codice su `main` 77b907a) — ruolo: gp (vale anche per gli altri ruoli che usano `_emergency`)
- Cosa fa il cittadino: descrive un'emergenza con parole diverse da quelle della lista fissa. Es. "ho un forte **male al petto**", "**dolore toracico** da stamattina", "sento un'**oppressione al petto**", "ho perso **forza alla gamba**", "**non sento la gamba** destra", "mi fa male il petto e il braccio sinistro", "chest tightness", "my chest hurts", "I can't feel my leg"
- Cosa risponde oggi il nostro agente: la lista fissa (`_RED_FLAGS` in `00_core.py:56`, `_RED_FLAGS_MORE` in `00_core.py:65`, le frasi in `20_gp.py:12`) riconosce solo "dolore al petto", "chest pain", "perdita di forza alle gambe", "non sento **più** le gamb**e**" (plurale). Le frasi sopra passano solo se `city.llm` risponde `RED_FLAG` entro 4 s (GP-03). Se il modello è lento, giù o risponde male → **nessuna escalation**: il cittadino riceve la domanda "Mi descrive meglio il disturbo?" o addirittura una ricetta (es. "mal di schiena e non sento la gamba" → ricetta fisiatrica, perché la parola "schiena" viene trovata prima)
- Review / punti persi: **−2** emergenza (primo agente sul caso senza escalation), più il rischio per la sicurezza del cittadino
- Cosa dovrebbe fare: la red flag non deve mai dipendere dal modello. Allargare il controllo fisso, che gira prima del modello, con radici di parole invece di frasi esatte:
  1. **Petto**: "petto" o "torac" insieme a "dolor", "male", "stretta", "oppressione", "peso", "fa male"; in inglese "chest" con "pain", "tight", "pressure", "hurt"
  2. **Gambe**: "gamba"/"gambe" (singolare e plurale, con o senza "più") con "non sento", "non riesco a muovere", "perso forza", "perdita di forza", "formicolio forte"; in inglese "leg"/"legs" con "can't feel", "cannot move", "lost strength", "numb"
  3. Il controllo della red flag va fatto **prima** del sintomo: se c'è una red flag, escalation anche se il messaggio contiene "schiena" o "ginocchio"
  4. Meglio un falso allarme che un'emergenza persa (stessa logica di GP-03)
- Test a parole: "dato `ho un forte male al petto` con il modello spento, mi aspetto `escalate.emergency reason=red_flag`"; "dato `mal di schiena e non sento la gamba` con il modello spento, mi aspetto `escalate.emergency reason=red_flag` e **nessun** `prescribe`"; "dato `my chest feels tight` con il modello spento, mi aspetto `escalate.emergency reason=red_flag`"
- Priorità secondo te: **P0** (112)

| Caso | Soluzione | Logica | Test |
|---|---|---|---|
| Red flag con parole diverse dalla lista | Controllo fisso con radici (petto/torac + dolore/male/stretta; gamba/e + non sento/forza) | Il modello può essere lento o giù: il −2 e la sicurezza non devono dipendere da lui | "male al petto", modello spento → `escalate.emergency` |
| Red flag + sintomo noto nello stesso messaggio | Escalation prima della ricetta | La red flag vince sempre sul protocollo | "mal di schiena e non sento la gamba" → escalation, nessun `prescribe` |

### [~] P-magesh-12 (da decidere: Filippo ha scelto avviso prima del 112; la frase "il più vicino" è già corretta con GP-15): medico di base, il messaggio del 112 aspetta le ricerche prima di partire
- Journey: nessuno (lettura del codice su `main` 77b907a) — ruolo: gp (`_escalate` è usato da tutti i ruoli)
- Cosa fa il cittadino: scrive una red flag ("dolore al petto").
- Cosa risponde oggi il nostro agente: il messaggio giusto (`escalate.emergency reason=red_flag` + "Chiami subito il 112…"), ma **in ritardo**. In `_escalate` (`20_gp.py:30`), prima di mandarlo, il medico aspetta: (a) `_peer` per trovare il nostro ospedale (fino a 5 s, solo la prima volta); (b) insieme (X-55) l'avviso all'ospedale e la ricerca del pronto soccorso più vicino (`_zone_point` + `_nearest_line`, fino a 4 s + 4 s con l'Index lento). Nel caso peggiore il cittadino aspetta **circa 13 secondi** il 112. In più la frase dice sempre "Il pronto soccorso più vicino nella nostra zona è il nostro ospedale in Via Arganini Gerolamo 38", anche se la ricerca subito dopo nomina un altro ospedale più vicino (due frasi in contrasto)
- Review / punti persi: risposta lenta proprio nel caso più grave (sicurezza, review); rischio −2 audit "offerta descritta in modo falso" se il PS "più vicino" non è il nostro
- Cosa dovrebbe fare: **il 112 parte per primo, subito, senza aspettare nessuna ricerca.** X-55 resta, ma spostato dopo:
  1. Primo messaggio, immediato: `escalate.emergency reason=red_flag` + "Capisco, va preso sul serio subito. Chiami subito il 112 o vada al pronto soccorso più vicino. Non si metta alla guida: se può, si faccia accompagnare e non resti da solo." Nessuna ricerca prima di questo messaggio
  2. Poi, in parallelo: l'avviso `emergency.notice reason=red_flag` al nostro ospedale e la ricerca del PS più vicino
  3. Secondo messaggio al cittadino, appena finiscono: "Ho già avvisato il nostro ospedale (Via Arganini Gerolamo 38, accessibile in sedia a rotelle)" e, solo se la ricerca lo trova, "Il pronto soccorso più vicino alla sua zona è …". Dire "il più vicino" solo quando la ricerca lo conferma; altrimenti dire "il nostro ospedale"
  4. La domanda "Mi dice dove si trova adesso?" (X-42) resta dopo
  - La collaborazione resta visibile nella chat del cittadino (era il motivo di X-55): il "li ho già avvisati" passa solo nel secondo messaggio
- Test a parole: "dato `dolore al petto` con l'Index che risponde dopo 4 s, mi aspetto `escalate.emergency reason=red_flag` come **primo** messaggio al cittadino, prima di qualsiasi `city.find`"; "dato un PS più vicino di un'altra ASST, mi aspetto che la frase non dica che il nostro ospedale è il più vicino"
- Priorità secondo te: **P0** (112)

| Caso | Soluzione | Logica | Test |
|---|---|---|---|
| Il 112 aspetta `_peer` + ricerca PS (fino a ~13 s) | 112 subito, ricerche dopo, secondo messaggio con avviso e PS più vicino | Nell'emergenza conta il primo secondo; X-55 resta ma non blocca più il 112 | Index lento → primo messaggio = `escalate.emergency` |
| "Il PS più vicino è il nostro" sempre | Dire "il più vicino" solo se la ricerca lo conferma | Nessuna frase falsa al cittadino (audit −2) | PS di altra ASST più vicino → la frase non dice "il nostro è il più vicino" |

### [ ] P-magesh-9: consultorio, hold rifiutato → rioffre lo stesso slot rifiutato → la seconda conferma resta senza risposta
- Journey: N-2026-11-02-8909120001050002 (cittadino 000105, L3, Fallito, wave W01QQQ) — ruolo: family_counseling. Lettura del codice su `main` 78dab8a
- Cosa fa il cittadino: chiede una visita al consultorio (00:30:13); riceve 3 offerte (10:30, 12:00, 14:30 del 17/11) e, in un secondo messaggio, una quarta (16:00); conferma `of-…-20261117-1030` con `cons-…-booking` (00:30:42). Dopo l'annullamento riceve di nuovo le stesse 3 offerte e riconferma **la stessa** `of-…-1030` (01:03:37)
- Cosa risponde oggi il nostro agente: `cancel offer_id=of-…-1030 reason=facility_cancelled` (00:31:25), poi rioffre 10:30 / 12:00 / 14:30, **compreso lo slot appena rifiutato** (00:31:26). Alla seconda conferma: **niente**. Il testo dell'offerta comincia anche con "offer offer"
- Review / punti persi: percorso Fallito, il giudice non ha registrato il motivo; Valutazioni NEUTRAL. Cittadino che conferma e non riceve risposta. Lo stesso schema (cittadini 000064 ×4, 000057, 000051, 000113 ×3) potrebbe spiegare altri Falliti: **da confermare** con il log del Consultorio (Log → Scarica JSON) di questo journey e di 2-3 altri
- Causa probabile (codice):
  1. **Slot rifiutato riofferto**: `_on_refused` (`40_facility.py:346`) manda il `cancel` al cittadino e poi chiama `_advance(replacing=True)` (`40_facility.py:375`) con la stessa storia del caso, che non contiene ancora il `cancel` appena mandato (`_say` non lo aggiunge). Così `_withdrawn` (`30_booking.py:116`, usato a `:1121`) non vede lo slot annullato e lo rioffre. Al booking_centre questo non succede, perché lì il `cancel` arriva dal partner ed è già nella storia
  2. **Seconda conferma muta**: in `_on_confirm` (`30_booking.py:1268`) l'`hold` per quello slot risulta "già mandato", quindi non si manda un nuovo `hold`; `_finish_booking` (`30_booking.py:1343`) aspetta una risposta che non arriva o ritrova il vecchio rifiuto, il cui `cancel` è già stato mandato → al cittadino non arriva niente
  3. **Motivo del rifiuto nascosto**: il Ledger ha rifiutato l'`hold` ma il motivo diventa `facility_cancelled`. Già coperto da Francesco (`proposte/francesco.md`, codice del Ledger nel `reason=`); la lettura nuova del catalogo dopo il rifiuto è il punto 2 di P-magesh-8
- Cosa dovrebbe fare:
  1. Dopo un `hold`/`commit` rifiutato, lo slot rifiutato non va **mai** riofferto: contarlo tra gli slot annullati prima di cercare le nuove offerte, e rioffrire solo gli altri (12:00, 14:30, 16:00)
  2. Se il cittadino conferma uno slot che ha già avuto un `hold` rifiutato, mai silenzio: rispondere subito "Mi dispiace, quel posto non è più disponibile. Le propongo questi altri orari" con le offerte ancora libere (o la lista d'attesa se non ce ne sono)
  3. Togliere il doppio "offer offer" all'inizio della frase al cittadino
- Test a parole: "dato il consultorio con offerte s1030, s1200, s1430, il cittadino conferma s1030 e il Ledger risponde `refused hold slot_id=s1030`: mi aspetto `cancel offer_id=of-s1030` al cittadino e una nuova offerta **senza** `slot_id=s1030`"; "dato poi un secondo `confirm offer_id=of-s1030`, mi aspetto un messaggio al cittadino (posto non disponibile + altre offerte o lista d'attesa), non il silenzio e non un secondo `hold` per s1030"
- Priorità secondo te: P0 (cittadino che conferma e non riceve risposta)

| Caso | Soluzione | Logica | Test |
|---|---|---|---|
| Hold rifiutato al consultorio, lo slot rifiutato viene riofferto | Escludere lo slot rifiutato dalle nuove offerte | La storia del caso non contiene ancora il nostro `cancel`, quindi lo slot va segnato come annullato a mano | `refused hold slot_id=s1030` → nuova offerta senza s1030 |
| Seconda conferma dello slot rifiutato → silenzio | Rispondere sempre: posto non disponibile + altre offerte / lista d'attesa | Un `hold` già rifiutato non si rimanda, ma il cittadino deve sapere cosa succede | secondo `confirm of-s1030` → messaggio al cittadino, nessun nuovo `hold` |
| "offer offer" nel testo | Togliere la parola ripetuta | Frase pulita per il cittadino | il testo dell'offerta non contiene "offer offer" |


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
