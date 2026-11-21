# Centro prenotazioni: la macchina a stati

Questo documento dice **come deve muoversi** il booking (`asst/brain/parts/30_booking.py`).
Ogni patch futura parte da qui: prima si trova lo stato, poi si cambia il codice di quello stato.
Ogni stato ha un test di replay in `asst/tests/test_replay.py`.

Fonte: 67 percorsi letti dalla console il 21/11 tra le 01:18 e le 01:45 (26 nati dopo il deploy di
booking 1.0.10 delle 01:01, 41 nati prima e usati come contesto). Elenco in fondo.
In quell'ora `main` è passato da 1.0.10 a 1.0.17: la sezione 3 guarda il codice di 1.0.17.

## 1. Fatti della città che comandano il disegno

Questi fatti vengono dal kit (`e19-rules.md`) e dai percorsi veri. Il codice vecchio ne ignorava quattro.

| Fatto | Da dove | Conseguenza |
|---|---|---|
| Un minuto vero è un'ora di agenda (60x). | kit | 16 minuti di silenzio bruciano 16 ore di una finestra B di 48 ore. |
| La finestra della priorità parte **dalla ricetta**, non da adesso. | 0001660002: due offerte rifiutate con `reason=deadline` | Il limite è `emissione + 2 giorni` (B) o `+ 5` (D). |
| Una risposta del Ledger spesso arriva **solo nella history** e non apre un turno. | commento in `00_core.py`, 000180, 000179 | Chi chiede una pagina del catalogo la legge nello stesso turno. |
| Il cittadino sceglie nel turno del **primo** messaggio che nomina un posto. | kit | Un solo messaggio di offerte per volta, massimo 3 righe. |
| Il cittadino annulla **una per una** le offerte fuori dal suo insieme `S`. | 0001420002: 48 annulli | Fuori da `S` non si offre niente: lingua, scadenza, orario passato. |
| Un rifiuto arriva in parole semplici, senza atto e senza il campo chiesto. | kit, 000172 | Dopo la seconda domanda, una risposta senza `consent_ref` è un no. |
| Gli slot locali dentro la finestra finiscono presto (un cittadino al minuto). | `effective_size` 119–152 su 208 | L'altra ASST è il percorso normale dal livello 2, non un'eccezione. |

## 2. Gli stati

Lo stato si ricava dalla history del caso. La memoria del processo (`_SENT`) serve solo per i messaggi
appena mandati che la history non mostra ancora.

```mermaid
stateDiagram-v2
  [*] --> RICETTA: need.request del cittadino
  RICETTA --> RINNOVO: ricetta scaduta
  RICETTA --> LISTA: priorità P
  RICETTA --> LOCALE: ricetta valida
  LOCALE --> OFFERTA: 1-3 slot che vanno bene
  LOCALE --> CONSENSO: catalogo finito, nessuno slot
  OFFERTA --> CONFERMA: confirm
  OFFERTA --> LOCALE: tutte le offerte annullate (una volta)
  OFFERTA --> LISTA: secondo giro tutto annullato
  CONFERMA --> RICEVUTA: booking.receipt dalla struttura
  CONFERMA --> LOCALE: cancel dalla nostra struttura
  CONFERMA --> PARTNER: cancel da un'altra ASST
  CONSENSO --> PARTNER: consent_ref o data.response
  CONSENSO --> LISTA: no, oppure seconda risposta senza consent_ref
  PARTNER --> OFFERTA: 1-3 offerte dei partner che vanno bene
  PARTNER --> LISTA: nessuna offerta adatta, o 3 giri finiti
  RICEVUTA --> MAPPA: data.response con l'indirizzo
  RINNOVO --> [*]
  LISTA --> [*]
  MAPPA --> [*]
```

Esiti finali: `RICEVUTA` (poi `MAPPA`), `LISTA`, `RINNOVO`. Ogni percorso ne ha **uno solo**.

### RICETTA

