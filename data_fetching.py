"""
Data Fetching Utilities

This module contains data fetching functions that are used by both strategy_lab.py
and strategy_analysis.py. By placing them here, we avoid circular import issues.

These functions include Streamlit caching decorators and provider fallback logic.
"""

import streamlit as st
import pandas as pd
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

def estimate_next_ex_div(stock, current_price):
    """Estimate next ex-dividend date"""
    try:
        divs = stock.dividends
        if divs.empty:
            return None, 0.0
        
        last_div_date = divs.index[-1]
        last_div_amount = divs.iloc[-1]
        
        # Estimate next date (typically quarterly)
        next_date = last_div_date + timedelta(days=90)
        
        return next_date, last_div_amount
    except Exception:
        return None, 0.0

def check_expiration_risk(expiration_str, ticker=None):
    """Check if expiration date has elevated risk"""
    try:
        exp_date = datetime.strptime(expiration_str, "%Y-%m-%d")
        # Check if it's a monthly expiration (3rd Friday)
        # More checks can be added here
        return {
            "expiration_type": "monthly" if exp_date.day >= 15 and exp_date.day <= 21 else "weekly",
            "is_monthly": exp_date.day >= 15 and exp_date.day <= 21,
            "elevated_risk": False  # Can add more sophisticated risk checks
        }
    except Exception:
        return {
            "expiration_type": "unknown",
            "is_monthly": False,
            "elevated_risk": False
        }
