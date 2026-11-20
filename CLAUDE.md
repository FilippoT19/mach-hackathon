# MACH: Milano Agentic City Hackathon (20–21 Nov 2026)

**What scores is `asst/`**: five agents (gp, booking_centre, hospital, specialist,
family_counseling) deployed to the city platform with `city deploy`. Read `asst/README.md`
first. Official rules: https://github.com/projectnandaitaly/mach-hackathon-kit
(`docs/kit/e19-rules.md`: rubric, message formats, rule changes, levels).

- One shared brain, split by role in `asst/brain/parts/` (00_core, 10_shared, 15_voice, 20_gp,
  30_booking, 40_facility). Edit ONLY the parts. `python seats.py --brain` (from `asst/`) joins
  them into `asst/brain/agent.py` and the five `asst/<agent>/agent/agent.py` (generated files).
  `python seats.py --check` + `tests/test_brain.py` must pass. It reads its role from `card.yaml`.
- Only Filippo (captain) reviews PRs and runs `city deploy`. Teammates: branch → PR, never deploy.
- Never edit an agent's `Dockerfile` or `city.yaml` (conformance fails). No data files in the image.
- The brain may import only `city_sdk.city` + Python stdlib. LLM only via `city.llm` (city gateway,
  Gemma/GLM/Qwen) — no Anthropic key involved.
- Messages are text: act word + `key=value` tokens. Write to the Ledger before telling the citizen.
- Test locally with `city run <agent>`; ship with `city deploy <agent>` (specialist before hospital);
  undo with `city rollback agent:<agent> --to <version>`.
- NEVER run `city retire` (permanent). Never retry a 4xx. Never commit `~/.config/city/` or `.city/`.
- Level descriptions appear during the race in "Il Token della Sera" on https://projectnandaitaly.ai;
  journeys and verdicts are in the team console https://projectnandaitaly.ai/team → Journeys.

`backend/` and `frontend/` (FastAPI + Next.js) are the earlier generic starter; they don't affect
the score. Only use them for side tooling (e.g. a monitoring dashboard).
Branch per change, small PRs into `main` when there's time; during the race, speed wins.
