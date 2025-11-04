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

# Import options math module (Black-Scholes, Greeks, Monte Carlo)
from options_math import (
    bs_call_price, bs_put_price,
    call_delta, put_delta,
    option_gamma, option_vega,
    call_theta, put_theta,
    expected_move,
    compute_spread_pct,
    trailing_dividend_info,
    get_earnings_date,
    gbm_terminal_prices,
    mc_pnl,
    _bs_d1_d2,  # Helper function for d1/d2 calculations
    _norm_cdf   # Normal CDF helper
)


# Import utility functions
from utils import (
    _safe_float, _safe_int, _get_num_from_row,
    _mid_price, _fmt_usd, _iv_decimal, _series_get,
    effective_credit, effective_debit
)

# Import strategy analyzers from strategy_analysis module
from strategy_analysis import (
    analyze_csp,
    analyze_cc,
    analyze_collar,
    analyze_iron_condor,
    analyze_bull_put_spread,
    analyze_bear_call_spread,
    prescreen_tickers
)
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


# ----------------------------- Expiration Safety Module -----------------------------

def check_expiration_risk(expiration_str: str, strategy: str, open_interest: int = 0, 
                          bid_ask_spread_pct: float = 0.0) -> dict:
    """
    Analyze expiration date risk and return comprehensive safety assessment.
    
    Args:
        expiration_str: Expiration date string (e.g., "2025-11-15")
        strategy: Strategy type ("CSP", "CC", "Collar", "Bull Put Spread", "Bear Call Spread", "Iron Condor")
        open_interest: Open interest for the option(s)
        bid_ask_spread_pct: Bid-ask spread as percentage of mid price
    
    Returns:
        dict with keys:
            - is_standard: bool (True if standard Friday expiration)
            - expiration_type: str ("Monthly 3rd Friday", "Weekly Friday", "Non-Standard")
            - day_of_week: str (e.g., "Friday", "Monday")
            - risk_level: str ("LOW", "MEDIUM", "HIGH", "EXTREME")
            - action: str ("ALLOW", "WARN", "BLOCK")
            - warning_message: str (human-readable warning)
            - risk_factors: list[str] (specific concerns)
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
            "risk_factors": ["Cannot parse expiration date"]
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
        "risk_factors": risk_factors
    }


def display_expiration_warning(risk_info: dict) -> None:
    """Display expiration risk warning in Streamlit UI."""
    if risk_info["action"] == "BLOCK":
        st.error(f"""
**{risk_info['warning_message']}**

This combination is too risky and has been blocked:
- Expiration: {risk_info['expiration_type']}
- Risk Level: {risk_info['risk_level']}

**Risk Factors:**
{chr(10).join('• ' + factor for factor in risk_info['risk_factors'])}

**Why Blocked:**
- Multi-leg strategies on non-standard expirations have extreme liquidity risk
- Wide spreads on entry/exit can eliminate profit potential
- Difficult to close positions early if needed
- Higher risk of partial fills leaving you exposed

**Recommendation:** Use standard Friday expirations (preferably 3rd Friday of month)
        """)
    elif risk_info["action"] == "WARN":
        st.warning(f"""
**{risk_info['warning_message']}**

**Risk Factors:**
{chr(10).join('• ' + factor for factor in risk_info['risk_factors'])}

