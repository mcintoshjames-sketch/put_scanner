# strategy_lab.py
# Multi-strategy options income lab:
# - Cash-Secured Puts (CSP)
# - Covered Calls (CC)
# - Collars (Stock + Short Call + Long Put)
#
# Features:
# - Scan & rank opportunities with tunable filters
# - Compare projected annualized ROI across strategies
# - Monte Carlo risk on the selected contract/structure
# - At-a-glance summary (returns at percentiles, annualized)
# - Best-practice playbook (exit, liquidity, tenor)
#
# Notes:
# - Data: Supports multiple providers (YFinance, Schwab, Polygon)
# - This is educational tooling, not advice. Verify prior to trading.

import math
from datetime import datetime, timedelta, timezone
import os
import threading
import json

# Import provider system
try:
    from providers import get_provider, OptionsProvider
    from config import PROVIDER
    PROVIDER_SYSTEM_AVAILABLE = True
except Exception:
    PROVIDER_SYSTEM_AVAILABLE = False
    get_provider = None
    PROVIDER = "yfinance"

# Legacy Polygon support (will be replaced by provider system)
try:
    from providers.polygon import PolygonClient, PolygonError  # type: ignore
except Exception:  # providers client optional
    PolygonClient = None  # type: ignore

    class PolygonError(Exception):
        pass


import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

# Thread-safe diagnostics counters (accessible from worker threads)
_diagnostics_lock = threading.Lock()
_diagnostics_counters = {
    "price": {"yfinance": 0, "schwab": 0, "polygon": 0},
    "expirations": {"yfinance": 0, "schwab": 0, "polygon": 0},
    "chain": {"yfinance": 0, "schwab": 0, "polygon": 0},
}
_last_provider_used = {
    "price": None,
    "expirations": None,
    "chain": None
}


# ----------------------------- Utils -----------------------------

# Initialize the options provider
PROVIDER_INSTANCE = None
USE_PROVIDER_SYSTEM = False

try:
    if PROVIDER_SYSTEM_AVAILABLE and get_provider is not None:
        PROVIDER_INSTANCE = get_provider()
        USE_PROVIDER_SYSTEM = True
        # Show provider status in sidebar (will be called later in UI section)
except Exception as e:
    # Provider system not available, fall back to legacy methods
    USE_PROVIDER_SYSTEM = False

# Legacy Polygon support (for backward compatibility)
try:
    from app import POLY, USE_POLYGON  # type: ignore
except Exception:  # pragma: no cover - optional
    POLY = None
    USE_POLYGON = False
    # Try to initialize Polygon client directly if running standalone
    if not USE_PROVIDER_SYSTEM:
        try:
            from providers.polygon import PolygonClient

            # Try Streamlit secrets first, then fall back to environment variable
            polygon_key = ""
            if hasattr(st, "secrets") and "POLYGON_API_KEY" in st.secrets:
                polygon_key = st.secrets["POLYGON_API_KEY"]
            else:
                polygon_key = os.getenv("POLYGON_API_KEY", "")

            if polygon_key:
                POLY = PolygonClient(api_key=polygon_key)
                USE_POLYGON = True
        except Exception:
            pass  # Stay with Yahoo-only fallback

# Diagnostics: Track which provider was used for each fetch_* call


def _init_data_calls():
    """Initialize session state from thread-safe counters."""
    # Sync thread-safe counters to session state for display
    with _diagnostics_lock:
        if "data_calls" not in st.session_state:
            st.session_state["data_calls"] = {
                "price": dict(_diagnostics_counters["price"]),
                "expirations": dict(_diagnostics_counters["expirations"]),
                "chain": dict(_diagnostics_counters["chain"]),
            }
        else:
            # Update session state with current thread-safe counter values
            for call_type in ["price", "expirations", "chain"]:
                for provider in ["yfinance", "schwab", "polygon"]:
                    st.session_state["data_calls"][call_type][provider] = _diagnostics_counters[call_type][provider]
        
        if "last_provider" not in st.session_state:
            st.session_state["last_provider"] = dict(_last_provider_used)
        else:
            st.session_state["last_provider"].update(_last_provider_used)
    
    if "last_attempt" not in st.session_state:
        st.session_state["last_attempt"] = {
            "price": None, "expirations": None, "chain": None
        }
    if "data_errors" not in st.session_state:
        st.session_state["data_errors"] = {
            "price": {"yfinance": None, "schwab": None, "polygon": None},
            "expirations": {"yfinance": None, "schwab": None, "polygon": None},
            "chain": {"yfinance": None, "schwab": None, "polygon": None},
        }


def _record_data_source(name: str, provider: str) -> None:
    """Thread-safe recording of data source usage."""
    try:
        with _diagnostics_lock:
            _diagnostics_counters[name][provider] += 1
            _last_provider_used[name] = provider
    except Exception as e:
        # Debug: print error to help diagnose issues
        print(f"Error recording data source {name}/{provider}: {e}")


def _provider_override() -> str:
    # 'auto' (default) tries Polygon first; 'yahoo' forces Yahoo fallback
    return str(st.session_state.get("provider_override", "auto")).lower()


def _polygon_ready() -> bool:
    try:
        return bool(USE_POLYGON) and (POLY is not None)
    except Exception:
        return False


@st.cache_data(ttl=30, show_spinner=False)
def fetch_price(symbol: str) -> float:
    """Get last price from configured provider (Schwab/Polygon/YFinance)."""
    try:
        # Use new provider system if available
        if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE:
            try:
                val = float(PROVIDER_INSTANCE.last_price(symbol))
                _record_data_source("price", PROVIDER)
                return val
            except Exception as e:
                st.warning(f"Provider {PROVIDER} failed for {symbol}: {e}")
                # Fall through to legacy methods
        
        # Legacy: Try provider override
        ov = _provider_override()
        if ov == "polygon" and not _polygon_ready():
            return float("nan")
        if ov != "yahoo" and _polygon_ready():
            try:
                val = float(POLY.last_price(symbol))
                _record_data_source("price", "polygon")
                return val
            except Exception as e:
                if ov == "polygon":
                    return float("nan")
                # else fall through to yahoo
    except Exception as e:
        pass
    
    # Fallback to yfinance
    t = yf.Ticker(symbol)
    try:
        val = float(t.history(period="1d")["Close"].iloc[-1])
        _record_data_source("price", "yfinance")
        return val
    except Exception as e:
        return float("nan")


@st.cache_data(ttl=600, show_spinner=False)
def fetch_expirations(symbol: str) -> list:
    """List option expirations using configured provider."""
    try:
        # Use new provider system if available
        if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE:
            try:
                exps = PROVIDER_INSTANCE.expirations(symbol)
                _record_data_source("expirations", PROVIDER)
                return list(exps or [])
            except Exception as e:
                st.warning(f"Provider {PROVIDER} failed for {symbol} expirations: {e}")
                # Fall through to legacy methods
        
        # Legacy: Try provider override
        ov = _provider_override()
        if ov == "polygon" and not _polygon_ready():
            return []
        if ov != "yahoo" and _polygon_ready():
            try:
                exps = POLY.expirations(symbol)
                _record_data_source("expirations", "polygon")
                return list(exps or [])
            except Exception as e:
                if ov == "polygon":
                    return []
                # else fall through
    except Exception as e:
        pass
    
    # Fallback to yfinance
    try:
        vals = list(yf.Ticker(symbol).options or [])
        _record_data_source("expirations", "yfinance")
        return vals
    except Exception as e:
        return []


@st.cache_data(ttl=30, show_spinner=False)
def fetch_chain(symbol: str, expiration: str) -> pd.DataFrame:
    """Return a unified calls+puts DataFrame with a 'type' column ("call"/"put")."""
    try:
        # Use new provider system if available
        if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE:
            try:
                df = PROVIDER_INSTANCE.chain_snapshot_df(symbol, expiration)
                # For put scanner, we might only get puts - need to fetch both for strategy lab
                # Try to get full chain if the provider supports it
                if "type" in df.columns:
                    df = df.copy()
                    df["type"] = df["type"].astype(str).str.lower()
                _record_data_source("chain", PROVIDER)
                return df
            except Exception as e:
                st.warning(f"Provider {PROVIDER} failed for {symbol} chain: {e}")
                # Fall through to legacy methods
        
        # Legacy: Try provider override
        ov = _provider_override()
        if ov == "polygon" and not _polygon_ready():
            return pd.DataFrame()
        if ov != "yahoo" and _polygon_ready():
            try:
                df = POLY.chain_snapshot_df(symbol, expiration)
                # Ensure 'type' is lower-case if present
                if "type" in df.columns:
                    df = df.copy()
                    df["type"] = df["type"].astype(str).str.lower()
                _record_data_source("chain", "polygon")
                return df
            except Exception as e:
                if ov == "polygon":
                    return pd.DataFrame()
                # else fall through
    except Exception as e:
        pass
    
    # yfinance fallback
    t = yf.Ticker(symbol)
    try:
        ch = t.option_chain(expiration)
    except Exception:
        return pd.DataFrame()
    dfs = []
    for typ, df in (("call", ch.calls), ("put", ch.puts)):
        if df is None or df.empty:
            continue
        tmp = df.copy()
        tmp["type"] = typ
        dfs.append(tmp)
    out = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    _record_data_source("chain", "yfinance")
    return out

# --- Uncached probe helpers (for Diagnostics) ---


def fetch_price_uncached(symbol: str) -> float:
    try:
        # Use new provider system if available
        if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE:
            st.session_state["last_attempt"]["price"] = PROVIDER
            try:
                val = float(PROVIDER_INSTANCE.last_price(symbol))
                _record_data_source("price", PROVIDER)
                st.session_state["data_errors"]["price"][PROVIDER] = None
                return val
            except Exception as e:
                st.session_state["data_errors"]["price"][PROVIDER] = str(e)
                # Fall through to legacy
        
        # Legacy: Try provider override
        ov = _provider_override()
        if ov == "polygon" and not _polygon_ready():
            st.session_state["last_attempt"]["price"] = "polygon"
            st.session_state["data_errors"]["price"][
                "polygon"] = "Polygon not configured (USE_POLYGON/POLY missing)"
            return float("nan")
        if ov != "yahoo" and _polygon_ready():
            st.session_state["last_attempt"]["price"] = "polygon"
            try:
                val = float(POLY.last_price(symbol))
                _record_data_source("price", "polygon")
                st.session_state["data_errors"]["price"]["polygon"] = None
                return val
            except Exception as e:
                st.session_state["data_errors"]["price"]["polygon"] = str(e)
                if ov == "polygon":
                    return float("nan")
                # else fall through
    except Exception as e:
        st.session_state["data_errors"]["price"]["polygon"] = str(e)
    
    # Fallback to yfinance
    try:
        st.session_state["last_attempt"]["price"] = "yfinance"
        t = yf.Ticker(symbol)
        val = float(t.history(period="1d")["Close"].iloc[-1])
        _record_data_source("price", "yfinance")
        st.session_state["data_errors"]["price"]["yfinance"] = None
        return val
    except Exception as e:
        st.session_state["data_errors"]["price"]["yfinance"] = str(e)
        return float("nan")


def fetch_expirations_uncached(symbol: str) -> list:
    try:
        # Use new provider system if available
        if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE:
            st.session_state["last_attempt"]["expirations"] = PROVIDER
            try:
                exps = PROVIDER_INSTANCE.expirations(symbol)
                _record_data_source("expirations", PROVIDER)
                st.session_state["data_errors"]["expirations"][PROVIDER] = None
                return list(exps or [])
            except Exception as e:
                st.session_state["data_errors"]["expirations"][PROVIDER] = str(e)
                # Fall through to legacy
        
        # Legacy: Try provider override
        ov = _provider_override()
        if ov == "polygon" and not _polygon_ready():
            st.session_state["last_attempt"]["expirations"] = "polygon"
            st.session_state["data_errors"]["expirations"][
                "polygon"] = "Polygon not configured (USE_POLYGON/POLY missing)"
            return []
        if ov != "yahoo" and _polygon_ready():
            st.session_state["last_attempt"]["expirations"] = "polygon"
            try:
                exps = POLY.expirations(symbol)
                _record_data_source("expirations", "polygon")
                st.session_state["data_errors"]["expirations"]["polygon"] = None
                return list(exps or [])
            except Exception as e:
                st.session_state["data_errors"]["expirations"]["polygon"] = str(
                    e)
                if ov == "polygon":
                    return []
                # else fall through
    except Exception as e:
        st.session_state["data_errors"]["expirations"]["polygon"] = str(e)
    
    # Fallback to yfinance
    try:
        st.session_state["last_attempt"]["expirations"] = "yfinance"
        vals = list(yf.Ticker(symbol).options or [])
        _record_data_source("expirations", "yfinance")
        st.session_state["data_errors"]["expirations"]["yfinance"] = None
        return vals
    except Exception as e:
        st.session_state["data_errors"]["expirations"]["yfinance"] = str(e)
        return []


def fetch_chain_uncached(symbol: str, expiration: str) -> pd.DataFrame:
    try:
        # Use new provider system if available
        if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE:
            st.session_state["last_attempt"]["chain"] = PROVIDER
            try:
                df = PROVIDER_INSTANCE.chain_snapshot_df(symbol, expiration)
                if "type" in df.columns:
                    df = df.copy()
                    df["type"] = df["type"].astype(str).str.lower()
                _record_data_source("chain", PROVIDER)
                st.session_state["data_errors"]["chain"][PROVIDER] = None
                return df
            except Exception as e:
                st.session_state["data_errors"]["chain"][PROVIDER] = str(e)
                # Fall through to legacy
        
        # Legacy: Try provider override
        ov = _provider_override()
        if ov == "polygon" and not _polygon_ready():
            st.session_state["last_attempt"]["chain"] = "polygon"
            st.session_state["data_errors"]["chain"][
                "polygon"] = "Polygon not configured (USE_POLYGON/POLY missing)"
            return pd.DataFrame()
        if ov != "yahoo" and _polygon_ready():
            st.session_state["last_attempt"]["chain"] = "polygon"
            try:
                df = POLY.chain_snapshot_df(symbol, expiration)
                if "type" in df.columns:
                    df = df.copy()
                    df["type"] = df["type"].astype(str).str.lower()
                _record_data_source("chain", "polygon")
                st.session_state["data_errors"]["chain"]["polygon"] = None
                return df
            except Exception as e:
                st.session_state["data_errors"]["chain"]["polygon"] = str(e)
                if ov == "polygon":
                    return pd.DataFrame()
                # else fall through
    except Exception as e:
        st.session_state["data_errors"]["chain"]["polygon"] = str(e)
    try:
        st.session_state["last_attempt"]["chain"] = "yfinance"
        t = yf.Ticker(symbol)
        ch = t.option_chain(expiration)
        dfs = []
        for typ, df in (("call", ch.calls), ("put", ch.puts)):
            if df is None or df.empty:
                continue
            tmp = df.copy()
            tmp["type"] = typ
            dfs.append(tmp)
        out = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        _record_data_source("chain", "yfinance")
        st.session_state["data_errors"]["chain"]["yfinance"] = None
        return out
    except Exception as e:
        st.session_state["data_errors"]["chain"]["yfinance"] = str(e)
        return pd.DataFrame()


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


def _safe_float(x, default=float("nan")):
    try:
        return float(x)
    except Exception:
        return default


def _safe_int(x, default=0):
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


def _mid_price(bid, ask, last):
    bid = _safe_float(bid)
    ask = _safe_float(ask)
    last = _safe_float(last, 0.0)
    if bid == bid and ask == ask and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    if last == last and last > 0:
        return last
    return float("nan")


def _norm_cdf(x):
    try:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    except Exception:
        return float("nan")


def _bs_d1_d2(S, K, r, sigma, T, q=0.0):
    # Merton w/ continuous dividend yield q
    if S <= 0 or K <= 0 or sigma <= 0 or T <= 0:
        return float("nan"), float("nan")
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / \
            (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return d1, d2
    except Exception:
        return float("nan"), float("nan")
# --- Black–Scholes prices with continuous dividend yield q ---


def bs_call_price(S, K, r, q, sigma, T):
    # Guard tiny or zero time
    T = max(T, 1e-6)
    d1, d2 = _bs_d1_d2(S, K, r, sigma, T, q)
    if not (d1 == d1 and d2 == d2):  # NaN guard
        return max(0.0, S - K)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    return S * disc_q * _norm_cdf(d1) - K * disc_r * _norm_cdf(d2)


def bs_put_price(S, K, r, q, sigma, T):
    T = max(T, 1e-6)
    d1, d2 = _bs_d1_d2(S, K, r, sigma, T, q)
    if not (d1 == d1 and d2 == d2):
        return max(0.0, K - S)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    return K * disc_r * _norm_cdf(-d2) - S * disc_q * _norm_cdf(-d1)


def call_delta(S, K, r, sigma, T, q=0.0):
    d1, _ = _bs_d1_d2(S, K, r, sigma, T, q)
    if d1 != d1:  # NaN check
        return float("nan")
    disc_q = math.exp(-q * T)
    return disc_q * _norm_cdf(d1)


def put_delta(S, K, r, sigma, T, q=0.0):
    cd = call_delta(S, K, r, sigma, T, q)
    if cd == cd:
        return cd - 1.0
    return float("nan")


def option_gamma(S, K, r, sigma, T, q=0.0):
    """
    Gamma: rate of change of delta with respect to underlying price.
    Same for calls and puts.
    """
    if sigma <= 0 or T <= 0 or S <= 0:
        return float("nan")
    d1, _ = _bs_d1_d2(S, K, r, sigma, T, q)
    if d1 != d1:
        return float("nan")
    disc_q = math.exp(-q * T)
    phi_d1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * d1 * d1)
    return (disc_q * phi_d1) / (S * sigma * math.sqrt(T))


def put_theta(S, K, r, sigma, T, q=0.0):
    """
    Theta for a put option: daily time decay (negative value = decay helps seller).
    Returns value in dollars per day (divided by 365).
    """
    if sigma <= 0 or T <= 0 or S <= 0:
        return float("nan")
    d1, d2 = _bs_d1_d2(S, K, r, sigma, T, q)
    if d1 != d1 or d2 != d2:
        return float("nan")

    phi_d1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * d1 * d1)
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)

    term1 = -(S * disc_q * phi_d1 * sigma) / (2.0 * math.sqrt(T))
    term2 = r * K * disc_r * _norm_cdf(-d2)
    term3 = -q * S * disc_q * _norm_cdf(-d1)

    # Theta in dollars per year, convert to per day
    theta_annual = term1 + term2 + term3
    return theta_annual / 365.0


def call_theta(S, K, r, sigma, T, q=0.0):
    """
    Theta for a call option: daily time decay (negative value = decay helps seller).
    Returns value in dollars per day (divided by 365).
    """
    if sigma <= 0 or T <= 0 or S <= 0:
        return float("nan")
    d1, d2 = _bs_d1_d2(S, K, r, sigma, T, q)
    if d1 != d1 or d2 != d2:
        return float("nan")

    phi_d1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * d1 * d1)
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)

    term1 = -(S * disc_q * phi_d1 * sigma) / (2.0 * math.sqrt(T))
    term2 = -r * K * disc_r * _norm_cdf(d2)
    term3 = q * S * disc_q * _norm_cdf(d1)

    # Theta in dollars per year, convert to per day
    theta_annual = term1 + term2 + term3
    return theta_annual / 365.0


def expected_move(S, iv, T):
    """
    Expected 1-standard-deviation move (68% confidence interval).
    Returns: S * σ * sqrt(T)
    """
    if iv != iv or T <= 0:
        return float("nan")
    return S * iv * math.sqrt(T)


def compute_spread_pct(bid, ask, mid):
    bid = _safe_float(bid)
    ask = _safe_float(ask)
    mid = _safe_float(mid)
    if bid == bid and ask == ask and bid > 0 and ask > 0 and mid > 0:
        return ((ask - bid) / mid) * 100.0
    return None  # None => unknown; don't auto-reject


def trailing_dividend_info(ticker_obj, S):
    """
    Returns (div_per_share_annual, trailing_yield_decimal).
    """
    try:
        divs = ticker_obj.dividends
        if divs is None or divs.empty:
            return 0.0, 0.0
        cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=365)
        last_year = divs[divs.index >= cutoff]
        per_share = float(last_year.sum()) if not last_year.empty else 0.0
        yld = per_share / S if S > 0 else 0.0
        return per_share, yld
    except Exception:
        return 0.0, 0.0


def get_earnings_date(stock: yf.Ticker, use_alpha_vantage=False):
    """
    Try multiple methods to get earnings date from yfinance.
    Optionally falls back to Alpha Vantage if Yahoo Finance has no data.
    
    Args:
        stock: yfinance Ticker object
        use_alpha_vantage: If True, fall back to Alpha Vantage when Yahoo fails.
                          Default False to preserve API quota during screening.
    
    Returns:
        Earnings date or None if unavailable.
    """
    yahoo_date = None
    
    try:
        # Method 1: Try the calendar attribute
        cal = stock.calendar
        if cal is not None and not cal.empty:
            if "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"]
                if hasattr(ed, "__iter__") and len(ed) > 0:
                    yahoo_date = pd.to_datetime(ed[0]).date()
                else:
                    yahoo_date = pd.to_datetime(ed).date()
            elif "Earnings Date" in cal.columns:
                ed = cal["Earnings Date"].iloc[0]
                if hasattr(ed, "__iter__") and len(ed) > 0:
                    yahoo_date = pd.to_datetime(ed[0]).date()
                else:
                    yahoo_date = pd.to_datetime(ed).date()
            
            if yahoo_date:
                return yahoo_date
    except Exception:
        pass

    # Method 2: Try earnings_dates property (if available)
    try:
        if hasattr(stock, 'earnings_dates'):
            earnings_dates = stock.earnings_dates
            if earnings_dates is not None and not earnings_dates.empty:
                # Get the first future date
                future_dates = earnings_dates[earnings_dates.index > pd.Timestamp.now()]
                if not future_dates.empty:
                    yahoo_date = future_dates.index[0].date()
                    return yahoo_date
    except Exception:
        pass
    
    # Method 3: Fallback to Alpha Vantage if Yahoo has no data (ONLY if enabled)
    # This is disabled by default to preserve API quota during screening
    if use_alpha_vantage:
        try:
            from providers.alpha_vantage import get_earnings_with_fallback
            
            # This will only call Alpha Vantage if yahoo_date is None
            symbol = stock.ticker if hasattr(stock, 'ticker') else None
            if symbol:
                fallback_date = get_earnings_with_fallback(symbol, yahoo_date)
                if fallback_date:
                    return fallback_date
        except Exception:
            pass

    return None


# -------------------------- Monte Carlo --------------------------

def gbm_terminal_prices(S0, mu, sigma, T_years, n_paths, rng=None):
    rng = rng or np.random.default_rng()
    Z = rng.standard_normal(n_paths)
    drift = (mu - 0.5 * sigma**2) * T_years
    vol_term = sigma * np.sqrt(T_years)
    return S0 * np.exp(drift + vol_term * Z)


