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

Stato di ogni proposta (lo aggiorna Filippo/Claude): `nuova` → `accettata (ID CASI)` / `scartata (perché)`.

## Dove cercare i punti persi

1. https://projectnandaitaly.ai/v1/team/journeys → apri un journey chiuso.
2. Guarda `review.agents[].notes`: ogni nota non piena è una proposta possibile.
3. Chiediti: cosa poteva dire in più l'agente? A quale altro agente poteva scrivere? Ha risposto nella lingua giusta?

## Proposte

<!-- aggiungi sotto, la più nuova in alto -->
