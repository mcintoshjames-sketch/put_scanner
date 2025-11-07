"""
Integration validation for PMCC and Synthetic Collar using live market data.

- Pulls real chains via yfinance (or configured provider fallbacks)
- Builds candidates with analyze_pmcc/analyze_synthetic_collar
- Verifies Monte Carlo outputs are finite and within reasonable bounds
- Confirms Schwab order constructors build valid payloads from real strikes/expirations
- Asserts runbook text includes key metrics and instructions

Set RUN_INTEGRATION=1 to run these tests (they use network calls).
Run: RUN_INTEGRATION=1 pytest -q test_pmcc_synthetic_validation.py
"""
from __future__ import annotations
import os
import math
import pytest
import pandas as pd

# Skip by default unless explicitly enabled
if not os.getenv("RUN_INTEGRATION"):
    pytest.skip("Skipping live-data validation tests; set RUN_INTEGRATION=1 to run.", allow_module_level=True)

from strategy_analysis import analyze_pmcc, analyze_synthetic_collar
from strategy_lab import build_runbook
from providers.schwab_trading import SchwabTrader

TICKERS = ["AAPL", "MSFT", "SPY", "QQQ"]


def _first_valid(df: pd.DataFrame) -> pd.Series | None:
    if df is None or df.empty:
        return None
    # Prefer rows with finite MC metrics
    df2 = df.copy()
    if "MC_ROI_ann%" in df2.columns:
        df2 = df2[pd.to_numeric(df2["MC_ROI_ann%"], errors="coerce").notna()]
    return df2.iloc[0] if not df2.empty else df.iloc[0]


def _finite(x) -> bool:
    try:
        f = float(x)
        return math.isfinite(f)
    except Exception:
        return False


