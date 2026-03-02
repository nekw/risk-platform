import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    ignite_host: str = os.getenv("IGNITE_HOST", "127.0.0.1")
    ignite_port: int = int(os.getenv("IGNITE_PORT", "10800"))
    stream_symbols: tuple[str, ...] = tuple(
        symbol.strip() for symbol in os.getenv("STREAM_SYMBOLS", "EURUSD,USDJPY,SPOT_GOLD").split(",")
    )


settings = Settings()
