from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"
    # Effort per role: the router is a quick classification; specialists do real work.
    router_effort: str = "low"
    agent_effort: str = "medium"
    cors_origins: str = "http://localhost:3000"
    # Any Vercel deployment (production + previews) may call the API.
    cors_origin_regex: str = r"https://.*\.vercel\.app"


settings = Settings()
