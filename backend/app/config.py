from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://erp:erp@localhost:5432/erp"
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

    # --- per-user auth (JWT) ----------------------------------------------
    # When set, mutating endpoints require a per-user JWT (POST /auth/login) and
    # the audit log records the real user's email. Empty = fall back to the
    # shared API_TOKEN / open-dev behaviour, so local + mock runs need no setup.
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    # Demo controller seeded on first boot (only when jwt_secret is set).
    seed_user_email: str = "controller@demo"
    seed_user_password: str = "demo1234"

    # --- gated autonomy ---------------------------------------------------
    # Allow drafts matched by an auto_approve Rule to finalize without a human
    # click (still fully audited + reversible). Confidence floor for that path.
    auto_approve_enabled: bool = True
    auto_approve_min_confidence: float = 0.95

    # --- event bus (Redis Streams) ---------------------------------------
    # Stream key, consumer group, and dead-letter stream. Multiple worker
    # replicas share one group so each event is processed once (at-least-once).
    event_channel: str = "erp.events"
    event_group: str = "erp-workers"
    # Per-consumer name; defaults to the hostname so replicas are distinct.
    event_consumer: str = ""
    event_dead_letter: str = "erp.events.dead"
    # Max delivery attempts before a message is moved to the dead-letter stream.
    event_max_deliveries: int = 5
    # Idle ms before an unacked pending message is reclaimed by another consumer.
    event_reclaim_idle_ms: int = 60000

    # Embedding model for the Categorizer's vector memory (runs locally, no API).
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
