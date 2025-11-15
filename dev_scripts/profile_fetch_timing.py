"""Measure uncached data-fetch timings for Strategy Lab providers.

This script avoids Streamlit runtimes by using the *_uncached helper functions in
strategy_lab to exercise price, expiration, and chain fetches. It prints per-call
and aggregate timings so we can see where scans spend time.
"""

from __future__ import annotations

import statistics
import time
from typing import Dict, List

import logging

import pandas as pd


def _silence_streamlit_logging() -> None:
    logging.getLogger().setLevel(logging.CRITICAL)
    logger_names = [
        "streamlit",
        "streamlit.runtime",
        "streamlit.runtime.scriptrunner_utils",
        "streamlit.runtime.scriptrunner_utils.script_run_context",
        "streamlit.runtime.caching",
        "streamlit.runtime.caching.cache_data_api",
        "streamlit.runtime.state",
        "streamlit.runtime.state.session_state_proxy",
    ]
    for name in logger_names:
        logger = logging.getLogger(name)
        logger.setLevel(logging.CRITICAL)
        logger.disabled = True
        logger.propagate = False
        logger.handlers.clear()


_silence_streamlit_logging()

import strategy_lab as sl

_silence_streamlit_logging()

TICKERS = ["AAPL", "MSFT", "SPY", "AMD", "TSLA"]
MAX_EXPIRATIONS_PER_TICKER = 2


def timed_call(func, *args, **kwargs):
    start = time.perf_counter()
    try:
        result = func(*args, **kwargs)
        duration = time.perf_counter() - start
        return {
            "ok": True,
            "duration": duration,
            "result": result,
            "error": None,
        }
    except Exception as exc:  # pragma: no cover - diagnostic utility
        duration = time.perf_counter() - start
        return {
            "ok": False,
            "duration": duration,
            "result": None,
            "error": str(exc),
        }


def summarize(durations: List[float]) -> Dict[str, float]:
    if not durations:
        return {"count": 0, "avg": 0.0, "median": 0.0, "p95": 0.0}
    sorted_vals = sorted(durations)
    avg = sum(sorted_vals) / len(sorted_vals)
    median = statistics.median(sorted_vals)
    p95_idx = int(0.95 * (len(sorted_vals) - 1))
    return {
        "count": len(sorted_vals),
        "avg": avg,
        "median": median,
        "p95": sorted_vals[p95_idx],
    }


def main():  # pragma: no cover - diagnostic script
    price_times: List[float] = []
    exp_times: List[float] = []
    chain_times: List[float] = []

    per_ticker_chain_counts: Dict[str, int] = {}

    print("Profiling providers with tickers:", ", ".join(TICKERS))

    for ticker in TICKERS:
        price_result = timed_call(sl.fetch_price_uncached, ticker)
        if price_result["ok"]:
            price_times.append(price_result["duration"])
        print(f"{ticker}: price ok={price_result['ok']} time={price_result['duration']:.3f}s")
        if not price_result["ok"]:
            print(f"  price error: {price_result['error']}")

        exp_result = timed_call(sl.fetch_expirations_uncached, ticker)
        if exp_result["ok"]:
            exp_times.append(exp_result["duration"])
        print(f"{ticker}: expirations ok={exp_result['ok']} time={exp_result['duration']:.3f}s")
        if not exp_result["ok"]:
            print(f"  expirations error: {exp_result['error']}")
            continue

        expirations = exp_result["result"] or []
        if not expirations:
            print(f"  no expirations returned for {ticker}")
            continue

        per_ticker_chain_counts[ticker] = 0
        for exp in expirations[:MAX_EXPIRATIONS_PER_TICKER]:
            chain_result = timed_call(sl.fetch_chain_uncached, ticker, exp)
            per_ticker_chain_counts[ticker] += 1
            if chain_result["ok"]:
                chain_times.append(chain_result["duration"])
                rows = len(chain_result["result"]) if isinstance(chain_result["result"], pd.DataFrame) else "?"
                print(
                    f"  chain {exp}: ok time={chain_result['duration']:.3f}s rows={rows}"
                )
            else:
                print(
                    f"  chain {exp}: ERROR time={chain_result['duration']:.3f}s error={chain_result['error']}"
                )

    print("\nAggregate timings (seconds):")
    for label, durations in (
        ("price", price_times),
        ("expirations", exp_times),
        ("chain", chain_times),
    ):
        stats = summarize(durations)
        print(
            f"  {label:<12} count={stats['count']:>3} avg={stats['avg']:.3f} "
            f"median={stats['median']:.3f} p95={stats['p95']:.3f}"
        )

    print("\nChain fetch counts per ticker:")
    for ticker, count in per_ticker_chain_counts.items():
        print(f"  {ticker}: {count} chain requests")


if __name__ == "__main__":
    main()
