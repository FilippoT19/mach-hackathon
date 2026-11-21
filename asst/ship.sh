#!/usr/bin/env bash
# ship.sh — rilascio veloce. Uso (da asst/, su main aggiornato):
#   ./ship.sh                 # tutti e 5 i ruoli, in parallelo
#   ./ship.sh booking_centre gp
# Fa: seats --brain/--check + test, poi un deploy per ruolo IN FILA, nell'ordine dato (il primo
# è il più urgente). La quota è PER SQUADRA: un deploy ogni 5 minuti, quindi 5 ruoli = 25 min.
# Mandate solo i ruoli che cambiano davvero. Ogni ruolo riprova da solo su QUOTA_EXCEEDED,
# ingress 404 e health p99; UPSTREAM_TIMEOUT = il server continua, quindi non riprova.
# Alla fine committa le version alzate dalla CLI (card.yaml) e la riga in RILASCI.md (OPS-14).
set -u
cd "$(dirname "$0")"
PY=~/.local/share/uv/tools/city-cli/bin/python
ROLES=("$@"); [ ${#ROLES[@]} -eq 0 ] && ROLES=(specialist booking_centre gp hospital family_counseling)
LOGS=${SHIP_LOGS:-/tmp/ship-logs}; mkdir -p "$LOGS"

python3 seats.py --brain >/dev/null && python3 seats.py --check || { echo "STOP: brain non compila"; exit 1; }
$PY tests/test_brain.py | tail -1 | grep -q "TUTTI I TEST OK" || { echo "STOP: test falliti"; exit 1; }

# OPS-14: id della build (digest delle parti, scritto nel brain: lo stesso che compare nei log come
# build=...) e commit da cui si rilascia; "+modifiche" se l'albero non è pulito.
BUILD=$(python3 seats.py --build-id)
COMMIT=$(git rev-parse --short HEAD)$(git diff --quiet HEAD -- . 2>/dev/null || echo "+modifiche")

one() {
  local role=$1 log="$LOGS/$1.log"
  for try in 1 2 3 4 5 6 7 8; do
    city deploy "$role" >"$log" 2>&1
    grep -q "Status.*promoted" "$log" && {
      local ver; ver=$(grep -o '@[0-9.]*' "$log" | tail -1)
      echo "PASS $role $ver build=$BUILD commit=$COMMIT"
      # OPS-14: una riga per rilascio in RILASCI.md (fix e comportamento atteso si scrivono a mano).
      echo "| $(date -u +%FT%TZ) | $role | ${ver#@} | $BUILD | $COMMIT | DA SCRIVERE | DA SCRIVERE | da fare |" >> ../RILASCI.md
      return; }
    grep -q "UPSTREAM_TIMEOUT" "$log" && { echo "IN CORSO $role (UPSTREAM_TIMEOUT, il server continua)"; return; }
    if grep -q QUOTA_EXCEEDED "$log"; then sleep 60
    elif grep -qE "ingress route|p99" "$log"; then sleep 30
    else echo "FAIL $role: $(grep '✗' "$log" | tail -1)"; return; fi
  done
  echo "FAIL $role dopo 8 tentativi: $(grep '✗' "$log" | tail -1)"
}

for r in "${ROLES[@]}"; do one "$r"; done

cd .. && git add asst/*/card.yaml RILASCI.md && git diff --cached --quiet || {
  git commit -qm "ship: version alzate dalla CLI dopo il rilascio" && git push -q origin HEAD:main 2>/dev/null \
    || echo "nota: push diretto su main bloccato, le card restano da committare con una PR"
}
