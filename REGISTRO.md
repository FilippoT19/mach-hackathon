# Registro dei percorsi — il pilastro delle modifiche

Ogni percorso non pieno (failed, o review sotto +3) va in un **gruppo di causa**. Ogni gruppo ha un
fix (ID di CASI.md) e uno stato. Un gruppo è chiuso solo quando un percorso **dopo** il deploy lo mostra
risolto (need_id di prova).

Stati: `aperto` → `fix su main` → `online (versione)` → `verificato (need_id)` · `non risolto (need_id)`

Aggiornamento: a ogni giro del monitor leggo gli ultimi 60 percorsi, metto i nuovi nel gruppo giusto e
controllo se i gruppi "online" hanno un percorso nuovo che li verifica.

## Gruppi di causa

| # | Causa | Percorsi (need_id finale) | Fix | Stato | Prova |
|---|---|---|---|---|---|
| G1 | Booking muto (22:14–22:51): `failed` senza righe negative, cittadino senza risposta | 103–116, 122, 0002x vari | BK-28 | verificato | 650004 done, 630002 e 280002 booked (booking 1.0.10) |
| G2 | Ciclo offerta/annullo: il cittadino annulla ogni offerta (`reason=deadline`) → `wrong_outcome no_booking` | 129, 119, 0003/0002 (14/20 msg) | BK-29, BK-31, BK-32, Codex P-14/15/26 | online (booking 1.0.10, 01:01) | 000175, 000176 senza raffiche: da confermare a fine percorso |
| G3 | Booking muto vecchio (BK-15, livello 2) | 045–065 | BK-15 | verificato | 069–074 done |
| G4 | Red flag: percorso chiuso al primo messaggio, review gp 0/0/1 (collab 0) | 125, 126, 127, 130, 132, 133 | X-42b (PS più vicino nel primo messaggio) | fix su main, in coda (ship11) | — |
| G5 | **Collaborazione 0 per tutti gli agenti**, anche con referral e avviso all'ospedale. Regola e19: +1 solo per "uno scambio con un altro agente che ha fatto avanzare il need". Nota su 120: il gp "ha contattato il booking" ma C=0; il booking "ha solo risposto". Il referral + "Ricevuto" non fa avanzare niente. | quasi tutti | G5-a booking.notice, G5-b report.notice | online (gp 1.0.8, booking 1.0.10) | review non ancora uscite |
| G6 | Proattività 0 per booking e strutture | 118, 121, 122, 500002 | P-02 (promemoria), X-31 (mappa) | online parziale | da verificare in un percorso `done` dopo 1.0.7 |

## Regole

1. Prima di un fix nuovo, guardo qui se la causa ha già un gruppo: se il fix c'è ma il gruppo non è
   verificato, prima capisco **perché** non funziona (come G4: il fix era online ma il percorso si chiudeva prima).
2. Un fix senza un percorso di prova non è "fatto".
3. CASI.md dice **cosa** abbiamo cambiato; questo registro dice **se ha funzionato**.

| G7 | Booking muto fino a 48 s su catalogo lungo, consenso in italiano a cittadino inglese | 0164 | BK-30 | verificato | 000176, 650004: "sto controllando" subito |
| G8 | Consenso cross_asst dato come data.response: domanda ripetuta (000175, 21 msg) | 000175 | BK-36 | online (booking 1.0.11) | — |
| G9 | Mappa: fermata sempre M5 Ca Granda, porte di riserva sbagliate | — | X-50 | verificato | 000195: indirizzo chiesto, km, fermata metro |
| G11 | "Sto controllando" e poi silenzio: l'avviso contava come offerta aperta | 000180, 000179, 000187, 0001130004, 0001420003, 0000510005, 0000640006, 0001110004, 0001660002 | BK-45 | in PR | — |
| G12 | Offerte fuori da S (lingua, scadenza dalla ricetta, passato) e raffiche offerta/annullo con le altre ASST | 0001660002, 0001110003, 000141, 0001420002, 000147, 0001160002 | BK-46, BK-47, BK-48 | in PR | — |
| G13 | Consenso cross_asst chiesto senza fine ("Which consent_ref?") | 000172, 000160, 000165 | BK-49 (dopo BK-36) | in PR | — |
| G14 | Palpitazioni lette come red flag: 112 invece della ricetta (booking no_booking −1, 11 su 14 percorsi chiusi alle 02:20–02:27) | 0001830004, 0001750007, 0002390004, 000275 | GP-15 | verificato (0001820006: "cuore che batte a mille" → ricetta VIS-CARD in 70 s, gp online dalle ~02:50 locali) | — |
| G15 | Red flag: 112 giusto ma avviso all ospedale non partito ("li avviso io adesso"), domanda sulla posizione mancante | 0000540007 | X-55 non risolto → X-56 | online (gp, 03:40Z) | — |
| G16 | Booking muto o lento: need.request e cancel senza risposta per minuti (0131, 0228, 278) | 0001310003, 0002280005, 000278 | P-magesh-17, OPS-11 | online (booking 1.0.23 03:40Z, 1.0.24 03:55Z); P-17 verificato (0001820007, 0002040005, 0002400003: `status` alle 03:56:55); latenza ancora alta (p50 222 s alle 03:42–03:55, ~15 msg/min) | — |
| G17 | Agenda saltata al cambio livello: offerte fuori scadenza o passate; held in ritardo al consultorio; preferenze di giorni/genere | 0001690003, 0002230003, 0912000308, 0912000304 | BK-59, FA-21, BK-60, BK-60b | online (booking 1.0.24, family 03:55–03:57Z), da verificare | — |
| G18 | Revisione booking: pagina 1 sola, raffica dopo cancel, ricevuta spoglia, orologio, cross-ASST dopo rifiuto, cancel.ack lento | 0912000304 | BK-61 | fix su main (non rilasciato) | — |

Macchina a stati del booking e cause con riga di codice: [docs/booking-flow.md](docs/booking-flow.md). Replay dei percorsi veri: `asst/tests/test_replay.py`.
