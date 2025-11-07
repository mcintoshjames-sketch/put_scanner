"""Tests for PMCC and Synthetic Collar order constructors in SchwabTrader.
Run with: pytest -q test_pmcc_synthetic_orders.py
"""
import pytest
from providers.schwab_trading import SchwabTrader

@pytest.fixture
def trader():
    return SchwabTrader(dry_run=True)

def test_pmcc_entry_order(trader):
    order = trader.create_pmcc_order(
        symbol="AAPL",
        long_expiration="2026-01-17",
        long_strike=120.0,
        short_expiration="2025-12-19",
        short_strike=150.0,
        quantity=2,
        net_debit_limit=15.25,
        duration="GTC"
    )
    assert order["orderType"] == "NET_DEBIT"
    assert len(order["orderLegCollection"]) == 2
    legs = order["orderLegCollection"]
    assert legs[0]["instruction"] == "BUY_TO_OPEN"
    assert legs[1]["instruction"] == "SELL_TO_OPEN"
    assert "C" in legs[0]["instrument"]["symbol"]
    assert "C" in legs[1]["instrument"]["symbol"]

def test_pmcc_exit_order(trader):
    order = trader.create_pmcc_exit_order(
        symbol="AAPL",
        long_expiration="2026-01-17",
        long_strike=120.0,
        short_expiration="2025-12-19",
        short_strike=150.0,
        quantity=2,
        net_limit_price=3.10,
        duration="DAY"
    )
    assert len(order["orderLegCollection"]) == 2
    assert order["orderLegCollection"][0]["instruction"] == "BUY_TO_CLOSE"
    assert order["orderLegCollection"][1]["instruction"] == "SELL_TO_CLOSE"


def test_synthetic_collar_entry_order(trader):
    order = trader.create_synthetic_collar_order(
        symbol="MSFT",
        long_expiration="2026-03-21",
        long_call_strike=250.0,
        short_expiration="2025-12-19",
        put_strike=230.0,
        short_call_strike=300.0,
        quantity=1,
        net_limit_price=22.40,
        duration="DAY"
    )
    assert len(order["orderLegCollection"]) == 3
    instrs = [leg["instruction"] for leg in order["orderLegCollection"]]
    assert instrs.count("BUY_TO_OPEN") == 2  # long call + long put
    assert instrs.count("SELL_TO_OPEN") == 1  # short call


def test_synthetic_collar_exit_order(trader):
    order = trader.create_synthetic_collar_exit_order(
        symbol="MSFT",
        long_expiration="2026-03-21",
        long_call_strike=250.0,
        short_expiration="2025-12-19",
        put_strike=230.0,
        short_call_strike=300.0,
        quantity=1,
        net_limit_price=5.15,
        duration="GTC"
    )
    assert len(order["orderLegCollection"]) == 3
    instrs = [leg["instruction"] for leg in order["orderLegCollection"]]
    assert instrs.count("BUY_TO_CLOSE") == 1  # short call
    assert instrs.count("SELL_TO_CLOSE") == 2  # long call + long put

