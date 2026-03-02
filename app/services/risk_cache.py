"""TTL-cached risk summary service.

Wraps the expensive Ignite SQL GROUP BY query behind a 1-second TTL cache so
the dashboard can poll /risk/summary frequently without hammering the store.
"""

import threading
import time

import structlog

from app.ignite_client import IgniteStore
from app.risk import compute_risk_summary, compute_risk_summary_fast

log = structlog.get_logger(__name__)

_RISK_CACHE_TTL = 1.0  # seconds


class RiskCacheService:
    """Thread-safe, TTL-bounded risk summary cache."""

    def __init__(self, store: IgniteStore) -> None:
        self._store = store
        self._lock = threading.Lock()
        self._cache: dict = {"ts": 0.0, "data": None}

    def get(self) -> dict:
        """Return cached risk summary, recomputing at most once per TTL."""
        with self._lock:
            if (
                time.monotonic() - self._cache["ts"] < _RISK_CACHE_TTL
                and self._cache["data"] is not None
            ):
                return self._cache["data"]

        # Compute outside the lock so concurrent callers don't all block.
        prices = self._store.get_prices()
        if self._store._initialized:
            data = compute_risk_summary_fast(
                self._store.get_position_aggregates(), prices
            ).model_dump()
        else:
            data = compute_risk_summary(self._store.get_all_trades(), prices).model_dump()

        with self._lock:
            self._cache["ts"] = time.monotonic()
            self._cache["data"] = data

        log.debug("risk_cache_refreshed", symbols=list(data.get("symbols", {}).keys()))
        return data

    def invalidate(self) -> None:
        """Force the next call to get() to recompute from the store."""
        with self._lock:
            self._cache["ts"] = 0.0
            self._cache["data"] = None
