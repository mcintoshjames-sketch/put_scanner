"""
Utility Functions Module

This module contains helper functions used across strategy_lab.py, strategy_analysis.py,
and other modules. These are pure utility functions with no Streamlit dependencies.
"""

import pandas as pd
import numpy as np


def _safe_float(x, default=float("nan")):
    """Safely convert value to float with a default fallback"""
    try:
        return float(x)
    except Exception:
        return default


def _safe_int(x, default=0):
    """Safely convert value to int with a default fallback"""
    try:
        f = float(x)
        if f != f:  # NaN
            return default
        return int(f)
    except Exception:
        return default


def _get_num_from_row(r: pd.Series, keys: list, default=float("nan")) -> float:
    """
    Try each key in 'keys' until one works, returning float(val).
    If none succeed, return default.
    """
    for k in keys:
        try:
            if hasattr(r, "get"):
                v = r.get(k, None)
            else:
                v = r[k]
        except Exception:
            v = None
        f = _safe_float(v, default)
        if f == f:  # not NaN
            return f
    return default


def _mid_price(bid, ask, last):
    """
    Compute mid-price from bid/ask, with last price fallback.
    Returns float("nan") if unavailable.
    """
    b = _safe_float(bid)
    a = _safe_float(ask)
    l = _safe_float(last)
    if b == b and a == a and b > 0 and a > 0:
        return (b + a) / 2.0
    if l == l and l > 0:
        return l
    return float("nan")


def _fmt_usd(x, nd=2):
    """Format a number as USD with specified decimal places"""
    try:
        return f"${float(x):,.{nd}f}"
    except Exception:
        return str(x)


def _iv_decimal(row, default=0.20):
    """
    Extract IV from row and convert from percentage to decimal.
    Returns default if unavailable or invalid.
    """
    iv = row.get("IV", float("nan"))
    try:
        ivf = float(iv) / 100.0
        return ivf if ivf == ivf and ivf > 0 else default
    except Exception:
        return default


def _series_get(row, key, default=float("nan")):
    """
    Safely get a value from a pandas Series/dict.
    Returns default if key missing or value is NaN.
    """
    try:
        v = row.get(key, default)
        return v if v == v else default
    except Exception:
        return default


def _dynamic_alpha_from_spread(bid, ask, default=0.25):
    """
    Compute a liquidity-aware alpha based on bid-ask spread percentage.
    Tighter spreads => alpha closer to 0.5 (near mid), wider spreads => alpha near 0.05 (near bid).

    Returns an alpha in [0.05, 0.5]. Falls back to `default` if inputs are invalid.
    """
    b = _safe_float(bid)
    a = _safe_float(ask)
    if b == b and a == a and b > 0 and a > 0 and a <= a and a >= b:
        mid = (a + b) / 2.0
        if mid > 0:
            spread_pct = ((a - b) / mid) * 100.0
            # Continuous mapping: 0.5 at 0% spread, ~0.30 at 5%, ~0.10 at 10%, floored at 0.05
            alpha = 0.5 - 0.04 * float(spread_pct)
            if alpha < 0.05:
                alpha = 0.05
            if alpha > 0.5:
                alpha = 0.5
            return alpha
    return default


def _apply_aggressiveness(alpha: float, aggressiveness: str | None,
                          min_alpha: float = 0.05, max_alpha: float = 0.55) -> float:
    """Adjust alpha by aggressiveness preset and clamp."""
    if not isinstance(aggressiveness, str):
        return max(min_alpha, min(max_alpha, float(alpha)))
    preset = aggressiveness.strip().lower()
    adj = 0.0
    if preset.startswith("conserv"):
        adj = -0.05
    elif preset.startswith("assert") or preset.startswith("aggres"):
        adj = 0.10
    return max(min_alpha, min(max_alpha, float(alpha) + adj))


def _dynamic_alpha(bid, ask, oi: int | None = None, volume: int | None = None,
                   dte: int | None = None, aggressiveness: str | None = None,
                   base_default: float = 0.25) -> float:
    """
    Dynamic alpha based on spread, with overlays from OI/volume/DTE and aggressiveness.
    """
    # Base from spread only
    alpha = _dynamic_alpha_from_spread(bid, ask, default=base_default)

    # OI/Volume overlays
    try:
        oi_val = int(oi) if oi is not None else 0
    except Exception:
        oi_val = 0
    try:
        vol_val = int(volume) if volume is not None else 0
    except Exception:
        vol_val = 0

    if oi_val >= 2000 or vol_val >= 1000:
        alpha += 0.05
    elif oi_val >= 500 or vol_val >= 250:
        alpha += 0.02

    # DTE nuance: near-term tends to fill closer to mid
    try:
        if dte is not None and float(dte) <= 7:
            alpha += 0.03
    except Exception:
        pass

    # Aggressiveness preset
    alpha = _apply_aggressiveness(alpha, aggressiveness)
    return alpha


def effective_credit(bid, ask, last=None, alpha=None, *, oi: int | None = None,
                     volume: int | None = None, dte: int | None = None,
                     aggressiveness: str | None = None):
    """
    Realistic credit for SELL orders: bid + alpha*(ask-bid).
    By default, alpha is determined dynamically from the spread (liquidity-aware).
    Falls back to 0.95*last if no quotes.
    
    Args:
        bid: Bid price
        ask: Ask price
        last: Last traded price (optional)
        alpha: Fill improvement factor (0.0-1.0). If None, choose dynamically based on spread.
    
    Returns:
        Expected credit per contract
    """
    b = _safe_float(bid)
    a = _safe_float(ask)
    l = _safe_float(last, 0.0)
    if b == b and a == a and b > 0 and a > 0 and a >= b:
        if alpha is None:
            use_alpha = _dynamic_alpha(b, a, oi=oi, volume=volume, dte=dte, aggressiveness=aggressiveness)
        else:
            use_alpha = _apply_aggressiveness(float(alpha), aggressiveness)
        price = b + use_alpha * (a - b)
        # clamp within [bid, ask]
        if price < b:
            price = b
        if price > a:
            price = a
        return price
    if l == l and l > 0:
        return 0.95 * l
    return float("nan")


def effective_debit(bid, ask, last=None, alpha=None, *, oi: int | None = None,
                    volume: int | None = None, dte: int | None = None,
                    aggressiveness: str | None = None):
    """
    Realistic debit for BUY orders: ask - alpha*(ask-bid).
    By default, alpha is determined dynamically from the spread (liquidity-aware).
    Falls back to 1.05*last if no quotes.
    
    Args:
        bid: Bid price
        ask: Ask price
        last: Last traded price (optional)
        alpha: Fill improvement factor (0.0-1.0). If None, choose dynamically based on spread.
    
    Returns:
        Expected debit per contract
    """
    b = _safe_float(bid)
    a = _safe_float(ask)
    l = _safe_float(last, 0.0)
    if b == b and a == a and b > 0 and a > 0 and a >= b:
        if alpha is None:
            use_alpha = _dynamic_alpha(b, a, oi=oi, volume=volume, dte=dte, aggressiveness=aggressiveness)
        else:
            use_alpha = _apply_aggressiveness(float(alpha), aggressiveness)
        price = a - use_alpha * (a - b)
        if price < b:
            price = b
        if price > a:
            price = a
        return price
    if l == l and l > 0:
        return 1.05 * l
    return float("nan")
