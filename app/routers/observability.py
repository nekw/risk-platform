"""Observability router — health check and request metrics."""

import structlog
from fastapi import APIRouter, Depends

from app.dependencies import get_store, get_streamer
from app.middleware.metrics import METRICS_LOCK, METRICS_STARTED_AT, METRICS_STATE

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Observability"])


@router.get(
    "/health",
    summary="Service liveness and dependency health",
    response_description="ok when all dependencies are reachable, degraded otherwise",
)
def health(
    store=Depends(get_store),
    streamer=Depends(get_streamer),
) -> dict:
    ignite_connected = store.check_connection()
    status = "ok" if ignite_connected else "degraded"
    if status == "degraded":
        log.warning("health_degraded", ignite_connected=ignite_connected)
    return {
        "status": status,
        "stream_running": streamer.running,
        "ignite_host": "connected" if ignite_connected else "unavailable",
        "storage_mode": store.storage_mode,
    }


@router.get(
    "/metrics/simple",
    summary="Per-route request count, error rate, and latency percentiles",
)
def get_simple_metrics() -> dict:
    with METRICS_LOCK:
        routes: dict[str, dict] = {}
        for path, stats in METRICS_STATE["routes"].items():
            count = max(1, int(stats["count"]))
            routes[path] = {
                "count": int(stats["count"]),
                "error_count": int(stats["error_count"]),
                "avg_ms": round(float(stats["total_ms"]) / count, 2),
                "last_ms": round(float(stats["last_ms"]), 2),
                "max_ms": round(float(stats["max_ms"]), 2),
            }
        return {
            "started_at": METRICS_STARTED_AT,
            "in_flight": int(METRICS_STATE["in_flight"]),
            "routes": routes,
        }
