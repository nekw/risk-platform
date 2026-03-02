# Real-Time Risk Platform (Python + Apache Ignite)

A real-time sell-side risk platform in Python (FastAPI + Apache Ignite + Streamlit) featuring live trade ingestion, pre-trade limit enforcement, scenario stress-testing, and a layered enterprise architecture with dependency injection, structured logging, and domain-driven services.

Runs locally with Docker and demonstrates:

- trade ingestion across **4 asset classes** (FX, Commodity, Equity, Fixed Income)
- streaming mock market/trade updates for 7 symbols
- in-memory storage on Apache Ignite
- near real-time risk summary (position, MTM, 1-day 99% VaR proxy) — USD-normalised
- per-asset-class desk watch thresholds with live alert banners
- firm-wide hard limits with pre-trade gate and live breach banner
- scenario shock analysis (presets + custom per-asset-class shocks)
- trade blotter with filtering and mock live price feed
- replay from historical CSV
- **enterprise-grade layered architecture** — routers, services, DI, domain exceptions, structured logging

## 1) Run locally

```bash
docker compose up --build
```

API starts at `http://localhost:8000`.
Dashboard starts at `http://localhost:8501`.

> Docker Desktop note: API container uses `host.docker.internal` to reach Ignite thin client (`10800`) reliably on Windows/macOS.

## 2) Demo
# UI
![Overview](docs/images/1-overview.png)
![Scenarios](docs/images/2-scenarios.png)
![Pre-Trade Check](docs/images/3-pre-trade-check.png)
![Governance](docs/images/4-governance.png)
![Bloter](docs/images/5-blotter.png)

# Bash
```bash
# health
curl http://localhost:8000/health

# replay sample day
curl -X POST "http://localhost:8000/replay"

# check risk snapshot
curl http://localhost:8000/risk/summary

# start synthetic stream
curl -X POST http://localhost:8000/stream/start

# wait 5-10 seconds, then inspect updated risk
curl http://localhost:8000/risk/summary

# stop stream
curl -X POST http://localhost:8000/stream/stop
```

On PowerShell, use `Invoke-RestMethod` if `curl` aliases unexpectedly.



## 3) Dashboard flow

The dashboard has **5 tabs**:

| Tab | Content |
|---|---|
| 📊 **Overview** | KPI cards, firm limit + desk watch breach banners, symbol breakdown by asset class |
| 📈 **Scenarios** | Apply preset or custom per-asset-class shocks, view baseline vs shocked P&L |
| 🔍 **Pre-Trade Check** | Submit a hypothetical trade and see current vs projected risk with accept/reject |
| 🏦 **Governance** | Firm hard limits config, breach audit log with CSV export |
| 📋 **Blotter** | Filterable trade log (newest first) + live mark prices per symbol |

1. Open `http://localhost:8501`
2. Click **🚀 Demo** in the sidebar (replays CSV + starts stream)
3. Check **Overview** KPI cards: Gross Notional, Net MTM, 1d 99% VaR (all USD)
4. Expand **Desk Watch Thresholds** in sidebar to tune per-asset-class soft alerts
5. In **Governance**, click **🎯 Demo Limits** then use **Pre-Trade Check** to trigger a hard reject
6. Open **Scenarios**, pick *Risk-Off* preset and observe shocked P&L per symbol
7. Open **Blotter** to browse the live trade log and current mark prices
8. Click **Stop Stream**

## 4) API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness + storage mode |
| GET | `/metrics/simple` | Per-route latency, error counts, in-flight |
| POST | `/trade` | Ingest a single trade (pre-trade check applied) |
| POST | `/trade/check` | Pre-trade check without ingesting |
| POST | `/replay` | Replay CSV (`?file_path=sample_data/trades.csv`) |
| POST | `/demo/start` | Replay + start stream in one call |
| POST | `/stream/start` | Start synthetic market/trade streamer |
| POST | `/stream/stop` | Stop streamer |
| GET | `/positions` | Raw position map per symbol |
| GET | `/risk/summary` | Aggregated risk: notional, MTM, VaR, per-symbol breakdown with asset class |
| GET | `/trades` | Trade blotter (`?limit=500&symbol=&trader=&book=`) |
| GET | `/prices` | Current mark prices for all symbols |
| GET | `/limits` | Active firm hard limits |
| POST | `/limits` | Update firm hard limits |
| GET | `/breaches` | Breach audit log (`?trader=&symbol=&limit=`) |
| POST | `/scenario/shock` | Apply price shocks and return risk delta |
| GET | `/scenario/history` | Scenario run history |
| POST | `/scenario/history/clear` | Clear scenario run history |
| GET | `/scenario/history/export.csv` | Export scenario history as CSV |
| POST | `/admin/clear` | Stop stream + wipe all trades, breaches, prices, meta |

