"""CSV replay service — bulk-loads trades from a CSV file into the store."""

import csv
from pathlib import Path

import structlog

from app.exceptions import ReplayFileNotFoundError
from app.ignite_client import IgniteStore

log = structlog.get_logger(__name__)


class ReplayService:
    """Reads a trades CSV and inserts each row into the Ignite store."""

    def __init__(self, store: IgniteStore) -> None:
        self._store = store

    def load(self, file_path: str) -> int:
        """
        Insert all trades from *file_path* into the store.

        Returns the number of rows inserted.
        Raises ReplayFileNotFoundError if the file does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise ReplayFileNotFoundError(file_path)

        inserted = 0
        with path.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                trade = {
                    "trade_id": int(row["trade_id"]),
                    "timestamp": row["timestamp"],
                    "symbol": row["symbol"],
                    "side": row["side"],
                    "quantity": float(row["quantity"]),
                    "price": float(row["price"]),
                    "book": row["book"],
                    "trader": row["trader"],
                }
                self._store.put_trade(trade["trade_id"], trade)
                self._store.put_price(
                    trade["symbol"],
                    {
                        "symbol": trade["symbol"],
                        "price": trade["price"],
                        "timestamp": trade["timestamp"],
                    },
                )
                inserted += 1

        log.info("replay_complete", file=file_path, rows=inserted)
        return inserted