def mc_pnl(strategy, params, n_paths=20000, mu=0.0, seed=None, rf=0.0):
    """
    Monte Carlo P&L simulation for options strategies.

    For CSP: adds continuous risk-free carry on collateral.
    For CC/Collar: includes stock price movement and dividends (no additional rf on stock capital).

    Returns dict with pnl_paths, roi_ann_paths, and summary statistics.
    """
    S0 = float(params["S0"])
    days = int(params["days"])
    T = days / 365.0
    # Ensure non-degenerate volatility for stochastic paths
    sigma = float(params.get("iv", 0.20))
    if not (sigma == sigma) or sigma <= 0.0:
        sigma = 0.20
    rng = np.random.default_rng(seed)
    S_T = gbm_terminal_prices(S0, mu, sigma, T, n_paths, rng)

    div_ps_annual = float(params.get("div_ps_annual", 0.0))
    div_ps_period = div_ps_annual * (days / 365.0)

    if strategy == "CSP":
        Kp = float(params["Kp"])
        Pp = float(params["put_premium"])
        pnl_per_share = Pp - np.maximum(0.0, Kp - S_T)
        # Add continuous risk-free interest on collateral
        pnl_per_share += Kp * (np.exp(rf * T) - 1.0)
        capital_per_share = Kp

    elif strategy == "CC":
        Kc = float(params["Kc"])
        Pc = float(params["call_premium"])
        pnl_per_share = (S_T - S0) + Pc - \
            np.maximum(0.0, S_T - Kc) + div_ps_period
        capital_per_share = S0

    elif strategy == "COLLAR":
        Kc = float(params["Kc"])
        Pc = float(params["call_premium"])
        Kp = float(params["Kp"])
        Pp = float(params["put_premium"])
        pnl_per_share = ((S_T - S0)
                         + Pc - np.maximum(0.0, S_T - Kc)
                         - Pp + np.maximum(0.0, Kp - S_T)
                         + div_ps_period)
        capital_per_share = S0
    
    elif strategy == "IRON_CONDOR":
        # Iron Condor: Sell OTM put spread + Sell OTM call spread
        # Profit if stock stays between short strikes
        Kps = float(params["put_short_strike"])   # Short put strike
        Kpl = float(params["put_long_strike"])    # Long put strike (lower)
        Kcs = float(params["call_short_strike"])  # Short call strike
        Kcl = float(params["call_long_strike"])   # Long call strike (higher)
        net_credit = float(params["net_credit"])
        
        # P&L calculation for Iron Condor
        # Start with net credit received
        pnl_per_share = np.full_like(S_T, net_credit)
        
        # Subtract put spread loss if price < short put strike
        # Max loss on put side: (Kps - Kpl) when S_T <= Kpl
        put_spread_loss = np.maximum(0.0, Kps - S_T) - np.maximum(0.0, Kpl - S_T)
        pnl_per_share -= put_spread_loss
        
        # Subtract call spread loss if price > short call strike  
        # Max loss on call side: (Kcl - Kcs) when S_T >= Kcl
        call_spread_loss = np.maximum(0.0, S_T - Kcs) - np.maximum(0.0, S_T - Kcl)
        pnl_per_share -= call_spread_loss
        
        # Capital = max loss = (width of wider spread - net credit)
        put_spread_width = Kps - Kpl
        call_spread_width = Kcl - Kcs
        max_spread_width = max(put_spread_width, call_spread_width)
        capital_per_share = max_spread_width - net_credit
    
    else:
        raise ValueError("Unknown strategy for MC")

    pnl_contract = 100.0 * pnl_per_share
    capital_contract = 100.0 * capital_per_share

    with np.errstate(invalid="ignore", divide="ignore"):
        roi_cycle = pnl_contract / capital_contract
        roi_ann = (1.0 + roi_cycle) ** (365.0 / days) - 1.0

    out = {
        "S_T": S_T,
        "pnl_paths": pnl_contract,
        "roi_ann_paths": roi_ann,
        "collateral": capital_contract,
        "capital_per_share": capital_per_share,
        "days": days,
        "paths": int(n_paths),
    }
    for label, arr in [("pnl", pnl_contract), ("roi_ann", roi_ann)]:
        arr_clean = arr[np.isfinite(arr)]
        if arr_clean.size == 0:
            out[f"{label}_expected"] = float("nan")
            out[f"{label}_std"] = float("nan")
            out[f"{label}_p5"] = float("nan")
            out[f"{label}_p50"] = float("nan")
            out[f"{label}_p95"] = float("nan")
            out[f"{label}_min"] = float("nan")
        else:
            out[f"{label}_expected"] = float(np.mean(arr_clean))
            out[f"{label}_std"] = float(np.std(arr_clean))
            out[f"{label}_p5"] = float(np.percentile(arr_clean, 5))
            out[f"{label}_p50"] = float(np.percentile(arr_clean, 50))
            out[f"{label}_p95"] = float(np.percentile(arr_clean, 95))
            out[f"{label}_min"] = float(np.min(arr_clean))
    
    # Calculate Sharpe ratio
    pnl_clean = pnl_contract[np.isfinite(pnl_contract)]
    if pnl_clean.size > 0 and np.std(pnl_clean) > 0:
        # Assuming risk-free rate ~= 0 for simplicity (or use mu)
        sharpe = np.mean(pnl_clean) / np.std(pnl_clean) * np.sqrt(365.0 / days)
        out["sharpe"] = float(sharpe)
    else:
        out["sharpe"] = float("nan")
    
    return out


# -------------------------- Analyzers ----------------------------


def analyze_csp(ticker, *, min_days=0, days_limit, min_otm, min_oi, max_spread, min_roi, min_cushion,
                min_poew, earn_window, risk_free, per_contract_cap=None, bill_yield=0.0):
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame(), {}

    expirations = fetch_expirations(ticker)

    earn_date = get_earnings_date(stock)
    # dividend yield for q
    div_ps_annual, div_y = trailing_dividend_info(stock, S)
    q = div_y  # continuous dividend yield proxy

    rows = []
    counters = {
        "expirations": 0,
        "rows": 0,
        "premium_pass": 0,
        "otm_pass": 0,
        "roi_pass": 0,
        "oi_pass": 0,
        "spread_pass": 0,
        "cushion_pass": 0,
        "poew_pass": 0,
        "cap_pass": 0,
        "final": 0,
    }
    for exp in expirations:
        try:
            ed = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        D = (ed - datetime.now(timezone.utc).date()).days
        if D < int(min_days) or D > int(days_limit):
            continue
        if earn_date is not None and abs((earn_date - ed).days) <= int(earn_window):
            continue

        chain_all = fetch_chain(ticker, exp)
        if chain_all is None or chain_all.empty:
            continue
        counters["expirations"] += 1
        if "type" in chain_all.columns:
            chain = chain_all[chain_all["type"].str.lower() == "put"].copy()
        else:
            chain = chain_all.copy()
        if chain.empty:
            continue

        counters["rows"] += len(chain)
        T = D / 365.0
        for _, r in chain.iterrows():
            K = _get_num_from_row(
                r, ["strike", "Strike", "k", "K"], float("nan"))
            if not (K == K and K > 0):
                continue

            bid = _get_num_from_row(r, ["bid", "Bid", "b"])  # may be NaN
            ask = _get_num_from_row(r, ["ask", "Ask", "a"])  # may be NaN
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"])
            prem = effective_credit(bid, ask, last)
            if prem != prem or prem <= 0:
                continue
            counters["premium_pass"] += 1

            iv_raw = _get_num_from_row(
                r, ["impliedVolatility", "iv", "IV"], float("nan"))
            # Normalize IV to decimal if provided in vol points
            if iv_raw == iv_raw and iv_raw > 3.0:
                iv_dec = iv_raw / 100.0
            else:
                iv_dec = iv_raw
            # Treat zero/negative IV as missing and use default for calculations
            iv_for_calc = iv_dec if (
                iv_dec == iv_dec and iv_dec > 0.0) else 0.20
            d1, d2 = _bs_d1_d2(S, K, risk_free, iv_for_calc, T, q)
            poew = _norm_cdf(d2) if d2 == d2 else float("nan")

            otm_pct = (S - K) / S * 100.0
            if otm_pct < float(min_otm):
                continue
            counters["otm_pass"] += 1

            # ROI on collateral (K) and on net cash (K - prem)
            roi_ann_collat = (prem / K) * (365.0 / D)
            roi_ann_net = (prem / max(K - prem, 1e-9)) * \
                (365.0 / D) if K > prem else float("nan")
            if roi_ann_collat != roi_ann_collat or roi_ann_collat < float(min_roi):
                continue
            counters["roi_pass"] += 1

            oi = _safe_int(_get_num_from_row(
                r, ["openInterest", "oi", "open_interest"], 0), 0)
            if min_oi and oi < int(min_oi):
                continue
            counters["oi_pass"] += 1

            mid = prem
            spread_pct = compute_spread_pct(bid, ask, mid)
            if (spread_pct is not None) and (spread_pct > float(max_spread)):
                continue
            counters["spread_pass"] += 1

            exp_mv = expected_move(S, iv_for_calc, T)
            cushion_sigma = ((S - K) / exp_mv) if (exp_mv ==
                                                   exp_mv and exp_mv > 0) else float("nan")
            if cushion_sigma == cushion_sigma and cushion_sigma < float(min_cushion):
                continue
            counters["cushion_pass"] += 1

            if poew == poew and poew < float(min_poew):
                continue
            counters["poew_pass"] += 1

            collateral = K * 100.0
            if per_contract_cap is not None and collateral > float(per_contract_cap):
                continue
            counters["cap_pass"] += 1

            excess_vs_bills = roi_ann_collat - float(bill_yield)

            # Calculate Greeks for theta/gamma ratio
            put_theta_val = put_theta(S, K, risk_free, iv_for_calc, T, q)
            gamma_val = option_gamma(S, K, risk_free, iv_for_calc, T, q)

            # Theta/Gamma ratio (higher is better for sellers)
            # Theta is negative for long, but we're short, so use absolute value
            # Multiply by 100 to get per-contract values
            theta_gamma_ratio = float("nan")
            if gamma_val == gamma_val and gamma_val > 0 and put_theta_val == put_theta_val:
                theta_per_contract = abs(put_theta_val) * 100.0  # per contract
                gamma_per_contract = gamma_val * 100.0
                theta_gamma_ratio = theta_per_contract / gamma_per_contract

            # Score: yield + cushion + liquidity + theta/gamma
            liq_score = max(0.0, 1.0 - min((spread_pct or 20.0), 20.0) / 20.0)
            # Improved theta/gamma scoring: optimal range 0.8-3.0 for short-term income
            if theta_gamma_ratio == theta_gamma_ratio:
                if theta_gamma_ratio < 0.5:
                    tg_score = 0.0  # Too risky (gamma explosion)
                elif theta_gamma_ratio < 0.8:
                    tg_score = theta_gamma_ratio / 0.8  # Ramp up to 1.0
                elif theta_gamma_ratio <= 3.0:
                    tg_score = 1.0  # Sweet spot for 10-45 DTE
                elif theta_gamma_ratio <= 5.0:
                    # Linear decline 3.0->5.0: score 1.0->0.5
                    tg_score = 1.0 - (theta_gamma_ratio - 3.0) * 0.25
                elif theta_gamma_ratio <= 10.0:
                    # Linear decline 5.0->10.0: score 0.5->0.2
                    tg_score = 0.5 - (theta_gamma_ratio - 5.0) * 0.06
                else:
                    # Ultra-conservative, almost no premium
                    tg_score = 0.1
            else:
                tg_score = 0.0

            # Reweighted for short-term (10-45 DTE) income focus
            score = (0.35 * roi_ann_collat +
                     0.15 * (min(cushion_sigma, 3.0) / 3.0 if cushion_sigma == cushion_sigma else 0.0) +
                     0.30 * tg_score +
                     0.20 * liq_score)

            # Calculate days to earnings if available
            days_to_earnings = None
            if earn_date is not None:
                # Days from TODAY to earnings (negative = earnings passed)
                days_to_earnings = (
                    earn_date - datetime.now(timezone.utc).date()).days

            rows.append({
                "Strategy": "CSP",
                "Ticker": ticker, "Price": round(S, 2), "Exp": exp, "Days": D,
                "Strike": float(K), "Premium": round(prem, 2),
                "OTM%": round(otm_pct, 2),

                # ROI fields (all as % where appropriate)
                # primary
                "ROI%_ann": round(roi_ann_collat * 100.0, 2),
                "ROI%_ann_net": round(roi_ann_net * 100.0, 2) if roi_ann_net == roi_ann_net else float("nan"),

                # Display IV only if positive; else mark as n/a
                "IV": round(iv_dec * 100.0, 2) if (iv_dec == iv_dec and iv_dec > 0.0) else float("nan"),
                "POEW": round(poew, 3) if poew == poew else float("nan"),
                "CushionSigma": round(cushion_sigma, 2) if cushion_sigma == cushion_sigma else float("nan"),
                "Theta/Gamma": round(theta_gamma_ratio, 2) if theta_gamma_ratio == theta_gamma_ratio else float("nan"),
                "Spread%": round(spread_pct, 2) if spread_pct is not None else float("nan"),
                "OI": oi, "Collateral": int(collateral),
                "DaysToEarnings": days_to_earnings,
                "Score": round(score, 6)
            })
            counters["final"] += 1
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Score", "ROI%_ann"], ascending=[
                            False, False]).reset_index(drop=True)
    return df, counters


def analyze_cc(ticker, *, min_days=0, days_limit, min_otm, min_oi, max_spread, min_roi,
               earn_window, risk_free, include_dividends=True, bill_yield=0.0):
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame()
    expirations = fetch_expirations(ticker)
    earn_date = get_earnings_date(stock)

    div_ps_annual, div_y = trailing_dividend_info(stock, S)  # per share annual
    rows = []
    for exp in expirations:
        try:
            ed = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        D = (ed - datetime.now(timezone.utc).date()).days
        if D < int(min_days) or D > int(days_limit):
            continue
        if earn_date is not None and abs((earn_date - ed).days) <= int(earn_window):
            continue

        chain_all = fetch_chain(ticker, exp)
        if chain_all is None or chain_all.empty:
            continue
        if "type" in chain_all.columns:
            chain = chain_all[chain_all["type"].str.lower() == "call"].copy()
        else:
            chain = chain_all.copy()
        if chain.empty:
            continue

        T = D / 365.0
        for _, r in chain.iterrows():
            K = _get_num_from_row(
                r, ["strike", "Strike", "k", "K"], float("nan"))
            if not (K == K and K > 0):
                continue
            bid = _get_num_from_row(r, ["bid", "Bid", "b"])  # may be NaN
            ask = _get_num_from_row(r, ["ask", "Ask", "a"])  # may be NaN
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"])
            prem = effective_credit(bid, ask, last)
            if prem != prem or prem <= 0:
                continue
            iv_raw = _get_num_from_row(
                r, ["impliedVolatility", "iv", "IV"], float("nan"))
            if iv_raw == iv_raw and iv_raw > 3.0:
                iv_dec = iv_raw / 100.0
            else:
                iv_dec = iv_raw
            iv_for_calc = iv_dec if (
                iv_dec == iv_dec and iv_dec > 0.0) else 0.20
            d1, d2 = _bs_d1_d2(S, K, risk_free, iv_for_calc, T, div_y)
            # Prob(call expires worthless)
            poec = _norm_cdf(-d2) if d2 == d2 else float("nan")
            otm_pct = (K - S) / S * 100.0
            if otm_pct < float(min_otm):
                continue

            # Annualized ROI on stock capital (S)
            roi_ann = (prem / S) * (365.0 / D)
            if include_dividends and div_ps_annual > 0:
                roi_ann += (div_ps_annual / S)

            if roi_ann != roi_ann or roi_ann < float(min_roi):
                continue

            oi = _safe_int(_get_num_from_row(
                r, ["openInterest", "oi", "open_interest"], 0), 0)
            if min_oi and oi < int(min_oi):
                continue

            mid = prem
            spread_pct = compute_spread_pct(bid, ask, mid)
            if (spread_pct is not None) and (spread_pct > float(max_spread)):
                continue

            exp_mv = expected_move(S, iv_for_calc, T)
            cushion_sigma = ((K - S) / exp_mv) if (exp_mv ==
                                                   exp_mv and exp_mv > 0) else float("nan")

            # Calculate Greeks for theta/gamma ratio
            call_theta_val = call_theta(S, K, risk_free, iv_for_calc, T, div_y)
            gamma_val = option_gamma(S, K, risk_free, iv_for_calc, T, div_y)

            # Theta/Gamma ratio (higher is better for sellers)
            theta_gamma_ratio = float("nan")
            if gamma_val == gamma_val and gamma_val > 0 and call_theta_val == call_theta_val:
                theta_per_contract = abs(
                    call_theta_val) * 100.0  # per contract
                gamma_per_contract = gamma_val * 100.0
                theta_gamma_ratio = theta_per_contract / gamma_per_contract

            liq_score = max(0.0, 1.0 - min((spread_pct or 20.0), 20.0) / 20.0)
            # Improved theta/gamma scoring: optimal range 0.8-3.0 for short-term income
            if theta_gamma_ratio == theta_gamma_ratio:
                if theta_gamma_ratio < 0.5:
                    tg_score = 0.0  # Too risky (gamma explosion)
                elif theta_gamma_ratio < 0.8:
                    tg_score = theta_gamma_ratio / 0.8  # Ramp up to 1.0
                elif theta_gamma_ratio <= 3.0:
                    tg_score = 1.0  # Sweet spot for 10-45 DTE
                elif theta_gamma_ratio <= 5.0:
                    # Linear decline 3.0->5.0: score 1.0->0.5
                    tg_score = 1.0 - (theta_gamma_ratio - 3.0) * 0.25
                elif theta_gamma_ratio <= 10.0:
                    # Linear decline 5.0->10.0: score 0.5->0.2
                    tg_score = 0.5 - (theta_gamma_ratio - 5.0) * 0.06
                else:
                    # Ultra-conservative, almost no premium
                    tg_score = 0.1
            else:
                tg_score = 0.0

            # Reweighted for short-term (10-45 DTE) income focus
            score = (0.35 * roi_ann +
                     0.15 * (min(cushion_sigma, 3.0) / 3.0 if cushion_sigma == cushion_sigma else 0.0) +
                     0.30 * tg_score +
                     0.20 * liq_score)

            # Calculate days to earnings if available
            days_to_earnings = None
            if earn_date is not None:
                days_to_earnings = (
                    earn_date - datetime.now(timezone.utc).date()).days

            rows.append({
                "Strategy": "CC",
                "Ticker": ticker, "Price": round(S, 2), "Exp": exp, "Days": D,
                "Strike": float(K), "Premium": round(prem, 2),
                "OTM%": round(otm_pct, 2), "ROI%_ann": round(roi_ann * 100.0, 2),
                "IV": round(iv_dec * 100.0, 2) if (iv_dec == iv_dec and iv_dec > 0.0) else float("nan"),
                # keep shares prob
                "POEC": round(poec, 3) if poec == poec else float("nan"),
                "CushionSigma": round(cushion_sigma, 2) if cushion_sigma == cushion_sigma else float("nan"),
                "Theta/Gamma": round(theta_gamma_ratio, 2) if theta_gamma_ratio == theta_gamma_ratio else float("nan"),
                "Spread%": round(spread_pct, 2) if spread_pct is not None else float("nan"),
                "OI": oi, "Capital": int(S * 100.0),
                "DivYld%": round(div_y * 100.0, 2),
                "DaysToEarnings": days_to_earnings,
                "Score": round(score, 6),
                "DivAnnualPS": round(div_ps_annual, 4)
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Score", "ROI%_ann"], ascending=[
                            False, False]).reset_index(drop=True)
    return df