## 5) Project structure

```
app/
├── main.py               — App factory: registers routers, middleware, exception handlers, startup
├── config.py             — Settings (stream symbols, Ignite host/port via env vars)
├── models.py             — Pydantic request/response models (TradeEvent, RiskSummary, BreachEvent, …)
├── risk.py               — Pure risk engine: USD-normalised notional/MTM/VaR, per-asset-class vol assumptions
├── ignite_client.py      — Ignite thin-client: SQL DDL/DML, KV cache helpers, GROUP BY aggregates
├── stream.py             — Synthetic market streamer: 7 symbols × 4 asset classes
├── scenarios.py          — Re-export shim for PRESET_SCENARIOS
│
├── dependencies.py       — FastAPI Depends() providers (store, streamer, services)
├── exceptions.py         — Domain exceptions (LimitBreachError, UnknownPresetError, …) + HTTP handlers
├── logging_config.py     — structlog setup: JSON in production, pretty console locally
│
├── routers/              — One file per domain; each exposes an APIRouter
│   ├── observability.py  — GET /health, GET /metrics/simple
│   ├── risk.py           — GET /risk/summary, GET /positions, GET /prices
│   ├── trades.py         — POST /trade, GET /trades, POST /replay
│   ├── pretrade.py       — POST /trade/check
│   ├── scenarios.py      — POST /scenario/shock, GET/POST /scenario/history, CSV export
│   ├── governance.py     — GET+POST /limits, GET /breaches
│   ├── stream.py         — POST /stream/start, POST /stream/stop
│   └── admin.py          — POST /admin/clear, POST /demo/start
│
├── services/             — Business logic; no FastAPI imports, fully unit-testable
│   ├── risk_cache.py     — RiskCacheService: 1-second TTL cache around Ignite GROUP BY query
│   ├── pretrade_service.py — PreTradeService: scoped limit evaluation + limits CRUD
│   ├── scenario_service.py — ScenarioService: shock computation, history, CSV serialisation
│   └── replay_service.py — ReplayService: bulk CSV load into Ignite
│
└── middleware/
    └── metrics.py        — Per-route request count, error rate, avg/max/last latency

dashboard/
└── app.py                — Streamlit UI: 5-tab layout, @st.fragment isolation, sidebar controls

presets.py                — PRESET_SCENARIOS dict (canonical location, imported by API + dashboard)
sample_data/trades.csv    — Replay seed data
```

### Symbols & asset classes

| Symbol | Asset Class | Notes |
|---|---|---|
| EURUSD | FX | Base = EUR, notional = position × price |
| USDJPY | FX | Base = USD, notional = abs(position); P&L ÷ price to get USD |
| SPOT_GOLD | Commodity | Troy oz |
| SPX | Equity | Index units |
| AAPL | Equity | Shares |
| US10Y | Fixed Income | Face value; price per $100 |
| US2Y | Fixed Income | Face value; price per $100 |

## 6) Design Rationale

1. **Why Ignite**: low-latency in-memory data grid, SQL-queryable, scales horizontally; thin-client keeps the app stateless.
2. **Risk flow**: event ingestion → GROUP BY position aggregates (7 rows, not N trades) → USD-normalised MTM + VaR snapshot.
3. **Two-tier limit framework**: desk watch thresholds (per-asset-class, soft/visual) vs firm hard limits (server-enforced, hard reject).
4. **Multi-asset USD normalisation**: each asset class has its own notional and P&L conversion; USDJPY treated as USD-base to avoid ×150 inflation.
5. **1-second TTL risk cache**: `RiskCacheService` shields the expensive Ignite GROUP BY query from high-frequency dashboard polling without stale data visible for more than 1s.
6. **Layered architecture**: routers own HTTP concerns only; services own business logic; `dependencies.py` wires them together via `Depends()` — any layer is replaceable or mockable independently.
7. **Domain exceptions**: `LimitBreachError`, `UnknownPresetError`, `ReplayFileNotFoundError` propagate from services to registered FastAPI exception handlers — no scattered `raise HTTPException` inside business logic.
8. **Structured logging**: `structlog` emits JSON in production (`ENVIRONMENT=production`) and readable colour output locally — every log event carries typed fields (`trade_id`, `symbol`, `duration_ms`) rather than formatted strings.
9. **Production upgrades**:
   - Kafka ingestion replacing synthetic streamer
   - Full SQL schema with indexes on SYMBOL, TRADER, TIMESTAMP
   - Greeks (delta, DV01) and full revaluation scenarios
   - Auth, trader-level limit overrides, and signed audit trail

## 7) Architecture
see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
