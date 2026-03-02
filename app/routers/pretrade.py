"""Pre-trade check router — evaluate a hypothetical trade against risk limits."""

import structlog
from datetime import UTC, datetime
from fastapi import APIRouter, Depends

from app.dependencies import get_pretrade_service, get_store
from app.models import BreachEvent, PreTradeCheckRequest
from app.services.pretrade_service import append_breach_event

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Pre-Trade"])


@router.post(
    "/trade/check",
    summary="Pre-trade risk check without booking the trade",
    response_description="Whether the trade would be accepted and projected risk metrics",
)
def check_trade(
    request: PreTradeCheckRequest,
    store=Depends(get_store),
    svc=Depends(get_pretrade_service),
) -> dict:
    scope_key = (
        request.trader
        if request.scope == "trader"
        else (request.book if request.scope == "book" else "firm")
    )
    payload = {
        "trade_id": -1,
        "timestamp": datetime.now(UTC).isoformat(),
        "symbol": request.symbol,
        "side": request.side,
        "quantity": request.quantity,
        "price": request.price,
        "book": request.book,
        "trader": request.trader,
    }
    result = svc.evaluate(payload, scope=request.scope, scope_key=scope_key)

    if not result.accepted:
        append_breach_event(
            store,
            BreachEvent(
                timestamp=payload["timestamp"],
                event_type="pre_trade_check_breach",
                trader=payload["trader"],
                symbol=payload["symbol"],
                side=payload["side"],
                book=payload["book"],
                trade_notional=result.trade_notional,
                breaches=result.breaches,
                projected_notional_abs=result.projected_notional_abs,
                projected_var_1d_99=result.projected_var_1d_99,
                scope=result.scope,
                scope_key=result.scope_key,
            ),
        )
        log.warning(
            "pretrade_breach",
            trader=request.trader,
            symbol=request.symbol,
            scope=f"{result.scope}/{result.scope_key}",
            breaches=result.breaches,
        )

    return result.model_dump()
