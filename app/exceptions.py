"""Domain exception types and FastAPI exception handlers."""

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------

class LimitBreachError(Exception):
    """Raised when a trade violates one or more risk limits."""

    def __init__(self, breaches: list[str], result) -> None:
        self.breaches = breaches
        self.result = result
        super().__init__(str(breaches))


class UnknownPresetError(Exception):
    """Raised when a caller references a scenario preset that does not exist."""

    def __init__(self, preset_name: str) -> None:
        self.preset_name = preset_name
        super().__init__(f"Unknown scenario preset: {preset_name!r}")


class ReplayFileNotFoundError(Exception):
    """Raised when a replay CSV file path cannot be resolved."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Replay file not found: {path!r}")


class MissingShocksError(Exception):
    """Raised when a scenario shock request supplies neither a preset nor custom shocks."""


# ---------------------------------------------------------------------------
# HTTP exception handlers — register these in main.py
# ---------------------------------------------------------------------------

async def limit_breach_handler(request: Request, exc: LimitBreachError) -> JSONResponse:
    log.warning(
        "limit_breach",
        path=request.url.path,
        breaches=exc.breaches,
        projected_notional=exc.result.projected_notional_abs,
        projected_var=exc.result.projected_var_1d_99,
    )
    return JSONResponse(
        status_code=409,
        content={
            "message": "Pre-trade limits breached",
            "breaches": exc.breaches,
            "projected_notional_abs": exc.result.projected_notional_abs,
            "projected_var_1d_99": exc.result.projected_var_1d_99,
        },
    )


async def unknown_preset_handler(request: Request, exc: UnknownPresetError) -> JSONResponse:
    log.warning("unknown_preset", preset=exc.preset_name, path=request.url.path)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


async def replay_file_handler(request: Request, exc: ReplayFileNotFoundError) -> JSONResponse:
    log.error("replay_file_not_found", path=exc.path, request_path=request.url.path)
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def missing_shocks_handler(request: Request, exc: MissingShocksError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": "Provide at least one of: preset, custom_shocks"},
    )