def analyze_collar(ticker, *, min_days=0, days_limit, min_oi, max_spread,
                   call_delta_target, put_delta_target, earn_window, risk_free,
                   include_dividends=True, min_net_credit=None, bill_yield=0.0):
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame()

    expirations = fetch_expirations(ticker)
    earn_date = get_earnings_date(stock)
    div_ps_annual, div_y = trailing_dividend_info(stock, S)
    rows = []

    for exp in expirations:
        try:
            ed = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        D = (ed - datetime.now(timezone.utc).date()).days
        if D < int(min_days) or D > int(days_limit):
            continue
        if earn_date is not None and abs((earn_date - ed).days) <= int(earn_window):
            continue

        T = D / 365.0
        chain_all = fetch_chain(ticker, exp)
        if chain_all is None or chain_all.empty:
            continue
        if "type" in chain_all.columns:
            calls = chain_all[chain_all["type"].str.lower() == "call"].copy()
            puts = chain_all[chain_all["type"].str.lower() == "put"].copy()
        else:
            # assume both present in separate calls; not ideal but fallback
            calls = chain_all.copy()
            puts = chain_all.copy()

        pred_ex, next_div = estimate_next_ex_div(stock)
        ex_div_in_window = bool(pred_ex and 0 <= (pred_ex - datetime.now(timezone.utc).date()
                                                  ).days <= D)

        def _add_call_delta(df):
            out = []
            for _, r in df.iterrows():
                K = _get_num_from_row(
                    r, ["strike", "Strike", "k", "K"], float("nan"))
                if not (K == K and K > 0):
                    continue
                iv = _get_num_from_row(
                    r, ["impliedVolatility", "iv", "IV"], 0.20)
                if iv == iv and iv > 3.0:
                    iv = iv / 100.0
                cd = call_delta(S, K, risk_free, iv, T, div_y)
                prem = effective_credit(
                    _get_num_from_row(r, ["bid", "Bid", "b"]),
                    _get_num_from_row(r, ["ask", "Ask", "a"]),
                    _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"]))
                if prem != prem or prem <= 0:
                    continue
                spread_pct = compute_spread_pct(
                    _get_num_from_row(r, ["bid", "Bid", "b"]),
                    _get_num_from_row(r, ["ask", "Ask", "a"]),
                    prem)
                oi = _safe_int(_get_num_from_row(
                    r, ["openInterest", "oi", "open_interest"], 0), 0)
                out.append({"K": K, "prem": prem, "delta": cd,
                           "iv": iv, "spread%": spread_pct, "oi": oi})
            return pd.DataFrame(out)

        def _add_put_delta(df):
            out = []
            for _, r in df.iterrows():
                K = _get_num_from_row(
                    r, ["strike", "Strike", "k", "K"], float("nan"))
                if not (K == K and K > 0):
                    continue
                iv = _get_num_from_row(
                    r, ["impliedVolatility", "iv", "IV"], 0.20)
                if iv == iv and iv > 3.0:
                    iv = iv / 100.0
                pdlt = put_delta(S, K, risk_free, iv, T, div_y)
                prem = effective_debit(
                    _get_num_from_row(r, ["bid", "Bid", "b"]),
                    _get_num_from_row(r, ["ask", "Ask", "a"]),
                    _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"]))
                if prem != prem or prem <= 0:
                    continue
                spread_pct = compute_spread_pct(
                    _get_num_from_row(r, ["bid", "Bid", "b"]),
                    _get_num_from_row(r, ["ask", "Ask", "a"]),
                    prem)
                oi = _safe_int(_get_num_from_row(
                    r, ["openInterest", "oi", "open_interest"], 0), 0)
                out.append({"K": K, "prem": prem, "delta": pdlt,
                           "iv": iv, "spread%": spread_pct, "oi": oi})
            return pd.DataFrame(out)

        cdf = _add_call_delta(calls)
        pdf = _add_put_delta(puts)
        if cdf.empty or pdf.empty:
            continue

        cdf = cdf[(cdf["oi"] >= min_oi) | (min_oi is None)]
        pdf = pdf[(pdf["oi"] >= min_oi) | (min_oi is None)]
        if cdf.empty or pdf.empty:
            continue

        cdf = cdf[cdf["K"] >= S].copy()
        pdf = pdf[pdf["K"] <= S].copy()
        if cdf.empty or pdf.empty:
            continue

        cdf["delta_diff"] = (cdf["delta"] - float(call_delta_target)).abs()
        pdf["delta_diff"] = (pdf["delta"] + float(put_delta_target)).abs()
        c_row = cdf.sort_values("delta_diff").iloc[0]
        p_row = pdf.sort_values("delta_diff").iloc[0]

        if (c_row["spread%"] is not None) and (c_row["spread%"] > max_spread):
            continue
        if (p_row["spread%"] is not None) and (p_row["spread%"] > max_spread):
            continue

        call_prem = float(c_row["prem"])
        put_debit = float(p_row["prem"])
        net_credit = call_prem - put_debit
        if (min_net_credit is not None) and (net_credit < min_net_credit):
            continue

        # Dividend in window with early-assignment haircut (same idea as CC)
        div_in_period = 0.0
        assign_risk = False
        if include_dividends and ex_div_in_window and next_div > 0.0:
            intrinsic = max(0.0, S - float(c_row["K"]))
            extrinsic = max(0.0, call_prem - intrinsic)
            if next_div > extrinsic:
                assign_risk = True
                div_in_period = 0.0
            else:
                div_in_period = next_div

        roi_ann = ((net_credit + div_in_period) / S) * (365.0 / D)
        excess_vs_bills = roi_ann - float(bill_yield)

        iv_mix = float(c_row["iv"]) if c_row["iv"] == c_row["iv"] else 0.20
        exp_mv = expected_move(S, iv_mix, T)
        put_cushion = (S - p_row["K"]) / exp_mv if (exp_mv ==
                                                    exp_mv and exp_mv > 0) else float("nan")
        call_cushion = (c_row["K"] - S) / exp_mv if (exp_mv ==
                                                     exp_mv and exp_mv > 0) else float("nan")

        liq_score = 1.0 - \
            min(((c_row["spread%"] or 20.0) +
                (p_row["spread%"] or 20.0)) / 40.0, 1.0)
        score = 0.45 * roi_ann + 0.25 * \
            max(0.0, put_cushion) / 3.0 + 0.15 * \
            max(0.0, call_cushion) / 3.0 + 0.15 * liq_score

        floor = (p_row["K"] - S) + net_credit
        cap_to_call = (c_row["K"] - S) + net_credit

        rows.append({
            "Strategy": "COLLAR",
            "Ticker": ticker, "Price": round(S, 2), "Exp": exp, "Days": D,
            "CallStrike": float(c_row["K"]), "CallPrem": round(call_prem, 2),
            "PutStrike": float(p_row["K"]), "PutPrem": round(put_debit, 2),
            "NetCredit": round(net_credit, 2),

            "ROI%_ann": round(roi_ann * 100.0, 2),
            "ROI%_excess_bills": round(excess_vs_bills * 100.0, 2),

            "CallΔ": round(float(c_row["delta"]), 3),
            "PutΔ": round(float(p_row["delta"]), 3),
            "CallSpread%": round(float(c_row["spread%"]), 2) if c_row["spread%"] is not None else float("nan"),
            "PutSpread%": round(float(p_row["spread%"]), 2) if p_row["spread%"] is not None else float("nan"),
            "CallOI": _safe_int(c_row["oi"], 0), "PutOI": _safe_int(p_row["oi"], 0),
            "Floor$/sh": round(floor, 2), "Cap$/sh": round(cap_to_call, 2),
            "PutCushionσ": round(put_cushion, 2) if put_cushion == put_cushion else float("nan"),
            "CallCushionσ": round(call_cushion, 2) if call_cushion == call_cushion else float("nan"),
            "DivInWindow": round(div_in_period, 4),
            "AssignRisk": bool(assign_risk),
            "Score": round(score, 6)
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Score", "ROI%_ann"], ascending=[
                            False, False]).reset_index(drop=True)
    return df


def analyze_iron_condor(ticker, *, min_days=1, days_limit, min_oi, max_spread,
                        min_roi, min_cushion, earn_window, risk_free,
                        spread_width_put=5.0, spread_width_call=5.0,
                        target_delta_short=0.16, bill_yield=0.0):
    """
    Scan for Iron Condor opportunities (sell OTM put spread + sell OTM call spread).
    
    Structure:
    - Sell put at strike Kps (short put)
    - Buy put at strike Kpl (long put, Kpl < Kps)
    - Sell call at strike Kcs (short call)
    - Buy call at strike Kcl (long call, Kcl > Kcs)
    
    Returns DataFrame with ranked Iron Condor opportunities.
    """
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame()

    expirations = fetch_expirations(ticker)
    earn_date = get_earnings_date(stock)
    div_ps_annual, div_y = trailing_dividend_info(stock, S)
    
    rows = []
    
    for exp in expirations:
        try:
            ed = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        D = (ed - datetime.now(timezone.utc).date()).days
        if D < int(min_days) or D > int(days_limit):
            continue
        if earn_date is not None and abs((earn_date - ed).days) <= int(earn_window):
            continue

        T = D / 365.0
        chain_all = fetch_chain(ticker, exp)
        if chain_all is None or chain_all.empty:
            continue
        
        if "type" in chain_all.columns:
            calls = chain_all[chain_all["type"].str.lower() == "call"].copy()
            puts = chain_all[chain_all["type"].str.lower() == "put"].copy()
        else:
            calls = chain_all.copy()
            puts = chain_all.copy()
        
        # Find short put (sell) - target delta around -0.16 (84% POEW)
        puts_sell = []
        for _, r in puts.iterrows():
            K = _get_num_from_row(r, ["strike", "Strike", "k", "K"], float("nan"))
            if not (K == K and K > 0 and K < S):  # OTM puts
                continue
            
            iv = _get_num_from_row(r, ["impliedVolatility", "iv", "IV"], 0.20)
            if iv == iv and iv > 3.0:
                iv = iv / 100.0
            
            pd_val = put_delta(S, K, risk_free, iv, T, div_y)
            bid = _get_num_from_row(r, ["bid", "Bid", "b"])
            ask = _get_num_from_row(r, ["ask", "Ask", "a"])
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"])
            prem = effective_credit(bid, ask, last)
            
            if prem != prem or prem <= 0:
                continue
            
            oi = _safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0)
            spread_pct = compute_spread_pct(bid, ask, prem)
            
            puts_sell.append({
                "K": K, "prem": prem, "delta": pd_val, "iv": iv,
                "spread%": spread_pct, "oi": oi, "bid": bid, "ask": ask
            })
        
        # Find short call (sell) - target delta around +0.16 (84% POEW)
        calls_sell = []
        for _, r in calls.iterrows():
            K = _get_num_from_row(r, ["strike", "Strike", "k", "K"], float("nan"))
            if not (K == K and K > 0 and K > S):  # OTM calls
                continue
            
            iv = _get_num_from_row(r, ["impliedVolatility", "iv", "IV"], 0.20)
            if iv == iv and iv > 3.0:
                iv = iv / 100.0
            
            cd_val = call_delta(S, K, risk_free, iv, T, div_y)
            bid = _get_num_from_row(r, ["bid", "Bid", "b"])
            ask = _get_num_from_row(r, ["ask", "Ask", "a"])
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"])
            prem = effective_credit(bid, ask, last)
            
            if prem != prem or prem <= 0:
                continue
            
            oi = _safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0)
            spread_pct = compute_spread_pct(bid, ask, prem)
            
            calls_sell.append({
                "K": K, "prem": prem, "delta": cd_val, "iv": iv,
                "spread%": spread_pct, "oi": oi, "bid": bid, "ask": ask
            })
        
        if not puts_sell or not calls_sell:
            continue
        
        # Find best short put (closest to target delta)
        ps_df = pd.DataFrame(puts_sell)
        ps_df = ps_df[ps_df["oi"] >= min_oi]
        if ps_df.empty:
            continue
        ps_df["delta_diff"] = (ps_df["delta"] + target_delta_short).abs()
        ps_row = ps_df.sort_values("delta_diff").iloc[0]
        
        # Find best short call (closest to target delta)
        cs_df = pd.DataFrame(calls_sell)
        cs_df = cs_df[cs_df["oi"] >= min_oi]
        if cs_df.empty:
            continue
        cs_df["delta_diff"] = (cs_df["delta"] - target_delta_short).abs()
        cs_row = cs_df.sort_values("delta_diff").iloc[0]
        
        # Check spreads
        if (ps_row["spread%"] is not None and ps_row["spread%"] > max_spread):
            continue
        if (cs_row["spread%"] is not None and cs_row["spread%"] > max_spread):
            continue
        
        # Find long put (buy) - fixed width below short put
        Kps = float(ps_row["K"])
        Kpl = Kps - spread_width_put
        
        # Find long call (buy) - fixed width above short call
        Kcs = float(cs_row["K"])
        Kcl = Kcs + spread_width_call
        
        # Get premiums for long legs
        put_long = puts[puts.apply(lambda r: abs(_get_num_from_row(r, ["strike", "Strike", "k", "K"], 0) - Kpl) < 0.5, axis=1)]
        call_long = calls[calls.apply(lambda r: abs(_get_num_from_row(r, ["strike", "Strike", "k", "K"], 0) - Kcl) < 0.5, axis=1)]
        
        if put_long.empty or call_long.empty:
            continue
        
        # Get long put premium (debit)
        pl_row = put_long.iloc[0]
        pl_bid = _get_num_from_row(pl_row, ["bid", "Bid", "b"])
        pl_ask = _get_num_from_row(pl_row, ["ask", "Ask", "a"])
        pl_last = _get_num_from_row(pl_row, ["lastPrice", "last", "mark", "mid"])
        pl_prem = effective_debit(pl_bid, pl_ask, pl_last)
        pl_oi = _safe_int(_get_num_from_row(pl_row, ["openInterest", "oi", "open_interest"], 0), 0)
        
        # Get long call premium (debit)
        cl_row = call_long.iloc[0]
        cl_bid = _get_num_from_row(cl_row, ["bid", "Bid", "b"])
        cl_ask = _get_num_from_row(cl_row, ["ask", "Ask", "a"])
        cl_last = _get_num_from_row(cl_row, ["lastPrice", "last", "mark", "mid"])
        cl_prem = effective_debit(cl_bid, cl_ask, cl_last)
        cl_oi = _safe_int(_get_num_from_row(cl_row, ["openInterest", "oi", "open_interest"], 0), 0)
        
        if pl_prem != pl_prem or pl_prem <= 0 or cl_prem != cl_prem or cl_prem <= 0:
            continue
        
        # Check long legs OI
        if pl_oi < min_oi or cl_oi < min_oi:
            continue
        
        # Calculate net credit
        put_spread_credit = float(ps_row["prem"]) - pl_prem
        call_spread_credit = float(cs_row["prem"]) - cl_prem
        net_credit = put_spread_credit + call_spread_credit
        
        if net_credit <= 0:
            continue
        
        # Calculate max loss (width of widest spread - net credit)
        put_spread_width = Kps - Kpl
        call_spread_width = Kcl - Kcs
        max_spread_width = max(put_spread_width, call_spread_width)
        max_loss = max_spread_width - net_credit
        
        # Capital at risk = max loss
        capital = max_loss * 100.0
        
        # ROI calculations
        roi_cycle = net_credit / max_loss if max_loss > 0 else 0.0
        roi_ann = roi_cycle * (365.0 / D)
        excess_vs_bills = roi_ann - float(bill_yield)
        
        if roi_ann < float(min_roi):
            continue
        
        # Cushion calculations
        iv_avg = (float(ps_row["iv"]) + float(cs_row["iv"])) / 2.0
        exp_mv = expected_move(S, iv_avg, T)
        
        put_cushion = (S - Kps) / exp_mv if exp_mv > 0 else float("nan")
        call_cushion = (Kcs - S) / exp_mv if exp_mv > 0 else float("nan")
        
        if put_cushion == put_cushion and put_cushion < float(min_cushion):
            continue
        if call_cushion == call_cushion and call_cushion < float(min_cushion):
            continue
        
        # Breakeven points
        breakeven_lower = Kps - net_credit
        breakeven_upper = Kcs + net_credit
        
        # Probability of max profit (both spreads expire worthless)
        # This is approximate: POEW_put * POEW_call
        d1_p, d2_p = _bs_d1_d2(S, Kps, risk_free, iv_avg, T, div_y)
        d1_c, d2_c = _bs_d1_d2(S, Kcs, risk_free, iv_avg, T, div_y)
        poew_put = _norm_cdf(d2_p) if d2_p == d2_p else float("nan")
        poew_call = _norm_cdf(-d2_c) if d2_c == d2_c else float("nan")
        prob_max_profit = poew_put * poew_call if (poew_put == poew_put and poew_call == poew_call) else float("nan")
        
        # Scoring: optimize for credit/risk ratio, cushion, and liquidity
        # Iron Condor scoring emphasizes:
        # - High ROI (40%): credit / max_loss ratio
        # - Balanced wings (30%): equal cushion on both sides
        # - Low probability of touching (20%): min(put_cushion, call_cushion)
        # - Liquidity (10%): avg spread across 4 legs
        
        avg_spread = (ps_row["spread%"] or 20.0 + cs_row["spread%"] or 20.0) / 2.0
        liq_score = max(0.0, 1.0 - avg_spread / 20.0)
        
        min_cushion_val = min(put_cushion, call_cushion) if (put_cushion == put_cushion and call_cushion == call_cushion) else 0.0
        cushion_score = min(min_cushion_val / 3.0, 1.0)  # normalize to 3 sigma
        
        # Balance score: penalize if one wing much farther than other
        if put_cushion == put_cushion and call_cushion == call_cushion:
            balance_ratio = min(put_cushion, call_cushion) / max(put_cushion, call_cushion, 1e-9)
            balance_score = balance_ratio  # 1.0 = perfect balance, <1.0 = imbalanced
        else:
            balance_score = 0.0
        
        # NOTE: roi_ann is already a large value (e.g., 7.77 for 777% ROI)
        # Other strategies use fractional values (0.10 for 10% ROI) in scoring
        # To make scores comparable, use roi_cycle (fractional) instead
        score = (0.40 * roi_cycle +
                 0.30 * balance_score +
                 0.20 * cushion_score +
                 0.10 * liq_score)
        
        rows.append({
            "Strategy": "IRON_CONDOR",
            "Ticker": ticker,
            "Price": round(S, 2),
            "Exp": exp,
            "Days": D,
            
            # Put spread (sell Kps, buy Kpl)
            "PutShortStrike": float(Kps),
            "PutLongStrike": float(Kpl),
            "PutSpreadCredit": round(put_spread_credit, 2),
            "PutShortΔ": round(float(ps_row["delta"]), 3),
            
            # Call spread (sell Kcs, buy Kcl)
            "CallShortStrike": float(Kcs),
            "CallLongStrike": float(Kcl),
            "CallSpreadCredit": round(call_spread_credit, 2),
            "CallShortΔ": round(float(cs_row["delta"]), 3),
            
            # Overall metrics
            "NetCredit": round(net_credit, 2),
            "MaxLoss": round(max_loss, 2),
            "Capital": round(capital, 2),
            
            "ROI%_ann": round(roi_ann * 100.0, 2),
            "ROI%_excess_bills": round(excess_vs_bills * 100.0, 2),
            
            "BreakevenLower": round(breakeven_lower, 2),
            "BreakevenUpper": round(breakeven_upper, 2),
            "Range": round(breakeven_upper - breakeven_lower, 2),
            
            "PutCushionσ": round(put_cushion, 2) if put_cushion == put_cushion else float("nan"),
            "CallCushionσ": round(call_cushion, 2) if call_cushion == call_cushion else float("nan"),
            
            "ProbMaxProfit": round(prob_max_profit, 3) if prob_max_profit == prob_max_profit else float("nan"),
            
            "PutSpread%": round(float(ps_row["spread%"]), 2) if ps_row["spread%"] is not None else float("nan"),
            "CallSpread%": round(float(cs_row["spread%"]), 2) if cs_row["spread%"] is not None else float("nan"),
            "PutShortOI": int(ps_row["oi"]),
            "CallShortOI": int(cs_row["oi"]),
            
            "IV": round(iv_avg * 100.0, 2),
            "Score": round(score, 6)
        })
    
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Score", "ROI%_ann"], ascending=[False, False]).reset_index(drop=True)
    return df


# -------------------------- Best Practices -----------------------

def best_practices(strategy):
    if strategy == "CSP":
        return [
            "Tenor sweet spot: **21–45 DTE** for robust theta and rolling flexibility.",
            "Target **Δ ≈ 0.15–0.30** and **OTM ≥ 8–15%** on single names; looser for broad ETFs.",
            "Liquidity: **OI ≥ 200**, **bid–ask ≤ 10% of mid** (ETFs can be a bit wider).",
            "Avoid **earnings windows** (±3–7 days) for single stocks; ETF CSPs avoid idiosyncratic gaps.",
            "Risk controls: cap **per-contract collateral**, cap **per-ticker exposure**, cap **total options exposure**.",
            "Exit: take **50–75%** of max profit or **roll** when Δ > ~0.35 or ~7–10 DTE.",
        ]
    if strategy == "CC":
        return [
            "Tenor sweet spot: **21–45 DTE**; roll earlier if Δ > ~0.35 or extrinsic collapses.",
            "Strike selection: **OTM 1–6%** or **Δ ≈ 0.20–0.35** depending on desired call-away risk.",
            "Liquidity: **OI ≥ 200**, **bid–ask ≤ 10% of mid**; prefer highly liquid ETFs/megacaps.",
            "Dividend awareness: Calls across ex-div can raise assignment risk; consider strikes beyond expected dividend drop.",
            "Exit: take **50–75%** of max profit; **roll up/out** if the stock trends and you want to keep shares.",
        ]
    if strategy == "COLLAR":
        return [
            "Structure: sell **call Δ ~ +0.25–0.35**, buy **put Δ ~ −0.10–0.15** for low/zero-cost protection.",
            "Tenor: **30–60 DTE** to balance put cost vs. roll cadence.",
            "Liquidity: OI & spreads on **both legs**; avoid expiries with thin puts.",
            "Risk: Downside **floor ≈ (K_put − S) + net credit**; upside **capped near K_call**.",
            "Exit: roll the **short call** when Δ > ~0.40; roll the **put** if floor drifts too low vs. risk tolerance.",
        ]
    if strategy == "IRON_CONDOR":
        return [
            "Structure: Sell **OTM put spread** + Sell **OTM call spread** (neutral income, defined risk).",
            "Tenor: **30–45 DTE** to capture theta decay while avoiding gamma risk near expiry.",
            "Strike selection: Short strikes **Δ ~ ±0.15–0.25** (84–75% POEW); wing width **$5–10** or **5–10% OTM**.",
            "Liquidity: **All 4 legs need OI ≥ 200** and **bid-ask ≤ 10%**; prefer liquid underlyings.",
            "Risk: Max loss = **wing width − net credit**; ideal **credit/max_loss ≥ 25–35%**.",
            "Balance: Target **symmetric wings** (equal cushion on both sides) for neutral outlook.",
            "Exit: Take profit at **50–75% of max credit**; close early if one side Δ > ~0.35 or breached.",
            "Avoid earnings and high-IV events that can cause gap risk through breakevens.",
        ]
    return []

# ---------- Strategy Fit & Runbook helpers ----------


def _fmt_usd(x, nd=2):
    try:
        return f"${float(x):,.{nd}f}"
    except Exception:
        return str(x)


def _iv_decimal(row, default=0.20):
    iv = row.get("IV", float("nan"))
    try:
        ivf = float(iv) / 100.0
        return ivf if ivf == ivf and ivf > 0 else default
    except Exception:
        return default


def _series_get(row, key, default=float("nan")):
    try:
        v = row.get(key, default)
        return v if v == v else default
    except Exception:
        return default


def compute_put_delta_for_row(row, risk_free, div_y):
    S = float(_series_get(row, "Price"))
    K = float(_series_get(row, "Strike"))
    D = int(_series_get(row, "Days", 0))
    T = max(D, 0) / 365.0
    iv = _iv_decimal(row)
    return put_delta(S, K, risk_free, iv, T, q=div_y)


def compute_call_delta_for_row(row, risk_free, div_y, strike_key="Strike"):
    S = float(_series_get(row, "Price"))
    K = float(_series_get(row, strike_key))
    D = int(_series_get(row, "Days", 0))
    T = max(D, 0) / 365.0
    iv = _iv_decimal(row)
    return call_delta(S, K, risk_free, iv, T, q=div_y)


def evaluate_fit(strategy, row, thresholds, *, risk_free=0.0, div_y=0.0, bill_yield=0.0):
    """
    Returns: (summary_df, flags_dict)
      summary_df: table of checks with status (✅/⚠️/❌) and notes
      flags_dict: booleans for use in runbook warnings
    """
    checks = []
    flags = {"assignment_risk": False, "liquidity_warn": False, "tenor_warn": False,
             "excess_negative": False, "cushion_low": False}

    days = int(_series_get(row, "Days", 0))
    spread = float(_series_get(row, "Spread%", float("nan")))
    oi = int(_safe_int(_series_get(row, "OI", 0)))
    roi_ann = float(_series_get(row, "ROI%_ann", float("nan"))) / 100.0
    excess = float(_series_get(row, "ROI%_excess_bills", float("nan"))) / 100.0
    otm_pct = float(_series_get(row, "OTM%", float("nan")))

    # Try to get sigma cushion from the row; if missing/NaN, recompute on the fly.
    # For COLLAR we track separate put/call cushions; show both.
    cushion = float(_series_get(row, "CushionSigma", float("nan")))
    put_cushion = float(_series_get(row, "PutCushionσ", float("nan")))
    call_cushion = float(_series_get(row, "CallCushionσ", float("nan")))

    # Recompute cushion as a fallback if needed
    try:
        S = float(_series_get(row, "Price"))
        K = float(_series_get(row, "Strike", float("nan")))
        T = max(days, 0) / 365.0
        ivd = _iv_decimal(row)  # defaults to 0.20 if missing
        exp_mv = expected_move(S, ivd, T)
        if strategy == "CSP" and (cushion != cushion):
            cushion = ((S - K) / exp_mv) if (exp_mv ==
                                             exp_mv and exp_mv > 0 and K == K) else cushion
        elif strategy == "CC" and (cushion != cushion):
            cushion = ((K - S) / exp_mv) if (exp_mv ==
                                             exp_mv and exp_mv > 0 and K == K) else cushion
        elif strategy == "COLLAR":
            # If either collar cushion is NaN, try to recompute using Strike-like keys
            if put_cushion != put_cushion:
                try:
                    k_put = float(_series_get(row, "PutStrike", float("nan")))
                    put_cushion = ((S - k_put) / exp_mv) if (exp_mv ==
                                                             exp_mv and exp_mv > 0 and k_put == k_put) else put_cushion
                except Exception:
                    pass
            if call_cushion != call_cushion:
                try:
                    k_call = float(_series_get(
                        row, "CallStrike", float("nan")))
                    call_cushion = ((k_call - S) / exp_mv) if (exp_mv ==
                                                               exp_mv and exp_mv > 0 and k_call == k_call) else call_cushion
                except Exception:
                    pass
    except Exception:
        # best-effort fallback only
        pass

    # Tenor sweet spot
    t_low, t_high = (21, 45) if strategy in ("CSP", "CC") else (30, 60)
    if t_low <= days <= t_high:
        checks.append(("Tenor sweet spot", "✅",
                      f"{days} DTE within {t_low}-{t_high}"))
    else:
        checks.append(("Tenor sweet spot", "⚠️",
                      f"{days} DTE outside {t_low}-{t_high}"))
        flags["tenor_warn"] = True

    # Theta/Gamma ratio (for CSP and CC only)
    if strategy in ("CSP", "CC"):
        tg_ratio = float(_series_get(row, "Theta/Gamma", float("nan")))
        if tg_ratio == tg_ratio:
            if tg_ratio >= 1.0:
                checks.append(("Theta/Gamma ratio", "✅",
                              f"{tg_ratio:.2f} (good risk-adjusted decay)"))
            elif tg_ratio >= 0.5:
                checks.append(("Theta/Gamma ratio", "⚠️",
                              f"{tg_ratio:.2f} (acceptable, prefer ≥1.0)"))
            else:
                checks.append(("Theta/Gamma ratio", "❌",
                              f"{tg_ratio:.2f} (high gamma risk, prefer ≥1.0)"))
        else:
            checks.append(("Theta/Gamma ratio", "⚠️", "n/a"))

    # Liquidity
    if oi >= thresholds["min_oi"] and (spread != spread or spread <= thresholds["max_spread"]):
        notes = f"OI {oi} ok" + \
            ("" if spread != spread else f", spread {spread:.1f}% ok")
        checks.append(("Liquidity", "✅", notes))
    else:
        why = []
        if oi < thresholds["min_oi"]:
            why.append(f"OI {oi} < {thresholds['min_oi']}")
        if spread == spread and spread > thresholds["max_spread"]:
            why.append(f"spread {spread:.1f}% > {thresholds['max_spread']}")
        checks.append(
            ("Liquidity", "⚠️", "; ".join(why) or "insufficient data"))
        flags["liquidity_warn"] = True

    # Cushion (sigmas from strike)
    if strategy == "COLLAR":
        # Report both sides for collars
        if put_cushion == put_cushion:
            if put_cushion >= thresholds.get("min_cushion", 1.0):
                checks.append(
                    ("Put sigma cushion", "✅", f"{put_cushion:.2f}σ ≥ {thresholds.get('min_cushion', 1.0)}σ"))
            else:
                checks.append(
                    ("Put sigma cushion", "⚠️", f"{put_cushion:.2f}σ < {thresholds.get('min_cushion', 1.0)}σ"))
                flags["cushion_low"] = True
        else:
            checks.append(("Put sigma cushion", "⚠️", "n/a"))
        if call_cushion == call_cushion:
            if call_cushion >= thresholds.get("min_cushion", 1.0):
                checks.append(
                    ("Call sigma cushion", "✅", f"{call_cushion:.2f}σ ≥ {thresholds.get('min_cushion', 1.0)}σ"))
            else:
                checks.append(("Call sigma cushion", "⚠️",
                              f"{call_cushion:.2f}σ < {thresholds.get('min_cushion', 1.0)}σ"))
        else:
            checks.append(("Call sigma cushion", "⚠️", "n/a"))
    else:
        # CSP/CC: single cushion value
        if cushion == cushion:
            if cushion >= thresholds.get("min_cushion", 1.0):
                checks.append(
                    ("Sigma cushion", "✅", f"{cushion:.2f}σ ≥ {thresholds.get('min_cushion', 1.0)}σ"))
            else:
                checks.append(
                    ("Sigma cushion", "⚠️", f"{cushion:.2f}σ < {thresholds.get('min_cushion', 1.0)}σ"))
                flags["cushion_low"] = True
        else:
            checks.append(("Sigma cushion", "⚠️", "n/a"))

    # Excess over T-bills (if available)
    if excess == excess:
        if excess > 0:
            checks.append(("Excess vs T-bills", "✅",
                          f"+{excess*100:.1f}% annualized"))
        else:
            checks.append(("Excess vs T-bills", "❌",
                          f"{excess*100:.1f}% (negative pickup)"))
            flags["excess_negative"] = True

    # Strategy-specific checks
    if strategy == "CSP":
        pdelta = compute_put_delta_for_row(row, risk_free, div_y)
        target_low, target_high = -0.30, -0.15
        if pdelta == pdelta and target_low <= pdelta <= target_high:
            checks.append(
                ("Δ target (CSP)", "✅", f"put Δ {pdelta:.2f} in [{target_low:.2f},{target_high:.2f}]"))
        else:
            checks.append(
                ("Δ target (CSP)", "⚠️", f"put Δ {pdelta:.2f} (preferred {target_low:.2f}..{target_high:.2f})"))

        if otm_pct == otm_pct:
            if otm_pct >= thresholds.get("min_otm_csp", 10.0):
                checks.append(("OTM distance", "✅", f"{otm_pct:.1f}% OTM"))
            else:
                checks.append(
                    ("OTM distance", "⚠️", f"{otm_pct:.1f}% OTM < {thresholds.get('min_otm_csp', 10.0)}%"))

    elif strategy == "CC":
        cdelta = compute_call_delta_for_row(row, risk_free, div_y)
        # assignment risk proxy (ex-div logic exists in DF as AssignRisk)
        assign_risk = bool(_series_get(row, "AssignRisk", False))
        if cdelta == cdelta and 0.20 <= cdelta <= 0.35:
            checks.append(
                ("Δ target (CC)", "✅", f"call Δ {cdelta:.2f} ~ 0.20–0.35"))
        else:
            checks.append(
                ("Δ target (CC)", "⚠️", f"call Δ {cdelta:.2f} (pref 0.20–0.35)"))
        if assign_risk:
            checks.append(("Ex‑div assignment", "⚠️",
                          "Dividend > call extrinsic → high early assignment risk"))
            flags["assignment_risk"] = True
        if otm_pct == otm_pct and otm_pct < thresholds.get("min_otm_cc", 2.0):
            checks.append(
                ("OTM distance", "⚠️", f"{otm_pct:.1f}% OTM (pref ≥ 2–6%)"))

    elif strategy == "COLLAR":
        cdelta = compute_call_delta_for_row(
            row, risk_free, div_y, strike_key="CallStrike")
        pdelta = put_delta(float(row["Price"]), float(
            row["PutStrike"]), risk_free, _iv_decimal(row), int(row["Days"])/365.0, q=div_y)
        # Targets: call ~ +0.25–0.35, put ~ −0.10..−0.15
        if cdelta == cdelta and 0.25 <= cdelta <= 0.35:
            checks.append(("Δ target (call)", "✅", f"{cdelta:.2f}"))
        else:
            checks.append(("Δ target (call)", "⚠️",
                          f"{cdelta:.2f} (pref 0.25–0.35)"))
        if pdelta == pdelta and -0.15 <= pdelta <= -0.10:
            checks.append(("Δ target (put)", "✅", f"{pdelta:.2f}"))
        else:
            checks.append(
                ("Δ target (put)", "⚠️", f"{pdelta:.2f} (pref −0.10..−0.15)"))

    df = pd.DataFrame(checks, columns=["Check", "Status", "Notes"])
    return df, flags


