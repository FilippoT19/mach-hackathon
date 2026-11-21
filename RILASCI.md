# Rilasci del booking — una riga per rilascio

CASI.md dice **cosa** cambia, REGISTRO.md dice **se ha funzionato**. Qui c'è **quale build era online e da quando**,
per attribuire un `no_booking` o una ricevuta mancante alla versione che ha preso la decisione.

## Regole

1. **Una sola modifica di comportamento per rilascio.** Le modifiche che risolvono lo stesso problema vanno insieme.
   Sviluppo e test restano in parallelo; in fila ci va solo la pubblicazione.
2. **Si rilascia da `main` pulito** con `./ship.sh`: scrive qui la riga (ora UTC della promozione, versione, build,
   commit). Fix inclusi e comportamento atteso si scrivono a mano prima del rilascio successivo.
   `commit` con `+modifiche` = albero non pulito: quella build non corrisponde a nessun commit.
3. **Build** = `build=b-…` nei log (OPS-14): digest delle parti del brain, scritto in `agent.py` da `seats.py --brain`,
   quindi dentro l'immagine. `python3 seats.py --build-id` lo calcola per l'albero corrente;
   `git log -S'b-…' -- asst/brain/agent.py` trova il commit. `card=` nei log è la versione della card dentro l'immagine.
   La prima riga `build.start` di una build nei log è la prova più vecchia che sta servendo.
4. **Controllo mirato prima del fix successivo**, sul passaggio modificato, senza aspettare la fine della wave:
   cinque casi **nati dopo** la promozione. Per ogni caso: build ai passaggi rilevanti, tempi, punto in cui si ferma.
   I percorsi nati prima del deploy o passati tra più build si segnano **a parte** e non contano.
   - BK-72 (conferme): cinque nuovi `confirm` seguiti fino a ricevuta, rifiuto o timeout
     (`booking.confirm` → `ledger.in` → `booking.receipt.sent`).
   - Ricerca delle ricette B: cinque nuovi need con S > 0, quanti ricevono almeno un'offerta valida (`booking.window`).
   Cinque casi sono un primo controllo di regressione, non una misura.

## Rilasci

| Promozione (UTC) | Agente | Versione | Build | Commit | Fix inclusi | Comportamento atteso | Controllo |
|---|---|---|---|---|---|---|---|
| NON VERIFICABILE. Una build con BK-72 rispondeva già alle 11:12:29Z del 21/11 (`booking.pending slot_id=…` nel percorso …0003520005) | booking_centre | 1.0.34 secondo `city status` alle 11:30Z (card_digest `sha256:94ec991d…`); non so se alle 11:12 era già la 1.0.34 o la 1.0.33 | nessuno (prima di OPS-14); immagine `sha256:e6cff42b…` dalla ricevuta di compliance, che non porta versione né ora | NON VERIFICABILE. Dichiarato nel commit 12cc9af: ramo `giulia/mach-2.0` con main. Il commit di merge 3b5a23d è delle 11:14:23Z, dopo le 11:12:29Z: l'immagine è stata costruita da un albero non ancora committato | dichiarati: BK-72, OPS-13, MACH-2.0, P-magesh-23/24, MACH2-7 (più modifiche di comportamento insieme) | BK-72: una conferma finisce in ricevuta, rifiuto con alternative o `booking.pending` | 25 percorsi con il booking letti alle 11:35Z. Nati dopo le 11:19Z: 9, nessun `confirm` ancora. A cavallo (segnati a parte): 10 con `confirm`, 0 ricevute; 2 `cancel reason=grant_permission_denied` (11:17:31, 11:23:16: il Ledger rifiuta l'hold del booking per permessi), 2 `no_capacity` + nuove offerte, 2 `booking.pending`; 6 confirm delle 11:31:53Z ancora senza risposta. Righe di log: non recuperabili (la console cerca solo negli ultimi ~40 s e rispondeva 503) |
