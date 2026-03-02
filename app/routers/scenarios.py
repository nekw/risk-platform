"""Scenarios router — price shock analysis, run history, and CSV export."""

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.dependencies import get_scenario_service
from app.models import ScenarioShockRequest

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/scenario", tags=["Scenarios"])


@router.post(
    "/shock",
    summary="Run a price shock scenario against current positions",
    response_description="Baseline vs shocked risk metrics, per-symbol deltas, and shocked mark prices",
)
def run_scenario_shock(
    request: ScenarioShockRequest,
    svc=Depends(get_scenario_service),
) -> dict:
    result = svc.run_shock(request)
    return result.model_dump()


@router.get(
    "/history",
    summary="Retrieve recent scenario run history",
)
def get_scenario_history(
    limit: int = 20,
    svc=Depends(get_scenario_service),
) -> dict:
    items = svc.get_history(limit)
    return {"count": len(items), "items": items}


@router.post(
    "/history/clear",
    summary="Clear all scenario run history",
)
def clear_scenario_history(svc=Depends(get_scenario_service)) -> dict:
    svc.clear_history()
    return {"cleared": True}


@router.get(
    "/history/export.csv",
    response_class=PlainTextResponse,
    summary="Export scenario run history as a CSV file",
)
def export_scenario_history_csv(
    limit: int = 200,
    svc=Depends(get_scenario_service),
) -> str:
    return svc.export_csv(limit)
