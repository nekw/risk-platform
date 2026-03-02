PRESET_SCENARIOS: dict[str, dict[str, float]] = {
    # FX / Commodity
    "FX +2%":          {"EURUSD": 0.02, "USDJPY": 0.02},
    "Gold -3%":        {"SPOT_GOLD": -0.03},
    "Risk-Off":        {"EURUSD": -0.015, "USDJPY": 0.01,  "SPOT_GOLD": 0.03},
    # Equity
    "Equity Sell-Off": {"SPX": -0.05,   "AAPL": -0.07, "EURUSD": -0.01},
    "Equity Rally":    {"SPX":  0.03,   "AAPL":  0.04},
    # Fixed Income (bond prices fall when rates rise)
    "Rate Shock +50bp":{"US10Y": -0.03, "US2Y": -0.01},
    "Rate Rally -50bp":{"US10Y":  0.03, "US2Y":  0.01},
}
