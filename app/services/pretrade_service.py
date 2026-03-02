"""Pre-trade check service and breach event helpers.

Encapsulates scoped limit evaluation (firm / trader / book), limit CRUD, and
breach audit-log writes so that routers stay thin.
"""

import json
import uuid

import structlog

from app.ignite_client import IgniteStore
from app.models import (
    BreachEvent,
    BreachRecord,
    PreTradeCheckResult,
    RiskLimits,
    TraderLimits,
)
from app.risk import compute_risk_summary

log = structlog.get_logger(__name__)

_DEFAULT_LIMITS = RiskLimits().model_dump()


def append_breach_event(store: IgniteStore, event: BreachEvent) -> None:
    """Persist a breach event to the Ignite BREACH SQL table."""
    record = BreachRecord(
        breach_id=str(uuid.uuid4()),
        timestamp=event.timestamp,
        event_type=event.event_type,
        trader=event.trader,
        symbol=event.symbol,
        side=event.side,
        book=event.book,
        trade_notional=event.trade_notional,
        breaches_json=json.dumps(event.breaches),
        projected_notional_abs=event.projected_notional_abs,
        projected_var_1d_99=event.projected_var_1d_99,
        scope=event.scope,
        scope_key=event.scope_key,
    )
    store.insert_breach(record.model_dump())
    log.info(
        "breach_recorded",
        event_type=event.event_type,
        trader=event.trader,
        symbol=event.symbol,
        scope=f"{event.scope}/{event.scope_key}",
    )


class PreTradeService:
    """Evaluates hypothetical trades against scoped risk limits."""

    def __init__(self, store: IgniteStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Limits CRUD
    # ------------------------------------------------------------------

    def get_limits(self) -> RiskLimits:
        raw = self._store.get_meta("risk_limits", _DEFAULT_LIMITS)
        return RiskLimits(**raw)

    def set_limits(self, limits: RiskLimits) -> None:
        self._store.set_meta("risk_limits", limits.model_dump())
        log.info("limits_updated", limits=limits.model_dump())

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        trade_payload: dict,
        scope: str = "firm",
        scope_key: str = "firm",
    ) -> PreTradeCheckResult:
        """
        Scoped pre-trade check backed by Ignite SQL aggregates.

        - Notional: SQL SUM(NOTIONAL) WHERE <scope filter> — no Python table scan
        - VaR: scoped trade set fetched via SQL WHERE, computed in Python
        - Limits: firm-wide by default; per-trader overrides from meta cache
        """
        trade_notional = self._store._trade_notional(trade_payload)

        current_notional = self._store.aggregate_notional(scope, scope_key)
        projected_notional = current_notional + trade_notional

        scope_trades = self._store.get_trades_for_scope(scope, scope_key)
        prices = self._store.get_prices()
        symbol = trade_payload["symbol"]
        if symbol not in prices:
            prices[symbol] = {
                "symbol": symbol,
                "price": trade_payload["price"],
                "timestamp": trade_payload.get("timestamp", ""),
            }

        current_summary = compute_risk_summary(scope_trades, prices)
        projected_summary = compute_risk_summary(scope_trades + [trade_payload], prices)

        limits = self.get_limits()
        if scope == "trader":
            raw_tl = self._store.get_meta(f"trader_limits:{scope_key}")
            if raw_tl:
                tl = TraderLimits(**raw_tl)
                limits = RiskLimits(
                    max_notional_abs=tl.max_notional_abs or limits.max_notional_abs,
                    max_var_1d_99=tl.max_var_1d_99 or limits.max_var_1d_99,
                    enforce_pre_trade=limits.enforce_pre_trade,
                )

        breaches: list[str] = []
        if projected_notional > limits.max_notional_abs:
            breaches.append(
                f"[{scope}/{scope_key}] notional_limit: "
                f"{projected_notional:,.2f} > {limits.max_notional_abs:,.2f}"
            )
        if projected_summary.var_1d_99 > limits.max_var_1d_99:
            breaches.append(
                f"[{scope}/{scope_key}] var_limit: "
                f"{projected_summary.var_1d_99:,.2f} > {limits.max_var_1d_99:,.2f}"
            )

        log.debug(
            "pretrade_evaluated",
            symbol=symbol,
            scope=f"{scope}/{scope_key}",
            accepted=len(breaches) == 0,
            projected_notional=round(projected_notional, 2),
        )
        return PreTradeCheckResult(
            accepted=len(breaches) == 0,
            breaches=breaches,
            scope=scope,
            scope_key=scope_key,
            trade_notional=trade_notional,
            current_notional_abs=current_notional,
            current_var_1d_99=current_summary.var_1d_99,
            projected_notional_abs=projected_notional,
            projected_var_1d_99=projected_summary.var_1d_99,
        )
