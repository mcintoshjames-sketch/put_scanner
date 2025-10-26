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
# - Data: yfinance (non-pro). Quotes can be delayed, greeks limited.
# - This is educational tooling, not advice. Verify prior to trading.

import math
from datetime import datetime, timedelta, timezone

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import yfinance as yf


# ----------------------------- Utils -----------------------------

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
    b = _safe_float(bid); a = _safe_float(ask); l = _safe_float(last, 0.0)
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
    b = _safe_float(bid); a = _safe_float(ask); l = _safe_float(last, 0.0)
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
        amts  = list(divs.iloc[-4:])
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

    
def _safe_int(x, default=0):
    try:
        f = float(x)
        if f != f:  # NaN check
            return default
        return int(f)
    except Exception:
        return default


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
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
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
    return _norm_cdf(d1)

def put_delta(S, K, r, sigma, T, q=0.0):
    cd = call_delta(S, K, r, sigma, T, q)
    if cd == cd:
        return cd - 1.0
    return float("nan")


def expected_move(S, iv, T):
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

def get_earnings_date(stock: yf.Ticker):
    try:
        cal = stock.calendar
        if cal is not None and not cal.empty:
            if "Earnings Date" in cal.index:
                ed = cal.loc["Earnings Date"]
                if hasattr(ed, "__iter__"):
                    return pd.to_datetime(ed[0]).date()
                return pd.to_datetime(ed).date()
            if "Earnings Date" in cal.columns:
                ed = cal["Earnings Date"].iloc[0]
                if hasattr(ed, "__iter__"):
                    return pd.to_datetime(ed[0]).date()
                return pd.to_datetime(ed).date()
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
    Adds risk-free carry on CSP collateral: + rf * K * (D/365) * 100 per contract.
    For CC/Collar we do NOT add rf to stock capital (you already get stock exposure + dividends).
    """
    S0 = float(params["S0"])
    days = int(params["days"])
    T = days / 365.0
    sigma = float(params.get("iv", 0.20))
    rng = np.random.default_rng(seed)
    S_T = gbm_terminal_prices(S0, mu, sigma, T, n_paths, rng)

    div_ps_annual = float(params.get("div_ps_annual", 0.0))
    div_ps_period = div_ps_annual * (days / 365.0)

    if strategy == "CSP":
        Kp = float(params["Kp"])
        Pp = float(params["put_premium"])
        pnl_per_share = Pp - np.maximum(0.0, Kp - S_T)
        # add cash yield on collateral per share
        pnl_per_share += rf * Kp * (days / 365.0)
        capital_per_share = Kp

    elif strategy == "CC":
        Kc = float(params["Kc"])
        Pc = float(params["call_premium"])
        pnl_per_share = (S_T - S0) + Pc - np.maximum(0.0, S_T - Kc) + div_ps_period
        capital_per_share = S0

    elif strategy == "COLLAR":
        Kc = float(params["Kc"]); Pc = float(params["call_premium"])
        Kp = float(params["Kp"]); Pp = float(params["put_premium"])
        pnl_per_share = ((S_T - S0)
                         + Pc - np.maximum(0.0, S_T - Kc)
                         - Pp + np.maximum(0.0, Kp - S_T)
                         + div_ps_period)
        capital_per_share = S0
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
        "days": days,
        "paths": int(n_paths),
    }
    for label, arr in [("pnl", pnl_contract), ("roi_ann", roi_ann)]:
        arr_clean = arr[np.isfinite(arr)]
        if arr_clean.size == 0:
            out[f"{label}_expected"] = float("nan")
            out[f"{label}_p5"] = float("nan")
            out[f"{label}_p50"] = float("nan")
            out[f"{label}_p95"] = float("nan")
            out[f"{label}_min"] = float("nan")
        else:
            out[f"{label}_expected"] = float(np.mean(arr_clean))
            out[f"{label}_p5"] = float(np.percentile(arr_clean, 5))
            out[f"{label}_p50"] = float(np.percentile(arr_clean, 50))
            out[f"{label}_p95"] = float(np.percentile(arr_clean, 95))
            out[f"{label}_min"] = float(np.min(arr_clean))
    return out



# -------------------------- Analyzers ----------------------------

def analyze_csp(ticker, *, days_limit, min_otm, min_oi, max_spread, min_roi, min_cushion,
                min_poew, earn_window, risk_free, per_contract_cap=None, bill_yield=0.0):
    stock = yf.Ticker(ticker)
    try:
        S = float(stock.history(period="1d")["Close"].iloc[-1])
    except Exception:
        return pd.DataFrame()

    expirations = list(stock.options or [])
    earn_date = get_earnings_date(stock)
    # dividend yield for q
    div_ps_annual, div_y = trailing_dividend_info(stock, S)
    q = div_y  # continuous dividend yield proxy

    rows = []
    for exp in expirations:
        try:
            ed = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        D = (ed - datetime.now(timezone.utc).date()
).days
        if D <= 0 or D > int(days_limit):
            continue
        if earn_date is not None and abs((earn_date - ed).days) <= int(earn_window):
            continue

        try:
            chain = stock.option_chain(exp).puts
        except Exception:
            continue

        T = D / 365.0
        for _, r in chain.iterrows():
            K = _safe_float(r.get("strike"))
            if not (K == K and K > 0):
                continue

            prem = effective_credit(r.get("bid"), r.get("ask"), r.get("lastPrice"))
            if prem != prem or prem <= 0:
                continue

            iv = _safe_float(r.get("impliedVolatility"), float("nan"))
            d1, d2 = _bs_d1_d2(S, K, risk_free, iv if iv == iv else 0.20, T, q)
            poew = _norm_cdf(d2) if d2 == d2 else float("nan")

            otm_pct = (S - K) / S * 100.0
            if otm_pct < float(min_otm):
                continue

            # ROI on collateral (K) and on net cash (K - prem)
            roi_ann_collat = (prem / K) * (365.0 / D)
            roi_ann_net = (prem / max(K - prem, 1e-9)) * (365.0 / D) if K > prem else float("nan")
            if roi_ann_collat != roi_ann_collat or roi_ann_collat < float(min_roi):
                continue

            oi = _safe_int(r.get("openInterest"), 0)
            if min_oi and oi < int(min_oi):
                continue

            mid = prem
            spread_pct = compute_spread_pct(r.get("bid"), r.get("ask"), mid)
            if (spread_pct is not None) and (spread_pct > float(max_spread)):
                continue

            exp_mv = expected_move(S, iv if iv == iv else 0.20, T)
            cushion_sigma = ((S - K) / exp_mv) if (exp_mv == exp_mv and exp_mv > 0) else float("nan")
            if cushion_sigma == cushion_sigma and cushion_sigma < float(min_cushion):
                continue

            if poew == poew and poew < float(min_poew):
                continue

            collateral = K * 100.0
            if per_contract_cap is not None and collateral > float(per_contract_cap):
                continue

            excess_vs_bills = roi_ann_collat - float(bill_yield)

            # Score: yield + cushion + liquidity
            liq_score = max(0.0, 1.0 - min((spread_pct or 20.0), 20.0) / 20.0)
            score = 0.50 * roi_ann_collat + 0.30 * (min(cushion_sigma, 3.0) / 3.0 if cushion_sigma == cushion_sigma else 0.0) + 0.20 * liq_score

            rows.append({
                "Strategy": "CSP",
                "Ticker": ticker, "Price": round(S, 2), "Exp": exp, "Days": D,
                "Strike": float(K), "Premium": round(prem, 2),
                "OTM%": round(otm_pct, 2),

                # ROI fields (all as % where appropriate)
                "ROI%_ann": round(roi_ann_collat * 100.0, 2),            # primary
                "ROI%_ann_net": round(roi_ann_net * 100.0, 2) if roi_ann_net == roi_ann_net else float("nan"),
                "ROI%_excess_bills": round(excess_vs_bills * 100.0, 2),

                "IV": round(iv * 100.0, 2) if iv == iv else float("nan"),
                "POEW": round(poew, 3) if poew == poew else float("nan"),
                "CushionSigma": round(cushion_sigma, 2) if cushion_sigma == cushion_sigma else float("nan"),
                "Spread%": round(spread_pct, 2) if spread_pct is not None else float("nan"),
                "OI": oi, "Collateral": int(collateral),
                "Score": round(score, 6)
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Score", "ROI%_ann"], ascending=[False, False]).reset_index(drop=True)
    return df



def analyze_cc(ticker, *, days_limit, min_otm, min_oi, max_spread, min_roi,
               earn_window, risk_free, include_dividends=True, bill_yield=0.0):
    stock = yf.Ticker(ticker)
    try:
        S = float(stock.history(period="1d")["Close"].iloc[-1])
    except Exception:
        return pd.DataFrame()
    expirations = list(stock.options or [])
    earn_date = get_earnings_date(stock)

    div_ps_annual, div_y = trailing_dividend_info(stock, S)  # per share annual
    rows = []
    for exp in expirations:
        try:
            ed = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        D = (ed - datetime.now(timezone.utc).date()
).days
        if D <= 0 or D > int(days_limit):
            continue
        if earn_date is not None and abs((earn_date - ed).days) <= int(earn_window):
            continue

        try:
            chain = stock.option_chain(exp).calls
        except Exception:
            continue

        T = D / 365.0
        for _, r in chain.iterrows():
            K = _safe_float(r.get("strike"))
            if not (K == K):
                continue
            bid = r.get("bid"); ask = r.get("ask"); last = r.get("lastPrice")
            prem = _mid_price(bid, ask, last)
            if prem != prem or prem <= 0:
                continue
            iv = _safe_float(r.get("impliedVolatility"), float("nan"))
            d1, d2 = _bs_d1_d2(S, K, risk_free, iv if iv == iv else 0.20, T)
            poec = _norm_cdf(-d2) if d2 == d2 else float("nan")  # Prob(call expires worthless)
            otm_pct = (K - S) / S * 100.0
            if otm_pct < float(min_otm):
                continue

            # Annualized ROI on stock capital (S)
            roi_ann = (prem / S) * (365.0 / D)
            if include_dividends and div_ps_annual > 0:
                roi_ann += (div_ps_annual / S) * (D / 365.0) * (365.0 / D)  # just adds dividend yield

            if roi_ann != roi_ann or roi_ann < float(min_roi):
                continue

            oi = _safe_int(r.get("openInterest"), 0)
            if min_oi and oi < int(min_oi):
                continue

            mid = prem
            spread_pct = compute_spread_pct(bid, ask, mid)
            if (spread_pct is not None) and (spread_pct > float(max_spread)):
                continue

            exp_mv = expected_move(S, iv if iv == iv else 0.20, T)
            cushion_sigma = ((K - S) / exp_mv) if (exp_mv == exp_mv and exp_mv > 0) else float("nan")

            liq_score = max(0.0, 1.0 - min((spread_pct or 20.0), 20.0) / 20.0)
            score = 0.55 * roi_ann + 0.25 * (min(cushion_sigma, 3.0) / 3.0 if cushion_sigma == cushion_sigma else 0.0) + 0.20 * liq_score

            rows.append({
                "Strategy": "CC",
                "Ticker": ticker, "Price": round(S, 2), "Exp": exp, "Days": D,
                "Strike": float(K), "Premium": round(prem, 2),
                "OTM%": round(otm_pct, 2), "ROI%_ann": round(roi_ann * 100.0, 2),
                "IV": round(iv * 100.0, 2) if iv == iv else float("nan"),
                "POEC": round(poec, 3) if poec == poec else float("nan"),  # keep shares prob
                "CushionSigma": round(cushion_sigma, 2) if cushion_sigma == cushion_sigma else float("nan"),
                "Spread%": round(spread_pct, 2) if spread_pct is not None else float("nan"),
                "OI": oi, "Capital": int(S * 100.0),
                "DivYld%": round(div_y * 100.0, 2),
                "Score": round(score, 6),
                "DivAnnualPS": round(div_ps_annual, 4)
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Score", "ROI%_ann"], ascending=[False, False]).reset_index(drop=True)
    return df


def analyze_collar(ticker, *, days_limit, min_oi, max_spread,
                   call_delta_target, put_delta_target, earn_window, risk_free,
                   include_dividends=True, min_net_credit=None, bill_yield=0.0):
    stock = yf.Ticker(ticker)
    try:
        S = float(stock.history(period="1d")["Close"].iloc[-1])
    except Exception:
        return pd.DataFrame()

    expirations = list(stock.options or [])
    earn_date = get_earnings_date(stock)
    div_ps_annual, div_y = trailing_dividend_info(stock, S)
    rows = []

    for exp in expirations:
        try:
            ed = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        D = (ed - datetime.now(timezone.utc).date()
).days
        if D <= 0 or D > int(days_limit):
            continue
        if earn_date is not None and abs((earn_date - ed).days) <= int(earn_window):
            continue

        T = D / 365.0
        try:
            calls = stock.option_chain(exp).calls
            puts = stock.option_chain(exp).puts
        except Exception:
            continue

        pred_ex, next_div = estimate_next_ex_div(stock)
        ex_div_in_window = bool(pred_ex and 0 <= (pred_ex - datetime.now(timezone.utc).date()
).days <= D)

        def _add_call_delta(df):
            out = []
            for _, r in df.iterrows():
                K = _safe_float(r.get("strike"))
                if not (K == K and K > 0):
                    continue
                iv = _safe_float(r.get("impliedVolatility"), 0.20)
                cd = call_delta(S, K, risk_free, iv, T, div_y)
                prem = effective_credit(r.get("bid"), r.get("ask"), r.get("lastPrice"))
                if prem != prem or prem <= 0:
                    continue
                spread_pct = compute_spread_pct(r.get("bid"), r.get("ask"), prem)
                oi = _safe_int(r.get("openInterest"), 0)
                out.append({"K": K, "prem": prem, "delta": cd, "iv": iv, "spread%": spread_pct, "oi": oi})
            return pd.DataFrame(out)

        def _add_put_delta(df):
            out = []
            for _, r in df.iterrows():
                K = _safe_float(r.get("strike"))
                if not (K == K and K > 0):
                    continue
                iv = _safe_float(r.get("impliedVolatility"), 0.20)
                pdlt = put_delta(S, K, risk_free, iv, T, div_y)
                prem = effective_debit(r.get("bid"), r.get("ask"), r.get("lastPrice"))
                if prem != prem or prem <= 0:
                    continue
                spread_pct = compute_spread_pct(r.get("bid"), r.get("ask"), prem)
                oi = _safe_int(r.get("openInterest"), 0)
                out.append({"K": K, "prem": prem, "delta": pdlt, "iv": iv, "spread%": spread_pct, "oi": oi})
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
        put_cushion = (S - p_row["K"]) / exp_mv if (exp_mv == exp_mv and exp_mv > 0) else float("nan")
        call_cushion = (c_row["K"] - S) / exp_mv if (exp_mv == exp_mv and exp_mv > 0) else float("nan")

        liq_score = 1.0 - min(((c_row["spread%"] or 20.0) + (p_row["spread%"] or 20.0)) / 40.0, 1.0)
        score = 0.45 * roi_ann + 0.25 * max(0.0, put_cushion) / 3.0 + 0.15 * max(0.0, call_cushion) / 3.0 + 0.15 * liq_score

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
    cushion = float(_series_get(row, "CushionSigma", float("nan")))
    roi_ann = float(_series_get(row, "ROI%_ann", float("nan"))) / 100.0
    excess = float(_series_get(row, "ROI%_excess_bills", float("nan"))) / 100.0
    otm_pct = float(_series_get(row, "OTM%", float("nan")))

    # Tenor sweet spot
    t_low, t_high = (21, 45) if strategy in ("CSP", "CC") else (30, 60)
    if t_low <= days <= t_high:
        checks.append(("Tenor sweet spot", "✅", f"{days} DTE within {t_low}-{t_high}"))
    else:
        checks.append(("Tenor sweet spot", "⚠️", f"{days} DTE outside {t_low}-{t_high}"))
        flags["tenor_warn"] = True

    # Liquidity
    if oi >= thresholds["min_oi"] and (spread != spread or spread <= thresholds["max_spread"]):
        notes = f"OI {oi} ok" + ("" if spread != spread else f", spread {spread:.1f}% ok")
        checks.append(("Liquidity", "✅", notes))
    else:
        why = []
        if oi < thresholds["min_oi"]: why.append(f"OI {oi} < {thresholds['min_oi']}")
        if spread == spread and spread > thresholds["max_spread"]: why.append(f"spread {spread:.1f}% > {thresholds['max_spread']}")
        checks.append(("Liquidity", "⚠️", "; ".join(why) or "insufficient data"))
        flags["liquidity_warn"] = True

    # Cushion (sigmas from strike)
    if cushion == cushion:
        if cushion >= thresholds.get("min_cushion", 1.0):
            checks.append(("Sigma cushion", "✅", f"{cushion:.2f}σ ≥ {thresholds.get('min_cushion',1.0)}σ"))
        else:
            checks.append(("Sigma cushion", "⚠️", f"{cushion:.2f}σ < {thresholds.get('min_cushion',1.0)}σ"))
            flags["cushion_low"] = True
    else:
        checks.append(("Sigma cushion", "⚠️", "n/a"))

    # Excess over T-bills (if available)
    if excess == excess:
        if excess > 0:
            checks.append(("Excess vs T-bills", "✅", f"+{excess*100:.1f}% annualized"))
        else:
            checks.append(("Excess vs T-bills", "❌", f"{excess*100:.1f}% (negative pickup)"))
            flags["excess_negative"] = True

    # Strategy-specific checks
    if strategy == "CSP":
        pdelta = compute_put_delta_for_row(row, risk_free, div_y)
        target_low, target_high =  -0.30, -0.15
        if pdelta == pdelta and target_low <= pdelta <= target_high:
            checks.append(("Δ target (CSP)", "✅", f"put Δ {pdelta:.2f} in [{target_low:.2f},{target_high:.2f}]"))
        else:
            checks.append(("Δ target (CSP)", "⚠️", f"put Δ {pdelta:.2f} (preferred {target_low:.2f}..{target_high:.2f})"))

        if otm_pct == otm_pct:
            if otm_pct >= thresholds.get("min_otm_csp", 10.0):
                checks.append(("OTM distance", "✅", f"{otm_pct:.1f}% OTM"))
            else:
                checks.append(("OTM distance", "⚠️", f"{otm_pct:.1f}% OTM < {thresholds.get('min_otm_csp',10.0)}%"))

    elif strategy == "CC":
        cdelta = compute_call_delta_for_row(row, risk_free, div_y)
        # assignment risk proxy (ex-div logic exists in DF as AssignRisk)
        assign_risk = bool(_series_get(row, "AssignRisk", False))
        if cdelta == cdelta and 0.20 <= cdelta <= 0.35:
            checks.append(("Δ target (CC)", "✅", f"call Δ {cdelta:.2f} ~ 0.20–0.35"))
        else:
            checks.append(("Δ target (CC)", "⚠️", f"call Δ {cdelta:.2f} (pref 0.20–0.35)"))
        if assign_risk:
            checks.append(("Ex‑div assignment", "⚠️", "Dividend > call extrinsic → high early assignment risk"))
            flags["assignment_risk"] = True
        if otm_pct == otm_pct and otm_pct < thresholds.get("min_otm_cc", 2.0):
            checks.append(("OTM distance", "⚠️", f"{otm_pct:.1f}% OTM (pref ≥ 2–6%)"))

    elif strategy == "COLLAR":
        cdelta = compute_call_delta_for_row(row, risk_free, div_y, strike_key="CallStrike")
        pdelta = put_delta(float(row["Price"]), float(row["PutStrike"]), risk_free, _iv_decimal(row), int(row["Days"])/365.0, q=div_y)
        # Targets: call ~ +0.25–0.35, put ~ −0.10..−0.15
        if cdelta == cdelta and 0.25 <= cdelta <= 0.35:
            checks.append(("Δ target (call)", "✅", f"{cdelta:.2f}"))
        else:
            checks.append(("Δ target (call)", "⚠️", f"{cdelta:.2f} (pref 0.25–0.35)"))
        if pdelta == pdelta and -0.15 <= pdelta <= -0.10:
            checks.append(("Δ target (put)", "✅", f"{pdelta:.2f}"))
        else:
            checks.append(("Δ target (put)", "⚠️", f"{pdelta:.2f} (pref −0.10..−0.15)"))

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
            f"  Collateral required: {_fmt_usd(K*100*contracts,0)} (cash‑secured)",
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
            *([f"• Buy {contracts*100} shares {ticker} @ MKT/LIMIT ≤ {_fmt_usd(S)}"] if need_shares else ["• (You indicated you already hold the shares)"]),
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
            f"  Net (target):  {_fmt_usd(net_ps)}/sh  ({'credit' if net_ps>=0 else 'debit'})",
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
            ann_roi = (1.0 + cycle_roi) ** (365.0 / max(1, horizon_days if horizon_days > 0 else 1)) - 1.0
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
            ann_roi = (1.0 + cycle_roi) ** (365.0 / max(1, horizon_days if horizon_days > 0 else 1)) - 1.0
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
            put_now  = bs_put_price(S1, Kp, r, div_y, iv1, T)
            pnl_call = (call_entry - call_now) * 100.0  # short call
            pnl_put  = (put_now - put_entry) * 100.0    # long put
            pnl_shares = (S1 - S0) * 100.0
            total = pnl_shares + pnl_call + pnl_put
            capital = S0 * 100.0
            cycle_roi = total / capital
            ann_roi = (1.0 + cycle_roi) ** (365.0 / max(1, horizon_days if horizon_days > 0 else 1)) - 1.0
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

    raise ValueError("Unknown strategy for stress")

# -------------------------- Streamlit UI -------------------------

st.set_page_config(page_title="Strategy Lab: CSP vs CC vs Collar", layout="wide")
st.title("📊 Options Income Strategy Lab — CSP vs Covered Call vs Collar")

# Initialize session state
for key in ["df_csp", "df_cc", "df_collar"]:
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame()

with st.sidebar:
    st.header("Universe & Filters")
    tickers_str = st.text_input("Tickers (comma-separated)",
                                value="SPY, QQQ, IWM, AAPL, MSFT, NVDA, KO, IBM, XLF, XLE")
    days_limit = st.slider("Max Days to Expiry", 7, 90, 45, step=1)
    risk_free = st.number_input("Risk-free rate (annualized, decimal)", value=0.00, step=0.01, format="%.2f", key="risk_free_input")
    t_bill_yield = st.number_input(
    "13-week T-bill yield (annualized, decimal)",
    value=0.00, step=0.01, format="%.2f", key="t_bill_yield_input"
)
    st.caption("General liquidity filters")
    min_oi = st.slider("Min Open Interest", 0, 2000, 200, step=50)
    max_spread = st.slider("Max Bid–Ask % of Mid", 1.0, 30.0, 10.0, step=0.5)
    t_bill_yield = st.number_input("13-week T-bill yield (annualized, decimal)", value=0.00, step=0.01, format="%.2f")

    st.divider()
    st.subheader("CSP")
    min_otm_csp = st.slider("Min OTM % (CSP)", 0.0, 30.0, 12.0, step=0.5)
    min_roi_csp = st.slider("Min Ann. ROI (decimal, CSP)", 0.00, 0.50, 0.12, step=0.01)
    min_cushion = st.slider("Min Cushion σ (CSP)", 0.0, 3.0, 1.0, step=0.1)
    min_poew = st.slider("Min POEW (CSP, expire worthless)", 0.50, 0.95, 0.65, step=0.01)
    earn_window = st.slider("Earnings window (± days, CSP/CC)", 0, 14, 5, step=1)
    per_contract_cap = st.number_input("Per-contract collateral cap ($, CSP)", min_value=0, value=0, step=1000, key="per_contract_cap_input")
    per_contract_cap = None if per_contract_cap == 0 else float(per_contract_cap)

    st.divider()
    st.subheader("Covered Call")
    min_otm_cc = st.slider("Min OTM % (CC)", 0.0, 20.0, 3.0, step=0.5)
    min_roi_cc = st.slider("Min Ann. ROI (decimal, CC)", 0.00, 0.50, 0.08, step=0.01)
    include_div_cc = st.checkbox("Include dividend estimate (CC)", value=True)

    st.divider()
    st.subheader("Collar")
    call_delta_tgt = st.slider("Target Call Δ", 0.10, 0.50, 0.30, step=0.01)
    put_delta_tgt = st.slider("Target Put Δ (abs)", 0.05, 0.30, 0.10, step=0.01)
    include_div_col = st.checkbox("Include dividend estimate (Collar)", value=True)
    min_net_credit = st.number_input("Min net credit ($/sh, Collar, optional)", value=0.0, step=0.05, key="min_net_credit_input")

    st.divider()
    run_btn = st.button("🔎 Scan Strategies")

@st.cache_data(show_spinner=True, ttl=120)
def run_scans(tickers, params):
    csp_all = []
    cc_all = []
    col_all = []
    for t in tickers:
        csp = analyze_csp(
            t,
            days_limit=params["days_limit"], min_otm=params["min_otm_csp"], min_oi=params["min_oi"],
            max_spread=params["max_spread"], min_roi=params["min_roi_csp"], min_cushion=params["min_cushion"],
            min_poew=params["min_poew"], earn_window=params["earn_window"], risk_free=params["risk_free"],
            per_contract_cap=params["per_contract_cap"],
            bill_yield=params["bill_yield"] 
        )
        if not csp.empty:
            csp_all.append(csp)

        cc = analyze_cc(
            t,
            days_limit=params["days_limit"], min_otm=params["min_otm_cc"], min_oi=params["min_oi"],
            max_spread=params["max_spread"], min_roi=params["min_roi_cc"],
            earn_window=params["earn_window"], risk_free=params["risk_free"],
            include_dividends=params["include_div_cc"],
            bill_yield=params["bill_yield"]
        )
        if not cc.empty:
            cc_all.append(cc)

        col = analyze_collar(
            t,
            days_limit=params["days_limit"], min_oi=params["min_oi"], max_spread=params["max_spread"],
            call_delta_target=params["call_delta_tgt"], put_delta_target=params["put_delta_tgt"],
            earn_window=params["earn_window"], risk_free=params["risk_free"],
            include_dividends=params["include_div_col"], min_net_credit=params["min_net_credit"],
            bill_yield=params["bill_yield"]   
        )
        if not col.empty:
            col_all.append(col)

    df_csp = pd.concat(csp_all, ignore_index=True) if csp_all else pd.DataFrame()
    df_cc = pd.concat(cc_all, ignore_index=True) if cc_all else pd.DataFrame()
    df_col = pd.concat(col_all, ignore_index=True) if col_all else pd.DataFrame()
    return df_csp, df_cc, df_col

# Run scans
if run_btn:
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
    opts = dict(
        days_limit=int(days_limit),
        min_otm_csp=float(min_otm_csp), min_roi_csp=float(min_roi_csp),
        min_cushion=float(min_cushion), min_poew=float(min_poew),
        min_otm_cc=float(min_otm_cc), min_roi_cc=float(min_roi_cc),
        include_div_cc=bool(include_div_cc),
        call_delta_tgt=float(call_delta_tgt), put_delta_tgt=float(put_delta_tgt),
        include_div_col=bool(include_div_col), min_net_credit=float(min_net_credit),
        min_oi=int(min_oi), max_spread=float(max_spread),
        earn_window=int(earn_window), risk_free=float(risk_free),
        per_contract_cap=per_contract_cap,
            bill_yield=float(t_bill_yield)  
    )
    with st.spinner("Scanning..."):
        df_csp, df_cc, df_collar = run_scans(tickers, opts)
    st.session_state["df_csp"] = df_csp
    st.session_state["df_cc"] = df_cc
    st.session_state["df_collar"] = df_collar

# Read latest results

df_csp = st.session_state["df_csp"]
df_cc = st.session_state["df_cc"]
df_collar = st.session_state["df_collar"]

# --- Universal Contract / Structure Picker (applies to all tabs) ---
st.subheader("Selection — applies to Risk, Runbook, and Stress tabs")

# Determine available strategies based on scan results
_available = [("CSP", df_csp), ("CC", df_cc), ("COLLAR", df_collar)]
available_strats = [name for name, df in _available if not df.empty]
if "sel_strategy" not in st.session_state:
    st.session_state["sel_strategy"] = (available_strats[0] if available_strats else "CSP")

# Strategy picker (single source of truth)
sel_strategy = st.selectbox(
    "Strategy",
    ["CSP", "CC", "COLLAR"],
    index=["CSP", "CC", "COLLAR"].index(st.session_state["sel_strategy"]),
    key="sel_strategy",
)

# Helper to build key series per strategy (standardized across app)
def _keys_for(strategy: str) -> pd.Series:
    if strategy == "CSP":
        df = df_csp
        return (
            df["Ticker"] + " | " + df["Exp"] + " | K=" + df["Strike"].astype(str)
        ) if not df.empty else pd.Series([], dtype=str)
    if strategy == "CC":
        df = df_cc
        return (
            df["Ticker"] + " | " + df["Exp"] + " | K=" + df["Strike"].astype(str)
        ) if not df.empty else pd.Series([], dtype=str)
    # COLLAR
    df = df_collar
    if df.empty:
        return pd.Series([], dtype=str)
    return (
        df["Ticker"] + " | " + df["Exp"]
        + " | Kc=" + df["CallStrike"].astype(str)
        + " | Kp=" + df["PutStrike"].astype(str)
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
        ks = (df["Ticker"] + " | " + df["Exp"] + " | K=" + df["Strike"].astype(str)) if not df.empty else pd.Series([], dtype=str)
    elif strat == "CC":
        df = df_cc
        ks = (df["Ticker"] + " | " + df["Exp"] + " | K=" + df["Strike"].astype(str)) if not df.empty else pd.Series([], dtype=str)
    else:
        df = df_collar
        if df.empty:
            return strat, None
        ks = (df["Ticker"] + " | " + df["Exp"]
              + " | Kc=" + df["CallStrike"].astype(str)
              + " | Kp=" + df["PutStrike"].astype(str))
    if df.empty:
        return strat, None
    sel = df[ks == key]
    if sel.empty:
        return strat, None
    return strat, sel.iloc[0]

tabs = st.tabs([
    "Cash‑Secured Puts", "Covered Calls", "Collars",
    "Compare", "Risk (Monte Carlo)", "Playbook",
    "Plan & Runbook", "Stress Test"
])

# --- Tab 1: CSP ---
with tabs[0]:
    st.header("Cash‑Secured Puts")
    if df_csp.empty:
        st.info("Run a scan or loosen CSP filters.")
    else:
        show_cols = ["Strategy","Ticker","Price","Exp","Days","Strike","Premium","OTM%","ROI%_ann",
                     "IV","POEW","CushionSigma","Spread%","OI","Collateral","Score"]
        show_cols = [c for c in show_cols if c in df_csp.columns]
        st.dataframe(df_csp[show_cols], use_container_width=True, height=520)

# --- Tab 2: CC ---
with tabs[1]:
    st.header("Covered Calls")
    if df_cc.empty:
        st.info("Run a scan or loosen CC filters.")
    else:
        show_cols = ["Strategy","Ticker","Price","Exp","Days","Strike","Premium","OTM%","ROI%_ann",
                     "IV","POEC","CushionSigma","Spread%","OI","Capital","DivYld%","Score"]
        show_cols = [c for c in show_cols if c in df_cc.columns]
        st.dataframe(df_cc[show_cols], use_container_width=True, height=520)

# --- Tab 3: Collars ---
with tabs[2]:
    st.header("Collars (Stock + Short Call + Long Put)")
    if df_collar.empty:
        st.info("Run a scan or loosen Collar settings.")
    else:
        show_cols = ["Strategy","Ticker","Price","Exp","Days",
                     "CallStrike","CallPrem","PutStrike","PutPrem","NetCredit",
                     "ROI%_ann","CallΔ","PutΔ","CallSpread%","PutSpread%","CallOI","PutOI",
                     "Floor$/sh","Cap$/sh","PutCushionσ","CallCushionσ","Score"]
        show_cols = [c for c in show_cols if c in df_collar.columns]
        st.dataframe(df_collar[show_cols], use_container_width=True, height=520)

# --- Tab 4: Compare ---
with tabs[3]:
    st.header("Compare Projected Annualized ROIs (mid-price based)")
    if df_csp.empty and df_cc.empty and df_collar.empty:
        st.info("No results yet. Run a scan.")
    else:
        pieces = []
        if not df_csp.empty:
            tmp = df_csp[["Strategy","Ticker","Exp","Days","Strike","Premium","ROI%_ann","Score"]].copy()
            tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + " | K=" + tmp["Strike"].astype(str)
            pieces.append(tmp)
        if not df_cc.empty:
            tmp = df_cc[["Strategy","Ticker","Exp","Days","Strike","Premium","ROI%_ann","Score"]].copy()
            tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + " | K=" + tmp["Strike"].astype(str)
            pieces.append(tmp)
        if not df_collar.empty:
            tmp = df_collar[["Strategy","Ticker","Exp","Days","CallStrike","PutStrike","NetCredit","ROI%_ann","Score"]].copy()
            tmp = tmp.rename(columns={"CallStrike":"Strike"})
            tmp["Premium"] = tmp["NetCredit"]
            tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + " | K=" + tmp["Strike"].astype(str)
            tmp["Strategy"] = "COLLAR"
            pieces.append(tmp)

        cmp_df = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
        if cmp_df.empty:
            st.info("No comparable rows.")
        else:
            st.dataframe(cmp_df.sort_values(["Score","ROI%_ann"], ascending=[False, False]),
                         use_container_width=True, height=520)

# --- Tab 5: Risk (Monte Carlo) ---
with tabs[4]:
    st.header("Risk (Monte Carlo) — Uses the global selection above")
    st.caption("Simulates terminal prices via GBM and computes per-contract P&L and annualized ROI. Educational only.")

    # Controls (no per-tab strategy/contract pickers)
    colB, colC, colD = st.columns(3)
    with colB:
        paths = st.slider("Paths", 5000, 200000, 50000, step=5000)
    with colC:
        mc_drift = st.number_input("Drift (annual, decimal)", value=0.00, step=0.01, format="%.2f", key="mc_drift_input")
    with colD:
        seed = st.number_input("Seed (0 = random)", value=0, step=1, min_value=0, key="mc_seed_input")
        seed = None if seed == 0 else int(seed)

    strat_choice, row = _get_selected_row()
    if row is None:
        st.info("Select a strategy/contract above and ensure scans have results.")
    else:
        # Build MC params per strategy
        if strat_choice == "CSP":
            iv = float(row.get("IV", float("nan"))) / 100.0 if row.get("IV", float("nan")) == row.get("IV", float("nan")) else 0.20
            params = dict(
                S0=float(row["Price"]),
                days=int(row["Days"]),
                iv=iv,
                Kp=float(row["Strike"]),
                put_premium=float(row["Premium"]),
                div_ps_annual=0.0,
            )
            mc = mc_pnl("CSP", params, n_paths=int(paths), mu=float(mc_drift), seed=seed, rf=float(t_bill_yield))
        elif strat_choice == "CC":
            iv = float(row.get("IV", float("nan"))) / 100.0 if row.get("IV", float("nan")) == row.get("IV", float("nan")) else 0.20
            div_ps_annual = float(row.get("DivAnnualPS", 0.0)) if "DivAnnualPS" in row else 0.0
            params = dict(
                S0=float(row["Price"]),
                days=int(row["Days"]),
                iv=iv,
                Kc=float(row["Strike"]),
                call_premium=float(row["Premium"]),
                div_ps_annual=div_ps_annual,
                       )
            mc = mc_pnl("CC", params, n_paths=int(paths), mu=float(mc_drift), seed=seed)
        else:  # COLLAR
            iv = 0.20  # conservative default
            div_ps_annual = float(row.get("DivAnnualPS", 0.0)) if "DivAnnualPS" in row else 0.0
            params = dict(
                S0=float(row["Price"]),
                days=int(row["Days"]),
                iv=iv,
                Kc=float(row["CallStrike"]),
                call_premium=float(row["CallPrem"]),
                Kp=float(row["PutStrike"]),
                put_premium=float(row["PutPrem"]),
                div_ps_annual=div_ps_annual,
            )
            mc = mc_pnl("COLLAR", params, n_paths=int(paths), mu=float(mc_drift), seed=seed)

        # Render outputs (unchanged)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Expected P&L / contract", f"${mc['pnl_expected']:,.0f}")
        c2.metric("P&L (P5 / P50 / P95)", f"${mc['pnl_p5']:,.0f} / ${mc['pnl_p50']:,.0f} / ${mc['pnl_p95']:,.0f}")
        c3.metric("Worst path", f"${mc['pnl_min']:,.0f}")
        c4.metric("Collateral (capital)", f"${mc['collateral']:,.0f}")

        pnl = mc["pnl_paths"]
        bins = np.histogram_bin_edges(pnl, bins="auto")
        hist, edges = np.histogram(pnl, bins=bins)
        chart_df = pd.DataFrame({"pnl": (edges[:-1] + edges[1:]) / 2.0, "count": hist})
        base_chart = alt.Chart(chart_df).mark_bar().encode(
            x=alt.X("pnl:Q", title="P&L per contract (USD)"),
            y=alt.Y("count:Q", title="Frequency"),
            tooltip=["pnl","count"],
        )
        st.altair_chart(base_chart, use_container_width=True)

        def pct(x): return f"{x*100:.2f}%"
        roi_rows = [
            {"Scenario":"Expected", "Annualized ROI": pct(mc["roi_ann_expected"])},
            {"Scenario":"P5 (bear)", "Annualized ROI": pct(mc["roi_ann_p5"])},
            {"Scenario":"P50 (median)", "Annualized ROI": pct(mc["roi_ann_p50"])},
            {"Scenario":"P95 (bull)", "Annualized ROI": pct(mc["roi_ann_p95"])},
        ]
        st.subheader("Annualized ROI (from MC)")
        st.dataframe(pd.DataFrame(roi_rows), use_container_width=True)

        st.subheader("At‑a‑Glance: Trade Summary & Risk")
        summary_rows = [
            {"Scenario":"P5 (bear)", "P&L ($/contract)": f"{mc['pnl_p5']:,.0f}", "Annualized ROI": pct(mc["roi_ann_p5"])},
            {"Scenario":"P50 (median)","P&L ($/contract)": f"{mc['pnl_p50']:,.0f}", "Annualized ROI": pct(mc["roi_ann_p50"])},
            {"Scenario":"P95 (bull)", "P&L ($/contract)": f"{mc['pnl_p95']:,.0f}", "Annualized ROI": pct(mc["roi_ann_p95"])},
            {"Scenario":"Expected",   "P&L ($/contract)": f"{mc['pnl_expected']:,.0f}", "Annualized ROI": pct(mc["roi_ann_expected"])},
        ]
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

# --- Tab 6: Playbook ---
with tabs[5]:
    st.header("Best‑Practice Playbook")
    st.write("These are practical guardrails you can toggle against in the scanner.")
    for name in ["CSP","CC","COLLAR"]:
        with st.expander(f"{name} — tips"):
            tips = best_practices(name)
            for t in tips:
                st.markdown(f"- {t}")

# --- Tab 7: Plan & Runbook ---
with tabs[6]:
    st.header("Plan & Runbook — Uses the global selection above")
    st.caption("We’ll check the globally selected contract/structure against best practices and generate order tickets.")

    colB, colC = st.columns(2)
    with colB:
        contracts = st.number_input("Contracts", min_value=1, value=1, step=1, key="rb_contracts")
    with colC:
        capture_pct = st.slider("Profit capture target", 0.50, 0.90, 0.70, 0.05, key="rb_capture")

    strat_choice_rb, row = _get_selected_row()
    if row is None:
        st.info("Select a strategy/contract above and ensure scans have results.")
    else:
        base = {"CSP": df_csp, "CC": df_cc, "COLLAR": df_collar}[strat_choice_rb]

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
            holds_shares = st.checkbox("I already hold the required shares", value=False, key="rb_hold_shares")

        runbook_text = build_runbook(
            strat_choice_rb, row,
            contracts=int(contracts),
            capture_pct=float(capture_pct),
            risk_rules={},
            holds_shares=bool(holds_shares),
        )

        st.subheader("Trade Runbook")
        st.code(runbook_text, language="markdown")

        dl_name = f"runbook_{strat_choice_rb}_{row['Ticker']}_{row['Exp']}.txt".replace(" ","")
        st.download_button(
            "⬇️ Download Runbook (.txt)",
            data=runbook_text.encode("utf-8"),
            file_name=dl_name,
            mime="text/plain",
            key="rb_download_btn",
        )

        warn_msgs = []
        if flags["assignment_risk"]:
            warn_msgs.append("High early assignment risk around ex‑div on CC/Collar — consider rolling or skipping that expiry.")
        if flags["liquidity_warn"]:
            warn_msgs.append("Liquidity sub‑par (OI/spread). Consider a different strike/expiry/ticker.")
        if flags["tenor_warn"]:
            warn_msgs.append("Tenor outside the sweet spot. Consider 21–45 DTE (CSP/CC) or 30–60 DTE (Collar).")
        if flags["excess_negative"]:
            warn_msgs.append("Excess ROI vs T‑bills is negative. Consider passing on this trade.")
        if flags["cushion_low"]:
            warn_msgs.append("Sigma cushion is thin (< 1.0σ). Consider moving further OTM or extending tenor.")
        if warn_msgs:
            st.subheader("Notes & Cautions")
            for m in warn_msgs:
                st.markdown(f"- {m}")

# --- Tab 8: Stress Test ---
with tabs[7]:
    st.header("Stress Test — Uses the global selection above")
    st.caption("Apply price and IV shocks, reduce time by a horizon, and see leg-level and total P&L.")

    col2, col3, col4 = st.columns(3)
    with col2:
        horizon_days = st.number_input("Horizon (days)", min_value=0, value=1, step=1, key="stress_horizon_days")
    with col3:
        iv_dn_pp = st.number_input("IV shift on DOWN shocks (vol pts)", value=10.0, step=1.0, key="stress_iv_dn_pp")
    with col4:
        iv_up_pp = st.number_input("IV shift on UP shocks (vol pts)", value=0.0, step=1.0, key="stress_iv_up_pp")

    shocks_text = st.text_input("Price shocks (%) comma-separated", value="-20,-10,-5,0,5,10,20", key="stress_shocks_text")

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
        best  = float(df_stress["Total_P&L"].max())
        st.caption(f"Worst among tests: ${worst:,.0f} • Best among tests: ${best:,.0f}")

st.caption("This tool is for education only. Options involve risk and are not suitable for all investors.")
