"""Runs without Postgres or an API key: SQLite + a stubbed orchestrator."""
import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient

from app.agents import orchestrator
from app.main import app


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    async def fake(**kw):
        return orchestrator.AgentReply("general", f"echo: {kw['user_msg']}")
    monkeypatch.setattr(orchestrator, "handle_turn", fake)
    yield
    if os.path.exists("test.db"):
        os.remove("test.db")


def test_flow():
    with TestClient(app) as c:
        assert c.get("/health").json()["ok"]
        assert {a["key"] for a in c.get("/agents").json()} >= {"general", "health", "municipal"}
        uid = c.post("/users", json={"name": "Ada", "profile": {"city": "Torino"}}).json()["id"]
        r = c.post("/chat", json={"user_id": uid, "message": "ciao"}).json()
        assert r["reply"] == "echo: ciao"
        r2 = c.post("/chat", json={"user_id": uid, "message": "again",
                                   "conversation_id": r["conversation_id"]}).json()
        assert r2["conversation_id"] == r["conversation_id"]
        assert c.get(f"/users/{uid}/dashboard").status_code == 200
