# Catalogo in memoria (BK-67) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** il booking manda il primo messaggio di offerte senza aspettare il Ledger, leggendo agenda e catalogo da una memoria di processo condivisa tra i casi.

**Architecture:** una memoria di modulo in `30_booking.py` raccoglie ogni riga `agenda` e `slots` del Ledger che passa da un turno. `_advance_alone` aggiunge quelle righe alla storia del caso quando mancano, e il resto della ricerca resta com'è. Il `referral` del gp e il primo messaggio del cittadino fanno partire le domande di rinfresco senza aspettare la risposta.

**Tech Stack:** Python stdlib + `city_sdk.city`. Test con `FakeCity` (`asst/tests/test_brain.py`) e simulatore (`asst/tests/test_replay.py`).

**Spec:** `docs/superpowers/specs/2026-11-21-catalogo-in-memoria-design.md`

## Global Constraints

- Si modifica solo `asst/brain/parts/`. Dopo ogni modifica, da `asst/`: `python seats.py --brain && python seats.py --check`.
- Il brain importa solo `city_sdk.city` e la libreria standard. Nessun file di dati.
- Mai toccare `Dockerfile` o `city.yaml`. Mai `city deploy`, `city retire`, merge su `main`: li fa Filippo.
- Regola d'oro invariata: `booking.receipt` solo dopo `committed` del Ledger.
- Catalogo in memoria valido **30 minuti reali**; agenda **45** (`_AGENDA_REAL_MAX`, già esistente).
- Rinfresco: al massimo **una volta ogni 120 secondi** per procedura; pagine chieste in anticipo: **1..4**.
- Lettura `city.history(LEDGER)` su tutti i casi: tetto **4 secondi**, al massimo una ogni 120 secondi.
- Ogni memoria nuova è limitata (stesso stile di `_SENT_NEEDS`).
- Riga **BK-67** in `CASI.md`; PR con tabella caso → soluzione → logica → test in italiano. Nessuna riga di attribuzione nei commit o nella PR.
- Comandi di test, da `asst/` (`PY=~/.local/share/uv/tools/city-cli/bin/python`):
  `$PY tests/test_brain.py` → `TUTTI I TEST OK`; `$PY tests/test_journey.py` → `ALL PASS`; `$PY tests/test_replay.py` → `REPLAY OK`.

## Review Focus

1. Riga `slots` in memoria di un'altra procedura (VIS-CARD) usata per un caso VIS-FIS → non deve mai succedere (test in Task 1).
2. Pagina `slots` senza righe slot (`slots page=1/1` vuota) → non si può attribuire a una procedura: non va salvata, e non deve rompere la raccolta (test in Task 1).
3. Riga del Ledger senza `sent_at` (succede nei test e forse in produzione) → l'età si conta da quando l'abbiamo salvata (test in Task 1).
4. Messaggio con mittente che si finge Ledger: la raccolta accetta solo `row.sender == LEDGER` e `row.recipient == agent` (test in Task 1).
5. Il rinfresco scrive al Ledger: non deve far credere a `_desk` che il turno "ha già parlato" (BK-33), altrimenti il cittadino resta senza risposta (test in Task 3).

---

### Task 0: Ramo di lavoro

**Files:** nessuno.

- [ ] **Step 1:** chiedere a Filippo se unire prima la PR #136 (BK-66). Se sì, aspettare il merge e fare `git pull`. Se no, partire da `main` e segnalare nella PR che BK-66 resta a parte.
- [ ] **Step 2:** `git switch -c filippo/bk67-catalogo-memoria` dalla radice del repo.
- [ ] **Step 3:** da `asst/`, lanciare i tre test: devono passare prima di ogni modifica.

---

### Task 1: Memoria e raccolta

**Files:**
- Modify: `asst/brain/parts/30_booking.py` (nuovo blocco subito dopo `_latest_slots`, riga ~83)
- Test: `asst/tests/test_brain.py` (nuova `async def test_bk67(check)`, chiamata in `main()` prima di `print`)

**Interfaces:**
- Produces:
  - `_WORLD: dict[str, dict[int, tuple[Message, float]]]` — procedura → pagina → (riga, `time.time()` al salvataggio)
  - `_AGENDA_ROW: list[tuple[Message, float]]` — vuota o con un solo elemento
  - `_WORLD_TTL = timedelta(minutes=30)`, `_WORLD_PAGES = 4`, `_REFRESH_EVERY = 120.0`
  - `_remember_ledger(rows: Iterable[Message], agent: str) -> None`
  - `_memory_rows(procedure: str, *, at: float | None = None) -> list[Message]` — agenda (se fresca) seguita dalle pagine fresche in ordine di pagina; `at` è `time.time()` di riferimento (per i test)
  - `_row_procedure(text: str) -> str | None` — `procedure=` della prima riga slot di un messaggio `slots`

