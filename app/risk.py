from collections import defaultdict
from typing import Any

from app.models import RiskSummary


VOLATILITY_ASSUMPTIONS = {
    # FX Spot
    "EURUSD":    0.08,
    "USDJPY":    0.09,
    # Commodity
    "SPOT_GOLD": 0.15,
    # Equity
    "SPX":       0.16,
    "AAPL":      0.28,
    # Fixed Income (price-based vol; duration-adjusted)
    "US10Y":     0.07,
    "US2Y":      0.02,
}

ASSET_CLASS = {
    "EURUSD":    "FX",
    "USDJPY":    "FX",
    "SPOT_GOLD": "Commodity",
    "SPX":       "Equity",
    "AAPL":      "Equity",
    "US10Y":     "Fixed Income",
    "US2Y":      "Fixed Income",
}

# Symbols where USD is the BASE currency (quantity is already in USD).
# price = quote-currency per 1 USD, so:
#   notional_usd = abs(position)          (not position × price)
#   mtm_usd      = position × (mark - avg) / mark
#   var_usd      = abs(position) × sigma × z
USD_BASE_SYMBOLS = {"USDJPY"}


def _usd_notional(symbol: str, position: float, mark_price: float) -> float:
    if symbol in USD_BASE_SYMBOLS:
        return abs(position)
    return abs(position * mark_price)


def _usd_mtm(symbol: str, position: float, mark_price: float, avg_price: float) -> float:
    if symbol in USD_BASE_SYMBOLS:
        # P&L in quote (JPY), convert to USD by dividing by mark
        return position * (mark_price - avg_price) / mark_price if mark_price else 0.0
    return position * (mark_price - avg_price)


def compute_risk_summary(trades: list[dict], prices: dict[str, dict]) -> RiskSummary:
    signed_position = defaultdict(float)
    avg_trade_price_notional = defaultdict(float)
    traded_qty_abs = defaultdict(float)

    for trade in trades:
        symbol = trade["symbol"]
        qty = float(trade["quantity"])
        side = trade["side"]
        trade_price = float(trade["price"])

        sign = 1.0 if side == "BUY" else -1.0
        signed_position[symbol] += sign * qty

        avg_trade_price_notional[symbol] += qty * trade_price
        traded_qty_abs[symbol] += qty

    total_notional_abs = 0.0
    net_mtm = 0.0
    var_1d_99 = 0.0
    symbols = {}

    for symbol, position in signed_position.items():
        mark_price = float(prices.get(symbol, {}).get("price", 0.0))
        if mark_price == 0.0:
            continue

        gross_notional = _usd_notional(symbol, position, mark_price)
        total_notional_abs += gross_notional

        avg_trade_price = (
            avg_trade_price_notional[symbol] / traded_qty_abs[symbol]
            if traded_qty_abs[symbol] > 0
            else mark_price
        )
        mtm = _usd_mtm(symbol, position, mark_price, avg_trade_price)
        net_mtm += mtm

        sigma = VOLATILITY_ASSUMPTIONS.get(symbol, 0.10)
        symbol_var = _usd_notional(symbol, position, mark_price) * sigma * (2.33 / (252**0.5))
        var_1d_99 += symbol_var

        symbols[symbol] = {
            "asset_class":    ASSET_CLASS.get(symbol, "Other"),
            "position":       round(position, 4),
            "mark_price":     round(mark_price, 6),
            "gross_notional": round(gross_notional, 2),
            "mtm":            round(mtm, 2),
            "var_1d_99":      round(symbol_var, 2),
        }

    return RiskSummary(
        total_notional_abs=round(total_notional_abs, 2),
        net_mtm=round(net_mtm, 2),
        var_1d_99=round(var_1d_99, 2),
        symbols=symbols,
    )


def compute_risk_summary_fast(
    agg_rows: list[dict[str, Any]], prices: dict[str, dict]
) -> RiskSummary:
    """Compute RiskSummary from pre-aggregated SQL GROUP BY rows (no trade-level scan)."""
    total_notional_abs = 0.0
    net_mtm = 0.0
    var_1d_99 = 0.0
    symbols: dict[str, dict[str, float]] = {}

    for row in agg_rows:
        symbol    = row["symbol"]
        position  = row["net_qty"]
        sum_qty_price = row["sum_qty_price"]
        sum_qty   = row["sum_qty"]

        mark_price = float(prices.get(symbol, {}).get("price", 0.0))
        if mark_price == 0.0:
            continue

        gross_notional = _usd_notional(symbol, position, mark_price)
        total_notional_abs += gross_notional

        avg_trade_price = sum_qty_price / sum_qty if sum_qty > 0 else mark_price
        mtm = _usd_mtm(symbol, position, mark_price, avg_trade_price)
        net_mtm += mtm

        sigma = VOLATILITY_ASSUMPTIONS.get(symbol, 0.10)
        symbol_var = _usd_notional(symbol, position, mark_price) * sigma * (2.33 / (252**0.5))
        var_1d_99 += symbol_var

        symbols[symbol] = {
            "asset_class":    ASSET_CLASS.get(symbol, "Other"),
            "position":       round(position, 4),
            "mark_price":     round(mark_price, 6),
            "gross_notional": round(gross_notional, 2),
            "mtm":            round(mtm, 2),
            "var_1d_99":      round(symbol_var, 2),
        }

    return RiskSummary(
        total_notional_abs=round(total_notional_abs, 2),
        net_mtm=round(net_mtm, 2),
        var_1d_99=round(var_1d_99, 2),
        symbols=symbols,
    )
