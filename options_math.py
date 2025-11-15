"""
Options Math Module - Black-Scholes, Greeks, and Monte Carlo

This module contains pure mathematical functions for options pricing and risk analysis.
Extracted from strategy_lab.py for better code organization and testability.

Functions:
- Black-Scholes pricing (calls and puts)
- Greeks calculations (delta, gamma, theta, vega)
- Monte Carlo P&L simulation
- Expected move calculations
- Utility functions for pricing and spreads
"""

import math
import numpy as np
import pandas as pd
import yfinance as yf
from functools import lru_cache
from datetime import datetime


# ----------------------------- Helper Functions -----------------------------

def _safe_float(x, default=float("nan")):
    """Safely convert to float, returning default if conversion fails."""
    try:
        return float(x)
    except Exception:
        return default


def _norm_cdf(x):
    """Standard normal cumulative distribution function.

    Accepts scalars or numpy arrays. Uses vectorized numpy.erf when possible.
    """
    x_arr = np.asarray(x, dtype=float)
    # Prefer numpy's erf if available (fast ufunc). Some builds may not expose np.erf.
    np_erf = getattr(np, "erf", None)
    if np_erf is not None:
        return 0.5 * (1.0 + np_erf(x_arr / np.sqrt(2.0)))
    # Robust fallback: vectorize math.erf over numpy arrays
    v_erf = np.vectorize(math.erf, otypes=[float])
    return 0.5 * (1.0 + v_erf(x_arr / np.sqrt(2.0)))


# ----------------------------- Black-Scholes & Greeks -----------------------------

def _bs_d1_d2(S, K, r, sigma, T, q=0.0):
    """Calculate d1 and d2 for Black-Scholes formula (Merton with dividend yield q)."""
    if S <= 0 or K <= 0 or sigma <= 0 or T <= 0:
        return float("nan"), float("nan")
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / \
            (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return d1, d2
    except Exception:
        return float("nan"), float("nan")


def bs_call_price(S, K, r, q, sigma, T):
    """
    Black-Scholes call option price with continuous dividend yield.
    
    Args:
        S: Stock price
        K: Strike price
        r: Risk-free rate (annualized, decimal)
        q: Dividend yield (annualized, decimal)
        sigma: Volatility (annualized, decimal)
        T: Time to expiration (years)
    
    Returns:
        Call option price
    """
    # Guard tiny or zero time
    T = max(T, 1e-6)
    d1, d2 = _bs_d1_d2(S, K, r, sigma, T, q)
    if not (d1 == d1 and d2 == d2):  # NaN guard
        return max(0.0, S - K)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    return S * disc_q * _norm_cdf(d1) - K * disc_r * _norm_cdf(d2)


def bs_put_price(S, K, r, q, sigma, T):
    """
    Black-Scholes put option price with continuous dividend yield.
    
    Args:
        S: Stock price
        K: Strike price
        r: Risk-free rate (annualized, decimal)
        q: Dividend yield (annualized, decimal)
        sigma: Volatility (annualized, decimal)
        T: Time to expiration (years)
    
    Returns:
        Put option price
    """
    T = max(T, 1e-6)
    d1, d2 = _bs_d1_d2(S, K, r, sigma, T, q)
    if not (d1 == d1 and d2 == d2):
        return max(0.0, K - S)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    return K * disc_r * _norm_cdf(-d2) - S * disc_q * _norm_cdf(-d1)


def call_delta(S, K, r, sigma, T, q=0.0):
    """
    Call option delta (rate of change with respect to underlying price).
    
    Returns:
        Delta value (0 to 1 for calls)
    """
    d1, _ = _bs_d1_d2(S, K, r, sigma, T, q)
    if d1 != d1:  # NaN check
        return float("nan")
    disc_q = math.exp(-q * T)
    return disc_q * _norm_cdf(d1)


def put_delta(S, K, r, sigma, T, q=0.0):
    """
    Put option delta (rate of change with respect to underlying price).
    
    Returns:
        Delta value (-1 to 0 for puts)
    """
    cd = call_delta(S, K, r, sigma, T, q)
    if cd == cd:
        return cd - 1.0
    return float("nan")


def option_gamma(S, K, r, sigma, T, q=0.0):
    """
    Option gamma (rate of change of delta with respect to underlying price).
    Same for calls and puts.
    
    Returns:
        Gamma value
    """
    if sigma <= 0 or T <= 0 or S <= 0:
        return float("nan")
    d1, _ = _bs_d1_d2(S, K, r, sigma, T, q)
    if d1 != d1:
        return float("nan")
    disc_q = math.exp(-q * T)
    phi_d1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * d1 * d1)
    return (disc_q * phi_d1) / (S * sigma * math.sqrt(T))


