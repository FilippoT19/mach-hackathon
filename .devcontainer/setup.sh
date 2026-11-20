#!/usr/bin/env bash
set -euo pipefail
[ -f .env ] || cp .env.example .env
# Codespaces secrets win over .env defaults
[ -n "${ANTHROPIC_API_KEY:-}" ] && sed -i "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}|" .env
[ -n "${DATABASE_URL:-}" ] && sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${DATABASE_URL}|" .env
python -m venv .venv && .venv/bin/pip install -q -r backend/requirements-dev.txt
(cd frontend && npm ci)
echo "Ready: run 'make dev' (API :8000, web :3000)"
