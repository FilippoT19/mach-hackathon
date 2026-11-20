"""Tests run on a throwaway SQLite file with the LLM stubbed: no Postgres or API key needed."""
import os

DB_FILE = "test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///./{DB_FILE}"
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)


def pytest_sessionfinish(session, exitstatus):
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