def build_runbook(strategy, row, *, contracts=1, capture_pct=0.70,
                  risk_rules=None, holds_shares=False):
    """
    Returns plain-text runbook with entry orders, triggers, and close-out orders.
    capture_pct: fraction of initial credit you intend to capture before closing (e.g., 0.70 = 70%)
    risk_rules: dict of extra triggers (e.g., {'delta_limit':0.35})
    """
    risk_rules = risk_rules or {}
    ticker = str(_series_get(row, "Ticker"))
    exp = str(_series_get(row, "Exp"))
    days = int(_series_get(row, "Days", 0))
    S = float(_series_get(row, "Price"))
    lines = []
    hr = "-"*60

    if strategy == "CSP":
        K = float(_series_get(row, "Strike"))
        prem_ps = float(_series_get(row, "Premium"))  # per share
        credit_pc = prem_ps * 100.0
        be = K - prem_ps
        tgt_close_ps = max(0.05, prem_ps * (1.0 - capture_pct))
        lines += [
            f"# RUNBOOK — CASH‑SECURED PUT ({ticker})",
            hr,
            "ENTRY:",
            f"• Sell to Open  {contracts}  {ticker}  {exp}  {int(K)} PUT",
            f"  Order: LIMIT, credit ≥ {_fmt_usd(prem_ps)} per share (≥ {_fmt_usd(credit_pc)} per contract), GTC",
            f"  Collateral required: {_fmt_usd(K*100*contracts, 0)} (cash‑secured)",
            "",
            "PROFIT‑TAKING TRIGGER(S):",
            f"• Close when option mark ≤ {_fmt_usd(tgt_close_ps)} per share  (≈ {int(capture_pct*100)}% credit captured), OR",
            "• Close/roll at ~7–10 DTE if ≥50% credit captured.",
            "",
            "RISK CLOSE‑OUT TRIGGER(S):",
            f"• Underlying ≤ {_fmt_usd(be)} (breakeven) on a close OR",
            "• Put Δ exceeds 0.35 (assignment risk rising) OR",
            "• Sigma cushion < 0.5σ.",
            "",
            "EXIT ORDERS:",
            f"• Profit‑take:  Buy to Close  {contracts}  {ticker}  {exp}  {int(K)} PUT",
            f"  Order: LIMIT, debit ≤ {_fmt_usd(tgt_close_ps)} per share, GTC",
            "• Risk close‑out:  Buy to Close same contract (use STOP‑LIMIT if using price trigger).",
            "",
            "IF ASSIGNED (optional follow‑up):",
            "• Own 100×contracts shares; next cycle consider a Covered Call:",
            "  Sell to Open call Δ≈0.20–0.35, 21–45 DTE, OTM 2–6%, LIMIT."
        ]

    elif strategy == "CC":
        K = float(_series_get(row, "Strike"))
        prem_ps = float(_series_get(row, "Premium"))
        credit_pc = prem_ps * 100.0
        tgt_close_ps = max(0.05, prem_ps * (1.0 - capture_pct))
        need_shares = not holds_shares
        lines += [
            f"# RUNBOOK — COVERED CALL ({ticker})",
            hr,
            "ENTRY:",
            *([f"• Buy {contracts*100} shares {ticker} @ MKT/LIMIT ≤ {_fmt_usd(S)}"]
              if need_shares else ["• (You indicated you already hold the shares)"]),
            f"• Sell to Open  {contracts}  {ticker}  {exp}  {int(K)} CALL",
            f"  Order: LIMIT, credit ≥ {_fmt_usd(prem_ps)} per share (≥ {_fmt_usd(credit_pc)} per contract), GTC",
            "",
            "PROFIT‑TAKING / ROLLING:",
            f"• Buy to Close when call mark ≤ {_fmt_usd(tgt_close_ps)} per share (≈ {int(capture_pct*100)}% credit captured), OR",
            "• If call Δ > 0.35 or price approaches strike, roll up/out (BTC current call, STO next expiry with Δ≈0.25–0.35).",
            "",
            "RISK CLOSE‑OUT:",
            "• If stock declines >8–10% from entry or breaches your risk level, either:",
            "  (A) Add protection: Buy to Open put Δ≈−0.10–−0.15 (create a collar), OR",
            "  (B) Exit: Sell shares and Buy to Close call (or permit assignment if near expiry).",
            "",
            "EXIT ORDERS:",
            f"• Profit‑take: Buy to Close  {contracts}  {ticker}  {exp}  {int(K)} CALL, LIMIT ≤ {_fmt_usd(tgt_close_ps)} per share",
            "• Roll:  (1) BTC current call  (2) STO next‑cycle call (same #contracts), LIMIT combo if supported."
        ]

    elif strategy == "COLLAR":
        Kc = float(_series_get(row, "CallStrike"))
        Kp = float(_series_get(row, "PutStrike"))
        call_prem_ps = float(_series_get(row, "CallPrem"))
        put_debit_ps = float(_series_get(row, "PutPrem"))
        net_ps = call_prem_ps - put_debit_ps
        tgt_close_call_ps = max(0.05, call_prem_ps * (1.0 - capture_pct))
        lines += [
            f"# RUNBOOK — COLLAR ({ticker})",
            hr,
            "ENTRY (combo preferred if broker supports):",
            f"• Buy {contracts*100} shares {ticker} @ MKT/LIMIT ≤ {_fmt_usd(S)}",
            f"• Sell to Open  {contracts}  {ticker}  {exp}  {int(Kc)} CALL   (LIMIT ≥ {_fmt_usd(call_prem_ps)}/sh)",
            f"• Buy to Open   {contracts}  {ticker}  {exp}  {int(Kp)} PUT    (LIMIT ≤ {_fmt_usd(put_debit_ps)}/sh)",
            f"  Net (target):  {_fmt_usd(net_ps)}/sh  ({'credit' if net_ps >= 0 else 'debit'})",
            "",
            "PROFIT‑TAKING / ROLLING:",
            f"• When short call mark ≤ {_fmt_usd(tgt_close_call_ps)}/sh (~{int(capture_pct*100)}% captured), consider:",
            "  (A) Unwind both legs (BTC call + STC put) and keep/exit shares, OR",
            "  (B) Roll the call (BTC then STO higher strike/next cycle).",
            "",
            "RISK CLOSE‑OUT:",
            f"• If price approaches floor (~K_put): consider exiting legs early (BTC call, STC put) and decide on shares.",
            "",
            "EXIT ORDERS:",
            f"• Profit‑take:  BTC  {contracts}  {ticker}  {exp}  {int(Kc)} CALL  (LIMIT),  STC  {contracts}  {ticker}  {exp}  {int(Kp)} PUT  (LIMIT)",
            "• Risk close‑out: same as above; add share exit if needed."
        ]

    return "\n".join(lines)


# ---------- Stress Test engine ----------
def run_stress(strategy, row, *, shocks_pct, horizon_days, r, div_y,
               iv_down_shift=0.10, iv_up_shift=0.00):
    """
    Mark-to-market stress using Black–Scholes with dividend yield q.
    shocks_pct: list of % shocks to S0, e.g., [-20, -10, -5, 0, 5, 10, 20]
    horizon_days: days elapsed before re-marking (reduces T)
    iv_down_shift / iv_up_shift: absolute shifts in volatility (decimal), applied on down/up shocks respectively
    Returns DataFrame with leg marks and P&L per contract.
    """
    S0 = float(row["Price"])
    D = int(row["Days"])
    T0 = max(D, 0) / 365.0
    # Remaining time after horizon; clamp to small positive
    T = max(T0 - max(horizon_days, 0) / 365.0, 1e-6)

    # Base IV (decimal). For collars IV may be missing; fallback to 20%
    try:
        iv_base = float(row.get("IV", float("nan"))) / 100.0
        if not (iv_base == iv_base and iv_base > 0):
            iv_base = 0.20
    except Exception:
        iv_base = 0.20

    out = []
    shocks_pct = list(shocks_pct)
    shocks_pct.sort()

    if strategy == "CSP":
        K = float(row["Strike"])
        prem_entry = float(row["Premium"])  # per share
        for sp in shocks_pct:
            S1 = S0 * (1.0 + sp / 100.0)
            iv1 = max(0.02, iv_base + (iv_down_shift if sp < 0 else iv_up_shift))
            put_now = bs_put_price(S1, K, r, div_y, iv1, T)
            # short put P&L: entry credit - current mark
            pnl_put = (prem_entry - put_now) * 100.0
            total = pnl_put
            capital = K * 100.0
            cycle_roi = total / capital
            # For annualization: if horizon=0 (immediate), use remaining time T0 in years
            # Otherwise use horizon_days
            ann_days = T0 * 365.0 if horizon_days == 0 else float(horizon_days)
            ann_roi = (1.0 + cycle_roi) ** (365.0 / max(1.0, ann_days)) - 1.0
            out.append({
                "Shock%": sp, "Price": S1,
                "Put_mark": put_now, "Put_P&L": pnl_put,
                "Total_P&L": total,
                "ROI_on_cap%": cycle_roi * 100.0,
                "Ann_ROI%": ann_roi * 100.0
            })
        return pd.DataFrame(out)

    if strategy == "CC":
        K = float(row["Strike"])
        call_entry = float(row["Premium"])  # per share
        for sp in shocks_pct:
            S1 = S0 * (1.0 + sp / 100.0)
            iv1 = max(0.02, iv_base + (iv_down_shift if sp < 0 else iv_up_shift))
            call_now = bs_call_price(S1, K, r, div_y, iv1, T)
            pnl_call = (call_entry - call_now) * 100.0    # short call
            pnl_shares = (S1 - S0) * 100.0
            total = pnl_shares + pnl_call
            capital = S0 * 100.0
            cycle_roi = total / capital
            # For annualization: if horizon=0 (immediate), use remaining time T0 in years
            # Otherwise use horizon_days
            ann_days = T0 * 365.0 if horizon_days == 0 else float(horizon_days)
            ann_roi = (1.0 + cycle_roi) ** (365.0 / max(1.0, ann_days)) - 1.0
            out.append({
                "Shock%": sp, "Price": S1,
                "Call_mark": call_now, "Call_P&L": pnl_call,
                "Shares_P&L": pnl_shares,
                "Total_P&L": total,
                "ROI_on_cap%": cycle_roi * 100.0,
                "Ann_ROI%": ann_roi * 100.0
            })
        return pd.DataFrame(out)

    if strategy == "COLLAR":
        Kc = float(row["CallStrike"])
        Kp = float(row["PutStrike"])
        call_entry = float(row["CallPrem"])  # per share credit
        put_entry = float(row["PutPrem"])    # per share debit
        # Collars often have different IVs per wing; use a single IV with shifts for simplicity
        for sp in shocks_pct:
            S1 = S0 * (1.0 + sp / 100.0)
            iv1 = max(0.02, iv_base + (iv_down_shift if sp < 0 else iv_up_shift))
            call_now = bs_call_price(S1, Kc, r, div_y, iv1, T)
            put_now = bs_put_price(S1, Kp, r, div_y, iv1, T)
            pnl_call = (call_entry - call_now) * 100.0  # short call
            pnl_put = (put_now - put_entry) * 100.0    # long put
            pnl_shares = (S1 - S0) * 100.0
            total = pnl_shares + pnl_call + pnl_put
            capital = S0 * 100.0
            cycle_roi = total / capital
            # For annualization: if horizon=0 (immediate), use remaining time T0 in years
            # Otherwise use horizon_days
            ann_days = T0 * 365.0 if horizon_days == 0 else float(horizon_days)
            ann_roi = (1.0 + cycle_roi) ** (365.0 / max(1.0, ann_days)) - 1.0
            out.append({
                "Shock%": sp, "Price": S1,
                "Call_mark": call_now, "Put_mark": put_now,
                "Call_P&L": pnl_call, "Put_P&L": pnl_put,
                "Shares_P&L": pnl_shares,
                "Total_P&L": total,
                "ROI_on_cap%": cycle_roi * 100.0,
                "Ann_ROI%": ann_roi * 100.0
            })
        return pd.DataFrame(out)

    if strategy == "IRON_CONDOR":
        Kps = float(row["PutShortStrike"])
        Kpl = float(row["PutLongStrike"])
        Kcs = float(row["CallShortStrike"])
        Kcl = float(row["CallLongStrike"])
        net_credit = float(row["NetCredit"])  # per share
        
        for sp in shocks_pct:
            S1 = S0 * (1.0 + sp / 100.0)
            iv1 = max(0.02, iv_base + (iv_down_shift if sp < 0 else iv_up_shift))
            
            # Calculate mark prices for all 4 legs
            put_short_now = bs_put_price(S1, Kps, r, div_y, iv1, T)
            put_long_now = bs_put_price(S1, Kpl, r, div_y, iv1, T)
            call_short_now = bs_call_price(S1, Kcs, r, div_y, iv1, T)
            call_long_now = bs_call_price(S1, Kcl, r, div_y, iv1, T)
            
            # P&L calculation: we sold put spread and call spread
            # Put spread: sold Kps, bought Kpl (credit spread, want it to go to zero)
            pnl_put_spread = (put_short_now - put_long_now) * -100.0  # negative because we want value to decrease
            
            # Call spread: sold Kcs, bought Kcl (credit spread, want it to go to zero)
            pnl_call_spread = (call_short_now - call_long_now) * -100.0  # negative because we want value to decrease
            
            # Total P&L = credit received - current spread values
            total = (net_credit * 100.0) + pnl_put_spread + pnl_call_spread
            
            # Capital = max spread width - net credit
            put_width = Kps - Kpl
            call_width = Kcl - Kcs
            capital = (max(put_width, call_width) - net_credit) * 100.0
            
            cycle_roi = total / capital if capital > 0 else 0.0
            ann_days = T0 * 365.0 if horizon_days == 0 else float(horizon_days)
            ann_roi = (1.0 + cycle_roi) ** (365.0 / max(1.0, ann_days)) - 1.0
            
            out.append({
                "Shock%": sp, "Price": S1,
                "PutSpread_mark": put_short_now - put_long_now,
                "CallSpread_mark": call_short_now - call_long_now,
                "PutSpread_P&L": pnl_put_spread,
                "CallSpread_P&L": pnl_call_spread,
                "Total_P&L": total,
                "ROI_on_cap%": cycle_roi * 100.0,
                "Ann_ROI%": ann_roi * 100.0
            })
        return pd.DataFrame(out)

    raise ValueError("Unknown strategy for stress")


def prescreen_tickers(tickers, min_price=5.0, max_price=1000.0, min_avg_volume=500000,
                      min_hv=15.0, max_hv=150.0, min_option_volume=50, check_liquidity=True):
    """
    Pre-screen tickers for options income strategy suitability.
    Uses parallel processing for faster execution on large ticker lists.

    OPTIMIZED FOR SHORT-TERM (10-45 DTE) INCOME STRATEGIES
    Scoring aligns with strategy aggregate score components:
    - High ROI potential (premium/price ratio)
    - Good theta/gamma zones (moderate volatility)
    - Strong liquidity (tight spreads, high OI)
    - Adequate cushion potential (HV 20-50% sweet spot)

    Filters based on:
    - Stock price range (avoid penny stocks, expensive shares)
    - Average daily volume (liquidity)
    - Historical volatility (premium potential) - HV in PERCENTAGE (e.g., 25.0 = 25%)
    - Options market activity (tradeable markets)

    UNITS:
    - HV_30d%: Historical volatility as PERCENTAGE (e.g., 25.0 for 25%)
    - IV%: Implied volatility as PERCENTAGE (e.g., 30.0 for 30%)
    - IV/HV: Ratio of the two percentages (both normalized to same units)

    Returns:
        pd.DataFrame with screening metrics for passed tickers, sorted by quality score
    """

    def screen_single_ticker(ticker):
        """Screen a single ticker - designed for parallel execution"""
        try:
            # Fetch basic stock data
            stock = yf.Ticker(ticker)
            hist = stock.history(period="3mo")

            if hist.empty or len(hist) < 20:
                return None

            # Current price
            current_price = hist['Close'].iloc[-1]
            if current_price < min_price or current_price > max_price:
                return None

            # Average volume
            avg_volume = hist['Volume'].mean()
            if avg_volume < min_avg_volume:
                return None

            # Historical volatility (30-day annualized) - returns as PERCENTAGE
            returns = hist['Close'].pct_change().dropna()
            if len(returns) < 20:
                return None
            # HV calculation: std * sqrt(252) gives decimal, * 100 = percentage
            # Result: percentage (e.g., 25.0 for 25%)
            hv_30 = returns.iloc[-30:].std() * np.sqrt(252) * 100.0

            if hv_30 < min_hv or hv_30 > max_hv:
                return None

            # Check options availability and liquidity
            expirations = stock.options
            if not expirations or len(expirations) == 0:
                return None

            # Get near-term options chain (first expiration)
            try:
                chain = stock.option_chain(expirations[0])

                # Find ATM strike for IV check
                atm_idx = (chain.calls['strike'] -
                           current_price).abs().idxmin()
                atm_call = chain.calls.loc[atm_idx]

                # Extract metrics
                iv = atm_call.get('impliedVolatility', np.nan)
                if pd.isna(iv) or iv <= 0:
                    # Try to get IV from puts if calls missing
                    atm_put_idx = (
                        chain.puts['strike'] - current_price).abs().idxmin()
                    atm_put = chain.puts.loc[atm_put_idx]
                    iv = atm_put.get('impliedVolatility', np.nan)

                if pd.isna(iv) or iv <= 0:
                    return None

                # UNIT CONSISTENCY FIX: Ensure IV is in decimal form (0.0-1.0)
                # yfinance typically returns IV as decimal (e.g., 0.25 for 25%)
                # but can vary by source. Normalize here.
                if iv > 5.0:  # If IV > 5, it's likely already a percentage
                    iv = iv / 100.0  # Convert to decimal

                iv_pct = iv * 100.0  # Now convert to percentage for display/comparison

                # Option volume/OI check
                opt_volume = atm_call.get('volume', 0) or 0
                opt_oi = atm_call.get('openInterest', 0) or 0

                if check_liquidity and (opt_volume < min_option_volume and opt_oi < min_option_volume * 10):
                    return None

                # Bid-Ask spread check for liquidity quality
                bid = atm_call.get('bid', 0) or 0
                ask = atm_call.get('ask', 0) or 0
                mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else 0
                spread_pct = ((ask - bid) / mid * 100.0) if mid > 0 else 100.0

                # Calculate IV Rank proxy (IV vs HV)
                # Both iv_pct and hv_30 are in percentage units (e.g., 25.0 for 25%)
                # Ratio of 1.0 = IV equals HV; >1.0 = IV elevated; <1.0 = IV compressed
                iv_hv_ratio = iv_pct / hv_30 if hv_30 > 0 else 1.0

                # ===== IMPROVED QUALITY SCORE ALIGNED WITH STRATEGY SCORING =====

                # 1. ROI Potential (35% weight in strategy)
                # Premium/price ratio estimate: higher IV = higher premium
                # Sweet spot: 25-50% IV for good premium without excessive risk
                if iv_pct < 20:
                    roi_score = iv_pct / 20.0  # Ramp up to 1.0
                elif iv_pct <= 40:
                    roi_score = 1.0  # Sweet spot
                elif iv_pct <= 60:
                    roi_score = 1.0 - (iv_pct - 40) / 40.0  # Decline to 0.5
                else:
                    # Decline to 0.25
                    roi_score = 0.5 * (1.0 - (iv_pct - 60) / 80.0)
                roi_score = max(0.25, roi_score)

                # 2. Theta/Gamma Optimization (30% weight in strategy)
                # HV 20-40% is optimal for theta/gamma ratio 0.8-3.0
                # Too low = not enough premium, too high = gamma explosion
                if hv_30 < 15:
                    tg_score = 0.3  # Too low, no premium
                elif hv_30 < 20:
                    tg_score = 0.3 + (hv_30 - 15) / 5.0 * 0.4  # Ramp 0.3->0.7
                elif hv_30 <= 35:
                    tg_score = 1.0  # Sweet spot for 21-35 DTE
                elif hv_30 <= 50:
                    tg_score = 1.0 - (hv_30 - 35) / 15.0 * \
                        0.3  # Decline to 0.7
                else:
                    # Continue declining
                    tg_score = 0.7 * (1.0 - (hv_30 - 50) / 100.0)
                tg_score = max(0.2, min(tg_score, 1.0))

                # 3. Liquidity Score (20% weight in strategy)
                # Based on spread, volume, and OI
                spread_score = max(0.0, 1.0 - spread_pct /
                                   20.0)  # Perfect at 0%, zero at 20%
                # Max at 200 contracts
                volume_score = min(opt_volume / 200, 1.0)
                oi_score = min(opt_oi / 1000, 1.0)  # Max at 1000 OI
                liq_score = 0.5 * spread_score + 0.3 * volume_score + 0.2 * oi_score

                # 4. Cushion/Safety Score (15% weight in strategy)
                # Stock volume and price stability
                # Higher volume = easier to trade, better fills
                # Max at 2M shares/day
                vol_score = min(avg_volume / 2_000_000, 1.0)

                # Check price stability (lower daily range = more predictable)
                price_range_pct = ((hist['High'].iloc[-20:].mean() - hist['Low'].iloc[-20:].mean()) /
                                   hist['Close'].iloc[-20:].mean() * 100.0)
                # Penalize >10% daily ranges
                stability_score = max(0.3, 1.0 - price_range_pct / 10.0)

                cushion_score = 0.6 * vol_score + 0.4 * stability_score

                # ===== WEIGHTED QUALITY SCORE (aligned with strategy weights) =====
                quality_score = (0.35 * roi_score +      # ROI potential
                                 0.30 * tg_score +        # Theta/Gamma optimization
                                 0.20 * liq_score +       # Liquidity
                                 0.15 * cushion_score)    # Safety/cushion

                # IV/HV ratio for additional insight
                # Ideal: 1.0-1.5 (IV slightly elevated vs HV = good premium without crazy risk)
                iv_rank_proxy = "HIGH" if iv_hv_ratio > 1.3 else (
                    "NORMAL" if iv_hv_ratio > 0.8 else "LOW")

                return {
                    'Ticker': ticker,
                    'Price': round(current_price, 2),
                    'Avg_Volume': int(avg_volume),
                    'HV_30d%': round(hv_30, 1),
                    'IV%': round(iv_pct, 1),
                    'IV/HV': round(iv_hv_ratio, 2),
                    'IV_Rank': iv_rank_proxy,
                    'Spread%': round(spread_pct, 1),
                    'Opt_Volume': int(opt_volume),
                    'Opt_OI': int(opt_oi),
                    'Expirations': len(expirations),
                    'Quality_Score': round(quality_score, 3),
                    # Component scores for transparency
                    'ROI_Score': round(roi_score, 2),
                    'TG_Score': round(tg_score, 2),
                    'Liq_Score': round(liq_score, 2),
                    'Safe_Score': round(cushion_score, 2)
                }

            except Exception:
                # Chain fetch failed, skip this ticker
                return None

        except Exception:
            # Ticker fetch failed entirely, skip
            return None

    # Parallel execution for pre-screening
    results = []
    max_workers = min(len(tickers), 10)  # Cap at 10 workers for pre-screening

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all ticker screens
        future_to_ticker = {executor.submit(
            screen_single_ticker, ticker): ticker for ticker in tickers}

        # Collect results as they complete
        for future in as_completed(future_to_ticker):
            result = future.result()
            if result is not None:
                results.append(result)

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df = df.sort_values(
        'Quality_Score', ascending=False).reset_index(drop=True)
    return df

