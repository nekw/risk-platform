"""Request metrics middleware — tracks in-flight requests and per-route latency."""

import threading
import time
from datetime import UTC, datetime

import structlog
from fastapi import Request

log = structlog.get_logger(__name__)

METRICS_STARTED_AT: str = datetime.now(UTC).isoformat()
METRICS_LOCK = threading.Lock()
METRICS_STATE: dict = {"in_flight": 0, "routes": {}}


async def request_metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    status_code = 500
    path = request.url.path

    with METRICS_LOCK:
        METRICS_STATE["in_flight"] += 1

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        with METRICS_LOCK:
            METRICS_STATE["in_flight"] = max(0, METRICS_STATE["in_flight"] - 1)
            route = METRICS_STATE["routes"].setdefault(
                path,
                {"count": 0, "error_count": 0, "total_ms": 0.0, "max_ms": 0.0, "last_ms": 0.0},
            )
            route["count"] += 1
            route["total_ms"] += duration_ms
            route["last_ms"] = duration_ms
            route["max_ms"] = max(route["max_ms"], duration_ms)
            if status_code >= 400:
                route["error_count"] += 1

        if duration_ms > 500:
            log.warning("slow_request", path=path, duration_ms=round(duration_ms, 2), status=status_code)
