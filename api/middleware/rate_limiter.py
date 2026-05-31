"""
API Middleware — Rate Limiter  (api/middleware/rate_limiter.py)

Uses slowapi (Starlette-compatible limiter backed by in-memory storage).
For production with multiple API workers, swap the storage_uri to Redis:
    storage_uri="redis://localhost:6379"
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from config.settings import get_settings

cfg = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{cfg.rate_limit_per_minute}/minute"],
    storage_uri="memory://",
)