- [ ] **Step 1: test che falliscono** — in `test_bk67`, con `bk = brain._OUR_AGENTS["booking_centre"]` e una `slot(...)` come quella di `test_bk63`:

```python
brain._WORLD.clear(); brain._AGENDA_ROW.clear()
fis1 = row(LEDGER, bk, "slots page=1/2\n" + slot("A1", "h1", "2026-11-03T10:00:00Z", "tue"), 1)
fis2 = row(LEDGER, bk, "slots page=2/2\n" + slot("B1", "h2", "2026-11-04T10:00:00Z", "wed"), 2)
card = row(LEDGER, bk, "slots page=1/1\n" + slot("C1", "s1", "2026-11-04T10:00:00Z", "wed", proc="VIS-CARD"), 3)
ag = row(LEDGER, bk, "agenda agenda_now=2026-11-02T07:00:00Z", 4)
empty = row(LEDGER, bk, "slots page=1/1", 5)
fake = row("agent:impostore", bk, "slots page=1/1\n" + slot("X1", "h1", "2026-11-03T10:00:00Z", "tue"), 6)
other = row(LEDGER, "agent:altro", "slots page=3/3\n" + slot("Y1", "h1", "2026-11-03T10:00:00Z", "tue"), 7)
brain._remember_ledger([fis1, fis2, card, ag, empty, fake, other], bk)
got = brain._memory_rows("VIS-FIS")
check("BK-67 memoria: agenda + pagine VIS-FIS in ordine", [r.msg_id for r in got] == ["h4", "h1", "h2"], got)
check("BK-67 memoria: mai righe di un'altra procedura", all("VIS-CARD" not in r.text for r in got), got)
check("BK-67 memoria: impostore e destinatario diverso ignorati", "X1" not in str(got) and "Y1" not in str(got), got)
import time as _t
check("BK-67 memoria: catalogo vecchio di 31 minuti non usato",
      [r.msg_id for r in brain._memory_rows("VIS-FIS", at=_t.time() + 31 * 60)] == ["h4"], "")
check("BK-67 memoria: agenda vecchia di 46 minuti non usata",
      brain._memory_rows("VIS-FIS", at=_t.time() + 46 * 60) == [], "")
```

- [ ] **Step 2:** `python seats.py --brain && $PY tests/test_brain.py` → FAIL (`_WORLD` non esiste).
- [ ] **Step 3: implementare** il blocco in `30_booking.py`. Decisioni: una riga più recente della stessa pagina sostituisce la vecchia; l'età si conta da `sent_at` se si legge con `_when`, altrimenti dall'ora di salvataggio; `_WORLD` tiene al massimo 8 procedure e 20 pagine per procedura; `_row_procedure` restituisce `None` per una pagina senza righe slot e quella pagina non si salva.
- [ ] **Step 4:** `python seats.py --brain && python seats.py --check && $PY tests/test_brain.py` → `TUTTI I TEST OK`.
- [ ] **Step 5:** `git add asst && git commit -m "BK-67: memoria di agenda e catalogo del Ledger"`

---

### Task 2: La ricerca legge dalla memoria

**Files:**
- Modify: `asst/brain/parts/30_booking.py` — `_advance_alone` (riga ~1637), nel ciclo `for _pass in range(3)`, subito prima di `agenda = _ledger(chat, "agenda")` (la seconda occorrenza, dopo il controllo `state`)
- Modify: `asst/brain/parts/00_core.py` — `main()`: dopo `case = await city.history(...)`
- Modify: `asst/brain/parts/10_shared.py` — `_until`: dopo `fresh = _keep(fresh, chat)`
- Test: `asst/tests/test_brain.py` (`test_bk67`)

**Interfaces:**
- Consumes: `_remember_ledger`, `_memory_rows` (Task 1)
- Produces: `_with_memory(chat: list[Message], procedure: str) -> list[Message]` — restituisce `chat` più le righe di memoria che mancano: l'agenda solo se `_ledger(chat, "agenda")` è `None`, le pagine solo se `_latest_slots(chat)` è `None`. Mai duplicati di `msg_id`.

