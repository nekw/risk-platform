"""Scenario shock service — price shock computation and history management."""

import csv
from datetime import UTC, datetime
from io import StringIO

import structlog

from app.exceptions import MissingShocksError, UnknownPresetError
from app.ignite_client import IgniteStore
from app.models import ScenarioShockRequest, ScenarioShockResult
from app.risk import compute_risk_summary
from presets import PRESET_SCENARIOS

log = structlog.get_logger(__name__)


class ScenarioService:
    """Runs price shock scenarios and manages scenario run history."""

    def __init__(self, store: IgniteStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Shock computation
    # ------------------------------------------------------------------

    @staticmethod
    def apply_shocks(
        prices: dict[str, dict],
        shocks: dict[str, float],
    ) -> tuple[dict[str, dict], dict[str, float]]:
        """
        Apply percentage shocks to a prices snapshot.

        Returns (shocked_prices_dict, shocked_mark_prices_dict).
        shocked_mark_prices only contains symbols that were actually shocked.
        """
        shocked_prices = {symbol: dict(info) for symbol, info in prices.items()}
        shocked_marks: dict[str, float] = {}

        for symbol, shock in shocks.items():
            base_price = float(shocked_prices.get(symbol, {}).get("price", 0.0))
            if base_price <= 0:
                continue
            new_price = round(base_price * (1 + float(shock)), 6)
            shocked_prices[symbol] = {
                "symbol": symbol,
                "price": new_price,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            shocked_marks[symbol] = new_price

        return shocked_prices, shocked_marks

    def run_shock(self, request: ScenarioShockRequest) -> ScenarioShockResult:
        """Resolve preset or custom shocks, compute baseline vs shocked risk, persist history."""
        shocks = dict(request.custom_shocks or {})
        scenario_name = "Custom"

        if request.preset:
            preset = PRESET_SCENARIOS.get(request.preset)
            if not preset:
                raise UnknownPresetError(request.preset)
            shocks = dict(preset)
            scenario_name = request.preset

        if not shocks:
            raise MissingShocksError()

        trades = self._store.get_all_trades()
        prices = self._store.get_prices()
        baseline = compute_risk_summary(trades, prices)

        shocked_prices, shocked_marks = self.apply_shocks(prices, shocks)
        shocked = compute_risk_summary(trades, shocked_prices)

        result = ScenarioShockResult(
            scenario_name=scenario_name,
            shocks=shocks,
            baseline=baseline,
            shocked=shocked,
            delta={
                "total_notional_abs": round(shocked.total_notional_abs - baseline.total_notional_abs, 2),
                "net_mtm": round(shocked.net_mtm - baseline.net_mtm, 2),
                "var_1d_99": round(shocked.var_1d_99 - baseline.var_1d_99, 2),
            },
            shocked_prices=shocked_marks,
        )

        self._append_history(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "scenario_name": scenario_name,
                "shocks": shocks,
                "delta": result.delta,
                "baseline_var_1d_99": baseline.var_1d_99,
                "shocked_var_1d_99": shocked.var_1d_99,
                "baseline_notional_abs": baseline.total_notional_abs,
                "shocked_notional_abs": shocked.total_notional_abs,
            }
        )
        log.info("scenario_run", scenario=scenario_name, delta_var=result.delta["var_1d_99"])
        return result

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _append_history(self, entry: dict) -> None:
        logs = self._store.get_meta("scenario_history", [])
        logs.append(entry)
        self._store.set_meta("scenario_history", logs[-200:])

    def get_history(self, limit: int = 20) -> list[dict]:
        logs = self._store.get_meta("scenario_history", [])
        return logs[-max(1, min(limit, 100)):]

    def clear_history(self) -> None:
        self._store.set_meta("scenario_history", [])
        log.info("scenario_history_cleared")

    def export_csv(self, limit: int = 200) -> str:
        """Serialize scenario history to a CSV string."""
        logs = self._store.get_meta("scenario_history", [])
        tail = logs[-max(1, min(limit, 1000)):]

        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "timestamp",
                "scenario_name",
                "shocks",
                "delta_total_notional_abs",
                "delta_net_mtm",
                "delta_var_1d_99",
                "baseline_var_1d_99",
                "shocked_var_1d_99",
                "baseline_notional_abs",
                "shocked_notional_abs",
            ],
        )
        writer.writeheader()
        for item in tail:
            delta = item.get("delta", {})
            writer.writerow(
                {
                    "timestamp": item.get("timestamp", ""),
                    "scenario_name": item.get("scenario_name", ""),
                    "shocks": item.get("shocks", {}),
                    "delta_total_notional_abs": delta.get("total_notional_abs", 0),
                    "delta_net_mtm": delta.get("net_mtm", 0),
                    "delta_var_1d_99": delta.get("var_1d_99", 0),
                    "baseline_var_1d_99": item.get("baseline_var_1d_99", 0),
                    "shocked_var_1d_99": item.get("shocked_var_1d_99", 0),
                    "baseline_notional_abs": item.get("baseline_notional_abs", 0),
                    "shocked_notional_abs": item.get("shocked_notional_abs", 0),
                }
            )
        return output.getvalue()
