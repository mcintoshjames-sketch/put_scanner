"""Quick check to ensure Schwab token refresh isn't invoked on every API call.

This script monkeypatches providers.schwab.auth.client_from_token_file to record how
many times it's invoked while exercising SchwabClient.last_price multiple times.
"""

import json
import os
import tempfile
from contextlib import contextmanager

from unittest import mock

from providers import schwab


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class FakeClient:
    def __init__(self):
        self.quote_calls = []

    def get_quote(self, symbol: str):
        self.quote_calls.append(symbol)
        return FakeResponse({symbol.upper(): {"quote": {"lastPrice": 123.45}}})


@contextmanager
def temp_token_file():
    fd, path = tempfile.mkstemp(prefix="schwab_token_", suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"token": {"access_token": "abc", "refresh_token": "def", "expires_at": 9999999999}}, fh)
    try:
        yield path
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    call_counter = {"client_from_token_file": 0}

    def fake_client_from_token_file(token_path, api_key, app_secret):
        call_counter["client_from_token_file"] += 1
        return FakeClient()

    with temp_token_file() as token_path:
        with mock.patch("providers.schwab.auth.client_from_token_file", side_effect=fake_client_from_token_file):
            client = schwab.SchwabClient(api_key="test", app_secret="secret", token_path=token_path)
            price_a = client.last_price("SPY")
            price_b = client.last_price("QQQ")

    summary = (
        f"client_from_token_file calls: {call_counter['client_from_token_file']}\n"
        f"SPY price: {price_a}\n"
        f"QQQ price: {price_b}\n"
    )
    # Persist summary for debugging environments where stdout is suppressed.
    with open("dev_scripts/test_refresh_behavior_output.txt", "w", encoding="utf-8") as fh:
        fh.write(summary)

    print(summary)


if __name__ == "__main__":
    main()
