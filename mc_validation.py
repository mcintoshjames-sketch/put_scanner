"""
MC Validation for PMCC and Synthetic Collar

Goal: Confirm conceptual soundness of the MC calculations using real market inputs
by cross-validating with a deterministic quasi-Monte Carlo (quantile sampling)
under the same GBM assumptions and strategy payoff math.

Validation checks:
- Distribution agreement: MC vs quasi-MC for mean, p5, p50, p95 within tolerances
- Bounds consistency: MC min/max within grid min/max envelopes
- Capital consistency: capital_per_share > 0 and collateral matches definition
- Strategy payoff logic: vectorized revaluation of long LEAPS and (for SYNTHETIC_COLLAR) near-expiring put

Usage:
    from mc_validation import validate_strategy_mc
    report = validate_strategy_mc("SYNTHETIC_COLLAR", params, mu=0.0, rf=0.0, n=20000)

"""
from __future__ import annotations
import math
from typing import Dict, Any
import numpy as np
import pandas as pd

from options_math import mc_pnl

# ----------------------------- Helpers -----------------------------

def _norm_cdf_vec(x: np.ndarray) -> np.ndarray:
    np_erf = getattr(np, "erf", None)
    if np_erf is not None:
        return 0.5 * (1.0 + np_erf(x / np.sqrt(2.0)))
    v_erf = np.vectorize(math.erf, otypes=[float])
    return 0.5 * (1.0 + v_erf(x / np.sqrt(2.0)))


