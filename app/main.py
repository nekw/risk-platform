"""Application entry point.

Responsibilities:
- Configure structured logging
- Instantiate the FastAPI application
- Register middleware, exception handlers, and domain routers
- Launch background workers on startup

All business logic lives in app/services/.
All route handlers live in app/routers/.
"""

import threading

import structlog
from fastapi import FastAPI

from app.ignite_client import store
from app.logging_config import configure_logging

# Configure logging before anything else so all subsequent loggers are formatted.
configure_logging()
log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    application = FastAPI(
        title="Real-Time Risk Platform",
        version="1.0.0",
        description=(
            "Sell-side risk management API  real-time pre-trade checks, "
            "scenario stress-testing, breach governance, and live market streaming."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # --- Middleware ---------------------------------------------------------
    from app.middleware.metrics import request_metrics_middleware
    application.middleware("http")(request_metrics_middleware)

    # --- Exception handlers ------------------------------------------------
    from app.exceptions import (
        LimitBreachError,
        MissingShocksError,
        ReplayFileNotFoundError,
        UnknownPresetError,
        limit_breach_handler,
        missing_shocks_handler,
        replay_file_handler,
        unknown_preset_handler,
    )
    application.add_exception_handler(LimitBreachError, limit_breach_handler)
    application.add_exception_handler(UnknownPresetError, unknown_preset_handler)
    application.add_exception_handler(ReplayFileNotFoundError, replay_file_handler)
    application.add_exception_handler(MissingShocksError, missing_shocks_handler)

    # --- Routers -----------------------------------------------------------
    from app.routers import (
        admin,
        governance,
        observability,
        pretrade,
        risk,
        scenarios,
        stream,
        trades,
    )
    for router in [
        observability.router,
        risk.router,
        trades.router,
        pretrade.router,
        scenarios.router,
        governance.router,
        stream.router,
        admin.router,
    ]:
        application.include_router(router)

    return application


app = create_app()

# ---------------------------------------------------------------------------
# Startup: background Ignite reconnect worker
# ---------------------------------------------------------------------------

@app.on_event("startup")
def startup_background_workers() -> None:
    def _reconnect_worker() -> None:
        import time
        while True:
            if not store.check_connection():
                log.warning("ignite_disconnected", action="reconnecting")
                store.ensure_connected(retries=3, delay_seconds=1.0)
            time.sleep(3)

    thread = threading.Thread(target=_reconnect_worker, daemon=True)
    thread.start()
    log.info("startup_complete", version=app.version)
