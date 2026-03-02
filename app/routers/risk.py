"""Risk router — real-time portfolio risk summary, positions, and mark prices."""

import structlog
from fastapi import APIRouter, Depends

from app.dependencies import get_risk_cache, get_store

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Risk"])


@router.get(
    "/risk/summary",
    summary="Real-time portfolio risk summary (1-second TTL cache)",
    response_description="Aggregated notional, MTM, and VaR across all open positions",
)
def risk_summary(cache=Depends(get_risk_cache)) -> dict:
    return cache.get()


@router.get(
    "/positions",
    summary="Per-symbol position breakdown",
    response_description="Symbol-level notional, MTM, VaR, and asset class",
)
def positions(cache=Depends(get_risk_cache)) -> dict:
    return {"symbols": cache.get()["symbols"]}


@router.get(
    "/prices",
    summary="Latest mark prices for all tracked symbols",
)
def list_prices(store=Depends(get_store)) -> dict:
    prices = store.get_prices()
    items = [
        {
            "symbol": symbol,
            "price": float(info.get("price", 0)),
            "timestamp": info.get("timestamp", ""),
        }
        for symbol, info in prices.items()
    ]
    return {"count": len(items), "items": items}
