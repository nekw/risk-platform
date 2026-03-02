import json
import logging
import sys
import threading
import time
from typing import Any

from pyignite import Client

from app.config import settings

_log = logging.getLogger(__name__)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)

# ---------------------------------------------------------------------------
# SQL DDL — define table schemas via CREATE TABLE
# ---------------------------------------------------------------------------

_CREATE_TRADE_TABLE = """
CREATE TABLE IF NOT EXISTS TRADE (
    TRADE_ID     BIGINT      PRIMARY KEY,
    TIMESTAMP    VARCHAR,
    SYMBOL       VARCHAR,
    SIDE         VARCHAR,
    QUANTITY     DOUBLE,
    PRICE        DOUBLE,
    NOTIONAL     DOUBLE,
    BOOK         VARCHAR,
    TRADER       VARCHAR,
    TRADE_DATE   VARCHAR
) WITH "template=partitioned,cache_name=trades"
"""

_CREATE_BREACH_TABLE = """
CREATE TABLE IF NOT EXISTS BREACH (
    BREACH_ID              VARCHAR     PRIMARY KEY,
    TIMESTAMP              VARCHAR,
    EVENT_TYPE             VARCHAR,
    TRADER                 VARCHAR,
    SYMBOL                 VARCHAR,
    SIDE                   VARCHAR,
    BOOK                   VARCHAR,
    TRADE_NOTIONAL         DOUBLE,
    BREACHES_JSON          VARCHAR,
    PROJECTED_NOTIONAL_ABS DOUBLE,
    PROJECTED_VAR_1D_99    DOUBLE,
    SCOPE                  VARCHAR,
    SCOPE_KEY              VARCHAR
) WITH "template=partitioned,cache_name=breaches"
"""

_TRADE_INDEXES = [
    'CREATE INDEX IF NOT EXISTS IDX_TRADE_SYMBOL     ON TRADE (SYMBOL)',
    'CREATE INDEX IF NOT EXISTS IDX_TRADE_TRADER     ON TRADE (TRADER)',
    'CREATE INDEX IF NOT EXISTS IDX_TRADE_BOOK       ON TRADE (BOOK)',
    'CREATE INDEX IF NOT EXISTS IDX_TRADE_DATE       ON TRADE (TRADE_DATE)',
]
_BREACH_INDEXES = [
    'CREATE INDEX IF NOT EXISTS IDX_BREACH_TRADER    ON BREACH (TRADER)',
    'CREATE INDEX IF NOT EXISTS IDX_BREACH_SYMBOL    ON BREACH (SYMBOL)',
    'CREATE INDEX IF NOT EXISTS IDX_BREACH_TIMESTAMP ON BREACH (TIMESTAMP)',
]

# ---------------------------------------------------------------------------
# DML statements (column order matches query_args lists below)
# ---------------------------------------------------------------------------
_MERGE_TRADE = """
MERGE INTO TRADE
    (TRADE_ID, TIMESTAMP, SYMBOL, SIDE, QUANTITY, PRICE, NOTIONAL, BOOK, TRADER, TRADE_DATE)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_MERGE_BREACH = """
MERGE INTO BREACH
    (BREACH_ID, TIMESTAMP, EVENT_TYPE, TRADER, SYMBOL, SIDE, BOOK,
     TRADE_NOTIONAL, BREACHES_JSON, PROJECTED_NOTIONAL_ABS, PROJECTED_VAR_1D_99,
     SCOPE, SCOPE_KEY)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_TRADES = (
    "SELECT TRADE_ID, TIMESTAMP, SYMBOL, SIDE, QUANTITY, PRICE, "
    "NOTIONAL, BOOK, TRADER, TRADE_DATE FROM TRADE"
)

# Pre-aggregated query used by /risk/summary — avoids materialising every row in Python
_SUMMARY_AGG = (
    "SELECT SYMBOL, "
    "SUM(CASE WHEN SIDE='BUY' THEN QUANTITY ELSE -QUANTITY END) AS NET_QTY, "
    "SUM(QUANTITY * PRICE) AS SUM_QTY_PRICE, "
    "SUM(QUANTITY) AS SUM_QTY "
    "FROM TRADE GROUP BY SYMBOL"
)


