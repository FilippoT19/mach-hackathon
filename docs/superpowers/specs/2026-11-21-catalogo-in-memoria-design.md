# Catalogo in memoria per il booking — progetto

Data: 21/11/2026. Stato: da approvare (Filippo). Caso previsto in `CASI.md`: **BK-67**.

## Perché

Nei 16 journey falliti delle 04:45–05:26 UTC (wave W01QQQ) la prima offerta è partita circa
32 minuti dopo la ricetta e la wave si è chiusa 6–9 minuti dopo. Tra il primo `status` del
booking e il passo successivo passano sempre circa 14 minuti: è il tempo che il Ledger impiega a
rispondere a `prescription` + `agenda` + `world page=1`. Ogni caso fa queste domande per conto
suo, anche se catalogo e agenda sono uguali per tutti i cittadini della stessa procedura.

Effetti visti: 7 liste d'attesa con `S` tra 130 e 286, 3 gruppi di offerte tutte nello stesso
giorno con la stessa dottoressa, 2 journey chiusi a "sto controllando".

## Obiettivo

Il primo messaggio di offerte parte entro pochi secondi dal messaggio del cittadino, senza
aspettare il Ledger, e copre più giorni e i due generi di medico.

Non obiettivi: cambiare hold, commit, ricevuta, cross-ASST, consultorio lato struttura; riaccendere
l'AI; dividere `30_booking.py`.

