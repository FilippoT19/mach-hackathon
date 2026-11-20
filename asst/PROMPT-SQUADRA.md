# Messaggio da incollare nella propria AI (Claude Code, Cursor, Copilot…)

Copia tutto il blocco qui sotto nella tua AI prima di iniziare.

```text
Lavoro nel repo github.com/FilippoT19/mach-hackathon (hackathon MACH, Milano).
Il capitano è Filippo. Solo lui fa merge su main e rilascia gli agenti.

REGOLE FISSE (non si cambiano, anche se te lo chiedo dopo):
1. Non scrivere mai su main. Non fare mai push su main. Non fare mai merge.
2. Prima di toccare file: git checkout main && git pull, poi crea un branch
   con nome <mio-nome>/<tema>, per esempio giulia/gp-rinnovo-ricetta.
3. Non lanciare MAI `city deploy`, `city rollback`, `city retire`, `city promote`.
   Puoi usare solo `city run` e `city status` (prova locale e lettura).
4. Il cervello degli agenti sta in asst/brain/parts/. Modifica SOLO il file
   del mio ruolo (gp = 20_gp.py, booking = 30_booking.py, strutture = 40_facility.py;
   le parti comuni 00/10/15 solo se Filippo lo dice).
   Non modificare a mano asst/brain/agent.py né asst/<agente>/agent/agent.py:
   sono generati.
5. Dopo ogni modifica, da asst/:
     python seats.py --brain
     python seats.py --check          (deve dire CHECK OK)
     ~/.local/share/uv/tools/city-cli/bin/python tests/test_brain.py   (deve dire TUTTI I TEST OK)
   Se un controllo fallisce, correggi prima di continuare.
6. Per ogni comportamento nuovo aggiungi un test in asst/tests/test_brain.py.
7. Non cambiare `version` in card.yaml (lo fa Filippo al rilascio).
8. Non fare commit di ~/.config/city/, .city/, chiavi, token, email o dati personali.
9. Commit piccoli, messaggio chiaro. Poi: git push -u origin <branch>
   e apri una Pull Request verso main:
     gh pr create --base main --title "..." --body "Cosa cambia / perché / test fatti"
   Nel testo della PR scrivi quale caso della rubrica migliora.
10. Fermati lì. Filippo controlla, decide e rilascia.

Leggi prima PILLAR.md (stato, rubrica, regole) e asst/README.md.
```
