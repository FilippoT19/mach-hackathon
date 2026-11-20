#!/usr/bin/env bash
# ship.sh — rilascio veloce. Uso (da asst/, su main aggiornato):
#   ./ship.sh                 # tutti e 5 i ruoli, in parallelo
#   ./ship.sh booking_centre gp
# Fa: seats --brain/--check + test, poi un deploy per ruolo IN PARALLELO (la quota di 5 min
# vale per agente, non per squadra). Ogni ruolo riprova da solo su QUOTA_EXCEEDED, ingress 404
# e health p99; UPSTREAM_TIMEOUT = il server continua, quindi non riprova.
# Alla fine committa le version alzate dalla CLI (solo card.yaml).
set -u
cd "$(dirname "$0")"
PY=~/.local/share/uv/tools/city-cli/bin/python
ROLES=("$@"); [ ${#ROLES[@]} -eq 0 ] && ROLES=(specialist booking_centre gp hospital family_counseling)
LOGS=${SHIP_LOGS:-/tmp/ship-logs}; mkdir -p "$LOGS"

python3 seats.py --brain >/dev/null && python3 seats.py --check || { echo "STOP: brain non compila"; exit 1; }
$PY tests/test_brain.py | tail -1 | grep -q "TUTTI I TEST OK" || { echo "STOP: test falliti"; exit 1; }

one() {
  local role=$1 log="$LOGS/$1.log"
  for try in 1 2 3 4 5; do
    city deploy "$role" >"$log" 2>&1
    grep -q "Status.*promoted" "$log" && { echo "PASS $role $(grep -o '@[0-9.]*' "$log" | tail -1)"; return; }
    grep -q "UPSTREAM_TIMEOUT" "$log" && { echo "IN CORSO $role (UPSTREAM_TIMEOUT, il server continua)"; return; }
    if grep -q QUOTA_EXCEEDED "$log"; then sleep 300
    elif grep -qE "ingress route|p99" "$log"; then sleep 30
    else echo "FAIL $role: $(grep '✗' "$log" | tail -1)"; return; fi
  done
  echo "FAIL $role dopo 5 tentativi: $(grep '✗' "$log" | tail -1)"
}

for r in "${ROLES[@]}"; do one "$r" & sleep 2; done
wait

cd .. && git add asst/*/card.yaml && git diff --cached --quiet || {
  git commit -qm "ship: version alzate dalla CLI dopo il rilascio" && git push -q origin HEAD:main 2>/dev/null \
    || echo "nota: push diretto su main bloccato, le card restano da committare con una PR"
}