- [ ] **Step 1: test che falliscono** (in `test_bk67`, dopo quelli del Task 1; `desk_turn` e `rx_number` sono quelli già usati da `test_bk63`):

```python
# secondo cittadino della stessa procedura: offerte subito, nessuna domanda world/agenda
brain._SENT.clear(); brain._HELD_FOR.clear(); brain._WORLD.clear(); brain._AGENDA_ROW.clear()
p1 = "slots page=1/2\n" + "\n".join(slot(f"A{i}", "h1", f"2026-11-03T1{i}:00:00Z", "tue") for i in range(3))
p2 = "slots page=2/2\n" + "\n".join([slot("B1", "h2", "2026-11-04T10:00:00Z", "wed"), slot("B2", "h2", "2026-11-05T10:00:00Z", "thu")])
brain._remember_ledger([row(LEDGER, bk, "agenda agenda_now=2026-11-02T07:00:00Z", 90), row(LEDGER, bk, p1, 91), row(LEDGER, bk, p2, 92)], bk)
ref = row(brain._OUR_AGENTS["gp"], bk, f"referral prescription_number={rx_number} procedure=VIS-FIS priority=D", 0)
ask = row(CITIZEN, bk, f"Vorrei una visita need.request lang=it prescription_number={rx_number} service_type=hospital.physiatry", 1)
city = FakeCity(bk)
await desk_turn(city, ask, [ref, ask])
offers = [t for t in to(city, CITIZEN) if t.startswith("offer ")]
check("BK-67 memoria calda: UN messaggio di offerte nello stesso turno", len(offers) == 1, city.sent)
check("BK-67 memoria calda: nessuna domanda world page=1 al Ledger",
      "world procedure=VIS-FIS page=1" not in to(city, LEDGER), to(city, LEDGER))
check("BK-67 offerte su almeno due giorni e due medici",
      len(offers) == 1 and "agenda_day=tue" in offers[0] and ("agenda_day=wed" in offers[0] or "agenda_day=thu" in offers[0])
      and "h1" in offers[0] and "h2" in offers[0], offers)
# memoria vuota: comportamento di oggi
brain._SENT.clear(); brain._WORLD.clear(); brain._AGENDA_ROW.clear()
city = FakeCity(bk)
await desk_turn(city, ask, [ask])
check("BK-67 memoria vuota: domande al Ledger come prima",
      "world procedure=VIS-FIS page=1" in to(city, LEDGER) and "agenda" in to(city, LEDGER), to(city, LEDGER))
# raccolta dalla storia di un caso
brain._WORLD.clear(); brain._AGENDA_ROW.clear()
class Hist(FakeCity):
    async def history(self, peer=None, *, need_id=None):
        return [row(LEDGER, bk, p1, 91)]
await brain._until(Hist(bk), "N-1", [], lambda rows: True)
check("BK-67 raccolta: la storia riletta riempie la memoria", 1 in brain._WORLD.get("VIS-FIS", {}), brain._WORLD)
```

- [ ] **Step 2:** `python seats.py --brain && $PY tests/test_brain.py` → FAIL sui controlli BK-67 nuovi.
- [ ] **Step 3: implementare.**
  - `_with_memory` in `30_booking.py`; chiamarla nel punto indicato con `chat = _with_memory(chat, procedure)`.
  - Se dopo l'iniezione le offerte non coprono più pagine, usare `_all_slot_lines(chat, agent)` come fonte dei candidati del primo messaggio, come già fa il passo dopo i cancel (BK-63). Verificare leggendo il codice tra le righe ~1780 e ~1850: il test "almeno due giorni e due medici" decide.
  - In `main()` (`00_core.py`): per i ruoli `booking_centre` e `family_counseling`, `_remember_ledger([message], city.agent_id)` prima della lettura della storia e `_remember_ledger(case, city.agent_id)` dopo.
  - In `_until` (`10_shared.py`): `_remember_ledger(fresh, city.agent_id)` dopo `_keep`. `_remember_ledger` è definita in `30_booking.py`: le parti sono unite in un solo file, quindi il nome esiste a runtime.
- [ ] **Step 4:** `python seats.py --brain && python seats.py --check`, poi i tre test → tutti verdi. Se un test vecchio cambia esito perché la memoria resta piena tra un test e l'altro, aggiungere `brain._WORLD.clear(); brain._AGENDA_ROW.clear()` dove quel test azzera `_SENT`, e in `reset()` di `test_replay.py`.
- [ ] **Step 5:** `git add asst && git commit -m "BK-67: la ricerca del booking legge agenda e catalogo dalla memoria"`

