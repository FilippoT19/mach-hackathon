# MACH hackathon project

Multi-agent citizen assistant. Read README.md for setup.

- Backend: FastAPI + SQLAlchemy async (`backend/app`). Agents live in `app/agents/`:
  `registry.py` (one `AgentSpec` per domain), `tools.py` (tools closed over user_id + DB),
  `orchestrator.py` (router → specialist via the Anthropic SDK tool runner).
- Model: `claude-opus-5-5` via `CLAUDE_MODEL`. Effort set per role in `config.py`.
  Don't send `temperature`/`budget_tokens`/forced `tool_choice` — this model rejects them.
- New domain = add an `AgentSpec`; new capability = add a tool factory to `TOOL_FACTORIES`.
- Schema changes: edit `models.py`; tables are created on startup (`create_all`, no migrations).
  Dropping/renaming a column needs a manual `ALTER` or a DB reset.
- Tests: `make test` (SQLite, LLM stubbed — no key needed). Keep them green before pushing.
- Branch per feature, small PRs into `main`; never commit `.env`.