# -------------------------- Streamlit UI -------------------------


st.set_page_config(
    page_title="Strategy Lab: CSP vs CC vs Collar", layout="wide")
# Initialize Polygon client only if not already provided by app.py and toggle enabled
if "USE_POLYGON" in globals() and USE_POLYGON and "POLY" in globals() and POLY is None and PolygonClient:
    try:
        POLY = PolygonClient()  # reads POLYGON_API_KEY
    except Exception as e:
        st.warning(f"Polygon not initialized: {e}. Falling back to yfinance.")
        USE_POLYGON = False

st.title("📊 Options Income Strategy Lab — CSP vs Covered Call vs Collar")

# Initialize session state
for key in ["df_csp", "df_cc", "df_collar", "df_iron_condor"]:
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame()

# Initialize diagnostics tracking
_init_data_calls()

with st.sidebar:
    st.header("Universe & Filters")
    
    # Data Provider Selection
    with st.expander("📡 Data Provider", expanded=False):
        provider_options = ["yfinance", "schwab", "polygon"]
        current_provider = PROVIDER if PROVIDER_SYSTEM_AVAILABLE else "yfinance"
        
        selected_provider = st.selectbox(
            "Select Data Provider",
            options=provider_options,
            index=provider_options.index(current_provider) if current_provider in provider_options else 0,
            help="YFinance: Free, 15-min delay | Schwab: Real-time (requires auth) | Polygon: Premium data"
        )
        
        # Update provider if changed
        if selected_provider != current_provider:
            import os
            os.environ["OPTIONS_PROVIDER"] = selected_provider
            st.info(f"Provider changed to {selected_provider}. Restart app to apply changes.")
        
        # Show provider status
        if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE:
            st.success(f"✓ Active: {selected_provider.upper()}")
        else:
            st.warning(f"⚠ Using fallback: YFinance")
            if selected_provider == "schwab":
                st.caption("Configure Schwab credentials in environment or secrets")
            elif selected_provider == "polygon":
                st.caption("Set POLYGON_API_KEY in environment")

    # Pre-screener section
    with st.expander("🎯 Pre-Screen Tickers", expanded=False):
        st.caption(
            "Filter a large ticker list for high-quality options candidates")
        prescreen_input = st.text_area(
            "Tickers to pre-screen (comma-separated)",
            value="AAPL, MSFT, GOOGL, AMZN, NVDA, AMD, TSLA, META, NFLX, JPM, BAC, GS, XOM, CVX, DIS, COIN, PLTR, SHOP, SQ, RIOT, MARA, SOFI, F, GM, BA, CAT, NKE, MCD, WMT, TGT, HD, LOW, PFE, JNJ, UNH, CRM, ORCL, INTC, QCOM, MU, AVGO",
            height=100,
            key="prescreen_tickers"
        )
        col1, col2 = st.columns(2)
        with col1:
            ps_min_price = st.number_input(
                "Min price", value=5.0, step=1.0, key="ps_min_price")
            ps_min_hv = st.number_input(
                "Min HV%", value=15.0, step=5.0, key="ps_min_hv")
            ps_min_volume = st.number_input(
                "Min avg volume", value=500000, step=100000, key="ps_min_volume", format="%d")
        with col2:
            ps_max_price = st.number_input(
                "Max price", value=1000.0, step=50.0, key="ps_max_price")
            ps_max_hv = st.number_input(
                "Max HV%", value=150.0, step=10.0, key="ps_max_hv")
            ps_min_opt_vol = st.number_input(
                "Min option vol", value=50, step=10, key="ps_min_opt_vol")

        if st.button("🔍 Run Pre-Screen", key="btn_prescreen"):
            prescreen_tickers_list = [t.strip().upper()
                                      for t in prescreen_input.split(",") if t.strip()]
            if prescreen_tickers_list:
                with st.spinner(f"Pre-screening {len(prescreen_tickers_list)} tickers..."):
                    ps_results = prescreen_tickers(
                        prescreen_tickers_list,
                        min_price=ps_min_price,
                        max_price=ps_max_price,
                        min_avg_volume=int(ps_min_volume),
                        min_hv=ps_min_hv,
                        max_hv=ps_max_hv,
                        min_option_volume=int(ps_min_opt_vol),
                        check_liquidity=True
                    )
                    st.session_state["prescreen_results"] = ps_results
                    if not ps_results.empty:
                        st.success(
                            f"✅ {len(ps_results)} tickers passed screening")
                        # Auto-populate main ticker input with top results
                        top_tickers = ps_results.head(10)['Ticker'].tolist()
                        st.session_state["prescreen_top_tickers"] = ", ".join(
                            top_tickers)
                    else:
                        st.warning("No tickers passed the screening criteria")
            else:
                st.error("Please enter tickers to pre-screen")

        # Display results if available
        if "prescreen_results" in st.session_state and not st.session_state["prescreen_results"].empty:
            st.divider()
            st.subheader("📊 Pre-Screen Results")
            ps_df = st.session_state["prescreen_results"]

            # Add summary statistics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Passed", len(ps_df))
            with col2:
                avg_quality = ps_df['Quality_Score'].mean()
                st.metric("Avg Quality", f"{avg_quality:.2f}")
            with col3:
                high_quality = len(ps_df[ps_df['Quality_Score'] >= 0.70])
                st.metric("High Quality (≥0.70)", high_quality)
            with col4:
                avg_iv = ps_df['IV%'].mean()
                st.metric("Avg IV", f"{avg_iv:.1f}%")

            st.caption("""
            **Quality Score Breakdown:**
            - 35% ROI Potential (IV 25-40% optimal)
            - 30% Theta/Gamma (HV 20-35% optimal)  
            - 20% Liquidity (spread, volume, OI)
            - 15% Safety/Cushion (volume, stability)
            """)

            # Show main columns
            display_cols = ['Ticker', 'Price', 'HV_30d%', 'IV%', 'IV/HV', 'IV_Rank',
                            'Spread%', 'Opt_Volume', 'Opt_OI', 'Quality_Score']
            display_cols = [c for c in display_cols if c in ps_df.columns]
            st.dataframe(ps_df[display_cols], height=300,
                         use_container_width=True)

            # Expandable detailed scores
            with st.expander("🔍 View Detailed Component Scores"):
                detail_cols = ['Ticker', 'Quality_Score', 'ROI_Score', 'TG_Score',
                               'Liq_Score', 'Safe_Score', 'IV%', 'HV_30d%', 'Spread%']
                detail_cols = [c for c in detail_cols if c in ps_df.columns]
                st.dataframe(ps_df[detail_cols], use_container_width=True)
                st.caption("""
                **Component Scores (0.0 - 1.0):**
                - **ROI_Score**: Premium potential (higher IV = more premium)
                - **TG_Score**: Theta/Gamma efficiency (HV 20-35% ideal)
                - **Liq_Score**: Market liquidity (tight spreads, high volume/OI)
                - **Safe_Score**: Trading safety (volume, price stability)
                """)

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("📋 Use Top 10 for Scan", key="btn_use_prescreen"):
                    top_tickers = ps_df.head(10)['Ticker'].tolist()
                    tickers_str = ", ".join(top_tickers)
                    st.session_state["main_tickers_input"] = tickers_str
                    st.rerun()
            with col_b:
                csv = ps_df.to_csv(index=False)
                st.download_button(
                    label="💾 Download CSV",
                    data=csv,
                    file_name="prescreen_results.csv",
                    mime="text/csv",
                    key="btn_download_prescreen"
                )

    st.divider()
    tickers_str = st.text_input("Tickers (comma-separated)",
                                value="SPY, QQQ, IWM, AAPL, MSFT, NVDA, KO, IBM, XLF, XLE",
                                key="main_tickers_input")

    col_days1, col_days2 = st.columns(2)
    with col_days1:
        min_days = st.slider("Min Days to Expiry", 1, 60,
                             10, step=1, key="min_days")
    with col_days2:
        days_limit = st.slider("Max Days to Expiry", 7,
                               90, 45, step=1, key="max_days")

    risk_free = st.number_input("Risk-free rate (annualized, decimal)",
                                value=0.00, step=0.01, format="%.2f", key="risk_free_input")
    t_bill_yield = st.number_input(
        "13-week T-bill yield (annualized, decimal)",
        value=0.00, step=0.01, format="%.2f", key="t_bill_yield_input"
    )
    st.caption("General liquidity filters")
    min_oi = st.slider("Min Open Interest", 0, 2000,
                       200, step=50, key="min_oi")
    max_spread = st.slider("Max Bid–Ask % of Mid", 1.0,
                           30.0, 10.0, step=0.5, key="max_spread")

    st.divider()
    # Diagnostics
    _init_data_calls()
    with st.expander("Diagnostics", expanded=False):
        # Show provider system status
        if USE_PROVIDER_SYSTEM:
            st.success(f"✓ Provider System Active: {PROVIDER}")
        else:
            st.info("Using legacy provider system")
        
        st.radio(
            "Provider override (legacy)",
            options=["auto", "yfinance", "polygon"],
            index=["auto", "yfinance", "polygon"].index(
                str(st.session_state.get("provider_override", "auto"))),
            key="provider_override",
            help="auto = try Polygon first, then YFinance fallback; yfinance = force YFinance-only; polygon = force Polygon-only (no fallback). Note: New provider system takes precedence.",
        )
        st.caption(
            f"Polygon enabled by config (USE_POLYGON): {bool(USE_POLYGON)}; Client present: {POLY is not None}")
        if _provider_override() == "polygon" and not _polygon_ready():
            st.warning("Polygon override selected but Polygon is not configured. Set USE_POLYGON=True and provide a POLY client (or add a providers.polygon adapter and POLYGON_API_KEY).")
    # Diagnostics will display below after actions (to reflect latest state)
        colA, colB = st.columns(2)
        with colA:
            if st.button("Clear data cache", key="btn_clear_cache"):
                fetch_price.clear()
                fetch_expirations.clear()
                fetch_chain.clear()
                st.success("Data cache cleared.")
        with colB:
            if st.button("Reset counters", key="btn_reset_counters"):
                st.session_state.pop("data_calls", None)
                st.session_state.pop("last_provider", None)
                _init_data_calls()
                st.success("Diagnostics reset.")

        st.divider()
        st.write("Live probe (bypass cache)")
        probe_symbol = st.text_input(
            "Symbol to probe", value="AAPL", key="diag_symbol")
        probe_exp = st.text_input(
            "Expiry to probe (YYYY-MM-DD)", value="", key="diag_exp")
        if st.button("Run probes", key="btn_run_probes"):
            # Price
            _ = fetch_price_uncached(probe_symbol)
            # Expirations
            exps = fetch_expirations_uncached(probe_symbol)
            # Chain (only if expiry provided or exists)
            exp_to_use = probe_exp.strip() or (exps[0] if exps else "")
            if exp_to_use:
                _ = fetch_chain_uncached(probe_symbol, exp_to_use)
            st.success(
                "Probes executed. See 'Last provider used' and counters below.")
    # Always show the latest values after any actions above
        calls = st.session_state["data_calls"]
        lastp = st.session_state["last_provider"]
        st.write("Last provider used:")
        st.json(lastp)
        st.write("Call counters:")
        st.json(calls)
        st.write("Last attempt (provider tried):")
        st.json(st.session_state.get("last_attempt", {}))
        st.write("Last errors (by provider):")
        st.json(st.session_state.get("data_errors", {}))
        if "scan_counters" in st.session_state:
            st.write("Last scan counters:")
            st.json(st.session_state.get("scan_counters", {}))
    st.subheader("CSP")
    min_otm_csp = st.slider("Min OTM % (CSP)", 0.0, 30.0,
                            8.0, step=0.5, key="min_otm_csp")
    min_roi_csp = st.slider("Min Ann. ROI (decimal, CSP)",
                            0.00, 0.50, 0.20, step=0.01)
    min_cushion = st.slider("Min Cushion σ (CSP)", 0.0, 3.0, 0.75, step=0.1)
    min_poew = st.slider("Min POEW (CSP, expire worthless)",
                         0.50, 0.95, 0.60, step=0.01)
    earn_window = st.slider(
        "Earnings window (± days, CSP/CC)", 0, 14, 5, step=1, key="earn_window")
    per_contract_cap = st.number_input(
        "Per-contract collateral cap ($, CSP)", min_value=0, value=0, step=1000, key="per_contract_cap_input")
    per_contract_cap = None if per_contract_cap == 0 else float(
        per_contract_cap)

    st.divider()
    st.subheader("Covered Call")
    min_otm_cc = st.slider("Min OTM % (CC)", 0.0, 20.0,
                           3.0, step=0.5, key="min_otm_cc")
    min_roi_cc = st.slider("Min Ann. ROI (decimal, CC)",
                           0.00, 0.50, 0.08, step=0.01)
    include_div_cc = st.checkbox("Include dividend estimate (CC)", value=True)

    st.divider()
    st.subheader("Collar")
    call_delta_tgt = st.slider(
        "Target Call Δ", 0.10, 0.50, 0.30, step=0.01, key="call_delta_tgt")
    put_delta_tgt = st.slider("Target Put Δ (abs)",
                              0.05, 0.30, 0.10, step=0.01, key="put_delta_tgt")
    include_div_col = st.checkbox(
        "Include dividend estimate (Collar)", value=True)
    min_net_credit = st.number_input(
        "Min net credit ($/sh, Collar, optional)", value=0.0, step=0.05, key="min_net_credit_input")

    st.subheader("Iron Condor")
    ic_target_delta = st.slider(
        "Short Strike Target Δ (abs)", 0.10, 0.30, 0.16, step=0.01, key="ic_target_delta",
        help="Target delta for short strikes (~0.16 = 84% POEW)")
    ic_spread_width_put = st.number_input(
        "Put Spread Width ($)", value=5.0, step=1.0, key="ic_spread_width_put",
        help="Distance between short and long put strikes")
    ic_spread_width_call = st.number_input(
        "Call Spread Width ($)", value=5.0, step=1.0, key="ic_spread_width_call",
        help="Distance between short and long call strikes")
    ic_min_roi = st.number_input(
        "Min ROI % (annualized, Iron Condor)", value=15.0, step=1.0, key="ic_min_roi_input",
        help="Minimum annualized return on risk")
    ic_min_cushion = st.number_input(
        "Min Cushion (σ, Iron Condor)", value=0.5, step=0.1, key="ic_min_cushion_input",
        help="Minimum cushion in standard deviations for both wings")

    st.divider()
    run_btn = st.button("🔎 Scan Strategies")


@st.cache_data(show_spinner=True, ttl=120)
def run_scans(tickers, params):
    """
    Run CSP, CC, Collar, and Iron Condor scans in parallel across tickers.
    Uses ThreadPoolExecutor for concurrent processing.
    """
    # Handle empty ticker list
    if not tickers or len(tickers) == 0:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {"CSP": {}}

    csp_all = []
    cc_all = []
    col_all = []
    ic_all = []
    scan_counters = {"CSP": {}}

    def scan_ticker(t):
        """Scan a single ticker for all strategies"""
        # CSP scan
        csp, csp_cnt = analyze_csp(
            t,
            min_days=params["min_days"],
            days_limit=params["days_limit"],
            min_otm=params["min_otm_csp"],
            min_oi=params["min_oi"],
            max_spread=params["max_spread"],
            min_roi=params["min_roi_csp"],
            min_cushion=params["min_cushion"],
            min_poew=params["min_poew"],
            earn_window=params["earn_window"],
            risk_free=params["risk_free"],
            per_contract_cap=params["per_contract_cap"],
            bill_yield=params["bill_yield"]
        )

        # CC scan
        cc = analyze_cc(
            t,
            min_days=params["min_days"],
            days_limit=params["days_limit"],
            min_otm=params["min_otm_cc"],
            min_oi=params["min_oi"],
            max_spread=params["max_spread"],
            min_roi=params["min_roi_cc"],
            earn_window=params["earn_window"],
            risk_free=params["risk_free"],
            include_dividends=params["include_div_cc"],
            bill_yield=params["bill_yield"]
        )

        # Collar scan
        col = analyze_collar(
            t,
            min_days=params["min_days"],
            days_limit=params["days_limit"],
            min_oi=params["min_oi"],
            max_spread=params["max_spread"],
            call_delta_target=params["call_delta_tgt"],
            put_delta_target=params["put_delta_tgt"],
            earn_window=params["earn_window"],
            risk_free=params["risk_free"],
            include_dividends=params["include_div_col"],
            min_net_credit=params["min_net_credit"],
            bill_yield=params["bill_yield"]
        )

        # Iron Condor scan
        ic = analyze_iron_condor(
            t,
            min_days=params["min_days"],
            days_limit=params["days_limit"],
            min_oi=params["min_oi"],
            max_spread=params["max_spread"],
            min_roi=params["ic_min_roi"] / 100.0,
            min_cushion=params["ic_min_cushion"],
            earn_window=params["earn_window"],
            risk_free=params["risk_free"],
            spread_width_put=params["ic_spread_width_put"],
            spread_width_call=params["ic_spread_width_call"],
            target_delta_short=params["ic_target_delta"],
            bill_yield=params["bill_yield"]
        )

        return csp, csp_cnt, cc, col, ic

    # Parallel execution with ThreadPoolExecutor
    max_workers = min(len(tickers), 8)  # Cap at 8 concurrent workers

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all ticker scans
        future_to_ticker = {executor.submit(
            scan_ticker, t): t for t in tickers}

        # Collect results as they complete
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                csp, csp_cnt, cc, col, ic = future.result()

                # Accumulate results
                if not csp.empty:
                    csp_all.append(csp)
                if not cc.empty:
                    cc_all.append(cc)
                if not col.empty:
                    col_all.append(col)
                if not ic.empty:
                    ic_all.append(ic)

                # Aggregate counters
                for k, v in csp_cnt.items():
                    scan_counters["CSP"][k] = scan_counters["CSP"].get(
                        k, 0) + int(v)

            except Exception as e:
                # Log error but continue with other tickers
                st.warning(f"⚠️ Error scanning {ticker}: {str(e)}")
                import traceback
                st.text(traceback.format_exc())

    # Combine all results
    df_csp = pd.concat(
        csp_all, ignore_index=True) if csp_all else pd.DataFrame()
    df_cc = pd.concat(cc_all, ignore_index=True) if cc_all else pd.DataFrame()
    df_col = pd.concat(
        col_all, ignore_index=True) if col_all else pd.DataFrame()
    df_ic = pd.concat(
        ic_all, ignore_index=True) if ic_all else pd.DataFrame()

    return df_csp, df_cc, df_col, df_ic, scan_counters


