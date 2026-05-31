"""Central configuration — loaded once at import time via lru_cache."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_sql_model: str = "sqlcoder"
    ollama_report_model: str = "mistral"
    ollama_timeout_seconds: int = 120

    # Schema Registry metadata DB
    registry_db_url: str = "sqlite:///./data/registry.db"

    # Metrics / source DB (read-only)
    metrics_db_url: str = "sqlite:///./data/telecom_metrics.db"
    metrics_db_pool_size: int = 5
    metrics_db_max_overflow: int = 10
    query_row_limit: int = 10_000
    query_timeout_seconds: int = 30

    # JWT
    jwt_secret_key: str = "change-me-to-a-long-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # Rate limiting
    rate_limit_per_minute: int = 20

    # Audit
    audit_db_url: str = "sqlite:///./data/audit.db"

    # Auto-scanner / delta detector
    auto_scan_low_cardinality_threshold: int = 50
    alert_email_to: str = "data-team@telecom.internal"
    smtp_host: str = "localhost"
    smtp_port: int = 25

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
