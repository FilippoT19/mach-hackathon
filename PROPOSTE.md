# PROPOSTE — casi e soluzioni dalla squadra (niente codice)

Qui la squadra scrive i casi. **Non si scrive codice nel brain.** Filippo e Claude leggono, decidono e
implementano; il caso accettato diventa una riga in [CASI.md](CASI.md) con un ID.

## Come si scrive una proposta (copia il blocco)

```
### P-<tuo nome>-<n>: <titolo corto>
- Journey: N-...-000123 (se c'è) — ruolo: gp / booking_centre / hospital / specialist / family_counseling
- Cosa fa il cittadino: <il messaggio, o il riassunto>
- Cosa risponde oggi il nostro agente: <frase, oppure "niente">
- Review / punti persi: <proactivity/collaboration/domain e la nota, se c'è>
- Cosa dovrebbe fare: <la frase da dire, a quale agente scrivere, quali campi `chiave=valore`>
- Test a parole: "dato <messaggio>, mi aspetto <risposta>"
- Priorità secondo te: P0 (agente muto, 112) / P1 (punti persi spesso) / P2 (raro)
```

Stato di ogni proposta (lo aggiorna Filippo/Claude), sulla riga del titolo:
- `[ ] nuova` → Claude la legge al primo controllo (ogni 5 minuti su `main`).
- `[~] in lavoro (ID CASI)` → accettata, fix in corso.
- `[x] risolta (ID CASI, versione online)` → fix online e verificato nei journey.
- `[-] scartata (perché)`.

**Ognuno scrive solo nel proprio file**, così due persone non vanno mai in conflitto:
[giulia](proposte/giulia.md) · [francesco](proposte/francesco.md) · [magesh](proposte/magesh.md) · [filippo](proposte/filippo.md).
Nuovo membro: crea `proposte/<nome>.md`. Si scrive con l'editor di GitHub (matita → "Commit directly to main" è bloccato: scegli "Create a new branch" e apri la PR) oppure con una PR. Le PR che toccano solo `proposte/` vengono unite subito.
In questo file restano solo il modello e lo storico.

## Dove cercare i punti persi

1. https://projectnandaitaly.ai/v1/team/journeys → apri un journey chiuso.
2. Guarda `review.agents[].notes`: ogni nota non piena è una proposta possibile.
3. Chiediti: cosa poteva dire in più l'agente? A quale altro agente poteva scrivere? Ha risposto nella lingua giusta?

## Proposte

<!-- aggiungi sotto, la più nuova in alto -->

### [x] P-giulia-1: booking completo (rinnovo, giorni preferiti, fuori ASST) — risolta (GP-10/BK-11/BK-12, in deploy 20/11 sera)
- Passi 1, 2, 3, 5, 6, 7, 8 già coperti; mancavano rinnovo, `days` e ricerca cross-ASST: portati dal suo branch.
