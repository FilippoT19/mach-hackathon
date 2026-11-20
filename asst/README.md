# ASST: i 5 agenti per Milano Agentic City

Questa cartella è quella che conta per la classifica. Gli agenti girano sulla piattaforma
della città (`city deploy`), non sul nostro backend FastAPI.

- `brain/agent.py`: **un solo brain per tutti e 5 i ruoli** (legge il ruolo dalla card).
  Parte dall'esempio ufficiale `templates/examples/agent.py` del kit, che copre i livelli 1–3.
  Si modifica solo qui, poi si ricopia nelle 5 cartelle con `python seats.py --brain`.
- `seats.py`: imposta `role` e `capabilities` nelle 5 card e copia il brain.
- Le 5 cartelle agente (`gp/`, `booking_centre/`, `hospital/`, `specialist/`,
  `family_counseling/`) le crea `city init` dopo il login, con gli id veri della squadra.

## Setup (una persona sola, il team leader, sul laptop)

```bash
uv tool install city-cli        # oppure: uv tool upgrade city-cli
city login                      # deve finire con "Signed in as <squadra>"
cd asst
city init agent booking_centre
city init agent hospital
city init agent gp
city init agent specialist
city init agent family_counseling
python seats.py                 # imposta i ruoli + copia il brain
for a in booking_centre hospital gp specialist family_counseling; do city card validate $a; done
city deploy specialist          # specialist PRIMA di hospital
city deploy hospital
city deploy booking_centre
city deploy gp
city deploy family_counseling
city status
```

Ogni deploy dura circa 2 minuti e deve chiudere con `released`. Poi committate le 5 cartelle
(contengono solo card, yaml e brain: nessun segreto). **Mai** committare `~/.config/city/`.

## Ciclo di lavoro in gara

```bash
# 1. modificare asst/brain/agent.py
python seats.py --brain
city run gp                     # test locale in chat (citizen / agent / ledger)
city deploy gp                  # rilascia solo il ruolo cambiato
city rollback agent:gp --to 1.0.1   # se la versione nuova va male
```

**Mai** `city retire`: l'agente non si può più riusare.
