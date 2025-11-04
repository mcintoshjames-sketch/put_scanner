from __future__ import annotations
import json
from pathlib import Path
import pytest

from providers.schwab_trading import SchwabTrader
from providers.schwab_mock import MockSchwabClient


@pytest.fixture()
def trader(tmp_path: Path) -> SchwabTrader:
    return SchwabTrader(
        account_id="HASH_TEST",
        dry_run=False,  # exercise live path with mock transport
        client=MockSchwabClient(),
        export_dir=str(tmp_path),  # keep artifacts isolated per test
    )


def build_csp_order(trader: SchwabTrader):
    return trader.create_cash_secured_put_order(
        symbol="AAPL",
        expiration="2025-12-19",
        strike=100.0,
        quantity=1,
        limit_price=1.50,
        duration="GTC",
    )


def test_mock_trading_happy_path(trader: SchwabTrader, tmp_path: Path):
    order = build_csp_order(trader)

    # Validate order structure
    v = trader.validate_order(order)
    assert v["valid"], f"order invalid: {v['errors']}"

    # Preview must succeed and write file
    prev = trader.preview_order(order)
    assert prev["status"] == "preview_success"
    preview_path = Path(prev["filepath"]) if "filepath" in prev else None
    assert preview_path and preview_path.exists()

    # Submit must succeed and write executed file with orderId
    res = trader.submit_order(order, strategy_type="csp")
    assert res["status"] == "executed"
    assert "order_id" in res and res["order_id"]

    exec_path = Path(res["filepath"]) if "filepath" in res else None
    assert exec_path and exec_path.exists()

    data = json.loads(exec_path.read_text())
    assert data.get("status") == "LIVE_TRADE_EXECUTED"
    assert data.get("order_id") == res["order_id"]
    legs = data.get("order", {}).get("orderLegCollection", [])
    assert isinstance(legs, list) and len(legs) >= 1


def test_submit_without_preview_raises(trader: SchwabTrader):
    order = build_csp_order(trader)

    with pytest.raises(RuntimeError) as ei:
        trader.submit_order(order, strategy_type="csp")

    # Error message should indicate preview requirement
    msg = str(ei.value)
    assert "previewed" in msg.lower() and "preview" in msg.lower()


def test_covered_call_order(trader: SchwabTrader, tmp_path: Path):
    order = trader.create_covered_call_order(
        symbol="AAPL",
        expiration="2025-12-19",
        strike=160.0,
        quantity=2,
        limit_price=1.25,
        duration="DAY",
    )

    v = trader.validate_order(order)
    assert v["valid"]
    assert order["orderType"] == "LIMIT"
    assert order["duration"] == "DAY"
    assert "price" in order and order["price"] == 1.25

    legs = order.get("orderLegCollection", [])
    assert len(legs) == 1
    assert legs[0]["instruction"] == "SELL_TO_OPEN"

    # Preview + submit
    trader.preview_order(order)
    res = trader.submit_order(order, strategy_type="cc")
    assert res["status"] == "executed"


def test_buy_write_order(trader: SchwabTrader):
    order = trader.create_buy_write_order(
        symbol="AAPL",
        expiration="2025-12-19",
        strike=160.0,
        quantity=1,
        stock_price_limit=150.0,
        option_credit=2.50,
        duration="GTC",
    )

    v = trader.validate_order(order)
    assert v["valid"]
    assert order["orderType"] == "NET_DEBIT"
    # Net debit per share = stock_price_limit - option_credit
    assert order["price"] == 147.5
    assert order["duration"] == "GTC"

    legs = order.get("orderLegCollection", [])
    assert len(legs) == 2
    assert legs[0]["instruction"] == "BUY"  # equity shares
    assert legs[1]["instruction"] == "SELL_TO_OPEN"  # call option

    trader.preview_order(order)
    res = trader.submit_order(order, strategy_type="buy_write")
    assert res["status"] == "executed"


def test_collar_order(trader: SchwabTrader):
    order = trader.create_collar_order(
        symbol="AAPL",
        expiration="2025-12-19",
        call_strike=170.0,
        put_strike=150.0,
        quantity=1,
        limit_price=0.10,  # small net credit
        duration="GTC",
    )

    v = trader.validate_order(order)
    assert v["valid"]
    assert order["orderType"] == "NET_CREDIT"
    assert order["price"] == 0.10
    legs = order.get("orderLegCollection", [])
    assert len(legs) == 2
    assert legs[0]["instruction"] == "SELL_TO_OPEN"  # call
    assert legs[1]["instruction"] == "BUY_TO_OPEN"   # put

    trader.preview_order(order)
    res = trader.submit_order(order, strategy_type="collar")
    assert res["status"] == "executed"


def test_iron_condor_order(trader: SchwabTrader):
    order = trader.create_iron_condor_order(
        symbol="AAPL",
        expiration="2025-12-19",
        long_put_strike=95.0,
        short_put_strike=100.0,
        short_call_strike=110.0,
        long_call_strike=115.0,
        quantity=1,
        limit_price=1.20,
        duration="DAY",
    )

    v = trader.validate_order(order)
    assert v["valid"]
    assert order["orderType"] == "NET_CREDIT"
    assert order["price"] == 1.20
    legs = order.get("orderLegCollection", [])
    assert len(legs) == 4
    assert [leg["instruction"] for leg in legs] == [
        "BUY_TO_OPEN",
        "SELL_TO_OPEN",
        "SELL_TO_OPEN",
        "BUY_TO_OPEN",
    ]

    trader.preview_order(order)
    res = trader.submit_order(order, strategy_type="iron_condor")
    assert res["status"] == "executed"