def _bs_call_val(S: np.ndarray, K: float, vol: float, T: float, rf: float) -> np.ndarray:
    vol = float(max(1e-6, min(vol, 3.0)))
    T = float(max(T, 1e-6))
    d1 = (np.log(S / K) + (rf + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    d2 = d1 - vol * np.sqrt(T)
    return S * _norm_cdf_vec(d1) - K * math.e**(-rf * T) * _norm_cdf_vec(d2)


def _bs_put_val(S: np.ndarray, K: float, vol: float, T: float, rf: float) -> np.ndarray:
    vol = float(max(1e-6, min(vol, 3.0)))
    T = float(max(T, 1e-6))
    d1 = (np.log(S / K) + (rf + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    d2 = d1 - vol * np.sqrt(T)
    call_val = S * _norm_cdf_vec(d1) - K * math.e**(-rf * T) * _norm_cdf_vec(d2)
    return call_val - S + K * math.e**(-rf * T)


# Robust inverse normal CDF (Acklam's approximation)
def _inv_norm_cdf(p: np.ndarray | float) -> np.ndarray:
    # Coefficients for approximation
    a = [
        -3.969683028665376e+01,
        2.209460984245205e+02,
        -2.759285104469687e+02,
        1.383577518672690e+02,
        -3.066479806614716e+01,
        2.506628277459239e+00,
    ]
    b = [
        -5.447609879822406e+01,
        1.615858368580409e+02,
        -1.556989798598866e+02,
        6.680131188771972e+01,
        -1.328068155288572e+01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e+00,
        -2.549732539343734e+00,
        4.374664141464968e+00,
        2.938163982698783e+00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e+00,
        3.754408661907416e+00,
    ]
    p = np.asarray(p, dtype=float)
    # Break-points
    plow = 0.02425
    phigh = 1 - plow
    z = np.zeros_like(p)
    # Lower region
    mask = p < plow
    if np.any(mask):
        q = np.sqrt(-2 * np.log(p[mask]))
        z[mask] = (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                  ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    # Central region
    mask = (p >= plow) & (p <= phigh)
    if np.any(mask):
        q = p[mask] - 0.5
        r = q*q
        z[mask] = (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5]) * q / \
                  (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1)
    # Upper region
    mask = p > phigh
    if np.any(mask):
        q = np.sqrt(-2 * np.log(1 - p[mask]))
        z[mask] = -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                   ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1)
    return z


def _erfinv(y: np.ndarray | float) -> np.ndarray:
    # erfinv(y) = invnormcdf((y+1)/2) / sqrt(2)
    p = (np.asarray(y, dtype=float) + 1.0) / 2.0
    return _inv_norm_cdf(p) / np.sqrt(2.0)


def _lognormal_quantile_samples(S0: float, mu: float, sigma: float, T: float, n: int) -> np.ndarray:
    # Deterministic quantile sampling (quasi-MC) using inverse CDF
    # u in (0,1), z = Phi^{-1}(u)
    i = np.arange(1, n + 1)
    u = (i - 0.5) / n
    z = np.sqrt(2.0) * _erfinv(2.0 * u - 1.0)
    drift = (mu - 0.5 * sigma**2) * T
    volterm = sigma * np.sqrt(T)
    return S0 * np.exp(drift + volterm * z)


# ----------------------------- Payoff functions -----------------------------

def _pnl_pmcc_per_share(S_T: np.ndarray, params: Dict[str, Any], days: int, rf: float) -> np.ndarray:
    long_K = float(params["long_call_strike"])
    long_cost = float(params["long_call_cost"])  # debit
    long_days_total = int(params.get("long_days_total", days))
    long_remaining_days = max(long_days_total - days, 1)
    short_K = float(params["short_call_strike"])
    short_prem = float(params["short_call_premium"])  # credit
    long_iv = float(params.get("long_iv", params.get("iv", 0.20)))
    short_iv = float(params.get("short_iv", params.get("iv", 0.20)))
    T_long_remaining = long_remaining_days / 365.0
    long_call_vals = _bs_call_val(S_T, long_K, long_iv, T_long_remaining, rf)
    intrinsic_short = np.maximum(0.0, S_T - short_K)
    return (long_call_vals - long_cost) + short_prem - intrinsic_short


def _pnl_synthetic_collar_per_share(S_T: np.ndarray, params: Dict[str, Any], days: int, rf: float) -> np.ndarray:
    long_K = float(params["long_call_strike"])
    long_cost = float(params["long_call_cost"])  # debit
    long_days_total = int(params.get("long_days_total", days))
    long_remaining_days = max(long_days_total - days, 1)
    put_K = float(params["put_strike"])
    put_cost = float(params["put_cost"])  # debit
    short_K = float(params["short_call_strike"])
    short_prem = float(params["short_call_premium"])  # credit
    long_iv = float(params.get("long_iv", params.get("iv", 0.20)))
    put_iv = float(params.get("put_iv", params.get("iv", 0.20)))
    short_iv = float(params.get("short_iv", params.get("iv", 0.20)))
    # LEAPS retains time at horizon; protective put effectively expires now
    T_long_remaining = long_remaining_days / 365.0
    T_put_remaining = 1e-6
    long_call_vals = _bs_call_val(S_T, long_K, long_iv, T_long_remaining, rf)
    put_vals = _bs_put_val(S_T, put_K, put_iv, T_put_remaining, rf)
    intrinsic_short = np.maximum(0.0, S_T - short_K)
    return (long_call_vals - long_cost) + (put_vals - put_cost) + short_prem - intrinsic_short


# ----------------------------- Validation -----------------------------

def _summarize(arr: np.ndarray) -> Dict[str, float]:
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"mean": float("nan"), "p5": float("nan"), "p50": float("nan"), "p95": float("nan"), "min": float("nan"), "max": float("nan")}
    return {
        "mean": float(np.mean(arr)),
        "p5": float(np.percentile(arr, 5)),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def validate_strategy_mc(strategy: str, params: Dict[str, Any], *, mu: float, rf: float, n: int = 20000, seed: int | None = 1234, tolerances: Dict[str, float] | None = None) -> Dict[str, Any]:
    """
    Validate MC outputs against deterministic quantile-sampled outcomes under the same GBM assumptions.

    tolerances: dict with keys 'mean_bps', 'pctl_bps' as basis-point thresholds relative to collateral.
    Defaults: mean_bps=50 (0.50% of collateral), pctl_bps=100 (1.00% of collateral)
    """
    days = int(params.get("days", 0))
    S0 = float(params.get("S0", 0.0))
    sigma = float(params.get("iv", 0.20))
    if not tolerances:
        tolerances = {"mean_bps": 50.0, "pctl_bps": 100.0}

    # Run the actual MC to get reference outputs
    mc = mc_pnl(strategy, params, n_paths=int(n), mu=float(mu), seed=seed, rf=float(rf))
    pnl_mc = mc.get("pnl_paths")
    collateral = float(mc.get("collateral", 0.0))
    mc_sum = _summarize(pnl_mc)

    # Deterministic samples for the same GBM (conceptual cross-check)
    T = max(days, 0) / 365.0
    S_T = _lognormal_quantile_samples(S0, mu, sigma, T, n)
    if strategy == "PMCC":
        pnl_per_share = _pnl_pmcc_per_share(S_T, params, days, rf)
    elif strategy == "SYNTHETIC_COLLAR":
        pnl_per_share = _pnl_synthetic_collar_per_share(S_T, params, days, rf)
    else:
        raise ValueError("Only PMCC and SYNTHETIC_COLLAR are supported by this validator")
    pnl_qmc = 100.0 * pnl_per_share
    qmc_sum = _summarize(pnl_qmc)

    # Compute deltas vs tolerances (relative to collateral)
    def _ok(delta: float, limit_bps: float) -> bool:
        if not np.isfinite(collateral) or collateral <= 0:
            return abs(delta) < 1e-6
        return abs(delta) <= (limit_bps / 10000.0) * collateral

    checks = []
    # Mean check
    mean_delta = mc_sum["mean"] - qmc_sum["mean"]
    checks.append({"metric": "mean", "mc": mc_sum["mean"], "qmc": qmc_sum["mean"], "delta": mean_delta, "ok": _ok(mean_delta, tolerances["mean_bps"])})
    # Percentiles
    for k in ["p5", "p50", "p95"]:
        d = mc_sum[k] - qmc_sum[k]
        checks.append({"metric": k, "mc": mc_sum[k], "qmc": qmc_sum[k], "delta": d, "ok": _ok(d, tolerances["pctl_bps"])})
    # Bounds
    bounds_ok = (mc_sum["min"] >= (qmc_sum["min"] - 0.02 * collateral)) and (mc_sum["max"] <= (qmc_sum["max"] + 0.02 * collateral))

    # Capital consistency
    cap_ps = float(mc.get("capital_per_share", float("nan")))
    capital_ok = (cap_ps == cap_ps) and (cap_ps > 0.0) and (abs(100.0 * cap_ps - collateral) < 1e-3)

    overall_ok = all(x["ok"] for x in checks) and bounds_ok and capital_ok

    # Build a human-readable position snapshot for transparency
    def _position_snapshot() -> Dict[str, Any]:
        snap: Dict[str, Any] = {
            "Strategy": strategy,
            "Ticker": params.get("Ticker"),
            "S0": S0,
            "Days": days,
            "BaseIV": sigma,
            "mu": mu,
            "rf": rf,
        }
        if strategy == "PMCC":
            snap.update({
                "LongCall": {
                    "Strike": params.get("long_call_strike"),
                    "Cost": params.get("long_call_cost"),
                    "LongDaysTotal": params.get("long_days_total"),
                    "IV": params.get("long_iv", sigma),
                    "LongExp": params.get("LongExp"),
                },
                "ShortCall": {
                    "Strike": params.get("short_call_strike"),
                    "Premium": params.get("short_call_premium"),
                    "IV": params.get("short_iv", sigma),
                    "Exp": params.get("Exp"),
                },
            })
            sel_id = f"{params.get('Ticker')}|{params.get('Exp')}|L={params.get('long_call_strike')}|S={params.get('short_call_strike')}"
        elif strategy == "SYNTHETIC_COLLAR":
            snap.update({
                "LongCall": {
                    "Strike": params.get("long_call_strike"),
                    "Cost": params.get("long_call_cost"),
                    "LongDaysTotal": params.get("long_days_total"),
                    "IV": params.get("long_iv", sigma),
                    "LongExp": params.get("LongExp"),
                },
                "Put": {
                    "Strike": params.get("put_strike"),
                    "Cost": params.get("put_cost"),
                    "IV": params.get("put_iv", sigma),
                },
                "ShortCall": {
                    "Strike": params.get("short_call_strike"),
                    "Premium": params.get("short_call_premium"),
                    "IV": params.get("short_iv", sigma),
                    "Exp": params.get("Exp"),
                },
            })
            sel_id = f"{params.get('Ticker')}|{params.get('Exp')}|L={params.get('long_call_strike')}|P={params.get('put_strike')}|S={params.get('short_call_strike')}"
        else:
            sel_id = None
        snap["SelectionId"] = sel_id
        return snap

    report = {
        "strategy": strategy,
        "n": int(n),
        "days": int(days),
        "mu": float(mu),
        "iv_paths": float(sigma),
        "collateral": float(collateral),
        "params_snapshot": dict(params),
        "position": _position_snapshot(),
        "mc_summary": mc_sum,
        "qmc_summary": qmc_sum,
        "checks": checks,
        "bounds_ok": bool(bounds_ok),
        "capital_ok": bool(capital_ok),
        "overall_ok": bool(overall_ok),
    }
    return report


def report_dataframe(report: Dict[str, Any]) -> pd.DataFrame:
    rows = []
    for c in report.get("checks", []):
        rows.append({
            "Metric": c["metric"],
            "MC": c["mc"],
            "QMC": c["qmc"],
            "Delta": c["delta"],
            "OK": c["ok"],
        })
    rows.append({"Metric": "Bounds", "MC": "min/max", "QMC": "min/max", "Delta": "±2% collateral", "OK": report.get("bounds_ok")})
    rows.append({"Metric": "Capital", "MC": "capital_per_share", "QMC": "collateral/100", "Delta": "match", "OK": report.get("capital_ok")})
    rows.append({"Metric": "OVERALL", "MC": "—", "QMC": "—", "Delta": "—", "OK": report.get("overall_ok")})
    return pd.DataFrame(rows)
