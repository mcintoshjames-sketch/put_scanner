"""Profile end-to-end scan timings using the same pipeline as Streamlit.

This script imports `strategy_lab.run_scans` and calls it with a representative
set of tickers and parameters, without going through Streamlit. It measures the
overall runtime and prints basic stats about the resulting DataFrames.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Any, List
import os
import sys
import traceback
from datetime import datetime

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

# Ensure repo root is on sys.path so we can import strategy_lab
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import strategy_lab as sl  # noqa: E402

_silence_streamlit_logging()

RUN_SCANS = getattr(sl.run_scans, "__wrapped__", sl.run_scans)


def _log_to_file(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "profile_scan_timing.log",
    )
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"[{ts}] {message}\n")


def _default_params() -> Dict[str, Any]:
    """Construct a representative params dict similar to the app UI.

    These defaults mirror the keys passed to `run_scans` in `strategy_lab.py`.
    Values are intentionally moderate so the scan does real work but finishes
    quickly.
    """
    return {
        "min_days": 7,
        "days_limit": 45,
        "min_otm_csp": 5.0,
        "min_roi_csp": 20.0,
        "min_cushion": 5.0,
        "min_poew": 0.55,
        "min_otm_cc": 3.0,
        "min_roi_cc": 15.0,
        "include_div_cc": True,
        "call_delta_tgt": 0.25,
        "put_delta_tgt": 0.25,
        "include_div_col": True,
        "min_net_credit": 0.10,
        "ic_target_delta": 0.20,
        "ic_spread_width_put": 5.0,
        "ic_spread_width_call": 5.0,
        "ic_min_roi": 20.0,
        "ic_min_cushion": 5.0,
        "cs_spread_width": 5.0,
        "cs_target_delta": 0.20,
        "cs_min_roi": 20.0,
        # PMCC controls
        "pmcc_long_delta": 0.80,
        "pmcc_long_days_min": 180,
        "pmcc_long_days_max": 400,
        "pmcc_short_days_min": 21,
        "pmcc_short_days_max": 60,
        "pmcc_short_delta_lo": 0.20,
        "pmcc_short_delta_hi": 0.35,
        "pmcc_min_buffer_days": 120,
        "pmcc_avoid_exdiv": True,
        "pmcc_long_leg_min_oi": 50,
        "pmcc_long_leg_max_spread": 15.0,
        # Synthetic Collar controls
        "syn_long_delta": 0.80,
        "syn_put_delta_abs": 0.15,
        "syn_long_days_min": 180,
        "syn_long_days_max": 400,
        "syn_short_days_min": 21,
        "syn_short_days_max": 60,
        "syn_short_delta_lo": 0.20,
        "syn_short_delta_hi": 0.35,
        "syn_min_buffer_days": 120,
        "syn_avoid_exdiv": True,
        "syn_min_floor_sigma": 1.0,
        "syn_long_leg_min_oi": 50,
        "syn_long_leg_max_spread": 15.0,
        "syn_put_leg_min_oi": 50,
        "syn_put_leg_max_spread": 15.0,
        # Shared controls
        "min_oi": 50,
        "max_spread": 15.0,
        "earn_window": 7,
        "risk_free": 0.02,
        "per_contract_cap": 5000.0,
        "bill_yield": 0.0,
        "require_nonneg_mc": False,
    }


def _describe_df(name: str, df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return f"{name}: 0 rows"
    cols = list(df.columns)
    return f"{name}: {len(df)} rows, cols={cols[:8]}{'...' if len(cols) > 8 else ''}"


def main() -> None:
    tickers: List[str] = ["AAPL", "MSFT", "SPY", "AMD", "TSLA"]
    params = _default_params()

    n_runs = 3
    durations: List[float] = []

    print("Profiling full scan via run_scans()")
    print("Tickers:", ", ".join(tickers))
    print(f"Runs: {n_runs}\n")

    last_results = None

    for i in range(1, n_runs + 1):
        msg = f"Run {i}: starting"
        print(msg, flush=True)
        _log_to_file(msg)
        start = time.perf_counter()
        try:
            last_results = RUN_SCANS(tickers, params)
        except Exception as exc:  # pragma: no cover - diagnostic helper
            err_msg = f"Run {i}: error {exc}"
            print(err_msg, flush=True)
            _log_to_file(err_msg)
            traceback.print_exc()
            return
        elapsed = time.perf_counter() - start
        durations.append(elapsed)
        done_msg = f"Run {i}: completed in {elapsed:.3f}s"
        print(done_msg, flush=True)
        _log_to_file(done_msg)

    print("\nSummary over runs:")
    _log_to_file("Summary over runs:")
    min_msg = f"  min: {min(durations):.3f}s"
    max_msg = f"  max: {max(durations):.3f}s"
    avg = sum(durations) / len(durations)
    avg_msg = f"  avg: {avg:.3f}s"
    print(min_msg)
    print(max_msg)
    print(avg_msg)
    _log_to_file(min_msg)
    _log_to_file(max_msg)
    _log_to_file(avg_msg)

    if last_results is None:
        print("No successful runs completed; exiting.")
        return

    (
        df_csp,
        df_cc,
        df_collar,
        df_iron_condor,
        df_bull_put_spread,
        df_bear_call_spread,
        df_pmcc,
        df_synthetic_collar,
        scan_counters,
    ) = last_results

    print("\nResult sizes from last run:")
    _log_to_file("Result sizes from last run:")
    print("  ", _describe_df("CSP", df_csp))
    print("  ", _describe_df("CC", df_cc))
    print("  ", _describe_df("Collar", df_collar))
    print("  ", _describe_df("IronCondor", df_iron_condor))
    print("  ", _describe_df("BullPut", df_bull_put_spread))
    print("  ", _describe_df("BearCall", df_bear_call_spread))
    print("  ", _describe_df("PMCC", df_pmcc))
    print("  ", _describe_df("SyntheticCollar", df_synthetic_collar))

    print("\nScan counters (CSP if present):")
    _log_to_file("Scan counters (CSP if present):")
    csp_counters = scan_counters.get("CSP", {}) if isinstance(scan_counters, dict) else {}
    for k, v in csp_counters.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":  # pragma: no cover
    main()