def test_pmcc_live_validation():
    # Find a PMCC candidate from a liquid ticker
    row = None
    picked = None
    for t in TICKERS:
        try:
            df = analyze_pmcc(t)
        except Exception:
            continue
        cand = _first_valid(df)
        if cand is not None:
            row = cand
            picked = t
            break
    if row is None:
        pytest.skip("No PMCC candidate found from live data (chains unavailable)")

    # Basic structure checks
    assert row["Strategy"] == "PMCC"
    assert float(row["NetDebit"]) > 0.0
    assert 0.60 <= float(row.get("LongΔ", 0.0)) <= 0.98
    assert 0.15 <= float(row.get("ShortΔ", 0.0)) <= 0.45

    # MC reasonableness (prefer MC outputs; fall back to deterministic ROI if MC unavailable)
    mc_pnl = row.get("MC_ExpectedPnL")
    mc_roi_val = float(row.get("MC_ROI_ann%", float("nan")))
    if _finite(mc_pnl) and _finite(mc_roi_val):
        assert -200.0 <= mc_roi_val <= 300.0
    else:
        roi_ann = float(row.get("ROI%_ann", float("nan")))
        assert _finite(roi_ann), "ROI%_ann should be finite when MC metrics are unavailable"
        assert -100.0 <= roi_ann <= 500.0

    # Runbook content
    rb = build_runbook("PMCC", row, contracts=1, capture_pct=0.70)
    assert picked is not None and picked in rb
    assert "PMCC" in rb
    assert "Net Debit" in rb
    assert "EXIT ORDERS" in rb
    assert "BTC" in rb  # profit-take short call
    # Strikes present
    assert str(int(float(row["LongStrike"]))) in rb
    assert str(int(float(row["ShortStrike"]))) in rb

    # Trade constructors using real exp/strikes
    trader = SchwabTrader(dry_run=True)
    order = trader.create_pmcc_order(
        symbol=row["Ticker"],
        long_expiration=str(row["LongExp"]),
        long_strike=float(row["LongStrike"]),
        short_expiration=str(row["Exp"]),
        short_strike=float(row["ShortStrike"]),
        quantity=1,
        net_debit_limit=round(float(row["NetDebit"]), 2),
        duration="GTC",
    )
    assert order["orderType"] == "NET_DEBIT"
    legs = order["orderLegCollection"]
    assert len(legs) == 2
    assert legs[0]["instruction"] == "BUY_TO_OPEN" and "C" in legs[0]["instrument"]["symbol"]
    assert legs[1]["instruction"] == "SELL_TO_OPEN" and "C" in legs[1]["instrument"]["symbol"]

    exit_order = trader.create_pmcc_exit_order(
        symbol=row["Ticker"],
        long_expiration=str(row["LongExp"]),
        long_strike=float(row["LongStrike"]),
        short_expiration=str(row["Exp"]),
        short_strike=float(row["ShortStrike"]),
        quantity=1,
        net_limit_price=round(max(0.05, 0.25 * float(row.get("ShortPrem", 0.50))), 2),
        duration="DAY",
    )
    assert len(exit_order["orderLegCollection"]) == 2
    assert exit_order["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    assert exit_order["orderLegCollection"][1]["instruction"] == "SELL_TO_CLOSE"


def test_synthetic_collar_live_validation():
    # Find a Synthetic Collar candidate
    row = None
    picked = None
    for t in TICKERS:
        try:
            df = analyze_synthetic_collar(t)
        except Exception:
            continue
        cand = _first_valid(df)
        if cand is not None:
            row = cand
            picked = t
            break
    if row is None:
        pytest.skip("No Synthetic Collar candidate found from live data")

    # Structure checks
    assert row["Strategy"] == "SYNTHETIC_COLLAR"
    assert float(row["NetDebit"]) > 0.0
    assert 0.60 <= float(row.get("LongΔ", 0.0)) <= 0.98
    assert 0.15 <= float(row.get("ShortΔ", 0.0)) <= 0.45
    assert -0.30 <= float(row.get("PutΔ", 0.0)) <= -0.05

    # MC reasonableness (prefer MC outputs; fall back to deterministic ROI if MC unavailable)
    mc_pnl = row.get("MC_ExpectedPnL")
    mc_roi_val = float(row.get("MC_ROI_ann%", float("nan")))
    if _finite(mc_pnl) and _finite(mc_roi_val):
        assert -200.0 <= mc_roi_val <= 300.0
    else:
        roi_ann = float(row.get("ROI%_ann", float("nan")))
        assert _finite(roi_ann), "ROI%_ann should be finite when MC metrics are unavailable"
        assert -100.0 <= roi_ann <= 500.0

    # Runbook content
    rb = build_runbook("SYNTHETIC_COLLAR", row, contracts=1, capture_pct=0.70)
    assert picked is not None and picked in rb
    assert "SYNTHETIC COLLAR" in rb
    assert "Net Debit" in rb
    assert "EXIT ORDERS" in rb
    assert "BTC" in rb  # profit-take short call
    # Strikes present
    assert str(int(float(row["LongStrike"]))) in rb
    assert str(int(float(row["PutStrike"]))) in rb
    assert str(int(float(row["ShortStrike"]))) in rb

    # Trade constructors
    trader = SchwabTrader(dry_run=True)
    order = trader.create_synthetic_collar_order(
        symbol=row["Ticker"],
        long_expiration=str(row["LongExp"]),
        long_call_strike=float(row["LongStrike"]),
        short_expiration=str(row["Exp"]),
        put_strike=float(row["PutStrike"]),
        short_call_strike=float(row["ShortStrike"]),
        quantity=1,
        net_limit_price=round(float(row["NetDebit"]), 2),
        duration="GTC",
    )
    legs = order["orderLegCollection"]
    assert len(legs) == 3
    instrs = [leg["instruction"] for leg in legs]
    assert instrs.count("BUY_TO_OPEN") == 2 and instrs.count("SELL_TO_OPEN") == 1

    exit_order = trader.create_synthetic_collar_exit_order(
        symbol=row["Ticker"],
        long_expiration=str(row["LongExp"]),
        long_call_strike=float(row["LongStrike"]),
        short_expiration=str(row["Exp"]),
        put_strike=float(row["PutStrike"]),
        short_call_strike=float(row["ShortStrike"]),
        quantity=1,
        net_limit_price=round(max(0.05, 0.25 * float(row.get("ShortPrem", 0.50))), 2),
        duration="DAY",
    )
    exit_instrs = [leg["instruction"] for leg in exit_order["orderLegCollection"]]
    assert exit_instrs.count("BUY_TO_CLOSE") == 1  # short call
    assert exit_instrs.count("SELL_TO_CLOSE") == 2  # long call + long put
