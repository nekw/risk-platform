import random
import threading
import time
from datetime import UTC, datetime

from app.config import settings
from app.ignite_client import store


class MarketTradeStreamer:
    def __init__(self) -> None:
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _next_trade_id(self) -> int:
        current = int(store.get_meta("trade_seq", 1000))
        nxt = current + 1
        store.set_meta("trade_seq", nxt)
        return nxt

    def _seed_prices_if_empty(self) -> None:
        existing = store.get_prices()
        if existing:
            return

        seeds = {
            # FX Spot
            "EURUSD":    1.0840,
            "USDJPY":    149.50,
            # Commodity
            "SPOT_GOLD": 2020.0,
            # Equity
            "SPX":       5_250.0,
            "AAPL":      225.0,
            # Fixed Income (price per $100 face value)
            "US10Y":     96.50,
            "US2Y":      99.20,
        }
        now = datetime.now(UTC).isoformat()
        for symbol, price in seeds.items():
            store.put_price(symbol, {"symbol": symbol, "price": price, "timestamp": now})

    def _run(self) -> None:
        self._seed_prices_if_empty()
        while self._running:
            now = datetime.now(UTC).isoformat()
            prices = store.get_prices()

            for symbol in settings.stream_symbols:
                current = float(prices.get(symbol, {}).get("price", 100.0))
                shock = random.uniform(-0.002, 0.002)
                new_price = round(current * (1 + shock), 6)
                store.put_price(symbol, {"symbol": symbol, "price": new_price, "timestamp": now})

                trade = {
                    "trade_id": self._next_trade_id(),
                    "timestamp": now,
                    "symbol": symbol,
                    "side": random.choice(["BUY", "SELL"]),
                    "quantity": {
                        # FX: base currency units
                        "EURUSD":    random.choice([50_000, 100_000, 200_000]),
                        "USDJPY":    random.choice([50_000, 100_000, 200_000]),
                        # Commodity: troy oz
                        "SPOT_GOLD": random.choice([5, 10, 20]),
                        # Equity: shares / index units
                        "SPX":       random.choice([1, 5, 10]),
                        "AAPL":      random.choice([100, 500, 1_000]),
                        # Fixed Income: face value
                        "US10Y":     random.choice([100_000, 500_000, 1_000_000]),
                        "US2Y":      random.choice([100_000, 500_000, 1_000_000]),
                    }.get(symbol, random.choice([50_000, 100_000, 200_000])),
                    "price": new_price,
                    "book": {
                        "EURUSD": "FX_SPOT", "USDJPY": "FX_SPOT",
                        "SPOT_GOLD": "COMMODITIES",
                        "SPX": "EQUITIES", "AAPL": "EQUITIES",
                        "US10Y": "RATES", "US2Y": "RATES",
                    }.get(symbol, "DEFAULT_BOOK"),
                    "trader": random.choice(["alice", "bob", "carol"]),
                }
                store.put_trade(trade["trade_id"], trade)

            time.sleep(1)

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return True

    def stop(self) -> bool:
        with self._lock:
            if not self._running:
                return False
            self._running = False
            return True

    @property
    def running(self) -> bool:
        return self._running


streamer = MarketTradeStreamer()
