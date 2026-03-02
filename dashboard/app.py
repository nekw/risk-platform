import os
import sys
from typing import Any

# Ensure the repo root is on sys.path so top-level modules (e.g. presets.py)
# are importable regardless of where Streamlit launches the script from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import streamlit as st

from presets import PRESET_SCENARIOS

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT_SECONDS = 20


st.set_page_config(page_title="Risk Dashboard", layout="wide")
st.title("Real-Time Risk Dashboard")
st.caption("Python + Apache Ignite | Real-Time Risk Platform")


@st.cache_data(ttl=2)
def get_json(path: str) -> dict[str, Any]:
    response = requests.get(f"{API_BASE_URL}{path}", timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def post_json(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.post(f"{API_BASE_URL}{path}", json=payload, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def safe_post_json(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        return post_json(path, payload)
    except requests.RequestException as exc:
        st.error(f"Request failed for {path}: {exc}")
        return None


# session state defaults for firm limits
if "firm_notional" not in st.session_state:
    st.session_state["firm_notional"] = 60_000_000.0
if "firm_var" not in st.session_state:
    st.session_state["firm_var"] = 700_000.0
if "scenario_result" not in st.session_state:
    st.session_state["scenario_result"] = None
for _cs_key, _cs_default in [
    ("cs_eurusd", 0.0), ("cs_usdjpy", 0.0), ("cs_gold", 0.0),
    ("cs_spx", 0.0), ("cs_aapl", 0.0), ("cs_us10y", 0.0), ("cs_us2y", 0.0),
]:
    if _cs_key not in st.session_state:
        st.session_state[_cs_key] = _cs_default


# symbol → (book, default_price, default_quantity)
_SYMBOL_DEFAULTS: dict[str, tuple[str, float, float]] = {
    "EURUSD":    ("FX_SPOT",     1.0840,   1_000_000.0),
    "USDJPY":    ("FX_SPOT",   149.50,    1_000_000.0),
    "SPOT_GOLD": ("COMMODITIES", 2020.0,         10.0),
    "SPX":       ("EQUITIES",   5_250.0,          5.0),
    "AAPL":      ("EQUITIES",     225.0,        500.0),
    "US10Y":     ("RATES",        96.50,    500_000.0),
    "US2Y":      ("RATES",        99.20,    500_000.0),
}

if "ptc_symbol" not in st.session_state:
    st.session_state["ptc_symbol"] = "EURUSD"
if "ptc_book" not in st.session_state:
    st.session_state["ptc_book"] = "FX_SPOT"
if "ptc_price" not in st.session_state:
    st.session_state["ptc_price"] = 1.0840
if "ptc_quantity" not in st.session_state:
    st.session_state["ptc_quantity"] = 1_000_000.0


def _on_ptc_symbol_change() -> None:
    """Auto-fill Book, Price and Quantity when the Symbol is changed."""
    sym = st.session_state["ptc_symbol"]
    book, price, qty = _SYMBOL_DEFAULTS.get(sym, ("DEFAULT_BOOK", 1.0, 100_000.0))
    st.session_state["ptc_book"]     = book
    st.session_state["ptc_price"]    = price
    st.session_state["ptc_quantity"] = qty


def _on_preset_change() -> None:
    """Mirror the selected preset's shocks into the custom shock fields."""
    shocks = PRESET_SCENARIOS.get(st.session_state["preset_selectbox"], {})
    st.session_state["cs_eurusd"] = round(shocks.get("EURUSD",    0.0) * 100, 4)
    st.session_state["cs_usdjpy"] = round(shocks.get("USDJPY",    0.0) * 100, 4)
    st.session_state["cs_gold"]   = round(shocks.get("SPOT_GOLD", 0.0) * 100, 4)
    st.session_state["cs_spx"]    = round(shocks.get("SPX",       0.0) * 100, 4)
    st.session_state["cs_aapl"]   = round(shocks.get("AAPL",      0.0) * 100, 4)
    st.session_state["cs_us10y"]  = round(shocks.get("US10Y",     0.0) * 100, 4)
    st.session_state["cs_us2y"]   = round(shocks.get("US2Y",      0.0) * 100, 4)

with st.sidebar:
    st.header("Controls")
    _c1, _c2 = st.columns(2)
    if _c1.button("🚀 Demo", use_container_width=True, help="Replay sample day + start stream"):
        result = safe_post_json("/demo/start")
        if result:
            st.success(f"Demo started: {result['replayed']} trades | stream: {result['stream_running']}")
            st.cache_data.clear()
    if _c2.button("📂 Replay", use_container_width=True, help="Replay sample day trades"):
        result = safe_post_json("/replay")
        if result:
            st.success(f"Replayed {result['replayed']} trades")
            st.cache_data.clear()

    _c3, _c4, _c5, _c6 = st.columns(4)
    if _c3.button("▶️", use_container_width=True, help="Start stream"):
        result = safe_post_json("/stream/start")
        if result:
            st.info(f"Stream: {result['stream_running']}")
            st.cache_data.clear()
    if _c4.button("⏹️", use_container_width=True, help="Stop stream"):
        result = safe_post_json("/stream/stop")
        if result:
            st.info(f"Stream: {result['stream_running']}")
            st.cache_data.clear()
    if _c5.button("🔄", use_container_width=True, help="Refresh dashboard"):
        st.cache_data.clear()
        st.rerun()
    if _c6.button("🗑️", use_container_width=True, help="Clear all data (trades, breaches, prices, meta)"):
        result = safe_post_json("/admin/clear")
        if result:
            removed = result.get("removed", {})
            st.warning(
                f"Data cleared — trades: {removed.get('trades', 0)}, "
                f"breaches: {removed.get('breaches', 0)}"
            )
            st.cache_data.clear()

    st.divider()
    st.header("Desk Watch Thresholds")
    st.caption("VaR | MTM limits per asset class (USD)")

    _WATCH_DEFAULTS = {
        "FX":           (15_000.0, 8_000.0,  1_000.0, 500.0),
        "Commodity":    (10_000.0, 5_000.0,  1_000.0, 500.0),
        "Equity":       (30_000.0, 15_000.0, 2_000.0, 1_000.0),
        "Fixed Income": (20_000.0, 10_000.0, 2_000.0, 1_000.0),
    }
    watch_limits: dict[str, dict[str, float]] = {}
    for _ac, (_var_def, _mtm_def, _var_step, _mtm_step) in _WATCH_DEFAULTS.items():
        with st.expander(_ac, expanded=False):
            _wc1, _wc2 = st.columns(2)
            watch_limits[_ac] = {
                "var":  _wc1.number_input(f"VaR",  value=_var_def,  step=_var_step,  min_value=0.0, key=f"watch_{_ac}_var"),
                "mtm":  _wc2.number_input(f"MTM",  value=_mtm_def,  step=_mtm_step,  min_value=0.0, key=f"watch_{_ac}_mtm"),
            }

    st.divider()
    st.header("Firm Hard Limits")
    _l1, _l2 = st.columns(2)
    # Handle Demo Limits BEFORE inputs render so session_state is updated first
    if _l1.button("🎯 Demo\nLimits", use_container_width=True, help="Set strict 1M notional / 10K VaR for breach demo"):
        st.session_state["firm_notional"] = 1_000_000.0
        st.session_state["firm_var"] = 10_000.0
        result = safe_post_json(
            "/limits",
            {"max_notional_abs": 1_000_000.0, "max_var_1d_99": 10_000.0, "enforce_pre_trade": True},
        )
        if result:
            st.warning("Demo breach limits loaded")
            st.cache_data.clear()
    max_notional_abs = st.number_input("Firm max notional abs", key="firm_notional", step=1_000_000.0, min_value=0.0)
    max_var_1d_99 = st.number_input("Firm max VaR 1d 99%", key="firm_var", step=10_000.0, min_value=0.0)
    enforce_pre_trade = st.checkbox("Enforce firm hard reject", value=True)
    if _l2.button("✅ Apply\nLimits", use_container_width=True, help="Apply the firm hard limits above"):
        result = safe_post_json(
            "/limits",
            {
                "max_notional_abs": max_notional_abs,
                "max_var_1d_99": max_var_1d_99,
                "enforce_pre_trade": enforce_pre_trade,
            },
        )
        if result:
            st.success(f"Limits updated: {result['limits']}")
            st.cache_data.clear()


try:
    health = get_json("/health")
except requests.RequestException as exc:
    st.error(f"API unavailable at {API_BASE_URL}: {exc}")
    st.stop()

try:
    summary = get_json("/risk/summary")
except requests.RequestException as exc:
    st.warning(f"API reachable, but risk summary is temporarily unavailable: {exc}")
    summary = {"total_notional_abs": 0, "net_mtm": 0, "var_1d_99": 0, "symbols": {}}

try:
    current_limits = get_json("/limits")
except requests.RequestException:
    current_limits = None

try:
    breaches = get_json("/breaches?limit=20")
except requests.RequestException:
    breaches = {"count": 0, "items": []}

try:
    api_metrics = get_json("/metrics/simple")
except requests.RequestException:
    api_metrics = {"in_flight": 0, "routes": {}}

stream_running = health.get("stream_running", False)
status_text = "Running" if stream_running else "Stopped"
status_color = "🟢" if stream_running else "🟡"
storage_mode = health.get("storage_mode", "unknown")
risk_route_metrics = api_metrics.get("routes", {}).get("/risk/summary", {})

# ── Status bar ──────────────────────────────────────────────────────────────
sc1, sc2, sc3 = st.columns(3)
sc1.caption(f"Stream: {status_color} {status_text}")
sc2.caption(f"Storage: **{storage_mode}** | Ignite: {health.get('ignite_host', 'unknown')}")
if risk_route_metrics:
    sc3.caption(
        f"API: in_flight={api_metrics.get('in_flight', 0)} "
        f"| /risk/summary avg={risk_route_metrics.get('avg_ms', 0)}ms"
    )

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_overview, tab_scenarios, tab_pretrade, tab_governance, tab_blotter = st.tabs([
    "📊 Overview",
    "📈 Scenarios",
    "🔍 Pre-Trade Check",
    "🏦 Governance",
    "📋 Blotter",
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
with tab_overview:
    col1, col2, col3 = st.columns(3)
    col1.metric("Gross Notional (USD)", f"{summary.get('total_notional_abs', 0):,.2f}")
    col2.metric("Net MTM (USD)",        f"{summary.get('net_mtm', 0):,.2f}")
    col3.metric("1d 99% VaR (USD)",     f"{summary.get('var_1d_99', 0):,.2f}")

    if current_limits:
        st.caption(
            f"Firm limits — notional: {current_limits.get('max_notional_abs', 0):,.0f} | "
            f"VaR: {current_limits.get('max_var_1d_99', 0):,.0f} | "
            f"enforce: {current_limits.get('enforce_pre_trade', True)}"
        )
        _firm_notional = float(summary.get("total_notional_abs", 0))
        _firm_var      = float(summary.get("var_1d_99", 0))
        _lim_notional  = float(current_limits.get("max_notional_abs", 0))
        _lim_var       = float(current_limits.get("max_var_1d_99", 0))
        _firm_parts: list[str] = []
        if _lim_notional > 0 and _firm_notional > _lim_notional:
            _firm_parts.append(f"Notional {_firm_notional:,.0f} > {_lim_notional:,.0f}")
        if _lim_var > 0 and _firm_var > _lim_var:
            _firm_parts.append(f"VaR {_firm_var:,.0f} > {_lim_var:,.0f}")
        if _firm_parts:
            st.warning(f"🚫 [Firm Limit] {' | '.join(_firm_parts)}")

    st.divider()

    # Aggregate per-asset-class VaR and |MTM| from symbol breakdown
    _class_var:  dict[str, float] = {}
    _class_mtm:  dict[str, float] = {}
    for _sym, _sdata in summary.get("symbols", {}).items():
        _ac = _sdata.get("asset_class", "Other")
        _class_var[_ac]  = _class_var.get(_ac, 0.0)  + float(_sdata.get("var_1d_99", 0))
        _class_mtm[_ac]  = _class_mtm.get(_ac, 0.0)  + float(_sdata.get("mtm", 0))

    alerts: list[str] = []
    for _ac, _lims in watch_limits.items():
        _v = _class_var.get(_ac, 0.0)
        _m = _class_mtm.get(_ac, 0.0)
        _parts: list[str] = []
        if _v > _lims["var"]:
            _parts.append(f"VaR {_v:,.0f} > {_lims['var']:,.0f}")
        if abs(_m) > _lims["mtm"]:
            _parts.append(f"|MTM| {abs(_m):,.0f} > {_lims['mtm']:,.0f}")
        if _parts:
            alerts.append(f"{_ac}: {' | '.join(_parts)}")
    if alerts:
        for alert in alerts:
            st.error(f"⚠️ {alert}")
    else:
        st.success("✅ No active desk watch breaches")

    st.markdown("#### Symbol Breakdown")
    rows = []
    for symbol, data in summary.get("symbols", {}).items():
        row = {"symbol": symbol}
        row.update(data)
        rows.append(row)
    if rows:
        rows.sort(key=lambda r: (r.get("asset_class", ""), r["symbol"]))
        st.dataframe(
            rows, use_container_width=True, hide_index=True,
            column_order=["asset_class", "symbol", "position", "mark_price",
                          "gross_notional", "mtm", "var_1d_99"],
        )
    else:
        st.info("No positions yet — click 🚀 Demo or 📂 Replay in the sidebar.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — PRE-TRADE CHECK
# Wrapped in @st.fragment so the Run button doesn't trigger a full page re-run
# (which would jump the active tab back to Overview).
# ─────────────────────────────────────────────────────────────────────────────
@st.fragment
def _render_pretrade_tab() -> None:
    st.markdown("#### Trade Parameters")
    ptc_col1, ptc_col2, ptc_col3, ptc_col4 = st.columns(4)
    ptc_col1.selectbox(
        "Symbol",
        list(_SYMBOL_DEFAULTS.keys()),
        key="ptc_symbol",
        on_change=_on_ptc_symbol_change,
    )
    check_symbol = st.session_state["ptc_symbol"]
    check_side   = ptc_col2.selectbox("Side", ["BUY", "SELL"])
    check_scope  = ptc_col3.selectbox(
        "Scope", ["firm", "trader", "book"],
        help="firm = global portfolio · trader = per-trader · book = per-book",
    )
    check_trader = ptc_col4.text_input("Trader", value="alice")

    ptc_col5, ptc_col6, ptc_col7 = st.columns(3)
    check_quantity = ptc_col5.number_input(
        "Quantity", key="ptc_quantity", step=50_000.0, min_value=1.0,
    )
    check_price = ptc_col6.number_input(
        "Price", key="ptc_price", step=0.0001, min_value=0.0001, format="%.6f",
    )
    check_book = ptc_col7.text_input("Book", key="ptc_book")

    if st.button("▶ Run Pre-Trade Check", type="primary", use_container_width=True):
        pre_trade_result = safe_post_json(
            "/trade/check",
            {
                "symbol":   check_symbol,
                "side":     check_side,
                "quantity": check_quantity,
                "price":    check_price,
                "book":     check_book,
                "trader":   check_trader,
                "scope":    check_scope,
            },
        )
        if pre_trade_result:
            accepted = pre_trade_result.get("accepted", False)
            if accepted:
                st.success("✅ Pre-trade check **accepted**")
            else:
                st.error("❌ Pre-trade check **rejected**")
                for breach in pre_trade_result.get("breaches", []):
                    st.error(f"  • {breach}")

            st.divider()
            st.markdown("#### Impact Analysis")
            scope_label = f"{pre_trade_result.get('scope','firm')} / {pre_trade_result.get('scope_key','firm')}"
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Trade Notional",     f"{pre_trade_result.get('trade_notional', 0):,.0f}")
            m2.metric(
                "Current Notional",
                f"{pre_trade_result.get('current_notional_abs', 0):,.0f}",
                help=f"Scope: {scope_label} — SQL SUM(NOTIONAL)",
            )
            m3.metric(
                "Projected Notional",
                f"{pre_trade_result.get('projected_notional_abs', 0):,.0f}",
                delta=f"+{pre_trade_result.get('trade_notional', 0):,.0f}",
            )
            m4.metric(
                "Projected VaR 1d99%",
                f"{pre_trade_result.get('projected_var_1d_99', 0):,.0f}",
                delta=f"{pre_trade_result.get('projected_var_1d_99', 0) - pre_trade_result.get('current_var_1d_99', 0):,.0f}",
            )
            st.caption(f"Scope: **{scope_label}** | Current VaR: {pre_trade_result.get('current_var_1d_99', 0):,.0f}")
            with st.expander("Raw JSON"):
                st.json(pre_trade_result)


with tab_pretrade:
    _render_pretrade_tab()

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — SCENARIOS
# Wrapped in @st.fragment so button/form interactions only re-run this section,
# not the whole page — this prevents the active tab from resetting to Overview.
# ─────────────────────────────────────────────────────────────────────────────
@st.fragment
def _render_scenarios_tab() -> None:
    # Fetch scenario history fresh on each fragment run
    try:
        _scenario_history = get_json("/scenario/history?limit=20")
    except requests.RequestException:
        _scenario_history = {"count": 0, "items": []}

    st.markdown("#### Run Scenario")
    sc_col1, sc_col2 = st.columns([1, 2])
    with sc_col1:
        st.markdown("**Preset**")
        preset_choice = st.selectbox(
            "Preset", list(PRESET_SCENARIOS.keys()),
            label_visibility="collapsed",
            key="preset_selectbox",
            on_change=_on_preset_change,
        )
        if st.button("▶ Run Preset", use_container_width=True, type="primary"):
            result = safe_post_json("/scenario/shock", {"preset": preset_choice})
            if result:
                st.session_state["scenario_result"] = result
                get_json.clear()
    with sc_col2:
        st.markdown("**Custom shocks (%)**")
        with st.form("custom_shock_form", border=False):
            st.caption("FX / Commodity")
            cs1, cs2, cs3 = st.columns(3)
            custom_eurusd = cs1.number_input("EURUSD %",    step=0.5, format="%.2f", key="cs_eurusd")
            custom_usdjpy = cs2.number_input("USDJPY %",    step=0.5, format="%.2f", key="cs_usdjpy")
            custom_gold   = cs3.number_input("SPOT_GOLD %", step=0.5, format="%.2f", key="cs_gold")
            st.caption("Equity")
            cs4, cs5, _ = st.columns(3)
            custom_spx  = cs4.number_input("SPX %",  step=0.5, format="%.2f", key="cs_spx")
            custom_aapl = cs5.number_input("AAPL %", step=0.5, format="%.2f", key="cs_aapl")
            st.caption("Fixed Income")
            cs6, cs7, _ = st.columns(3)
            custom_us10y = cs6.number_input("US10Y %", step=0.1, format="%.2f", key="cs_us10y")
            custom_us2y  = cs7.number_input("US2Y %",  step=0.1, format="%.2f", key="cs_us2y")
            if st.form_submit_button("▶ Run Custom", use_container_width=True):
                result = safe_post_json(
                    "/scenario/shock",
                    {
                        "custom_shocks": {
                            "EURUSD":    custom_eurusd / 100.0,
                            "USDJPY":    custom_usdjpy / 100.0,
                            "SPOT_GOLD": custom_gold   / 100.0,
                            "SPX":       custom_spx    / 100.0,
                            "AAPL":      custom_aapl   / 100.0,
                            "US10Y":     custom_us10y  / 100.0,
                            "US2Y":      custom_us2y   / 100.0,
                        }
                    },
                )
                if result:
                    st.session_state["scenario_result"] = result
                    get_json.clear()

    st.divider()

    scenario_result = st.session_state.get("scenario_result")
    if scenario_result:
        shocked = scenario_result.get("shocked", {})
        delta   = scenario_result.get("delta", {})
        st.markdown(
            f"**Scenario:** {scenario_result.get('scenario_name', 'n/a')} &nbsp;|&nbsp; "
            f"**Shocks:** {scenario_result.get('shocks', {})}"
        )
        sm1, sm2, sm3 = st.columns(3)
        sm1.metric("Notional Δ",  f"{delta.get('total_notional_abs', 0):+,.2f}",
                   f"→ {shocked.get('total_notional_abs', 0):,.2f}")
        sm2.metric("Net MTM Δ",   f"{delta.get('net_mtm', 0):+,.2f}",
                   f"→ {shocked.get('net_mtm', 0):,.2f}")
        sm3.metric("VaR 1d99% Δ", f"{delta.get('var_1d_99', 0):+,.2f}",
                   f"→ {shocked.get('var_1d_99', 0):,.2f}")
        shocked_prices = scenario_result.get("shocked_prices", {})
        if shocked_prices:
            st.markdown("**Shocked prices**")
            st.dataframe(
                [{"symbol": s, "shocked_price": p} for s, p in shocked_prices.items()],
                use_container_width=True, hide_index=True,
            )
        st.divider()

    st.markdown("#### Scenario History")
    hist_btn1, hist_btn2 = st.columns([1, 1])
    if hist_btn1.button("⬇ Export CSV", key="export_csv", use_container_width=True):
        try:
            csv_bytes = requests.get(
                f"{API_BASE_URL}/scenario/history/export.csv", timeout=TIMEOUT_SECONDS
            ).content
            st.download_button(
                "💾 Save scenario_history.csv",
                data=csv_bytes,
                file_name="scenario_history.csv",
                mime="text/csv",
            )
        except requests.RequestException:
            st.caption("CSV export unavailable")
    if hist_btn2.button("🗑️ Clear History", key="clear_history", use_container_width=True):
        result = safe_post_json("/scenario/history/clear")
        if result:
            st.session_state["scenario_result"] = None
            get_json.clear()
            st.success("Scenario history cleared.")
    history_rows = _scenario_history.get("items", [])
    if history_rows:
        st.dataframe(history_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No scenario runs recorded yet.")


with tab_scenarios:
    _render_scenarios_tab()

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — GOVERNANCE
# ─────────────────────────────────────────────────────────────────────────────
with tab_governance:
    g1, g2 = st.columns(2)
    breach_rows = breaches.get("items", [])
    g1.metric("Total Breaches (last 20)", len(breach_rows))
    if current_limits:
        g2.metric(
            "Firm Notional Limit",
            f"{current_limits.get('max_notional_abs', 0):,.0f}",
            help="Set in sidebar → Firm Hard Limits",
        )

    st.divider()
    st.markdown("#### Breach Audit Log")
    if breach_rows:
        st.dataframe(breach_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No breach events recorded yet.")

    if api_metrics.get("routes"):
        st.divider()
        st.markdown("#### API Route Metrics")
        metric_rows = [
            {
                "route": path,
                "calls": stats.get("count", 0),
                "errors": stats.get("error_count", 0),
                "avg_ms": stats.get("avg_ms", 0),
                "max_ms": stats.get("max_ms", 0),
                "last_ms": stats.get("last_ms", 0),
            }
            for path, stats in api_metrics["routes"].items()
        ]
        st.dataframe(metric_rows, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — BLOTTER
# Wrapped in @st.fragment so refresh buttons don't reset the active tab.
# ─────────────────────────────────────────────────────────────────────────────
@st.fragment
def _render_blotter_tab() -> None:
    sub_trades, sub_prices = st.tabs(["🧾 Trades", "💱 Prices"])

    with sub_trades:
        tr_hdr, tr_btn = st.columns([6, 1])
        tr_hdr.markdown("#### Trade Blotter")
        if tr_btn.button("🔄", key="blotter_trades_refresh", help="Re-fetch trades", use_container_width=True):
            get_json.clear()
        try:
            blotter_trades = get_json("/trades?limit=500")
        except requests.RequestException:
            blotter_trades = {"count": 0, "items": []}

        trade_items = blotter_trades.get("items", [])
        bl1, bl2, bl3, bl4 = st.columns(4)
        bl_symbol = bl1.selectbox("Symbol", ["— all —"] + sorted({t["symbol"] for t in trade_items}), key="bl_sym")
        bl_trader = bl2.selectbox("Trader", ["— all —"] + sorted({t["trader"] for t in trade_items}), key="bl_trader")
        bl_book   = bl3.selectbox("Book",   ["— all —"] + sorted({t["book"]   for t in trade_items}), key="bl_book")
        bl_side   = bl4.selectbox("Side",   ["— all —", "BUY", "SELL"], key="bl_side")

        filtered = trade_items
        if bl_symbol != "— all —":
            filtered = [t for t in filtered if t["symbol"] == bl_symbol]
        if bl_trader != "— all —":
            filtered = [t for t in filtered if t["trader"] == bl_trader]
        if bl_book   != "— all —":
            filtered = [t for t in filtered if t["book"]   == bl_book]
        if bl_side   != "— all —":
            filtered = [t for t in filtered if t["side"]   == bl_side]

        st.caption(f"Showing {len(filtered):,} of {blotter_trades.get('count', 0):,} trades (latest first)")
        if filtered:
            st.dataframe(
                filtered,
                use_container_width=True,
                hide_index=True,
                column_order=["timestamp", "trade_id", "symbol", "side", "trader",
                               "book", "quantity", "price", "notional", "trade_date"],
            )
        else:
            st.info("No trades yet — click 🚀 Demo or 📂 Replay in the sidebar.")

    with sub_prices:
        pr_hdr, pr_btn = st.columns([6, 1])
        pr_hdr.markdown("#### Mark Prices")
        if pr_btn.button("🔄", key="blotter_prices_refresh", help="Re-fetch prices", use_container_width=True):
            get_json.clear()
        try:
            blotter_prices = get_json("/prices")
        except requests.RequestException:
            blotter_prices = {"count": 0, "items": []}

        price_items = blotter_prices.get("items", [])
        if price_items:
            st.caption(f"{len(price_items)} symbol(s) — mark prices update every stream tick")
            st.dataframe(
                sorted(price_items, key=lambda r: r["symbol"]),
                use_container_width=True,
                hide_index=True,
                column_order=["symbol", "price", "timestamp"],
            )
        else:
            st.info("No prices yet — start the stream or run a Demo.")


with tab_blotter:
    _render_blotter_tab()