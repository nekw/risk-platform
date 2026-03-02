"""Stream router — start and stop the simulated market trade stream."""

import structlog
from fastapi import APIRouter, Depends

from app.dependencies import get_streamer

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/stream", tags=["Stream"])


@router.post(
    "/start",
    summary="Start the simulated market trade stream",
    response_description="Whether the stream was newly started and current running state",
)
def start_stream(streamer=Depends(get_streamer)) -> dict:
    started = streamer.start()
    log.info("stream_start_requested", started=started, running=streamer.running)
    return {"started": started, "stream_running": streamer.running}


@router.post(
    "/stop",
    summary="Stop the simulated market trade stream",
    response_description="Whether the stream was running before stop and current running state",
)
def stop_stream(streamer=Depends(get_streamer)) -> dict:
    stopped = streamer.stop()
    log.info("stream_stop_requested", stopped=stopped, running=streamer.running)
    return {"stopped": stopped, "stream_running": streamer.running}