def option_vega(S, K, r, sigma, T, q=0.0):
    """
    Option vega (sensitivity of option price to changes in volatility).
    Same for calls and puts.
    
    Returns:
        Vega per 1% change in volatility
    """
    if sigma <= 0 or T <= 0 or S <= 0:
        return float("nan")
    d1, _ = _bs_d1_d2(S, K, r, sigma, T, q)
    if d1 != d1:
        return float("nan")
    disc_q = math.exp(-q * T)
    phi_d1 = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * d1 * d1)
    # Vega = S * phi(d1) * sqrt(T) * e^(-q*T)
    # Divide by 100 to get per 1% change in IV
    return (S * disc_q * phi_d1 * math.sqrt(T)) / 100.0


def put_theta(S, K, r, sigma, T, q=0.0):
    """
    Put option theta (daily time decay).
    Negative value = decay helps seller.
    
    Returns:
        Theta in dollars per day
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
    Call option theta (daily time decay).
    Negative value = decay helps seller.
    
    Returns:
        Theta in dollars per day
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
    
    Args:
        S: Stock price
        iv: Implied volatility (annualized, decimal)
        T: Time to expiration (years)
    
    Returns:
        Expected move: S * σ * sqrt(T)
    """
    if iv != iv or T <= 0:
        return float("nan")
    return S * iv * math.sqrt(T)


# ----------------------------- Pricing Utilities -----------------------------

def compute_spread_pct(bid, ask, mid):
    """
    Calculate bid-ask spread as percentage of mid price.
    
    Returns:
        Spread percentage, or None if unable to calculate
    """
    bid = _safe_float(bid)
    ask = _safe_float(ask)
    mid = _safe_float(mid)
    if bid == bid and ask == ask and bid > 0 and ask > 0 and mid > 0:
        return ((ask - bid) / mid) * 100.0
    return None  # None => unknown; don't auto-reject


# ----------------------------- ROI Utilities -----------------------------

def safe_annualize_roi(cycle_roi, days, clip_low: float = -50.0, clip_high: float = 700.0):
    """
    Numerically stable annualization of ROI for a cycle over `days` days.

    Computes (1 + cycle_roi) ** (365 / days) - 1 using log1p/expm1 with clipping
    to avoid overflow/underflow. Vectorized over `cycle_roi` (array-like or scalar).

    Args:
        cycle_roi: float or array-like of per-cycle ROI (e.g., P&L / capital)
        days: int > 0, number of days in the cycle
        clip_low: lower bound for the exponent's natural log (default -50)
        clip_high: upper bound for the exponent's natural log (default 700)

    Returns:
        Annualized ROI, same shape as `cycle_roi`. Returns NaN when days <= 0,
        or when (1 + cycle_roi) <= 0 (invalid base).
    """
    import numpy as _np

    arr = _np.asarray(cycle_roi, dtype=float)
    if days is None or float(days) <= 0.0:
        out = _np.full_like(arr, _np.nan)
        return out.item() if out.shape == () else out

    base = 1.0 + arr
    ln_base = _np.where(base > 0.0, _np.log1p(arr), _np.nan)
    ln_val = (365.0 / float(days)) * ln_base
    ln_val = _np.clip(ln_val, float(clip_low), float(clip_high))
    out = _np.expm1(ln_val)
    return out.item() if out.shape == () else out