# Run scans
if run_btn:
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]

    if not tickers:
        st.error("Please enter at least one ticker symbol")
    else:
        opts = dict(
            min_days=int(min_days),
            days_limit=int(days_limit),
            min_otm_csp=float(min_otm_csp), min_roi_csp=float(min_roi_csp),
            min_cushion=float(min_cushion), min_poew=float(min_poew),
            min_otm_cc=float(min_otm_cc), min_roi_cc=float(min_roi_cc),
            include_div_cc=bool(include_div_cc),
            call_delta_tgt=float(call_delta_tgt), put_delta_tgt=float(put_delta_tgt),
            include_div_col=bool(include_div_col), min_net_credit=float(min_net_credit),
            ic_target_delta=float(ic_target_delta),
            ic_spread_width_put=float(ic_spread_width_put),
            ic_spread_width_call=float(ic_spread_width_call),
            ic_min_roi=float(ic_min_roi),
            ic_min_cushion=float(ic_min_cushion),
            min_oi=int(min_oi), max_spread=float(max_spread),
            earn_window=int(earn_window), risk_free=float(risk_free),
            per_contract_cap=per_contract_cap,
            bill_yield=float(t_bill_yield)
        )
        try:
            with st.spinner("Scanning..."):
                df_csp, df_cc, df_collar, df_iron_condor, scan_counters = run_scans(
                    tickers, opts)
            st.session_state["df_csp"] = df_csp
            st.session_state["df_cc"] = df_cc
            st.session_state["df_collar"] = df_collar
            st.session_state["df_iron_condor"] = df_iron_condor
            st.session_state["scan_counters"] = scan_counters

            # Show results summary
            total_results = len(df_csp) + len(df_cc) + len(df_collar) + len(df_iron_condor)
            if total_results > 0:
                st.success(
                    f"✅ Scan complete! Found {len(df_csp)} CSP, {len(df_cc)} CC, {len(df_collar)} Collar, {len(df_iron_condor)} Iron Condor opportunities")
            else:
                st.warning(
                    "No opportunities found with current filters. Try loosening your criteria.")

                # ALWAYS show debug info when no results
                with st.expander("🔍 Debug: Why no results?", expanded=True):
                    st.write(f"**Tickers scanned:** {', '.join(tickers)}")
                    st.write(f"**Scan counters:** {scan_counters}")

                    # Show scan counters to help debug
                    if "CSP" in scan_counters and scan_counters["CSP"]:
                        st.write("**CSP Filter Results:**")
                        counters = scan_counters["CSP"]
                        if counters.get("expirations", 0) > 0:
                            st.write(
                                f"- Expirations checked: {counters.get('expirations', 0)}")
                            st.write(
                                f"- Total option rows: {counters.get('rows', 0)}")
                            st.write(
                                f"- Passed premium check: {counters.get('premium_pass', 0)}")
                            st.write(
                                f"- Passed OTM% check: {counters.get('otm_pass', 0)}")
                            st.write(
                                f"- Passed ROI% check: {counters.get('roi_pass', 0)}")
                            st.write(
                                f"- Passed OI check: {counters.get('oi_pass', 0)}")
                            st.write(
                                f"- Passed spread check: {counters.get('spread_pass', 0)}")
                            st.write(
                                f"- Passed cushion check: {counters.get('cushion_pass', 0)}")
                            st.write(
                                f"- Passed POEW check: {counters.get('poew_pass', 0)}")
                            st.write(
                                f"- Final results: {counters.get('final', 0)}")
                        else:
                            st.write(
                                "❌ No expirations were processed. This might indicate:")
                            st.write(
                                "- Network/API issues fetching option chains")
                            st.write(
                                "- All expirations filtered out by date range")
                            st.write("- Ticker has no options available")
                    else:
                        st.write(
                            "❌ **No CSP counters available - scan may have failed completely**")
                        st.write("Check if warnings appeared above during scan")
        except Exception as e:
            st.error(f"Error during scan: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# Read latest results

df_csp = st.session_state["df_csp"]
df_cc = st.session_state["df_cc"]
df_collar = st.session_state["df_collar"]
df_iron_condor = st.session_state["df_iron_condor"]

# --- Universal Contract / Structure Picker (applies to all tabs) ---
st.subheader("Selection — applies to Risk, Runbook, and Stress tabs")

# Determine available strategies based on scan results
_available = [("CSP", df_csp), ("CC", df_cc), ("COLLAR", df_collar), ("IRON_CONDOR", df_iron_condor)]
available_strats = [name for name, df in _available if not df.empty]
if "sel_strategy" not in st.session_state:
    st.session_state["sel_strategy"] = (
        available_strats[0] if available_strats else "CSP")

# Strategy picker (single source of truth)
sel_strategy = st.selectbox(
    "Strategy",
    ["CSP", "CC", "COLLAR", "IRON_CONDOR"],
    index=["CSP", "CC", "COLLAR", "IRON_CONDOR"].index(st.session_state["sel_strategy"]),
    key="sel_strategy",
)

# Helper to build key series per strategy (standardized across app)


def _keys_for(strategy: str) -> pd.Series:
    if strategy == "CSP":
        df = df_csp
        return (
            df["Ticker"] + " | " + df["Exp"] +
            " | K=" + df["Strike"].astype(str)
        ) if not df.empty else pd.Series([], dtype=str)
    if strategy == "CC":
        df = df_cc
        return (
            df["Ticker"] + " | " + df["Exp"] +
            " | K=" + df["Strike"].astype(str)
        ) if not df.empty else pd.Series([], dtype=str)
    if strategy == "COLLAR":
        df = df_collar
        if df.empty:
            return pd.Series([], dtype=str)
        return (
            df["Ticker"] + " | " + df["Exp"]
            + " | Kc=" + df["CallStrike"].astype(str)
            + " | Kp=" + df["PutStrike"].astype(str)
        )
    # IRON_CONDOR
    df = df_iron_condor
    if df.empty:
        return pd.Series([], dtype=str)
    return (
        df["Ticker"] + " | " + df["Exp"]
        + " | CS=" + df["CallShortStrike"].astype(str)
        + " | PS=" + df["PutShortStrike"].astype(str)
    )


# Contract/structure picker (single source of truth)
keys_series = _keys_for(sel_strategy)
if keys_series.empty:
    st.info("No results for selected strategy. Run a scan.")
    st.session_state["sel_key"] = None
else:
    current_key = st.session_state.get("sel_key")
    key_list = keys_series.tolist()
    if (current_key is None) or (current_key not in key_list):
        current_key = key_list[0]
        st.session_state["sel_key"] = current_key
    st.selectbox(
        "Contract / Structure",
        key_list,
        index=key_list.index(st.session_state["sel_key"]),
        key="sel_key",
    )

# Convenience: function to retrieve the selected row


def _get_selected_row():
    strat = st.session_state.get("sel_strategy")
    key = st.session_state.get("sel_key")
    if not key:
        return strat, None
    if strat == "CSP":
        df = df_csp
        ks = (df["Ticker"] + " | " + df["Exp"] + " | K=" +
              df["Strike"].astype(str)) if not df.empty else pd.Series([], dtype=str)
    elif strat == "CC":
        df = df_cc
        ks = (df["Ticker"] + " | " + df["Exp"] + " | K=" +
              df["Strike"].astype(str)) if not df.empty else pd.Series([], dtype=str)
    elif strat == "COLLAR":
        df = df_collar
        if df.empty:
            return strat, None
        ks = (df["Ticker"] + " | " + df["Exp"]
              + " | Kc=" + df["CallStrike"].astype(str)
              + " | Kp=" + df["PutStrike"].astype(str))
    else:  # IRON_CONDOR
        df = df_iron_condor
        if df.empty:
            return strat, None
        ks = (df["Ticker"] + " | " + df["Exp"]
              + " | CS=" + df["CallShortStrike"].astype(str)
              + " | PS=" + df["PutShortStrike"].astype(str))
    if df.empty:
        return strat, None
    sel = df[ks == key]
    if sel.empty:
        return strat, None
    return strat, sel.iloc[0]


# --- Earnings Calendar Display ---
# DISABLED: Commented out to improve performance
# st.divider()
# st.subheader("📅 Earnings Calendar")
#
# # Collect all unique tickers from results
# all_tickers = set()
# if not df_csp.empty:
#     all_tickers.update(df_csp["Ticker"].unique())
# if not df_cc.empty:
#     all_tickers.update(df_cc["Ticker"].unique())
# if not df_collar.empty:
#     all_tickers.update(df_collar["Ticker"].unique())
#
# if all_tickers:
#     with st.spinner("Fetching earnings dates..."):
#         earnings_data = []
#         failed_tickers = []
#         for ticker in sorted(all_tickers):
#             try:
#                 stock = yf.Ticker(ticker)
#                 earn_date = get_earnings_date(stock)
#                 if earn_date:
#                     days_to_earn = (
#                         earn_date - datetime.now(timezone.utc).date()).days
#                     status = "🟢 Safe" if abs(days_to_earn) > int(
#                         earn_window) else "🔴 CAUTION"
#                     earnings_data.append({
#                         "Ticker": ticker,
#                         "Earnings Date": earn_date.strftime("%Y-%m-%d"),
#                         "Days Away": days_to_earn,
#                         "Status": status
#                     })
#                 else:
#                     failed_tickers.append(ticker)
#             except Exception as e:
#                 failed_tickers.append(ticker)
#
#     if earnings_data:
#         earnings_df = pd.DataFrame(earnings_data).sort_values("Days Away")
#         st.dataframe(earnings_df, use_container_width=True, height=200)
#         st.caption(
#             f"🔴 CAUTION: Earnings within ±{int(earn_window)} days (positions filtered out automatically)")
#         st.caption(f"🟢 Safe: Earnings beyond ±{int(earn_window)} days")
#         if failed_tickers:
#             with st.expander(f"ℹ️ No earnings data for {len(failed_tickers)} ticker(s) - Click to view"):
#                 st.write(", ".join(failed_tickers))
#                 st.caption(
#                     "**Note:** ETFs, small-cap stocks, and some international tickers may lack earnings data. Always verify with your broker.")
#     else:
#         st.warning(
#             f"⚠️ No earnings dates available for: {', '.join(sorted(all_tickers))}")
#         st.info("**Why?** yfinance often lacks earnings data for ETFs and some stocks. For these tickers, manually verify earnings dates before trading. The automatic earnings filter only works when data is available.")
# else:
#     st.info("Run a scan to see earnings calendar for your tickers.")
#
# st.divider()

tabs = st.tabs([
    "Cash‑Secured Puts", "Covered Calls", "Collars", "Iron Condor",
    "Compare", "Risk (Monte Carlo)", "Playbook",
    "Plan & Runbook", "Stress Test", "Overview", "Roll Analysis"
])

# --- Tab 1: CSP ---
with tabs[0]:
    st.header("Cash‑Secured Puts")
    if df_csp.empty:
        st.info("Run a scan or loosen CSP filters.")
    else:
        show_cols = ["Strategy", "Ticker", "Price", "Exp", "Days", "Strike", "Premium", "OTM%", "ROI%_ann",
                     "IV", "POEW", "CushionSigma", "Theta/Gamma", "Spread%", "OI", "Collateral", "DaysToEarnings", "Score"]
        show_cols = [c for c in show_cols if c in df_csp.columns]

        # Add earnings warning info box
        if "DaysToEarnings" in df_csp.columns:
            # Filter for non-null values and convert to numeric to handle None
            days_col = pd.to_numeric(df_csp["DaysToEarnings"], errors='coerce')
            earnings_nearby = df_csp[days_col.notna() & (days_col.abs() <= 14)]
            if not earnings_nearby.empty:
                st.warning(
                    f"⚠️ {len(earnings_nearby)} position(s) have earnings within 14 days. Review 'DaysToEarnings' column.")

        st.dataframe(df_csp[show_cols], use_container_width=True, height=520)

        # Add earnings legend
        st.caption(
            "**DaysToEarnings**: Days until next earnings (positive = future, negative = past, blank = unknown) | "
            "Data source: Yahoo Finance (Alpha Vantage fallback enabled only during order preview to preserve API quota)"
        )

# --- Tab 2: CC ---
with tabs[1]:
    st.header("Covered Calls")
    if df_cc.empty:
        st.info("Run a scan or loosen CC filters.")
    else:
        show_cols = ["Strategy", "Ticker", "Price", "Exp", "Days", "Strike", "Premium", "OTM%", "ROI%_ann",
                     "IV", "POEC", "CushionSigma", "Theta/Gamma", "Spread%", "OI", "Capital", "DivYld%", "DaysToEarnings", "Score"]
        show_cols = [c for c in show_cols if c in df_cc.columns]

        # Add earnings warning info box
        if "DaysToEarnings" in df_cc.columns:
            # Filter for non-null values and convert to numeric to handle None
            days_col = pd.to_numeric(df_cc["DaysToEarnings"], errors='coerce')
            earnings_nearby = df_cc[days_col.notna() & (days_col.abs() <= 14)]
            if not earnings_nearby.empty:
                st.warning(
                    f"⚠️ {len(earnings_nearby)} position(s) have earnings within 14 days. Review 'DaysToEarnings' column.")

        st.dataframe(df_cc[show_cols], use_container_width=True, height=520)

        # Add earnings legend
        st.caption(
            "**DaysToEarnings**: Days until next earnings (positive = future, negative = past, blank = unknown) | "
            "Data source: Yahoo Finance (Alpha Vantage fallback enabled only during order preview to preserve API quota)"
        )

# --- Tab 3: Collars ---
with tabs[2]:
    st.header("Collars (Stock + Short Call + Long Put)")
    if df_collar.empty:
        st.info("Run a scan or loosen Collar settings.")
    else:
        show_cols = ["Strategy", "Ticker", "Price", "Exp", "Days",
                     "CallStrike", "CallPrem", "PutStrike", "PutPrem", "NetCredit",
                     "ROI%_ann", "CallΔ", "PutΔ", "CallSpread%", "PutSpread%", "CallOI", "PutOI",
                     "Floor$/sh", "Cap$/sh", "PutCushionσ", "CallCushionσ", "Score"]
        show_cols = [c for c in show_cols if c in df_collar.columns]
        st.dataframe(df_collar[show_cols],
                     use_container_width=True, height=520)

# --- Tab 3: Iron Condor ---
with tabs[3]:
    st.header("Iron Condor (Sell Put Spread + Sell Call Spread)")
    if df_iron_condor.empty:
        st.info("Run a scan or loosen Iron Condor settings.")
    else:
        show_cols = ["Strategy", "Ticker", "Price", "Exp", "Days",
                     "PutShortStrike", "PutLongStrike", "PutSpreadCredit", "PutShortΔ",
                     "CallShortStrike", "CallLongStrike", "CallSpreadCredit", "CallShortΔ",
                     "NetCredit", "MaxLoss", "Capital", "ROI%_ann", "ROI%_excess_bills",
                     "BreakevenLower", "BreakevenUpper", "Range",
                     "PutCushionσ", "CallCushionσ", "ProbMaxProfit",
                     "PutSpread%", "CallSpread%", "PutShortOI", "CallShortOI", "IV", "Score"]
        show_cols = [c for c in show_cols if c in df_iron_condor.columns]
        st.dataframe(df_iron_condor[show_cols],
                     use_container_width=True, height=520)
        
        st.caption(
            "**PutShortΔ/CallShortΔ**: Delta of short strikes (target ~±0.16 = 84% POEW) | "
            "**MaxLoss**: Wing width − net credit | "
            "**ROI%_ann**: (Net credit / Max loss) × (365 / Days) × 100 | "
            "**ProbMaxProfit**: Probability both spreads expire worthless (approximate)"
        )

# --- Tab 4: Compare ---
with tabs[4]:
    st.header("Compare Projected Annualized ROIs (mid-price based)")
    if df_csp.empty and df_cc.empty and df_collar.empty and df_iron_condor.empty:
        st.info("No results yet. Run a scan.")
    else:
        pieces = []
        if not df_csp.empty:
            tmp = df_csp[["Strategy", "Ticker", "Exp", "Days",
                          "Strike", "Premium", "ROI%_ann", "Score"]].copy()
            tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + \
                " | K=" + tmp["Strike"].astype(str)
            pieces.append(tmp)
        if not df_cc.empty:
            tmp = df_cc[["Strategy", "Ticker", "Exp", "Days",
                         "Strike", "Premium", "ROI%_ann", "Score"]].copy()
            tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + \
                " | K=" + tmp["Strike"].astype(str)
            pieces.append(tmp)
        if not df_collar.empty:
            tmp = df_collar[["Strategy", "Ticker", "Exp", "Days", "CallStrike",
                             "PutStrike", "NetCredit", "ROI%_ann", "Score"]].copy()
            tmp = tmp.rename(columns={"CallStrike": "Strike"})
            tmp["Premium"] = tmp["NetCredit"]
            tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + \
                " | K=" + tmp["Strike"].astype(str)
            tmp["Strategy"] = "COLLAR"
            pieces.append(tmp)
        if not df_iron_condor.empty:
            tmp = df_iron_condor[["Strategy", "Ticker", "Exp", "Days", "CallShortStrike",
                                   "PutShortStrike", "NetCredit", "ROI%_ann", "Score"]].copy()
            tmp = tmp.rename(columns={"CallShortStrike": "Strike"})
            tmp["Premium"] = tmp["NetCredit"]
            tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + \
                " | CS=" + tmp["Strike"].astype(str) + " | PS=" + tmp["PutShortStrike"].astype(str)
            pieces.append(tmp)

        cmp_df = pd.concat(
            pieces, ignore_index=True) if pieces else pd.DataFrame()
        if cmp_df.empty:
            st.info("No comparable rows.")
        else:
            st.dataframe(cmp_df.sort_values(["Score", "ROI%_ann"], ascending=[False, False]),
                         use_container_width=True, height=520)
        
        # Trade Execution Module
        st.divider()
        with st.expander("🔧 Trade Execution (Test Mode)", expanded=False):
            st.info("📋 **Test Mode Enabled**: Orders will be exported to JSON files for review, not sent to Schwab API")
            
            # Safety Settings
            with st.expander("⚙️ Safety Settings", expanded=False):
                st.write("**Earnings Protection:**")
                earnings_warning_days = st.slider(
                    "Warn if earnings within X days",
                    min_value=0,
                    max_value=30,
                    value=14,
                    step=1,
                    help="Show warning if stock reports earnings within this many days (before or after). Set to 0 to disable."
                )
                st.caption(f"Current setting: {'Disabled' if earnings_warning_days == 0 else f'Warn if earnings within {earnings_warning_days} days'}")
                
                # Alpha Vantage API Status
                st.divider()
                st.write("**📊 Earnings Data Sources:**")
                st.info("💡 **Smart API Usage**: Alpha Vantage is only called when you preview/place orders, NOT during screening. This preserves your 25 calls/day quota.")
                
                try:
                    from providers.alpha_vantage import AlphaVantageClient
                    import os
                    
                    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
                    if api_key:
                        client = AlphaVantageClient(api_key)
                        remaining = client.get_remaining_calls()
                        used = 25 - remaining
                        
                        # Color code based on usage
                        if remaining > 15:
                            status_color = "🟢"
                            status_text = "Healthy"
                        elif remaining > 5:
                            status_color = "🟡"
                            status_text = "Moderate"
                        else:
                            status_color = "🔴"
                            status_text = "Limited"
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Screening", "Yahoo Finance Only", help="Free, unlimited - protects API quota")
                        with col2:
                            st.metric("Order Preview", "Yahoo → Alpha Vantage", help="Fallback enabled for accurate data")
                        
                        st.progress(used / 25, text=f"{status_color} **Alpha Vantage**: {used}/25 calls used today ({status_text})")
                        st.caption(f"✓ {remaining} API calls remaining • Resets daily • 24hr cache active")
                        
                        if remaining <= 5:
                            st.warning("⚠️ Alpha Vantage API limit nearly reached. Cache will be used for repeated symbols.")
                    else:
                        st.info("📡 Using Yahoo Finance only (Alpha Vantage not configured)")
                except ImportError:
                    st.info("📡 Using Yahoo Finance for earnings data")
                except Exception as e:
                    st.caption(f"⚠️ Could not check API status: {str(e)}")
            
            # Account Numbers Section
            st.subheader("📋 Step 1: Get Account Numbers")
            st.write("**Required**: Retrieve your encrypted account ID for order placement")
            st.caption("Schwab API requires encrypted account IDs (hashValue) for all trading operations.")
            
            if st.button("🔍 Retrieve Account Numbers", use_container_width=True):
                try:
                    from providers.schwab_trading import SchwabTrader
                    from providers.schwab import SchwabClient
                    
                    # Initialize Schwab client
                    if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE and PROVIDER == "schwab":
                        # Get the underlying schwab client
                        schwab_client = PROVIDER_INSTANCE.client if hasattr(PROVIDER_INSTANCE, 'client') else None
                        if schwab_client:
                            trader = SchwabTrader(dry_run=True, client=schwab_client)
                            accounts = trader.get_account_numbers()
                            
                            st.success(f"✅ Retrieved {len(accounts)} account(s)")
                            
                            for i, account in enumerate(accounts, 1):
                                with st.expander(f"Account #{i}: {account.get('accountNumber', 'Unknown')}", expanded=True):
                                    st.write("**Plain Text Account Number:**")
                                    st.code(account.get('accountNumber', 'N/A'))
                                    
                                    st.write("**Encrypted Hash Value (use this for orders):**")
                                    st.code(account.get('hashValue', 'N/A'))
                                    
                                    st.info("💡 Copy the hashValue above and set it as SCHWAB_ACCOUNT_ID environment variable")
                                    
                                    # Provide download button for account info
                                    account_json = json.dumps({
                                        "accountNumber": account.get('accountNumber'),
                                        "hashValue": account.get('hashValue'),
                                        "retrieved_at": datetime.now().isoformat()
                                    }, indent=2)
                                    
                                    st.download_button(
                                        label="⬇️ Download Account Info",
                                        data=account_json,
                                        file_name=f"schwab_account_{account.get('accountNumber', 'unknown')}.json",
                                        mime="application/json"
                                    )
                            
                            st.caption("📁 Account numbers also saved to ./trade_orders/account_numbers_*.json")
                        else:
                            st.error("❌ Schwab client not available. Check provider initialization.")
                    else:
                        st.error("❌ Schwab provider not active. Set OPTIONS_PROVIDER=schwab and configure credentials.")
                        
                except Exception as e:
                    st.error(f"❌ Error retrieving account numbers: {str(e)}")
                    import traceback
                    with st.expander("Error Details"):
                        st.code(traceback.format_exc())
            
            st.divider()
            st.subheader("📝 Step 2: Create Order")
            
            # Strategy selection for Trade Execution
            st.write("**Select Strategy:**")
            col_strat, col_info = st.columns([2, 3])
            
            with col_strat:
                available_strategies = []
                if not df_csp.empty:
                    available_strategies.append("Cash-Secured Put")
                if not df_cc.empty:
                    available_strategies.append("Covered Call")
                if not df_collar.empty:
                    available_strategies.append("Collar")
                if not df_iron_condor.empty:
                    available_strategies.append("Iron Condor")
                
                if not available_strategies:
                    st.warning("⚠️ No scan results available. Run a scan first.")
                    selected_strategy = None
                else:
                    strategy_map = {
                        "Cash-Secured Put": ("CSP", df_csp),
                        "Covered Call": ("CC", df_cc),
                        "Collar": ("COLLAR", df_collar),
                        "Iron Condor": ("IRON_CONDOR", df_iron_condor)
                    }
                    
                    selected_strategy_name = st.selectbox(
                        "Strategy Type:",
                        available_strategies,
                        help="Select the strategy type to trade"
                    )
                    
                    selected_strategy = strategy_map[selected_strategy_name][0]
                    strategy_df = strategy_map[selected_strategy_name][1]
            
            with col_info:
                if selected_strategy == "CSP":
                    st.info("💡 **CSP**: Sell put option, collect premium, prepared to buy stock at strike")
                elif selected_strategy == "CC":
                    st.info("💡 **CC**: Sell call option on owned stock, collect premium, capped upside")
                elif selected_strategy == "COLLAR":
                    st.info("💡 **Collar**: Sell call + buy put for downside protection, limited upside")
                elif selected_strategy == "IRON_CONDOR":
                    st.info("💡 **Iron Condor**: Sell put spread + call spread, profit if price stays in range")
            
            # Select a contract from the results
            if selected_strategy and not strategy_df.empty:
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # Create selection options from scan results
                    df_display = strategy_df.copy()
                    
                    # Build display string based on strategy type
                    if selected_strategy == "CSP":
                        df_display['display'] = (
                            df_display['Ticker'] + " " +
                            df_display['Exp'] + " $" +
                            df_display['Strike'].astype(str) + " PUT @ $" +
                            df_display['Premium'].round(2).astype(str)
                        )
                    elif selected_strategy == "CC":
                        df_display['display'] = (
                            df_display['Ticker'] + " " +
                            df_display['Exp'] + " $" +
                            df_display['Strike'].astype(str) + " CALL @ $" +
                            df_display['Premium'].round(2).astype(str)
                        )
                    elif selected_strategy == "COLLAR":
                        df_display['display'] = (
                            df_display['Ticker'] + " " +
                            df_display['Exp'] +
                            " CALL $" + df_display['CallStrike'].astype(str) +
                            " / PUT $" + df_display['PutStrike'].astype(str) +
                            " @ $" + df_display['NetCredit'].round(2).astype(str)
                        )
                    elif selected_strategy == "IRON_CONDOR":
                        df_display['display'] = (
                            df_display['Ticker'] + " " +
                            df_display['Exp'] +
                            " P: $" + df_display['LongPut'].astype(str) + "/" +
                            df_display['ShortPut'].astype(str) +
                            " C: $" + df_display['ShortCall'].astype(str) + "/" +
                            df_display['LongCall'].astype(str) +
                            " @ $" + df_display['NetCredit'].round(2).astype(str)
                        )
                    
                    selected_idx = st.selectbox(
                        "Select contract to trade:",
                        options=range(len(df_display)),
                        format_func=lambda i: df_display.iloc[i]['display']
                    )
                    
                    if selected_idx is not None:
                        selected = strategy_df[strategy_df.index == df_display.index[selected_idx]].iloc[0]
                        
                        # Re-fetch earnings date with Alpha Vantage enabled for accurate data
                        try:
                            import yfinance as yf
                            stock = yf.Ticker(selected['Ticker'])
                            fresh_earnings = get_earnings_date(stock, use_alpha_vantage=True)
                            if fresh_earnings:
                                fresh_days = (fresh_earnings - datetime.now(timezone.utc).date()).days
                                selected['DaysToEarnings'] = fresh_days
                                st.caption(f"✓ Earnings data refreshed with Alpha Vantage fallback")
                        except Exception as e:
                            st.caption(f"⚠️ Could not refresh earnings: {str(e)}")
                        
                        # Display selected contract details
                        st.write("**Selected Contract:**")
                        cols_info = st.columns(4)
                        cols_info[0].metric("Ticker", selected['Ticker'])
                        
                        if selected_strategy == "CSP":
                            cols_info[1].metric("Strike", f"${selected['Strike']:.2f}")
                            cols_info[2].metric("Premium", f"${selected['Premium']:.2f}")
                            cols_info[3].metric("ROI (ann)", f"{selected['ROI%_ann']:.1f}%")
                        elif selected_strategy == "CC":
                            cols_info[1].metric("Strike", f"${selected['Strike']:.2f}")
                            cols_info[2].metric("Premium", f"${selected['Premium']:.2f}")
                            cols_info[3].metric("ROI (ann)", f"{selected['ROI%_ann']:.1f}%")
                        elif selected_strategy == "COLLAR":
                            cols_info[1].metric("Call Strike", f"${selected['CallStrike']:.2f}")
                            cols_info[2].metric("Put Strike", f"${selected['PutStrike']:.2f}")
                            cols_info[3].metric("Net Credit", f"${selected['NetCredit']:.2f}")
                        elif selected_strategy == "IRON_CONDOR":
                            st.write("**Put Spread:**")
                            col_p1, col_p2 = st.columns(2)
                            col_p1.metric("Long Put", f"${selected['LongPut']:.2f}")
                            col_p2.metric("Short Put", f"${selected['ShortPut']:.2f}")
                            st.write("**Call Spread:**")
                            col_c1, col_c2 = st.columns(2)
                            col_c1.metric("Short Call", f"${selected['ShortCall']:.2f}")
                            col_c2.metric("Long Call", f"${selected['LongCall']:.2f}")
                            st.metric("Net Credit", f"${selected['NetCredit']:.2f}")
                
                with col2:
                    st.write("**Order Settings:**")
                    num_contracts = st.number_input(
                        "Contracts",
                        min_value=1,
                        max_value=100,
                        value=1,
                        step=1,
                        help="Number of contracts to trade"
                    )
                    
                    order_duration = st.selectbox(
                        "Duration",
                        options=["DAY", "GTC"],
                        index=0,
                        help="DAY = good for today, GTC = good till canceled"
                    )
                    
                    # Use appropriate price field based on strategy
                    if selected_strategy in ["CSP", "CC"]:
                        limit_price = st.number_input(
                            "Limit Price",
                            min_value=0.01,
                            value=float(selected['Premium']),
                            step=0.01,
                            format="%.2f",
                            help="Maximum price you're willing to receive"
                        )
                    elif selected_strategy in ["COLLAR", "IRON_CONDOR"]:
                        limit_price = st.number_input(
                            "Limit Price (Net Credit)",
                            min_value=0.01,
                            value=float(selected['NetCredit']),
                            step=0.01,
                            format="%.2f",
                            help="Minimum net credit you're willing to receive"
                        )
                
                # Order preview
                st.divider()
                st.write("**Order Preview:**")
                
                if selected_strategy == "CSP":
                    col_a, col_b, col_c = st.columns(3)
                    col_a.write(f"**Action:** SELL TO OPEN (Cash-Secured Put)")
                    col_b.write(f"**Collateral Required:** ${selected['Strike'] * 100 * num_contracts:,.2f}")
                    col_c.write(f"**Max Premium:** ${limit_price * 100 * num_contracts:,.2f}")
                elif selected_strategy == "CC":
                    col_a, col_b, col_c = st.columns(3)
                    col_a.write(f"**Action:** SELL TO OPEN (Covered Call)")
                    col_b.write(f"**Stock Required:** {100 * num_contracts} shares")
                    col_c.write(f"**Max Premium:** ${limit_price * 100 * num_contracts:,.2f}")
                elif selected_strategy == "COLLAR":
                    col_a, col_b, col_c = st.columns(3)
                    col_a.write(f"**Action:** SELL CALL + BUY PUT")
                    col_b.write(f"**Stock Required:** {100 * num_contracts} shares")
                    col_c.write(f"**Net Credit:** ${limit_price * 100 * num_contracts:,.2f}")
                elif selected_strategy == "IRON_CONDOR":
                    col_a, col_b = st.columns(2)
                    col_a.write(f"**Action:** 4-LEG CREDIT SPREAD")
                    put_width = selected['ShortPut'] - selected['LongPut']
                    call_width = selected['LongCall'] - selected['ShortCall']
                    max_width = max(put_width, call_width)
                    col_b.write(f"**Max Risk:** ${(max_width - selected['NetCredit']) * 100 * num_contracts:,.2f}")
                    st.write(f"**Max Credit:** ${limit_price * 100 * num_contracts:,.2f}")
                
                # Earnings Safety Check
                days_to_earnings = selected.get('DaysToEarnings', None)
                earnings_warning_threshold = earnings_warning_days  # Use setting from above
                
                if earnings_warning_threshold > 0 and days_to_earnings is not None and not pd.isna(days_to_earnings):
                    days_to_earnings = float(days_to_earnings)
                    
                    if abs(days_to_earnings) <= earnings_warning_threshold:
                        st.divider()
                        if days_to_earnings > 0:
                            st.error(f"⚠️ **EARNINGS WARNING**: {selected['Ticker']} reports earnings in **{int(days_to_earnings)} days**")
                        elif days_to_earnings < 0:
                            st.warning(f"⚠️ **EARNINGS NOTICE**: {selected['Ticker']} reported earnings **{int(abs(days_to_earnings))} days ago**")
                        else:
                            st.error(f"🚨 **EARNINGS TODAY**: {selected['Ticker']} reports earnings **TODAY**")
                        
                        with st.expander("📊 Why This Matters", expanded=False):
                            st.write("**Risks Around Earnings:**")
                            st.write("• **High IV**: Implied volatility inflates before earnings (IV crush after)")
                            st.write("• **Price Gaps**: Stock can gap up/down significantly on earnings news")
                            st.write("• **Assignment Risk**: Higher chance of early assignment if deep ITM")
                            st.write("• **Unpredictable**: Even good earnings can cause selloffs (and vice versa)")
                            st.write("")
                            st.write("**Recommendation:**")
                            st.write("• For beginners: **Avoid trading around earnings entirely**")
                            st.write("• For experienced: Only trade if you understand the risks")
                            st.write("• Consider waiting until after earnings are announced")
                
                # Buying Power Check button
                st.divider()
                col_check, col_preview, col_export = st.columns(3)
                
                with col_check:
                    if st.button("💰 Check Buying Power", use_container_width=True):
                        try:
                            from providers.schwab_trading import SchwabTrader
                            from providers.schwab import SchwabClient
                            
                            # Earnings safety check before proceeding
                            if earnings_warning_threshold > 0 and days_to_earnings is not None and not pd.isna(days_to_earnings):
                                days_val = float(days_to_earnings)
                                if abs(days_val) <= earnings_warning_threshold:
                                    st.warning(f"⚠️ Earnings in {int(abs(days_val))} days - proceed with caution")
                            
                            # Check if Schwab provider is active
                            if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE and PROVIDER == "schwab":
                                schwab_client = PROVIDER_INSTANCE.client if hasattr(PROVIDER_INSTANCE, 'client') else None
                                if schwab_client:
                                    trader = SchwabTrader(dry_run=False, client=schwab_client)
                                    
                                    # Calculate required buying power based on strategy
                                    if selected_strategy == "CSP":
                                        required = selected['Strike'] * 100 * num_contracts
                                    elif selected_strategy == "CC":
                                        required = 0  # No cash required, just need stock ownership
                                    elif selected_strategy == "COLLAR":
                                        # Cost of protective put minus call premium
                                        required = max(0, (selected.get('PutPremium', 0) - selected.get('CallPremium', 0)) * 100 * num_contracts)
                                    elif selected_strategy == "IRON_CONDOR":
                                        put_width = selected['ShortPut'] - selected['LongPut']
                                        call_width = selected['LongCall'] - selected['ShortCall']
                                        max_width = max(put_width, call_width)
                                        required = (max_width - selected['NetCredit']) * 100 * num_contracts
                                    
                                    with st.spinner("Checking account..."):
                                        result = trader.check_buying_power(required)
                                    
                                    if result['sufficient']:
                                        st.success(f"✅ Sufficient buying power!")
                                        st.metric("Available", f"${result['available']:,.2f}")
                                        st.metric("Required", f"${result['required']:,.2f}")
                                        st.metric("Remaining", f"${result['available'] - result['required']:,.2f}")
                                    else:
                                        st.error(f"❌ Insufficient buying power")
                                        st.metric("Available", f"${result['available']:,.2f}")
                                        st.metric("Required", f"${result['required']:,.2f}")
                                        st.metric("Shortfall", f"${result['shortfall']:,.2f}")
                                    
                                    with st.expander("📊 Account Details"):
                                        st.write(f"**Account Type:** {result['account_type']}")
                                        st.write(f"**Option Buying Power:** ${result['option_buying_power']:,.2f}")
                                        st.write(f"**Total Buying Power:** ${result['total_buying_power']:,.2f}")
                                        st.write(f"**Cash Balance:** ${result['cash_balance']:,.2f}")
                                else:
                                    st.error("❌ Schwab client not available")
                            else:
                                st.error("❌ Schwab provider not active")
                        except Exception as e:
                            st.error(f"❌ Error checking buying power: {str(e)}")
                            import traceback
                            with st.expander("Error Details"):
                                st.code(traceback.format_exc())
                
                with col_preview:
                    if st.button("🔍 Preview Order with Schwab API", use_container_width=True):
                        try:
                            from providers.schwab_trading import SchwabTrader
                            from providers.schwab import SchwabClient
                            
                            # Earnings safety check before proceeding
                            if earnings_warning_threshold > 0 and days_to_earnings is not None and not pd.isna(days_to_earnings):
                                days_val = float(days_to_earnings)
                                if abs(days_val) <= earnings_warning_threshold:
                                    st.warning(f"⚠️ Earnings in {int(abs(days_val))} days - proceed with caution")
                            
                            # Check if Schwab provider is active
                            if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE and PROVIDER == "schwab":
                                # Get the underlying schwab client
                                schwab_client = PROVIDER_INSTANCE.client if hasattr(PROVIDER_INSTANCE, 'client') else None
                                if schwab_client:
                                    # Initialize trader (NOT dry-run, we want to call API)
                                    trader = SchwabTrader(dry_run=False, client=schwab_client)
                                    
                                    # Create order based on strategy
                                    if selected_strategy == "CSP":
                                        order = trader.create_cash_secured_put_order(
                                            symbol=selected['Ticker'],
                                            expiration=selected['Exp'],
                                            strike=float(selected['Strike']),
                                            quantity=int(num_contracts),
                                            limit_price=float(limit_price),
                                            duration=order_duration
                                        )
                                    elif selected_strategy == "CC":
                                        order = trader.create_covered_call_order(
                                            symbol=selected['Ticker'],
                                            expiration=selected['Exp'],
                                            strike=float(selected['Strike']),
                                            quantity=int(num_contracts),
                                            limit_price=float(limit_price),
                                            duration=order_duration
                                        )
                                    elif selected_strategy == "COLLAR":
                                        order = trader.create_collar_order(
                                            symbol=selected['Ticker'],
                                            expiration=selected['Exp'],
                                            call_strike=float(selected['CallStrike']),
                                            put_strike=float(selected['PutStrike']),
                                            quantity=int(num_contracts),
                                            limit_price=float(limit_price),
                                            duration=order_duration
                                        )
                                    elif selected_strategy == "IRON_CONDOR":
                                        order = trader.create_iron_condor_order(
                                            symbol=selected['Ticker'],
                                            expiration=selected['Exp'],
                                            long_put_strike=float(selected['LongPut']),
                                            short_put_strike=float(selected['ShortPut']),
                                            short_call_strike=float(selected['ShortCall']),
                                            long_call_strike=float(selected['LongCall']),
                                            quantity=int(num_contracts),
                                            limit_price=float(limit_price),
                                            duration=order_duration
                                        )
                                    
                                    # Validate order first
                                    validation = trader.validate_order(order)
                                    
                                    if not validation['valid']:
                                        st.error("❌ Order validation failed:")
                                        for error in validation['errors']:
                                            st.error(f"  • {error}")
                                    else:
                                        # Call preview API
                                        with st.spinner("Calling Schwab API..."):
                                            preview_result = trader.preview_order(order)
                                        
                                        if preview_result['status'] == 'preview_success':
                                            st.success("✅ Order preview received from Schwab!")
                                            
                                            # Display preview details
                                            with st.expander("📊 Schwab Preview Response", expanded=True):
                                                preview_data = preview_result['preview']
                                                
                                                # Display key metrics if available
                                                if isinstance(preview_data, dict):
                                                    st.write("**Order Details:**")
                                                    
                                                    # Commission
                                                    if 'commission' in preview_data:
                                                        st.metric("Commission", f"${preview_data['commission']:.2f}")
                                                    
                                                    # Total cost/credit
                                                    if 'estimatedTotalAmount' in preview_data:
                                                        st.metric("Estimated Credit", f"${preview_data['estimatedTotalAmount']:.2f}")
                                                    
                                                    # Buying power effect
                                                    if 'buyingPowerEffect' in preview_data:
                                                        st.metric("Buying Power Impact", f"${preview_data['buyingPowerEffect']:.2f}")
                                                    
                                                    # Margin requirement
                                                    if 'marginRequirement' in preview_data:
                                                        st.metric("Margin Requirement", f"${preview_data['marginRequirement']:.2f}")
                                                    
                                                    # Warnings
                                                    if 'warnings' in preview_data and preview_data['warnings']:
                                                        st.warning("⚠️ **Warnings:**")
                                                        for warning in preview_data['warnings']:
                                                            st.write(f"• {warning}")
                                                    
                                                    # Full response
                                                    st.write("**Full Response:**")
                                                    st.json(preview_data)
                                                else:
                                                    st.json(preview_data)
                                            
                                            st.caption(f"📁 Preview saved to: {preview_result['filepath']}")
                                        else:
                                            st.error(f"❌ Preview failed: {preview_result.get('message', 'Unknown error')}")
                                else:
                                    st.error("❌ Schwab client not available. Check provider initialization.")
                            else:
                                st.error("❌ Schwab provider not active. Set OPTIONS_PROVIDER=schwab and configure credentials.")
                                
                        except Exception as e:
                            st.error(f"❌ Error previewing order: {str(e)}")
                            import traceback
                            with st.expander("Error Details"):
                                st.code(traceback.format_exc())
                
                # Generate order button (dry-run export)
                with col_export:
                    if st.button("📥 Generate Order File", type="primary", use_container_width=True):
                        try:
                            from providers.schwab_trading import SchwabTrader, format_order_summary
                            
                            # Earnings safety check before proceeding
                            if earnings_warning_threshold > 0 and days_to_earnings is not None and not pd.isna(days_to_earnings):
                                days_val = float(days_to_earnings)
                                if abs(days_val) <= earnings_warning_threshold:
                                    st.warning(f"⚠️ Note: Earnings in {int(abs(days_val))} days")
                            
                            # Initialize trader in dry-run mode
                            trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
                            
                            # Create order based on strategy
                            if selected_strategy == "CSP":
                                order = trader.create_cash_secured_put_order(
                                    symbol=selected['Ticker'],
                                    expiration=selected['Exp'],
                                    strike=float(selected['Strike']),
                                    quantity=int(num_contracts),
                                    limit_price=float(limit_price),
                                    duration=order_duration
                                )
                                strategy_type = "csp"
                            elif selected_strategy == "CC":
                                order = trader.create_covered_call_order(
                                    symbol=selected['Ticker'],
                                    expiration=selected['Exp'],
                                    strike=float(selected['Strike']),
                                    quantity=int(num_contracts),
                                    limit_price=float(limit_price),
                                    duration=order_duration
                                )
                                strategy_type = "covered_call"
                            elif selected_strategy == "COLLAR":
                                order = trader.create_collar_order(
                                    symbol=selected['Ticker'],
                                    expiration=selected['Exp'],
                                    call_strike=float(selected['CallStrike']),
                                    put_strike=float(selected['PutStrike']),
                                    quantity=int(num_contracts),
                                    limit_price=float(limit_price),
                                    duration=order_duration
                                )
                                strategy_type = "collar"
                            elif selected_strategy == "IRON_CONDOR":
                                order = trader.create_iron_condor_order(
                                    symbol=selected['Ticker'],
                                    expiration=selected['Exp'],
                                    long_put_strike=float(selected['LongPut']),
                                    short_put_strike=float(selected['ShortPut']),
                                    short_call_strike=float(selected['ShortCall']),
                                    long_call_strike=float(selected['LongCall']),
                                    quantity=int(num_contracts),
                                    limit_price=float(limit_price),
                                    duration=order_duration
                                )
                                strategy_type = "iron_condor"
                            
                            # Validate order
                            validation = trader.validate_order(order)
                            
                            if not validation['valid']:
                                st.error("❌ Order validation failed:")
                                for error in validation['errors']:
                                    st.error(f"  • {error}")
                            else:
                                # Show warnings if any
                                if validation['warnings']:
                                    for warning in validation['warnings']:
                                        st.warning(f"⚠️ {warning}")
                                
                                # Submit order (exports to file)
                                metadata = {
                                    "scanner_data": {
                                        "strategy": selected_strategy,
                                        "otm_percent": float(selected.get('OTM%', 0)) if 'OTM%' in selected else None,
                                        "roi_annual": float(selected.get('ROI%_ann', 0)) if 'ROI%_ann' in selected else None,
                                        "iv": float(selected.get('IV', 0)) if 'IV' in selected else None,
                                        "delta": float(selected.get('Δ', 0)) if 'Δ' in selected else None,
                                        "theta": float(selected.get('Θ', 0)) if 'Θ' in selected else None,
                                        "open_interest": int(selected.get('OI', 0)) if 'OI' in selected else None,
                                        "days_to_exp": int(selected.get('Days', 0)) if 'Days' in selected else None,
                                        "net_credit": float(selected.get('NetCredit', 0)) if 'NetCredit' in selected else None
                                    },
                                    "source": f"strategy_lab_{strategy_type}_scanner"
                                }
                                
                                result = trader.submit_order(order, strategy_type=strategy_type, metadata=metadata)
                                
                                if result['status'] == 'exported':
                                    st.success(f"✅ Order exported successfully!")
                                    st.code(result['filepath'], language=None)
                                    
                                    # Show order summary
                                    with st.expander("📄 Order Details"):
                                        st.text(format_order_summary(order))
                                        st.json(order)
                                    
                                    # Provide download button
                                    with open(result['filepath'], 'r') as f:
                                        order_json = f.read()
                                    
                                    st.download_button(
                                        label="⬇️ Download Order File",
                                        data=order_json,
                                        file_name=result['filepath'].split('/')[-1],
                                        mime="application/json"
                                    )
                                else:
                                    st.error(f"❌ Failed to export order: {result.get('message', 'Unknown error')}")
                        
                        except Exception as e:
                            st.error(f"❌ Error generating order: {str(e)}")
                            import traceback
                            with st.expander("Error Details"):
                                st.code(traceback.format_exc())
            else:
                st.info("No contracts available. Run a scan first.")

# --- Tab 5: Risk (Monte Carlo) ---
with tabs[5]:
    st.header("Risk (Monte Carlo) — Uses the global selection above")
    st.caption(
        "Simulates terminal prices via GBM and computes per-contract P&L and annualized ROI. Educational only.")

    # Controls (no per-tab strategy/contract pickers)
    colB, colC, colD = st.columns(3)
    with colB:
        paths = st.slider("Paths", 5000, 200000, 50000, step=5000)
    with colC:
        # Get strategy choice first to set appropriate drift default
        strat_choice_preview, _ = _get_selected_row()
        # CSP: 0% drift (cash position, no equity exposure)
        # CC/Collar: 7% drift (realistic equity market assumption)
        default_drift = 0.00 if strat_choice_preview == "CSP" else 0.07
        
        mc_drift = st.number_input(
            "Drift (annual, decimal)", 
            value=default_drift, 
            step=0.01, 
            format="%.2f", 
            key="mc_drift_input",
            help="Expected annual return: 0% for CSP (cash-secured), 7% for CC/Collar (equity drift)")
    with colD:
        seed = st.number_input("Seed (0 = random)", value=0,
                               step=1, min_value=0, key="mc_seed_input")
        seed = None if seed == 0 else int(seed)

    strat_choice, row = _get_selected_row()
    if row is None:
        st.info("Select a strategy/contract above and ensure scans have results.")
    else:
        # Price Override Section
        st.divider()
        with st.expander("💰 Price Override (for live execution)", expanded=False):
            st.caption(
                "Override stock price and/or premium if market has moved since scan")

            original_price = float(row["Price"])
            original_premium = float(
                row.get("Premium", row.get("CallPrem", 0.0)))

            col1, col2, col3 = st.columns(3)
            with col1:
                use_custom_price = st.checkbox(
                    "Override stock price",
                    value=False,
                    key="use_custom_stock_price_mc",
                    help="Use current market price instead of scan price"
                )
                if use_custom_price:
                    custom_stock_price = st.number_input(
                        f"Current stock price (scan: ${original_price:.2f})",
                        value=original_price,
                        min_value=0.01,
                        step=0.01,
                        format="%.2f",
                        key="custom_stock_price_mc"
                    )
                    price_change_pct = (
                        (custom_stock_price - original_price) / original_price) * 100
                    st.caption(f"Change: {price_change_pct:+.2f}%")
                else:
                    custom_stock_price = original_price

            with col2:
                use_custom_premium = st.checkbox(
                    "Override premium",
                    value=False,
                    key="use_custom_premium_mc",
                    help="Use current option premium quote"
                )
                if use_custom_premium:
                    custom_premium = st.number_input(
                        f"Current premium (scan: ${original_premium:.2f})",
                        value=original_premium,
                        min_value=0.01,
                        step=0.01,
                        format="%.2f",
                        key="custom_premium_value_mc"
                    )
                    premium_change_pct = (
                        (custom_premium - original_premium) / original_premium) * 100
                    st.caption(f"Change: {premium_change_pct:+.2f}%")
                else:
                    custom_premium = original_premium

            with col3:
                if use_custom_price or use_custom_premium:
                    st.markdown("**Updated Metrics:**")
                    if strat_choice == "CSP":
                        new_otm = (
                            (custom_stock_price - float(row["Strike"])) / custom_stock_price) * 100
                        new_roi = (custom_premium / float(row["Strike"])) * (
                            365.0 / max(int(row.get("Days", 30)), 1)) * 100
                        st.metric("OTM%", f"{new_otm:.2f}%",
                                  delta=f"{new_otm - float(row.get('OTM%', 0)):.2f}%")
                        st.metric("ROI% (ann)", f"{new_roi:.2f}%",
                                  delta=f"{new_roi - float(row.get('ROI%_ann', 0)):.2f}%")
                    elif strat_choice == "CC":
                        new_otm = (
                            (float(row["Strike"]) - custom_stock_price) / custom_stock_price) * 100
                        new_roi = (custom_premium / custom_stock_price) * \
                            (365.0 / max(int(row.get("Days", 30)), 1)) * 100
                        st.metric("OTM%", f"{new_otm:.2f}%",
                                  delta=f"{new_otm - float(row.get('OTM%', 0)):.2f}%")
                        st.metric("ROI% (ann)", f"{new_roi:.2f}%",
                                  delta=f"{new_roi - float(row.get('ROI%_ann', 0)):.2f}%")

        st.divider()

        # Guard against degenerate T=0 simulations by using at least 1 day in MC
        row_days = int(row.get("Days", 0))
        days_for_mc = max(1, row_days)
        if row_days <= 0:
            st.caption(
                "Note: Selected contract has 0 DTE — using 1 day for Monte Carlo to avoid degenerate paths.")

        # Use custom prices if overridden, otherwise use scan prices
        execution_price = custom_stock_price if 'custom_stock_price' in locals() else original_price
        execution_premium = custom_premium if 'custom_premium' in locals() else original_premium

        # Build MC params per strategy
        if strat_choice == "CSP":
            iv_raw = float(row.get("IV", float("nan")))
            iv = (iv_raw / 100.0) if (iv_raw ==
                                      iv_raw and iv_raw > 0.0) else 0.20
            params = dict(
                S0=execution_price,  # Use overridden price
                days=int(days_for_mc),
                iv=iv,
                Kp=float(row["Strike"]),
                put_premium=execution_premium,  # Use overridden premium
                div_ps_annual=0.0,
            )
            mc = mc_pnl("CSP", params, n_paths=int(paths), mu=float(
                mc_drift), seed=seed, rf=float(t_bill_yield))

            # CSP-specific breach diagnostics (how often S_T < K?)
            try:
                S0 = float(params["S0"])
                Kp = float(params["Kp"])
                T = float(params["days"]) / 365.0
                r = float(t_bill_yield)
                d1, d2 = _bs_d1_d2(S0, Kp, r, iv, T, 0.0)
                poew_est = _norm_cdf(d2) if d2 == d2 else float("nan")
                breach_est = (
                    1.0 - poew_est) if poew_est == poew_est else float("nan")
                S_T = mc.get("S_T")
                if isinstance(S_T, np.ndarray) and S_T.size > 0:
                    breach_obs = float(np.mean(S_T < Kp))
                    breach_cnt = int(np.sum(S_T < Kp))
                else:
                    breach_obs, breach_cnt = float("nan"), 0

                info = f"Breach prob (est) ~ {breach_est:.4%} ; observed in MC: {breach_obs:.4%} ({breach_cnt} paths)" if (
                    breach_est == breach_est and breach_obs == breach_obs) else "Breach diagnostics unavailable"
                st.caption(info)
                if breach_obs == 0.0 and (breach_est == breach_est) and breach_est > 0.0:
                    st.info("MC didn’t sample any breaches. Deep OTM + short tenor can make breaches extremely rare. Increase paths, choose a closer strike, increase IV, or extend tenor to see left-tail outcomes.")
            except Exception:
                pass
        elif strat_choice == "CC":
            iv_raw = float(row.get("IV", float("nan")))
            iv = (iv_raw / 100.0) if (iv_raw ==
                                      iv_raw and iv_raw > 0.0) else 0.20
            div_ps_annual = float(
                row.get("DivAnnualPS", 0.0)) if "DivAnnualPS" in row else 0.0
            params = dict(
                S0=execution_price,  # Use overridden price
                days=int(days_for_mc),
                iv=iv,
                Kc=float(row["Strike"]),
                call_premium=execution_premium,  # Use overridden premium
                div_ps_annual=div_ps_annual,
            )
            mc = mc_pnl("CC", params, n_paths=int(paths),
                        mu=float(mc_drift), seed=seed)
        elif strat_choice == "COLLAR":
            iv = 0.20  # conservative default
            div_ps_annual = float(
                row.get("DivAnnualPS", 0.0)) if "DivAnnualPS" in row else 0.0
            params = dict(
                S0=execution_price,  # Use overridden price
                days=int(days_for_mc),
                iv=iv,
                Kc=float(row["CallStrike"]),
                call_premium=float(row.get("CallPrem", 0.0)),
                Kp=float(row["PutStrike"]),
                put_premium=float(row.get("PutPrem", 0.0)),
                div_ps_annual=div_ps_annual,
            )
            mc = mc_pnl("COLLAR", params, n_paths=int(
                paths), mu=float(mc_drift), seed=seed)
        else:  # IRON_CONDOR
            # Extract IV from Iron Condor row
            iv = float(row.get("IV", 20.0)) / 100.0  # Convert from percentage to decimal
            
            # Build params dict with all required Iron Condor parameters
            params = dict(
                S0=execution_price,  # Use overridden price
                days=int(days_for_mc),
                iv=iv,
                put_short_strike=float(row["PutShortStrike"]),
                put_long_strike=float(row["PutLongStrike"]),
                call_short_strike=float(row["CallShortStrike"]),
                call_long_strike=float(row["CallLongStrike"]),
                net_credit=float(row["NetCredit"])
            )
            mc = mc_pnl("IRON_CONDOR", params, n_paths=int(
                paths), mu=float(mc_drift), seed=seed)

        # Render outputs (only if mc simulation was run)
        if mc is not None:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Expected P&L / contract", f"${mc['pnl_expected']:,.0f}")
            c2.metric("P&L (P5 / P50 / P95)",
                      f"${mc['pnl_p5']:,.0f} / ${mc['pnl_p50']:,.0f} / ${mc['pnl_p95']:,.0f}")
            c3.metric("Worst path", f"${mc['pnl_min']:,.0f}")
            c4.metric("Collateral (capital)", f"${mc['collateral']:,.0f}")

            pnl = mc["pnl_paths"]
            bins = np.histogram_bin_edges(pnl, bins="auto")
            hist, edges = np.histogram(pnl, bins=bins)
            chart_df = pd.DataFrame(
                {"pnl": (edges[:-1] + edges[1:]) / 2.0, "count": hist})
            base_chart = alt.Chart(chart_df).mark_bar().encode(
                x=alt.X("pnl:Q", title="P&L per contract (USD)"),
                y=alt.Y("count:Q", title="Frequency"),
                tooltip=["pnl", "count"],
            )
            st.altair_chart(base_chart, use_container_width=True)

            def pct(x): return f"{x*100:.2f}%"
            roi_rows = [
                {"Scenario": "Expected", "Annualized ROI": pct(
                    mc["roi_ann_expected"])},
                {"Scenario": "P5 (bear)", "Annualized ROI": pct(mc["roi_ann_p5"])},
                {"Scenario": "P50 (median)", "Annualized ROI": pct(
                    mc["roi_ann_p50"])},
                {"Scenario": "P95 (bull)", "Annualized ROI": pct(
                    mc["roi_ann_p95"])},
            ]
            st.subheader("Annualized ROI (from MC)")
            st.dataframe(pd.DataFrame(roi_rows), use_container_width=True)

            st.subheader("At‑a‑Glance: Trade Summary & Risk")
            summary_rows = [
                {"Scenario": "P5 (bear)", "P&L ($/contract)":
                 f"{mc['pnl_p5']:,.0f}", "Annualized ROI": pct(mc["roi_ann_p5"])},
                {"Scenario": "P50 (median)", "P&L ($/contract)":
                 f"{mc['pnl_p50']:,.0f}", "Annualized ROI": pct(mc["roi_ann_p50"])},
                {"Scenario": "P95 (bull)", "P&L ($/contract)":
                 f"{mc['pnl_p95']:,.0f}", "Annualized ROI": pct(mc["roi_ann_p95"])},
                {"Scenario": "Expected",
                    "P&L ($/contract)": f"{mc['pnl_expected']:,.0f}", "Annualized ROI": pct(mc["roi_ann_expected"])},
            ]
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

# --- Tab 6: Playbook ---
with tabs[6]:
    st.header("Best‑Practice Playbook")
    st.write("These are practical guardrails you can toggle against in the scanner.")
    for name in ["CSP", "CC", "COLLAR", "IRON_CONDOR"]:
        with st.expander(f"{name} — tips"):
            tips = best_practices(name)
            for t in tips:
                st.markdown(f"- {t}")

# --- Tab 7: Plan & Runbook ---
with tabs[7]:
    st.header("Plan & Runbook — Uses the global selection above")
    st.caption(
        "We’ll check the globally selected contract/structure against best practices and generate order tickets.")

    colB, colC = st.columns(2)
    with colB:
        contracts = st.number_input(
            "Contracts", min_value=1, value=1, step=1, key="rb_contracts")
    with colC:
        capture_pct = st.slider("Profit capture target",
                                0.50, 0.90, 0.70, 0.05, key="rb_capture")

    strat_choice_rb, row = _get_selected_row()
    if row is None:
        st.info("Select a strategy/contract above and ensure scans have results.")
    else:
        base = {"CSP": df_csp, "CC": df_cc,
                "COLLAR": df_collar, "IRON_CONDOR": df_iron_condor}[strat_choice_rb]

        # Inputs for checks
        thresholds = dict(
            min_oi=int(_safe_int(st.session_state.get("min_oi", 200))),
            max_spread=float(st.session_state.get("max_spread", 10.0)),
            min_cushion=float(st.session_state.get("min_cushion", 1.0)),
            min_otm_csp=float(st.session_state.get("min_otm_csp", 10.0)),
            min_otm_cc=float(st.session_state.get("min_otm_cc", 2.0)),
        )

        # Dividend yield proxy (q) for deltas
        try:
            div_y = float(row.get("DivYld%", 0.0)) / 100.0
        except Exception:
            div_y = 0.0

        fit_df, flags = evaluate_fit(
            strat_choice_rb, row, thresholds,
            risk_free=float(risk_free),
            div_y=float(div_y),
            bill_yield=float(t_bill_yield),
        )
        st.subheader("Best‑Practice Fit")
        st.dataframe(fit_df, use_container_width=True)

        # Extra options for CC runbook (do you already own shares?)
        holds_shares = False
        if strat_choice_rb == "CC":
            holds_shares = st.checkbox(
                "I already hold the required shares", value=False, key="rb_hold_shares")

        runbook_text = build_runbook(
            strat_choice_rb, row,
            contracts=int(contracts),
            capture_pct=float(capture_pct),
            risk_rules={},
            holds_shares=bool(holds_shares),
        )

        st.subheader("Trade Runbook")
        st.code(runbook_text, language="markdown")

        dl_name = f"runbook_{strat_choice_rb}_{row['Ticker']}_{row['Exp']}.txt".replace(
            " ", "")
        st.download_button(
            "⬇️ Download Runbook (.txt)",
            data=runbook_text.encode("utf-8"),
            file_name=dl_name,
            mime="text/plain",
            key="rb_download_btn",
        )

        warn_msgs = []
        if flags["assignment_risk"]:
            warn_msgs.append(
                "High early assignment risk around ex‑div on CC/Collar — consider rolling or skipping that expiry.")
        if flags["liquidity_warn"]:
            warn_msgs.append(
                "Liquidity sub‑par (OI/spread). Consider a different strike/expiry/ticker.")
        if flags["tenor_warn"]:
            warn_msgs.append(
                "Tenor outside the sweet spot. Consider 21–45 DTE (CSP/CC) or 30–60 DTE (Collar).")
        if flags["excess_negative"]:
            warn_msgs.append(
                "Excess ROI vs T‑bills is negative. Consider passing on this trade.")
        if flags["cushion_low"]:
            warn_msgs.append(
                "Sigma cushion is thin (< 1.0σ). Consider moving further OTM or extending tenor.")
        if warn_msgs:
            st.subheader("Notes & Cautions")
            for m in warn_msgs:
                st.markdown(f"- {m}")

# --- Tab 8: Stress Test ---
with tabs[8]:
    st.header("Stress Test — Uses the global selection above")
    st.caption(
        "Apply price and IV shocks, reduce time by a horizon, and see leg-level and total P&L.")

    col2, col3, col4 = st.columns(3)
    with col2:
        horizon_days = st.number_input(
            "Horizon (days)", min_value=0, value=1, step=1, key="stress_horizon_days")
    with col3:
        iv_dn_pp = st.number_input(
            "IV shift on DOWN shocks (vol pts)", value=10.0, step=1.0, key="stress_iv_dn_pp")
    with col4:
        iv_up_pp = st.number_input(
            "IV shift on UP shocks (vol pts)", value=0.0, step=1.0, key="stress_iv_up_pp")

    shocks_text = st.text_input("Price shocks (%) comma-separated",
                                value="-20,-10,-5,0,5,10,20", key="stress_shocks_text")

    def _parse_shocks(s):
        out = []
        for tok in s.split(","):
            tok = tok.strip()
            if not tok:
                continue
            try:
                out.append(float(tok))
            except Exception:
                pass
        return out or [0.0]

    shocks = _parse_shocks(shocks_text)

    strat_st, row = _get_selected_row()
    if row is None:
        st.info("Select a strategy/contract above and ensure scans have results.")
    else:
        try:
            div_y = float(row.get("DivYld%", 0.0)) / 100.0
        except Exception:
            div_y = 0.0

        iv_down_shift = float(iv_dn_pp) / 100.0
        iv_up_shift = float(iv_up_pp) / 100.0

        df_stress = run_stress(
            strat_st, row,
            shocks_pct=shocks,
            horizon_days=int(horizon_days),
            r=float(risk_free),
            div_y=float(div_y),
            iv_down_shift=iv_down_shift,
            iv_up_shift=iv_up_shift,
        )

        st.subheader("Stress Table")
        st.dataframe(df_stress, use_container_width=True)

        st.subheader("P&L vs Price Shock")
        chart = alt.Chart(df_stress).mark_line(point=True).encode(
            x=alt.X("Shock%:Q", title="Shock (%)"),
            y=alt.Y("Total_P&L:Q", title="Total P&L per contract (USD)"),
            tooltip=list(df_stress.columns),
        )
        st.altair_chart(chart, use_container_width=True)

        worst = float(df_stress["Total_P&L"].min())
        best = float(df_stress["Total_P&L"].max())
        st.caption(
            f"Worst among tests: ${worst:,.0f} • Best among tests: ${best:,.0f}")

st.caption("This tool is for education only. Options involve risk and are not suitable for all investors.")

# --- Tab 9: Overview ---
with tabs[9]:
    st.header("Quick Overview — Strategy & Risk")
    st.caption(
        "A concise summary for the globally selected contract/structure, with tail‑loss probability.")

    strat_choice, row = _get_selected_row()
    if row is None:
        st.info("Select a strategy/contract above and ensure scans have results.")
    else:
        # Assemble a compact summary of the structure
        days = int(_safe_int(row.get("Days", 0), 0))
        price = float(_safe_float(row.get("Price")))
        iv_raw = float(_safe_float(row.get("IV", float("nan"))))
        iv_dec = (iv_raw / 100.0) if (iv_raw ==
                                      iv_raw and iv_raw > 0.0) else float("nan")

        if strat_choice == "CSP":
            strike = float(_safe_float(row.get("Strike")))
            prem = float(_safe_float(row.get("Premium")))
            collateral = strike * 100.0

            # Calculate profit capture targets
            target_50_pct = prem * 0.50
            target_75_pct = prem * 0.25

            base_rows = [
                ("Strategy", "CSP"),
                ("Ticker", row.get("Ticker")),
                ("Price", f"${price:,.2f}"),
                ("Strike", f"{strike:,.2f}"),
                ("Exp", row.get("Exp")),
                ("Days", f"{days}"),
                ("Premium", f"${prem:,.2f}"),
                ("Collateral", f"${collateral:,.0f}"),
                ("IV", f"{iv_raw:.2f}%" if iv_raw ==
                 iv_raw and iv_raw > 0 else "n/a"),
                ("POEW", f"{row.get('POEW'):.3f}" if row.get(
                    'POEW') == row.get('POEW') else "n/a"),
                ("Cushionσ", f"{row.get('CushionSigma'):.2f}" if row.get(
                    'CushionSigma') == row.get('CushionSigma') else "n/a"),
                ("Theta/Gamma", f"{row.get('Theta/Gamma'):.2f}" if row.get(
                    'Theta/Gamma') == row.get('Theta/Gamma') else "n/a"),
                ("—", "—"),
                ("Exit: 50% profit",
                 f"Close when mark ≤ ${target_50_pct:.2f}"),
                ("Exit: 75% profit",
                 f"Close when mark ≤ ${target_75_pct:.2f}"),
            ]
            st.subheader("Contract summary")
            st.table(pd.DataFrame(base_rows, columns=["Field", "Value"]))

            # Monte Carlo quick run (independent of MC tab controls)
            paths = 50000
            days_for_mc = max(1, days)
            iv_for_calc = iv_dec if (
                iv_dec == iv_dec and iv_dec > 0.0) else 0.20
            params = dict(S0=price, days=days_for_mc, iv=iv_for_calc,
                          Kp=strike, put_premium=prem, div_ps_annual=0.0)
            mc = mc_pnl("CSP", params, n_paths=int(paths),
                        mu=0.0, seed=None, rf=float(t_bill_yield))

        elif strat_choice == "CC":
            strike = float(_safe_float(row.get("Strike")))
            prem = float(_safe_float(row.get("Premium")))
            capital = price * 100.0
            div_ps_annual = float(_safe_float(row.get("DivAnnualPS", 0.0)))

            # Calculate profit capture targets
            target_50_pct = prem * 0.50
            target_75_pct = prem * 0.25

            base_rows = [
                ("Strategy", "CC"),
                ("Ticker", row.get("Ticker")),
                ("Price", f"${price:,.2f}"),
                ("Strike", f"{strike:,.2f}"),
                ("Exp", row.get("Exp")),
                ("Days", f"{days}"),
                ("Premium", f"${prem:,.2f}"),
                ("Capital", f"${capital:,.0f}"),
                ("IV", f"{iv_raw:.2f}%" if iv_raw ==
                 iv_raw and iv_raw > 0 else "n/a"),
                ("POEC", f"{row.get('POEC'):.3f}" if row.get(
                    'POEC') == row.get('POEC') else "n/a"),
                ("Cushionσ", f"{row.get('CushionSigma'):.2f}" if row.get(
                    'CushionSigma') == row.get('CushionSigma') else "n/a"),
                ("Theta/Gamma", f"{row.get('Theta/Gamma'):.2f}" if row.get(
                    'Theta/Gamma') == row.get('Theta/Gamma') else "n/a"),
                ("DivYield%", f"{row.get('DivYld%', float('nan')):.2f}%" if row.get(
                    'DivYld%', float('nan')) == row.get('DivYld%', float('nan')) else "n/a"),
                ("—", "—"),
                ("Exit: 50% profit",
                 f"Close when mark ≤ ${target_50_pct:.2f}"),
                ("Exit: 75% profit",
                 f"Close when mark ≤ ${target_75_pct:.2f}"),
            ]
            st.subheader("Contract summary")
            st.table(pd.DataFrame(base_rows, columns=["Field", "Value"]))

            paths = 50000
            days_for_mc = max(1, days)
            iv_for_calc = iv_dec if (
                iv_dec == iv_dec and iv_dec > 0.0) else 0.20
            params = dict(S0=price, days=days_for_mc, iv=iv_for_calc,
                          Kc=strike, call_premium=prem, div_ps_annual=div_ps_annual)
            # Use realistic equity drift for CC (7% annual = historical equity returns)
            mc = mc_pnl("CC", params, n_paths=int(paths), mu=0.07, seed=None)

        else:  # COLLAR
            kc = float(_safe_float(row.get("CallStrike")))
            kp = float(_safe_float(row.get("PutStrike")))
            call_prem = float(_safe_float(row.get("CallPrem"))) if row.get(
                "CallPrem") == row.get("CallPrem") else float(_safe_float(row.get("Premium", 0.0)))
            put_prem = float(_safe_float(row.get("PutPrem"))) if row.get(
                "PutPrem") == row.get("PutPrem") else 0.0
            capital = price * 100.0
            div_ps_annual = float(_safe_float(row.get("DivAnnualPS", 0.0)))
            base_rows = [
                ("Strategy", "COLLAR"),
                ("Ticker", row.get("Ticker")),
                ("Price", f"${price:,.2f}"),
                ("Call K", f"{kc:,.2f}"),
                ("Put K", f"{kp:,.2f}"),
                ("Exp", row.get("Exp")),
                ("Days", f"{days}"),
                ("Call Prem", f"${call_prem:,.2f}"),
                ("Put Prem", f"${put_prem:,.2f}"),
                ("Capital", f"${capital:,.0f}"),
                ("IV", f"{iv_raw:.2f}%" if iv_raw ==
                 iv_raw and iv_raw > 0 else "n/a"),
                ("PutCushionσ", f"{row.get('PutCushionσ'):.2f}" if row.get(
                    'PutCushionσ') == row.get('PutCushionσ') else "n/a"),
                ("CallCushionσ", f"{row.get('CallCushionσ'):.2f}" if row.get(
                    'CallCushionσ') == row.get('CallCushionσ') else "n/a"),
            ]
            st.subheader("Structure summary")
            st.table(pd.DataFrame(base_rows, columns=["Field", "Value"]))

            paths = 50000
            days_for_mc = max(1, days)
            iv_for_calc = iv_dec if (
                iv_dec == iv_dec and iv_dec > 0.0) else 0.20
            params = dict(S0=price, days=days_for_mc, iv=iv_for_calc,
                          Kc=kc, call_premium=call_prem, Kp=kp, put_premium=put_prem,
                          div_ps_annual=div_ps_annual)
            # Use realistic equity drift for Collar (7% annual)
            mc = mc_pnl("COLLAR", params, n_paths=int(
                paths), mu=0.07, seed=None)

        # Risk & reward summary from MC
        pnl = mc.get("pnl_paths")
        collateral = float(mc.get("collateral", 0.0))

        def _pct(x):
            try:
                return f"{100.0*float(x):.2f}%"
            except Exception:
                return "n/a"

        if isinstance(pnl, np.ndarray) and pnl.size > 0 and collateral > 0:
            loss10_prob = float(np.mean(pnl <= (-0.10 * collateral)))
            loss_any_prob = float(np.mean(pnl < 0.0))
            roi_cycle_expected = float(
                mc.get("pnl_expected", float("nan")) / collateral)
        else:
            loss10_prob = float("nan")
            loss_any_prob = float("nan")
            roi_cycle_expected = float("nan")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Expected P&L / contract", f"${mc['pnl_expected']:,.0f}")
        c2.metric("Annualized ROI (expected)", _pct(
            mc.get("roi_ann_expected", float("nan"))))
        c3.metric("ROI per cycle (expected)", _pct(roi_cycle_expected))

        def _pct_precise(x):
            try:
                return f"{100.0*float(x):.4f}%"
            except Exception:
                return "n/a"

        c4.metric("P(loss > 10% of capital)", _pct_precise(loss10_prob))
        c5.metric("P(any loss)", _pct(loss_any_prob))

        if isinstance(pnl, np.ndarray) and pnl.size > 0:
            df_hist = pd.DataFrame({"P&L": pnl})
            st.subheader("P&L distribution")
            chart = alt.Chart(df_hist).mark_bar().encode(
                x=alt.X("P&L:Q", bin=alt.Bin(maxbins=60),
                        title="P&L per contract (USD)"),
                y=alt.Y("count()", title="Paths"),
                tooltip=[alt.Tooltip("count()", title="Paths")]
            )
            st.altair_chart(chart, use_container_width=True)

        st.caption(
            "Loss probabilities based on a GBM simulation with 50k paths, IV defaulted to 20% if missing, and 1 day used when DTE is 0.")

# --- Tab 10: Roll Analysis ---
with tabs[10]:
    st.header("Roll Analysis — Should I Roll This Position?")
    st.caption(
        "Evaluate whether rolling to a new expiration is better than closing the current position.")

    strat_choice_roll, current_row = _get_selected_row()
    if current_row is None:
        st.info("Select a strategy/contract above to analyze roll opportunities.")
    else:
        current_ticker = current_row.get("Ticker")
        current_dte = int(_safe_int(current_row.get("Days", 0), 0))
        current_strike = float(_safe_float(current_row.get("Strike")))
        current_prem = float(_safe_float(current_row.get("Premium")))
        current_price = float(_safe_float(current_row.get("Price")))

        st.subheader(
            f"Current Position: {strat_choice_roll} on {current_ticker}")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Current DTE", f"{current_dte} days")
            st.metric("Current Strike", f"${current_strike:,.2f}")
        with col2:
            st.metric("Entry Premium", f"${current_prem:.2f}")
            st.metric("Current Price", f"${current_price:,.2f}")
        with col3:
            # Simulate current value for demo (in real use, would fetch live quote)
            # For now, estimate based on time decay (rough approximation)
            # Rough linear decay
            time_decayed = max(0.0, current_prem * (current_dte / 45.0))
            profit_captured = ((current_prem - time_decayed) /
                               current_prem) * 100 if current_prem > 0 else 0
            st.metric("Est. Profit Captured", f"{profit_captured:.1f}%")
            st.caption("⚠️ This is an estimate. Check real market price.")

        st.divider()
        st.subheader("Roll Opportunity Scan")

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            roll_min_dte = st.number_input(
                "Target min DTE for new position",
                min_value=current_dte,
                value=max(current_dte + 14, 21),
                step=7,
                key="roll_min_dte"
            )
        with col_r2:
            roll_max_dte = st.number_input(
                "Target max DTE for new position",
                min_value=roll_min_dte,
                value=max(current_dte + 30, 45),
                step=7,
                key="roll_max_dte"
            )

        same_strike = st.checkbox(
            "Only show same strike (less risk)",
            value=True,
            key="roll_same_strike"
        )

        if st.button("🔄 Find Roll Candidates", key="btn_find_rolls"):
            with st.spinner(f"Scanning {current_ticker} for roll opportunities..."):
                # Re-run analyzer with extended date range
                if strat_choice_roll == "CSP":
                    roll_df, _ = analyze_csp(
                        current_ticker,
                        min_days=roll_min_dte,
                        days_limit=roll_max_dte,
                        min_otm=0.0,  # Open it up for rolls
                        min_oi=int(min_oi),
                        max_spread=float(max_spread),
                        min_roi=0.0,  # Open it up
                        min_cushion=0.0,
                        min_poew=0.0,
                        earn_window=int(earn_window),
                        risk_free=float(risk_free),
                        bill_yield=float(t_bill_yield)
                    )
                elif strat_choice_roll == "CC":
                    roll_df = analyze_cc(
                        current_ticker,
                        min_days=roll_min_dte,
                        days_limit=roll_max_dte,
                        min_otm=0.0,
                        min_oi=int(min_oi),
                        max_spread=float(max_spread),
                        min_roi=0.0,
                        earn_window=int(earn_window),
                        risk_free=float(risk_free),
                        include_dividends=bool(include_div_cc),
                        bill_yield=float(t_bill_yield)
                    )
                else:
                    st.warning(
                        "Roll analysis currently supports CSP and CC only.")
                    roll_df = pd.DataFrame()

                if not roll_df.empty:
                    # Filter to same strike if requested
                    if same_strike:
                        roll_df = roll_df[roll_df["Strike"] == current_strike]

                    if not roll_df.empty:
                        # Calculate roll metrics
                        roll_df["Roll_Credit"] = roll_df["Premium"] - \
                            time_decayed
                        roll_df["Days_Extension"] = roll_df["Days"] - \
                            current_dte
                        roll_df["Roll_ROI_Ann"] = (
                            roll_df["Roll_Credit"] / current_strike) * (365.0 / roll_df["Days_Extension"])

                        st.success(f"Found {len(roll_df)} roll candidates")

                        # Display comparison
                        st.subheader("Roll vs Close Decision")

                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.markdown("### Option 1: Close Now")
                            st.metric(
                                "Profit Realized", f"${(current_prem - time_decayed) * 100:.0f}")
                            st.metric("Capital Freed",
                                      f"${current_strike * 100:,.0f}")
                            st.caption("✅ Immediate profit, can redeploy")

                        with col_b:
                            st.markdown("### Option 2: Roll Forward")
                            best_roll = roll_df.iloc[0]
                            roll_credit = best_roll["Roll_Credit"]
                            roll_days = best_roll["Days_Extension"]
                            st.metric("Additional Credit",
                                      f"${roll_credit * 100:.0f}")
                            st.metric("Time Extension", f"+{roll_days} days")
                            st.caption(
                                f"✅ Continue position, collect ${roll_credit * 100:.0f} more")

                        st.divider()
                        st.subheader("Top Roll Candidates")

                        show_cols = ["Strike", "Premium", "Days", "OTM%", "ROI%_ann",
                                     "Roll_Credit", "Days_Extension", "Roll_ROI_Ann",
                                     "Theta/Gamma", "CushionSigma", "Score"]
                        show_cols = [
                            c for c in show_cols if c in roll_df.columns]

                        st.dataframe(
                            roll_df[show_cols].head(10),
                            use_container_width=True,
                            height=400
                        )

                        st.info("""
                        **Roll Decision Framework:**
                        - **Roll if:** Roll credit > $50 AND extended DTE keeps you in sweet spot (21-45 DTE) AND Theta/Gamma stays > 0.8
                        - **Close if:** Profit captured > 75% OR current DTE < 10 days OR roll credit < $30
                        - **Consider strike adjustment:** If rolling out, consider rolling UP (CSP) or DOWN (CC) for more premium
                        """)
                    else:
                        st.warning(
                            f"No candidates found at strike ${current_strike}. Try unchecking 'same strike'.")
                else:
                    st.warning(
                        f"No roll opportunities found for {current_ticker} in the {roll_min_dte}-{roll_max_dte} DTE range.")
