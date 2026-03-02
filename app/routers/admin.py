"""Admin router — data wipe, demo mode bootstrap, and replay."""

import structlog
from fastapi import APIRouter, Depends

from app.dependencies import get_replay_service, get_risk_cache, get_store, get_streamer

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Admin"])


@router.post(
    "/admin/clear",
    summary="Stop the stream and wipe all trades, breaches, prices, and meta",
    response_description="Confirmation with count of removed records",
)
def admin_clear(
    store=Depends(get_store),
    streamer=Depends(get_streamer),
    cache=Depends(get_risk_cache),
) -> dict:
    streamer.stop()
    removed = store.clear_all()
    cache.invalidate()
    log.warning("admin_clear_executed", removed=removed)
    return {"cleared": True, "stream_stopped": True, "removed": removed}


@router.post(
    "/demo/start",
    summary="Seed trades from CSV and start the live stream (one-click demo mode)",
    response_description="Replay count, stream state, and initial risk summary",
)
def start_demo_mode(
    file_path: str = "sample_data/trades.csv",
    store=Depends(get_store),
    streamer=Depends(get_streamer),
    replay_svc=Depends(get_replay_service),
    cache=Depends(get_risk_cache),
) -> dict:
    replayed = replay_svc.load(file_path)
    stream_started = streamer.start()
    log.info("demo_started", replayed=replayed, stream_started=stream_started)
    return {
        "demo_started": True,
        "replayed": replayed,
        "stream_started": stream_started,
        "stream_running": streamer.running,
        "risk_summary": cache.get(),
    }
