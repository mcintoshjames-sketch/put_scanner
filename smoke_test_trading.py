#!/usr/bin/env python3
"""
Smoke test the live trading order execution path WITHOUT sending real orders.

This uses a mock Schwab client to exercise:
- Order construction helpers
- Preview safety mechanism and file export
- Live submit path (with preview check) and executed-file export
- Response parsing (Location header orderId extraction)

It does not contact the real Schwab API.
"""

from __future__ import annotations
import json
from pathlib import Path

from providers.schwab_trading import SchwabTrader
from providers.schwab_mock import MockSchwabClient


def main() -> int:
    export_dir = Path("./trade_orders"); export_dir.mkdir(exist_ok=True)

    # Create trader with dry_run=False but a mock transport client
    trader = SchwabTrader(account_id="HASH_DEMO", dry_run=False, client=MockSchwabClient())

    # Build a small, deterministic sample order (CSP)
    order = trader.create_cash_secured_put_order(
        symbol="AAPL",
        expiration="2025-12-19",
        strike=100.0,
        quantity=1,
        limit_price=1.50,  # limit credit per share
        duration="GTC",
    )

    # Validate basic shape
    validation = trader.validate_order(order)
    if not validation["valid"]:
        print("❌ Order validation failed:")
        for e in validation["errors"]:
            print("  -", e)
        return 1

    # Preview (mocked)
    prev = trader.preview_order(order)
    print("✅ Preview OK:")
    print("  ", prev["message"])  # file path

    # Submit (mocked). Preview check must pass.
    res = trader.submit_order(order, strategy_type="csp")
    print("✅ Submit OK:")
    print("  ", res["message"])  # file path + order id if available

    # Load executed record and show a short summary
    exec_path = Path(res["filepath"]) if "filepath" in res else None
    if exec_path and exec_path.exists():
        data = json.loads(exec_path.read_text())
        print("\nExecution record:")
        print(f"  status = {data.get('status')}")
        print(f"  order_id = {data.get('order_id')}")
        print(f"  account_id = {data.get('account_id')}")
        legs = data.get('order', {}).get('orderLegCollection', [])
        print(f"  legs = {len(legs)}")
    else:
        print("⚠️ Executed file not found (unexpected in mock path)")

    print("\nSmoke test complete. No live orders were sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
