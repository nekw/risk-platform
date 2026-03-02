"""Governance router — risk limits management and breach audit log."""

import structlog
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_pretrade_service, get_store
from app.models import RiskLimits

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Governance"])


@router.get(
    "/limits",
    summary="Get current firm-wide risk limits",
)
def get_limits(svc=Depends(get_pretrade_service)) -> dict:
    return svc.get_limits().model_dump()


@router.post(
    "/limits",
    summary="Update firm-wide risk limits",
)
def set_limits(
    limits: RiskLimits,
    svc=Depends(get_pretrade_service),
) -> dict:
    svc.set_limits(limits)
    return {"updated": True, "limits": limits.model_dump()}


@router.get(
    "/breaches",
    summary="SQL-backed breach audit log with optional filters",
    response_description="Paginated list of breach events ordered by most recent first",
)
def get_breaches(
    limit: int = 20,
    trader: str | None = Query(default=None, description="Filter by trader name"),
    symbol: str | None = Query(default=None, description="Filter by instrument symbol"),
    store=Depends(get_store),
) -> dict:
    items = store.query_breaches(
        limit=max(1, min(limit, 100)),
        trader=trader,
        symbol=symbol,
    )
    return {"count": len(items), "items": items}