---

### Task 3: Rinfresco e riscaldamento

**Files:**
- Modify: `asst/brain/parts/30_booking.py` — nuovo `_refresh_memory`, nuovo `_warm_memory`; chiamate in `_on_referral` (riga ~1484, dopo il `referral.ack`) e in `_advance_alone` (subito prima di `_with_memory`)
- Test: `asst/tests/test_brain.py` (`test_bk67`)

**Interfaces:**
- Consumes: `_remember_ledger`, `_memory_rows`, `_WORLD_PAGES`, `_REFRESH_EVERY`, `_ledger_asks`
- Produces:
  - `_ASKED_AT: dict[str, float]` — chiave `"agenda"`, `"world:<procedura>"`, `"warm"`
  - `async _refresh_memory(city: City, message: Message, procedure: str | None) -> None` — manda `agenda` e `world procedure=<p> page=1` … `page=4` insieme, senza aspettare risposte, solo se l'ultima richiesta della stessa chiave ha più di 120 s. Non lascia `LEDGER` in `_SAID` se non c'era già (stesso schema usato intorno a `_fresh_agenda`).
  - `async _warm_memory(city: City) -> None` — una `city.history(LEDGER)` con `asyncio.wait_for(…, 4)`, poi `_remember_ledger`; al massimo una ogni 120 s; ogni errore o timeout è ignorato.

- [ ] **Step 1: test che falliscono:**

```python
brain._WORLD.clear(); brain._AGENDA_ROW.clear(); brain._ASKED_AT.clear()
city = FakeCity(bk)
await brain._on_referral(city, ref, [ref])
asks = to(city, LEDGER)
check("BK-67 referral: parte il rinfresco di agenda e 4 pagine",
      "agenda" in asks and all(f"world procedure=VIS-FIS page={n}" in asks for n in (1, 2, 3, 4)), asks)
check("BK-67 referral: l'ack al gp parte comunque", any(t.startswith("referral.ack") for t in to(city, brain._OUR_AGENTS["gp"])), city.sent)
city2 = FakeCity(bk)
await brain._refresh_memory(city2, ref, "VIS-FIS")
check("BK-67 rinfresco: non si ripete entro 120 secondi", to(city2, LEDGER) == [], to(city2, LEDGER))
# memoria fredda: una lettura di tutti i casi la riempie, e le offerte partono nello stesso turno
brain._SENT.clear(); brain._WORLD.clear(); brain._AGENDA_ROW.clear(); brain._ASKED_AT.clear()
class All(FakeCity):
    async def history(self, peer=None, *, need_id=None):
        if peer == LEDGER and need_id is None:
            return [row(LEDGER, bk, "agenda agenda_now=2026-11-02T07:00:00Z", 90), row(LEDGER, bk, p1, 91), row(LEDGER, bk, p2, 92)]
        return []
city = All(bk)
await desk_turn(city, ask, [ref, ask])
check("BK-67 memoria fredda: offerte dalla storia del Ledger di tutti i casi",
      len([t for t in to(city, CITIZEN) if t.startswith("offer ")]) == 1, city.sent)
# il rinfresco non rende muto il turno (BK-33)
brain._SENT.clear(); brain._WORLD.clear(); brain._AGENDA_ROW.clear(); brain._ASKED_AT.clear()
city = FakeCity(bk)
await brain._desk(city, ask, [ask], hold_self=False, fixed=None)
check("BK-67 rinfresco: il cittadino riceve comunque una riga", len(to(city, CITIZEN)) >= 1, city.sent)
```

- [ ] **Step 2:** `python seats.py --brain && $PY tests/test_brain.py` → FAIL.
- [ ] **Step 3: implementare.** In `_advance_alone`: se `_memory_rows(procedure)` non ha pagine, `await _warm_memory(city)`; poi `await _refresh_memory(city, message, procedure)`; poi `_with_memory`. In `_on_referral`: `_refresh_memory` dopo l'ack, con la procedura del referral (se manca, solo `agenda`). Il controllo BK-63 "primo giro di Ledger: ricetta, agenda e catalogo insieme" confronta un insieme esatto di domande: aggiornarlo per accettare anche le pagine 2–4 del rinfresco e dirlo nella riga di `CASI.md`.
- [ ] **Step 4:** i tre test → verdi. Poi `$PY tests/bench_booking.py --calls --text`: nel turno a memoria calda non devono comparire attese sul Ledger prima del messaggio di offerte. Annotare il numero di chiamate nella PR.
- [ ] **Step 5:** `git add asst && git commit -m "BK-67: rinfresco al referral e riscaldamento della memoria"`