| | |
|---|---|
| Riceve | `need.request` con `prescription_number`, `lang`, a volte `days`, `gender`. Prima, dal GP, il `referral` con procedura, priorità e preferenze. |
| Fa | Chiede al Ledger `prescription`, `agenda`, `world page=1`. Se il Ledger tace usa procedura e priorità del referral. |
| Risponde | Niente, se la prima pagina basta. `prescription.wait` se dopo tre attese non c'è ancora la procedura. |
| Si ferma | Ricetta scaduta → `RINNOVO` (`data.request purpose=prescription_renewal`, in italiano o inglese). Stato diverso da `issued` → `prescription.note`. Priorità P → `LISTA`. |

### LOCALE (catalogo della nostra ASST)

| | |
|---|---|
| Riceve | Le pagine `slots page=n/m` del Ledger. |
| Fa | Filtra: medico che parla la lingua, giorno del medico, almeno 4 ore di agenda da adesso, **entro la scadenza contata dalla ricetta**, genere, riserva U. Legge la pagina dopo **nello stesso turno**. |
| Risponde | Una volta "sto controllando", solo se serve la pagina 2. |
| Si ferma | Slot trovati → `OFFERTA`. Il Ledger non manda la pagina in 4 attese → `LISTA` (BK-39). Pagine finite, pagina 20, oppure (dalla pagina 2) una pagina tutta oltre la scadenza → `CONSENSO`. Nessun nostro medico parla la lingua → `CONSENSO` senza leggere il catalogo. |

### OFFERTA

