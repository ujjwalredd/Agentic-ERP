from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://flow:flow@localhost:5432/flow"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""
    use_mock_llm: bool = False

    # --- security ---------------------------------------------------------
    # Comma-separated allowed browser origins for CORS. "*" only for local dev.
    cors_origins: str = "http://localhost:3000"
    # Bearer token required on state-changing endpoints. Empty = open dev mode.
    api_token: str = ""
    # Identity recorded in the audit log when a token is presented.
    api_user: str = "controller@demo"

    # --- gated autonomy ---------------------------------------------------
    # Allow drafts matched by an auto_approve Rule to finalize without a human
    # click (still fully audited + reversible). Confidence floor for that path.
    auto_approve_enabled: bool = True
    auto_approve_min_confidence: float = 0.95

    # Channel names for the Redis event bus.
    event_channel: str = "flow.events"

    # Embedding model for the Categorizer's vector memory (runs locally, no API).
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
