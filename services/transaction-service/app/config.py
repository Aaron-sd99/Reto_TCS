from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://smartbancs:smartbancs@localhost:5432/smartbancs")
    bancs_adapter_url: str = os.getenv("BANCS_ADAPTER_URL", "http://localhost:8081")
    ai_service_url: str = os.getenv("AI_SERVICE_URL", "http://localhost:8082")
    core_timeout_seconds: float = float(os.getenv("CORE_TIMEOUT_SECONDS", "1.4"))
    outbox_poll_seconds: float = float(os.getenv("OUTBOX_POLL_SECONDS", "1"))
    outbox_batch_size: int = int(os.getenv("OUTBOX_BATCH_SIZE", "100"))
    outbox_max_concurrency: int = int(os.getenv("OUTBOX_MAX_CONCURRENCY", "25"))
    db_pool_max_size: int = int(os.getenv("DB_POOL_MAX_SIZE", "24"))


settings = Settings()