class IgniteStore:
    def __init__(self) -> None:
        self.client = Client()
        self._client_lock = threading.RLock()
        self.prices_cache = None
        self.meta_cache   = None
        self._initialized = False
        self._using_fallback = False
        self._last_connect_attempt = 0.0
        self._reconnect_cooldown_seconds = 5.0
        # fallback in-memory stores (used when Ignite is unreachable)
        self._fallback_trades:   dict[int, str] = {}
        self._fallback_prices:   dict[str, str] = {}
        self._fallback_breaches: list[dict]     = []
        self._fallback_meta:     dict[str, str] = {}

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect_with_retry(self, retries: int = 20, delay_seconds: float = 1.5) -> None:
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                with self._client_lock:
                    # Always create a fresh Client — reusing a failed client causes socket errors
                    # handshake_timeout=60s: QEMU-emulated Ignite (ARM host running x86 image)
                    # can take >10s to complete the thin-client handshake.
                    self.client = Client(handshake_timeout=60.0)
                    self.client.connect(settings.ignite_host, settings.ignite_port)
                    _err("[ignite] connected — running DDL")
                    # Create SQL tables via DDL (idempotent — safe to call on reconnect)
                    self.client.sql(_CREATE_TRADE_TABLE)
                    self.client.sql(_CREATE_BREACH_TABLE)
                    for ddl in _TRADE_INDEXES + _BREACH_INDEXES:
                        self.client.sql(ddl)
                    # Simple key-value caches for prices + meta (no SQL needed)
                    self.prices_cache = self.client.get_or_create_cache("prices")
                    self.meta_cache   = self.client.get_or_create_cache("meta")
                    self._initialized = True
                    _err("[ignite] SQL schema ready")
                    return
            except Exception as error:
                last_error = error
                _err(f"[ignite] attempt {attempt + 1}/{retries} failed: {type(error).__name__}: {error}")
                time.sleep(delay_seconds)
        raise RuntimeError(
            f"Failed to connect to Ignite at {settings.ignite_host}:{settings.ignite_port}"
        ) from last_error

    def ensure_connected(self, retries: int = 2, delay_seconds: float = 0.2) -> None:
        if self._initialized:
            return
        now = time.time()
        if self._using_fallback and (now - self._last_connect_attempt) < self._reconnect_cooldown_seconds:
            return
        self._last_connect_attempt = now
        try:
            self._connect_with_retry(retries=retries, delay_seconds=delay_seconds)
            self._using_fallback = False
        except RuntimeError:
            self._using_fallback = True

    def check_connection(self) -> bool:
        return self._initialized

    @property
    def storage_mode(self) -> str:
        return "ignite" if self._initialized else "fallback"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize(value: dict[str, Any]) -> str:
        return json.dumps(value)

    @staticmethod
    def _deserialize(value: str) -> dict[str, Any]:
        return json.loads(value)

    @staticmethod
    def _trade_notional(trade: dict[str, Any]) -> float:
        return round(abs(float(trade.get("quantity", 0)) * float(trade.get("price", 0))), 6)

    # ------------------------------------------------------------------
    # Trade SQL writes and reads
    # ------------------------------------------------------------------

    def put_trade(self, trade_id: int, trade: dict[str, Any]) -> None:
        self.ensure_connected()
        notional   = self._trade_notional(trade)
        trade_date = str(trade.get("timestamp", ""))[:10]

        if self._initialized:
            with self._client_lock:
                self.client.sql(
                    _MERGE_TRADE,
                    query_args=[
                        trade_id,
                        trade.get("timestamp", ""),
                        trade.get("symbol", ""),
                        trade.get("side", ""),
                        float(trade.get("quantity", 0)),
                        float(trade.get("price", 0)),
                        notional,
                        trade.get("book", ""),
                        trade.get("trader", ""),
                        trade_date,
                    ],
                )
            return
        # fallback
        self._fallback_trades[trade_id] = self._serialize(
            {**trade, "notional": notional, "trade_date": trade_date}
        )

    def get_all_trades(self) -> list[dict[str, Any]]:
        self.ensure_connected()
        if self._initialized:
            with self._client_lock:
                cursor = self.client.sql(_SELECT_TRADES)
                return [
                    {
                        "trade_id": row[0], "timestamp": row[1], "symbol": row[2],
                        "side":     row[3], "quantity": float(row[4] or 0),
                        "price":    float(row[5] or 0), "notional": float(row[6] or 0),
                        "book":     row[7], "trader": row[8], "trade_date": row[9],
                    }
                    for row in cursor
                ]
        return [self._deserialize(item) for item in self._fallback_trades.values()]

    # ------------------------------------------------------------------
    # SQL aggregate queries — the core value of the SQL schema
    # ------------------------------------------------------------------

    def get_position_aggregates(self) -> list[dict[str, Any]]:
        """Return per-symbol net qty + price aggregates via SQL GROUP BY — O(symbols) not O(trades)."""
        self.ensure_connected()
        if not self._initialized:
            return []
        with self._client_lock:
            cursor = self.client.sql(_SUMMARY_AGG)
            return [
                {
                    "symbol":        row[0],
                    "net_qty":       float(row[1] or 0),
                    "sum_qty_price": float(row[2] or 0),
                    "sum_qty":       float(row[3] or 0),
                }
                for row in cursor
            ]

    def aggregate_notional(self, scope: str = "firm", scope_key: str = "firm") -> float:
        """
        SQL SUM(NOTIONAL) for the given scope — avoids loading all trades into Python.
        Backed by indexed columns: TRADER, BOOK.
        """
        self.ensure_connected()
        if self._initialized:
            with self._client_lock:
                if scope == "trader":
                    cursor = self.client.sql(
                        "SELECT SUM(NOTIONAL) FROM TRADE WHERE TRADER = ?",
                        query_args=[scope_key],
                    )
                elif scope == "book":
                    cursor = self.client.sql(
                        "SELECT SUM(NOTIONAL) FROM TRADE WHERE BOOK = ?",
                        query_args=[scope_key],
                    )
                else:  # firm
                    cursor = self.client.sql("SELECT SUM(NOTIONAL) FROM TRADE")
                rows = list(cursor)
            return float(rows[0][0]) if rows and rows[0][0] is not None else 0.0

        # fallback: Python aggregate
        trades = [self._deserialize(t) for t in self._fallback_trades.values()]
        if scope == "trader":
            trades = [t for t in trades if t.get("trader") == scope_key]
        elif scope == "book":
            trades = [t for t in trades if t.get("book") == scope_key]
        return sum(self._trade_notional(t) for t in trades)

    def get_trades_for_scope(self, scope: str = "firm", scope_key: str = "firm") -> list[dict[str, Any]]:
        """SQL-filtered trade set for VaR computation on a scoped portfolio."""
        self.ensure_connected()
        if self._initialized:
            with self._client_lock:
                if scope == "trader":
                    cursor = self.client.sql(
                        _SELECT_TRADES + " WHERE TRADER = ?", query_args=[scope_key]
                    )
                elif scope == "book":
                    cursor = self.client.sql(
                        _SELECT_TRADES + " WHERE BOOK = ?", query_args=[scope_key]
                    )
                else:
                    cursor = self.client.sql(_SELECT_TRADES)
                return [
                    {
                        "trade_id": r[0], "timestamp": r[1], "symbol": r[2],
                        "side": r[3], "quantity": float(r[4] or 0),
                        "price": float(r[5] or 0), "notional": float(r[6] or 0),
                        "book": r[7], "trader": r[8], "trade_date": r[9],
                    }
                    for r in cursor
                ]
        trades = [self._deserialize(t) for t in self._fallback_trades.values()]
        if scope == "trader":
            return [t for t in trades if t.get("trader") == scope_key]
        if scope == "book":
            return [t for t in trades if t.get("book") == scope_key]
        return trades

    # ------------------------------------------------------------------
    # Price cache (key-value, no SQL)
    # ------------------------------------------------------------------

    def put_price(self, symbol: str, price: dict[str, Any]) -> None:
        self.ensure_connected()
        if self._initialized:
            with self._client_lock:
                self.prices_cache.put(symbol, self._serialize(price))
            return
        self._fallback_prices[symbol] = self._serialize(price)

    def get_prices(self) -> dict[str, dict[str, Any]]:
        self.ensure_connected()
        if self._initialized:
            with self._client_lock:
                return {item[0]: self._deserialize(item[1]) for item in self.prices_cache.scan()}
        return {k: self._deserialize(v) for k, v in self._fallback_prices.items()}

    # ------------------------------------------------------------------
    # Breach SQL writes and reads
    # ------------------------------------------------------------------

    def insert_breach(self, record: dict[str, Any]) -> None:
        self.ensure_connected()
        if self._initialized:
            with self._client_lock:
                self.client.sql(
                    _MERGE_BREACH,
                    query_args=[
                        record["breach_id"],
                        record["timestamp"],
                        record["event_type"],
                        record["trader"],
                        record["symbol"],
                        record.get("side", ""),
                        record.get("book", ""),
                        float(record.get("trade_notional", 0)),
                        record.get("breaches_json", "[]"),
                        float(record.get("projected_notional_abs", 0)),
                        float(record.get("projected_var_1d_99", 0)),
                        record.get("scope", "firm"),
                        record.get("scope_key", "firm"),
                    ],
                )
            return
        self._fallback_breaches.append(record)
        self._fallback_breaches = self._fallback_breaches[-200:]

    def query_breaches(
        self,
        limit: int = 20,
        trader: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """SQL-queryable audit log with optional trader/symbol filters."""
        COLS = (
            "BREACH_ID", "TIMESTAMP", "EVENT_TYPE", "TRADER", "SYMBOL", "SIDE",
            "BOOK", "TRADE_NOTIONAL", "BREACHES_JSON",
            "PROJECTED_NOTIONAL_ABS", "PROJECTED_VAR_1D_99", "SCOPE", "SCOPE_KEY",
        )
        sql = f"SELECT {', '.join(COLS)} FROM BREACH"
        args: list = []
        conditions: list[str] = []
        if trader:
            conditions.append("TRADER = ?")
            args.append(trader)
        if symbol:
            conditions.append("SYMBOL = ?")
            args.append(symbol)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY TIMESTAMP DESC LIMIT ?"
        args.append(limit)

        self.ensure_connected()
        if self._initialized:
            with self._client_lock:
                cursor = self.client.sql(sql, query_args=args)
                rows = list(cursor)
            return [
                {
                    "breach_id": r[0], "timestamp": r[1], "event_type": r[2],
                    "trader": r[3], "symbol": r[4], "side": r[5], "book": r[6],
                    "trade_notional": float(r[7] or 0),
                    "breaches": json.loads(r[8] or "[]"),
                    "projected_notional_abs": float(r[9] or 0),
                    "projected_var_1d_99": float(r[10] or 0),
                    "scope": r[11], "scope_key": r[12],
                }
                for r in rows
            ]
        items = list(self._fallback_breaches)
        if trader:
            items = [b for b in items if b.get("trader") == trader]
        if symbol:
            items = [b for b in items if b.get("symbol") == symbol]
        return items[-limit:]

    # ------------------------------------------------------------------
    # Meta cache (key-value JSON — limits, scenario history)
    # ------------------------------------------------------------------

    def set_meta(self, key: str, value: Any) -> None:
        self.ensure_connected()
        if self._initialized:
            with self._client_lock:
                self.meta_cache.put(key, json.dumps(value))
            return
        self._fallback_meta[key] = json.dumps(value)

    def get_meta(self, key: str, default: Any = None) -> Any:
        self.ensure_connected()
        if self._initialized:
            with self._client_lock:
                value = self.meta_cache.get(key)
            return json.loads(value) if value else default
        value = self._fallback_meta.get(key)
        return json.loads(value) if value else default

    # ------------------------------------------------------------------
    # Admin — clear all data
    # ------------------------------------------------------------------

    def clear_all(self) -> dict[str, int]:
        """Delete all trades, breaches, prices and meta. Returns row counts removed."""
        result: dict[str, int] = {"trades": 0, "breaches": 0, "prices": 0, "meta": 0}
        if self._initialized:
            with self._client_lock:
                # Count before truncate so we can report what was removed
                rows = list(self.client.sql("SELECT COUNT(*) FROM TRADE"))
                result["trades"] = int(rows[0][0]) if rows and rows[0][0] else 0
                rows = list(self.client.sql("SELECT COUNT(*) FROM BREACH"))
                result["breaches"] = int(rows[0][0]) if rows and rows[0][0] else 0
                self.client.sql("DELETE FROM TRADE WHERE 1=1")
                self.client.sql("DELETE FROM BREACH WHERE 1=1")
                self.prices_cache.clear()
                self.meta_cache.clear()
        else:
            result["trades"]   = len(self._fallback_trades)
            result["breaches"] = len(self._fallback_breaches)
            result["prices"]   = len(self._fallback_prices)
            result["meta"]     = len(self._fallback_meta)
            self._fallback_trades.clear()
            self._fallback_breaches.clear()
            self._fallback_prices.clear()
            self._fallback_meta.clear()
        return result


store = IgniteStore()
