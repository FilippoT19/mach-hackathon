# MACH (Milano Agentic City Hackathon): multi-agent citizen assistant

Event: Fri 20 Nov 2026 (challenge reveal 16:40, coding starts 20:00, overnight online) → Sat 21 Nov (10:00–16:00 final coding and submission, pitches 16:00).

Pre-built foundation so we can start coding the minute the challenge is announced.
A **router agent** reads each message and hands it to a **specialist agent** (health,
municipal, state/public-admin, general). Each specialist runs a Claude tool loop with
tools that read and write **that user's** state: tasks, long-term memories, and conversations
in Postgres. Swap or add domains in `backend/app/agents/registry.py` once we know the theme.

```
frontend (Next.js :3000) ──► api (FastAPI :8000) ──► router (Claude) ──► specialist agent (Claude + tools)
                                     │                                          │
                                     └──────────── Postgres 16 + pgvector ◄─────┘   Redis (queues/cache)
```

## Start coding in the cloud (nothing runs on your laptop)

1. Open the repo on GitHub → **Code → Codespaces → Create codespace on main**.
   The devcontainer installs Python, Node, Docker and Claude Code, starts Postgres and Redis,
   and installs every dependency.
2. In the codespace terminal, run `make data` once (imports about 5,400 real Milan places), then `make dev`. The web app opens on port 3000 and the API runs on 8000 (`/docs` = Swagger).
3. Run `make test` before pushing. It uses SQLite and stubs the LLM, so it needs no key.

Each teammate gets their own codespace (own DB and ports), and everyone shares code through branches and PRs.
To show someone your running app, go to the Ports tab, right-click the port, and set **Port visibility → Public**.

## Secrets

Set these once in **GitHub → repo Settings → Secrets and variables → Codespaces**.
They get injected into every teammate's codespace.

| Secret | What |
|---|---|
| `ANTHROPIC_API_KEY` | Team key from console.anthropic.com |
| `DATABASE_URL` | *(optional)* shared cloud Postgres URL, `postgresql+asyncpg://…`. Without it each codespace uses its own local DB |

## Shared cloud database (for the demo / shared data)

Create a free **Supabase** project (it includes Postgres, pgvector, auth, storage, and a dashboard). Then go to
Project Settings → Database → Connection string (URI) and change `postgresql://` to
`postgresql+asyncpg://`. Put the result in the `DATABASE_URL` secret. Tables get created on the first API start.

## Deploy (for judging)

- **API**: Render → New → Blueprint → this repo (`render.yaml`). Set `ANTHROPIC_API_KEY`,
  `DATABASE_URL`, and `CORS_ORIGINS` (= the frontend URL).
- **Web**: Vercel → Import repo → Root directory `frontend` → env `NEXT_PUBLIC_API_URL` = API URL.

## Milan open data

`make data` downloads official datasets from dati.comune.milano.it (pharmacies, metro and
bus/tram stops, AMSA recycling centres, case dell'acqua, street markets, MM help desks) into the
`places` table. Agents query it with the `find_places` tool (e.g. "nearest pharmacy to Loreto").
To add a dataset, add a `Dataset(...)` line in `backend/app/opendata.py` (the portal has 2,600+ datasets).

## API

| Method | Path | |
|---|---|---|
| GET | `/health` | DB check + whether an LLM key is configured |
| GET | `/agents` | specialist catalog |
| POST | `/users` | `{name, email?, profile?}` |
| GET | `/users/{id}/dashboard` | the user's tasks and memories |
| GET | `/places?category=pharmacy&near=Duomo` | Milan points of interest (also for maps) |
| POST | `/chat` | `{user_id, message, conversation_id?, agent?}` → `{reply, agent, conversation_id}` |

## Day-1 checklist once the challenge drops

- [ ] Rename/replace agents in `registry.py` to match the theme
- [ ] Add domain tables to `models.py`, or start with `Task.data` JSON
- [ ] Add domain tools (e.g. `book_slot`, `check_requirements`) to `tools.py`
- [ ] Load any dataset or API the organizers provide; add a retrieval tool if there are documents
- [ ] Polish the UI and deploy early, not at the last hour
