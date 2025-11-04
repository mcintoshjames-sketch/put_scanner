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


def effective_credit(bid, ask, last=None, alpha=0.25):
    """
    Realistic credit for SELL orders: bid + alpha*(ask-bid).
    alpha ~ 0.25 for liquid names; falls back to 0.95*last if no quotes.
    
    Args:
        bid: Bid price
        ask: Ask price
        last: Last traded price (optional)
        alpha: Fill improvement factor (0.0-1.0, default 0.25)
    
    Returns:
        Expected credit per contract
    """
    b = _safe_float(bid)
    a = _safe_float(ask)
    l = _safe_float(last, 0.0)
    if b == b and a == a and b > 0 and a > 0 and a >= b:
        return b + alpha * (a - b)
    if l == l and l > 0:
        return 0.95 * l
    return float("nan")


def effective_debit(bid, ask, last=None, alpha=0.25):
    """
    Realistic debit for BUY orders: ask - alpha*(ask-bid).
    Falls back to 1.05*last if no quotes.
    
    Args:
        bid: Bid price
        ask: Ask price
        last: Last traded price (optional)
        alpha: Fill improvement factor (0.0-1.0, default 0.25)
    
    Returns:
        Expected debit per contract
    """
    b = _safe_float(bid)
    a = _safe_float(ask)
    l = _safe_float(last, 0.0)
    if b == b and a == a and b > 0 and a > 0 and a >= b:
        return a - alpha * (a - b)
    if l == l and l > 0:
        return 1.05 * l
    return float("nan")
