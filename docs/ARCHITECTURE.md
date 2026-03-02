# Architecture

### Component overview

| Layer | Technology | Role |
|---|---|---|
| **Event sources** | CSV replay + synthetic streamer | 7 symbols across FX, Commodity, Equity, Fixed Income |
| **API** | FastAPI (Python 3.11) | Thin factory — delegates to routers and services |
| **Routers** | `app/routers/` (8 modules) | HTTP boundary — parse requests, call services, return responses |
| **Services** | `app/services/` (4 classes) | Business logic — pretrade evaluation, scenario shocks, replay, risk cache |
| **Dependency injection** | `app/dependencies.py` | `Depends()` providers wiring routers to services and singletons |
| **Exception handling** | `app/exceptions.py` | Domain exceptions + registered FastAPI HTTP handlers |
| **In-memory store** | Apache Ignite 2.14.0 (thin client) | TRADE + BREACH SQL tables; prices, limits, scenario history in KV caches |
| **Risk engine** | Pure Python (`risk.py`) | USD-normalised position aggregation, MTM, 1-day 99% VaR with per-asset-class vol assumptions |
| **Dashboard** | Streamlit (5 tabs) | Overview, Pre-Trade Check, Scenarios, Governance, Blotter |
| **Observability** | structlog + custom middleware | Structured JSON logs; per-route request count, error rate, avg/max/last latency, in-flight |

### Data flow

```
CSV / Synthetic Stream
        │
        ▼
  POST /trade ──► Pre-trade check (limits) ──► reject 409 if breached
        │                                           │
        │                                     Breach logged to Ignite
        ▼
  Apache Ignite ◄──────────────────────────────────┘
  ┌─────────────────────────────┐
  │  trades_cache               │
  │  prices_cache               │
  │  meta_cache                 │
  │   ├─ limits                 │
  │   ├─ breach_log             │
  │   └─ scenario_history       │
  └─────────────────────────────┘
        │
        ▼
  GET /risk/summary
  (positions + MTM + VaR)
        │
        ▼
  Streamlit Dashboard (5 tabs)
  ┌────────────────────────────────────────────────┐
  │ 📊 Overview  — KPI cards, breach banners       │
  │ 🔍 Pre-Trade — submit & check hypothetical     │
  │ 📈 Scenarios — preset + custom shocks          │
  │ 🏦 Governance — limits, breach log, CSV export │
  │ 📋 Blotter   — trade log + live prices         │
  └────────────────────────────────────────────────┘
```

### Architecture diagram

```
 +---------------------------+   +---------------------------+
 |       CSV Replay          |   |    Synthetic Streamer     |
 | sample_data/trades.csv    |   |  7 symbols x 4 asset cls  |
 +-------------+-------------+   +-------------+-------------+
               |  POST /trade                  |  POST /trade
               +---------------+---------------+
                               |
                               v
 +-----------------------------------------------------------------------------+
 |                     FastAPI Service  :8000                                  |
 |                                                                             |
 |  +----------------------- ROUTERS  app/routers/ --------------------------+ |
 |  |                                                                        | |
 |  |  trades.py        pretrade.py     risk.py         governance.py        | |
 |  |  POST /trade      POST            GET             GET+POST /limits      | |
 |  |  GET  /trades       /trade/check  /risk/summary  GET /breaches         | |
 |  |  POST /replay                     GET /positions                       | |
 |  |                                   GET /prices                          | |
 |  |                                                                        | |
 |  |  scenarios.py                     stream.py       admin.py             | |
 |  |  POST /scenario/shock             POST /stream/*  POST /admin/clear    | |
 |  |  GET  /scenario/history                           POST /demo/start     | |
 |  |  POST /scenario/history/clear     observability.py                    | |
 |  |  GET  /scenario/history/export    GET /health  GET /metrics/simple    | |
 |  +-----------------------------------+----------------------------------------+
 |                              Depends() via dependencies.py                 |
 |  +----------------------- SERVICES  app/services/ -------------------------+ |
 |  |                                                                        | |
 |  |  PreTradeService          ScenarioService      RiskCacheService        | |
 |  |  .evaluate()              .run_shock()         .get()  <- 1s TTL cache | |
 |  |  .get_limits()            .get_history()       .invalidate()           | |
 |  |  .set_limits()            .clear_history()                             | |
 |  |                           .export_csv()        ReplayService           | |
 |  |                                                .load(path)             | |
 |  +------------------------------------------------------------------------+ |
 |                                                                             |
 |  +----------------------- CROSS-CUTTING -----------------------------------+ |
 |  |  dependencies.py  |  exceptions.py   |  logging_config.py              | |
 |  |  Depends() wiring |  domain errors   |  structlog JSON/pretty          | |
 |  |  middleware/metrics.py  <- per-route latency, error count, in-flight   | |
 |  +------------------------------------------------------------------------+ |
 +-----------------------------------------------------------------------------+
               |  SQL + KV reads/writes           |  REST API calls
               v                                  v
 +------------------------------+   +-----------------------------------------------+
 |  Apache Ignite  :10800       |   |  Streamlit Dashboard  :8501                   |
 |                              |   |                                               |
 |  TRADE  (SQL table)          |   |  [Overview]    Notional / MTM / 1d-99%-VaR   |
 |  BREACH (SQL table)          |   |  [Pre-Trade]   live accept / reject check     |
 |  prices_cache   (KV)         |   |  [Scenarios]   preset + custom shocks         |
 |  meta_cache     (KV)         |   |  [Governance]  limits config + breach audit   |
 |    +- risk_limits            |   |  [Blotter]     trade log + live mark prices   |
 |    +- scenario_history       |   |                                               |
 |    +- trader_limits:<name>   |   |  sidebar: Demo | Stream | Clear | Replay      |
 +------------------------------+   +-----------------------------------------------+
```
