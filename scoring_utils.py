"""Unified cross-strategy scoring utilities.

Goals:
 - Provide a single, conceptually consistent score across heterogeneous option strategies
 - Strongly penalize negative Monte Carlo (MC) expected P&L
 - Reward higher risk‑adjusted return while considering tail risk, liquidity, and cushion

Score Components (weights sum to 1.0):
  1. Expected Return (0.45): Annualized expected ROI (MC preferred, deterministic fallback) capped at 150%.
     Negative MC expected P&L -> return component forced to 0 and global penalty applied.
  2. Tail Risk (p5) (0.25): Measures downside robustness: p5 / capital_at_risk truncated to [-1, 0]; mapped to [0,1].
  3. Liquidity (0.15): Blend of tight bid/ask (Spread%) and turnover (Volume/OI).
  4. Cushion / Distance (0.10): Standard deviation or structural cushion (varies by strategy) normalized 0..3σ.
  5. Efficiency / Edge (0.05): Ratio of (credit or expected P&L) to capital_at_risk, capped at 1.

Penalty Policy:
  - MC_ExpectedPnL < 0 ⇒ multiplicative penalty_factor = 0.05 (95% reduction) applied AFTER component sum.
  - Missing data handled gracefully (neutral 0.5 where appropriate, or 0 if truly absent risk mitigation).

The resulting UnifiedScore is in [0,1].
"""

from __future__ import annotations

from typing import Iterable, Optional
import pandas as pd
import numpy as np

NEG_MC_PENALTY_FACTOR = 0.05  # 95% reduction for negative expected value


def _clip01(x):
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0


def _norm(x: float, lo: float, hi: float) -> float:
    try:
        if x != x or hi <= lo:
            return 0.0
        return _clip01((x - lo) / (hi - lo))
    except Exception:
        return 0.0


def _first_present(row, candidates: Iterable[str]):
    for c in candidates:
        if c in row and pd.notna(row[c]):
            return row[c]
    return np.nan


def _capital_at_risk(row) -> float:
    # Preference order: MaxLoss, Capital, Collateral, Width*100, NetDebit*100, Strike*100
    for col in ["MaxLoss", "Capital", "Collateral"]:
        if col in row and pd.notna(row[col]) and float(row[col]) > 0:
            return float(row[col])
    if all(k in row for k in ("Width",)) and pd.notna(row.get("Width")):
        return float(row["Width"]) * 100.0
    if all(k in row for k in ("NetDebit",)) and pd.notna(row.get("NetDebit")):
        return float(row["NetDebit"]) * 100.0
    if all(k in row for k in ("Strike",)) and pd.notna(row.get("Strike")):
        return float(row["Strike"]) * 100.0
    return float("nan")


def _cushion_value(row) -> float:
    # Try multiple possible cushion / distance measures
    return _first_present(row, [
        "CushionSigma", "PutCushionσ", "CallCushionσ", "PutCushionSigma", "FloorSigma", "CapSigma"
    ])


def _spread_pct(row) -> float:
    return _first_present(row, ["Spread%", "CallSpread%", "PutSpread%"])


def _volume(row) -> float:
    return _first_present(row, ["Volume", "CallVolume", "PutVolume"])


def _open_interest(row) -> float:
    return _first_present(row, ["OI", "CallOI", "PutOI"])


def compute_unified_score(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)

    # Pre-extract frequently used columns where vectorization helps
    mc_exp = df.get("MC_ExpectedPnL")
    mc_roi_pct = df.get("MC_ROI_ann%")
    det_roi_pct = df.get("ROI%_ann")
    p5 = df.get("MC_PnL_p5")  # may be absent

    # Capital at risk per row (vectorized via apply for hetero schema)
    capital_series = df.apply(_capital_at_risk, axis=1)

    # Expected ROI (decimal) – MC preferred
    exp_roi_dec = pd.Series(np.where(pd.notna(mc_roi_pct), mc_roi_pct, det_roi_pct), index=df.index) / 100.0
    exp_roi_dec = exp_roi_dec.fillna(0.0)
    exp_roi_comp = exp_roi_dec.clip(lower=0.0, upper=1.5) / 1.5  # map 0..150% -> 0..1

    # Tail risk component: p5 relative to capital
    if p5 is not None:
        tail_ratio = p5 / capital_series.replace(0, np.nan)
        # Clamp to [-1, 0]; -1 -> 0 score, 0 -> 1 score
        tail_ratio = tail_ratio.clip(lower=-1.0, upper=0.0)
        tail_comp = 1.0 + tail_ratio  # since tail_ratio in [-1,0]
        tail_comp = tail_comp.fillna(0.5)  # neutral when missing
    else:
        tail_comp = pd.Series(0.5, index=df.index)

    # Liquidity: spread and turnover
    spread_vals = df.apply(_spread_pct, axis=1)
    spread_comp = 1.0 - (spread_vals.clip(lower=0.0, upper=20.0) / 20.0)

    vol_vals = df.apply(_volume, axis=1)
    oi_vals = df.apply(_open_interest, axis=1)
    with np.errstate(divide='ignore', invalid='ignore'):
        vol_oi_ratio = vol_vals / oi_vals
    vol_oi_comp = (vol_oi_ratio / 0.5).clip(lower=0.0, upper=1.0)
    liq_comp = 0.7 * spread_comp.fillna(0.0) + 0.3 * vol_oi_comp.fillna(0.0)

    # Cushion component (0..3σ)
    cushion_vals = df.apply(_cushion_value, axis=1)
    cushion_comp = (cushion_vals / 3.0).clip(lower=0.0, upper=1.0)
    cushion_comp = cushion_comp.fillna(0.0)

    # Efficiency: credit or expected pnl over capital
    credit = df.get("NetCredit")
    if credit is not None:
        eff_raw = (credit * 100.0) / capital_series.replace(0, np.nan)
    else:
        # fallback to expected P&L
        eff_raw = mc_exp / capital_series.replace(0, np.nan) if mc_exp is not None else pd.Series(0.0, index=df.index)
    efficiency_comp = eff_raw.clip(lower=0.0, upper=1.0).fillna(0.0)

    # Base weighted score
    base = (
        0.45 * exp_roi_comp +
        0.25 * tail_comp +
        0.15 * liq_comp +
        0.10 * cushion_comp +
        0.05 * efficiency_comp
    )

    # Negative MC expected P&L penalty
    if mc_exp is not None:
        neg_mask = (mc_exp < 0) & mc_exp.notna()
        base = base.mask(neg_mask, base * NEG_MC_PENALTY_FACTOR)

    return base.clip(lower=0.0, upper=1.0).round(6)


def apply_unified_score(df: pd.DataFrame, *, score_col: str = "UnifiedScore") -> pd.DataFrame:
    if df is None or df.empty:
        return df
    try:
        df[score_col] = compute_unified_score(df)
    except Exception:
        # Fail gracefully without interrupting UI
        df[score_col] = np.nan
    return df


__all__ = [
    "compute_unified_score",
    "apply_unified_score",
    "NEG_MC_PENALTY_FACTOR",
]
