from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ------------------------------------------------------------------
# Scope type for pre-trade checks
# ------------------------------------------------------------------
LimitScope = Literal["firm", "trader", "book"]


# ------------------------------------------------------------------
# Raw inbound events
# ------------------------------------------------------------------
class TradeEvent(BaseModel):
    trade_id: int
    timestamp: str
    symbol: str
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: float
    price: float
    book: str
    trader: str


class PriceEvent(BaseModel):
    symbol: str
    price: float
    timestamp: str


# ------------------------------------------------------------------
# Stored trade record — richer model persisted to Ignite SQL schema
# ------------------------------------------------------------------
class TradeRecord(TradeEvent):
    """Trade enriched with server-side computed fields stored in Ignite."""

    notional: float = Field(default=0.0, description="abs(quantity * price) — pre-computed for SQL SUM")
    trade_date: str = Field(default="", description="YYYY-MM-DD — enables date-range SQL queries")

    @model_validator(mode="after")
    def _compute_derived(self) -> "TradeRecord":
        self.notional = round(abs(self.quantity * self.price), 6)
        self.trade_date = self.timestamp[:10] if self.timestamp else ""
        return self


# ------------------------------------------------------------------
# Risk output
# ------------------------------------------------------------------
class RiskSummary(BaseModel):
    total_notional_abs: float
    net_mtm: float
    var_1d_99: float
    symbols: dict[str, dict]  # dict value includes asset_class (str) alongside float fields


# ------------------------------------------------------------------
# Limits — firm-wide + optional per-trader overrides in meta cache
# ------------------------------------------------------------------
class RiskLimits(BaseModel):
    max_notional_abs: float = 60_000_000.0
    max_var_1d_99: float = 700_000.0
    enforce_pre_trade: bool = True


class TraderLimits(BaseModel):
    """Per-trader limit overrides stored in meta cache under key 'trader_limits:<name>'."""

    trader: str
    max_notional_abs: float | None = None
    max_var_1d_99: float | None = None


# ------------------------------------------------------------------
# Pre-trade check — scoped request + enriched result
# ------------------------------------------------------------------
class PreTradeCheckRequest(BaseModel):
    symbol: str
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: float
    price: float
    book: str = "DEFAULT_BOOK"
    trader: str = "demo_user"
    scope: LimitScope = Field(
        default="firm",
        description="firm = global portfolio, trader = per-trader book, book = per-book",
    )


class PreTradeCheckResult(BaseModel):
    accepted: bool
    breaches: list[str]
    scope: LimitScope
    scope_key: str = Field(description="'firm', trader name, or book name")
    trade_notional: float = Field(description="Notional of this single trade")
    current_notional_abs: float = Field(description="Scope notional BEFORE this trade (from Ignite SQL SUM)")
    current_var_1d_99: float = Field(description="Scope VaR BEFORE this trade")
    projected_notional_abs: float = Field(description="Scope notional AFTER adding this trade")
    projected_var_1d_99: float = Field(description="Scope VaR AFTER adding this trade")


# ------------------------------------------------------------------
# Breach record — stored in Ignite SQL schema for queryable audit log
# ------------------------------------------------------------------
class BreachRecord(BaseModel):
    """Full breach record stored in Ignite BREACH SQL table."""

    breach_id: str = Field(description="UUID key for breach SQL row")
    timestamp: str
    event_type: str
    trader: str
    symbol: str
    side: str
    book: str
    trade_notional: float
    breaches_json: str = Field(description="JSON-encoded breach messages (SQL-storable string)")
    projected_notional_abs: float
    projected_var_1d_99: float
    scope: str
    scope_key: str


class BreachEvent(BaseModel):
    """Backward-compatible breach event used for legacy meta-cache storage."""

    timestamp: str
    event_type: str
    trader: str
    symbol: str
    side: str = ""
    book: str = ""
    trade_notional: float = 0.0
    breaches: list[str]
    projected_notional_abs: float
    projected_var_1d_99: float
    scope: str = "firm"
    scope_key: str = "firm"


# ------------------------------------------------------------------
# Scenario stress testing
# ------------------------------------------------------------------
class ScenarioShockRequest(BaseModel):
    preset: str | None = None
    custom_shocks: dict[str, float] = {}


class ScenarioShockResult(BaseModel):
    scenario_name: str
    shocks: dict[str, float]
    baseline: RiskSummary
    shocked: RiskSummary
    delta: dict[str, float]
    shocked_prices: dict[str, float]
