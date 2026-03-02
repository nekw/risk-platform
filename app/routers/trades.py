"""Trades router — ingest, query, and replay trades."""

import structlog
from fastapi import APIRouter, Depends

from app.dependencies import get_pretrade_service, get_replay_service, get_store
from app.exceptions import LimitBreachError
from app.models import BreachEvent, TradeEvent
from app.services.pretrade_service import append_breach_event

log = structlog.get_logger(__name__)
router = APIRouter(tags=["Trades"])


@router.post(
    "/trade",
    summary="Ingest a new trade with real-time pre-trade risk check",
    response_description="Acceptance status, trade notional, and any limit breach messages",
)
def ingest_trade(
    trade: TradeEvent,
    store=Depends(get_store),
    svc=Depends(get_pretrade_service),
) -> dict:
    payload = trade.model_dump()
    result = svc.evaluate(payload, scope="firm", scope_key="firm")
    limits = svc.get_limits()

    if not result.accepted:
        append_breach_event(
            store,
            BreachEvent(
                timestamp=payload["timestamp"],
                event_type=(
                    "trade_rejected" if limits.enforce_pre_trade else "trade_breach_allowed"
                ),
                trader=payload["trader"],
                symbol=payload["symbol"],
                side=payload["side"],
                book=payload["book"],
                trade_notional=result.trade_notional,
                breaches=result.breaches,
                projected_notional_abs=result.projected_notional_abs,
                projected_var_1d_99=result.projected_var_1d_99,
                scope="firm",
                scope_key="firm",
            ),
        )
        if limits.enforce_pre_trade:
            log.warning(
                "trade_rejected",
                trade_id=payload["trade_id"],
                symbol=payload["symbol"],
                breaches=result.breaches,
            )
            raise LimitBreachError(result.breaches, result)

    store.put_trade(payload["trade_id"], payload)
    log.info("trade_ingested", trade_id=payload["trade_id"], symbol=payload["symbol"])
    return {
        "accepted": True,
        "trade_id": payload["trade_id"],
        "trade_notional": result.trade_notional,
        "breaches": result.breaches,
    }


@router.get(
    "/trades",
    summary="List trades with optional symbol / trader / book filters",
)
def list_trades(
    limit: int = 500,
    symbol: str | None = None,
    trader: str | None = None,
    book: str | None = None,
    store=Depends(get_store),
) -> dict:
    trades = store.get_all_trades()
    if symbol:
        trades = [t for t in trades if t.get("symbol") == symbol]
    if trader:
        trades = [t for t in trades if t.get("trader") == trader]
    if book:
        trades = [t for t in trades if t.get("book") == book]
    trades = sorted(trades, key=lambda t: t.get("timestamp", ""), reverse=True)
    trades = trades[: max(1, min(limit, 5000))]
    return {"count": len(trades), "items": trades}


@router.post(
    "/replay",
    summary="Bulk-load trades from a CSV file into the store",
    response_description="Number of rows inserted and the file path used",
)
def replay_from_csv(
    file_path: str = "sample_data/trades.csv",
    svc=Depends(get_replay_service),
) -> dict:
    inserted = svc.load(file_path)
    return {"replayed": inserted, "file": file_path}
