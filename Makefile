.PHONY: dev api web db test
db:        ## start Postgres (pgvector) + Redis
	docker compose up -d db redis
api:       ## backend with hot reload on :8000
	cd backend && ../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
web:       ## frontend on :3000
	cd frontend && npm run dev
dev: db    ## everything (api + web) in one terminal
	$(MAKE) -j2 api web
test:
	cd backend && ../.venv/bin/python -m pytest -q
