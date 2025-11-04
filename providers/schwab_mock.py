"""
Mock Schwab transport for smoke-testing order execution without hitting the real API.

Implements the subset of the schwab client interface that our SchwabTrader uses:
- preview_order(account_id, order)
- place_order(account_id, order)

Also provides light stubs for account endpoints used in the UI helper paths:
- get_account_numbers()
- get_account(account_id, fields=None)

Usage:
    from providers.schwab_trading import SchwabTrader
    from providers.schwab_mock import MockSchwabClient

    trader = SchwabTrader(account_id="HASH123", dry_run=False, client=MockSchwabClient())
    ... build order ...
    trader.preview_order(order)
    trader.submit_order(order, strategy_type="csp")

This exercises safety checks, preview tracking, response parsing, and file export
without touching the live Schwab API.
"""

from __future__ import annotations
import json
import random
import time
from types import SimpleNamespace
from datetime import datetime


class _MockResponse:
    def __init__(self, data: dict, status_code: int = 200, headers: dict | None = None):
        self._data = data
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> dict:
        return self._data

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"Mock HTTP {self.status_code}")


class MockSchwabClient:
    """
    Drop-in mock for the subset of schwab.client.Client our code calls.
    Safe for local smoke tests.
    """

    # --- Trading endpoints ---

    def preview_order(self, account_id: str, order: dict) -> _MockResponse:
        # Simulate a short delay and a deterministic fee calc
        time.sleep(0.05)
        est_value = self._estimate_order_value(order)
        preview = {
            "orderPreview": {
                "accountId": account_id,
                "estimatedValue": round(est_value, 2),
                "estimatedCommission": 0.65,  # flat per-leg mock
                "buyingPowerEffect": {
                    "changeInBuyingPower": -abs(round(est_value, 2))
                },
                "messages": [{"type": "INFO", "text": "Mock preview OK"}],
            }
        }
        return _MockResponse(preview, status_code=200)

    def place_order(self, account_id: str, order: dict) -> _MockResponse:
        # Simulate order acceptance and return an orderId in headers
        time.sleep(0.05)
        order_id = str(int(time.time())) + str(random.randint(100, 999))
        location = f"https://api.mock.schwab/trader/v1/accounts/{account_id}/orders/{order_id}"
        body = {
            "orderId": order_id,
            "status": "ACCEPTED",
            "receivedTime": datetime.utcnow().isoformat() + "Z",
        }
        return _MockResponse(body, status_code=201, headers={"Location": location})

    # --- Accounts/quotes endpoints (minimal stubs for UI helpers) ---

    def get_account_numbers(self) -> _MockResponse:
        data = [
            {"accountNumber": "000000000", "hashValue": "HASH000"},
            {"accountNumber": "111111111", "hashValue": "HASH111"},
        ]
        return _MockResponse(data)

    class Account(SimpleNamespace):
        class Fields:
            POSITIONS = "positions"

    def get_account(self, account_id: str, fields: str | None = None) -> _MockResponse:
        # Provide a minimal structure used by SchwabTrader.get_account_info
        data = {
            "securitiesAccount": {
                "type": "MARGIN",
                "accountNumber": account_id,
                "currentBalances": {
                    "cashBalance": 50000.0,
                    "buyingPower": 200000.0,
                    "optionBuyingPower": 50000.0,
                },
                "positions": [
                    {
                        "instrument": {"assetType": "EQUITY", "symbol": "AAPL"},
                        "longQuantity": 200,
                        "averagePrice": 150.0,
                        "marketValue": 30000.0,
                    }
                ],
            }
        }
        return _MockResponse(data)

    # --- Helpers ---

    def _estimate_order_value(self, order: dict) -> float:
        # Very rough estimate based on limit/credit/debit and legs quantities
        price = float(order.get("price", 0.0) or 0.0)
        ot = (order.get("orderType") or "").upper()
        qty = sum(int(leg.get("quantity", 0)) for leg in order.get("orderLegCollection", []))
        # Assume options quantities are in contracts (x100 shares)
        shares = qty * 100
        sign = 1.0
        if ot in ("NET_DEBIT", "LIMIT"):
            sign = -1.0
        elif ot in ("NET_CREDIT",):
            sign = 1.0
        return sign * price * shares