---

### Task 3b: Anche la struttura risponde ai partner dalla memoria (MACH-1.3 R1)

**Files:**
- Modify: `asst/brain/parts/40_facility.py` — `_partner_request` (riga ~679)
- Modify: `asst/brain/parts/00_core.py` — la raccolta in `main()` vale anche per i ruoli `hospital` e `specialist`
- Test: `asst/tests/test_brain.py` (`test_bk67`)

**Interfaces:**
- Consumes: `_with_memory`, `_remember_ledger`, `_refresh_memory` (Task 1–3)
- Produces: nessuna interfaccia nuova.

- [ ] **Step 1: test che fallisce** (`hospital` è l'id del nostro ospedale già usato da `test_bk63`):

```python
brain._WORLD.clear(); brain._AGENDA_ROW.clear(); brain._ASKED_AT.clear(); brain._PARTNER_DONE.clear()
brain._remember_ledger([row(LEDGER, hospital, "agenda agenda_now=2026-11-02T07:00:00Z", 90), row(LEDGER, hospital, p2, 92)], hospital)
req = row("agent:partner-bk", hospital, "need.request mach=1.3 service_type=hospital.physiatry procedure=VIS-FIS priority=D "
          "deadline=2026-11-06T18:00 lease_s=480 request_id=ring-N-77", 1)
city = FakeCity(hospital)
await brain._partner_request(city, req, [req])
out = to(city, "agent:partner-bk")
check("BK-67 struttura: offerta al partner dalla memoria, nello stesso turno",
      len(out) == 1 and out[0].startswith("offer ") and "request_id=ring-N-77" in out[0] and "slot_id=B1" in out[0], city.sent)
```

- [ ] **Step 2:** `python seats.py --brain && $PY tests/test_brain.py` → FAIL (oggi senza risposta del Ledger esce `cancel reason=no_availability`).
- [ ] **Step 3: implementare.** In `_partner_request`: `chat = _with_memory(chat, procedure)` prima delle domande al Ledger; se agenda e catalogo ci sono già, non si aspetta (`_until` si salta) e parte solo il rinfresco. I token sconosciuti (`mach=`, `lease_s=`, `after=`) si ignorano come oggi. Nessun altro cambiamento di formato: è BK-68.
- [ ] **Step 4:** i tre test → verdi.
- [ ] **Step 5:** `git add asst && git commit -m "BK-67: la struttura risponde ai partner dalla memoria"`

---

### Task 4: Lo `status` con offerte aperte ripete le offerte

**Files:**
- Modify: `asst/brain/parts/30_booking.py` — `_still_here`, ramo `elif open_offer` (riga ~1364)
- Test: `asst/tests/test_brain.py` (`test_bk67`)

**Interfaces:**
- Consumes: `_open_offers(chat, agent, citizen)`, `_fit`
- Produces: nessuna interfaccia nuova.

- [ ] **Step 1: test che fallisce:**

```python
offer = "\n".join(f"offer offer_id=of-A{i} slot_id=A{i} doctor_id=asst-niguarda-h1 facility={hospital} procedure=VIS-FIS "
                  f"agenda_date=2026-11-03T1{i}:00:00Z agenda_day=tue" for i in range(3)) + "\nEcco i posti liberi."
chat = [ask, row(bk, CITIZEN, offer, 5), row(CITIZEN, bk, "cancel offer_id=of-A0 reason=day", 6)]
again = row(CITIZEN, bk, "Allora? Mi fate sapere?", 7)
city = FakeCity(bk)
await brain._still_here(city, again, [*chat, again], fixed=None)
out = to(city, CITIZEN)
check("BK-67 status con offerte aperte: ripete le righe offer ancora aperte",
      len(out) == 1 and "offer_id=of-A1" in out[0] and "slot_id=A1" in out[0] and "offer_id=of-A2" in out[0], out)
check("BK-67 status con offerte aperte: non ripete l'offerta annullata", "of-A0" not in out[0], out)
check("BK-67 status con offerte aperte: resta sotto 2000 caratteri", len(out[0]) <= 2000, len(out[0]))
```

- [ ] **Step 2:** `python seats.py --brain && $PY tests/test_brain.py` → FAIL (oggi il testo è `status Le ho già mandato…`).
- [ ] **Step 3: implementare.** Il messaggio diventa: le righe `offer …` originali delle offerte ancora aperte (prese dai nostri messaggi nella storia, una per `offer_id`), poi una frase. Testo: IT "Le rimando i posti ancora liberi per lei: mi risponda con quello che preferisce e lo blocco subito." / EN "Here are the appointments still open for you: reply with the one you prefer and I will lock it at once." Se nessuna riga originale si trova nella storia, resta il testo di oggi.
- [ ] **Step 4:** i tre test → verdi. Il replay conta i messaggi di offerte (`max_offer_messages`): se un replay fallisce per questo, alzare il limite solo in quel replay e scriverlo in `CASI.md`.
- [ ] **Step 5:** `git add asst && git commit -m "BK-67: lo status con offerte aperte ripete le offerte"`

---

### Task 5: Finestra B — solo indagine

**Files:** nessuna modifica al brain in questo task.

- [ ] **Step 1:** leggere nel kit (`gh api repos/projectnandaitaly/mach-hackathon-kit/contents/docs/kit/e19-rules.md -H "Accept: application/vnd.github.raw"`) come si conta la finestra di priorità e che campi ha la risposta `prescription` del Ledger.
- [ ] **Step 2:** rifare a mano il conto di `_rx_deadline` per il journey `N-2026-11-02-8909120003250002` (ricetta 04:46:30 UTC, offerta 05:18:58, priorità B, offerte D dello stesso minuto tutte al 2026-12-07) e dire quale scadenza usciva.
- [ ] **Step 2b:** MACH-1.3 R5 dice: ore di agenda esatte dalla nascita del need (primo messaggio del cittadino al gp), B = 48 ore. Confrontare con e19 e con l'ancora usata da `_rx_deadline` (primo messaggio del caso che nomina la ricetta).
- [ ] **Step 2c:** capire perché nei 7 journey con lista d'attesa (0002150006, 0003250002, 0003300002, 0003000003, 0001670005, 0002600003, 000352) non è partita la domanda `consent purpose=cross_asst`: seguire `_after_local` → `_cross_asst` → `_relaxed` e gli altri punti che chiamano `_relaxed`, e dire quale ramo ha portato alla lista d'attesa (MACH-1.3 R2: mai prima del giro tra le ASST).
- [ ] **Step 3:** scrivere a Filippo tre righe: cosa dice la regola, cosa calcoliamo, differenza. Se la regola è chiara e il codice sbaglia, proporre il fix come caso a parte (**BK-68**) con il suo test. Se resta un dubbio, non cambiare niente.

---

### Task 6: Replay, registro, PR

**Files:**
- Modify: `asst/tests/test_replay.py` — due replay nuovi (`r19`, `r20`) aggiunti all'elenco in fondo
- Modify: `CASI.md` — riga BK-67
- Modify: file generati da `seats.py`

- [ ] **Step 1: replay `r19`** (da 0003250002: mal di schiena, priorità B, `lang=it`). Due cittadini uno dopo l'altro sullo stesso `Sim`; il Ledger risponde solo in history. Atteso per il secondo: offerte nello stesso turno del suo `need.request`, nessuna domanda `world` sua.
- [ ] **Step 2: replay `r20`** (da 000351: ginocchio, priorità D, "solo in giorni specifici"). Catalogo su due pagine, pagina 1 tutta lunedì con h1. Memoria calda. Atteso: il primo messaggio di offerte contiene almeno due `agenda_day` diversi.
- [ ] **Step 3:** `$PY tests/test_replay.py` → `REPLAY OK`; poi gli altri due test e `python seats.py --check`.
- [ ] **Step 4:** riga **BK-67** in `CASI.md` con: caso (16 journey W01QQQ, 04:45–05:26 UTC, need_id elencati), rischio (nessuna prenotazione con `S` non vuoto), soluzione, logica, test, stato "in PR". Aggiornare la riga BK-63 se il suo controllo è cambiato.
- [ ] **Step 5:** `git add -A && git commit -m "BK-67: replay r19 r20 e riga in CASI.md"`, `git push -u origin filippo/bk67-catalogo-memoria`, poi `gh pr create` verso `main` con la tabella caso → soluzione → logica → test in italiano e la nota: "da misurare prima del deploy: durata di `city.history(LEDGER)` senza `need_id`". **Nessun merge, nessun deploy.**
