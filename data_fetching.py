"""
Data Fetching Utilities

This module contains data fetching functions that are used by both strategy_lab.py
and strategy_analysis.py. By placing them here, we avoid circular import issues.

These functions include Streamlit caching decorators and provider fallback logic.
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

# Import provider globals (these will be set by strategy_lab.py)
# Using late binding to avoid import order issues
def _get_providers():
    """Get provider globals from strategy_lab if available"""
    try:
        from strategy_lab import POLY, USE_POLYGON, PROVIDER_SYSTEM_AVAILABLE, PROVIDER
        return POLY, USE_POLYGON, PROVIDER_SYSTEM_AVAILABLE, PROVIDER
    except ImportError:
        return None, False, False, "yfinance"

@st.cache_data(ttl=60, show_spinner=False)
def fetch_price(ticker):
    """Fetch current stock price with provider fallback"""
    POLY, USE_POLYGON, PROVIDER_SYSTEM_AVAILABLE, PROVIDER = _get_providers()
    
    if USE_POLYGON and POLY:
        try:
            return float(POLY.last_price(ticker))
        except Exception:
            pass
    
    # Fallback to yfinance
    stock = yf.Ticker(ticker)
    hist = stock.history(period="1d")
    if hist.empty:
        raise ValueError(f"No price data for {ticker}")
    return float(hist['Close'].iloc[-1])

@st.cache_data(ttl=300, show_spinner=False)
def fetch_expirations(ticker):
    """Fetch available option expirations with provider fallback"""
    POLY, USE_POLYGON, PROVIDER_SYSTEM_AVAILABLE, PROVIDER = _get_providers()
    
    if USE_POLYGON and POLY:
        try:
            return POLY.expirations(ticker)
        except Exception:
            pass
    
    # Fallback to yfinance
    stock = yf.Ticker(ticker)
    exps = stock.options
    if not exps:
        raise ValueError(f"No expirations for {ticker}")
    return list(exps)

@st.cache_data(ttl=120, show_spinner=False)
def fetch_chain(ticker, expiration):
    """Fetch option chain with provider fallback"""
    POLY, USE_POLYGON, PROVIDER_SYSTEM_AVAILABLE, PROVIDER = _get_providers()
    
    if USE_POLYGON and POLY:
        try:
            return POLY.chain_snapshot_df(ticker, expiration)
        except Exception:
            pass
    
    # Fallback to yfinance
    stock = yf.Ticker(ticker)
    try:
        chain = stock.option_chain(expiration)
    except Exception as e:
        raise ValueError(f"No chain for {ticker} {expiration}: {e}")
    
    calls_df = chain.calls.copy()
    calls_df['type'] = 'call'
    puts_df = chain.puts.copy()
    puts_df['type'] = 'put'
    df = pd.concat([calls_df, puts_df], ignore_index=True)
    
    # Standardize column names
    rename_map = {
        'contractSymbol': 'symbol',
        'lastTradeDate': 'lastTradeDate',
        'strike': 'strike',
        'lastPrice': 'last',
        'bid': 'bid',
        'ask': 'ask',
        'change': 'change',
        'percentChange': 'percentChange',
        'volume': 'volume',
        'openInterest': 'oi',
        'impliedVolatility': 'iv'
    }
    df = df.rename(columns=rename_map)
    df['expiration'] = expiration
    
    return df

def _safe_float(x, default=float("nan")):
    """Safely convert value to float with default"""
    try:
        return float(x)
    except Exception:
        return default


def _get_num_from_row(r: pd.Series, keys: list, default=float("nan")) -> float:
    """Try multiple key names from a row/Series and return numeric value."""
    for k in keys:
        try:
            if hasattr(r, "get"):
                v = r.get(k, None)
            else:
                v = r[k]
        except Exception:
            v = None
        
        # Skip None values - try the next key
        if v is None:
            continue
        
        f = _safe_float(v, default)
        if f == f:  # not NaN
            return f
    
    return default

def _safe_int(x, default=0):
    """Safely convert value to int with default"""
    try:
        f = float(x)
        if f != f:  # NaN
            return default
        return int(f)
    except Exception:
        return default

def effective_credit(bid, ask, last=None, alpha=0.25):
    """
    Realistic credit for SELL orders: bid + alpha*(ask-bid).
    alpha ~ 0.25 for liquid names; falls back to 0.95*last if no quotes.
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
    """
    b = _safe_float(bid)
    a = _safe_float(ask)
    l = _safe_float(last, 0.0)
    if b == b and a == a and b > 0 and a > 0 and a >= b:
        return a - alpha * (a - b)
    if l == l and l > 0:
        return 1.05 * l
    return float("nan")

def estimate_next_ex_div(stock):
    """
    Heuristic: use last 2-4 historical dividend dates to estimate next ex-div date & amount.
    Returns (date|None, amount_per_share).
    """
    try:
        divs = stock.dividends
        if divs is None or divs.empty:
            return None, 0.0
        divs = divs.sort_index()
        dates = list(divs.index[-4:])  # last up to 4
        amts = list(divs.iloc[-4:])
        if not dates:
            return None, 0.0
        if len(dates) >= 2:
            gaps = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
            avg_gap = int(np.median(gaps)) if gaps else 90
        else:
            avg_gap = 90  # quarterly-ish default
        next_date = dates[-1] + pd.Timedelta(days=avg_gap)
        amt = float(amts[-1])
        return next_date.date(), amt
    except Exception:
        return None, 0.0

def check_expiration_risk(expiration_str: str, strategy: str = "CSP", open_interest: int = 0, 
                          bid_ask_spread_pct: float = 0.0, ticker=None) -> dict:
    """
    Analyze expiration date risk and return comprehensive safety assessment.
    
    Args:
        expiration_str: Expiration date string (e.g., "2025-11-15")
        strategy: Strategy type ("CSP", "CC", "Collar", "Bull Put Spread", "Bear Call Spread", "Iron Condor")
        open_interest: Open interest for the option(s)
        bid_ask_spread_pct: Bid-ask spread as percentage of mid price
        ticker: Legacy parameter for backwards compatibility (unused)
    
    Returns:
        dict with keys:
            - is_standard: bool (True if standard Friday expiration)
            - expiration_type: str ("Monthly 3rd Friday", "Weekly Friday", "Non-Standard")
            - day_of_week: str (e.g., "Friday", "Monday")
            - risk_level: str ("LOW", "MEDIUM", "HIGH", "EXTREME")
            - action: str ("ALLOW", "WARN", "BLOCK")
            - warning_message: str (human-readable warning)
            - risk_factors: list[str] (specific concerns)
            - is_monthly: bool (for backwards compatibility)
            - elevated_risk: bool (for backwards compatibility)
    """
    try:
        exp_date = datetime.strptime(expiration_str, "%Y-%m-%d").date()
    except Exception:
        return {
            "is_standard": False,
            "expiration_type": "Invalid Date",
            "day_of_week": "Unknown",
            "risk_level": "EXTREME",
            "action": "BLOCK",
            "warning_message": "⛔ INVALID EXPIRATION DATE",
            "risk_factors": ["Cannot parse expiration date"],
            "is_monthly": False,
            "elevated_risk": True
        }
    
    day_of_week = exp_date.strftime("%A")
    weekday_num = exp_date.weekday()  # 0=Monday, 4=Friday
    
    # Check if it's a Friday
    is_friday = (weekday_num == 4)
    
    # Check if it's the 3rd Friday (monthly standard)
    first_day = exp_date.replace(day=1)
    first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
    third_friday = first_friday + timedelta(days=14)
    is_third_friday = (exp_date == third_friday)
    
    risk_factors = []
    
    # Determine expiration type
    if is_third_friday:
        expiration_type = "Monthly (3rd Friday)"
        is_standard = True
        base_risk = "LOW"
    elif is_friday:
        expiration_type = "Weekly (Friday)"
        is_standard = True
        base_risk = "MEDIUM"
        risk_factors.append("Weekly option - verify liquidity")
    else:
        expiration_type = f"Non-Standard ({day_of_week})"
        is_standard = False
        base_risk = "HIGH"
        risk_factors.append(f"⚠️ Expires on {day_of_week} (not Friday)")
    
    # Liquidity assessment
    if open_interest > 0:
        if open_interest < 100:
            risk_factors.append(f"Very low OI ({open_interest}) - poor liquidity")
        elif open_interest < 500:
            risk_factors.append(f"Low OI ({open_interest}) - limited liquidity")
        elif open_interest < 1000 and not is_standard:
            risk_factors.append(f"Moderate OI ({open_interest}) but non-standard expiration")
    
    if bid_ask_spread_pct > 0:
        if bid_ask_spread_pct > 10.0:
            risk_factors.append(f"Extremely wide spread ({bid_ask_spread_pct:.1f}%)")
        elif bid_ask_spread_pct > 5.0:
            risk_factors.append(f"Wide spread ({bid_ask_spread_pct:.1f}%)")
        elif bid_ask_spread_pct > 3.0 and not is_standard:
            risk_factors.append(f"Spread {bid_ask_spread_pct:.1f}% on non-standard expiration")
    
    # Strategy-specific risk assessment
    strategy_risk_map = {
        "CSP": {
            "standard": "LOW",
            "weekly": "MEDIUM",
            "nonstandard": "HIGH",
            "multi_leg": False
        },
        "CC": {
            "standard": "MEDIUM",
            "weekly": "HIGH",
            "nonstandard": "HIGH",
            "multi_leg": False
        },
        "Collar": {
            "standard": "MEDIUM",
            "weekly": "HIGH",
            "nonstandard": "HIGH",
            "multi_leg": True
        },
        "Bull Put Spread": {
            "standard": "MEDIUM",
            "weekly": "HIGH",
            "nonstandard": "EXTREME",
            "multi_leg": True
        },
        "Bear Call Spread": {
            "standard": "MEDIUM",
            "weekly": "HIGH",
            "nonstandard": "EXTREME",
            "multi_leg": True
        },
        "Iron Condor": {
            "standard": "MEDIUM",
            "weekly": "HIGH",
            "nonstandard": "EXTREME",
            "multi_leg": True
        }
    }
    
    strat_info = strategy_risk_map.get(strategy, {
        "standard": "MEDIUM",
        "weekly": "HIGH",
        "nonstandard": "EXTREME",
        "multi_leg": False
    })
    
    # Determine final risk level
    if is_third_friday:
        risk_level = strat_info["standard"]
    elif is_friday:
        risk_level = strat_info["weekly"]
    else:
        risk_level = strat_info["nonstandard"]
    
    # Escalate risk based on liquidity
    if open_interest > 0 and open_interest < 100:
        if risk_level == "LOW":
            risk_level = "MEDIUM"
        elif risk_level == "MEDIUM":
            risk_level = "HIGH"
    
    if bid_ask_spread_pct > 5.0 and risk_level in ["LOW", "MEDIUM"]:
        risk_level = "HIGH"
    
    # Multi-leg strategies get extra scrutiny
    if strat_info["multi_leg"] and not is_standard:
        if open_interest < 1000:
            risk_factors.append("⛔ Multi-leg strategy requires OI > 1000 for non-standard expirations")
            risk_level = "EXTREME"
    
    # Determine action
    if risk_level == "EXTREME":
        action = "BLOCK"
        warning_icon = "⛔"
    elif risk_level == "HIGH":
        if strat_info["multi_leg"]:
            action = "BLOCK"  # Block high-risk multi-leg
            warning_icon = "⛔"
        else:
            action = "WARN"
            warning_icon = "⚠️"
    elif risk_level == "MEDIUM":
        action = "WARN"
        warning_icon = "⚠️"
    else:
        action = "ALLOW"
        warning_icon = "✅"
    
    # Build warning message
    if action == "BLOCK":
        warning_message = f"⛔ BLOCKED: {expiration_type} - {strategy}"
    elif action == "WARN":
        warning_message = f"⚠️ WARNING: {expiration_type} - {strategy}"
    else:
        warning_message = f"✅ Standard: {expiration_type}"
    
    return {
        "is_standard": is_standard,
        "expiration_type": expiration_type,
        "day_of_week": day_of_week,
        "risk_level": risk_level,
        "action": action,
        "warning_message": warning_message,
        "risk_factors": risk_factors,
        # Backwards compatibility fields
        "is_monthly": is_third_friday,
        "elevated_risk": (risk_level in ["HIGH", "EXTREME"])
    }