def trailing_dividend_info(ticker_obj, S):
    """
    Calculate trailing 12-month dividend information.
    
    Args:
        ticker_obj: yfinance Ticker object
        S: Current stock price
    
    Returns:
        tuple: (div_per_share_annual, trailing_yield_decimal)
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


@lru_cache(maxsize=512)
def get_earnings_date_cached(ticker_symbol: str, use_alpha_vantage: bool = False):
    """
    Cached wrapper for earnings date lookup. Uses ticker symbol string for caching.
    This eliminates duplicate lookups when multiple strategies scan the same ticker.
    
    Cache is valid for the duration of the Python process (typically one Streamlit session).
    For overnight runs, restart the app to refresh earnings data.
    
    Args:
        ticker_symbol: Stock ticker symbol (string)
        use_alpha_vantage: If True, fall back to Alpha Vantage when Yahoo fails.
    
    Returns:
        Earnings date or None if unavailable.
    """
    stock = yf.Ticker(ticker_symbol)
    return get_earnings_date(stock, use_alpha_vantage=use_alpha_vantage)


def get_earnings_date(stock: yf.Ticker, use_alpha_vantage=False):
    """
    Try multiple methods to get earnings date from yfinance.
    Optionally falls back to Alpha Vantage if Yahoo Finance has no data.
    
    NOTE: Use get_earnings_date_cached() instead for better performance when
    scanning multiple strategies on the same ticker.
    
    Args:
        stock: yfinance Ticker object
        use_alpha_vantage: If True, fall back to Alpha Vantage when Yahoo fails.
                          Default False to preserve API quota during screening.
    
    Returns:
        Earnings date or None if unavailable.
    """
    import warnings
    import sys
    import io
    import logging
    yahoo_date = None
    
    try:
        # Method 1: Try the calendar attribute
        # Suppress warnings/errors from yfinance (e.g., 404 for ETFs with no earnings)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Suppress yfinance logger
            yf_logger = logging.getLogger('yfinance')
            old_level = yf_logger.level
            yf_logger.setLevel(logging.CRITICAL)
            # Also suppress stdout/stderr output (HTTP errors from yfinance)
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
            try:
                cal = stock.calendar
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                yf_logger.setLevel(old_level)
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


# ----------------------------- Monte Carlo Simulation -----------------------------

def gbm_terminal_prices(S0, mu, sigma, T_years, n_paths, rng=None):
    """
    Generate terminal stock prices using Geometric Brownian Motion.
    
    Args:
        S0: Initial stock price
        mu: Drift (expected return, annualized decimal)
        sigma: Volatility (annualized decimal)
        T_years: Time horizon (years)
        n_paths: Number of simulation paths
        rng: Random number generator (optional)
    
    Returns:
        Array of terminal prices
    """
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

    Args:
        strategy: Strategy type ("CSP", "CC", "COLLAR", "IRON_CONDOR", "BULL_PUT_SPREAD", "BEAR_CALL_SPREAD")
        params: Dictionary of strategy parameters
        n_paths: Number of Monte Carlo paths
        mu: Expected return (drift, annualized decimal)
        seed: Random seed for reproducibility
        rf: Risk-free rate (annualized decimal)
    
    Returns:
        Dictionary with pnl_paths, roi_ann_paths, and summary statistics
    """
    S0 = float(params["S0"])
    days = int(params["days"])
    # Time horizon for price simulation; allow T=0 for same-day to maintain P&L logic
    T = max(days, 0) / 365.0
    # Ensure non-degenerate volatility for stochastic paths
    sigma = float(params.get("iv", 0.20))
    # Clamp volatility to reasonable bounds to avoid numerical issues
    if not (sigma == sigma) or sigma <= 0.0:
        sigma = 0.20
    sigma = max(1e-6, min(sigma, 3.0))
    rng = np.random.default_rng(seed)
    S_T = gbm_terminal_prices(S0, mu, sigma, T, n_paths, rng)

    div_ps_annual = float(params.get("div_ps_annual", 0.0))
    div_ps_period = div_ps_annual * (days / 365.0)

    if strategy == "CSP":
        Kp = float(params["Kp"])
        Pp = float(params["put_premium"])
        # Choose collateral base: full strike (default) or net of premium if requested
        use_net_collateral = bool(params.get("use_net_collateral", False))
        collateral_base = Kp - Pp if use_net_collateral else Kp
        collateral_base = max(collateral_base, 1e-6)
        pnl_per_share = Pp - np.maximum(0.0, Kp - S_T)
        # Add continuous risk-free interest on collateral base
        pnl_per_share += collateral_base * (np.exp(rf * T) - 1.0)
        capital_per_share = collateral_base

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
    
    elif strategy == "FENCE":
        # Two-leg structure: short call + long put, no stock position
        # P&L per share at expiration (ignoring borrow/dividends):
        #   = -max(0, S_T - Kc) + max(0, Kp - S_T) + (call_premium - put_premium)
        Kc = float(params["Kc"])
        Pc = float(params["call_premium"])  # credit from short call
        Kp = float(params["Kp"])
        Pp = float(params["put_premium"])   # debit for long put
        net_credit = float(Pc) - float(Pp)
        pnl_per_share = (-np.maximum(0.0, S_T - Kc)
                         + np.maximum(0.0, Kp - S_T)
                         + net_credit)
        # There is no bounded max loss on the upside; capital is undefined here.
        # Return NaN capital so ROI is suppressed while still providing P&L stats.
        capital_per_share = float("nan")
    
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
        capital_per_share = max(max_spread_width - net_credit, 1e-6)
    
    elif strategy == "BULL_PUT_SPREAD":
        # Bull Put Spread: SELL higher strike put + BUY lower strike put = NET CREDIT
        # Profit if stock stays above sell strike
        sell_strike = float(params["sell_strike"])  # Short put (higher strike)
        buy_strike = float(params["buy_strike"])    # Long put (lower strike)
        net_credit = float(params["net_credit"])
        
        # P&L calculation for Bull Put Spread
        # Start with net credit received
        pnl_per_share = np.full_like(S_T, net_credit)
        
        # Subtract spread loss if price < sell strike
        # Loss = max(0, sell_strike - S_T) - max(0, buy_strike - S_T)
        # This simplifies to: min(sell_strike - S_T, sell_strike - buy_strike) when S_T < sell_strike
        spread_loss = np.maximum(0.0, sell_strike - S_T) - np.maximum(0.0, buy_strike - S_T)
        pnl_per_share -= spread_loss
        
        # Capital at risk = max loss = spread width - net credit
        spread_width = sell_strike - buy_strike
        capital_per_share = max(spread_width - net_credit, 1e-6)
    
    elif strategy == "BEAR_CALL_SPREAD":
        # Bear Call Spread: SELL lower strike call + BUY higher strike call = NET CREDIT
        # Profit if stock stays below sell strike
        sell_strike = float(params["sell_strike"])  # Short call (lower strike)
        buy_strike = float(params["buy_strike"])    # Long call (higher strike)
        net_credit = float(params["net_credit"])
        
        # P&L calculation for Bear Call Spread
        # Start with net credit received
        pnl_per_share = np.full_like(S_T, net_credit)
        
        # Subtract spread loss if price > sell strike
        # Loss = max(0, S_T - sell_strike) - max(0, S_T - buy_strike)
        # This simplifies to: min(S_T - sell_strike, buy_strike - sell_strike) when S_T > sell_strike
        spread_loss = np.maximum(0.0, S_T - sell_strike) - np.maximum(0.0, S_T - buy_strike)
        pnl_per_share -= spread_loss
        
        # Capital at risk = max loss = spread width - net credit
        spread_width = buy_strike - sell_strike
        capital_per_share = max(spread_width - net_credit, 1e-6)
    
    elif strategy == "PMCC":
        # Poor Man's Covered Call (Diagonal): Long deep ITM LEAPS call + Short near-term call
        # Params:
        #   long_call_strike, long_call_cost, long_days_total, long_iv
        #   short_call_strike, short_call_premium, short_days (sim horizon), short_iv
        # P&L at short expiry approximated as (value of long call with remaining time - initial cost)
        # + short call premium - intrinsic short call payoff.
        long_K = float(params["long_call_strike"])
        long_cost = float(params["long_call_cost"])  # debit paid per share
        long_days_total = int(params.get("long_days_total", days))
        long_remaining_days = max(long_days_total - days, 1)
        short_K = float(params["short_call_strike"])
        short_prem = float(params["short_call_premium"])  # credit per share
        # IV handling
        long_iv = float(params.get("long_iv", sigma))
        short_iv = float(params.get("short_iv", sigma))
        # Remaining time for long call after short leg expires
        T_long_remaining = long_remaining_days / 365.0
        # Reprice long call at horizon for each path using Black-Scholes approximation
        # Use same drifted terminal prices S_T already simulated.
        # Avoid importing bs_call_price here (would create circular if renamed); replicate minimal formula.
        def _reprice_long_call(S_T_path):
            # Use Black-Scholes with dividend yield 0 for simplicity
            S = S_T_path
            K = long_K
            vol = max(1e-6, min(long_iv, 3.0))
            T_rem = max(T_long_remaining, 1e-6)
            d1 = (np.log(S / K) + (rf + 0.5 * vol**2) * T_rem) / (vol * np.sqrt(T_rem))
            d2 = d1 - vol * np.sqrt(T_rem)
            call_val = S * _norm_cdf(d1) - K * np.exp(-rf * T_rem) * _norm_cdf(d2)
            return call_val
        long_call_vals = _reprice_long_call(S_T)
        intrinsic_short = np.maximum(0.0, S_T - short_K)
        pnl_per_share = (long_call_vals - long_cost) + short_prem - intrinsic_short
        # Capital at risk approximated as net debit: long cost - short premium
        capital_per_share = max(long_cost - short_prem, 1e-6)

    elif strategy == "SYNTHETIC_COLLAR":
        # Synthetic Collar: Long deep ITM call (stock proxy) + Long protective put + Short OTM call
        # Params:
        #   long_call_strike, long_call_cost, long_days_total, long_iv
        #   put_strike, put_cost, put_iv
        #   short_call_strike, short_call_premium, short_iv
        long_K = float(params["long_call_strike"])
        long_cost = float(params["long_call_cost"])  # debit per share
        long_days_total = int(params.get("long_days_total", days))
        long_remaining_days = max(long_days_total - days, 1)
        put_K = float(params["put_strike"])
        put_cost = float(params["put_cost"])  # debit
        short_K = float(params["short_call_strike"])
        short_prem = float(params["short_call_premium"])  # credit
        long_iv = float(params.get("long_iv", sigma))
        put_iv = float(params.get("put_iv", sigma))
        short_iv = float(params.get("short_iv", sigma))
        # At the horizon (short leg expiry), the LEAPS call still has time remaining,
        # while the protective put expires now. Reflect that explicitly:
        T_long_remaining = long_remaining_days / 365.0
        T_put_remaining = 1e-6  # effectively intrinsic at short expiry

        def _bs_call_val(S, K, vol, T_rem):
            vol = max(1e-6, min(vol, 3.0))
            T_rem = max(T_rem, 1e-6)
            d1 = (np.log(S / K) + (rf + 0.5 * vol**2) * T_rem) / (vol * np.sqrt(T_rem))
            d2 = d1 - vol * np.sqrt(T_rem)
            return S * _norm_cdf(d1) - K * np.exp(-rf * T_rem) * _norm_cdf(d2)
        def _bs_put_val(S, K, vol, T_rem):
            vol = max(1e-6, min(vol, 3.0))
            T_rem = max(T_rem, 1e-6)
            d1 = (np.log(S / K) + (rf + 0.5 * vol**2) * T_rem) / (vol * np.sqrt(T_rem))
            d2 = d1 - vol * np.sqrt(T_rem)
            # Put via parity
            call_val = S * _norm_cdf(d1) - K * np.exp(-rf * T_rem) * _norm_cdf(d2)
            put_val = call_val - S + K * np.exp(-rf * T_rem)
            return put_val
        long_call_vals = _bs_call_val(S_T, long_K, long_iv, T_long_remaining)
        put_vals = _bs_put_val(S_T, put_K, put_iv, T_put_remaining)
        intrinsic_short = np.maximum(0.0, S_T - short_K)
        pnl_per_share = (long_call_vals - long_cost) + (put_vals - put_cost) + short_prem - intrinsic_short
        capital_per_share = max(long_cost + put_cost - short_prem, 1e-6)

    else:
        raise ValueError(f"Unknown strategy for MC: {strategy}")

    pnl_contract = 100.0 * pnl_per_share
    capital_contract = 100.0 * capital_per_share

    with np.errstate(invalid="ignore", divide="ignore", over="ignore", under="ignore"):
        roi_cycle = pnl_contract / capital_contract
        roi_ann = safe_annualize_roi(roi_cycle, days)

    out = {
        "S_T": S_T,
        "pnl_paths": pnl_contract,
        "roi_ann_paths": roi_ann,
        "collateral": capital_contract,
        "capital_per_share": capital_per_share,
        "days": days,
        "paths": int(n_paths),
    }
    
    # Calculate statistics for both P&L and annualized ROI
    for label, arr in [("pnl", pnl_contract), ("roi_ann", roi_ann)]:
        arr_clean = arr[np.isfinite(arr)]
        if arr_clean.size == 0:
            out[f"{label}_expected"] = float("nan")
            out[f"{label}_std"] = float("nan")
            out[f"{label}_p5"] = float("nan")
            out[f"{label}_p50"] = float("nan")
            out[f"{label}_p95"] = float("nan")
            out[f"{label}_min"] = float("nan")
            out[f"{label}_max"] = float("nan")
        else:
            out[f"{label}_expected"] = float(np.mean(arr_clean))
            out[f"{label}_std"] = float(np.std(arr_clean))
            out[f"{label}_p5"] = float(np.percentile(arr_clean, 5))
            out[f"{label}_p50"] = float(np.percentile(arr_clean, 50))
            out[f"{label}_p95"] = float(np.percentile(arr_clean, 95))
            out[f"{label}_min"] = float(np.min(arr_clean))
            out[f"{label}_max"] = float(np.max(arr_clean))
    
    # Calculate Sharpe ratio
    pnl_clean = pnl_contract[np.isfinite(pnl_contract)]
    if days > 0 and pnl_clean.size > 0 and np.std(pnl_clean) > 0:
        # Assuming risk-free rate ~= 0 for simplicity (or use mu)
        sharpe = np.mean(pnl_clean) / np.std(pnl_clean) * np.sqrt(365.0 / days)
        out["sharpe"] = float(sharpe)
    else:
        out["sharpe"] = float("nan")

    # Provide a compact summary expected by some tests
    roi_clean = roi_ann[np.isfinite(roi_ann)] if isinstance(roi_ann, np.ndarray) else np.array([])
    out["summary"] = {
        "mean_pnl_per_share": float(np.mean(pnl_per_share)) if np.isfinite(np.mean(pnl_per_share)) else float("nan"),
        "mean_roi_ann": float(np.mean(roi_clean)) if roi_clean.size > 0 else float("nan"),
    }

    # --- Theoretical min payoff override for bounded credit strategies ---
    # In rare cases with low volatility + few MC paths the tail (max loss) might not be sampled,
    # leading to an unrealistic pnl_min equal to the net credit. Expose true worst-case risk.
    try:
        # Only override if distribution shows variance (i.e., we actually sampled some loss paths)
        pnl_std = out.get("pnl_std")
        def _should_override(sampled_min, theoretical_min, max_profit=None):
            if not np.isfinite(theoretical_min):
                return False
            if not np.isfinite(sampled_min) or sampled_min > theoretical_min + 1e-9:
                # If all sampled paths are at max profit (std ~ 0 and sampled_min ≈ max_profit) skip override
                if max_profit is not None and np.isfinite(max_profit):
                    if pnl_std is not None and np.isfinite(pnl_std) and pnl_std < 1e-6 and abs(sampled_min - max_profit) < 1e-3:
                        return False
                return True
            return False

        if strategy == "BEAR_CALL_SPREAD":
            sell_strike = float(params["sell_strike"])
            buy_strike = float(params["buy_strike"])
            net_credit = float(params["net_credit"])
            spread_width = buy_strike - sell_strike
            theoretical_min = (net_credit - spread_width) * 100.0
            sampled_min = out.get("pnl_min", float("nan"))
            max_profit = net_credit * 100.0
            if _should_override(sampled_min, theoretical_min, max_profit=max_profit):
                out["pnl_min"] = theoretical_min
                capital = capital_contract if np.isfinite(capital_contract) and capital_contract > 0 else (spread_width - net_credit) * 100.0
                if np.isfinite(capital) and capital > 0:
                    out["roi_ann_min"] = safe_annualize_roi(theoretical_min / capital, days)
                out["pnl_min_theoretical"] = theoretical_min
        elif strategy == "BULL_PUT_SPREAD":
            sell_strike = float(params["sell_strike"])
            buy_strike = float(params["buy_strike"])
            net_credit = float(params["net_credit"])
            spread_width = sell_strike - buy_strike
            theoretical_min = (net_credit - spread_width) * 100.0
            sampled_min = out.get("pnl_min", float("nan"))
            max_profit = net_credit * 100.0
            if _should_override(sampled_min, theoretical_min, max_profit=max_profit):
                out["pnl_min"] = theoretical_min
                capital = capital_contract if np.isfinite(capital_contract) and capital_contract > 0 else (spread_width - net_credit) * 100.0
                if np.isfinite(capital) and capital > 0:
                    out["roi_ann_min"] = safe_annualize_roi(theoretical_min / capital, days)
                out["pnl_min_theoretical"] = theoretical_min
        elif strategy == "IRON_CONDOR":
            put_short = float(params["put_short_strike"])
            put_long = float(params["put_long_strike"])
            call_short = float(params["call_short_strike"])
            call_long = float(params["call_long_strike"])
            net_credit = float(params["net_credit"])
            put_width = put_short - put_long
            call_width = call_long - call_short
            worst_width = max(put_width, call_width)
            theoretical_min = (net_credit - worst_width) * 100.0
            sampled_min = out.get("pnl_min", float("nan"))
            if _should_override(sampled_min, theoretical_min):
                out["pnl_min"] = theoretical_min
                capital = capital_contract if np.isfinite(capital_contract) and capital_contract > 0 else (worst_width - net_credit) * 100.0
                if np.isfinite(capital) and capital > 0:
                    out["roi_ann_min"] = safe_annualize_roi(theoretical_min / capital, days)
                out["pnl_min_theoretical"] = theoretical_min
    except Exception:
        pass
    
    return out