Da evitare: offrire slot senza aver mai letto il Ledger; scrivere al cittadino una prenotazione
prima del `committed` (regola d'oro invariata); più deploy per questo lavoro.

## Vincoli trovati nel codice

- `city.say` lega ogni messaggio al `need_id` del messaggio in arrivo: non si scrive al Ledger
  "fuori da un caso". Ogni domanda viaggia sul turno di un caso.
- `city.history(peer=LEDGER)` senza `need_id` restituisce i messaggi con il Ledger di **tutti** i
  casi. Quanto è lenta sotto carico non è misurato.
- Tutta la ricerca (`_advance_alone`) legge agenda e catalogo dalle righe del Ledger dentro `chat`
  (`_ledger`, `_latest_slots`, `_all_slot_lines`, `_agenda_now`).
- `_prescription_reply` usa già il `referral` del gp se il Ledger non ha risposto (BK-28).
- Sotto carico la risposta del Ledger arriva dopo minuti: nessun turno può aspettarla (tetto 40 s).

## Strade considerate

1. **Memoria di processo, riempita da ogni risposta del Ledger e iniettata in `chat`** (scelta).
   La ricerca non cambia: all'inizio di `_advance_alone` le righe `agenda` e `slots` in memoria
   vengono aggiunte a `chat` se il caso non le ha. Modifica piccola in un punto solo; i test
   esistenti restano validi.
2. Riscrivere la ricerca su una struttura dati propria (lista di slot, non righe di testo).
   Più pulito, ma tocca le 300 righe di `_advance_alone` il giorno della gara.
3. Solo anticipare le domande al `referral`, senza memoria condivisa. Aiuta, ma ogni caso paga
   ancora il suo giro e i cittadini senza referral (consultorio) non ne beneficiano.

Scelta: la 1, più l'anticipo al `referral` della 3 come modo di tenere calda la memoria.

## Come funziona

**Memoria** (nuova, in `30_booking.py`, limitata, si perde al riavvio come le altre):

- `_WORLD[procedura][pagina]` = riga `slots …` del Ledger con la sua ora reale (`sent_at`).
- `_AGENDA_ROW` = ultima riga `agenda agenda_now=…` con la sua ora reale.
- `_ASKED_AT[chiave]` = quando abbiamo fatto l'ultima domanda, per non ripeterla (una ogni 2 minuti).

**Raccolta** (tre punti, nessuna attesa in più):

- messaggio in arrivo dal Ledger (`slots` o `agenda`): salvato subito, prima di leggere la storia;
- ogni volta che un turno rilegge la storia di un caso: le righe `slots`/`agenda` trovate vengono salvate;
- a memoria vuota o vecchia, su un turno di cittadino o di referral: una sola lettura
  `city.history(LEDGER)` (tutti i casi) per prendere le righe più recenti. Con tetto di tempo (4 s).

**Uso**: all'inizio di `_advance_alone`, se a `chat` manca l'agenda o il catalogo della procedura
e la memoria li ha freschi, le righe vengono aggiunte a `chat` (tutte le pagine in memoria, non
solo la prima). Da lì il codice di oggi prosegue: `_agenda_now` porta avanti l'orologio con il
tempo reale, `fitting` e `_diverse` scelgono su più pagine, quindi su più giorni e medici.

**Freschezza**: catalogo valido 30 minuti reali, agenda 45 (limite già in uso, `_AGENDA_REAL_MAX`).
Oltre, si torna al comportamento di oggi.

**Rinfresco**: a ogni `referral` del gp e a ogni primo messaggio di un cittadino, se l'ultima
domanda è più vecchia di 2 minuti, partono `agenda` e `world procedure=… page=1..4` insieme, senza
aspettare la risposta. La risposta rientra dalla raccolta. Il referral arriva circa 17 minuti prima
del cittadino: quando il cittadino scrive, la memoria è già piena.

**Ricetta**: se in `chat` c'è il referral del gp con procedura e priorità, non si aspetta la
risposta del Ledger sulla ricetta (già previsto da BK-28; oggi però si aspetta comunque un giro).
La domanda `prescription …` parte lo stesso, senza attesa, per scoprire ricette scadute o usate
al turno dopo.

**Slot già presi**: la memoria può avere slot occupati nel frattempo. L'hold viene rifiutato dal
Ledger e il codice di oggi offre il successivo (P-magesh-9). Nessuna prenotazione fantasma: la
ricevuta parte solo dopo `committed`.

## Fix piccoli nello stesso rilascio

- **BK-66** (PR #136): già scritto, va solo unito.
- **`status` "Le ho già mandato i posti liberi"** (`_still_here`): in 3 journey su 3 il cittadino
  risponde "Which offer_id, slot_id?". Il messaggio ripeterà le righe `offer` ancora aperte.
- **Finestra B** (`_rx_deadline`): da capire prima di toccare. Ipotesi: togliamo i minuti reali
  passati × 60 e, con sabato e domenica senza posti, non resta niente, mentre il giudice contava
  22 posti per ASST. Primo passo: leggere in e19 come si conta la finestra e guardare se la
  risposta `prescription` del Ledger porta una data. Se resta un dubbio, non si cambia.

## Confronto con MACH-1.3 (proposta tra squadre del 21/11, compatibile con 1.2)

Letta il 21/11 dalla pagina condivisa da Filippo. È una proposta tra squadre, non una regola degli
organizzatori: dove tocca il punteggio va riletta contro `e19-rules.md`.

- **Nessun conflitto con BK-67.** La memoria riguarda il catalogo locale; MACH-1.3 regola il traffico tra ASST.
- **R1 (la struttura risponde a ogni `need.request` entro 10 s)**: oggi `_partner_request` aspetta
  agenda e catalogo dal Ledger, che sotto carico arrivano dopo minuti. La stessa memoria va usata
  anche lì: entra in BK-67 (Task 4 del piano).
- **R5 (scadenze in ore di agenda esatte, dalla nascita del need = primo messaggio del cittadino al
  gp)**: sostituisce l'ipotesi "dall'emissione della ricetta". Il booking non vede quel messaggio;
  l'ora del `referral` del gp è la stima più vicina. Entra nell'indagine sulla finestra B.
- **R2 (lista d'attesa solo dopo il giro tra le ASST; `S` è calcolato su tutta la città)**: nei 7
  journey con lista d'attesa non è partita nemmeno la domanda di consenso cross-ASST. Va capito
  perché: entra nell'indagine.
- **Fuori da BK-67, caso a parte (BK-68)**: token nuovi (`mach=1.3`, `after=`, `lease_s=`,
  `next_free=`), lease per `request_id`, al massimo 6 slot per offerta, `cancel reason=past` con
  offerte nuove al confirm, e soprattutto l'ordine nuovo del giro: `need.request` con soli criteri
  **prima** del consenso, consenso `cross_asst` chiesto solo al `confirm`. Toglierebbe la domanda
  che genera "Which consent_ref?", ma cambia un comportamento che tocca la riga −2 dell'audit:
  serve la decisione di Filippo dopo aver riletto e19.

## Prove

- `test_brain.py`: controlli `BK-67` — secondo cittadino della stessa procedura riceve offerte senza
  nessuna domanda `world` al Ledger; memoria vecchia → comportamento di oggi; offerte su almeno due
  giorni quando la memoria ha più pagine; hold rifiutato su slot di memoria → nuova offerta.
- `test_replay.py`: un replay dai journey 0003250002 (B, lista d'attesa) e 000351 (D, tutto lunedì).
- `bench_booking.py --calls`: il turno del secondo cittadino non deve contenere attese sul Ledger.
- Misura da fare prima del rilascio: durata di `city.history(LEDGER)` senza `need_id` con `city run`.

## Lasciato a chi implementa

Nomi esatti, dimensione massima delle memorie, numero di pagine da chiedere in anticipo (proposta: 4),
testo dei messaggi. Riga `BK-67` in `CASI.md` e tabella caso → soluzione → logica → test nella PR.

## Rischi

- `city.history(LEDGER)` lenta o enorme: per questo ha un tetto di 4 s ed è solo la terza via di raccolta.
- Più copie del booking in esecuzione: ogni copia ha la sua memoria; funziona lo stesso, solo meno calda.
- Salto dell'agenda al cambio di livello: l'agenda in memoria sarebbe sbagliata finché non arriva il
  rinfresco (al massimo pochi minuti); il cittadino risponde `reason=past` e il codice rilegge (BK-59).
