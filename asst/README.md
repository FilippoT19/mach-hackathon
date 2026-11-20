# ASST: i 5 agenti per Milano Agentic City

Questa cartella è quella che conta per la classifica. Gli agenti girano sulla piattaforma
della città (`city deploy`), non sul nostro backend FastAPI.

**Leggete prima [PILLAR.md](../PILLAR.md):** stato della gara, link, rubrica, regole, imprevisti, logica degli agenti.

## Dove si lavora

Un solo brain serve tutti e 5 gli agenti (legge il ruolo dalla card). Il brain è diviso in parti, **una per ruolo**:

**Filippo è responsabile di tutti i file.** Gli altri lavorano in coppia con lui e danno consigli.

| File | Cosa contiene | Responsabile · in coppia con |
|---|---|---|
| `brain/parts/00_core.py` | Avvio, costanti (medici, protocolli, red flag), smistamento per ruolo | Filippo |
| `brain/parts/10_shared.py` | Funzioni comuni: token, storia del caso, filtro degli slot | Filippo |
| `brain/parts/15_voice.py` | `city.llm`: capire il sintomo, frasi umane, pulizia delle frasi | Filippo · Giulia (testi) |
| `brain/parts/20_gp.py` | Medico di base | Filippo · Giulia |
| `brain/parts/30_booking.py` | Centro prenotazioni (e prenotazione del consultorio) | Filippo · Magesh |
| `brain/parts/40_facility.py` | Ospedale, specialista, consultorio | Filippo |

**Modificate solo `brain/parts/`.** `brain/agent.py` e `<agente>/agent/agent.py` sono **generati**: non toccateli a mano.

## Come lavoriamo (regola d'oro: Filippo controlla tutto prima della piattaforma)

1. Un branch per modifica: `git checkout -b gp/rinnovo-ricetta`.
2. Modificate il vostro file in `brain/parts/`.
3. Generate e controllate:
   ```bash
   cd asst
   python seats.py --brain                                        # unisce le parti e copia nei 5 agenti
   python seats.py --check                                        # deve dire CHECK OK
   ~/.local/share/uv/tools/city-cli/bin/python tests/test_brain.py   # deve dire TUTTI I TEST OK
   ```
4. Provate in locale, se volete: `city run gp` (chat come `citizen`, `agent` o `ledger`; non tocca la città).
5. Aprite una PR verso `main`, oppure mandate la proposta a Filippo. **Filippo** decide, la legge e la unisce.
6. **Solo Filippo** fa il merge su `main` e `city deploy`. Nessun altro rilascia sulla piattaforma.

Messaggio pronto da incollare nella propria AI: [PROMPT-SQUADRA.md](PROMPT-SQUADRA.md).

## Comandi di rilascio (solo Filippo)

```bash
cd ~/mach-hackathon/asst
git checkout main && git pull
python seats.py --check
./ship.sh                            # test + deploy in parallelo di tutti i ruoli, retry automatico
./ship.sh booking_centre             # solo i ruoli indicati
city deploy gp                       # a mano: solo il ruolo cambiato; specialist PRIMA di hospital
city status agent:gp
city rollback agent:gp --to 1.0.1    # se la versione nuova va male
```

Ogni deploy dura circa 2 minuti e deve chiudere con `released`. Dopo il deploy committate la `version` aggiornata in `card.yaml`.
**Mai** `city retire`: l'agente non si può più riusare. **Mai** committare `~/.config/city/`.

## Setup iniziale (già fatto il 20/11)

```bash
city login
cd asst
city init agent booking_centre   # e hospital, gp, specialist, family_counseling
python seats.py                  # ruoli nelle card + brain
city deploy specialist           # poi hospital, booking_centre, gp, family_counseling
```