| | |
|---|---|
| Manda | **Un** messaggio: fino a 3 righe `offer offer_id= slot_id= …` e una frase nella lingua del cittadino. |
| Riceve `confirm` | → `CONFERMA`. |
| Riceve `cancel` | Risponde subito `cancel.ack`. Se il cittadino tiene ancora un'altra offerta, **nient'altro**. Quando non ne tiene più nessuna: un secondo giro (locale o partner), poi `LISTA`. |
| Riceve altro testo | Ripete le offerte una volta, solo se il messaggio è arrivato dopo le offerte. |
| Mai | Un secondo messaggio di offerte mentre il primo è aperto (nemmeno se arriva un'altra pagina del Ledger). |

### CONFERMA

| | |
|---|---|
| Riceve | `confirm offer_id= consent_ref=`. Senza `consent_ref` chiede `consent purpose=booking` una volta. |
| Fa | Manda `confirm` alla struttura, una volta per slot. Verso un'altra ASST aggiunge `cross_asst_consent_ref`. Intanto chiede indirizzo e accessibilità (`data.request purpose=booking`, X-49). |
| Riceve lo stesso `confirm` di nuovo | Risponde `booking.pending`: mai silenzio, mai un secondo confirm alla struttura. |
| Riceve `cancel` dalla struttura | Lo dice al cittadino **con una frase**, poi torna a `LOCALE` o `PARTNER`. Le offerte ancora valide ripartono nel giro nuovo. |
| Riceve `booking.receipt` | → `RICEVUTA`. |

### CONSENSO (regola P2)

| | |
|---|---|
| Manda | `consent purpose=cross_asst` con una domanda semplice. Mai "mi mandi il riferimento": il cittadino rispondeva `Which consent_ref?` o un `data.response` vuoto. |
| Riceve `consent_ref`, oppure `data.response purpose=cross_asst` (BK-36) | → `PARTNER`. |
| Riceve un no | → `LISTA`. |
| Riceve altro senza `consent_ref` | Ripete la domanda **una volta**. Alla seconda risposta senza riferimento → `LISTA`. |
| Mai | Più di due domande (tre se il cittadino rimanda solo la stessa `need.request`). Nessun dato del cittadino esce prima del sì. |

### PARTNER (altre ASST)

| | |
|---|---|
| Fa | `city.find`, poi una `need.request` con soli criteri a ogni struttura (`service_type`, `procedure`, `priority`, `request_id`, `lang`, `gender`, `days`). Aspetta le risposte nello stesso turno. |
| Sceglie | Fra **tutte** le offerte arrivate: medico che parla la lingua (campo `doctor_lang`, altrimenti la tabella dei medici), non nel passato, entro la scadenza della ricetta. Le prime 3 per data, al massimo 2 per struttura. |
| Manda | **Un** messaggio con quelle offerte e `cross_asst=true`. Le altre restano di riserva. |
| Risposta tardiva di un partner | `offer.ack` al partner. Al cittadino niente, se ha già un messaggio di offerte. |
| `cancel offer_id=none` di un partner | `cancel.ack` al partner. Al cittadino niente. |
| Si ferma | Nessuna offerta adatta e tutti hanno risposto → `LISTA`. Dopo 3 messaggi di offerte → `LISTA`. |

### LISTA (esito finale)

`offer offer_id=wl-<need> waiting_list=true procedure= priority=` con una frase. Una volta per need.
Dopo, un `cancel` del cittadino riceve solo `cancel.ack`.

### RICEVUTA e MAPPA

| | |
|---|---|
| Ricevuta | `booking.receipt booking_id= ledger_ref=` + frase + come arrivare + cosa portare. Una per prenotazione. Poi `booking.notice` al nostro GP. |
| Mappa | Alla risposta sull'indirizzo, una sola frase. L'indirizzo è una via senza coordinate: la distanza è **dalla zona** (Municipio) e la frase lo dice. La metro M5 Ca' Granda si nomina solo per le nostre strutture. |

## 3. Dove il codice di oggi non rispetta la macchina

"Oggi" è `main` a booking 1.0.17 (`b6670f2`, 21/11 circa 02:00). Le righe sono di
`asst/brain/parts/30_booking.py` su quel commit. Ogni riga è riprodotta da un replay che su `main`
fallisce (14 replay su 17, 46 controlli nelle due modalità) e su questo branch passa. Per rivederlo:
`REPLAY_BRAIN=<agent.py di main> python tests/test_replay.py`.

| # | Causa vera | Sintomo visto | Percorsi | Riga responsabile su `main` | Caso | Replay |
|---|---|---|---|---|---|---|
| 1 | Gli avvisi `"wait"` e `"again"` stanno in `sent.offers`. Alla pagina dopo `taken` non è vuoto, il desk crede di avere offerte aperte e si ferma. BK-37 legge la pagina nello stesso turno, ma poi si ferma qui lo stesso. | "Sto controllando" e poi silenzio | 000180, 000179, 000187, 0001130004, 0001110004, 0001420003, 0000510005, 0000640006, 0001660002 (16 min) | r. 994 (`sent.offers.add("wait")`) + r. 979 (`if taken and not replacing`) | BK-45 | r03–r05, r14, r16 (r01, r02 tengono fermo BK-37) |
| 2 | La finestra della priorità è `adesso + giorni`. Deve essere `ricetta + giorni`. `_before_rx_deadline` cerca date che il Ledger non manda. | `cancel … reason=deadline` | 0001660002, 0000930002, 0001190002 | `10_shared.py` r. 326 (`horizon = now + …`), r. 265 | BK-48 | r07 |
| 3 | La domanda di consenso chiede "il riferimento del suo consenso". Il cittadino risponde `Which consent_ref?`. `_desk` ripete la domanda a ogni risposta, senza limite. | Stessa domanda 4–17 volte | 000172, 000160, 000165, 000175 | r. 449 e r. 453 (`_cross_question`), r. 707 | BK-49 | r06, r11 |
| 4 | `_partner_offer` manda il primo gruppo di risposte. Controlla la lingua solo se c'è `doctor_lang`. Niente controllo su passato e scadenza, nessun tetto, nessuna riserva. | `reason=lang`, `reason=past`, decine di annulli | 0001110003, 0001130003, 0000640005, 0000510004, 000141, 0001420002, 000147 | r. 605–645, r. 626 | BK-47 | r03, r05, r08–r10, r14 |
| 5 | `_citizen_cancel` apre una ricerca nuova al primo annullo e manda la lista d'attesa al secondo, anche con un `confirm` in corso. | Lista d'attesa sopra una conferma, raffiche | 0001110003, 000147 | r. 1631–1640 | BK-46 | r08, r09 |
| 6 | Dopo il `cancel` di un partner si passa da `_advance`, che trova "partner già chiesti" e si ferma. | Nessun passo dopo `no_capacity` | 0001110003, 000147, 0001160002 | r. 1290 → r. 482 (`if sent.cross_sent: return True`) | BK-47 | r08, r09 |
| 7 | Un messaggio del cittadino arrivato **prima** delle offerte le fa ripetere. | Offerte doppie dopo il `confirm` | 000177 | r. 980–985 | BK-46 | r03, r12 (con push) |
| 8 | `confirm` rimandato: `_on_confirm` esce senza dire niente se il confirm alla struttura è già partito. | Silenzio, `no_reply` | 000147, 0001160002, 0000930002, 0000910002 | r. 1146 | BK-51 | r13 |
| 9 | Lingua rara: si legge tutto il catalogo (ora 20 pagine) anche se nessun nostro medico la parla. | Attesa lunga prima dell'altra ASST | 0001420003, 000187 | r. 987 | BK-50 | r04, r05 |
| 10 | La distanza è presa dal Municipio ma la frase dice "da lei". | Stessi km per ogni cittadino della zona | 000182, 000185, 000177 | r. 1526, r. 1535 | BK-53 | r15 |
| 11 | `_ask_renewal` ha solo la frase italiana. | Lingua sbagliata | (dal codice) | r. 61–66 | BK-52 | — |

La causa 1 spiega perché il silenzio tornava dopo ogni fix. BK-30 ha aggiunto "sto controllando" per
coprire l'attesa, e proprio quel messaggio fermava la ricerca alla pagina dopo. BK-37 ha tolto
l'attesa della spinta del Ledger, ma il blocco restava.

Già a posto su `main` e tenuti: `data.response purpose=cross_asst` vale come consenso (BK-36), pagina
dopo nello stesso turno (BK-37), 20 pagine (BK-38), pagina persa → lista d'attesa (BK-39), fermata della
metro vera (X-50), ASST giusta per la lingua rara (X-51).

## 4. Cosa resta fuori da questa PR

- **Formato vero del catalogo.** Dalla console non si vedono i messaggi del Ledger. Il simulatore usa
  righe `slot_id= doctor_id= facility= procedure= at= day=` in ordine di data. Se il Ledger ordina in
  un altro modo, la regola "pagina tutta oltre la scadenza → stop" può fermarsi una pagina prima.
  Vale solo dalla pagina 2. Da verificare con `booking.slots` nei log (OPS-07).
- **Perché i partner annullano dopo il nostro `confirm`** (`facility_cancelled`, 000147, 0001160002).
  Non lo sappiamo: serve il loro log. Ora il cittadino riceve subito le offerte dopo.
- **Indirizzo senza coordinate.** La distanza è stimata dal Municipio. Un geocoder esterno non è nel brain.
- **Lingue rare non in tabella** (`am`): senza `doctor_lang` del partner l'offerta non parte. `S` era 5.

## 5. Percorsi letti

Nati dopo le 01:01 (26): 000173, 000174, 000175, 000176, 000177, 000179, 000180, 000181, 000182, 000183,
000185, 000187, 000188, 0000510005, 0000540004, 0000620004, 0000640006, 0000650004, 0001110004,
0001130004, 0001160003, 0001280002, 0001340002, 0001420003, 0001630002, 0001660002.

| Gruppo | Quanti | Esempi |
|---|---|---|
| "Sto controllando" e poi niente | 9 | 000180, 000179, 000187, 0001130004 |
| Consenso chiesto più volte | 2 (+4 nati prima, finiti dopo le 01:01) | 000175, 0001340002, 000160, 000172 |
| Offerte partner rifiutate per scadenza | 1 | 0001660002 |
| Offerta doppia | 1 | 000177 |
| Prenotati o chiusi bene | 10 | 000182, 000185, 000176, 000173 |
| Senza booking (red flag, appena partiti) | 3 | 000181, 0001160003 |

Nati prima (41, contesto): 000131–000172 e i ritorni `…0002`–`…0004`. 21 `failed` con `no_booking −1`,
quasi tutti mal di schiena in inglese o lingua rara passati dalle altre ASST.