**Proceed with caution:**
- Verify Open Interest > 500 (preferably > 1,000)
- Check bid-ask spread < 3% of mid price
- Plan to hold to expiration (harder to exit early)
- Consider using standard Friday expiration instead
        """)
    else:
        st.success(f"✅ {risk_info['expiration_type']} - Standard expiration with acceptable risk")


# ----------------------------- Black-Scholes & Greeks -----------------------------
# NOTE: Black-Scholes pricing, Greeks, and Monte Carlo functions moved to options_math.py
# Imported at top of file for use throughout this module.


# -------------------------- Analyzers ----------------------------

# -------------------------- Analyzers ----------------------------


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
    if strategy == "BULL_PUT_SPREAD":
        return [
            "Structure: **SELL higher strike put** (collect premium), **BUY lower strike put** (define max loss).",
            "Tenor: **21–45 DTE** for optimal theta decay; same sweet spot as CSP.",
            "Strike selection: Short strike **Δ ~ -0.15 to -0.25** (75–85% POEW); spread width **$5–10** or **5–10% of stock price**.",
            "Liquidity: **Both legs need OI ≥ 200** and **bid-ask ≤ 10%**; avoid illiquid strikes.",
            "Risk: Max loss = **spread width − net credit** (fully defined); max profit = **net credit**.",
            "Capital efficiency: **5-10x more efficient than CSP** (only risk spread width, not full strike).",
            "Target: Collect **25–40% of spread width** as credit (higher is better but riskier).",
            "Breakeven: **Short strike − net credit**; below this, you lose money.",
            "Exit: Take profit at **50–75% of max credit**; close early if short strike Δ > ~0.35.",
            "Avoid earnings and high-IV events that can cause gap moves through strikes.",
        ]
    if strategy == "BEAR_CALL_SPREAD":
        return [
            "Structure: **SELL lower strike call** (collect premium), **BUY higher strike call** (define max loss).",
            "Tenor: **21–45 DTE** for optimal theta decay; same sweet spot as CC.",
            "Strike selection: Short strike **Δ ~ +0.15 to +0.25** (75–85% POEW); spread width **$5–10** or **5–10% of stock price**.",
            "Liquidity: **Both legs need OI ≥ 200** and **bid-ask ≤ 10%**; avoid illiquid strikes.",
            "Risk: Max loss = **spread width − net credit** (fully defined); max profit = **net credit**.",
            "Capital efficiency: Better than naked calls (defined risk) but requires margin for spread.",
            "Target: Collect **25–40% of spread width** as credit (higher is better but riskier).",
            "Breakeven: **Short strike + net credit**; above this, you lose money.",
            "Dividend risk: Calls may be assigned early if deep ITM before ex-div; monitor closely.",
            "Exit: Take profit at **50–75% of max credit**; close early if short strike Δ > ~0.35.",
            "Avoid earnings and high-IV events that can cause gap moves through strikes.",
        ]
    return []

# ---------- Strategy Fit & Runbook helpers ----------


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
             "excess_negative": False, "cushion_low": False, "earnings_risk": False}

    days = int(_series_get(row, "Days", 0))
    spread = float(_series_get(row, "Spread%", float("nan")))
    
    # For multi-leg strategies, get OI from appropriate columns
    if strategy == "COLLAR":
        call_oi = int(_safe_int(_series_get(row, "CallOI", 0)))
        put_oi = int(_safe_int(_series_get(row, "PutOI", 0)))
        oi = min(call_oi, put_oi)  # Use worst case for liquidity check
    else:
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

    # Volume/OI ratio (liquidity health check)
    # For multi-leg strategies, try to get volume from different columns
    volume = float(_series_get(row, "Volume", float("nan")))
    
    # For spread strategies, try alternative volume columns
    if volume != volume:  # if Volume is NaN, try alternatives
        if strategy == "COLLAR":
            # Use average of call and put volumes if available
            call_vol = float(_series_get(row, "CallVolume", float("nan")))
            put_vol = float(_series_get(row, "PutVolume", float("nan")))
            if call_vol == call_vol and put_vol == put_vol:
                volume = (call_vol + put_vol) / 2.0
            elif call_vol == call_vol:
                volume = call_vol
            elif put_vol == put_vol:
                volume = put_vol
        elif strategy == "IRON_CONDOR":
            # Use average of put and call short volumes
            put_vol = float(_series_get(row, "PutShortVolume", float("nan")))
            call_vol = float(_series_get(row, "CallShortVolume", float("nan")))
            if put_vol == put_vol and call_vol == call_vol:
                volume = (put_vol + call_vol) / 2.0
            elif put_vol == put_vol:
                volume = put_vol
            elif call_vol == call_vol:
                volume = call_vol
    
    if volume == volume and oi > 0:
        vol_oi_ratio = volume / oi
        if vol_oi_ratio >= 0.5:
            checks.append(("Volume/OI ratio", "✅", f"{vol_oi_ratio:.2f} (healthy turnover)"))
        elif vol_oi_ratio >= 0.25:
            checks.append(("Volume/OI ratio", "⚠️", f"{vol_oi_ratio:.2f} (moderate, prefer ≥0.5)"))
        else:
            checks.append(("Volume/OI ratio", "❌", f"{vol_oi_ratio:.2f} (stale OI risk)"))
    else:
        checks.append(("Volume/OI ratio", "⚠️", "n/a (volume data missing)"))

    # Earnings proximity check (for CSP and CC)
    if strategy in ("CSP", "CC"):
        days_to_earnings = int(_safe_int(_series_get(row, "DaysToEarnings", -1)))
        if 0 <= days_to_earnings <= days:
            checks.append(("Earnings risk", "⚠️", 
                          f"Earnings in {days_to_earnings} days (high volatility event)"))
            flags["earnings_risk"] = True
        elif 0 <= days_to_earnings <= days + 7:
            checks.append(("Earnings risk", "⚠️", 
                          f"Earnings shortly after expiry (+{days_to_earnings - days} days)"))
        elif days_to_earnings > 0:
            checks.append(("Earnings risk", "✅", f"No earnings within cycle (>{days_to_earnings} days)"))
        # If days_to_earnings is -1 or invalid, skip the check (data not available)

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
        
        # Check strike vs cost basis (if cost basis is available)
        cost_basis = float(_series_get(row, "CostBasis", float("nan")))
        K = float(_series_get(row, "Strike", float("nan")))
        if cost_basis == cost_basis and K == K and cost_basis > 0:
            if K >= cost_basis:
                profit_on_assignment = ((K - cost_basis) / cost_basis) * 100
                checks.append(("Strike vs cost basis", "✅", 
                              f"Strike ${K:.2f} ≥ basis ${cost_basis:.2f} (+{profit_on_assignment:.1f}% if assigned)"))
            else:
                loss_on_assignment = ((K - cost_basis) / cost_basis) * 100
                checks.append(("Strike vs cost basis", "❌", 
                              f"Strike ${K:.2f} < basis ${cost_basis:.2f} ({loss_on_assignment:.1f}% loss if assigned)"))
                flags["below_cost_basis"] = True

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

    elif strategy == "IRON_CONDOR":
        # Iron Condor specific checks
        put_long_strike = float(_series_get(row, "PutLongStrike", float("nan")))
        put_short_strike = float(_series_get(row, "PutShortStrike", float("nan")))
        call_short_strike = float(_series_get(row, "CallShortStrike", float("nan")))
        call_long_strike = float(_series_get(row, "CallLongStrike", float("nan")))
        net_credit = float(_series_get(row, "NetCredit", float("nan")))
        
        # Check profit zone width (distance between short strikes)
        if put_short_strike == put_short_strike and call_short_strike == call_short_strike:
            profit_zone = call_short_strike - put_short_strike
            zone_pct = (profit_zone / S) * 100.0 if S > 0 else 0.0
            if zone_pct >= 10.0:
                checks.append(("Profit zone width", "✅", f"${profit_zone:.0f} ({zone_pct:.1f}% of price)"))
            elif zone_pct >= 5.0:
                checks.append(("Profit zone width", "⚠️", f"${profit_zone:.0f} ({zone_pct:.1f}% of price, prefer ≥10%)"))
            else:
                checks.append(("Profit zone width", "❌", f"${profit_zone:.0f} ({zone_pct:.1f}% of price too narrow)"))
        
        # Check risk/reward ratio
        if net_credit == net_credit and put_short_strike == put_short_strike and put_long_strike == put_long_strike:
            put_spread_width = put_short_strike - put_long_strike
            max_loss = put_spread_width - net_credit
            max_profit = net_credit
            risk_reward = max_profit / max_loss if max_loss > 0 else 0.0
            if risk_reward >= 0.5:
                checks.append(("Risk/reward ratio", "✅", f"{risk_reward:.2f} (profit ${max_profit:.2f} / risk ${max_loss:.2f})"))
            elif risk_reward >= 0.33:
                checks.append(("Risk/reward ratio", "⚠️", f"{risk_reward:.2f} (acceptable, prefer ≥0.5)"))
            else:
                checks.append(("Risk/reward ratio", "❌", f"{risk_reward:.2f} (poor, prefer ≥0.5)"))
        
        # Check balanced spreads (both spreads should be same width)
        if all(x == x for x in [put_long_strike, put_short_strike, call_short_strike, call_long_strike]):
            put_width = put_short_strike - put_long_strike
            call_width = call_long_strike - call_short_strike
            if abs(put_width - call_width) < 0.01:
                checks.append(("Balanced spreads", "✅", f"Both ${put_width:.0f} wide"))
            else:
                checks.append(("Balanced spreads", "⚠️", f"Put ${put_width:.0f}, Call ${call_width:.0f} (unbalanced)"))
        
        # Check wing distance (distance from short to long strikes)
        if all(x == x for x in [put_long_strike, put_short_strike, call_short_strike, call_long_strike]):
            put_wing_dist = put_short_strike - put_long_strike
            call_wing_dist = call_long_strike - call_short_strike
            
            # Calculate distance as % of short strike
            put_wing_pct = (put_wing_dist / put_short_strike) * 100 if put_short_strike > 0 else 0.0
            call_wing_pct = (call_wing_dist / call_short_strike) * 100 if call_short_strike > 0 else 0.0
            min_wing_pct = min(put_wing_pct, call_wing_pct)
            
            if min_wing_pct >= 2.0:
                checks.append(("Wing distance", "✅", 
                              f"Put {put_wing_pct:.1f}%, Call {call_wing_pct:.1f}% (adequate buffer)"))
            elif min_wing_pct >= 1.0:
                checks.append(("Wing distance", "⚠️", 
                              f"Put {put_wing_pct:.1f}%, Call {call_wing_pct:.1f}% (tight wings)"))
            else:
                checks.append(("Wing distance", "❌", 
                              f"Put {put_wing_pct:.1f}%, Call {call_wing_pct:.1f}% (very tight, high risk)"))

    elif strategy == "BULL_PUT_SPREAD":
        # Bull Put Spread specific checks
        sell_strike = float(_series_get(row, "SellStrike", float("nan")))
        buy_strike = float(_series_get(row, "BuyStrike", float("nan")))
        net_credit = float(_series_get(row, "NetCredit", float("nan")))
        
        # Check spread width
        if sell_strike == sell_strike and buy_strike == buy_strike:
            spread_width = sell_strike - buy_strike
            spread_width_pct = (spread_width / S) * 100.0 if S > 0 else 0.0
            if 2.0 <= spread_width_pct <= 10.0:
                checks.append(("Spread width", "✅", f"${spread_width:.0f} ({spread_width_pct:.1f}% of price)"))
            elif spread_width_pct < 2.0:
                checks.append(("Spread width", "⚠️", f"${spread_width:.0f} ({spread_width_pct:.1f}% too narrow)"))
            else:
                checks.append(("Spread width", "⚠️", f"${spread_width:.0f} ({spread_width_pct:.1f}% very wide)"))
        
        # Check risk/reward ratio
        if net_credit == net_credit and sell_strike == sell_strike and buy_strike == buy_strike:
            spread_width = sell_strike - buy_strike
            max_loss = spread_width - net_credit
            max_profit = net_credit
            risk_reward = max_profit / max_loss if max_loss > 0 else 0.0
            if risk_reward >= 0.4:
                checks.append(("Risk/reward ratio", "✅", f"{risk_reward:.2f} (profit ${max_profit:.2f} / risk ${max_loss:.2f})"))
            elif risk_reward >= 0.25:
                checks.append(("Risk/reward ratio", "⚠️", f"{risk_reward:.2f} (acceptable, prefer ≥0.4)"))
            else:
                checks.append(("Risk/reward ratio", "❌", f"{risk_reward:.2f} (poor, prefer ≥0.4)"))
        
        # Delta target check (short put delta should be ~0.20-0.30)
        delta = float(_series_get(row, "Δ", float("nan")))
        if delta == delta:
            delta_abs = abs(delta)
            if 0.15 <= delta_abs <= 0.30:
                checks.append(("Δ target (short put)", "✅", f"{delta:.2f} (good POEW ~{(1-delta_abs)*100:.0f}%)"))
            elif 0.10 <= delta_abs < 0.15:
                checks.append(("Δ target (short put)", "⚠️", f"{delta:.2f} (too far OTM, low premium)"))
            else:
                checks.append(("Δ target (short put)", "⚠️", f"{delta:.2f} (prefer ~0.15-0.30)"))

    elif strategy == "BEAR_CALL_SPREAD":
        # Bear Call Spread specific checks
        sell_strike = float(_series_get(row, "SellStrike", float("nan")))
        buy_strike = float(_series_get(row, "BuyStrike", float("nan")))
        net_credit = float(_series_get(row, "NetCredit", float("nan")))
        
        # Check spread width
        if sell_strike == sell_strike and buy_strike == buy_strike:
            spread_width = buy_strike - sell_strike
            spread_width_pct = (spread_width / S) * 100.0 if S > 0 else 0.0
            if 2.0 <= spread_width_pct <= 10.0:
                checks.append(("Spread width", "✅", f"${spread_width:.0f} ({spread_width_pct:.1f}% of price)"))
            elif spread_width_pct < 2.0:
                checks.append(("Spread width", "⚠️", f"${spread_width:.0f} ({spread_width_pct:.1f}% too narrow)"))
            else:
                checks.append(("Spread width", "⚠️", f"${spread_width:.0f} ({spread_width_pct:.1f}% very wide)"))
        
        # Check risk/reward ratio
        if net_credit == net_credit and sell_strike == sell_strike and buy_strike == buy_strike:
            spread_width = buy_strike - sell_strike
            max_loss = spread_width - net_credit
            max_profit = net_credit
            risk_reward = max_profit / max_loss if max_loss > 0 else 0.0
            if risk_reward >= 0.4:
                checks.append(("Risk/reward ratio", "✅", f"{risk_reward:.2f} (profit ${max_profit:.2f} / risk ${max_loss:.2f})"))
            elif risk_reward >= 0.25:
                checks.append(("Risk/reward ratio", "⚠️", f"{risk_reward:.2f} (acceptable, prefer ≥0.4)"))
            else:
                checks.append(("Risk/reward ratio", "❌", f"{risk_reward:.2f} (poor, prefer ≥0.4)"))
        
        # Delta target check (short call delta should be ~0.20-0.30)
        delta = float(_series_get(row, "Δ", float("nan")))
        if delta == delta:
            delta_abs = abs(delta)
            if 0.15 <= delta_abs <= 0.30:
                checks.append(("Δ target (short call)", "✅", f"{delta:.2f} (good POEW ~{(1-delta_abs)*100:.0f}%)"))
            elif 0.10 <= delta_abs < 0.15:
                checks.append(("Δ target (short call)", "⚠️", f"{delta:.2f} (too far OTM, low premium)"))
            else:
                checks.append(("Δ target (short call)", "⚠️", f"{delta:.2f} (prefer ~0.15-0.30)"))

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

    elif strategy == "IRON_CONDOR":
        Kpl = float(_series_get(row, "PutLongStrike"))
        Kps = float(_series_get(row, "PutShortStrike"))
        Kcs = float(_series_get(row, "CallShortStrike"))
        Kcl = float(_series_get(row, "CallLongStrike"))
        net_credit_ps = float(_series_get(row, "NetCredit"))
        credit_pc = net_credit_ps * 100.0
        
        # Calculate max profit and max loss
        put_spread_width = Kps - Kpl
        call_spread_width = Kcl - Kcs
        max_spread_width = max(put_spread_width, call_spread_width)
        max_loss = (max_spread_width - net_credit_ps) * 100.0
        max_profit = credit_pc
        
        # Breakeven points
        be_lower = Kps - net_credit_ps
        be_upper = Kcs + net_credit_ps
        
        # Profit capture target
        tgt_close_ps = max(0.05, net_credit_ps * (1.0 - capture_pct))
        
        lines += [
            f"# RUNBOOK — IRON CONDOR ({ticker})",
            hr,
            "ENTRY (4-leg order):",
            f"• Buy to Open   {contracts}  {ticker}  {exp}  {int(Kpl)} PUT   (long put - downside protection)",
            f"• Sell to Open  {contracts}  {ticker}  {exp}  {int(Kps)} PUT   (short put - collect premium)",
            f"• Sell to Open  {contracts}  {ticker}  {exp}  {int(Kcs)} CALL  (short call - collect premium)",
            f"• Buy to Open   {contracts}  {ticker}  {exp}  {int(Kcl)} CALL  (long call - upside protection)",
            f"  Order: NET CREDIT, ≥ {_fmt_usd(net_credit_ps)} per share (≥ {_fmt_usd(credit_pc)} per contract), GTC",
            f"  Capital required: {_fmt_usd(max_loss * contracts, 0)}",
            f"  Max profit: {_fmt_usd(max_profit * contracts, 0)} (if {ticker} stays between {_fmt_usd(Kps)} and {_fmt_usd(Kcs)})",
            f"  Max loss: {_fmt_usd(max_loss * contracts, 0)} (if {ticker} moves beyond wings)",
            f"  Breakevens: {_fmt_usd(be_lower)} (lower) and {_fmt_usd(be_upper)} (upper)",
            "",
            "PROFIT‑TAKING TRIGGER(S):",
            f"• Close when total spread mark ≤ {_fmt_usd(tgt_close_ps)} per share  (≈ {int(capture_pct*100)}% credit captured), OR",
            "• Close/roll at ~7–10 DTE if ≥50% credit captured, OR",
            "• Close at ~21 DTE if ≥75% credit captured.",
            "",
            "RISK CLOSE‑OUT TRIGGER(S):",
            f"• Price approaches short strikes: ≤ {_fmt_usd(Kps + 2)} (put side) or ≥ {_fmt_usd(Kcs - 2)} (call side)",
            f"• Price breaches breakevens: ≤ {_fmt_usd(be_lower)} or ≥ {_fmt_usd(be_upper)}",
            "• Total P&L reaches 2× max profit (close to avoid further losses)",
            "• Consider rolling threatened side: close losing spread, open new one further out",
            "",
            "EXIT ORDERS (close all 4 legs):",
            f"• Profit‑take:  Close entire spread for NET DEBIT ≤ {_fmt_usd(tgt_close_ps)} per share, GTC",
            f"  - STC  {contracts}  {ticker}  {exp}  {int(Kpl)} PUT",
            f"  - BTC  {contracts}  {ticker}  {exp}  {int(Kps)} PUT",
            f"  - BTC  {contracts}  {ticker}  {exp}  {int(Kcs)} CALL",
            f"  - STC  {contracts}  {ticker}  {exp}  {int(Kcl)} CALL",
            "• Risk close‑out: Close at market or use STOP‑LIMIT for full spread.",
            "",
            "ADJUSTMENTS (if one side threatened):",
            "• Roll threatened spread: close losing spread, open new spread at better strikes/later expiry",
            "• Convert to vertical spread: close unthreatened side, manage remaining spread"
        ]

    elif strategy == "BULL_PUT_SPREAD":
        Ks = float(_series_get(row, "SellStrike"))
        Kb = float(_series_get(row, "BuyStrike"))
        net_credit_ps = float(_series_get(row, "NetCredit"))
        credit_pc = net_credit_ps * 100.0
        
        # Calculate max profit and max loss
        spread_width = Ks - Kb
        max_loss = (spread_width - net_credit_ps) * 100.0
        max_profit = credit_pc
        be = Ks - net_credit_ps
        
        # Profit capture target
        tgt_close_ps = max(0.05, net_credit_ps * (1.0 - capture_pct))
        
        lines += [
            f"# RUNBOOK — BULL PUT SPREAD ({ticker})",
            hr,
            "ENTRY (2-leg vertical spread):",
            f"• Sell to Open  {contracts}  {ticker}  {exp}  {int(Ks)} PUT   (short put - collect premium)",
            f"• Buy to Open   {contracts}  {ticker}  {exp}  {int(Kb)} PUT   (long put - define max loss)",
            f"  Order: NET CREDIT, ≥ {_fmt_usd(net_credit_ps)} per share (≥ {_fmt_usd(credit_pc)} per contract), GTC",
            f"  Capital required: {_fmt_usd(max_loss * contracts, 0)} (max risk per spread)",
            f"  Max profit: {_fmt_usd(max_profit * contracts, 0)} (if {ticker} stays above {_fmt_usd(Ks)})",
            f"  Max loss: {_fmt_usd(max_loss * contracts, 0)} (if {ticker} drops below {_fmt_usd(Kb)})",
            f"  Breakeven: {_fmt_usd(be)}",
            "",
            "PROFIT‑TAKING TRIGGER(S):",
            f"• Close when spread mark ≤ {_fmt_usd(tgt_close_ps)} per share  (≈ {int(capture_pct*100)}% credit captured), OR",
            "• Close/roll at ~7–10 DTE if ≥50% credit captured, OR",
            "• Close at ~21 DTE if ≥75% credit captured.",
            "",
            "RISK CLOSE‑OUT TRIGGER(S):",
            f"• Underlying drops to within $2 of short strike: ≤ {_fmt_usd(Ks + 2)}",
            f"• Underlying breaches breakeven: ≤ {_fmt_usd(be)}",
            "• Total P&L reaches 2× max profit (close to avoid max loss)",
            "• Consider rolling down/out: close current spread, open new one with lower strikes or later expiry",
            "",
            "EXIT ORDERS (close both legs):",
            f"• Profit‑take:  Close entire spread for NET DEBIT ≤ {_fmt_usd(tgt_close_ps)} per share, GTC",
            f"  - BTC  {contracts}  {ticker}  {exp}  {int(Ks)} PUT",
            f"  - STC  {contracts}  {ticker}  {exp}  {int(Kb)} PUT",
            "• Risk close‑out: Close at market or use STOP‑LIMIT for full spread.",
            "",
            "ROLLING (if under pressure):",
            f"• Roll down/out: Close current {int(Ks)}/{int(Kb)} spread, open new spread further OTM or later expiry",
            "• Target: collect additional credit while reducing breach risk",
            "• Keep spread width consistent (same risk profile)"
        ]

    elif strategy == "BEAR_CALL_SPREAD":
        Ks = float(_series_get(row, "SellStrike"))
        Kb = float(_series_get(row, "BuyStrike"))
        net_credit_ps = float(_series_get(row, "NetCredit"))
        credit_pc = net_credit_ps * 100.0
        
        # Calculate max profit and max loss
        spread_width = Kb - Ks
        max_loss = (spread_width - net_credit_ps) * 100.0
        max_profit = credit_pc
        be = Ks + net_credit_ps
        
        # Profit capture target
        tgt_close_ps = max(0.05, net_credit_ps * (1.0 - capture_pct))
        
        lines += [
            f"# RUNBOOK — BEAR CALL SPREAD ({ticker})",
            hr,
            "ENTRY (2-leg vertical spread):",
            f"• Sell to Open  {contracts}  {ticker}  {exp}  {int(Ks)} CALL  (short call - collect premium)",
            f"• Buy to Open   {contracts}  {ticker}  {exp}  {int(Kb)} CALL  (long call - define max loss)",
            f"  Order: NET CREDIT, ≥ {_fmt_usd(net_credit_ps)} per share (≥ {_fmt_usd(credit_pc)} per contract), GTC",
            f"  Capital required: {_fmt_usd(max_loss * contracts, 0)} (max risk per spread)",
            f"  Max profit: {_fmt_usd(max_profit * contracts, 0)} (if {ticker} stays below {_fmt_usd(Ks)})",
            f"  Max loss: {_fmt_usd(max_loss * contracts, 0)} (if {ticker} rises above {_fmt_usd(Kb)})",
            f"  Breakeven: {_fmt_usd(be)}",
            "",
            "PROFIT‑TAKING TRIGGER(S):",
            f"• Close when spread mark ≤ {_fmt_usd(tgt_close_ps)} per share  (≈ {int(capture_pct*100)}% credit captured), OR",
            "• Close/roll at ~7–10 DTE if ≥50% credit captured, OR",
            "• Close at ~21 DTE if ≥75% credit captured.",
            "",
            "RISK CLOSE‑OUT TRIGGER(S):",
            f"• Underlying rises to within $2 of short strike: ≥ {_fmt_usd(Ks - 2)}",
            f"• Underlying breaches breakeven: ≥ {_fmt_usd(be)}",
            "• Total P&L reaches 2× max profit (close to avoid max loss)",
            "• Consider rolling up/out: close current spread, open new one with higher strikes or later expiry",
            "",
            "EXIT ORDERS (close both legs):",
            f"• Profit‑take:  Close entire spread for NET DEBIT ≤ {_fmt_usd(tgt_close_ps)} per share, GTC",
            f"  - BTC  {contracts}  {ticker}  {exp}  {int(Ks)} CALL",
            f"  - STC  {contracts}  {ticker}  {exp}  {int(Kb)} CALL",
            "• Risk close‑out: Close at market or use STOP‑LIMIT for full spread.",
            "",
            "ROLLING (if under pressure):",
            f"• Roll up/out: Close current {int(Ks)}/{int(Kb)} spread, open new spread further OTM or later expiry",
            "• Target: collect additional credit while reducing breach risk",
            "• Keep spread width consistent (same risk profile)"
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
            
            # Current spread marks (what we'd pay to close)
            # Put spread: short Kps @ put_short_now, long Kpl @ put_long_now
            # Net debit to close = pay put_short_now, receive put_long_now
            put_spread_mark = put_short_now - put_long_now
            
            # Call spread: short Kcs @ call_short_now, long Kcl @ call_long_now  
            # Net debit to close = pay call_short_now, receive call_long_now
            call_spread_mark = call_short_now - call_long_now
            
            # Iron Condor P&L Logic:
            # Entry: Collected net_credit per share
            # Now: Would cost (put_spread_mark + call_spread_mark) per share to close
            # P&L per share = net_credit - (put_spread_mark + call_spread_mark)
            # Multiply by 100 for per-contract
            
            total_spread_mark = put_spread_mark + call_spread_mark
            total = (net_credit - total_spread_mark) * 100.0
            
            # Individual spread P&L (from current marks relative to zero)
            pnl_put_spread = -put_spread_mark * 100.0
            pnl_call_spread = -call_spread_mark * 100.0
            
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

    if strategy == "BULL_PUT_SPREAD":
        sell_strike = float(row["SellStrike"])
        buy_strike = float(row["BuyStrike"])
        net_credit = float(row["NetCredit"])  # per share
        
        for sp in shocks_pct:
            S1 = S0 * (1.0 + sp / 100.0)
            iv1 = max(0.02, iv_base + (iv_down_shift if sp < 0 else iv_up_shift))
            
            # Calculate mark prices for both legs
            sell_put_now = bs_put_price(S1, sell_strike, r, div_y, iv1, T)
            buy_put_now = bs_put_price(S1, buy_strike, r, div_y, iv1, T)
            
            # Spread mark (what we'd pay to close)
            spread_mark = sell_put_now - buy_put_now
            
            # P&L: Entry credit - current spread mark
            total = (net_credit - spread_mark) * 100.0
            
            # Capital = max loss = spread width - net credit
            spread_width = sell_strike - buy_strike
            capital = (spread_width - net_credit) * 100.0
            
            cycle_roi = total / capital if capital > 0 else 0.0
            ann_days = T0 * 365.0 if horizon_days == 0 else float(horizon_days)
            ann_roi = (1.0 + cycle_roi) ** (365.0 / max(1.0, ann_days)) - 1.0
            
            out.append({
                "Shock%": sp, "Price": S1,
                "SellPut_mark": sell_put_now,
                "BuyPut_mark": buy_put_now,
                "Spread_mark": spread_mark,
                "Total_P&L": total,
                "ROI_on_cap%": cycle_roi * 100.0,
                "Ann_ROI%": ann_roi * 100.0
            })
        return pd.DataFrame(out)

    if strategy == "BEAR_CALL_SPREAD":
        sell_strike = float(row["SellStrike"])
        buy_strike = float(row["BuyStrike"])
        net_credit = float(row["NetCredit"])  # per share
        
        for sp in shocks_pct:
            S1 = S0 * (1.0 + sp / 100.0)
            iv1 = max(0.02, iv_base + (iv_down_shift if sp < 0 else iv_up_shift))
            
            # Calculate mark prices for both legs
            sell_call_now = bs_call_price(S1, sell_strike, r, div_y, iv1, T)
            buy_call_now = bs_call_price(S1, buy_strike, r, div_y, iv1, T)
            
            # Spread mark (what we'd pay to close)
            spread_mark = sell_call_now - buy_call_now
            
            # P&L: Entry credit - current spread mark
            total = (net_credit - spread_mark) * 100.0
            
            # Capital = max loss = spread width - net credit
            spread_width = buy_strike - sell_strike
            capital = (spread_width - net_credit) * 100.0
            
            cycle_roi = total / capital if capital > 0 else 0.0
            ann_days = T0 * 365.0 if horizon_days == 0 else float(horizon_days)
            ann_roi = (1.0 + cycle_roi) ** (365.0 / max(1.0, ann_days)) - 1.0
            
            out.append({
                "Shock%": sp, "Price": S1,
                "SellCall_mark": sell_call_now,
                "BuyCall_mark": buy_call_now,
                "Spread_mark": spread_mark,
                "Total_P&L": total,
                "ROI_on_cap%": cycle_roi * 100.0,
                "Ann_ROI%": ann_roi * 100.0
            })
        return pd.DataFrame(out)

    raise ValueError("Unknown strategy for stress")


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
for key in ["df_csp", "df_cc", "df_collar", "df_iron_condor", "df_bull_put_spread", "df_bear_call_spread"]:
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

    # Live Trading Control
    with st.expander("⚡ LIVE TRADING", expanded=False):
        st.warning("⚠️ **DANGER ZONE** - Live order execution")
        
        # Initialize live trading mode in session state
        if "live_trading_enabled" not in st.session_state:
            st.session_state["live_trading_enabled"] = False
        
        # Live trading toggle
        live_mode = st.toggle(
            "Enable Live Trading",
            value=st.session_state.get("live_trading_enabled", False),
            key="live_trading_toggle",
            help="When enabled, orders are sent to Schwab API for execution. When disabled, orders are exported to JSON files only."
        )
        
        # Update session state
        st.session_state["live_trading_enabled"] = live_mode
        
        if live_mode:
            st.error("🔴 **LIVE TRADING ACTIVE**")
            st.caption("""
            ⚠️ Orders will be executed on your Schwab account!
            
            **Safety Features:**
            - All orders MUST be previewed first
            - Preview valid for 30 minutes only
            - Preview cleared after execution
            - Cannot execute same order twice
            
            **Process:**
            1. Click "Preview Order" button
            2. Review order details carefully
            3. Click "Execute Order" within 30 min
            4. Order submitted to Schwab API
            """)
            
            # Check if Schwab API is configured
            schwab_client = PROVIDER_INSTANCE.client if (PROVIDER_INSTANCE and hasattr(PROVIDER_INSTANCE, 'client')) else None
            if not schwab_client:
                st.warning("⚠️ Schwab API not configured. Live trading will fail.")
                st.caption("Set up Schwab credentials to use live trading.")
        else:
            st.success("✅ **DRY RUN MODE** (Safe)")
            st.caption("""
            📁 Orders are exported to JSON files only.
            No real trades will be executed.
            
            Perfect for:
            - Testing strategies
            - Learning the system
            - Paper trading
            - Validating order structure
            """)
    
    # Pre-screener section
    with st.expander("🎯 Pre-Screen Tickers", expanded=False):
        st.caption(
            "Filter a large ticker list for high-quality options candidates")
        # Top 200 S&P 500 tickers by market cap (as of Oct 2025)
        default_tickers = """AAPL, MSFT, NVDA, AMZN, GOOGL, GOOG, META, BRK.B, TSLA, LLY, AVGO, V, JPM, WMT, UNH, XOM, MA, ORCL, COST, HD, PG, NFLX, JNJ, ABBV, BAC, CRM, CVX, KO, MRK, AMD, CSCO, ACN, PEP, TMO, MCD, ABT, ADBE, LIN, IBM, PM, WFC, INTU, GE, TXN, QCOM, CAT, MS, ISRG, CMCSA, NOW, HON, VZ, AMGN, DHR, NEE, LOW, AXP, SPGI, T, UNP, BLK, PFE, UPS, AMAT, COP, RTX, GS, BKNG, SYK, DE, ELV, TJX, MDT, BX, VRTX, SBUX, PGR, PANW, ADP, BA, SCHW, ADI, GILD, MMC, CI, LRCX, CB, MDLZ, C, SO, REGN, FI, MU, INTC, ETN, BSX, AMT, DUK, ICE, PLD, KKR, CME, ZTS, WM, SLB, USB, MCO, EQIX, KLAC, NOC, BMY, APO, HCA, PH, MCK, ITW, SHW, CL, SNPS, PYPL, CEG, MSI, EOG, GD, APH, CTAS, MAR, CDNS, CMG, APD, WELL, FCX, TT, ORLY, ABNB, COF, ECL, ANET, PSX, TDG, FDX, MET, PCAR, AJG, AFL, RSG, NXPI, ADM, NEM, ROP, TRV, JCI, AZO, AMP, AIG, OXY, SRE, CARR, GM, ROST, MCHP, ADSK, CCI, BK, PAYX, SYY, TEL, MSCI, SPG, CPRT, O, HLT, TFC, URI, KMB, DXCM, CHTR, GWW, AEP, HES, FTNT, MNST, PSA, MRVL, ALL, DLR, OTIS, EA, DD, ACGL, NUE, CMI, KMI, D, HWM, IDXX, EW, IQV, PRU, PCG, YUM, KVUE, PWR, AXON, KHC, BKR, NDAQ, VST, CSGP, XYL, LHX, ROK"""
        
        prescreen_input = st.text_area(
            "Tickers to pre-screen (comma-separated)",
            value=default_tickers,
            height=150,
            key="prescreen_tickers",
            help="Default: Top 200 S&P 500 stocks by market cap"
        )
        col1, col2 = st.columns(2)
        with col1:
            ps_min_price = st.number_input(
                "Min price", value=5.0, step=1.0, key="ps_min_price")
            ps_min_hv = st.number_input(
                "Min HV%", value=18.0, step=5.0, key="ps_min_hv")
            ps_min_volume = st.number_input(
                "Min avg volume", value=1500000, step=100000, key="ps_min_volume", format="%d")
        with col2:
            ps_max_price = st.number_input(
                "Max price", value=1000.0, step=50.0, key="ps_max_price")
            ps_max_hv = st.number_input(
                "Max HV%", value=70.0, step=10.0, key="ps_max_hv")
            ps_min_opt_vol = st.number_input(
                "Min option vol", value=150, step=10, key="ps_min_opt_vol")

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
                         width='stretch')

            # Expandable detailed scores
            with st.expander("🔍 View Detailed Component Scores"):
                detail_cols = ['Ticker', 'Quality_Score', 'ROI_Score', 'TG_Score',
                               'Liq_Score', 'Safe_Score', 'IV%', 'HV_30d%', 'Spread%']
                detail_cols = [c for c in detail_cols if c in ps_df.columns]
                st.dataframe(ps_df[detail_cols], width='stretch')
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
    
    # Expiration safety controls
    st.divider()
    st.subheader("⚠️ Expiration Safety")
    allow_nonstandard = st.checkbox(
        "Include non-standard expirations (higher risk)",
        value=False,
        key="allow_nonstandard",
        help="""
        Non-standard = expires on Mon/Tue/Wed/Thu or unusual Fridays.
        
        Risks:
        • Much lower liquidity (wider spreads, lower OI)
        • Harder to exit early if needed
        • Higher assignment risk (especially for CC)
        • EXTREME risk for multi-leg strategies (spreads, IC)
        
        Only enable if you understand these risks and plan to hold to expiration.
        """
    )
    block_high_risk_multileg = st.checkbox(
        "Block high-risk multi-leg on non-standard dates",
        value=True,
        key="block_high_risk_multileg",
        help="Automatically block spreads and Iron Condors on non-standard expirations (RECOMMENDED)"
    )

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

    st.subheader("Credit Spreads (Bull Put / Bear Call)")
    cs_spread_width = st.number_input(
        "Spread Width ($)", value=5.0, step=1.0, key="cs_spread_width",
        help="Distance between short and long strikes for credit spreads")
    cs_target_delta = st.slider(
        "Short Strike Target Δ (abs)", 0.10, 0.30, 0.20, step=0.01, key="cs_target_delta",
        help="Target delta for short strikes (~0.20 = 80% POEW)")
    cs_min_roi = st.number_input(
        "Min ROI % (annualized)", value=20.0, step=1.0, key="cs_min_roi_input",
        help="Minimum annualized return on risk capital")

    st.divider()
    run_btn = st.button("🔎 Scan Strategies")


@st.cache_data(show_spinner=True, ttl=120)
def run_scans(tickers, params):
    """
    Run CSP, CC, Collar, Iron Condor, Bull Put Spread, and Bear Call Spread scans in parallel across tickers.
    Uses ThreadPoolExecutor for concurrent processing.
    """
    # Handle empty ticker list
    if not tickers or len(tickers) == 0:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {"CSP": {}}

    csp_all = []
    cc_all = []
    col_all = []
    ic_all = []
    bps_all = []  # Bull Put Spread
    bcs_all = []  # Bear Call Spread
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

        # Bull Put Spread scan
        bps = analyze_bull_put_spread(
            t,
            min_days=params["min_days"],
            days_limit=params["days_limit"],
            min_oi=params["min_oi"],
            max_spread=params["max_spread"],
            min_roi=params["cs_min_roi"] / 100.0,
            min_cushion=params["min_cushion"],
            min_poew=params["min_poew"],
            earn_window=params["earn_window"],
            risk_free=params["risk_free"],
            spread_width=params["cs_spread_width"],
            target_delta_short=params["cs_target_delta"],
            bill_yield=params["bill_yield"]
        )

        # Bear Call Spread scan
        bcs = analyze_bear_call_spread(
            t,
            min_days=params["min_days"],
            days_limit=params["days_limit"],
            min_oi=params["min_oi"],
            max_spread=params["max_spread"],
            min_roi=params["cs_min_roi"] / 100.0,
            min_cushion=params["min_cushion"],
            min_poew=params["min_poew"],
            earn_window=params["earn_window"],
            risk_free=params["risk_free"],
            spread_width=params["cs_spread_width"],
            target_delta_short=params["cs_target_delta"],
            bill_yield=params["bill_yield"]
        )

        return csp, csp_cnt, cc, col, ic, bps, bcs

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
                csp, csp_cnt, cc, col, ic, bps, bcs = future.result()

                # Accumulate results
                if not csp.empty:
                    csp_all.append(csp)
                if not cc.empty:
                    cc_all.append(cc)
                if not col.empty:
                    col_all.append(col)
                if not ic.empty:
                    ic_all.append(ic)
                if not bps.empty:
                    bps_all.append(bps)
                if not bcs.empty:
                    bcs_all.append(bcs)

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
    df_bps = pd.concat(
        bps_all, ignore_index=True) if bps_all else pd.DataFrame()
    df_bcs = pd.concat(
        bcs_all, ignore_index=True) if bcs_all else pd.DataFrame()

    return df_csp, df_cc, df_col, df_ic, df_bps, df_bcs, scan_counters


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
            cs_spread_width=float(cs_spread_width),
            cs_target_delta=float(cs_target_delta),
            cs_min_roi=float(cs_min_roi),
            min_oi=int(min_oi), max_spread=float(max_spread),
            earn_window=int(earn_window), risk_free=float(risk_free),
            per_contract_cap=per_contract_cap,
            bill_yield=float(t_bill_yield)
        )
        try:
            with st.spinner("Scanning..."):
                df_csp, df_cc, df_collar, df_iron_condor, df_bull_put_spread, df_bear_call_spread, scan_counters = run_scans(
                    tickers, opts)
            st.session_state["df_csp"] = df_csp
            st.session_state["df_cc"] = df_cc
            st.session_state["df_collar"] = df_collar
            st.session_state["df_iron_condor"] = df_iron_condor
            st.session_state["df_bull_put_spread"] = df_bull_put_spread
            st.session_state["df_bear_call_spread"] = df_bear_call_spread
            st.session_state["scan_counters"] = scan_counters

            # Show results summary
            total_results = len(df_csp) + len(df_cc) + len(df_collar) + len(df_iron_condor) + len(df_bull_put_spread) + len(df_bear_call_spread)
            if total_results > 0:
                st.success(
                    f"✅ Scan complete! Found {len(df_csp)} CSP, {len(df_cc)} CC, {len(df_collar)} Collar, {len(df_iron_condor)} IC, {len(df_bull_put_spread)} Bull Put, {len(df_bear_call_spread)} Bear Call")
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
df_bull_put_spread = st.session_state["df_bull_put_spread"]
df_bear_call_spread = st.session_state["df_bear_call_spread"]

# Apply expiration safety filtering
allow_nonstandard = st.session_state.get("allow_nonstandard", False)
block_high_risk_multileg = st.session_state.get("block_high_risk_multileg", True)

# Count blocked items before filtering
original_counts = {
    "CSP": len(df_csp),
    "CC": len(df_cc),
    "Collar": len(df_collar),
    "Iron Condor": len(df_iron_condor),
    "Bull Put Spread": len(df_bull_put_spread),
    "Bear Call Spread": len(df_bear_call_spread)
}

if not allow_nonstandard:
    # Filter out non-standard expirations entirely
    if not df_csp.empty and "ExpAction" in df_csp.columns:
        df_csp = df_csp[df_csp["ExpAction"] != "BLOCK"].copy()
    if not df_cc.empty and "ExpAction" in df_cc.columns:
        df_cc = df_cc[df_cc["ExpAction"] != "BLOCK"].copy()
    if not df_collar.empty and "ExpAction" in df_collar.columns:
        df_collar = df_collar[df_collar["ExpAction"] != "BLOCK"].copy()
    if not df_iron_condor.empty and "ExpAction" in df_iron_condor.columns:
        df_iron_condor = df_iron_condor[df_iron_condor["ExpAction"] != "BLOCK"].copy()
    if not df_bull_put_spread.empty and "ExpAction" in df_bull_put_spread.columns:
        df_bull_put_spread = df_bull_put_spread[df_bull_put_spread["ExpAction"] != "BLOCK"].copy()
    if not df_bear_call_spread.empty and "ExpAction" in df_bear_call_spread.columns:
        df_bear_call_spread = df_bear_call_spread[df_bear_call_spread["ExpAction"] != "BLOCK"].copy()

if block_high_risk_multileg:
    # Additional blocking for multi-leg strategies on non-standard dates
    if not df_iron_condor.empty and "ExpAction" in df_iron_condor.columns:
        df_iron_condor = df_iron_condor[df_iron_condor["ExpAction"] == "ALLOW"].copy()
    if not df_bull_put_spread.empty and "ExpAction" in df_bull_put_spread.columns and "ExpRisk" in df_bull_put_spread.columns:
        df_bull_put_spread = df_bull_put_spread[
            (df_bull_put_spread["ExpAction"] == "ALLOW") | 
            ((df_bull_put_spread["ExpAction"] == "WARN") & (df_bull_put_spread["ExpRisk"] != "HIGH"))
        ].copy()
    if not df_bear_call_spread.empty and "ExpAction" in df_bear_call_spread.columns and "ExpRisk" in df_bear_call_spread.columns:
        df_bear_call_spread = df_bear_call_spread[
            (df_bear_call_spread["ExpAction"] == "ALLOW") | 
            ((df_bear_call_spread["ExpAction"] == "WARN") & (df_bear_call_spread["ExpRisk"] != "HIGH"))
        ].copy()

# Calculate and display filtered counts
filtered_counts = {
    "CSP": len(df_csp),
    "CC": len(df_cc),
    "Collar": len(df_collar),
    "Iron Condor": len(df_iron_condor),
    "Bull Put Spread": len(df_bull_put_spread),
    "Bear Call Spread": len(df_bear_call_spread)
}

# Show warning if items were filtered out
blocked_any = False
for strategy in original_counts:
    diff = original_counts[strategy] - filtered_counts[strategy]
    if diff > 0:
        blocked_any = True

if blocked_any and not allow_nonstandard:
    st.info(f"""
    **⚠️ Expiration Safety Filter Active**
    
    Filtered out non-standard expirations for your protection:
    - CSP: {original_counts['CSP'] - filtered_counts['CSP']} blocked
    - CC: {original_counts['CC'] - filtered_counts['CC']} blocked
    - Collar: {original_counts['Collar'] - filtered_counts['Collar']} blocked
    - Iron Condor: {original_counts['Iron Condor'] - filtered_counts['Iron Condor']} blocked
    - Bull Put Spread: {original_counts['Bull Put Spread'] - filtered_counts['Bull Put Spread']} blocked
    - Bear Call Spread: {original_counts['Bear Call Spread'] - filtered_counts['Bear Call Spread']} blocked
    
    **Why?** Non-standard expirations (Mon/Tue/Wed/Thu) have poor liquidity and higher risk.
    
    To see all results, enable "Include non-standard expirations" in the sidebar (not recommended).
    """)


# --- Universal Contract / Structure Picker (applies to all tabs) ---
st.subheader("Selection — applies to Risk, Runbook, and Stress tabs")

# Determine available strategies based on scan results
_available = [("CSP", df_csp), ("CC", df_cc), ("COLLAR", df_collar), ("IRON_CONDOR", df_iron_condor),
              ("BULL_PUT_SPREAD", df_bull_put_spread), ("BEAR_CALL_SPREAD", df_bear_call_spread)]
available_strats = [name for name, df in _available if not df.empty]
if "sel_strategy" not in st.session_state:
    st.session_state["sel_strategy"] = (
        available_strats[0] if available_strats else "CSP")

# Strategy picker (single source of truth)
sel_strategy = st.selectbox(
    "Strategy",
    ["CSP", "CC", "COLLAR", "IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"],
    index=["CSP", "CC", "COLLAR", "IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"].index(st.session_state["sel_strategy"]),
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
    if strategy == "IRON_CONDOR":
        df = df_iron_condor
        if df.empty:
            return pd.Series([], dtype=str)
        return (
            df["Ticker"] + " | " + df["Exp"]
            + " | CS=" + df["CallShortStrike"].astype(str)
            + " | PS=" + df["PutShortStrike"].astype(str)
        )
    if strategy == "BULL_PUT_SPREAD":
        df = df_bull_put_spread
        if df.empty:
            return pd.Series([], dtype=str)
        return (
            df["Ticker"] + " | " + df["Exp"]
            + " | Sell=" + df["SellStrike"].astype(str)
            + " | Buy=" + df["BuyStrike"].astype(str)
        )
    if strategy == "BEAR_CALL_SPREAD":
        df = df_bear_call_spread
        if df.empty:
            return pd.Series([], dtype=str)
        return (
            df["Ticker"] + " | " + df["Exp"]
            + " | Sell=" + df["SellStrike"].astype(str)
            + " | Buy=" + df["BuyStrike"].astype(str)
        )
    # Default fallback
    return pd.Series([], dtype=str)


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
    elif strat == "IRON_CONDOR":
        df = df_iron_condor
        if df.empty:
            return strat, None
        ks = (df["Ticker"] + " | " + df["Exp"]
              + " | CS=" + df["CallShortStrike"].astype(str)
              + " | PS=" + df["PutShortStrike"].astype(str))
    elif strat == "BULL_PUT_SPREAD":
        df = df_bull_put_spread
        if df.empty:
            return strat, None
        ks = (df["Ticker"] + " | " + df["Exp"]
              + " | Sell=" + df["SellStrike"].astype(str)
              + " | Buy=" + df["BuyStrike"].astype(str))
    elif strat == "BEAR_CALL_SPREAD":
        df = df_bear_call_spread
        if df.empty:
            return strat, None
        ks = (df["Ticker"] + " | " + df["Exp"]
              + " | Sell=" + df["SellStrike"].astype(str)
              + " | Buy=" + df["BuyStrike"].astype(str))
    else:
        return strat, None
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
#         st.dataframe(earnings_df, width='stretch', height=200)
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
    "Bull Put Spread", "Bear Call Spread",
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
                     "IV", "POEW", "CushionSigma", "Theta/Gamma", "Spread%", "OI", "Collateral", "DaysToEarnings", "ExpType", "ExpRisk", "Score"]
        show_cols = [c for c in show_cols if c in df_csp.columns]

        # Show expiration risk warnings if any WARN actions exist
        if "ExpAction" in df_csp.columns:
            warn_count = len(df_csp[df_csp["ExpAction"] == "WARN"])
            if warn_count > 0:
                st.warning(f"""
                ⚠️ **{warn_count} position(s) have non-standard expirations**
                
                Check the 'ExpType' and 'ExpRisk' columns. Non-standard expirations may have:
                - Lower liquidity (wider spreads)
                - Harder to exit early
                - Consider using standard Friday expirations instead
                """)

        # Add earnings warning info box
        if "DaysToEarnings" in df_csp.columns:
            # Filter for non-null values and convert to numeric to handle None
            days_col = pd.to_numeric(df_csp["DaysToEarnings"], errors='coerce')
            earnings_nearby = df_csp[days_col.notna() & (days_col.abs() <= 14)]
            if not earnings_nearby.empty:
                st.warning(
                    f"⚠️ {len(earnings_nearby)} position(s) have earnings within 14 days. Review 'DaysToEarnings' column.")

        st.dataframe(df_csp[show_cols], width='stretch', height=520)

        # Add earnings legend
        st.caption(
            "**DaysToEarnings**: Days until next earnings (positive = future, negative = past, blank = unknown) | "
            "**ExpType**: Monthly (3rd Fri), Weekly (Fri), or Non-Standard | "
            "**ExpRisk**: LOW/MEDIUM/HIGH/EXTREME | "
            "Data source: Yahoo Finance (Alpha Vantage fallback enabled only during order preview to preserve API quota)"
        )

# --- Tab 2: CC ---
with tabs[1]:
    st.header("Covered Calls")
    if df_cc.empty:
        st.info("Run a scan or loosen CC filters.")
    else:
        show_cols = ["Strategy", "Ticker", "Price", "Exp", "Days", "Strike", "Premium", "OTM%", "ROI%_ann",
                     "IV", "POEC", "CushionSigma", "Theta/Gamma", "Spread%", "OI", "Capital", "DivYld%", "DaysToEarnings", "ExpType", "ExpRisk", "Score"]
        show_cols = [c for c in show_cols if c in df_cc.columns]

        # Show expiration risk warnings
        if "ExpAction" in df_cc.columns:
            warn_count = len(df_cc[df_cc["ExpAction"] == "WARN"])
            if warn_count > 0:
                st.warning(f"""
                ⚠️ **{warn_count} position(s) have non-standard expirations**
                
                **HIGH RISK for Covered Calls:**
                - Early assignment risk on non-Friday expirations
                - May coincide with ex-dividend dates
                - Harder to manage if stock moves against you
                
                **Recommendation:** Use standard Friday expirations only.
                """)

        # Add earnings warning info box
        if "DaysToEarnings" in df_cc.columns:
            # Filter for non-null values and convert to numeric to handle None
            days_col = pd.to_numeric(df_cc["DaysToEarnings"], errors='coerce')
            earnings_nearby = df_cc[days_col.notna() & (days_col.abs() <= 14)]
            if not earnings_nearby.empty:
                st.warning(
                    f"⚠️ {len(earnings_nearby)} position(s) have earnings within 14 days. Review 'DaysToEarnings' column.")

        st.dataframe(df_cc[show_cols], width='stretch', height=520)

        # Add earnings legend
        st.caption(
            "**DaysToEarnings**: Days until next earnings (positive = future, negative = past, blank = unknown) | "
            "**ExpType**: Monthly (3rd Fri), Weekly (Fri), or Non-Standard | "
            "**ExpRisk**: LOW/MEDIUM/HIGH (assignment risk) | "
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
                     "Floor$/sh", "Cap$/sh", "PutCushionσ", "CallCushionσ", "ExpType", "ExpRisk", "Score"]
        show_cols = [c for c in show_cols if c in df_collar.columns]
        
        # Show expiration risk warnings
        if "ExpAction" in df_collar.columns:
            warn_count = len(df_collar[df_collar["ExpAction"] == "WARN"])
            if warn_count > 0:
                st.warning(f"""
                ⚠️ **{warn_count} position(s) have non-standard expirations**
                
                **2-Leg Strategy Risk:**
                - Must manage both call and put sides
                - Liquidity issues on BOTH legs
                - Harder to adjust or roll
                
                Use OI > 1,000 on both legs if trading non-standard dates.
                """)
        
        st.dataframe(df_collar[show_cols],
                     width='stretch', height=520)

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
                     "PutSpread%", "CallSpread%", "PutShortOI", "CallShortOI", "IV", "ExpType", "ExpRisk", "Score"]
        show_cols = [c for c in show_cols if c in df_iron_condor.columns]
        
        # Show expiration risk warnings - STRONGEST WARNING
        if "ExpAction" in df_iron_condor.columns:
            warn_count = len(df_iron_condor[df_iron_condor["ExpAction"] == "WARN"])
            block_count = len(df_iron_condor[df_iron_condor["ExpAction"] == "BLOCK"])
            if warn_count > 0 or block_count > 0:
                st.error(f"""
                🚨 **EXTREME RISK: {warn_count + block_count} position(s) have non-standard expirations**
                
                **4-Leg Strategy - DO NOT TRADE:**
                - All 4 legs must have excellent liquidity
                - Non-standard dates = DISASTER for Iron Condors
                - Cannot close positions without massive slippage
                - Partial fills will leave you exposed
                
                ⛔ **BLOCKED** by default. Only use standard Friday expirations for Iron Condors.
                """)
        
        st.dataframe(df_iron_condor[show_cols],
                     width='stretch', height=520)
        
        st.caption(
            "**PutShortΔ/CallShortΔ**: Delta of short strikes (target ~±0.16 = 84% POEW) | "
            "**MaxLoss**: Wing width − net credit | "
            "**ROI%_ann**: (Net credit / Max loss) × (365 / Days) × 100 | "
            "**ExpType**: ONLY use Monthly or Weekly Friday | "
            "**ExpRisk**: Should be LOW only | "
            "**ProbMaxProfit**: Probability both spreads expire worthless (approximate)"
        )

# --- Tab 4: Bull Put Spread ---
with tabs[4]:
    st.header("Bull Put Spread (Defined Risk Credit Spread)")
    if df_bull_put_spread.empty:
        st.info("Run a scan or loosen Credit Spread settings.")
    else:
        show_cols = ["Strategy", "Ticker", "Price", "Exp", "Days",
                     "SellStrike", "BuyStrike", "Spread", "NetCredit", "MaxLoss",
                     "OTM%", "ROI%", "ROI%_ann",
                     "Δ", "Γ", "Θ", "Vρ", "IV", "POEW",
                     "CushionSigma", "Theta/Gamma", "Spread%", "OI", "Capital",
                     "DaysToEarnings", "ExpType", "ExpRisk", "Score"]
        show_cols = [c for c in show_cols if c in df_bull_put_spread.columns]
        
        # Show expiration risk warnings
        if "ExpAction" in df_bull_put_spread.columns:
            warn_count = len(df_bull_put_spread[df_bull_put_spread["ExpAction"] == "WARN"])
            if warn_count > 0:
                st.warning(f"""
                ⚠️ **{warn_count} position(s) have non-standard expirations**
                
                **2-Leg Spread Risk:**
                - Liquidity on BOTH legs critical
                - Wide spreads = reduced profit potential
                - Risk of partial fills (one leg only)
                
                **Recommendation:** Use OI > 500 and spread < 3% on BOTH legs.
                """)
        
        st.dataframe(df_bull_put_spread[show_cols],
                     width='stretch', height=520)
        
        st.caption(
            "**Bull Put Spread**: SELL higher strike put + BUY lower strike put = NET CREDIT | "
            "**Max Profit**: Net credit received | "
            "**Max Loss**: Spread width − net credit | "
            "**Breakeven**: Sell strike − net credit | "
            "**Capital**: Max loss × 100 (risk capital per contract) | "
            "**5-10x more efficient than CSP** (only risk spread width, not full strike)"
        )

# --- Tab 5: Bear Call Spread ---
with tabs[5]:
    st.header("Bear Call Spread (Defined Risk Credit Spread)")
    if df_bear_call_spread.empty:
        st.info("Run a scan or loosen Credit Spread settings.")
    else:
        show_cols = ["Strategy", "Ticker", "Price", "Exp", "Days",
                     "SellStrike", "BuyStrike", "Spread", "NetCredit", "MaxLoss",
                     "OTM%", "ROI%", "ROI%_ann",
                     "Δ", "Γ", "Θ", "Vρ", "IV", "POEW",
                     "CushionSigma", "Theta/Gamma", "Spread%", "OI", "Capital",
                     "DaysToEarnings", "ExpType", "ExpRisk", "Score"]
        show_cols = [c for c in show_cols if c in df_bear_call_spread.columns]
        
        # Show expiration risk warnings
        if "ExpAction" in df_bear_call_spread.columns:
            warn_count = len(df_bear_call_spread[df_bear_call_spread["ExpAction"] == "WARN"])
            if warn_count > 0:
                st.warning(f"""
                ⚠️ **{warn_count} position(s) have non-standard expirations**
                
                **2-Leg Spread Risk:**
                - Liquidity on BOTH legs critical
                - Early assignment risk if deep ITM
                - Wide spreads = reduced profit potential
                
                **Recommendation:** Use OI > 500 and spread < 3% on BOTH legs.
                """)
        
        st.dataframe(df_bear_call_spread[show_cols],
                     width='stretch', height=520)
        
        st.caption(
            "**Bear Call Spread**: SELL lower strike call + BUY higher strike call = NET CREDIT | "
            "**Max Profit**: Net credit received | "
            "**Max Loss**: Spread width − net credit | "
            "**Breakeven**: Sell strike + net credit | "
            "**Capital**: Max loss × 100 (risk capital per contract) | "
            "**ExpType**: Prefer Friday expirations | "
            "**Defined risk, no stock ownership required**"
        )

# --- Tab 6: Compare ---
with tabs[6]:
    st.header("Compare Projected Annualized ROIs (mid-price based)")
    if df_csp.empty and df_cc.empty and df_collar.empty and df_iron_condor.empty and df_bull_put_spread.empty and df_bear_call_spread.empty:
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
        if not df_bull_put_spread.empty:
            tmp = df_bull_put_spread[["Strategy", "Ticker", "Exp", "Days",
                                       "SellStrike", "BuyStrike", "NetCredit", "ROI%_ann", "Score"]].copy()
            tmp = tmp.rename(columns={"SellStrike": "Strike"})
            tmp["Premium"] = tmp["NetCredit"]
            tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + \
                " | Sell=" + tmp["Strike"].astype(str) + " | Buy=" + tmp["BuyStrike"].astype(str)
            pieces.append(tmp)
        if not df_bear_call_spread.empty:
            tmp = df_bear_call_spread[["Strategy", "Ticker", "Exp", "Days",
                                        "SellStrike", "BuyStrike", "NetCredit", "ROI%_ann", "Score"]].copy()
            tmp = tmp.rename(columns={"SellStrike": "Strike"})
            tmp["Premium"] = tmp["NetCredit"]
            tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + \
                " | Sell=" + tmp["Strike"].astype(str) + " | Buy=" + tmp["BuyStrike"].astype(str)
            pieces.append(tmp)


        cmp_df = pd.concat(
            pieces, ignore_index=True) if pieces else pd.DataFrame()
        if cmp_df.empty:
            st.info("No comparable rows.")
        else:
            st.dataframe(cmp_df.sort_values(["Score", "ROI%_ann"], ascending=[False, False]),
                         width='stretch', height=520)
        
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
            
            if st.button("🔍 Retrieve Account Numbers", width='stretch'):
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
                if not df_bull_put_spread.empty:
                    available_strategies.append("Bull Put Spread")
                if not df_bear_call_spread.empty:
                    available_strategies.append("Bear Call Spread")
                
                if not available_strategies:
                    st.warning("⚠️ No scan results available. Run a scan first.")
                    selected_strategy = None
                else:
                    strategy_map = {
                        "Cash-Secured Put": ("CSP", df_csp),
                        "Covered Call": ("CC", df_cc),
                        "Collar": ("COLLAR", df_collar),
                        "Iron Condor": ("IRON_CONDOR", df_iron_condor),
                        "Bull Put Spread": ("BULL_PUT_SPREAD", df_bull_put_spread),
                        "Bear Call Spread": ("BEAR_CALL_SPREAD", df_bear_call_spread)
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
                elif selected_strategy == "BULL_PUT_SPREAD":
                    st.info("💡 **Bull Put Spread**: Sell higher strike put + buy lower strike put = NET CREDIT | Defined risk, 5-10x more efficient than CSP")
                elif selected_strategy == "BEAR_CALL_SPREAD":
                    st.info("💡 **Bear Call Spread**: Sell lower strike call + buy higher strike call = NET CREDIT | Defined risk, no stock ownership required")
            
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
                            " P: $" + df_display['PutLongStrike'].astype(str) + "/" +
                            df_display['PutShortStrike'].astype(str) +
                            " C: $" + df_display['CallShortStrike'].astype(str) + "/" +
                            df_display['CallLongStrike'].astype(str) +
                            " @ $" + df_display['NetCredit'].round(2).astype(str)
                        )
                    elif selected_strategy == "BULL_PUT_SPREAD":
                        df_display['display'] = (
                            df_display['Ticker'] + " " +
                            df_display['Exp'] +
                            " Sell $" + df_display['SellStrike'].astype(str) +
                            " / Buy $" + df_display['BuyStrike'].astype(str) + " PUT" +
                            " @ $" + df_display['NetCredit'].round(2).astype(str)
                        )
                    elif selected_strategy == "BEAR_CALL_SPREAD":
                        df_display['display'] = (
                            df_display['Ticker'] + " " +
                            df_display['Exp'] +
                            " Sell $" + df_display['SellStrike'].astype(str) +
                            " / Buy $" + df_display['BuyStrike'].astype(str) + " CALL" +
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
                            col_p1.metric("Long Put", f"${selected['PutLongStrike']:.2f}")
                            col_p2.metric("Short Put", f"${selected['PutShortStrike']:.2f}")
                            st.write("**Call Spread:**")
                            col_c1, col_c2 = st.columns(2)
                            col_c1.metric("Short Call", f"${selected['CallShortStrike']:.2f}")
                            col_c2.metric("Long Call", f"${selected['CallLongStrike']:.2f}")
                        
                        # Options Approval Level Information
                        st.divider()
                        if selected_strategy == "CC":
                            st.info(
                                "**📋 Covered Call Options (you have Level 3 approval):**\n\n"
                                "**Option 1 - Already Own Stock:**\n"
                                f"• You must own **100 shares per contract** of {selected['Ticker']} to sell calls directly\n"
                                f"• The app will verify your stock position before submitting\n\n"
                                "**Option 2 - Buy-Write Order (Recommended if you don't own stock):**\n"
                                f"• Submit a 2-leg order that buys stock + sells call simultaneously\n"
                                f"• Both legs fill together (atomic execution)\n"
                                f"• Schwab recognizes this as a legitimate covered call strategy\n"
                                f"• Works with Level 3 approval (no need to own stock first)\n\n"
                                "The app will offer the buy-write option if you don't have sufficient shares."
                            )
                        elif selected_strategy == "CSP":
                            # Calculate required cash based on the strike price (100 shares per contract)
                            required_cash_per_contract = selected['Strike'] * 100
                            st.info(
                                "**📋 Cash-Secured Put Requirements (Schwab Level 1 Options Approval):**\n\n"
                                f"• You need approximately **${required_cash_per_contract:,.2f} per contract** in cash/buying power\n"
                                f"• This covers the maximum loss if assigned at the strike price\n"
                                f"• The app will verify your buying power before submitting to Schwab"
                            )
                        elif selected_strategy == "BULL_PUT_SPREAD":
                            st.write("**Bull Put Spread (2-leg):**")
                            col_s1, col_s2 = st.columns(2)
                            col_s1.metric("Sell Put", f"${selected['SellStrike']:.2f}")
                            col_s2.metric("Buy Put", f"${selected['BuyStrike']:.2f}")
                            col_c1, col_c2 = st.columns(2)
                            col_c1.metric("Net Credit", f"${selected['NetCredit']:.2f}")
                            col_c2.metric("ROI (ann)", f"{selected['ROI%_ann']:.1f}%")
                        elif selected_strategy == "BEAR_CALL_SPREAD":
                            st.write("**Bear Call Spread (2-leg):**")
                            col_s1, col_s2 = st.columns(2)
                            col_s1.metric("Sell Call", f"${selected['SellStrike']:.2f}")
                            col_s2.metric("Buy Call", f"${selected['BuyStrike']:.2f}")
                            col_c1, col_c2 = st.columns(2)
                            col_c1.metric("Net Credit", f"${selected['NetCredit']:.2f}")
                            col_c2.metric("ROI (ann)", f"{selected['ROI%_ann']:.1f}%")
                
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
                    elif selected_strategy in ["COLLAR", "IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"]:
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
                    put_width = selected['PutShortStrike'] - selected['PutLongStrike']
                    call_width = selected['CallLongStrike'] - selected['CallShortStrike']
                    max_width = max(put_width, call_width)
                    col_b.write(f"**Max Risk:** ${(max_width - selected['NetCredit']) * 100 * num_contracts:,.2f}")
                    st.write(f"**Max Credit:** ${limit_price * 100 * num_contracts:,.2f}")
                elif selected_strategy == "BULL_PUT_SPREAD":
                    col_a, col_b = st.columns(2)
                    col_a.write(f"**Action:** 2-LEG CREDIT SPREAD (Bull Put)")
                    spread_width = selected['SellStrike'] - selected['BuyStrike']
                    col_b.write(f"**Max Risk:** ${(spread_width - selected['NetCredit']) * 100 * num_contracts:,.2f}")
                    st.write(f"**Max Credit:** ${limit_price * 100 * num_contracts:,.2f}")
                elif selected_strategy == "BEAR_CALL_SPREAD":
                    col_a, col_b = st.columns(2)
                    col_a.write(f"**Action:** 2-LEG CREDIT SPREAD (Bear Call)")
                    spread_width = selected['BuyStrike'] - selected['SellStrike']
                    col_b.write(f"**Max Risk:** ${(spread_width - selected['NetCredit']) * 100 * num_contracts:,.2f}")
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
                    if st.button("💰 Check Buying Power", width='stretch'):
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
                                        put_width = selected['PutShortStrike'] - selected['PutLongStrike']
                                        call_width = selected['CallLongStrike'] - selected['CallShortStrike']
                                        max_width = max(put_width, call_width)
                                        required = (max_width - selected['NetCredit']) * 100 * num_contracts
                                    elif selected_strategy == "BULL_PUT_SPREAD":
                                        spread_width = selected['SellStrike'] - selected['BuyStrike']
                                        required = (spread_width - selected['NetCredit']) * 100 * num_contracts
                                    elif selected_strategy == "BEAR_CALL_SPREAD":
                                        spread_width = selected['BuyStrike'] - selected['SellStrike']
                                        required = (spread_width - selected['NetCredit']) * 100 * num_contracts
                                    
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
                
                # Display preview status if available
                if '_previewed_order' in st.session_state:
                    preview_strategy = st.session_state.get('_previewed_strategy', 'Unknown')
                    preview_hash = st.session_state.get('_previewed_order_hash', 'N/A')
                    
                    if preview_strategy == selected_strategy:
                        st.success(
                            f"📋 **Order Previewed**: Ready for submission\n\n"
                            f"Strategy: {preview_strategy} | Hash: {preview_hash[:8]}..."
                        )
                    else:
                        st.warning(
                            f"⚠️ **Different Strategy Previewed**: You have a {preview_strategy} order previewed, "
                            f"but selected {selected_strategy}. Preview will be cleared if you submit."
                        )
                    
                    col_clear1, col_clear2 = st.columns([1, 3])
                    with col_clear1:
                        if st.button("🗑️ Clear Preview", help="Remove stored preview"):
                            st.session_state.pop('_previewed_order', None)
                            st.session_state.pop('_previewed_order_hash', None)
                            st.session_state.pop('_previewed_strategy', None)
                            st.session_state.pop('_preview_timestamp', None)
                            st.rerun()
                
                # PRE-FLIGHT CHECK for CC: Check stock position and offer buy-write if needed
                show_buy_write_option = False
                buy_write_stock_price = None
                
                if selected_strategy == "CC" and USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE and PROVIDER == "schwab":
                    try:
                        from providers.schwab_trading import SchwabTrader
                        schwab_client = PROVIDER_INSTANCE.client if hasattr(PROVIDER_INSTANCE, 'client') else None
                        if schwab_client:
                            trader = SchwabTrader(dry_run=False, client=schwab_client)
                            required_shares = int(num_contracts) * 100
                            
                            try:
                                position_check = trader.check_stock_position(
                                    symbol=selected['Ticker'],
                                    required_shares=required_shares
                                )
                                
                                if not position_check['hasSufficientShares']:
                                    show_buy_write_option = True
                                    st.warning(
                                        f"⚠️ **No Stock Position Found**: {position_check['message']}\n\n"
                                        f"You currently own {position_check['sharesOwned']} shares but need {required_shares} shares."
                                    )
                                    
                                    st.info(
                                        "**💡 Alternative Option (Level 3 Approval Required):**\n\n"
                                        "Since you have Level 3 options approval, you can submit a **Buy-Write Order** "
                                        "that buys the stock and sells the call simultaneously as a 2-leg strategy. "
                                        "Schwab will recognize this as a legitimate covered call and both legs will fill together.\n\n"
                                        "✓ No need to own stock first\n"
                                        "✓ Atomic execution (both legs fill together)\n"
                                        "✓ Recognized as covered call strategy"
                                    )
                                    
                                    # Let user choose
                                    use_buy_write_choice = st.radio(
                                        "How would you like to proceed?",
                                        options=[
                                            "Cancel - I'll buy the stock first",
                                            "Use Buy-Write Order (buy stock + sell call together)"
                                        ],
                                        key="buy_write_choice"
                                    )
                                    
                                    if "Buy-Write" in use_buy_write_choice:
                                        # Get current stock price for the order
                                        try:
                                            import yfinance as yf
                                            stock = yf.Ticker(selected['Ticker'])
                                            current_price = stock.info.get('currentPrice') or stock.info.get('regularMarketPrice', 0)
                                            if current_price == 0:
                                                hist = stock.history(period='1d')
                                                if not hist.empty:
                                                    current_price = hist['Close'].iloc[-1]
                                            
                                            buy_write_stock_price = current_price
                                            st.info(f"📊 Current stock price: ${current_price:.2f}")
                                            
                                            # Show net debit calculation
                                            net_debit = current_price - float(limit_price)
                                            total_cost = net_debit * 100 * int(num_contracts)
                                            st.write(f"**Net Debit:** ${net_debit:.2f} per share (${total_cost:,.2f} total)")
                                            st.caption(
                                                f"You'll pay ~${current_price:.2f} for stock, "
                                                f"receive ~${limit_price:.2f} for call = "
                                                f"net ${net_debit:.2f} per share"
                                            )
                                        except Exception as e:
                                            st.error(f"Could not get current stock price: {e}")
                                            show_buy_write_option = False
                                else:
                                    st.success(f"✅ **Stock Position Verified**: {position_check['message']}")
                            except Exception as e:
                                st.warning(f"⚠️ **Unable to verify stock position**: {str(e)}")
                    except Exception as e:
                        st.warning(f"Could not perform pre-flight check: {e}")
                
                with col_preview:
                    # Disable button if user chose "Cancel"
                    preview_disabled = False
                    if show_buy_write_option:
                        use_buy_write_choice = st.session_state.get('buy_write_choice', 'Cancel - I\'ll buy the stock first')
                        if "Cancel" in use_buy_write_choice:
                            preview_disabled = True
                            st.info("💡 Buy the stock first, then come back to create a covered call order")
                    
                    if st.button("🔍 Preview Order with Schwab API", width='stretch', disabled=preview_disabled):
                        try:
                            from providers.schwab_trading import SchwabTrader
                            from providers.schwab import SchwabClient
                            
                            # Earnings safety check before proceeding
                            if earnings_warning_threshold > 0 and days_to_earnings is not None and not pd.isna(days_to_earnings):
                                days_val = float(days_to_earnings)
                                if abs(days_val) <= earnings_warning_threshold:
                                    st.warning(f"⚠️ Earnings in {int(abs(days_val))} days - proceed with caution")
                            
                            # Guardrail: warn and require acknowledgement if MC expected P&L is negative
                            mc_expected = None
                            try:
                                if selected is not None and ('MC_ExpectedPnL' in selected):
                                    mc_expected = float(selected['MC_ExpectedPnL'])
                            except Exception:
                                mc_expected = None
                            if mc_expected is not None and not pd.isna(mc_expected) and mc_expected < 0:
                                st.warning(
                                    f"🚧 Monte Carlo expected P&L for this position is negative (${mc_expected:,.2f}).\n\n"
                                    "Previewing an order on a negative-expectation setup may not align with your risk rules."
                                )
                                proceed_key = "ack_negative_mc_preview"
                                proceed_anyway = st.checkbox(
                                    "I understand the MC expected P&L is negative and want to preview anyway",
                                    key=proceed_key,
                                )
                                if not proceed_anyway:
                                    st.info("Check the box above to preview anyway, or choose a different candidate.")
                                    st.stop()
                            
                            # Check if Schwab provider is active
                            if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE and PROVIDER == "schwab":
                                # Get the underlying schwab client
                                schwab_client = PROVIDER_INSTANCE.client if hasattr(PROVIDER_INSTANCE, 'client') else None
                                if schwab_client:
                                    # Initialize trader (NOT dry-run, we want to call API)
                                    trader = SchwabTrader(dry_run=False, client=schwab_client)
                                    
                                    # PRE-FLIGHT CHECKS based on strategy
                                    preflight_warnings = []
                                    preflight_errors = []
                                    use_buy_write = False  # Flag to switch to buy-write order
                                    
                                    if selected_strategy == "CC":
                                        # Check if buy-write was selected
                                        if show_buy_write_option and buy_write_stock_price:
                                            use_buy_write = True
                                            st.session_state['_stock_price'] = buy_write_stock_price
                                            preflight_warnings.append(
                                                f"📦 **Using Buy-Write Order**: Will buy {int(num_contracts) * 100} shares + sell {int(num_contracts)} call(s)"
                                            )
                                        # If no buy-write option shown, user must own stock (already checked above)
                                    
                                    elif selected_strategy == "CSP":
                                        # Check if user has sufficient buying power
                                        required_bp = float(selected['Strike']) * 100 * int(num_contracts)
                                        try:
                                            bp_check = trader.check_buying_power(
                                                required_amount=required_bp
                                            )
                                            
                                            if not bp_check['hasSufficientFunds']:
                                                preflight_warnings.append(
                                                    f"⚠️ **Buying Power Check**: You may need ${required_bp:,.2f} in cash/margin to secure this put. "
                                                    f"Current buying power: ${bp_check['buyingPower']:,.2f}"
                                                )
                                            else:
                                                preflight_warnings.append(
                                                    f"✅ **Buying Power Verified**: ${bp_check['buyingPower']:,.2f} available (need ${required_bp:,.2f})"
                                                )
                                        except Exception as e:
                                            preflight_warnings.append(
                                                f"⚠️ **Unable to verify buying power**: {str(e)}\n\n"
                                                f"Make sure you have ~${required_bp:,.2f} available."
                                            )
                                    
                                    # Display pre-flight warnings/errors
                                    if preflight_errors:
                                        for error in preflight_errors:
                                            st.error(error)
                                        st.info("**💡 How to fix**: Either buy the required shares first, or use buy-write order (Level 3).")
                                        # Don't create order if there are errors
                                        st.stop()
                                    
                                    if preflight_warnings:
                                        for warning in preflight_warnings:
                                            if "✅" in warning:
                                                st.success(warning)
                                            else:
                                                st.warning(warning)
                                    
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
                                        if use_buy_write:
                                            # Create buy-write order (buy stock + sell call)
                                            stock_price = st.session_state.get('_stock_price', 0)
                                            order = trader.create_buy_write_order(
                                                symbol=selected['Ticker'],
                                                expiration=selected['Exp'],
                                                strike=float(selected['Strike']),
                                                quantity=int(num_contracts),
                                                stock_price_limit=stock_price * 1.01,  # Allow 1% slippage
                                                option_credit=float(limit_price),
                                                duration=order_duration
                                            )
                                            st.info(
                                                f"📦 **Buy-Write Order Created**: This will buy {int(num_contracts) * 100} shares "
                                                f"of {selected['Ticker']} and sell {int(num_contracts)} call(s) simultaneously."
                                            )
                                        else:
                                            # Standard covered call (user already owns stock)
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
                                            long_put_strike=float(selected['PutLongStrike']),
                                            short_put_strike=float(selected['PutShortStrike']),
                                            short_call_strike=float(selected['CallShortStrike']),
                                            long_call_strike=float(selected['CallLongStrike']),
                                            quantity=int(num_contracts),
                                            limit_price=float(limit_price),
                                            duration=order_duration
                                        )
                                    elif selected_strategy == "BULL_PUT_SPREAD":
                                        order = trader.create_bull_put_spread_order(
                                            symbol=selected['Ticker'],
                                            expiration=selected['Exp'],
                                            sell_strike=float(selected['SellStrike']),
                                            buy_strike=float(selected['BuyStrike']),
                                            quantity=int(num_contracts),
                                            limit_price=float(limit_price),
                                            duration=order_duration
                                        )
                                    elif selected_strategy == "BEAR_CALL_SPREAD":
                                        order = trader.create_bear_call_spread_order(
                                            symbol=selected['Ticker'],
                                            expiration=selected['Exp'],
                                            sell_strike=float(selected['SellStrike']),
                                            buy_strike=float(selected['BuyStrike']),
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
                                            
                                            # STORE THE PREVIEWED ORDER in session state for later submission
                                            st.session_state['_previewed_order'] = order
                                            st.session_state['_previewed_order_hash'] = preview_result.get('order_hash')
                                            st.session_state['_previewed_strategy'] = selected_strategy
                                            st.session_state['_preview_timestamp'] = preview_result.get('preview', {}).get('timestamp', 'N/A')
                                            
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
                                            
                                            # Show info about submitting the previewed order
                                            st.info(
                                                "✅ **Order Ready for Submission**\n\n"
                                                "This previewed order is now stored and ready to submit. "
                                                "Use the 'Generate Order' button below to submit it for live trading "
                                                "or export it for dry-run mode.\n\n"
                                                "⏰ Preview expires in 30 minutes."
                                            )
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
                
                # Initialize session state for orders if not exists
                if 'generated_orders' not in st.session_state:
                    st.session_state.generated_orders = None
                if 'preview_results' not in st.session_state:
                    st.session_state.preview_results = {}
                
                # Generate order button (dry-run export)
                with col_export:
                    if st.button("📥 Generate Order Files", type="primary", width='stretch'):
                        # Clear previous orders and previews
                        st.session_state.generated_orders = None
                        st.session_state.preview_results = {}
                        
                        try:
                            from providers.schwab_trading import SchwabTrader, format_order_summary
                            
                            # Earnings safety check before proceeding
                            if earnings_warning_threshold > 0 and days_to_earnings is not None and not pd.isna(days_to_earnings):
                                days_val = float(days_to_earnings)
                                if abs(days_val) <= earnings_warning_threshold:
                                    st.warning(f"⚠️ Note: Earnings in {int(abs(days_val))} days")
                            
                            # Get profit capture percentage from user
                            col_profit, col_risk = st.columns(2)
                            
                            with col_profit:
                                profit_capture_pct = st.slider(
                                    "Profit capture target for exit order",
                                    min_value=25,
                                    max_value=100,
                                    value=70,
                                    step=5,
                                    help="Exit when this % of max profit is captured (standard: 50-75%)"
                                )
                            
                            with col_risk:
                                generate_stop_loss = st.checkbox(
                                    "Generate stop-loss order",
                                    value=True,
                                    help="Create risk limit order based on runbook (2x max profit loss)"
                                )
                                
                                if generate_stop_loss:
                                    risk_multiplier = st.slider(
                                        "Risk limit (× max profit)",
                                        min_value=1.5,
                                        max_value=3.0,
                                        value=2.0,
                                        step=0.5,
                                        help="Close if loss reaches this multiple of max profit (standard: 2x)"
                                    )
                            
                            # Initialize trader (dry-run or live based on user selection)
                            live_trading_enabled = st.session_state.get("live_trading_enabled", False)
                            
                            schwab_client = PROVIDER_INSTANCE.client if (PROVIDER_INSTANCE and hasattr(PROVIDER_INSTANCE, 'client')) else None
                            if live_trading_enabled and schwab_client:
                                trader = SchwabTrader(dry_run=False, client=schwab_client, export_dir="./trade_orders")
                                st.warning("⚠️ **LIVE TRADING MODE** - Orders will be executed on your Schwab account!")
                            else:
                                trader = SchwabTrader(dry_run=True, export_dir="./trade_orders")
                                if live_trading_enabled and not schwab_client:
                                    st.error("❌ Live trading enabled but Schwab client not configured. Using DRY RUN mode.")
                            
                            # Check if we have a previewed order to use
                            use_previewed_order = False
                            if '_previewed_order' in st.session_state and st.session_state.get('_previewed_strategy') == selected_strategy:
                                use_previewed_order = True
                                order = st.session_state['_previewed_order']
                                st.success(
                                    f"✅ Using previewed order (Hash: {st.session_state.get('_previewed_order_hash', 'N/A')[:8]}...)\n\n"
                                    "This is the EXACT order you previewed with Schwab API."
                                )
                            else:
                                if live_trading_enabled:
                                    st.warning(
                                        "⚠️ **No Preview Found**\n\n"
                                        "For live trading, you should preview the order first using the 'Preview Order' button above. "
                                        "This order will be created fresh (not previewed)."
                                    )
                                
                                # Create order based on strategy (fallback if no preview)
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
                                        long_put_strike=float(selected['PutLongStrike']),
                                        short_put_strike=float(selected['PutShortStrike']),
                                        short_call_strike=float(selected['CallShortStrike']),
                                        long_call_strike=float(selected['CallLongStrike']),
                                        quantity=int(num_contracts),
                                        limit_price=float(limit_price),
                                        duration=order_duration
                                    )
                                    strategy_type = "iron_condor"
                                elif selected_strategy == "BULL_PUT_SPREAD":
                                    order = trader.create_bull_put_spread_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        sell_strike=float(selected['SellStrike']),
                                        buy_strike=float(selected['BuyStrike']),
                                        quantity=int(num_contracts),
                                        limit_price=float(limit_price),
                                        duration=order_duration
                                    )
                                    strategy_type = "bull_put_spread"
                                elif selected_strategy == "BEAR_CALL_SPREAD":
                                    order = trader.create_bear_call_spread_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        sell_strike=float(selected['SellStrike']),
                                        buy_strike=float(selected['BuyStrike']),
                                        quantity=int(num_contracts),
                                        limit_price=float(limit_price),
                                        duration=order_duration
                                    )
                                    strategy_type = "bear_call_spread"
                            
                            # Determine strategy_type for previewed orders
                            if use_previewed_order:
                                strategy_type_map = {
                                    "CSP": "csp",
                                    "CC": "covered_call",
                                    "COLLAR": "collar",
                                    "IRON_CONDOR": "iron_condor",
                                    "BULL_PUT_SPREAD": "bull_put_spread",
                                    "BEAR_CALL_SPREAD": "bear_call_spread"
                                }
                                strategy_type = strategy_type_map.get(selected_strategy, "unknown")
                            
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
                                
                                # Clear the previewed order from session state after submission
                                if use_previewed_order and result['status'] in ['exported', 'success']:
                                    st.session_state.pop('_previewed_order', None)
                                    st.session_state.pop('_previewed_order_hash', None)
                                    st.session_state.pop('_previewed_strategy', None)
                                    st.session_state.pop('_preview_timestamp', None)
                                    if result['status'] == 'success':
                                        st.info("✅ Previewed order was successfully submitted and cleared from cache.")
                                
                                if result['status'] == 'exported':
                                    # Now create the profit-taking exit order
                                    exit_order = None
                                    exit_result = None
                                    profit_capture_decimal = profit_capture_pct / 100.0
                                    
                                    if selected_strategy == "CSP":
                                        # Exit: Buy to close at target price
                                        entry_premium = float(selected['Premium'])
                                        # Round to penny increments for Schwab API
                                        exit_price = round(max(0.05, entry_premium * (1.0 - profit_capture_decimal)), 2)
                                        
                                        exit_order = trader.create_option_order(
                                            symbol=selected['Ticker'],
                                            expiration=selected['Exp'],
                                            strike=float(selected['Strike']),
                                            option_type="PUT",
                                            action="BUY_TO_CLOSE",
                                            quantity=int(num_contracts),
                                            order_type="LIMIT",
                                            limit_price=exit_price,
                                            duration="GOOD_TILL_CANCEL"
                                        )
                                        exit_metadata = {
                                            **metadata,
                                            "exit_trigger": f"{profit_capture_pct}% profit capture",
                                            "entry_premium": entry_premium,
                                            "exit_price": exit_price,
                                            "profit_per_contract": (entry_premium - exit_price) * 100
                                        }
                                        exit_result = trader.submit_order(exit_order, strategy_type=f"{strategy_type}_exit", metadata=exit_metadata, skip_preview_check=True)
                                    
                                    elif selected_strategy == "CC":
                                        # Exit: Buy to close at target price
                                        entry_premium = float(selected['Premium'])
                                        # Round to penny increments for Schwab API
                                        exit_price = round(max(0.05, entry_premium * (1.0 - profit_capture_decimal)), 2)
                                        
                                        exit_order = trader.create_option_order(
                                            symbol=selected['Ticker'],
                                            expiration=selected['Exp'],
                                            strike=float(selected['Strike']),
                                            option_type="CALL",
                                            action="BUY_TO_CLOSE",
                                            quantity=int(num_contracts),
                                            order_type="LIMIT",
                                            limit_price=exit_price,
                                            duration="GOOD_TILL_CANCEL"
                                        )
                                        exit_metadata = {
                                            **metadata,
                                            "exit_trigger": f"{profit_capture_pct}% profit capture",
                                            "entry_premium": entry_premium,
                                            "exit_price": exit_price,
                                            "profit_per_contract": (entry_premium - exit_price) * 100
                                        }
                                        exit_result = trader.submit_order(exit_order, strategy_type=f"{strategy_type}_exit", metadata=exit_metadata, skip_preview_check=True)
                                    
                                    elif selected_strategy == "COLLAR":
                                        # Exit: Close both legs atomically
                                        call_entry = float(selected.get('CallPrem', 0))
                                        put_entry = float(selected.get('PutPrem', 0))
                                        
                                        # Calculate target exit prices
                                        call_exit = max(0.05, call_entry * (1.0 - profit_capture_decimal))
                                        put_exit = put_entry * 0.5  # Close put at ~50% of cost
                                        
                                        # Net exit: paying call_exit to close call, receiving put_exit for put
                                        # Net = put_exit - call_exit (negative = we pay net debit)
                                        # Round to penny increments for Schwab API
                                        net_exit = round(put_exit - call_exit, 2)
                                        
                                        # Create atomic multi-leg exit order
                                        try:
                                            exit_order = trader.create_collar_exit_order(
                                                symbol=selected['Ticker'],
                                                expiration=selected['Exp'],
                                                call_strike=float(selected['CallStrike']),
                                                put_strike=float(selected['PutStrike']),
                                                quantity=int(num_contracts),
                                                limit_price=net_exit,
                                                duration="GOOD_TILL_CANCEL"
                                            )
                                            
                                            exit_metadata = {
                                                **metadata,
                                                "exit_trigger": f"{profit_capture_pct}% profit capture",
                                                "call_entry_premium": call_entry,
                                                "call_exit_price": call_exit,
                                                "put_entry_cost": put_entry,
                                                "put_exit_price": put_exit,
                                                "net_exit": net_exit
                                            }
                                            
                                            exit_result = trader.submit_order(exit_order, strategy_type=f"{strategy_type}_exit", metadata=exit_metadata, skip_preview_check=True)
                                        except Exception as e:
                                            st.error(f"❌ Error creating collar exit order: {str(e)}")
                                            import traceback
                                            st.code(traceback.format_exc())
                                            exit_result = None
                                    
                                elif selected_strategy == "IRON_CONDOR":
                                    # Exit: Close entire spread (all 4 legs) as net debit
                                    entry_credit = float(selected['NetCredit'])
                                    # Round to penny increments for Schwab API
                                    exit_debit = round(max(0.05, entry_credit * (1.0 - profit_capture_decimal)), 2)
                                    
                                    exit_order = trader.create_iron_condor_exit_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        long_put_strike=float(selected['PutLongStrike']),
                                        short_put_strike=float(selected['PutShortStrike']),
                                        short_call_strike=float(selected['CallShortStrike']),
                                        long_call_strike=float(selected['CallLongStrike']),
                                        quantity=int(num_contracts),
                                        limit_price=exit_debit,
                                        duration="GOOD_TILL_CANCEL"
                                    )
                                    exit_metadata = {
                                        **metadata,
                                        "exit_trigger": f"{profit_capture_pct}% profit capture",
                                        "entry_credit": entry_credit,
                                        "exit_debit": exit_debit,
                                        "profit_per_contract": (entry_credit - exit_debit) * 100
                                    }
                                    exit_result = trader.submit_order(exit_order, strategy_type=f"{strategy_type}_exit", metadata=exit_metadata, skip_preview_check=True)
                                    
                                elif selected_strategy == "BULL_PUT_SPREAD":
                                    # Exit: Close entire spread (both legs) as net debit
                                    entry_credit = float(selected['NetCredit'])
                                    # Round to penny increments for Schwab API
                                    exit_debit = round(max(0.05, entry_credit * (1.0 - profit_capture_decimal)), 2)
                                    
                                    exit_order = trader.create_bull_put_spread_exit_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        sell_strike=float(selected['SellStrike']),
                                        buy_strike=float(selected['BuyStrike']),
                                        quantity=int(num_contracts),
                                        limit_price=exit_debit,
                                        duration="GOOD_TILL_CANCEL"
                                    )
                                    exit_metadata = {
                                        **metadata,
                                        "exit_trigger": f"{profit_capture_pct}% profit capture",
                                        "entry_credit": entry_credit,
                                        "exit_debit": exit_debit,
                                        "profit_per_contract": (entry_credit - exit_debit) * 100
                                    }
                                    exit_result = trader.submit_order(exit_order, strategy_type=f"{strategy_type}_exit", metadata=exit_metadata, skip_preview_check=True)
                                    
                                elif selected_strategy == "BEAR_CALL_SPREAD":
                                    # Exit: Close entire spread (both legs) as net debit
                                    entry_credit = float(selected['NetCredit'])
                                    # Round to penny increments for Schwab API
                                    exit_debit = round(max(0.05, entry_credit * (1.0 - profit_capture_decimal)), 2)
                                    
                                    exit_order = trader.create_bear_call_spread_exit_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        sell_strike=float(selected['SellStrike']),
                                        buy_strike=float(selected['BuyStrike']),
                                        quantity=int(num_contracts),
                                        limit_price=exit_debit,
                                        duration="GOOD_TILL_CANCEL"
                                    )
                                    exit_metadata = {
                                        **metadata,
                                        "exit_trigger": f"{profit_capture_pct}% profit capture",
                                        "entry_credit": entry_credit,
                                        "exit_debit": exit_debit,
                                        "profit_per_contract": (entry_credit - exit_debit) * 100
                                    }
                                    exit_result = trader.submit_order(exit_order, strategy_type=f"{strategy_type}_exit", metadata=exit_metadata, skip_preview_check=True)
                                    
                                # Generate stop-loss orders if requested
                                stop_loss_order = None
                                stop_loss_order_call = None
                                stop_loss_result = None
                                if generate_stop_loss:
                                    if selected_strategy == "CSP":
                                        # Risk: Close if option value reaches 2x entry premium (doubled loss)
                                        entry_premium = float(selected['Premium'])
                                        # Round to penny increments for Schwab API
                                        stop_loss_price = round(entry_premium * risk_multiplier, 2)
                                        max_loss = entry_premium * (risk_multiplier - 1) * 100  # per contract
                                        
                                        stop_loss_order = trader.create_option_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        strike=float(selected['Strike']),
                                        option_type="PUT",
                                        action="BUY_TO_CLOSE",
                                        quantity=int(num_contracts),
                                        order_type="LIMIT",
                                        limit_price=stop_loss_price,
                                        duration="GOOD_TILL_CANCEL"
                                        )
                                        stop_loss_metadata = {
                                        **metadata,
                                        "order_type": "STOP_LOSS",
                                        "risk_trigger": f"{risk_multiplier}x max profit loss",
                                        "entry_premium": entry_premium,
                                        "stop_loss_price": stop_loss_price,
                                        "max_loss_per_contract": max_loss
                                        }
                                        stop_loss_result = trader.submit_order(stop_loss_order, strategy_type=f"{strategy_type}_stop_loss", metadata=stop_loss_metadata, skip_preview_check=True)
                                    
                                    elif selected_strategy == "CC":
                                        # Risk: Close if option value reaches 2x entry premium
                                        entry_premium = float(selected['Premium'])
                                        # Round to penny increments for Schwab API
                                        stop_loss_price = round(entry_premium * risk_multiplier, 2)
                                        max_loss = entry_premium * (risk_multiplier - 1) * 100
                                        
                                        stop_loss_order = trader.create_option_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        strike=float(selected['Strike']),
                                        option_type="CALL",
                                        action="BUY_TO_CLOSE",
                                        quantity=int(num_contracts),
                                        order_type="LIMIT",
                                        limit_price=stop_loss_price,
                                        duration="GOOD_TILL_CANCEL"
                                        )
                                        stop_loss_metadata = {
                                        **metadata,
                                        "order_type": "STOP_LOSS",
                                        "risk_trigger": f"{risk_multiplier}x max profit loss",
                                        "entry_premium": entry_premium,
                                        "stop_loss_price": stop_loss_price,
                                        "max_loss_per_contract": max_loss
                                        }
                                        stop_loss_result = trader.submit_order(stop_loss_order, strategy_type=f"{strategy_type}_stop_loss", metadata=stop_loss_metadata, skip_preview_check=True)
                                    
                                    elif selected_strategy == "IRON_CONDOR":
                                        # Risk: Close if total spread cost reaches 2x entry credit
                                        entry_credit = float(selected['NetCredit'])
                                        # Round to penny increments for Schwab API
                                        stop_loss_debit = round(entry_credit * risk_multiplier, 2)
                                        max_loss = (stop_loss_debit - entry_credit) * 100
                                        
                                        stop_loss_order = trader.create_iron_condor_exit_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        long_put_strike=float(selected['PutLongStrike']),
                                        short_put_strike=float(selected['PutShortStrike']),
                                        short_call_strike=float(selected['CallShortStrike']),
                                        long_call_strike=float(selected['CallLongStrike']),
                                        quantity=int(num_contracts),
                                        limit_price=stop_loss_debit,
                                        duration="GOOD_TILL_CANCEL"
                                        )
                                        stop_loss_metadata = {
                                        **metadata,
                                        "order_type": "STOP_LOSS",
                                        "risk_trigger": f"{risk_multiplier}x max profit loss",
                                        "entry_credit": entry_credit,
                                        "stop_loss_debit": stop_loss_debit,
                                        "max_loss_per_contract": max_loss
                                        }
                                        stop_loss_result = trader.submit_order(stop_loss_order, strategy_type=f"{strategy_type}_stop_loss", metadata=stop_loss_metadata, skip_preview_check=True)
                                    
                                    elif selected_strategy == "BULL_PUT_SPREAD":
                                        # Risk: Close if total spread cost reaches 2x entry credit (same as IC logic)
                                        entry_credit = float(selected['NetCredit'])
                                        # Round to penny increments for Schwab API
                                        stop_loss_debit = round(entry_credit * risk_multiplier, 2)
                                        max_loss = (stop_loss_debit - entry_credit) * 100
                                        
                                        stop_loss_order = trader.create_bull_put_spread_exit_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        sell_strike=float(selected['SellStrike']),
                                        buy_strike=float(selected['BuyStrike']),
                                        quantity=int(num_contracts),
                                        limit_price=stop_loss_debit,
                                        duration="GOOD_TILL_CANCEL"
                                        )
                                        stop_loss_metadata = {
                                        **metadata,
                                        "order_type": "STOP_LOSS",
                                        "risk_trigger": f"{risk_multiplier}x max profit loss",
                                        "entry_credit": entry_credit,
                                        "stop_loss_debit": stop_loss_debit,
                                        "max_loss_per_contract": max_loss
                                        }
                                        stop_loss_result = trader.submit_order(stop_loss_order, strategy_type=f"{strategy_type}_stop_loss", metadata=stop_loss_metadata, skip_preview_check=True)
                                    
                                    elif selected_strategy == "BEAR_CALL_SPREAD":
                                        # Risk: Close if total spread cost reaches 2x entry credit
                                        entry_credit = float(selected['NetCredit'])
                                        # Round to penny increments for Schwab API
                                        stop_loss_debit = round(entry_credit * risk_multiplier, 2)
                                        max_loss = (stop_loss_debit - entry_credit) * 100
                                        
                                        stop_loss_order = trader.create_bear_call_spread_exit_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        sell_strike=float(selected['SellStrike']),
                                        buy_strike=float(selected['BuyStrike']),
                                        quantity=int(num_contracts),
                                        limit_price=stop_loss_debit,
                                        duration="GOOD_TILL_CANCEL"
                                        )
                                        stop_loss_metadata = {
                                        **metadata,
                                        "order_type": "STOP_LOSS",
                                        "risk_trigger": f"{risk_multiplier}x max profit loss",
                                        "entry_credit": entry_credit,
                                        "stop_loss_debit": stop_loss_debit,
                                        "max_loss_per_contract": max_loss
                                        }
                                        stop_loss_result = trader.submit_order(stop_loss_order, strategy_type=f"{strategy_type}_stop_loss", metadata=stop_loss_metadata, skip_preview_check=True)
                                    
                                    elif selected_strategy == "COLLAR":
                                        # Risk: Close call if it reaches 2x entry premium
                                        call_entry = float(selected.get('CallPrem', 0))
                                        # Round to penny increments for Schwab API
                                        call_stop_loss = round(call_entry * risk_multiplier, 2)
                                        
                                        stop_loss_order_call = trader.create_option_order(
                                        symbol=selected['Ticker'],
                                        expiration=selected['Exp'],
                                        strike=float(selected['CallStrike']),
                                        option_type="CALL",
                                        action="BUY_TO_CLOSE",
                                        quantity=int(num_contracts),
                                        order_type="LIMIT",
                                        limit_price=call_stop_loss,
                                        duration="GOOD_TILL_CANCEL"
                                        )
                                        stop_loss_metadata_call = {
                                        **metadata,
                                        "order_type": "STOP_LOSS",
                                        "risk_trigger": f"{risk_multiplier}x max profit loss on call",
                                        "leg": "CALL",
                                        "entry_premium": call_entry,
                                        "stop_loss_price": call_stop_loss
                                        }
                                        stop_loss_result = trader.submit_order(stop_loss_order_call, strategy_type=f"{strategy_type}_stop_loss_call", metadata=stop_loss_metadata_call, skip_preview_check=True)
                                    
                                    # Display success message and files
                                    order_count = 2 if not generate_stop_loss else 3
                                    
                                    # Store orders in session state for persistence across reruns
                                    st.session_state.generated_orders = {
                                        'entry_order': order,
                                        'entry_result': result,
                                        'exit_order': exit_order,
                                        'exit_result': exit_result,
                                        'stop_loss_order': stop_loss_order if generate_stop_loss else None,
                                        'stop_loss_result': stop_loss_result if generate_stop_loss else None,
                                        'generate_stop_loss': generate_stop_loss,
                                        'profit_capture_pct': profit_capture_pct,
                                        'risk_multiplier': risk_multiplier if generate_stop_loss else None,
                                        'strategy_type': strategy_type,
                                        'selected_strategy': selected_strategy,
                                        # Store collar-specific stop-loss if needed
                                        'stop_loss_order_call': stop_loss_order_call if selected_strategy == "COLLAR" and generate_stop_loss else None
                                    }
                                    
                                    st.success(f"✅ {order_count} order files generated successfully!")
                                else:
                                    st.error(f"❌ Failed to export order: {result.get('message', 'Unknown error')}")
                        
                        except Exception as e:
                            st.error(f"❌ Error generating order: {str(e)}")
                            import traceback
                            with st.expander("Error Details"):
                                st.code(traceback.format_exc())
                
                # Display generated orders if they exist in session state
                if st.session_state.generated_orders is not None:
                    from providers.schwab_trading import format_order_summary
                    
                    orders_data = st.session_state.generated_orders
                    order = orders_data['entry_order']
                    result = orders_data['entry_result']
                    exit_order = orders_data['exit_order']
                    exit_result = orders_data['exit_result']
                    stop_loss_order = orders_data['stop_loss_order']
                    stop_loss_result = orders_data['stop_loss_result']
                    generate_stop_loss = orders_data['generate_stop_loss']
                    profit_capture_pct = orders_data['profit_capture_pct']
                    risk_multiplier = orders_data['risk_multiplier']
                    selected_strategy = orders_data['selected_strategy']
                    
                    # Collar-specific stop-loss order
                    stop_loss_order_call = orders_data.get('stop_loss_order_call')
                
                    st.divider()
                    st.subheader("📋 Generated Orders")
                    
                    # Create columns based on whether stop-loss is included
                    if generate_stop_loss:
                        col_entry, col_exit, col_stop = st.columns(3)
                    else:
                        col_entry, col_exit = st.columns(2)
                        col_stop = None
                    
                    with col_entry:
                        st.write("**📤 ENTRY Order**")
                        st.code(result['filepath'], language=None)
                        
                        # Show order summary
                        with st.expander("📄 Entry Order Details"):
                            st.text(format_order_summary(order))
                            st.json(order)
                        
                        # Check for preview result in session state
                        if 'preview_entry' in st.session_state.preview_results:
                            preview_result = st.session_state.preview_results['preview_entry']
                            st.success("✅ Entry order preview received!")
                            with st.expander("📊 Preview Details", expanded=True):
                                preview_data = preview_result['preview']
                                if isinstance(preview_data, dict):
                                    if 'commission' in preview_data:
                                        st.metric("Commission", f"${preview_data['commission']:.2f}")
                                    if 'estimatedTotalAmount' in preview_data:
                                        st.metric("Estimated Credit", f"${preview_data['estimatedTotalAmount']:.2f}")
                                    if 'buyingPowerEffect' in preview_data:
                                        st.metric("Buying Power Impact", f"${preview_data['buyingPowerEffect']:.2f}")
                                    if 'marginRequirement' in preview_data:
                                        st.metric("Margin Requirement", f"${preview_data['marginRequirement']:.2f}")
                                    st.json(preview_data)
                                else:
                                    st.json(preview_data)
                        
                        # Preview and download buttons
                        col_preview_entry, col_dl_entry = st.columns(2)
                        
                        with col_preview_entry:
                            if st.button("🔍 Preview", key="preview_entry_btn", width='stretch'):
                                    try:
                                        from providers.schwab_trading import SchwabTrader
                                        from providers.schwab import SchwabClient
                                        
                                        if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE and PROVIDER == "schwab":
                                            schwab_client = PROVIDER_INSTANCE.client if hasattr(PROVIDER_INSTANCE, 'client') else None
                                            if schwab_client:
                                                trader = SchwabTrader(dry_run=False, client=schwab_client)
                                                # Guardrail: warn and require acknowledgement if MC expected P&L is negative
                                                mc_expected = None
                                                try:
                                                    if selected is not None and ('MC_ExpectedPnL' in selected):
                                                        mc_expected = float(selected['MC_ExpectedPnL'])
                                                except Exception:
                                                    mc_expected = None
                                                if mc_expected is not None and not pd.isna(mc_expected) and mc_expected < 0:
                                                    st.warning(
                                                        f"🚧 Monte Carlo expected P&L for this position is negative (${mc_expected:,.2f}).\n\n"
                                                        "Previewing an order on a negative-expectation setup may not align with your risk rules."
                                                    )
                                                    proceed_key = "ack_negative_mc_entry"
                                                    proceed_anyway = st.checkbox(
                                                        "I understand the MC expected P&L is negative and want to preview anyway",
                                                        key=proceed_key,
                                                    )
                                                    if not proceed_anyway:
                                                        st.info("Check the box above to preview anyway, or choose a different candidate.")
                                                        st.stop()
                                                with st.spinner("Previewing entry order..."):
                                                    preview_result = trader.preview_order(order)
                                                
                                                if preview_result['status'] == 'preview_success':
                                                    st.session_state.preview_results['preview_entry'] = preview_result
                                                    st.rerun()
                                                else:
                                                    st.error(f"Preview failed: {preview_result.get('message', 'Unknown error')}")
                                            else:
                                                st.error("Schwab client not available")
                                        else:
                                            st.error("Schwab provider not active")
                                    except Exception as e:
                                        st.error(f"Error: {str(e)}")
                            
                            with col_dl_entry:
                                with open(result['filepath'], 'r') as f:
                                    order_json = f.read()
                                
                                st.download_button(
                                    label="⬇️ Download",
                                    data=order_json,
                                    file_name=result['filepath'].split('/')[-1],
                                    mime="application/json",
                                    key="download_entry_btn",
                                    width='stretch'
                                )
                        
                        with col_exit:
                            if exit_result:
                                # Single exit order (includes COLLAR atomic exit)
                                st.write(f"**📥 EXIT Order ({profit_capture_pct}% profit target)**")
                                st.code(exit_result['filepath'], language=None)
                                
                                with st.expander("📄 Exit Order Details"):
                                    st.text(format_order_summary(exit_order))
                                    st.json(exit_order)
                                
                                # Check for preview result
                                    if 'preview_exit' in st.session_state.preview_results:
                                        preview_result = st.session_state.preview_results['preview_exit']
                                        st.success("✅ Exit order preview received!")
                                        with st.expander("📊 Preview Details", expanded=True):
                                            preview_data = preview_result['preview']
                                            if isinstance(preview_data, dict):
                                                if 'commission' in preview_data:
                                                    st.metric("Commission", f"${preview_data['commission']:.2f}")
                                                if 'estimatedTotalAmount' in preview_data:
                                                    st.metric("Est. Cost", f"${preview_data['estimatedTotalAmount']:.2f}")
                                                if 'buyingPowerEffect' in preview_data:
                                                    st.metric("Buying Power Effect", f"${preview_data['buyingPowerEffect']:.2f}")
                                                st.json(preview_data)
                                            else:
                                                st.json(preview_data)
                                    
                                    # Preview and download buttons
                                    col_preview_exit, col_dl_exit = st.columns(2)
                                    
                                    with col_preview_exit:
                                        if st.button("🔍 Preview", key="preview_exit_btn", width='stretch'):
                                            try:
                                                from providers.schwab_trading import SchwabTrader
                                                from providers.schwab import SchwabClient
                                                
                                                if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE and PROVIDER == "schwab":
                                                    schwab_client = PROVIDER_INSTANCE.client if hasattr(PROVIDER_INSTANCE, 'client') else None
                                                    if schwab_client:
                                                        trader = SchwabTrader(dry_run=False, client=schwab_client)
                                                        # Guardrail: warn and require acknowledgement if MC expected P&L is negative
                                                        mc_expected = None
                                                        try:
                                                            if selected is not None and ('MC_ExpectedPnL' in selected):
                                                                mc_expected = float(selected['MC_ExpectedPnL'])
                                                        except Exception:
                                                            mc_expected = None
                                                        if mc_expected is not None and not pd.isna(mc_expected) and mc_expected < 0:
                                                            st.warning(
                                                                f"🚧 Monte Carlo expected P&L for this position is negative (${mc_expected:,.2f}).\n\n"
                                                                "Previewing an order on a negative-expectation setup may not align with your risk rules."
                                                            )
                                                            proceed_key = "ack_negative_mc_exit"
                                                            proceed_anyway = st.checkbox(
                                                                "I understand the MC expected P&L is negative and want to preview anyway",
                                                                key=proceed_key,
                                                            )
                                                            if not proceed_anyway:
                                                                st.info("Check the box above to preview anyway, or choose a different candidate.")
                                                                st.stop()
                                                        with st.spinner("Previewing exit order..."):
                                                            preview_result = trader.preview_order(exit_order)
                                                        
                                                        if preview_result['status'] == 'preview_success':
                                                            st.session_state.preview_results['preview_exit'] = preview_result
                                                            st.rerun()
                                                        else:
                                                            st.error(f"Preview failed: {preview_result.get('message', 'Unknown error')}")
                                                    else:
                                                        st.error("Schwab client not available")
                                                else:
                                                    st.error("Schwab provider not active")
                                            except Exception as e:
                                                st.error(f"Error: {str(e)}")
                                    
                                    with col_dl_exit:
                                        with open(exit_result['filepath'], 'r') as f:
                                            exit_json = f.read()
                                        
                                        st.download_button(
                                            label="⬇️ Download",
                                            data=exit_json,
                                            file_name=exit_result['filepath'].split('/')[-1],
                                            mime="application/json",
                                            key="download_exit_btn",
                                            width='stretch'
                                        )
                            else:
                                st.info("No exit order generated")
                        
                        # Stop-loss column
                        if col_stop and stop_loss_result:
                            with col_stop:
                                st.write(f"**🛑 STOP-LOSS Order ({risk_multiplier}x loss limit)**")
                                
                                if isinstance(stop_loss_result, dict) and 'call' in stop_loss_result:
                                    # Collar stop-loss
                                    st.code(stop_loss_result['filepath'], language=None)
                                else:
                                    st.code(stop_loss_result['filepath'], language=None)
                                
                                with st.expander("📄 Stop-Loss Details"):
                                    if isinstance(stop_loss_result, dict) and 'call' in stop_loss_result:
                                        st.json(stop_loss_order_call)
                                    else:
                                        st.json(stop_loss_order)
                                
                                # Check for preview result
                                if 'preview_stop_loss' in st.session_state.preview_results:
                                    preview_result = st.session_state.preview_results['preview_stop_loss']
                                    st.success("✅ Stop-loss preview received!")
                                    with st.expander("📊 Preview Details", expanded=True):
                                        preview_data = preview_result['preview']
                                        if isinstance(preview_data, dict):
                                            if 'commission' in preview_data:
                                                st.metric("Commission", f"${preview_data['commission']:.2f}")
                                            if 'estimatedTotalAmount' in preview_data:
                                                st.metric("Est. Cost", f"${preview_data['estimatedTotalAmount']:.2f}")
                                            if 'buyingPowerEffect' in preview_data:
                                                st.metric("Buying Power Effect", f"${preview_data['buyingPowerEffect']:.2f}")
                                            if 'marginRequirement' in preview_data:
                                                st.metric("Margin Requirement", f"${preview_data['marginRequirement']:.2f}")
                                            st.json(preview_data)
                                        else:
                                            st.json(preview_data)
                                
                                # Preview and download buttons
                                col_preview_stop, col_dl_stop = st.columns(2)
                                
                                with col_preview_stop:
                                    if st.button("🔍 Preview", key="preview_stop_loss_btn", width='stretch'):
                                        try:
                                            from providers.schwab_trading import SchwabTrader
                                            from providers.schwab import SchwabClient
                                            
                                            # Select the correct order to preview
                                            order_to_preview = stop_loss_order_call if (isinstance(stop_loss_result, dict) and 'call' in stop_loss_result) else stop_loss_order
                                            
                                            if USE_PROVIDER_SYSTEM and PROVIDER_INSTANCE and PROVIDER == "schwab":
                                                schwab_client = PROVIDER_INSTANCE.client if hasattr(PROVIDER_INSTANCE, 'client') else None
                                                if schwab_client:
                                                    trader = SchwabTrader(dry_run=False, client=schwab_client)
                                                    # Guardrail: warn and require acknowledgement if MC expected P&L is negative
                                                    mc_expected = None
                                                    try:
                                                        if selected is not None and ('MC_ExpectedPnL' in selected):
                                                            mc_expected = float(selected['MC_ExpectedPnL'])
                                                    except Exception:
                                                        mc_expected = None
                                                    if mc_expected is not None and not pd.isna(mc_expected) and mc_expected < 0:
                                                        st.warning(
                                                            f"🚧 Monte Carlo expected P&L for this position is negative (${mc_expected:,.2f}).\n\n"
                                                            "Previewing an order on a negative-expectation setup may not align with your risk rules."
                                                        )
                                                        proceed_key = "ack_negative_mc_stop"
                                                        proceed_anyway = st.checkbox(
                                                            "I understand the MC expected P&L is negative and want to preview anyway",
                                                            key=proceed_key,
                                                        )
                                                        if not proceed_anyway:
                                                            st.info("Check the box above to preview anyway, or choose a different candidate.")
                                                            st.stop()
                                                    with st.spinner("Previewing stop-loss order..."):
                                                        preview_result = trader.preview_order(order_to_preview)
                                                    
                                                    if preview_result['status'] == 'preview_success':
                                                        st.session_state.preview_results['preview_stop_loss'] = preview_result
                                                        st.rerun()
                                                    else:
                                                        st.error(f"Preview failed: {preview_result.get('message', 'Unknown error')}")
                                                else:
                                                    st.error("Schwab client not available")
                                            else:
                                                st.error("Schwab provider not active")
                                        except Exception as e:
                                            st.error(f"Error: {str(e)}")
                                
                                with col_dl_stop:
                                    filepath = stop_loss_result['filepath'] if not isinstance(stop_loss_result, dict) or 'call' not in stop_loss_result else stop_loss_result['filepath']
                                    with open(filepath, 'r') as f:
                                        stop_loss_json = f.read()
                                    
                                    st.download_button(
                                        label="⬇️ Download",
                                        data=stop_loss_json,
                                        file_name=filepath.split('/')[-1],
                                        mime="application/json",
                                        key="download_stop_loss_btn",
                                        width='stretch'
                                    )
                        
                        # Instructions
                        st.divider()
                        if generate_stop_loss:
                            st.info("""
                            **📋 "Set and Forget" with Risk Management:**
                            
                            1. **Submit ENTRY order first** via Schwab (web/mobile/thinkorswim)
                            2. **Wait for fill confirmation** before proceeding
                            3. **Submit BOTH exit orders immediately after fill:**
                               - ✅ Profit-taking exit (captures gains at target)
                               - 🛑 Stop-loss exit (limits losses if trade goes against you)
                            4. **Use GTC duration** for both exit orders
                            5. **Let the market work** - whichever hits first will execute automatically
                            6. **Cancel the other order** once one fills (or let Schwab OCO if supported)
                            
                            💡 **Risk Management:** Stop-loss triggers at 2x max profit loss per runbook best practices.
                            """)
                        else:
                            st.info("""
                            **📋 "Set and Forget" Instructions:**
                            
                            1. **Submit ENTRY order first** via Schwab (web/mobile/thinkorswim)
                            2. **Wait for fill confirmation** before proceeding
                            3. **Submit EXIT order immediately after fill** with GTC duration
                            4. **Monitor position** - exit order will automatically execute at profit target
                            5. **Set calendar reminder** at 7-10 DTE to review if not yet closed
                            
                            💡 **Pro Tip:** Use GTC (Good Till Canceled) duration for exit orders so they remain active until filled or you cancel them.
                            """)
                else:
                    st.info("No contracts available. Run a scan first.")

# --- Tab 7: Risk (Monte Carlo) ---
with tabs[7]:
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
        # CSP/Credit Spreads: 0% drift (cash position, no equity exposure)
        # CC/Collar: 7% drift (realistic equity market assumption)
        # Iron Condor: 0% drift (no stock ownership)
        default_drift = 0.00 if strat_choice_preview in ["CSP", "IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"] else 0.07
        
        mc_drift = st.number_input(
            "Drift (annual, decimal)", 
            value=default_drift, 
            step=0.01, 
            format="%.2f", 
            key="mc_drift_input",
            help="Expected annual return: 0% for CSP/Credit Spreads (no stock), 7% for CC/Collar (equity drift)")
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
            # Optional: model collateral as (strike - premium)
            use_net_collateral = st.checkbox(
                "Use net collateral (strike − premium)",
                value=False,
                key="mc_csp_use_net_collateral",
                help="When enabled, collateral used in ROI is K − premium instead of K."
            )
            params = dict(
                S0=execution_price,  # Use overridden price
                days=int(days_for_mc),
                iv=iv,
                Kp=float(row["Strike"]),
                put_premium=execution_premium,  # Use overridden premium
                div_ps_annual=0.0,
                use_net_collateral=bool(use_net_collateral),
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
        elif strat_choice == "IRON_CONDOR":
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
        
        elif strat_choice == "BULL_PUT_SPREAD":
            # Bull Put Spread: SELL higher put + BUY lower put = NET CREDIT
            # No stock ownership, so default drift = 0.0
            iv = float(row.get("IV", 20.0)) / 100.0  # Convert from percentage to decimal
            
            params = dict(
                S0=execution_price,  # Use overridden price
                days=int(days_for_mc),
                iv=iv,
                sell_strike=float(row["SellStrike"]),
                buy_strike=float(row["BuyStrike"]),
                net_credit=float(row["NetCredit"])
            )
            # Use 0% drift for credit spreads (no stock ownership)
            mc = mc_pnl("BULL_PUT_SPREAD", params, n_paths=int(paths), 
                       mu=0.0, seed=seed)
        
        elif strat_choice == "BEAR_CALL_SPREAD":
            # Bear Call Spread: SELL lower call + BUY higher call = NET CREDIT
            # No stock ownership, so default drift = 0.0
            iv = float(row.get("IV", 20.0)) / 100.0  # Convert from percentage to decimal
            
            params = dict(
                S0=execution_price,  # Use overridden price
                days=int(days_for_mc),
                iv=iv,
                sell_strike=float(row["SellStrike"]),
                buy_strike=float(row["BuyStrike"]),
                net_credit=float(row["NetCredit"])
            )
            # Use 0% drift for credit spreads (no stock ownership)
            mc = mc_pnl("BEAR_CALL_SPREAD", params, n_paths=int(paths), 
                       mu=0.0, seed=seed)
        
        else:
            st.error(f"Unknown strategy: {strat_choice}")
            mc = None

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
            st.altair_chart(base_chart, width='stretch')

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
            st.dataframe(pd.DataFrame(roi_rows), width='stretch')

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
            st.dataframe(pd.DataFrame(summary_rows), width='stretch')

# --- Tab 8: Playbook ---
with tabs[8]:
    st.header("Best‑Practice Playbook")
    st.write("These are practical guardrails you can toggle against in the scanner.")
    for name in ["CSP", "CC", "COLLAR", "IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD"]:
        with st.expander(f"{name} — tips"):
            tips = best_practices(name)
            for t in tips:
                st.markdown(f"- {t}")

# --- Tab 9: Plan & Runbook ---
with tabs[9]:
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
                "COLLAR": df_collar, "IRON_CONDOR": df_iron_condor,
                "BULL_PUT_SPREAD": df_bull_put_spread, "BEAR_CALL_SPREAD": df_bear_call_spread}[strat_choice_rb]

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
        st.dataframe(fit_df, width='stretch')

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
                "Tenor outside the sweet spot. Consider 21–45 DTE (CSP/CC) or 30–60 DTE (Collar/IC).")
        if flags["excess_negative"]:
            warn_msgs.append(
                "Excess ROI vs T‑bills is negative. Consider passing on this trade.")
        if flags["cushion_low"]:
            warn_msgs.append(
                "Sigma cushion is thin (< 1.0σ). Consider moving further OTM or extending tenor.")
        if flags.get("earnings_risk", False):
            warn_msgs.append(
                "Earnings announcement within cycle — expect elevated volatility and gap risk.")
        if flags.get("below_cost_basis", False):
            warn_msgs.append(
                "CC strike is below cost basis — assignment would lock in a loss. Consider higher strike or waiting.")
        if warn_msgs:
            st.subheader("Notes & Cautions")
            for m in warn_msgs:
                st.markdown(f"- {m}")

# --- Tab 10: Stress Test ---
with tabs[10]:
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
        st.dataframe(df_stress, width='stretch')

        st.subheader("P&L vs Price Shock")
        chart = alt.Chart(df_stress).mark_line(point=True).encode(
            x=alt.X("Shock%:Q", title="Shock (%)"),
            y=alt.Y("Total_P&L:Q", title="Total P&L per contract (USD)"),
            tooltip=list(df_stress.columns),
        )
        st.altair_chart(chart, width='stretch')

        worst = float(df_stress["Total_P&L"].min())
        best = float(df_stress["Total_P&L"].max())
        st.caption(
            f"Worst among tests: ${worst:,.0f} • Best among tests: ${best:,.0f}")

st.caption("This tool is for education only. Options involve risk and are not suitable for all investors.")

# --- Tab 11: Overview ---
with tabs[11]:
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
            # Optional toggle for net collateral in quick overview
            use_net_collateral_quick = st.checkbox(
                "Use net collateral (strike − premium)",
                value=False,
                key="overview_csp_use_net_collateral",
                help="When enabled, collateral used in ROI is K − premium instead of K."
            )
            params = dict(
                S0=price,
                days=days_for_mc,
                iv=iv_for_calc,
                Kp=strike,
                put_premium=prem,
                div_ps_annual=0.0,
                use_net_collateral=bool(use_net_collateral_quick),
            )
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

        elif strat_choice == "COLLAR":
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

        elif strat_choice == "IRON_CONDOR":
            # Iron Condor structure
            put_long_strike = float(_safe_float(row.get("PutLongStrike")))
            put_short_strike = float(_safe_float(row.get("PutShortStrike")))
            call_short_strike = float(_safe_float(row.get("CallShortStrike")))
            call_long_strike = float(_safe_float(row.get("CallLongStrike")))
            net_credit = float(_safe_float(row.get("NetCredit")))
            
            # Calculate spread widths and capital requirements
            put_spread_width = put_short_strike - put_long_strike
            call_spread_width = call_long_strike - call_short_strike
            max_spread_width = max(put_spread_width, call_spread_width)
            capital_per_share = max_spread_width - net_credit
            capital = capital_per_share * 100.0
            
            # Calculate max profit and max loss
            max_profit = net_credit * 100.0
            max_loss = capital
            
            # Calculate breakevens
            breakeven_lower = put_short_strike - net_credit
            breakeven_upper = call_short_strike + net_credit
            
            base_rows = [
                ("Strategy", "IRON_CONDOR"),
                ("Ticker", row.get("Ticker")),
                ("Price", f"${price:,.2f}"),
                ("Put Spread", f"${put_long_strike:.0f} / ${put_short_strike:.0f}"),
                ("Call Spread", f"${call_short_strike:.0f} / ${call_long_strike:.0f}"),
                ("Exp", row.get("Exp")),
                ("Days", f"{days}"),
                ("Net Credit", f"${net_credit:.2f}"),
                ("Capital Required", f"${capital:,.0f}"),
                ("Max Profit", f"${max_profit:.0f}"),
                ("Max Loss", f"${max_loss:.0f}"),
                ("Breakeven Lower", f"${breakeven_lower:.2f}"),
                ("Breakeven Upper", f"${breakeven_upper:.2f}"),
                ("IV", f"{iv_raw:.2f}%" if iv_raw ==
                 iv_raw and iv_raw > 0 else "n/a"),
                ("Score", f"{row.get('Score'):.2f}" if row.get(
                    'Score') == row.get('Score') else "n/a"),
            ]
            st.subheader("Structure summary")
            st.table(pd.DataFrame(base_rows, columns=["Field", "Value"]))

            paths = 50000
            days_for_mc = max(1, days)
            iv_for_calc = iv_dec if (
                iv_dec == iv_dec and iv_dec > 0.0) else 0.20
            params = dict(
                S0=price, 
                days=days_for_mc, 
                iv=iv_for_calc,
                put_long_strike=put_long_strike,
                put_short_strike=put_short_strike,
                call_short_strike=call_short_strike,
                call_long_strike=call_long_strike,
                net_credit=net_credit
            )
            # Use neutral drift for Iron Condor (0% annual = market neutral)
            mc = mc_pnl("IRON_CONDOR", params, n_paths=int(paths), mu=0.0, seed=None)

        elif strat_choice == "BULL_PUT_SPREAD":
            # Bull Put Spread structure
            sell_strike = float(_safe_float(row.get("SellStrike")))
            buy_strike = float(_safe_float(row.get("BuyStrike")))
            net_credit = float(_safe_float(row.get("NetCredit")))
            
            # Calculate spread width and capital requirements
            spread_width = sell_strike - buy_strike
            capital_per_share = spread_width - net_credit
            capital = capital_per_share * 100.0
            
            # Calculate max profit and max loss
            max_profit = net_credit * 100.0
            max_loss = capital
            
            # Calculate breakeven
            breakeven = sell_strike - net_credit
            
            # Calculate profit capture targets
            target_50_pct = net_credit * 0.50
            target_75_pct = net_credit * 0.25
            
            base_rows = [
                ("Strategy", "BULL PUT SPREAD"),
                ("Ticker", row.get("Ticker")),
                ("Price", f"${price:,.2f}"),
                ("Sell Strike (short put)", f"${sell_strike:.2f}"),
                ("Buy Strike (long put)", f"${buy_strike:.2f}"),
                ("Spread Width", f"${spread_width:.2f}"),
                ("Exp", row.get("Exp")),
                ("Days", f"{days}"),
                ("Net Credit", f"${net_credit:.2f}"),
                ("Capital Required", f"${capital:,.0f}"),
                ("Max Profit", f"${max_profit:.0f}"),
                ("Max Loss", f"${max_loss:.0f}"),
                ("Breakeven", f"${breakeven:.2f}"),
                ("IV", f"{iv_raw:.2f}%" if iv_raw == iv_raw and iv_raw > 0 else "n/a"),
                ("Score", f"{row.get('Score'):.2f}" if row.get('Score') == row.get('Score') else "n/a"),
                ("—", "—"),
                ("Exit: 50% profit", f"Close spread for ≤ ${target_50_pct:.2f}"),
                ("Exit: 75% profit", f"Close spread for ≤ ${target_75_pct:.2f}"),
            ]
            st.subheader("Structure summary")
            st.table(pd.DataFrame(base_rows, columns=["Field", "Value"]))

            paths = 50000
            days_for_mc = max(1, days)
            iv_for_calc = iv_dec if (iv_dec == iv_dec and iv_dec > 0.0) else 0.20
            params = dict(
                S0=price, 
                days=days_for_mc, 
                iv=iv_for_calc,
                sell_strike=sell_strike,
                buy_strike=buy_strike,
                net_credit=net_credit
            )
            # Use neutral drift for credit spreads (0% = no stock ownership)
            mc = mc_pnl("BULL_PUT_SPREAD", params, n_paths=int(paths), mu=0.0, seed=None)

        elif strat_choice == "BEAR_CALL_SPREAD":
            # Bear Call Spread structure
            sell_strike = float(_safe_float(row.get("SellStrike")))
            buy_strike = float(_safe_float(row.get("BuyStrike")))
            net_credit = float(_safe_float(row.get("NetCredit")))
            
            # Calculate spread width and capital requirements
            spread_width = buy_strike - sell_strike
            capital_per_share = spread_width - net_credit
            capital = capital_per_share * 100.0
            
            # Calculate max profit and max loss
            max_profit = net_credit * 100.0
            max_loss = capital
            
            # Calculate breakeven
            breakeven = sell_strike + net_credit
            
            # Calculate profit capture targets
            target_50_pct = net_credit * 0.50
            target_75_pct = net_credit * 0.25
            
            base_rows = [
                ("Strategy", "BEAR CALL SPREAD"),
                ("Ticker", row.get("Ticker")),
                ("Price", f"${price:,.2f}"),
                ("Sell Strike (short call)", f"${sell_strike:.2f}"),
                ("Buy Strike (long call)", f"${buy_strike:.2f}"),
                ("Spread Width", f"${spread_width:.2f}"),
                ("Exp", row.get("Exp")),
                ("Days", f"{days}"),
                ("Net Credit", f"${net_credit:.2f}"),
                ("Capital Required", f"${capital:,.0f}"),
                ("Max Profit", f"${max_profit:.0f}"),
                ("Max Loss", f"${max_loss:.0f}"),
                ("Breakeven", f"${breakeven:.2f}"),
                ("IV", f"{iv_raw:.2f}%" if iv_raw == iv_raw and iv_raw > 0 else "n/a"),
                ("Score", f"{row.get('Score'):.2f}" if row.get('Score') == row.get('Score') else "n/a"),
                ("—", "—"),
                ("Exit: 50% profit", f"Close spread for ≤ ${target_50_pct:.2f}"),
                ("Exit: 75% profit", f"Close spread for ≤ ${target_75_pct:.2f}"),
            ]
            st.subheader("Structure summary")
            st.table(pd.DataFrame(base_rows, columns=["Field", "Value"]))

            paths = 50000
            days_for_mc = max(1, days)
            iv_for_calc = iv_dec if (iv_dec == iv_dec and iv_dec > 0.0) else 0.20
            params = dict(
                S0=price, 
                days=days_for_mc, 
                iv=iv_for_calc,
                sell_strike=sell_strike,
                buy_strike=buy_strike,
                net_credit=net_credit
            )
            # Use neutral drift for credit spreads (0% = no stock ownership)
            mc = mc_pnl("BEAR_CALL_SPREAD", params, n_paths=int(paths), mu=0.0, seed=None)

        else:
            st.error(f"Unknown strategy: {strat_choice}")
            mc = {}

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
            st.altair_chart(chart, width='stretch')

        st.caption(
            "Loss probabilities based on a GBM simulation with 50k paths, IV defaulted to 20% if missing, and 1 day used when DTE is 0.")

# --- Tab 12: Roll Analysis ---
with tabs[12]:
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
                            width='stretch',
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
