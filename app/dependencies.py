"""FastAPI dependency providers.

All route handlers receive their dependencies via `Depends()` rather than
importing module-level globals directly. This makes individual routes trivially
unit-testable — override any provider with `app.dependency_overrides[...]`.
"""

from functools import lru_cache

from app.ignite_client import store as _ignite_store
from app.stream import streamer as _market_streamer


def get_store():
    """Return the singleton IgniteStore instance."""
    return _ignite_store


def get_streamer():
    """Return the singleton MarketTradeStreamer instance."""
    return _market_streamer


# ---------------------------------------------------------------------------
# Service singletons — constructed once, reused across all requests.
# lru_cache(maxsize=1) ensures a single instance even if the provider is
# called multiple times (FastAPI calls Depends providers per-request but
# lru_cache short-circuits after the first call).
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_risk_cache():
    from app.services.risk_cache import RiskCacheService
    return RiskCacheService(_ignite_store)


@lru_cache(maxsize=1)
def get_pretrade_service():
    from app.services.pretrade_service import PreTradeService
    return PreTradeService(_ignite_store)


@lru_cache(maxsize=1)
def get_scenario_service():
    from app.services.scenario_service import ScenarioService
    return ScenarioService(_ignite_store)


@lru_cache(maxsize=1)
def get_replay_service():
    from app.services.replay_service import ReplayService
    return ReplayService(_ignite_store)
