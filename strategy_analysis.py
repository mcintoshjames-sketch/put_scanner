"""
Strategy Analysis Module

This module contains all strategy analyzer functions that scan option chains
for opportunities across 6 different strategies:
- CSP (Cash-Secured Puts)
- CC (Covered Calls)
- COLLAR (Protective Collars)
- IRON_CONDOR (Iron Condors)
- BULL_PUT_SPREAD (Bull Put Spreads)
- BEAR_CALL_SPREAD (Bear Call Spreads)
 - PMCC (Poor Man's Covered Call – diagonal: long deep ITM LEAPS call + short near-term call)
 - SYNTHETIC_COLLAR (Deep ITM call + long protective put + short OTM call – options-only collar)

Plus the prescreen_tickers function for ticker filtering.

Each analyzer function takes parameters and returns a DataFrame of opportunities
along with scan statistics (counters).
"""

import pandas as pd
import numpy as np
import logging
import sys
import os

# Configure logging to output to stderr (which shows in terminal)
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s',
    stream=sys.stderr,
    force=True
)
import yfinance as yf
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import options math functions
from options_math import (
    bs_call_price, bs_put_price,
    call_delta, put_delta,
    option_gamma, option_vega,
    call_theta, put_theta,
    expected_move,
    compute_spread_pct,
    trailing_dividend_info,
    get_earnings_date,
    mc_pnl,
    _bs_d1_d2,
    _norm_cdf
)
from scoring_utils import apply_unified_score

# Note: Data fetching functions (fetch_price, fetch_expirations, fetch_chain, etc.)
# are imported inside each analyzer function to avoid circular imports.
# These functions use Streamlit caching decorators and must stay in strategy_lab.py


# ----------------------------- Unified Risk-Reward Scoring -----------------------------

def _get_scan_perf_config():
    """Return performance tuning knobs for scan-time computations.
    Defaults preserve existing behavior. Enable overrides via Streamlit session_state or env vars.
    Keys:
      - fast_scan (bool): If true, enable aggressive limits to speed scanning
      - mc_paths_scan (int): Monte Carlo paths to use during scanning
      - max_mc_per_exp (int|None): Cap MC evaluations per expiration (None = unlimited)
      - pre_mc_score_min (float|None): Skip MC if preliminary score below this threshold
    """
    fast = False
    # PERFORMANCE: Reduced defaults to prevent 30+ minute scans
    # 250 paths gives stable results in ~25% of time vs 1000 paths
    mc_paths = 250
    # Cap MC at 10 best candidates per expiration (prevents exponential blowup)
    max_mc = 10
    # Lower threshold for complex strategies (PMCC/Synthetic Collar have lower ROI profiles)
    # 0.10 allows capital-intensive strategies through while still filtering weak opportunities
    pre_mc_min = 0.10
    # Env overrides (useful in headless/tests/CLI)
    try:
        env_fast = os.getenv("FAST_SCAN", "").strip().lower()
        if env_fast in ("1", "true", "yes", "on"):  # enable
            fast = True
    except Exception:
        pass
    try:
        env_paths = os.getenv("SCAN_MC_PATHS")
        if env_paths:
            mc_paths = max(50, int(env_paths))
    except Exception:
        pass
    try:
        env_max_mc = os.getenv("SCAN_MAX_MC_PER_EXP")
        if env_max_mc:
            max_mc = max(1, int(env_max_mc))
    except Exception:
        pass
    try:
        env_pre = os.getenv("SCAN_PRE_MC_SCORE_MIN")
        if env_pre:
            pre_mc_min = float(env_pre)
    except Exception:
        pass

    # Streamlit sidebar/session overrides (if available)
    try:
        import streamlit as st  # type: ignore
        fast = bool(st.session_state.get("fast_scan", fast))
        mc_paths = int(st.session_state.get("scan_mc_paths", mc_paths))
        max_mc = st.session_state.get("scan_max_mc_per_exp", max_mc)
        pre_mc_min = st.session_state.get("scan_pre_mc_score_min", pre_mc_min)
    except Exception:
        pass

    if fast:
        # If fast mode toggled and caller didn't override, apply safe speedy defaults
        mc_paths = int(os.getenv("SCAN_MC_PATHS", 100))  # Ultra-fast: 100 paths
        max_mc = max_mc if max_mc is not None else 5  # Only top 5 per expiration
        pre_mc_min = pre_mc_min if pre_mc_min is not None else 0.25  # Higher threshold
    return {
        "fast_scan": fast,
        "mc_paths_scan": int(mc_paths),
        "max_mc_per_exp": None if (max_mc is None or (isinstance(max_mc, str) and not max_mc)) else int(max_mc),
        "pre_mc_score_min": None if (pre_mc_min is None or (isinstance(pre_mc_min, str) and not pre_mc_min)) else float(pre_mc_min),
    }


def _maybe_mc(strategy_name: str, mc_params: dict, *, rf: float, mu: float,
              prelim_score: float | None,
              perf_cfg: dict,
              exp_counter: dict) -> dict:
    """Run Monte Carlo conditionally based on performance config; return dict like mc_pnl output or NaNs.
    exp_counter: mutable dict with 'count' to enforce per-expiration caps.
    """
    # Gate by preliminary score if configured
    pre_min = perf_cfg.get("pre_mc_score_min")
    if pre_min is not None and isinstance(prelim_score, (int, float)):
        try:
            if prelim_score < float(pre_min):
                return {
                    "pnl_expected": float("nan"),
                    "roi_ann_expected": float("nan"),
                    "pnl_p5": float("nan"),
                    "roi_ann_p5": float("nan"),
                }
        except Exception:
            pass

    # Gate by per-expiration count cap
    cap = perf_cfg.get("max_mc_per_exp")
    if cap is not None:
        c = int(exp_counter.get("count", 0))
        if c >= cap:
            return {
                "pnl_expected": float("nan"),
                "roi_ann_expected": float("nan"),
                "pnl_p5": float("nan"),
                "roi_ann_p5": float("nan"),
            }

    # Execute MC with configured path count
    try:
        n_paths = int(perf_cfg.get("mc_paths_scan", 1000))
    except Exception:
        n_paths = 1000
    try:
        res = mc_pnl(strategy_name, mc_params, n_paths=n_paths, mu=mu, seed=None, rf=rf)
        # Update counter on success
        exp_counter["count"] = int(exp_counter.get("count", 0)) + 1
        return res
    except Exception:
        return {
            "pnl_expected": float("nan"),
            "roi_ann_expected": float("nan"),
            "pnl_p5": float("nan"),
            "roi_ann_p5": float("nan"),
        }
def _clip01(x: float) -> float:
    try:
        if x != x:
            return 0.0
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0


def _norm(x: float, lo: float, hi: float) -> float:
    try:
        if x != x:
            return 0.0
        if hi <= lo:
            return 0.0
        return _clip01((float(x) - lo) / (hi - lo))
    except Exception:
        return 0.0


def unified_risk_reward_score(*, expected_roi_ann_dec: float | None,
                              p5_pnl: float | None,
                              capital: float | None,
                              spread_pct: float | None,
                              oi: float | None,
                              volume: float | None,
                              cushion_sigma: float | None) -> float:
    """Compute a cross-strategy 0..1 score emphasizing risk-adjusted return.

    Components (weights sum to 1.0):
      - 0.50 Risk-adjusted expected return: MC expected annualized ROI (capped at 100%).
      - 0.20 Downside robustness: penalize deep negative p5 MC P&L relative to capital.
      - 0.20 Liquidity quality: tighter spreads and healthy vol/OI get higher scores.
      - 0.10 Cushion: more standard deviations to key barrier improves score.
    """
    # 1) Expected annualized ROI (decimal) capped at 100%
    roi_comp = _norm((expected_roi_ann_dec or 0.0), 0.0, 1.0)

    # 2) Downside robustness via p5 P&L vs. capital
    try:
        cap = float(capital) if (capital is not None and capital == capital and capital > 0) else float('nan')
        p5 = float(p5_pnl) if (p5_pnl is not None and p5_pnl == p5_pnl) else float('nan')
        if cap == cap and p5 == p5:
            # If p5 is >= 0, full credit. If negative, scale linearly down to -cap -> 0.0
            downside = 1.0 if p5 >= 0 else max(0.0, 1.0 + (p5 / cap))
        else:
            downside = 0.5  # unknown -> neutral
    except Exception:
        downside = 0.5

    # 3) Liquidity: spread and vol/OI
    try:
        sp = float(spread_pct) if (spread_pct is not None and spread_pct == spread_pct) else 20.0
        # Map 0% spread -> 1.0, 20%+ -> 0.0
        spread_score = _clip01(1.0 - min(max(sp, 0.0), 20.0) / 20.0)
    except Exception:
        spread_score = 0.5

    try:
        oi_val = float(oi) if (oi is not None and oi == oi and oi > 0) else float('nan')
        vol_val = float(volume) if (volume is not None and volume == volume) else float('nan')
        if oi_val == oi_val and vol_val == vol_val and oi_val > 0:
            vol_oi_ratio = vol_val / oi_val
            # 0 -> 0, 0.5 -> ~1. Clamp >= 0.5 to 1.0
            voloi_score = _clip01(vol_oi_ratio / 0.5)
        else:
            voloi_score = 0.5
    except Exception:
        voloi_score = 0.5
    liq_comp = 0.7 * spread_score + 0.3 * voloi_score

    # 4) Cushion in sigmas (normalize 0..3σ)
    try:
        cush = float(cushion_sigma) if (cushion_sigma is not None and cushion_sigma == cushion_sigma) else float('nan')
        cushion_comp = _norm(cush, 0.0, 3.0)
    except Exception:
        cushion_comp = 0.0

    score = 0.50 * roi_comp + 0.20 * downside + 0.20 * liq_comp + 0.10 * cushion_comp
    return round(_clip01(score), 6)


def analyze_csp(ticker, *, min_days=0, days_limit, min_otm, min_oi, max_spread, min_roi, min_cushion,
                min_poew, earn_window, risk_free, per_contract_cap=None, bill_yield=0.0):
    # Import from data_fetching to avoid circular import
    from data_fetching import (
        fetch_price, fetch_expirations, fetch_chain,
        _get_num_from_row, _safe_int, effective_credit, 
        effective_debit, estimate_next_ex_div, check_expiration_risk
    )
    
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
    # Single performance config fetch (remove prior duplicated calls)
    perf_cfg = _get_scan_perf_config()
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
    mc_counter = {"count": 0}
    for _, r in chain.iterrows():
            K = _get_num_from_row(
                r, ["strike", "Strike", "k", "K"], float("nan"))
            if not (K == K and K > 0):
                continue

            bid = _get_num_from_row(r, ["bid", "Bid", "b"])  # may be NaN
            ask = _get_num_from_row(r, ["ask", "Ask", "a"])  # may be NaN
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"])
            prem = effective_credit(
                bid, ask, last,
                oi=_safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest", "OI"], 0), 0),
                volume=_safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0),
                dte=D
            )
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

            # Get OI and volume - use NaN as default to detect missing values
            oi_val = _get_num_from_row(
                r, ["openInterest", "oi", "open_interest", "OI"], float("nan"))
            vol_val = _get_num_from_row(
                r, ["volume", "Volume", "vol"], float("nan"))
            
            # Convert to int, treating NaN as 0
            oi = _safe_int(oi_val, 0)
            vol = _safe_int(vol_val, 0)
            
            # DEBUG: Log first 5 options that passed ROI to see OI filter decisions
            if counters["roi_pass"] <= 5:
                logging.info(f"ROI-passed option #{counters['roi_pass']}: ticker={ticker}, strike={K}, OI={oi} (raw={oi_val}), min_oi={min_oi}, will_reject_OI={min_oi and oi_val == oi_val and oi < int(min_oi)}")
            
            # Only apply OI filter if we have valid data (not NaN)
            if min_oi and oi_val == oi_val and oi < int(min_oi):  # oi_val == oi_val checks for not NaN
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
            
            # ===== HARD FILTER: Earnings within 3 days is intolerable risk =====
            if days_to_earnings is not None and 0 <= days_to_earnings <= 3:
                # Skip this opportunity entirely - earnings too close
                continue
            
            # ===== APPLY BEST-PRACTICE PENALTIES TO SCORE =====
            # Tenor penalty: 21-45 DTE is sweet spot for CSP
            tenor_ok = 21 <= D <= 45
            tenor_penalty = 1.0 if tenor_ok else 0.70  # 30% reduction outside sweet spot
            
            # Volume/OI penalty: check liquidity health
            vol_oi_ratio = vol / oi if (oi > 0 and vol == vol) else 0.0
            if vol_oi_ratio >= 0.5:
                vol_penalty = 1.0  # Healthy turnover
            elif vol_oi_ratio >= 0.25:
                vol_penalty = 0.85  # Moderate, 15% reduction
            else:
                vol_penalty = 0.65  # Stale OI risk, 35% reduction
            
            # Earnings proximity penalty (beyond hard filter)
            if days_to_earnings is not None and days_to_earnings <= D + 7:
                # Earnings within cycle or shortly after
                earnings_penalty = 0.60  # 40% reduction - high vol event risk
            else:
                earnings_penalty = 1.0  # Safe
            
            # Theta/Gamma penalty: ≥1.0 is preferred
            if theta_gamma_ratio == theta_gamma_ratio:
                if theta_gamma_ratio >= 1.0:
                    tg_penalty = 1.0  # Good risk-adjusted decay
                elif theta_gamma_ratio >= 0.5:
                    tg_penalty = 0.85  # Acceptable, 15% reduction
                else:
                    tg_penalty = 0.70  # High gamma risk, 30% reduction
            else:
                tg_penalty = 0.85  # Unknown, slight penalty
            
            # Apply all penalties to base score
            score = score * tenor_penalty * vol_penalty * earnings_penalty * tg_penalty

            # Check expiration risk
            exp_risk = check_expiration_risk(
                expiration_str=exp,
                strategy="CSP",
                open_interest=oi,
                bid_ask_spread_pct=spread_pct or 0.0
            )

            # Quick Monte Carlo for expected P&L to enrich output and enable UI guardrails
            try:
                mc_params = dict(
                    S0=S,
                    days=D,
                    iv=iv_for_calc,
                    Kp=float(K),
                    put_premium=float(prem),
                    div_ps_annual=0.0,
                    use_net_collateral=False,
                )
                prelim = score  # use current heuristic score as prelim
                mc_result = _maybe_mc("CSP", mc_params, rf=risk_free, mu=0.0, prelim_score=prelim, perf_cfg=perf_cfg, exp_counter=mc_counter)
                mc_expected_pnl = mc_result.get('pnl_expected', float("nan"))
                mc_roi_ann = mc_result.get('roi_ann_expected', float("nan"))
                mc_pnl_p5 = mc_result.get('pnl_p5', float("nan"))
                mc_roi_p5 = mc_result.get('roi_ann_p5', float("nan"))
            except Exception:
                mc_expected_pnl = float("nan")
                mc_roi_ann = float("nan")
                mc_pnl_p5 = float("nan")
                mc_roi_p5 = float("nan")

            # Unified cross-strategy risk-reward score (0..1)
            try:
                rr_score = unified_risk_reward_score(
                    expected_roi_ann_dec=mc_roi_ann if mc_roi_ann == mc_roi_ann else 0.0,
                    p5_pnl=mc_pnl_p5,
                    capital=collateral,
                    spread_pct=spread_pct,
                    oi=oi,
                    volume=vol,
                    cushion_sigma=cushion_sigma,
                )
            except Exception:
                rr_score = float("nan")

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
                "Volume": vol,
                "DaysToEarnings": days_to_earnings,
                "Score": round(score, 6),
                "RiskRewardScore": rr_score if rr_score == rr_score else float("nan"),
                
                # Monte Carlo expected value (for guardrails and EV assessment)
                "MC_ExpectedPnL": round(mc_expected_pnl, 2) if 'mc_expected_pnl' in locals() and mc_expected_pnl == mc_expected_pnl else float("nan"),
                "MC_ROI_ann%": round(mc_roi_ann * 100.0, 2) if 'mc_roi_ann' in locals() and mc_roi_ann == mc_roi_ann else float("nan"),
                "MC_PnL_p5": round(mc_pnl_p5, 2) if 'mc_pnl_p5' in locals() and mc_pnl_p5 == mc_pnl_p5 else float("nan"),
                "MC_ROI_ann_p5%": round(mc_roi_p5 * 100.0, 2) if 'mc_roi_p5' in locals() and mc_roi_p5 == mc_roi_p5 else float("nan"),
                
                # Expiration risk assessment
                "ExpType": exp_risk["expiration_type"],
                "ExpRisk": exp_risk["risk_level"],
                "ExpAction": exp_risk["action"],
            })
            counters["final"] += 1
    
    # DEBUG: Print filter statistics
    logging.info(f"\n{ticker} Filter Statistics:")
    logging.info(f"  Total options examined: {counters['rows']}")
    logging.info(f"  Passed premium filter: {counters['premium_pass']} ({100*counters['premium_pass']/max(1,counters['rows']):.1f}%)")
    logging.info(f"  Passed OTM filter: {counters['otm_pass']} ({100*counters['otm_pass']/max(1,counters['rows']):.1f}%)")
    logging.info(f"  Passed ROI filter: {counters['roi_pass']} ({100*counters['roi_pass']/max(1,counters['rows']):.1f}%)")
    logging.info(f"  Passed OI filter: {counters['oi_pass']} ({100*counters['oi_pass']/max(1,counters['rows']):.1f}%)")
    logging.info(f"  Final results: {counters['final']}\n")
    
    df = pd.DataFrame(rows)
    if not df.empty:
        df = apply_unified_score(df)
        df = df.sort_values(["UnifiedScore", "Score", "ROI%_ann"], ascending=[False, False, False]).reset_index(drop=True)
    return df, counters


def analyze_cc(ticker, *, min_days=0, days_limit, min_otm, min_oi, max_spread, min_roi,
               earn_window, risk_free, include_dividends=True, bill_yield=0.0,
               _relaxed: bool = False, _final_relax: bool = False):
    # Import from strategy_lab to avoid circular import at module level
    from data_fetching import (
        fetch_price, fetch_expirations, fetch_chain,
        _get_num_from_row, _safe_int, effective_credit, 
        effective_debit, estimate_next_ex_div, check_expiration_risk
    )
    
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame()
    expirations = fetch_expirations(ticker)
    earn_date = get_earnings_date(stock)
    # Performance configuration (was previously missing causing MC to be skipped in tests)
    perf_cfg = _get_scan_perf_config()

    div_ps_annual, div_y = trailing_dividend_info(stock, S)  # per share annual
    
    # Debug counters
    counters = {
        "expirations": 0,
        "rows": 0,
        "premium_pass": 0,
        "otm_pass": 0,
        "roi_pass": 0,
        "oi_pass": 0,
        "spread_pass": 0,
        "final": 0,
    }
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
        counters["expirations"] += 1
        if "type" in chain_all.columns:
            chain = chain_all[chain_all["type"].str.lower() == "call"].copy()
        else:
            chain = chain_all.copy()
        if chain.empty:
            continue

        counters["rows"] += len(chain)

        T = D / 365.0
    mc_counter = {"count": 0}
    for _, r in chain.iterrows():
            K = _get_num_from_row(
                r, ["strike", "Strike", "k", "K"], float("nan"))
            if not (K == K and K > 0):
                continue
            bid = _get_num_from_row(r, ["bid", "Bid", "b"])  # may be NaN
            ask = _get_num_from_row(r, ["ask", "Ask", "a"])  # may be NaN
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"])
            prem = effective_credit(
                bid, ask, last,
                oi=_safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest", "OI"], 0), 0),
                volume=_safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0),
                dte=D
            )
            if prem != prem or prem <= 0:
                continue
            counters["premium_pass"] += 1
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
            counters["otm_pass"] += 1

            # Annualized ROI on stock capital (S)
            # Guard against 0-day expirations which would explode annualization
            if D <= 0:
                # Skip same-day expirations for CC to avoid pathological annualization
                continue
            roi_ann = (prem / S) * (365.0 / D)
            if include_dividends and div_ps_annual > 0:
                roi_ann += (div_ps_annual / S)

            if roi_ann != roi_ann or roi_ann < float(min_roi):
                continue
            counters["roi_pass"] += 1

            oi = _safe_int(_get_num_from_row(
                r, ["openInterest", "oi", "open_interest"], 0), 0)
            vol = _safe_int(_get_num_from_row(
                r, ["volume", "Volume", "vol"], 0), 0)
            
            if min_oi and oi < int(min_oi):
                continue
            counters["oi_pass"] += 1

            mid = prem
            spread_pct = compute_spread_pct(bid, ask, mid)
            if (spread_pct is not None) and (spread_pct > float(max_spread)):
                continue
            counters["spread_pass"] += 1

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
            
            # ===== HARD FILTER: Earnings within 3 days is intolerable risk =====
            if days_to_earnings is not None and 0 <= days_to_earnings <= 3:
                # Skip this opportunity entirely - earnings too close
                continue
            
            # ===== APPLY BEST-PRACTICE PENALTIES TO SCORE =====
            # Tenor penalty: 21-45 DTE is sweet spot for CC
            tenor_ok = 21 <= D <= 45
            tenor_penalty = 1.0 if tenor_ok else 0.70  # 30% reduction outside sweet spot
            
            # Volume/OI penalty: check liquidity health
            vol_oi_ratio = vol / oi if (oi > 0 and vol == vol) else 0.0
            if vol_oi_ratio >= 0.5:
                vol_penalty = 1.0  # Healthy turnover
            elif vol_oi_ratio >= 0.25:
                vol_penalty = 0.85  # Moderate, 15% reduction
            else:
                vol_penalty = 0.65  # Stale OI risk, 35% reduction
            
            # Earnings proximity penalty (beyond hard filter)
            if days_to_earnings is not None and days_to_earnings <= D + 7:
                # Earnings within cycle or shortly after
                earnings_penalty = 0.60  # 40% reduction - high vol event risk
            else:
                earnings_penalty = 1.0  # Safe
            
            # Theta/Gamma penalty: ≥1.0 is preferred
            if theta_gamma_ratio == theta_gamma_ratio:
                if theta_gamma_ratio >= 1.0:
                    tg_penalty = 1.0  # Good risk-adjusted decay
                elif theta_gamma_ratio >= 0.5:
                    tg_penalty = 0.85  # Acceptable, 15% reduction
                else:
                    tg_penalty = 0.70  # High gamma risk, 30% reduction
            else:
                tg_penalty = 0.85  # Unknown, slight penalty
            
            # Apply all penalties to base score
            score = score * tenor_penalty * vol_penalty * earnings_penalty * tg_penalty

            # ===== MONTE CARLO PENALTY: Validate against realistic price paths =====
            # Run quick MC simulation during scan to filter negative expected value
            mc_params = {
                "S0": S,
                "days": D,
                "iv": iv_dec if (iv_dec == iv_dec and iv_dec > 0.0) else 0.20,
                "Kc": K,  # Call strike for CC strategy
                "call_premium": prem,  # Premium received
                "div_ps_annual": div_ps_annual  # Annual dividend per share
            }
            try:
                prelim = score
                mc_result = _maybe_mc("CC", mc_params, rf=risk_free, mu=0.07, prelim_score=prelim, perf_cfg=perf_cfg, exp_counter=mc_counter)
                mc_expected_pnl = mc_result['pnl_expected']
                mc_roi_ann = mc_result['roi_ann_expected']
                mc_pnl_p5 = mc_result.get('pnl_p5', float("nan"))
                mc_roi_p5 = mc_result.get('roi_ann_p5', float("nan"))
                
                # ===== HARD FILTER: Negative MC expected P&L is intolerable =====
                # Skip opportunities with negative expected value under realistic price paths
                if mc_expected_pnl < 0:
                    # Skip this opportunity entirely - negative expected value
                    continue
                
                # Calculate max profit (premium received per contract)
                max_profit = prem * 100.0
                
                # Graduated penalty based on MC expected P&L vs. max profit
                # For positive expected value, reward based on quality
                if mc_expected_pnl < max_profit * 0.25:
                    # Linear scale from 0 to 25% of max profit: penalty 0.20 -> 0.50
                    mc_penalty = 0.20 + (mc_expected_pnl / (max_profit * 0.25)) * 0.30
                elif mc_expected_pnl < max_profit * 0.50:
                    # Linear scale from 25% to 50% of max profit: penalty 0.50 -> 0.80
                    mc_penalty = 0.50 + ((mc_expected_pnl - max_profit * 0.25) / (max_profit * 0.25)) * 0.30
                elif mc_expected_pnl < max_profit * 0.75:
                    # Linear scale from 50% to 75% of max profit: penalty 0.80 -> 0.90
                    mc_penalty = 0.80 + ((mc_expected_pnl - max_profit * 0.50) / (max_profit * 0.25)) * 0.10
                else:
                    # Above 75% of max profit: penalty 0.90 -> 1.0 (minimal reduction)
                    mc_penalty = 0.90 + min((mc_expected_pnl - max_profit * 0.75) / (max_profit * 0.25), 1.0) * 0.10
                
                # Apply 70% weight to MC penalty
                # Score impact: 
                #  - Negative MC P&L: score * 0.30 + score * 0.70 * 0.20 = score * 0.44 (56% reduction)
                #  - MC P&L at 25%: score * 0.65 (35% reduction)
                #  - MC P&L at 50%: score * 0.86 (14% reduction)
                #  - MC P&L at 75%: score * 0.93 (7% reduction)
                score = score * (0.30 + 0.70 * mc_penalty)
                
            except Exception as e:
                # If MC simulation fails, set MC values to NaN but don't penalize score
                mc_expected_pnl = float("nan")
                mc_roi_ann = float("nan")
                mc_pnl_p5 = float("nan")
                mc_roi_p5 = float("nan")

            # Unified cross-strategy risk-reward score (0..1)
            try:
                rr_score = unified_risk_reward_score(
                    expected_roi_ann_dec=mc_roi_ann if mc_roi_ann == mc_roi_ann else 0.0,
                    p5_pnl=mc_pnl_p5,
                    capital=S * 100.0,
                    spread_pct=spread_pct,
                    oi=oi,
                    volume=vol,
                    cushion_sigma=cushion_sigma,
                )
            except Exception:
                rr_score = float("nan")

            # Check expiration risk
            exp_risk = check_expiration_risk(
                expiration_str=exp,
                strategy="CC",
                open_interest=oi,
                bid_ask_spread_pct=spread_pct or 0.0
            )

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
                "Volume": vol,
                "DivYld%": round(div_y * 100.0, 2),
                "DaysToEarnings": days_to_earnings,
                "Score": round(score, 6),
                "RiskRewardScore": rr_score if rr_score == rr_score else float("nan"),
                "DivAnnualPS": round(div_ps_annual, 4),
                
                # Monte Carlo expected value (to assess realistic P&L)
                "MC_ExpectedPnL": round(mc_expected_pnl, 2) if mc_expected_pnl == mc_expected_pnl else float("nan"),
                "MC_ROI_ann%": round(mc_roi_ann * 100.0, 2) if mc_roi_ann == mc_roi_ann else float("nan"),
                "MC_PnL_p5": round(mc_pnl_p5, 2) if mc_pnl_p5 == mc_pnl_p5 else float("nan"),
                "MC_ROI_ann_p5%": round(mc_roi_p5 * 100.0, 2) if mc_roi_p5 == mc_roi_p5 else float("nan"),
                
                # Expiration risk assessment
                "ExpType": exp_risk["expiration_type"],
                "ExpRisk": exp_risk["risk_level"],
                "ExpAction": exp_risk["action"],
            })
            counters["final"] += 1
    
    # Log summary statistics
    logging.info(f"\n{ticker} CC Filter Statistics:")
    logging.info(f"  Total options examined: {counters['rows']}")
    if counters['rows'] > 0:
        logging.info(f"  Passed premium filter: {counters['premium_pass']} ({100.0*counters['premium_pass']/counters['rows']:.1f}%)")
        logging.info(f"  Passed OTM filter: {counters['otm_pass']} ({100.0*counters['otm_pass']/counters['rows']:.1f}%)")
        logging.info(f"  Passed ROI filter: {counters['roi_pass']} ({100.0*counters['roi_pass']/counters['rows']:.1f}%)")
        logging.info(f"  Passed OI filter: {counters['oi_pass']} ({100.0*counters['oi_pass']/counters['rows']:.1f}%)")
        logging.info(f"  Passed spread filter: {counters['spread_pass']} ({100.0*counters['spread_pass']/counters['rows']:.1f}%)")
        logging.info(f"  Final results: {counters['final']}")
    
    df = pd.DataFrame(rows)
    # Fallback: if no rows and not yet relaxed, retry once with half ROI threshold to avoid empty scans
    if df.empty and (not _relaxed) and float(min_roi) > 0.0:
        try:
            return analyze_cc(
                ticker=ticker,
                min_days=min_days,
                days_limit=days_limit,
                min_otm=min_otm,
                # Relax liquidity & ROI thresholds aggressively for fallback to ensure at least some rows
                min_oi=0,
                max_spread=max_spread * 1.25,
                min_roi=max(0.005, float(min_roi) * 0.5),
                earn_window=earn_window,
                risk_free=risk_free,
                include_dividends=include_dividends,
                bill_yield=bill_yield,
                _relaxed=True,
                _final_relax=False,
            )
        except Exception:
            pass
    # Final safety net for environments with thin quotes: drop ROI/OI/spread thresholds
    if df.empty and _relaxed and (not _final_relax):
        try:
            return analyze_cc(
                ticker=ticker,
                min_days=min_days,
                days_limit=days_limit,
                min_otm=min_otm,
                min_oi=0,
                max_spread=100.0,
                min_roi=0.0,
                earn_window=earn_window,
                risk_free=risk_free,
                include_dividends=include_dividends,
                bill_yield=bill_yield,
                _relaxed=True,
                _final_relax=True,
            )
        except Exception:
            pass
    if not df.empty:
        df = apply_unified_score(df)
        df = df.sort_values(["UnifiedScore", "Score", "ROI%_ann"], ascending=[False, False, False]).reset_index(drop=True)
    return df

# ----------------------------- PMCC (Poor Man's Covered Call) -----------------------------
def analyze_pmcc(ticker, *, target_long_delta=0.80, long_min_days=180, long_max_days=400,
                 short_min_days=21, short_max_days=60, short_delta_lo=0.20, short_delta_hi=0.35,
                 min_oi=50, max_spread=15.0, earn_window=7, risk_free=0.00, bill_yield=0.0,
                 pmcc_min_buffer_days: int = 120,
                 pmcc_avoid_exdiv: bool = True,
                 pmcc_long_leg_min_oi: int | None = None,
                 pmcc_long_leg_max_spread: float | None = None):
    """Scan for PMCC setups.
    Simplified approach:
      1. Pick a deep ITM LEAPS call (delta ~ target_long_delta, long_min_days..long_max_days)
      2. Pick a short-term call (short_min_days..short_max_days) with delta in [short_delta_lo, short_delta_hi]
    Returns DataFrame of candidates with estimated annualized ROI based on short call credit vs net debit.
    """
    from data_fetching import fetch_price, fetch_expirations, fetch_chain, effective_credit, effective_debit, _get_num_from_row, _safe_int, check_expiration_risk, estimate_next_ex_div
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame()
    expirations = fetch_expirations(ticker)
    earn_date = get_earnings_date(stock)
    div_ps_annual, div_y = trailing_dividend_info(stock, S)

    # Select LEAPS expiration
    leaps_exps = []
    short_exps = []
    today = datetime.now(timezone.utc).date()
    for exp in expirations:
        try:
            ed = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        D = (ed - today).days
        if long_min_days <= D <= long_max_days:
            leaps_exps.append((exp, D))
        if short_min_days <= D <= short_max_days:
            short_exps.append((exp, D))
    if not leaps_exps or not short_exps:
        return pd.DataFrame()

    # For simplicity choose best single long call candidate (highest delta near target)
    long_candidates = []
    perf_cfg = _get_scan_perf_config()
    for exp, D in leaps_exps:
        chain_all = fetch_chain(ticker, exp)
        if chain_all is None or chain_all.empty:
            continue
        calls = chain_all[chain_all["type"].str.lower() == "call"].copy() if "type" in chain_all.columns else chain_all.copy()
        if calls.empty:
            continue
        T = D / 365.0
        for _, r in calls.iterrows():
            K = _get_num_from_row(r, ["strike", "Strike", "K"]) or float("nan")
            if not (K == K and K > 0):
                continue
            # Deep ITM: strike well below spot
            if K >= S * 0.95:
                continue
            bid = _get_num_from_row(r, ["bid", "Bid"]) or float("nan")
            ask = _get_num_from_row(r, ["ask", "Ask"]) or float("nan")
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"]) or float("nan")
            oi_long = _safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0)
            prem = effective_debit(bid, ask, last, oi=oi_long)
            if not (prem == prem and prem > 0):
                continue
            iv_raw = _get_num_from_row(r, ["impliedVolatility", "iv", "IV"], float("nan"))
            iv_dec = iv_raw/100.0 if (iv_raw == iv_raw and iv_raw > 3.0) else iv_raw
            iv_for_calc = iv_dec if (iv_dec == iv_dec and iv_dec > 0) else 0.25
            d1, d2 = _bs_d1_d2(S, K, risk_free, iv_for_calc, T, div_y)
            delta = _norm_cdf(d1)
            if abs(delta - target_long_delta) <= 0.10:  # within tolerance
                spread_pct = compute_spread_pct(bid, ask, prem)
                # Per-leg liquidity constraints (long LEAPS)
                min_oi_long = pmcc_long_leg_min_oi if pmcc_long_leg_min_oi is not None else min_oi
                max_spread_long = pmcc_long_leg_max_spread if pmcc_long_leg_max_spread is not None else max_spread
                if (min_oi_long and oi_long > 0 and oi_long < int(min_oi_long)):
                    continue
                if (spread_pct is not None) and (float(spread_pct) > float(max_spread_long)):
                    continue
                long_candidates.append({"Exp": exp, "Days": D, "Strike": K, "Premium": prem, "Δ": delta, "IV": iv_for_calc*100.0, "Spread%": spread_pct, "OI": oi_long})
    if not long_candidates:
        return pd.DataFrame()
    # Pick candidate whose delta closest to target
    long_sel = sorted(long_candidates, key=lambda x: abs(x["Δ"] - target_long_delta))[0]

    # Short leg candidates - initialize ex-dividend info for assignment risk checks
    rows = []
    next_ex_date, next_div = estimate_next_ex_div(stock)
    # Per-expiration MC counter to enforce caps
    exp_mc_counters = {}
    
    for exp, D in short_exps:
        if earn_date and abs((earn_date - datetime.strptime(exp, "%Y-%m-%d").date()).days) <= earn_window:
            continue
        # Initialize MC counter for this expiration
        if exp not in exp_mc_counters:
            exp_mc_counters[exp] = {"count": 0}
        chain_all = fetch_chain(ticker, exp)
        if chain_all is None or chain_all.empty:
            continue
        calls = chain_all[chain_all["type"].str.lower() == "call"].copy() if "type" in chain_all.columns else chain_all.copy()
        if calls.empty:
            continue
        T = D / 365.0
        for _, r in calls.iterrows():
            K = _get_num_from_row(r, ["strike", "Strike", "K"]) or float("nan")
            if not (K == K and K > 0):
                continue
            # Short leg must be OTM relative to spot & above long strike
            if not (K > S and K > long_sel["Strike"]):
                continue
            bid = _get_num_from_row(r, ["bid", "Bid"]) or float("nan")
            ask = _get_num_from_row(r, ["ask", "Ask"]) or float("nan")
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"]) or float("nan")
            oi_short = _safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0)
            prem_short = effective_credit(bid, ask, last, oi=oi_short)
            if not (prem_short == prem_short and prem_short > 0):
                continue
            iv_raw = _get_num_from_row(r, ["impliedVolatility", "iv", "IV"], float("nan"))
            iv_dec = iv_raw/100.0 if (iv_raw == iv_raw and iv_raw > 3.0) else iv_raw
            iv_for_calc = iv_dec if (iv_dec == iv_dec and iv_dec > 0) else 0.25
            d1, d2 = _bs_d1_d2(S, K, risk_free, iv_for_calc, T, div_y)
            delta_short = _norm_cdf(d1)
            if not (short_delta_lo <= delta_short <= short_delta_hi):
                continue
            spread_pct = compute_spread_pct(bid, ask, prem_short)
            if spread_pct and spread_pct > max_spread:
                continue
            # LEAPS buffer after short expiry
            try:
                if (int(long_sel["Days"]) - int(D)) < int(pmcc_min_buffer_days):
                    continue
            except Exception:
                pass
            # Ex-dividend guard (assignment risk)
            try:
                if next_ex_date is not None:
                    ed = datetime.strptime(exp, "%Y-%m-%d").date()
                    if abs((next_ex_date - ed).days) <= 2:
                        if pmcc_avoid_exdiv:
                            continue
                        intrinsic = max(0.0, S - float(K))
                        extrinsic = max(0.0, float(prem_short) - intrinsic)
                        if next_div and next_div > 0.0 and extrinsic < (next_div - 0.02):
                            continue
            except Exception:
                pass
            net_debit = long_sel["Premium"] - prem_short
            if net_debit <= 0:  # require net debit (long diagonal)
                continue
            roi_ann = (prem_short / net_debit) * (365.0 / D)
            
            # Compute preliminary score BEFORE MC for gating
            prelim_score = unified_risk_reward_score(
                expected_roi_ann_dec=roi_ann/100.0,
                p5_pnl=None,  # No MC yet
                capital=net_debit*100.0,
                spread_pct=spread_pct,
                oi=_safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0),
                volume=_safe_int(_get_num_from_row(r, ["volume", "Volume"], 0), 0),
                cushion_sigma=float("nan")
            )
            
            exp_risk = check_expiration_risk(
                expiration_str=exp,
                strategy="CC",
                open_interest=_safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0),
                bid_ask_spread_pct=spread_pct or 0.0
            )

            # Monte Carlo approximation with gating
            mc_params = dict(
                S0=S, days=D, iv=iv_for_calc,
                long_call_strike=float(long_sel["Strike"]), long_call_cost=float(long_sel["Premium"]), long_days_total=int(long_sel["Days"]), long_iv=float(long_sel["IV"])/100.0,
                short_call_strike=float(K), short_call_premium=float(prem_short), short_iv=iv_for_calc
            )
            try:
                # Use preliminary score for gating and shared exp_counter
                # Note: PMCC typically has lower ROI (capital-intensive), so MC may be gated
                mc = _maybe_mc("PMCC", mc_params, rf=risk_free, mu=0.0, 
                              prelim_score=prelim_score, perf_cfg=perf_cfg, 
                              exp_counter=exp_mc_counters[exp])
                mc_expected = mc.get("pnl_expected", float("nan"))
                mc_roi_ann = mc.get("roi_ann_expected", float("nan"))
                mc_p5 = mc.get("pnl_p5", float("nan"))
            except Exception as e:
                # Log exception for debugging
                import sys
                print(f"Warning: PMCC MC failed for {ticker} {exp}: {e}", file=sys.stderr)
                mc_expected = float("nan"); mc_roi_ann = float("nan"); mc_p5 = float("nan")

            score = unified_risk_reward_score(
                expected_roi_ann_dec=mc_roi_ann/100.0 if mc_roi_ann == mc_roi_ann else roi_ann/100.0,
                p5_pnl=mc_p5,
                capital=net_debit*100.0,
                spread_pct=spread_pct,
                oi=_safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0),
                volume=_safe_int(_get_num_from_row(r, ["volume", "Volume"], 0), 0),
                cushion_sigma=float("nan")
            )
            rows.append({
                "Strategy": "PMCC", "Ticker": ticker, "Price": S, "Exp": exp, "Days": D,
                "LongExp": long_sel["Exp"], "LongDays": long_sel["Days"],
                "LongStrike": long_sel["Strike"], "ShortStrike": K,
                "LongCost": long_sel["Premium"], "ShortPrem": prem_short,
                "NetDebit": net_debit, "ROI%_ann": roi_ann*100.0,
                "LongΔ": long_sel["Δ"], "ShortΔ": delta_short,
                "AssignProb": delta_short*100.0,
                "IV": iv_for_calc*100.0, "Spread%": spread_pct,
                "MC_ExpectedPnL": mc_expected, "MC_ROI_ann%": mc_roi_ann,
                "MC_PnL_p5": mc_p5, "Score": score,
                "RiskType": "Bounded",
                "ExpType": exp_risk.get("expiration_type", "") if isinstance(exp_risk, dict) else "",
                "ExpRisk": exp_risk.get("risk_level", "") if isinstance(exp_risk, dict) else "",
                "ExpAction": exp_risk.get("action", "") if isinstance(exp_risk, dict) else "",
                "ExpWarn": exp_risk.get("warning_message", "") if isinstance(exp_risk, dict) else "",
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = apply_unified_score(df)
        # Sort by UnifiedScore primarily, fall back to legacy Score and ROI
        sort_keys = [c for c in ["UnifiedScore", "Score", "ROI%_ann"] if c in df.columns]
        if sort_keys:
            df = df.sort_values(sort_keys, ascending=[False]*len(sort_keys)).reset_index(drop=True)
    return df

# ----------------------------- Synthetic Collar -----------------------------
def analyze_synthetic_collar(ticker, *, target_long_delta=0.80, put_delta_target=-0.15,
                              long_min_days=180, long_max_days=400, short_min_days=21, short_max_days=60,
                              short_delta_lo=0.20, short_delta_hi=0.35, min_oi=50, max_spread=15.0,
                              earn_window=7, risk_free=0.0, bill_yield=0.0,
                              syn_min_floor_sigma: float = 1.0,
                              syn_min_buffer_days: int = 120,
                              syn_avoid_exdiv: bool = True,
                              syn_long_leg_min_oi: int | None = None,
                              syn_long_leg_max_spread: float | None = None,
                              syn_put_leg_min_oi: int | None = None,
                              syn_put_leg_max_spread: float | None = None):
    """Options-only collar: Long deep ITM call (synthetic stock) + Long put + Short OTM call.
    Simplified scanning similar to PMCC with added put leg.
    """
    from data_fetching import fetch_price, fetch_expirations, fetch_chain, effective_credit, effective_debit, _get_num_from_row, _safe_int, check_expiration_risk, estimate_next_ex_div
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame()
    expirations = fetch_expirations(ticker)
    earn_date = get_earnings_date(stock)
    # Performance configuration for conditional MC
    perf_cfg = _get_scan_perf_config()
    div_ps_annual, div_y = trailing_dividend_info(stock, S)
    today = datetime.now(timezone.utc).date()
    leaps_exps = []
    short_exps = []
    for exp in expirations:
        try:
            ed = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        D = (ed - today).days
        if long_min_days <= D <= long_max_days:
            leaps_exps.append((exp, D))
        if short_min_days <= D <= short_max_days:
            short_exps.append((exp, D))
    if not leaps_exps or not short_exps:
        return pd.DataFrame()
    # Long call selection (same as PMCC)
    long_candidates = []
    for exp, D in leaps_exps:
        chain_all = fetch_chain(ticker, exp)
        if chain_all is None or chain_all.empty:
            continue
        calls = chain_all[chain_all["type"].str.lower() == "call"].copy() if "type" in chain_all.columns else chain_all.copy()
        if calls.empty:
            continue
        T = D / 365.0
        for _, r in calls.iterrows():
            K = _get_num_from_row(r, ["strike", "Strike", "K"]) or float("nan")
            if not (K == K and K > 0):
                continue
            if K >= S * 0.95:
                continue
            bid = _get_num_from_row(r, ["bid", "Bid"]) or float("nan")
            ask = _get_num_from_row(r, ["ask", "Ask"]) or float("nan")
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"]) or float("nan")
            oi_long = _safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0)
            prem = effective_debit(bid, ask, last, oi=oi_long)
            if not (prem == prem and prem > 0):
                continue
            iv_raw = _get_num_from_row(r, ["impliedVolatility", "iv", "IV"], float("nan"))
            iv_dec = iv_raw/100.0 if (iv_raw == iv_raw and iv_raw > 3.0) else iv_raw
            iv_for_calc = iv_dec if (iv_dec == iv_dec and iv_dec > 0) else 0.25
            d1, d2 = _bs_d1_d2(S, K, risk_free, iv_for_calc, T, div_y)
            delta = _norm_cdf(d1)
            if abs(delta - target_long_delta) <= 0.10:
                spread_pct = compute_spread_pct(bid, ask, prem)
                min_oi_long = syn_long_leg_min_oi if syn_long_leg_min_oi is not None else min_oi
                max_spread_long = syn_long_leg_max_spread if syn_long_leg_max_spread is not None else max_spread
                if (min_oi_long and oi_long > 0 and oi_long < int(min_oi_long)):
                    continue
                if (spread_pct is not None) and (float(spread_pct) > float(max_spread_long)):
                    continue
                long_candidates.append({"Exp": exp, "Days": D, "Strike": K, "Premium": prem, "Δ": delta, "IV": iv_for_calc*100.0, "Spread%": spread_pct, "OI": oi_long})
    if not long_candidates:
        return pd.DataFrame()
    long_sel = sorted(long_candidates, key=lambda x: abs(x["Δ"] - target_long_delta))[0]

    # Initialize ex-dividend info for assignment risk checks
    next_ex_date, next_div = estimate_next_ex_div(stock)
    # Per-expiration MC counter to enforce caps
    exp_mc_counters = {}
    
    rows = []
    for exp, D in short_exps:
        if earn_date and abs((earn_date - datetime.strptime(exp, "%Y-%m-%d").date()).days) <= earn_window:
            continue
        # Initialize MC counter for this expiration
        if exp not in exp_mc_counters:
            exp_mc_counters[exp] = {"count": 0}
        chain_all = fetch_chain(ticker, exp)
        if chain_all is None or chain_all.empty:
            continue
        calls = chain_all[chain_all["type"].str.lower() == "call"].copy() if "type" in chain_all.columns else chain_all.copy()
        puts = chain_all[chain_all["type"].str.lower() == "put"].copy() if "type" in chain_all.columns else chain_all.copy()
        if calls.empty or puts.empty:
            continue
        T = D / 365.0
        # Select protective put near desired delta
        put_choice = None
        for _, r in puts.iterrows():
            Kp = _get_num_from_row(r, ["strike", "Strike", "K"]) or float("nan")
            if not (Kp == Kp and Kp > 0):
                continue
            if Kp >= S * 0.98:  # want OTM put
                continue
            bid = _get_num_from_row(r, ["bid", "Bid"]) or float("nan")
            ask = _get_num_from_row(r, ["ask", "Ask"]) or float("nan")
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"]) or float("nan")
            oi_put = _safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0)
            prem_put = effective_debit(bid, ask, last, oi=oi_put)
            if not (prem_put == prem_put and prem_put > 0):
                continue
            iv_raw = _get_num_from_row(r, ["impliedVolatility", "iv", "IV"], float("nan"))
            iv_dec = iv_raw/100.0 if (iv_raw == iv_raw and iv_raw > 3.0) else iv_raw
            iv_for_calc = iv_dec if (iv_dec == iv_dec and iv_dec > 0) else 0.25
            d1, d2 = _bs_d1_d2(S, Kp, risk_free, iv_for_calc, T, div_y)
            delta_put = _norm_cdf(d1) - 1.0  # convert to put delta approximation
            spread_put = compute_spread_pct(bid, ask, prem_put)
            min_oi_put = syn_put_leg_min_oi if syn_put_leg_min_oi is not None else min_oi
            max_spread_put = syn_put_leg_max_spread if syn_put_leg_max_spread is not None else max_spread
            if (min_oi_put and oi_put > 0 and oi_put < int(min_oi_put)):
                continue
            if (spread_put is not None) and (float(spread_put) > float(max_spread_put)):
                continue
            if abs(delta_put - put_delta_target) <= 0.05:
                put_choice = {"Strike": Kp, "Premium": prem_put, "Δ": delta_put, "IV": iv_for_calc*100.0, "Spread%": spread_put, "OI": oi_put}
                break
        if not put_choice:
            continue
        # Short call candidates
        for _, r in calls.iterrows():
            K = _get_num_from_row(r, ["strike", "Strike", "K"]) or float("nan")
            if not (K == K and K > 0):
                continue
            if not (K > S and K > long_sel["Strike"]):
                continue
            bid = _get_num_from_row(r, ["bid", "Bid"]) or float("nan")
            ask = _get_num_from_row(r, ["ask", "Ask"]) or float("nan")
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"]) or float("nan")
            oi_short = _safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0)
            prem_short = effective_credit(bid, ask, last, oi=oi_short)
            if not (prem_short == prem_short and prem_short > 0):
                continue
            iv_raw = _get_num_from_row(r, ["impliedVolatility", "iv", "IV"], float("nan"))
            iv_dec = iv_raw/100.0 if (iv_raw == iv_raw and iv_raw > 3.0) else iv_raw
            iv_for_calc = iv_dec if (iv_dec == iv_dec and iv_dec > 0) else 0.25
            d1, d2 = _bs_d1_d2(S, K, risk_free, iv_for_calc, T, div_y)
            delta_short = _norm_cdf(d1)
            if not (short_delta_lo <= delta_short <= short_delta_hi):
                continue
            spread_pct = compute_spread_pct(bid, ask, prem_short)
            if spread_pct and spread_pct > max_spread:
                continue
            # LEAPS time buffer
            try:
                if (int(long_sel["Days"]) - int(D)) < int(syn_min_buffer_days):
                    continue
            except Exception:
                pass
            # Ex-div safeguard
            try:
                if next_ex_date is not None:
                    ed = datetime.strptime(exp, "%Y-%m-%d").date()
                    if abs((next_ex_date - ed).days) <= 2:
                        if syn_avoid_exdiv:
                            continue
                        intrinsic = max(0.0, S - float(K))
                        extrinsic = max(0.0, float(prem_short) - intrinsic)
                        if next_div and next_div > 0.0 and extrinsic < (next_div - 0.02):
                            continue
            except Exception:
                pass
            net_debit = long_sel["Premium"] + put_choice["Premium"] - prem_short
            if net_debit <= 0:
                continue
            roi_ann = (prem_short / net_debit) * (365.0 / D)
            
            # Compute preliminary score BEFORE MC for gating
            prelim_score = unified_risk_reward_score(
                expected_roi_ann_dec=roi_ann/100.0,
                p5_pnl=None,  # No MC yet
                capital=net_debit*100.0,
                spread_pct=spread_pct,
                oi=_safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0),
                volume=_safe_int(_get_num_from_row(r, ["volume", "Volume"], 0), 0),
                cushion_sigma=float("nan")
            )
            
            exp_risk = check_expiration_risk(
                expiration_str=exp,
                strategy="COLLAR",
                open_interest=_safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0),
                bid_ask_spread_pct=spread_pct or 0.0
            )
            mc_params = dict(
                S0=S, days=D, iv=iv_for_calc,
                long_call_strike=float(long_sel["Strike"]), long_call_cost=float(long_sel["Premium"]), long_days_total=int(long_sel["Days"]), long_iv=float(long_sel["IV"])/100.0,
                put_strike=float(put_choice["Strike"]), put_cost=float(put_choice["Premium"]), put_iv=float(put_choice["IV"])/100.0,
                short_call_strike=float(K), short_call_premium=float(prem_short), short_iv=iv_for_calc
            )
            try:
                # Use preliminary score for gating and shared exp_counter
                # Note: Synthetic Collar typically has lower ROI (capital-intensive), so MC may be gated
                mc = _maybe_mc("SYNTHETIC_COLLAR", mc_params, rf=risk_free, mu=0.0, 
                              prelim_score=prelim_score, perf_cfg=perf_cfg, 
                              exp_counter=exp_mc_counters[exp])
                mc_expected = mc.get("pnl_expected", float("nan"))
                mc_roi_ann = mc.get("roi_ann_expected", float("nan"))
                mc_p5 = mc.get("pnl_p5", float("nan"))
            except Exception as e:
                # Log exception for debugging
                import sys
                print(f"Warning: Synthetic Collar MC failed for {ticker} {exp}: {e}", file=sys.stderr)
                mc_expected = float("nan"); mc_roi_ann = float("nan"); mc_p5 = float("nan")
            score = unified_risk_reward_score(
                expected_roi_ann_dec=mc_roi_ann/100.0 if mc_roi_ann == mc_roi_ann else roi_ann/100.0,
                p5_pnl=mc_p5,
                capital=net_debit*100.0,
                spread_pct=spread_pct,
                oi=_safe_int(_get_num_from_row(r, ["openInterest", "OI"], 0), 0),
                volume=_safe_int(_get_num_from_row(r, ["volume", "Volume"], 0), 0),
                cushion_sigma=float("nan")
            )
            # Floor cushion sigma using put IV
            try:
                exp_mv = expected_move(S, float(put_choice["IV"]) / 100.0 if put_choice.get("IV") else iv_for_calc, T)
                floor_sigma = ((S - float(put_choice["Strike"])) / exp_mv) if (exp_mv == exp_mv and exp_mv > 0) else float("nan")
                if floor_sigma == floor_sigma and float(floor_sigma) < float(syn_min_floor_sigma):
                    continue
            except Exception:
                floor_sigma = float("nan")

            rows.append({
                "Strategy": "SYNTHETIC_COLLAR", "Ticker": ticker, "Price": S, "Exp": exp, "Days": D,
                "LongExp": long_sel["Exp"], "LongDays": long_sel["Days"],
                "LongStrike": long_sel["Strike"], "ShortStrike": K, "PutStrike": put_choice["Strike"],
                "LongCost": long_sel["Premium"], "ShortPrem": prem_short, "PutCost": put_choice["Premium"],
                "NetDebit": net_debit, "ROI%_ann": roi_ann*100.0,
                "LongΔ": long_sel["Δ"], "ShortΔ": delta_short, "PutΔ": put_choice["Δ"],
                "AssignProb": delta_short*100.0,
                "IV": iv_for_calc*100.0, "ShortIV%": iv_for_calc*100.0, "LongIV%": float(long_sel["IV"]), "PutIV%": float(put_choice["IV"]), "Spread%": spread_pct, "PutCushionσ": float(floor_sigma) if floor_sigma == floor_sigma else float("nan"),
                "MC_ExpectedPnL": mc_expected, "MC_ROI_ann%": mc_roi_ann,
                "MC_PnL_p5": mc_p5, "Score": score,
                "RiskType": "Bounded",
                "ExpType": exp_risk.get("expiration_type", "") if isinstance(exp_risk, dict) else "",
                "ExpRisk": exp_risk.get("risk_level", "") if isinstance(exp_risk, dict) else "",
                "ExpAction": exp_risk.get("action", "") if isinstance(exp_risk, dict) else "",
                "ExpWarn": exp_risk.get("warning_message", "") if isinstance(exp_risk, dict) else "",
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = apply_unified_score(df)
        sort_keys = [c for c in ["UnifiedScore", "Score", "ROI%_ann"] if c in df.columns]
        if sort_keys:
            df = df.sort_values(sort_keys, ascending=[False]*len(sort_keys)).reset_index(drop=True)
    return df


def analyze_collar(ticker, *, min_days=0, days_limit, min_oi, max_spread,
                   call_delta_target, put_delta_target, earn_window, risk_free,
                   include_dividends=True, min_net_credit=None, bill_yield=0.0):
    # Import from strategy_lab to avoid circular import at module level
    from data_fetching import (
        fetch_price, fetch_expirations, fetch_chain,
        _get_num_from_row, _safe_int, effective_credit, 
        effective_debit, estimate_next_ex_div, check_expiration_risk
    )
    
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame()

    expirations = fetch_expirations(ticker)
    earn_date = get_earnings_date(stock)
    div_ps_annual, div_y = trailing_dividend_info(stock, S)
    rows = []
    # Performance configuration (previously missing)
    perf_cfg = _get_scan_perf_config()

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
                    _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"]),
                    oi=_safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0),
                    volume=_safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0),
                    dte=D
                )
                if prem != prem or prem <= 0:
                    continue
                spread_pct = compute_spread_pct(
                    _get_num_from_row(r, ["bid", "Bid", "b"]),
                    _get_num_from_row(r, ["ask", "Ask", "a"]),
                    prem)
                oi = _safe_int(_get_num_from_row(
                    r, ["openInterest", "oi", "open_interest"], 0), 0)
                vol = _safe_int(_get_num_from_row(
                    r, ["volume", "Volume", "vol"], 0), 0)
                out.append({"K": K, "prem": prem, "delta": cd,
                           "iv": iv, "spread%": spread_pct, "oi": oi, "volume": vol})
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
                bidv = _get_num_from_row(r, ["bid", "Bid", "b"])
                askv = _get_num_from_row(r, ["ask", "Ask", "a"])
                lastv = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"])
                oi_v = _safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0)
                vol_v = _safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0)
                prem = effective_debit(bidv, askv, lastv, oi=oi_v, volume=vol_v, dte=D)
                if prem != prem or prem <= 0:
                    continue
                spread_pct = compute_spread_pct(
                    _get_num_from_row(r, ["bid", "Bid", "b"]),
                    _get_num_from_row(r, ["ask", "Ask", "a"]),
                    prem)
                oi = _safe_int(_get_num_from_row(
                    r, ["openInterest", "oi", "open_interest"], 0), 0)
                vol = _safe_int(_get_num_from_row(
                    r, ["volume", "Volume", "vol"], 0), 0)
                out.append({"K": K, "prem": prem, "delta": pdlt,
                           "iv": iv, "spread%": spread_pct, "oi": oi, "volume": vol})
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
        
        # ===== HARD FILTER: High dividend assignment risk is intolerable =====
        if assign_risk:
            # Skip - call will likely be assigned for dividend capture
            continue
        
        # ===== APPLY BEST-PRACTICE PENALTIES TO SCORE =====
        # Tenor penalty: 30-60 DTE is sweet spot for Collar (longer-term protection)
        tenor_ok = 30 <= D <= 60
        tenor_penalty = 1.0 if tenor_ok else 0.70  # 30% reduction outside sweet spot
        
        # Volume/OI penalty: use worse of call/put liquidity
        call_vol = _safe_int(c_row["volume"], 0)
        put_vol = _safe_int(p_row["volume"], 0)
        call_oi = _safe_int(c_row["oi"], 0)
        put_oi = _safe_int(p_row["oi"], 0)
        
        # Calculate vol/oi for both legs, use minimum (worst case)
        call_vol_oi = call_vol / call_oi if call_oi > 0 else 0.0
        put_vol_oi = put_vol / put_oi if put_oi > 0 else 0.0
        vol_oi_ratio = min(call_vol_oi, put_vol_oi)
        
        if vol_oi_ratio >= 0.5:
            vol_penalty = 1.0  # Healthy turnover on both legs
        elif vol_oi_ratio >= 0.25:
            vol_penalty = 0.85  # Moderate, 15% reduction
        else:
            vol_penalty = 0.65  # Stale OI risk, 35% reduction
        
        # Apply all penalties to base score
        score = score * tenor_penalty * vol_penalty

        floor = (p_row["K"] - S) + net_credit
        cap_to_call = (c_row["K"] - S) + net_credit

        # Quick Monte Carlo for expected P&L to enrich output and enable UI guardrails
        try:
            iv_c = float(c_row["iv"]) if c_row["iv"] == c_row["iv"] else 0.20
            iv_p = float(p_row["iv"]) if p_row["iv"] == p_row["iv"] else 0.20
            iv_mc = (iv_c + iv_p) / 2.0
            mc_params = dict(
                S0=S,
                days=D,
                iv=iv_mc,
                Kc=float(c_row["K"]),
                call_premium=float(call_prem),
                Kp=float(p_row["K"]),
                put_premium=float(put_debit),
                div_ps_annual=float(div_ps_annual),
            )
            prelim = score
            # Per-exp counter (collar generates one per row; cap overall per exp)
            mc_counter = {"count": 0}
            mc_result = _maybe_mc("COLLAR", mc_params, rf=risk_free, mu=0.0, prelim_score=prelim, perf_cfg=perf_cfg, exp_counter=mc_counter)
            mc_expected_pnl = mc_result.get('pnl_expected', float("nan"))
            mc_roi_ann = mc_result.get('roi_ann_expected', float("nan"))
            mc_pnl_p5 = mc_result.get('pnl_p5', float("nan"))
            mc_roi_p5 = mc_result.get('roi_ann_p5', float("nan"))
        except Exception:
            mc_expected_pnl = float("nan")
            mc_roi_ann = float("nan")
            mc_pnl_p5 = float("nan")
            mc_roi_p5 = float("nan")

        # Unified risk-reward score
        try:
            # Use worst leg spread for spread component
            avg_spread = max(float(c_row.get("spread%") or 20.0), float(p_row.get("spread%") or 20.0))
            worst_oi = min(_safe_int(c_row["oi"], 0), _safe_int(p_row["oi"], 0))
            worst_vol = min(_safe_int(c_row["volume"], 0), _safe_int(p_row["volume"], 0))
            # Use min cushion as risk proxy
            cushion_min = min(put_cushion, call_cushion) if (put_cushion == put_cushion and call_cushion == call_cushion) else float("nan")
            rr_score = unified_risk_reward_score(
                expected_roi_ann_dec=mc_roi_ann if mc_roi_ann == mc_roi_ann else 0.0,
                p5_pnl=mc_pnl_p5,
                capital=S * 100.0,
                spread_pct=avg_spread,
                oi=worst_oi,
                volume=worst_vol,
                cushion_sigma=cushion_min,
            )
        except Exception:
            rr_score = float("nan")

        # Check expiration risk for Collar (2-leg strategy)
        exp_risk = check_expiration_risk(
            expiration_str=exp,
            strategy="Collar",
            open_interest=min(_safe_int(c_row["oi"], 0), _safe_int(p_row["oi"], 0)),  # Use worst case
            bid_ask_spread_pct=max(c_row["spread%"] or 0.0, p_row["spread%"] or 0.0)  # Use worst case
        )

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
            "CallVolume": _safe_int(c_row["volume"], 0), "PutVolume": _safe_int(p_row["volume"], 0),
            "Floor$/sh": round(floor, 2), "Cap$/sh": round(cap_to_call, 2),
            "PutCushionσ": round(put_cushion, 2) if put_cushion == put_cushion else float("nan"),
            "CallCushionσ": round(call_cushion, 2) if call_cushion == call_cushion else float("nan"),
            "DivInWindow": round(div_in_period, 4),
            "AssignRisk": bool(assign_risk),
            "Score": round(score, 6),
            "Capital": int(S * 100.0),
            "RiskRewardScore": rr_score if rr_score == rr_score else float("nan"),
            
            # Monte Carlo expected value (for guardrails and EV assessment)
            "MC_ExpectedPnL": round(mc_expected_pnl, 2) if mc_expected_pnl == mc_expected_pnl else float("nan"),
            "MC_ROI_ann%": round(mc_roi_ann * 100.0, 2) if mc_roi_ann == mc_roi_ann else float("nan"),
            "MC_PnL_p5": round(mc_pnl_p5, 2) if mc_pnl_p5 == mc_pnl_p5 else float("nan"),
            "MC_ROI_ann_p5%": round(mc_roi_p5 * 100.0, 2) if mc_roi_p5 == mc_roi_p5 else float("nan"),
            
            # Expiration risk assessment
            "ExpType": exp_risk["expiration_type"],
            "ExpRisk": exp_risk["risk_level"],
            "ExpAction": exp_risk["action"],
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = apply_unified_score(df)
        df = df.sort_values(["UnifiedScore", "Score", "ROI%_ann"], ascending=[False, False, False]).reset_index(drop=True)
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
    # Import from strategy_lab to avoid circular import at module level
    from data_fetching import (
        fetch_price, fetch_expirations, fetch_chain,
        _get_num_from_row, _safe_int, effective_credit, 
        effective_debit, estimate_next_ex_div, check_expiration_risk
    )
    
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame()

    expirations = fetch_expirations(ticker)
    earn_date = get_earnings_date(stock)
    div_ps_annual, div_y = trailing_dividend_info(stock, S)
    
    rows = []
    # Performance configuration for MC gating
    perf_cfg = _get_scan_perf_config()
    
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
            prem = effective_credit(
                bid, ask, last,
                oi=_safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0),
                volume=_safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0),
                dte=D
            )
            
            if prem != prem or prem <= 0:
                continue
            
            oi = _safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0)
            vol = _safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0)
            spread_pct = compute_spread_pct(bid, ask, prem)
            
            puts_sell.append({
                "K": K, "prem": prem, "delta": pd_val, "iv": iv,
                "spread%": spread_pct, "oi": oi, "volume": vol, "bid": bid, "ask": ask
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
            prem = effective_credit(
                bid, ask, last,
                oi=_safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0),
                volume=_safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0),
                dte=D
            )
            
            if prem != prem or prem <= 0:
                continue
            
            oi = _safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0)
            vol = _safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0)
            spread_pct = compute_spread_pct(bid, ask, prem)
            
            calls_sell.append({
                "K": K, "prem": prem, "delta": cd_val, "iv": iv,
                "spread%": spread_pct, "oi": oi, "volume": vol, "bid": bid, "ask": ask
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
        pl_oi = _safe_int(_get_num_from_row(pl_row, ["openInterest", "oi", "open_interest"], 0), 0)
        pl_vol = _safe_int(_get_num_from_row(pl_row, ["volume", "Volume", "vol"], 0), 0)
        pl_prem = effective_debit(pl_bid, pl_ask, pl_last, oi=pl_oi, volume=pl_vol, dte=D)
        
        # Get long call premium (debit)
        cl_row = call_long.iloc[0]
        cl_bid = _get_num_from_row(cl_row, ["bid", "Bid", "b"])
        cl_ask = _get_num_from_row(cl_row, ["ask", "Ask", "a"])
        cl_last = _get_num_from_row(cl_row, ["lastPrice", "last", "mark", "mid"])
        cl_oi = _safe_int(_get_num_from_row(cl_row, ["openInterest", "oi", "open_interest"], 0), 0)
        cl_vol = _safe_int(_get_num_from_row(cl_row, ["volume", "Volume", "vol"], 0), 0)
        cl_prem = effective_debit(cl_bid, cl_ask, cl_last, oi=cl_oi, volume=cl_vol, dte=D)
        
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
        
        # Average liquidity across short legs; default to 20% if unknown
        avg_spread = ((ps_row.get("spread%") or 20.0) + (cs_row.get("spread%") or 20.0)) / 2.0
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
        
        # ===== HARD FILTER: Extremely low liquidity is intolerable for 4-leg strategy =====
        # Iron Condor requires tighter liquidity due to 4 legs to manage
        ps_oi = int(ps_row["oi"]) if ps_row["oi"] == ps_row["oi"] else 0
        cs_oi = int(cs_row["oi"]) if cs_row["oi"] == cs_row["oi"] else 0
        min_oi_all_legs = min(ps_oi, pl_oi, cs_oi, cl_oi)
        if min_oi_all_legs < 50:  # Stricter than other strategies
            # Skip - insufficient liquidity across all legs
            continue
        
        # ===== APPLY BEST-PRACTICE PENALTIES TO SCORE =====
        # Tenor penalty: 30-60 DTE is sweet spot for Iron Condor
        tenor_ok = 30 <= D <= 60
        tenor_penalty = 1.0 if tenor_ok else 0.70  # 30% reduction outside sweet spot
        
        # Volume/OI penalty: STRICTER for 4-leg strategy (use worst leg)
        ps_vol = int(ps_row["volume"]) if ps_row["volume"] == ps_row["volume"] else 0
        cs_vol = int(cs_row["volume"]) if cs_row["volume"] == cs_row["volume"] else 0
        
        ps_vol_oi = ps_vol / ps_oi if ps_oi > 0 else 0.0
        cs_vol_oi = cs_vol / cs_oi if cs_oi > 0 else 0.0
        
        # Use minimum of short legs (most critical for liquidity)
        vol_oi_ratio = min(ps_vol_oi, cs_vol_oi)
        
        if vol_oi_ratio >= 0.5:
            vol_penalty = 1.0  # Healthy turnover
        elif vol_oi_ratio >= 0.3:  # STRICTER: 0.3 instead of 0.25 for 4-leg
            vol_penalty = 0.80  # 20% reduction (stricter)
        else:
            vol_penalty = 0.55  # 45% reduction (much stricter for IC)
        
        # Apply all penalties to base score
        score = score * tenor_penalty * vol_penalty
        
        # Quick Monte Carlo for expected P&L to enrich output and enable UI guardrails
        try:
            mc_params = dict(
                S0=S,
                days=D,
                iv=iv_avg if (iv_avg == iv_avg and iv_avg > 0.0) else 0.20,
                put_short_strike=float(Kps),
                put_long_strike=float(Kpl),
                call_short_strike=float(Kcs),
                call_long_strike=float(Kcl),
                net_credit=float(net_credit),
            )
            prelim = score
            mc_counter = {"count": 0}
            mc_result = _maybe_mc("IRON_CONDOR", mc_params, rf=risk_free, mu=0.0, prelim_score=prelim, perf_cfg=perf_cfg, exp_counter=mc_counter)
            mc_expected_pnl = mc_result.get('pnl_expected', float("nan"))
            mc_roi_ann = mc_result.get('roi_ann_expected', float("nan"))
            mc_pnl_p5 = mc_result.get('pnl_p5', float("nan"))
            mc_roi_p5 = mc_result.get('roi_ann_p5', float("nan"))
        except Exception:
            mc_expected_pnl = float("nan")
            mc_roi_ann = float("nan")
            mc_pnl_p5 = float("nan")
            mc_roi_p5 = float("nan")

        # Unified risk-reward score
        try:
            worst_oi = min(int(ps_row["oi"]) if ps_row["oi"] == ps_row["oi"] else 0,
                           int(cs_row["oi"]) if cs_row["oi"] == cs_row["oi"] else 0)
            worst_vol = min(int(ps_row["volume"]) if ps_row["volume"] == ps_row["volume"] else 0,
                            int(cs_row["volume"]) if cs_row["volume"] == cs_row["volume"] else 0)
            cushion_min = min(put_cushion, call_cushion) if (put_cushion == put_cushion and call_cushion == call_cushion) else float("nan")
            rr_score = unified_risk_reward_score(
                expected_roi_ann_dec=mc_roi_ann if mc_roi_ann == mc_roi_ann else 0.0,
                p5_pnl=mc_pnl_p5,
                capital=capital,
                spread_pct=avg_spread,
                oi=worst_oi,
                volume=worst_vol,
                cushion_sigma=cushion_min,
            )
        except Exception:
            rr_score = float("nan")

        # Check expiration risk for Iron Condor (4-leg strategy - EXTREME sensitivity)
        exp_risk = check_expiration_risk(
            expiration_str=exp,
            strategy="Iron Condor",
            open_interest=min(int(ps_row["oi"]), int(cs_row["oi"])),  # Use worst case across all legs
            bid_ask_spread_pct=avg_spread
        )
        
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
            "RiskRewardScore": rr_score if rr_score == rr_score else float("nan"),
            
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
            "PutShortVolume": int(ps_row["volume"]),
            "CallShortVolume": int(cs_row["volume"]),
            
            "IV": round(iv_avg * 100.0, 2),
            "Score": round(score, 6),
            
            # Monte Carlo expected value (for guardrails and EV assessment)
            "MC_ExpectedPnL": round(mc_expected_pnl, 2) if mc_expected_pnl == mc_expected_pnl else float("nan"),
            "MC_ROI_ann%": round(mc_roi_ann * 100.0, 2) if mc_roi_ann == mc_roi_ann else float("nan"),
            "MC_PnL_p5": round(mc_pnl_p5, 2) if mc_pnl_p5 == mc_pnl_p5 else float("nan"),
            "MC_ROI_ann_p5%": round(mc_roi_p5 * 100.0, 2) if mc_roi_p5 == mc_roi_p5 else float("nan"),
            
            # Expiration risk assessment
            "ExpType": exp_risk["expiration_type"],
            "ExpRisk": exp_risk["risk_level"],
            "ExpAction": exp_risk["action"],
        })
    
    df = pd.DataFrame(rows)
    if not df.empty:
        df = apply_unified_score(df)
        df = df.sort_values(["UnifiedScore", "Score", "ROI%_ann"], ascending=[False, False, False]).reset_index(drop=True)
    return df



def analyze_bull_put_spread(ticker, *, min_days=1, days_limit, min_oi, max_spread,
                             min_roi, min_cushion, min_poew, earn_window, risk_free,
                             spread_width=5.0, target_delta_short=0.20, bill_yield=0.0):
    """
    Scan for Bull Put Spread opportunities (bullish/neutral credit spread with defined risk).
    
    Structure:
    - SELL put at higher strike (Ks) - collect premium
    - BUY put at lower strike (Kl) - limit downside, Kl = Ks - spread_width
    
    This creates a NET CREDIT spread with:
    - Max Profit = Net Credit
    - Max Loss = Spread Width - Net Credit
    - Breakeven = Short Strike - Net Credit
    
    Returns DataFrame with ranked Bull Put Spread opportunities.
    """
    # Import from strategy_lab to avoid circular import at module level
    from data_fetching import (
        fetch_price, fetch_expirations, fetch_chain,
        _get_num_from_row, _safe_int, effective_credit, 
        effective_debit, estimate_next_ex_div, check_expiration_risk
    )
    
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame()

    expirations = fetch_expirations(ticker)
    earn_date = get_earnings_date(stock)
    div_ps_annual, div_y = trailing_dividend_info(stock, S)
    
    rows = []
    # Performance configuration for MC gating
    perf_cfg = _get_scan_perf_config()
    
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
            puts = chain_all[chain_all["type"].str.lower() == "put"].copy()
        else:
            puts = chain_all.copy()
        
        if puts.empty:
            continue
        
        # Find potential short puts (sell) - OTM puts with target delta
        puts_sell = []
        for _, r in puts.iterrows():
            K = _get_num_from_row(r, ["strike", "Strike", "k", "K"], float("nan"))
            if not (K == K and K > 0 and K < S):  # Must be OTM (below stock price)
                continue
            
            iv = _get_num_from_row(r, ["impliedVolatility", "iv", "IV"], 0.20)
            if iv == iv and iv > 3.0:
                iv = iv / 100.0
            
            # Calculate put delta (negative for puts)
            pd_val = put_delta(S, K, risk_free, iv, T, div_y)
            
            bid = _get_num_from_row(r, ["bid", "Bid", "b"])
            ask = _get_num_from_row(r, ["ask", "Ask", "a"])
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"])
            prem = effective_credit(
                bid, ask, last,
                oi=_safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0),
                volume=_safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0),
                dte=D
            )
            
            if prem != prem or prem <= 0:
                continue
            
            oi = _safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0)
            vol = _safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0)
            spread_pct = compute_spread_pct(bid, ask, prem)
            
            puts_sell.append({
                "K": K, "prem": prem, "delta": pd_val, "iv": iv,
                "spread%": spread_pct, "oi": oi, "volume": vol, "bid": bid, "ask": ask
            })
        
        if not puts_sell:
            continue
        
        # For each potential short put, find corresponding long put
        for ps in puts_sell:
            Ks = float(ps["K"])  # Short strike (higher)
            Kl = Ks - spread_width  # Long strike (lower)
            
            # Check OI and spread on short leg
            if ps["oi"] < min_oi:
                continue
            if ps["spread%"] is not None and ps["spread%"] > max_spread:
                continue
            
            # Find matching long put at Kl
            put_long = puts[puts.apply(
                lambda r: abs(_get_num_from_row(r, ["strike", "Strike", "k", "K"], 0) - Kl) < 0.5, 
                axis=1
            )]
            
            if put_long.empty:
                continue
            
            # Get long put premium (what we pay)
            pl_row = put_long.iloc[0]
            pl_bid = _get_num_from_row(pl_row, ["bid", "Bid", "b"])
            pl_ask = _get_num_from_row(pl_row, ["ask", "Ask", "a"])
            pl_last = _get_num_from_row(pl_row, ["lastPrice", "last", "mark", "mid"])
            pl_oi = _safe_int(_get_num_from_row(pl_row, ["openInterest", "oi", "open_interest"], 0), 0)
            pl_vol = _safe_int(_get_num_from_row(pl_row, ["volume", "Volume", "vol"], 0), 0)
            pl_prem = effective_debit(pl_bid, pl_ask, pl_last, oi=pl_oi, volume=pl_vol, dte=D)
            
            if pl_prem != pl_prem or pl_prem <= 0:
                continue
            
            # Check long leg OI
            if pl_oi < min_oi:
                continue
            
            # Calculate net credit (what we collect)
            net_credit = ps["prem"] - pl_prem
            
            if net_credit <= 0:
                continue
            
            # Calculate risk metrics
            max_loss = spread_width - net_credit
            capital_at_risk = max_loss * 100.0  # Per contract
            
            # ROI calculations
            roi_cycle = net_credit / max_loss if max_loss > 0 else 0.0
            roi_ann = roi_cycle * (365.0 / D)
            
            if roi_ann < float(min_roi):
                continue
            
            # OTM% based on short strike
            otm_pct = (S - Ks) / S * 100.0
            
            # Probability of expiring worthless (POEW) for short put
            poew = 1.0 - abs(ps["delta"]) if ps["delta"] == ps["delta"] else float("nan")
            
            if poew == poew and poew < float(min_poew):
                continue
            
            # Cushion calculation (standard deviations to short strike)
            exp_mv = expected_move(S, ps["iv"], T)
            cushion_sigma = (S - Ks) / exp_mv if exp_mv > 0 else float("nan")
            
            if cushion_sigma == cushion_sigma and cushion_sigma < float(min_cushion):
                continue
            
            # Calculate combined Greeks (net position)
            # Short put theta (positive for us)
            ps_theta = put_theta(S, Ks, risk_free, ps["iv"], T, div_y)
            pl_iv = _get_num_from_row(pl_row, ["impliedVolatility", "iv", "IV"], 0.20)
            if pl_iv == pl_iv and pl_iv > 3.0:
                pl_iv = pl_iv / 100.0
            pl_theta = put_theta(S, Kl, risk_free, pl_iv, T, div_y)
            
            # Net theta (short - long, since we're selling short and buying long)
            net_theta = ps_theta - pl_theta  # Should be negative (we lose time value)
            theta_per_day = abs(net_theta) * 100.0  # Per contract, absolute value
            
            # Gamma (risk measure)
            ps_gamma = option_gamma(S, Ks, risk_free, ps["iv"], T, div_y)
            pl_gamma = option_gamma(S, Kl, risk_free, pl_iv, T, div_y)
            net_gamma = ps_gamma - pl_gamma  # Short gamma - long gamma
            gamma_per_contract = abs(net_gamma) * 100.0
            
            # Theta/Gamma ratio
            theta_gamma_ratio = float("nan")
            if gamma_per_contract > 0 and theta_per_day == theta_per_day:
                theta_gamma_ratio = theta_per_day / gamma_per_contract
            
            # Delta (directional exposure)
            pl_delta = put_delta(S, Kl, risk_free, pl_iv, T, div_y)
            net_delta = ps["delta"] - pl_delta  # Negative (bearish)
            
            # Vega (IV sensitivity)
            ps_vega = option_vega(S, Ks, risk_free, ps["iv"], T, div_y)
            pl_vega = option_vega(S, Kl, risk_free, pl_iv, T, div_y)
            net_vega = ps_vega - pl_vega  # Negative (we want IV to decrease)
            
            # Scoring (normalize ROI for credit spreads to be comparable with CSPs)
            # Credit spreads naturally have higher ROI% due to lower capital requirement
            # Cap ROI contribution to prevent score inflation
            # CSP typical range: 10-50% annualized (0.10-0.50)
            # Credit spread typical range: 50-200% annualized (0.50-2.00)
            # Normalize by capping at 1.0 for scoring purposes
            roi_for_score = min(roi_ann, 1.0)  # Cap at 100% for scoring
            
            liq_score = max(0.0, 1.0 - min((ps["spread%"] or 20.0), 20.0) / 20.0)
            
            # Theta/Gamma scoring (same as CSP)
            if theta_gamma_ratio == theta_gamma_ratio:
                if theta_gamma_ratio < 0.5:
                    tg_score = 0.0
                elif theta_gamma_ratio < 0.8:
                    tg_score = theta_gamma_ratio / 0.8
                elif theta_gamma_ratio <= 3.0:
                    tg_score = 1.0
                elif theta_gamma_ratio <= 5.0:
                    tg_score = 1.0 - (theta_gamma_ratio - 3.0) * 0.25
                elif theta_gamma_ratio <= 10.0:
                    tg_score = 0.5 - (theta_gamma_ratio - 5.0) * 0.06
                else:
                    tg_score = 0.1
            else:
                tg_score = 0.0
            
            score = (0.35 * roi_for_score +
                     0.15 * (min(cushion_sigma, 3.0) / 3.0 if cushion_sigma == cushion_sigma else 0.0) +
                     0.30 * tg_score +
                     0.20 * liq_score)
            
            # Days to earnings
            days_to_earnings = None
            if earn_date is not None:
                days_to_earnings = (earn_date - datetime.now(timezone.utc).date()).days
            
            # ===== HARD FILTER: Earnings within 3 days is intolerable risk =====
            if days_to_earnings is not None and 0 <= days_to_earnings <= 3:
                # Skip this opportunity entirely - earnings too close
                continue
            
            # ===== APPLY BEST-PRACTICE PENALTIES TO SCORE =====
            # Tenor penalty: 21-45 DTE is sweet spot for Bull Put Spread
            tenor_ok = 21 <= D <= 45
            tenor_penalty = 1.0 if tenor_ok else 0.70  # 30% reduction outside sweet spot
            
            # Volume/OI penalty: check liquidity health on short leg
            vol_val = ps.get("volume")
            vol_oi_ratio = (vol_val / ps["oi"]) if (ps["oi"] > 0 and vol_val == vol_val) else 0.0
            if vol_oi_ratio >= 0.5:
                vol_penalty = 1.0  # Healthy turnover
            elif vol_oi_ratio >= 0.25:
                vol_penalty = 0.85  # Moderate, 15% reduction
            else:
                vol_penalty = 0.65  # Stale OI risk, 35% reduction
            
            # Earnings proximity penalty (beyond hard filter)
            if days_to_earnings is not None and days_to_earnings <= D + 7:
                # Earnings within cycle or shortly after
                earnings_penalty = 0.60  # 40% reduction - high vol event risk
            else:
                earnings_penalty = 1.0  # Safe
            
            # Theta/Gamma penalty: ≥1.0 is preferred
            if theta_gamma_ratio == theta_gamma_ratio:
                if theta_gamma_ratio >= 1.0:
                    tg_penalty = 1.0  # Good risk-adjusted decay
                elif theta_gamma_ratio >= 0.5:
                    tg_penalty = 0.85  # Acceptable, 15% reduction
                else:
                    tg_penalty = 0.70  # High gamma risk, 30% reduction
            else:
                tg_penalty = 0.85  # Unknown, slight penalty
            
            # Apply all penalties to base score
            score = score * tenor_penalty * vol_penalty * earnings_penalty * tg_penalty
            
            # ===== MONTE CARLO EXPECTED P&L PENALTY =====
            # Run quick MC simulation to validate expected P&L
            # This prevents negative-EV trades from scoring highly
            mc_params = {
                "S0": S,
                "days": D,
                "iv": ps["iv"],
                "sell_strike": Ks,
                "buy_strike": Kl,
                "net_credit": net_credit
            }
            try:
                prelim = score
                mc_counter = {"count": 0}
                mc_result = _maybe_mc("BULL_PUT_SPREAD", mc_params, rf=risk_free, mu=0.0, prelim_score=prelim, perf_cfg=perf_cfg, exp_counter=mc_counter)
                mc_expected_pnl = mc_result['pnl_expected']
                mc_roi_ann = mc_result['roi_ann_expected']
                mc_pnl_p5 = mc_result.get('pnl_p5', float("nan"))
                mc_roi_p5 = mc_result.get('roi_ann_p5', float("nan"))
                
                # Calculate MC penalty based on expected P&L vs max profit
                max_profit = net_credit * 100.0
                if mc_expected_pnl < 0:
                    # Negative expected P&L: severe penalty (80% reduction)
                    mc_penalty = 0.20
                elif mc_expected_pnl < max_profit * 0.25:
                    # Expected P&L < 25% of max profit: strong penalty (50-80% reduction)
                    mc_penalty = 0.20 + (mc_expected_pnl / (max_profit * 0.25)) * 0.30
                elif mc_expected_pnl < max_profit * 0.50:
                    # Expected P&L < 50% of max profit: moderate penalty (20-50% reduction)
                    mc_penalty = 0.50 + ((mc_expected_pnl - max_profit * 0.25) / (max_profit * 0.25)) * 0.30
                elif mc_expected_pnl < max_profit * 0.75:
                    # Expected P&L < 75% of max profit: light penalty (10-20% reduction)
                    mc_penalty = 0.80 + ((mc_expected_pnl - max_profit * 0.50) / (max_profit * 0.25)) * 0.10
                else:
                    # Expected P&L >= 75% of max profit: minimal/no penalty
                    mc_penalty = 0.90 + min((mc_expected_pnl - max_profit * 0.75) / (max_profit * 0.25), 1.0) * 0.10
            except Exception:
                # If MC fails, apply moderate penalty as conservative approach
                mc_penalty = 0.70
                mc_expected_pnl = float("nan")
                mc_roi_ann = float("nan")
                mc_pnl_p5 = float("nan")
                mc_roi_p5 = float("nan")
            
            # Apply MC penalty with HIGH WEIGHT (70% contribution to final score)
            # This makes MC validation the DOMINANT factor
            # Formula: score * (0.30 + 0.70 * mc_penalty)
            # - Negative MC P&L: 0.30 + 0.70*0.20 = 0.44 (56% reduction)
            # - MC P&L at 50% of max: 0.30 + 0.70*0.80 = 0.86 (14% reduction)
            # - MC P&L at 90% of max: 0.30 + 0.70*0.96 = 0.97 (3% reduction)
            score = score * (0.30 + 0.70 * mc_penalty)
            
            # Check expiration risk for Bull Put Spread (2-leg strategy)
            exp_risk = check_expiration_risk(
                expiration_str=exp,
                strategy="Bull Put Spread",
                open_interest=ps["oi"],  # Use short leg OI (typically worst case)
                bid_ask_spread_pct=ps["spread%"] or 0.0
            )

            # Unified cross-strategy risk-reward score (0..1)
            try:
                rr_score = unified_risk_reward_score(
                    expected_roi_ann_dec=mc_roi_ann if mc_roi_ann == mc_roi_ann else 0.0,
                    p5_pnl=mc_pnl_p5,
                    capital=capital_at_risk,
                    spread_pct=ps.get("spread%"),
                    oi=ps.get("oi"),
                    volume=ps.get("volume"),
                    cushion_sigma=cushion_sigma,
                )
            except Exception:
                rr_score = float("nan")
            
            rows.append({
                "Strategy": "BullPutSpread",
                "Ticker": ticker,
                "Price": round(S, 2),
                "Exp": exp,
                "Days": D,
                "SellStrike": float(Ks),  # Short strike (higher)
                "BuyStrike": float(Kl),   # Long strike (lower)
                "Spread": float(spread_width),
                "NetCredit": round(net_credit, 2),
                "MaxLoss": round(max_loss, 2),
                "OTM%": round(otm_pct, 2),
                "ROI%": round(roi_cycle * 100.0, 2),
                "ROI%_ann": round(roi_ann * 100.0, 2),
                "Δ": round(net_delta, 3),
                "Γ": round(net_gamma, 4),
                "Θ": round(net_theta, 3),
                "Vρ": round(net_vega, 3),
                "IV": round(ps["iv"] * 100.0, 2),
                "POEW": round(poew, 3) if poew == poew else float("nan"),
                "CushionSigma": round(cushion_sigma, 2) if cushion_sigma == cushion_sigma else float("nan"),
                "Theta/Gamma": round(theta_gamma_ratio, 2) if theta_gamma_ratio == theta_gamma_ratio else float("nan"),
                "Spread%": round(ps["spread%"], 2) if ps["spread%"] is not None else float("nan"),
                "OI": ps["oi"],
                "Volume": ps["volume"],
                "Capital": int(capital_at_risk),
                "DaysToEarnings": days_to_earnings,
                "MC_ExpectedPnL": round(mc_expected_pnl, 2) if mc_expected_pnl == mc_expected_pnl else float("nan"),
                "MC_ROI_ann%": round(mc_roi_ann * 100.0, 2) if mc_roi_ann == mc_roi_ann else float("nan"),
                "MC_PnL_p5": round(mc_pnl_p5, 2) if mc_pnl_p5 == mc_pnl_p5 else float("nan"),
                "MC_ROI_ann_p5%": round(mc_roi_p5 * 100.0, 2) if mc_roi_p5 == mc_roi_p5 else float("nan"),
                "Score": round(score, 6),
                "RiskRewardScore": rr_score if rr_score == rr_score else float("nan"),
                # Option symbols for order generation
                "SellLeg": None,  # Will be populated by UI if needed
                "BuyLeg": None,
                
                # Expiration risk assessment
                "ExpType": exp_risk["expiration_type"],
                "ExpRisk": exp_risk["risk_level"],
                "ExpAction": exp_risk["action"],
            })
    
    df = pd.DataFrame(rows)
    if not df.empty:
        df = apply_unified_score(df)
        df = df.sort_values(["UnifiedScore", "Score", "ROI%_ann"], ascending=[False, False, False]).reset_index(drop=True)
    return df


def analyze_bear_call_spread(ticker, *, min_days=1, days_limit, min_oi, max_spread,
                              min_roi, min_cushion, min_poew, earn_window, risk_free,
                              spread_width=5.0, target_delta_short=0.20, bill_yield=0.0):
    """
    Scan for Bear Call Spread opportunities (bearish/neutral credit spread with defined risk).
    
    Structure:
    - SELL call at lower strike (Ks) - collect premium
    - BUY call at higher strike (Kl) - limit upside, Kl = Ks + spread_width
    
    This creates a NET CREDIT spread with:
    - Max Profit = Net Credit
    - Max Loss = Spread Width - Net Credit
    - Breakeven = Short Strike + Net Credit
    
    Returns DataFrame with ranked Bear Call Spread opportunities.
    """
    # Import from strategy_lab to avoid circular import at module level
    from data_fetching import (
        fetch_price, fetch_expirations, fetch_chain,
        _get_num_from_row, _safe_int, effective_credit, 
        effective_debit, estimate_next_ex_div, check_expiration_risk
    )
    
    stock = yf.Ticker(ticker)
    try:
        S = fetch_price(ticker)
    except Exception:
        return pd.DataFrame()

    expirations = fetch_expirations(ticker)
    earn_date = get_earnings_date(stock)
    div_ps_annual, div_y = trailing_dividend_info(stock, S)
    
    rows = []
    # Performance configuration for MC gating
    perf_cfg = _get_scan_perf_config()
    
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
        else:
            calls = chain_all.copy()
        
        if calls.empty:
            continue
        
        # Find potential short calls (sell) - OTM calls with target delta
        calls_sell = []
        for _, r in calls.iterrows():
            K = _get_num_from_row(r, ["strike", "Strike", "k", "K"], float("nan"))
            if not (K == K and K > 0 and K > S):  # Must be OTM (above stock price)
                continue
            
            iv = _get_num_from_row(r, ["impliedVolatility", "iv", "IV"], 0.20)
            if iv == iv and iv > 3.0:
                iv = iv / 100.0
            
            # Calculate call delta (positive for calls)
            cd_val = call_delta(S, K, risk_free, iv, T, div_y)
            
            bid = _get_num_from_row(r, ["bid", "Bid", "b"])
            ask = _get_num_from_row(r, ["ask", "Ask", "a"])
            last = _get_num_from_row(r, ["lastPrice", "last", "mark", "mid"])
            prem = effective_credit(
                bid, ask, last,
                oi=_safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0),
                volume=_safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0),
                dte=D
            )
            
            if prem != prem or prem <= 0:
                continue
            
            oi = _safe_int(_get_num_from_row(r, ["openInterest", "oi", "open_interest"], 0), 0)
            vol = _safe_int(_get_num_from_row(r, ["volume", "Volume", "vol"], 0), 0)
            spread_pct = compute_spread_pct(bid, ask, prem)
            
            calls_sell.append({
                "K": K, "prem": prem, "delta": cd_val, "iv": iv,
                "spread%": spread_pct, "oi": oi, "volume": vol, "bid": bid, "ask": ask
            })
        
        if not calls_sell:
            continue
        
        # For each potential short call, find corresponding long call
        for cs in calls_sell:
            Ks = float(cs["K"])  # Short strike (lower)
            Kl = Ks + spread_width  # Long strike (higher)
            
            # Check OI and spread on short leg
            if cs["oi"] < min_oi:
                continue
            if cs["spread%"] is not None and cs["spread%"] > max_spread:
                continue
            
            # Find matching long call at Kl
            call_long = calls[calls.apply(
                lambda r: abs(_get_num_from_row(r, ["strike", "Strike", "k", "K"], 0) - Kl) < 0.5, 
                axis=1
            )]
            
            if call_long.empty:
                continue
            
            # Get long call premium (what we pay)
            cl_row = call_long.iloc[0]
            cl_bid = _get_num_from_row(cl_row, ["bid", "Bid", "b"])
            cl_ask = _get_num_from_row(cl_row, ["ask", "Ask", "a"])
            cl_last = _get_num_from_row(cl_row, ["lastPrice", "last", "mark", "mid"])
            cl_oi = _safe_int(_get_num_from_row(cl_row, ["openInterest", "oi", "open_interest"], 0), 0)
            cl_vol = _safe_int(_get_num_from_row(cl_row, ["volume", "Volume", "vol"], 0), 0)
            cl_prem = effective_debit(cl_bid, cl_ask, cl_last, oi=cl_oi, volume=cl_vol, dte=D)
            
            if cl_prem != cl_prem or cl_prem <= 0:
                continue
            
            # Check long leg OI
            if cl_oi < min_oi:
                continue
            
            # Calculate net credit (what we collect)
            net_credit = cs["prem"] - cl_prem
            
            if net_credit <= 0:
                continue
            
            # Calculate risk metrics
            max_loss = spread_width - net_credit
            capital_at_risk = max_loss * 100.0  # Per contract
            
            # ROI calculations
            roi_cycle = net_credit / max_loss if max_loss > 0 else 0.0
            roi_ann = roi_cycle * (365.0 / D)
            
            if roi_ann < float(min_roi):
                continue
            
            # OTM% based on short strike
            otm_pct = (Ks - S) / S * 100.0
            
            # Probability of expiring worthless (POEW) for short call
            poew = 1.0 - abs(cs["delta"]) if cs["delta"] == cs["delta"] else float("nan")
            
            if poew == poew and poew < float(min_poew):
                continue
            
            # Cushion calculation (standard deviations to short strike)
            exp_mv = expected_move(S, cs["iv"], T)
            cushion_sigma = (Ks - S) / exp_mv if exp_mv > 0 else float("nan")
            
            if cushion_sigma == cushion_sigma and cushion_sigma < float(min_cushion):
                continue
            
            # Calculate combined Greeks (net position)
            # Short call theta (positive for us)
            cs_theta = call_theta(S, Ks, risk_free, cs["iv"], T, div_y)
            cl_iv = _get_num_from_row(cl_row, ["impliedVolatility", "iv", "IV"], 0.20)
            if cl_iv == cl_iv and cl_iv > 3.0:
                cl_iv = cl_iv / 100.0
            cl_theta = call_theta(S, Kl, risk_free, cl_iv, T, div_y)
            
            # Net theta (short - long, since we're selling short and buying long)
            net_theta = cs_theta - cl_theta  # Should be negative (we lose time value)
            theta_per_day = abs(net_theta) * 100.0  # Per contract, absolute value
            
            # Gamma (risk measure)
            cs_gamma = option_gamma(S, Ks, risk_free, cs["iv"], T, div_y)
            cl_gamma = option_gamma(S, Kl, risk_free, cl_iv, T, div_y)
            net_gamma = cs_gamma - cl_gamma  # Short gamma - long gamma
            gamma_per_contract = abs(net_gamma) * 100.0
            
            # Theta/Gamma ratio
            theta_gamma_ratio = float("nan")
            if gamma_per_contract > 0 and theta_per_day == theta_per_day:
                theta_gamma_ratio = theta_per_day / gamma_per_contract
            
            # Delta (directional exposure)
            cl_delta = call_delta(S, Kl, risk_free, cl_iv, T, div_y)
            net_delta = cs["delta"] - cl_delta  # Positive (bullish)
            
            # Vega (IV sensitivity)
            cs_vega = option_vega(S, Ks, risk_free, cs["iv"], T, div_y)
            cl_vega = option_vega(S, Kl, risk_free, cl_iv, T, div_y)
            net_vega = cs_vega - cl_vega  # Negative (we want IV to decrease)
            
            # Scoring (normalize ROI for credit spreads to be comparable with CSPs)
            # Credit spreads naturally have higher ROI% due to lower capital requirement
            # Cap ROI contribution to prevent score inflation
            roi_for_score = min(roi_ann, 1.0)  # Cap at 100% for scoring
            
            liq_score = max(0.0, 1.0 - min((cs["spread%"] or 20.0), 20.0) / 20.0)
            
            # Theta/Gamma scoring (same as CSP)
            if theta_gamma_ratio == theta_gamma_ratio:
                if theta_gamma_ratio < 0.5:
                    tg_score = 0.0
                elif theta_gamma_ratio < 0.8:
                    tg_score = theta_gamma_ratio / 0.8
                elif theta_gamma_ratio <= 3.0:
                    tg_score = 1.0
                elif theta_gamma_ratio <= 5.0:
                    tg_score = 1.0 - (theta_gamma_ratio - 3.0) * 0.25
                elif theta_gamma_ratio <= 10.0:
                    tg_score = 0.5 - (theta_gamma_ratio - 5.0) * 0.06
                else:
                    tg_score = 0.1
            else:
                tg_score = 0.0
            
            score = (0.35 * roi_for_score +
                     0.15 * (min(cushion_sigma, 3.0) / 3.0 if cushion_sigma == cushion_sigma else 0.0) +
                     0.30 * tg_score +
                     0.20 * liq_score)
            
            # Days to earnings
            days_to_earnings = None
            if earn_date is not None:
                days_to_earnings = (earn_date - datetime.now(timezone.utc).date()).days
            
            # ===== HARD FILTER: Earnings within 3 days is intolerable risk =====
            if days_to_earnings is not None and 0 <= days_to_earnings <= 3:
                # Skip this opportunity entirely - earnings too close
                continue
            
            # ===== APPLY BEST-PRACTICE PENALTIES TO SCORE =====
            # Tenor penalty: 21-45 DTE is sweet spot for Bear Call Spread
            tenor_ok = 21 <= D <= 45
            tenor_penalty = 1.0 if tenor_ok else 0.70  # 30% reduction outside sweet spot
            
            # Volume/OI penalty: check liquidity health on short leg
            vol_val = cs.get("volume")
            vol_oi_ratio = (vol_val / cs["oi"]) if (cs["oi"] > 0 and vol_val == vol_val) else 0.0
            if vol_oi_ratio >= 0.5:
                vol_penalty = 1.0  # Healthy turnover
            elif vol_oi_ratio >= 0.25:
                vol_penalty = 0.85  # Moderate, 15% reduction
            else:
                vol_penalty = 0.65  # Stale OI risk, 35% reduction
            
            # Earnings proximity penalty (beyond hard filter)
            if days_to_earnings is not None and days_to_earnings <= D + 7:
                # Earnings within cycle or shortly after
                earnings_penalty = 0.60  # 40% reduction - high vol event risk
            else:
                earnings_penalty = 1.0  # Safe
            
            # Theta/Gamma penalty: ≥1.0 is preferred
            if theta_gamma_ratio == theta_gamma_ratio:
                if theta_gamma_ratio >= 1.0:
                    tg_penalty = 1.0  # Good risk-adjusted decay
                elif theta_gamma_ratio >= 0.5:
                    tg_penalty = 0.85  # Acceptable, 15% reduction
                else:
                    tg_penalty = 0.70  # High gamma risk, 30% reduction
            else:
                tg_penalty = 0.85  # Unknown, slight penalty
            
            # Apply all penalties to base score
            score = score * tenor_penalty * vol_penalty * earnings_penalty * tg_penalty
            
            # ===== MONTE CARLO EXPECTED P&L PENALTY =====
            # Run quick MC simulation to validate expected P&L
            # This prevents negative-EV trades from scoring highly
            mc_params = {
                "S0": S,
                "days": D,
                "iv": cs["iv"],
                "sell_strike": Ks,
                "buy_strike": Kl,
                "net_credit": net_credit
            }
            try:
                prelim = score
                mc_counter = {"count": 0}
                mc_result = _maybe_mc("BEAR_CALL_SPREAD", mc_params, rf=risk_free, mu=0.0, prelim_score=prelim, perf_cfg=perf_cfg, exp_counter=mc_counter)
                mc_expected_pnl = mc_result['pnl_expected']
                mc_roi_ann = mc_result['roi_ann_expected']
                mc_pnl_p5 = mc_result.get('pnl_p5', float("nan"))
                mc_roi_p5 = mc_result.get('roi_ann_p5', float("nan"))
                
                # Calculate MC penalty based on expected P&L vs max profit
                max_profit = net_credit * 100.0
                if mc_expected_pnl < 0:
                    # Negative expected P&L: severe penalty (80% reduction)
                    mc_penalty = 0.20
                elif mc_expected_pnl < max_profit * 0.25:
                    # Expected P&L < 25% of max profit: strong penalty (50-80% reduction)
                    mc_penalty = 0.20 + (mc_expected_pnl / (max_profit * 0.25)) * 0.30
                elif mc_expected_pnl < max_profit * 0.50:
                    # Expected P&L < 50% of max profit: moderate penalty (20-50% reduction)
                    mc_penalty = 0.50 + ((mc_expected_pnl - max_profit * 0.25) / (max_profit * 0.25)) * 0.30
                elif mc_expected_pnl < max_profit * 0.75:
                    # Expected P&L < 75% of max profit: light penalty (10-20% reduction)
                    mc_penalty = 0.80 + ((mc_expected_pnl - max_profit * 0.50) / (max_profit * 0.25)) * 0.10
                else:
                    # Expected P&L >= 75% of max profit: minimal/no penalty
                    mc_penalty = 0.90 + min((mc_expected_pnl - max_profit * 0.75) / (max_profit * 0.25), 1.0) * 0.10
            except Exception:
                # If MC fails, apply moderate penalty as conservative approach
                mc_penalty = 0.70
                mc_expected_pnl = float("nan")
                mc_roi_ann = float("nan")
                mc_pnl_p5 = float("nan")
                mc_roi_p5 = float("nan")
            
            # Apply MC penalty with HIGH WEIGHT (70% contribution to final score)
            # This makes MC validation the DOMINANT factor
            # Formula: score * (0.30 + 0.70 * mc_penalty)
            # - Negative MC P&L: 0.30 + 0.70*0.20 = 0.44 (56% reduction)
            # - MC P&L at 50% of max: 0.30 + 0.70*0.80 = 0.86 (14% reduction)
            # - MC P&L at 90% of max: 0.30 + 0.70*0.96 = 0.97 (3% reduction)
            score = score * (0.30 + 0.70 * mc_penalty)
            
            # Check expiration risk for Bear Call Spread (2-leg strategy)
            exp_risk = check_expiration_risk(
                expiration_str=exp,
                strategy="Bear Call Spread",
                open_interest=cs["oi"],  # Use short leg OI (typically worst case)
                bid_ask_spread_pct=cs["spread%"] or 0.0
            )

            # Unified cross-strategy risk-reward score (0..1)
            try:
                rr_score = unified_risk_reward_score(
                    expected_roi_ann_dec=mc_roi_ann if mc_roi_ann == mc_roi_ann else 0.0,
                    p5_pnl=mc_pnl_p5,
                    capital=capital_at_risk,
                    spread_pct=cs.get("spread%"),
                    oi=cs.get("oi"),
                    volume=cs.get("volume"),
                    cushion_sigma=cushion_sigma,
                )
            except Exception:
                rr_score = float("nan")
            
            rows.append({
                "Strategy": "BearCallSpread",
                "Ticker": ticker,
                "Price": round(S, 2),
                "Exp": exp,
                "Days": D,
                "SellStrike": float(Ks),  # Short strike (lower)
                "BuyStrike": float(Kl),   # Long strike (higher)
                "Spread": float(spread_width),
                "NetCredit": round(net_credit, 2),
                "MaxLoss": round(max_loss, 2),
                "OTM%": round(otm_pct, 2),
                "ROI%": round(roi_cycle * 100.0, 2),
                "ROI%_ann": round(roi_ann * 100.0, 2),
                "Δ": round(net_delta, 3),
                "Γ": round(net_gamma, 4),
                "Θ": round(net_theta, 3),
                "Vρ": round(net_vega, 3),
                "IV": round(cs["iv"] * 100.0, 2),
                "POEW": round(poew, 3) if poew == poew else float("nan"),
                "CushionSigma": round(cushion_sigma, 2) if cushion_sigma == cushion_sigma else float("nan"),
                "Theta/Gamma": round(theta_gamma_ratio, 2) if theta_gamma_ratio == theta_gamma_ratio else float("nan"),
                "Spread%": round(cs["spread%"], 2) if cs["spread%"] is not None else float("nan"),
                "OI": cs["oi"],
                "Volume": cs["volume"],
                "Capital": int(capital_at_risk),
                "DaysToEarnings": days_to_earnings,
                "MC_ExpectedPnL": round(mc_expected_pnl, 2) if mc_expected_pnl == mc_expected_pnl else float("nan"),
                "MC_ROI_ann%": round(mc_roi_ann * 100.0, 2) if mc_roi_ann == mc_roi_ann else float("nan"),
                "MC_PnL_p5": round(mc_pnl_p5, 2) if mc_pnl_p5 == mc_pnl_p5 else float("nan"),
                "MC_ROI_ann_p5%": round(mc_roi_p5 * 100.0, 2) if mc_roi_p5 == mc_roi_p5 else float("nan"),
                "Score": round(score, 6),
                "RiskRewardScore": rr_score if rr_score == rr_score else float("nan"),
                # Option symbols for order generation
                "SellLeg": None,  # Will be populated by UI if needed
                "BuyLeg": None,
                
                # Expiration risk assessment
                "ExpType": exp_risk["expiration_type"],
                "ExpRisk": exp_risk["risk_level"],
                "ExpAction": exp_risk["action"],
            })
    
    df = pd.DataFrame(rows)
    if not df.empty:
        df = apply_unified_score(df)
        df = df.sort_values(["UnifiedScore", "Score", "ROI%_ann"], ascending=[False, False, False]).reset_index(drop=True)
    return df


def prescreen_tickers(tickers, min_price=5.0, max_price=1000.0, min_avg_volume=1_500_000,
                      min_hv=18.0, max_hv=70.0, min_option_volume=150, check_liquidity=True):
    """
    Pre-screen tickers for options income strategy suitability.
    Uses parallel processing for faster execution on large ticker lists.

    OPTIMIZED FOR SHORT-TERM (10-45 DTE) INCOME STRATEGIES
    Scoring aligns with strategy aggregate score components:
    - High ROI potential (premium/price ratio)
    - Good theta/gamma zones (moderate volatility)
    - Strong liquidity (tight spreads, high OI)
    - Adequate cushion potential (HV 20-50% sweet spot)

    NEW IMPROVEMENTS (v2.0):
    1. ✅ Checks 21-45 DTE sweet spot availability (filters if none exist)
    2. ✅ Analyzes OTM strikes (5-15% range) where CSP/CC actually trade
    3. ✅ Applies Vol/OI ratio penalties matching strategy scoring
    4. ✅ Checks earnings proximity and applies penalties
    5. ✅ Refined IV/HV sweet spots for better alignment
    6. ✅ Hard filter on >15% bid-ask spreads (intolerable)

    Filters based on:
    - Stock price range (avoid penny stocks, expensive shares)
    - Average daily volume (liquidity)
    - Historical volatility (premium potential) - HV in PERCENTAGE (e.g., 25.0 = 25%)
    - Options market activity (tradeable markets)
    - Tenor availability (options in preferred 21-45 DTE range)
    - Earnings proximity (downweights near-term events)

    UNITS:
    - HV_30d%: Historical volatility as PERCENTAGE (e.g., 25.0 for 25%)
    - IV%: Implied volatility as PERCENTAGE (e.g., 30.0 for 30%)
    - IV/HV: Ratio of the two percentages (both normalized to same units)

    Returns:
        pd.DataFrame with screening metrics for passed tickers, sorted by quality score
    """
    # Import from strategy_lab to avoid circular import at module level
    from data_fetching import (
        fetch_price, fetch_expirations, fetch_chain,
        _get_num_from_row, _safe_int
    )

    def screen_single_ticker(ticker):
        """Screen a single ticker - designed for parallel execution"""
        try:
            # Prefer configured provider (Schwab/Polygon) for quotes/chain; fallback to yfinance
            provider = None
            try:
                from providers import get_provider
                provider = get_provider()
            except Exception:
                provider = None

            # Fetch 3 months of history (for avg volume and HV) via yfinance for speed/availability
            stock = yf.Ticker(ticker)
            hist = stock.history(period="3mo")

            if hist.empty or len(hist) < 20:
                return None

            # Current price: prefer provider quote, else last close from yfinance
            try:
                current_price = float(provider.last_price(ticker)) if provider else float(hist['Close'].iloc[-1])
            except Exception:
                current_price = float(hist['Close'].iloc[-1])
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
            if provider is not None:
                try:
                    expirations = provider.expirations(ticker)
                except Exception:
                    expirations = []
            else:
                expirations = stock.options
            if not expirations or len(expirations) == 0:
                return None

            # Find a suitable expiration (not expiring today, prefer 21-45 DTE)
            today = datetime.now().date()
            suitable_exp = None
            for exp_str in expirations[:15]:
                try:
                    exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                    days_to_exp = (exp_date - today).days
                    if 7 <= days_to_exp <= 60:  # At least a week out, max 2 months
                        suitable_exp = exp_str
                        break
                except:
                    continue
            
            # Fallback to first non-expiring expiration
            if not suitable_exp:
                for exp_str in expirations[:5]:
                    try:
                        exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                        days_to_exp = (exp_date - today).days
                        if days_to_exp > 0:
                            suitable_exp = exp_str
                            break
                    except:
                        continue
            
            # If still no suitable expiration, use first one
            if not suitable_exp:
                suitable_exp = expirations[0]

            # Get option chain for suitable expiration
            try:
                if provider is not None:
                    chain_df = provider.chain_snapshot_df(ticker, suitable_exp)
                    if isinstance(chain_df, pd.DataFrame) and ('type' in chain_df.columns):
                        type_lower = chain_df['type'].astype(str).str.lower()
                        calls_df = chain_df[type_lower == 'call'].copy()
                        puts_df = chain_df[type_lower == 'put'].copy()
                    else:
                        # Unexpected schema; treat as empty frames to skip
                        calls_df = pd.DataFrame()
                        puts_df = pd.DataFrame()
                else:
                    chain = stock.option_chain(suitable_exp)
                    calls_df = chain.calls.copy()
                    puts_df = chain.puts.copy()

                # Find ATM IV with robust source preference and sanity checks
                # Strategy: prefer provider IV when available; fall back to yfinance; as last resort use HV proxy.
                def _atm_iv_from_df(df: pd.DataFrame, spot: float) -> float:
                    try:
                        if df is None or df.empty:
                            return float('nan')
                        # nearest strike by absolute diff to spot
                        pos = np.abs(pd.to_numeric(df['strike'], errors='coerce').to_numpy() - float(spot)).argmin()
                        row = df.iloc[int(pos)]
                        for col in ['impliedVolatility', 'IV', 'iv', 'implied_volatility']:
                            if col in row.index:
                                return float(pd.to_numeric(row[col], errors='coerce'))
                        return float('nan')
                    except Exception:
                        return float('nan')

                def _is_sane_iv(iv_dec_or_pct: float) -> bool:
                    try:
                        x = float(iv_dec_or_pct)
                        if not (x == x) or x <= 0:
                            return False
                        # Accept plausible inputs: decimals ~0.03..3.0 OR percents ~3..300
                        return (0.03 <= x <= 3.0) or (3.0 <= x <= 300.0)
                    except Exception:
                        return False

                iv_source = 'unknown'
                iv_num = float('nan')  # decimal 0..1 expected after normalization

                # 1) Provider first (calls then puts)
                prov_iv = float('nan')
                if not calls_df.empty:
                    prov_iv = _atm_iv_from_df(calls_df, current_price)
                if (not _is_sane_iv(prov_iv)) and not puts_df.empty:
                    prov_iv = _atm_iv_from_df(puts_df, current_price)

                if _is_sane_iv(prov_iv):
                    iv_source = 'provider'
                    iv_num = prov_iv
                else:
                    # 2) yfinance fallback
                    yf_chain = None
                    try:
                        yf_chain = stock.option_chain(suitable_exp)
                    except Exception:
                        yf_chain = None
                    yf_iv = float('nan')
                    if yf_chain is not None and hasattr(yf_chain, 'calls') and not yf_chain.calls.empty:
                        yf_iv = _atm_iv_from_df(yf_chain.calls, current_price)
                    if (not _is_sane_iv(yf_iv)) and yf_chain is not None and hasattr(yf_chain, 'puts') and not yf_chain.puts.empty:
                        yf_iv = _atm_iv_from_df(yf_chain.puts, current_price)
                    if _is_sane_iv(yf_iv):
                        iv_source = 'yfinance'
                        iv_num = yf_iv

                # 3) As last resort, use HV proxy (assume IV ~= HV)
                if not _is_sane_iv(iv_num):
                    iv_source = 'hv_proxy'
                    iv_num = max(0.01, float(hv_30) / 100.0)  # ensure small positive

                # Normalize units to decimal: treat values >5 as percentage inputs
                if iv_num > 5.0:
                    iv_num = iv_num / 100.0

                # Final sanity clamp to realistic bounds to avoid YF 1e-05 bugs
                if not (0.01 <= iv_num <= 3.0):
                    # If wildly out of bounds, fall back to HV proxy
                    iv_source = 'hv_proxy'
                    iv_num = max(0.01, float(hv_30) / 100.0)

                iv_pct = iv_num * 100.0  # percentage for display/comparison

                # ===== IMPROVEMENT #2: Check multiple OTM strikes (CSP/CC sweet spot) =====
                # CSP typically sells 5-15% OTM puts, CC sells 5-15% OTM calls
                # Check strikes in this range for better liquidity signal
                otm_puts = puts_df[
                    (puts_df['strike'] >= current_price * 0.85) & 
                    (puts_df['strike'] <= current_price * 0.95)
                ] if not puts_df.empty else puts_df
                otm_calls = calls_df[
                    (calls_df['strike'] >= current_price * 1.05) & 
                    (calls_df['strike'] <= current_price * 1.15)
                ] if not calls_df.empty else calls_df
                
                # Helpers to robustly extract column maxima across provider schemas
                def _col_max(df: pd.DataFrame, cols: list[str]) -> int:
                    for c in cols:
                        if c in df.columns:
                            s = pd.to_numeric(df[c], errors='coerce').fillna(0)
                            if not s.empty:
                                m = float(s.max())
                                if m == m and m > 0:
                                    return int(m)
                    return 0

                def _best_metrics(df_puts: pd.DataFrame, df_calls: pd.DataFrame) -> tuple[int, int]:
                    put_vol = _col_max(df_puts, ['volume', 'Volume', 'totalVolume']) if not df_puts.empty else 0
                    put_oi = _col_max(df_puts, ['openInterest', 'oi', 'OpenInterest', 'OI']) if not df_puts.empty else 0
                    call_vol = _col_max(df_calls, ['volume', 'Volume', 'totalVolume']) if not df_calls.empty else 0
                    call_oi = _col_max(df_calls, ['openInterest', 'oi', 'OpenInterest', 'OI']) if not df_calls.empty else 0
                    return max(put_vol, call_vol), max(put_oi, call_oi)

                # Use BEST liquidity from OTM range (where actual trades happen)
                opt_volume, opt_oi = _best_metrics(otm_puts, otm_calls)
                opt_vol_src = 'provider'

                # Fallback A: if OTM windows are empty/zero, use ATM vicinity from provider frames
                if (opt_volume == 0 or opt_oi == 0) and (not puts_df.empty or not calls_df.empty):
                    near_puts = puts_df[(puts_df['strike'] >= current_price * 0.90) & (puts_df['strike'] <= current_price * 1.00)] if not puts_df.empty else puts_df
                    near_calls = calls_df[(calls_df['strike'] >= current_price * 1.00) & (calls_df['strike'] <= current_price * 1.10)] if not calls_df.empty else calls_df
                    vol_fb, oi_fb = _best_metrics(near_puts, near_calls)
                    before_v, before_oi = opt_volume, opt_oi
                    opt_volume = max(opt_volume, vol_fb)
                    opt_oi = max(opt_oi, oi_fb)
                    if (before_v == 0 and vol_fb > 0) or (before_oi == 0 and oi_fb > 0):
                        opt_vol_src = 'provider'

                # Fallback B: if still zero, compute from a yfinance chain regardless of IV source
                try:
                    if (opt_volume == 0 or opt_oi == 0):
                        try:
                            yf_chain_local = stock.option_chain(suitable_exp)
                        except Exception:
                            yf_chain_local = None
                        if yf_chain_local is not None:
                            yf_puts = yf_chain_local.puts.copy() if hasattr(yf_chain_local, 'puts') else pd.DataFrame()
                            yf_calls = yf_chain_local.calls.copy() if hasattr(yf_chain_local, 'calls') else pd.DataFrame()
                            if not yf_puts.empty or not yf_calls.empty:
                                otm_puts_yf = yf_puts[(yf_puts['strike'] >= current_price * 0.85) & (yf_puts['strike'] <= current_price * 0.95)] if not yf_puts.empty else yf_puts
                                otm_calls_yf = yf_calls[(yf_calls['strike'] >= current_price * 1.05) & (yf_calls['strike'] <= current_price * 1.15)] if not yf_calls.empty else yf_calls
                                vol_yf, oi_yf = _best_metrics(otm_puts_yf, otm_calls_yf)
                                if vol_yf == 0 or oi_yf == 0:
                                    # Try near-ATM for YF
                                    near_puts_yf = yf_puts[(yf_puts['strike'] >= current_price * 0.90) & (yf_puts['strike'] <= current_price * 1.00)] if not yf_puts.empty else yf_puts
                                    near_calls_yf = yf_calls[(yf_calls['strike'] >= current_price * 1.00) & (yf_calls['strike'] <= current_price * 1.10)] if not yf_calls.empty else yf_calls
                                    vol2_yf, oi2_yf = _best_metrics(near_puts_yf, near_calls_yf)
                                    vol_yf = max(vol_yf, vol2_yf)
                                    oi_yf = max(oi_yf, oi2_yf)
                                before_v, before_oi = opt_volume, opt_oi
                                opt_volume = max(opt_volume, vol_yf)
                                opt_oi = max(opt_oi, oi_yf)
                                if (before_v == 0 and vol_yf > 0) or (before_oi == 0 and oi_yf > 0):
                                    opt_vol_src = 'yfinance'
                except Exception:
                    pass

                if check_liquidity and (opt_volume < min_option_volume and opt_oi < min_option_volume * 10):
                    return None

                # ===== IMPROVEMENT #1: Check tenor availability in sweet spot =====
                # Strategies prefer 21-45 DTE - verify options exist in this range
                today = datetime.now().date()
                exp_dates = []
                for exp_str in expirations[:15]:  # Check first 15 expirations (increased from 10)
                    try:
                        exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                        days_to_exp = (exp_date - today).days
                        if 21 <= days_to_exp <= 60:  # Expanded range (was 21-45)
                            exp_dates.append(days_to_exp)
                    except:
                        continue
                
                # More lenient: require at least 1 expiration (not necessarily in 21-45)
                # but track count for scoring
                sweet_spot_count = len(exp_dates)
                # If no expirations at all in reasonable range, skip
                if len(expirations) == 0:
                    return None

                # Bid-Ask spread check for liquidity quality
                # Calculate average spread from OTM strikes (more realistic)
                # But use median instead of mean to avoid outlier strikes skewing results
                spread_pcts = []
                for strikes_df in [otm_puts, otm_calls]:
                    if not strikes_df.empty:
                        for _, row in strikes_df.head(5).iterrows():  # Only check top 5 strikes
                            bid = row.get('bid', 0) or row.get('Bid', 0) or 0
                            ask = row.get('ask', 0) or row.get('Ask', 0) or 0
                            mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else 0
                            if mid > 0.05:  # Lowered from 0.10 - count options with $0.05+ premium
                                spread_pcts.append((ask - bid) / mid * 100.0)
                
                # Use median (less sensitive to outliers) and fallback to a reasonable default
                # If we have ANY valid spreads, use them; otherwise assume moderate spread (15%)
                spread_sample_count = len(spread_pcts)
                if spread_sample_count >= 2:
                    spread_pct = np.median(spread_pcts)
                elif spread_pcts:
                    spread_pct = spread_pcts[0]
                else:
                    # No valid spreads found - likely low premium options
                    # Don't hard fail, use a moderate default for scoring
                    spread_pct = 15.0
                used_default_spread = (spread_sample_count < 2)
                
                # ===== BONUS: Hard filter on intolerable spreads =====
                # More selective threshold: 30% (was 40%) - filter out very illiquid options
                # Only hard filter if we actually measured real spreads (not using default)
                if len(spread_pcts) >= 2 and spread_pct > 30.0:
                    return None  # Too illiquid for income strategies

                # Calculate IV Rank proxy (IV vs HV)
                # Both iv_pct and hv_30 are in percentage units (e.g., 25.0 for 25%)
                # Ratio of 1.0 = IV equals HV; >1.0 = IV elevated; <1.0 = IV compressed
                iv_hv_ratio = iv_pct / hv_30 if hv_30 > 0 else 1.0

                # ===== IMPROVEMENT #3: Add Volume/OI ratio check =====
                vol_oi_ratio = (opt_volume / opt_oi) if (isinstance(opt_oi, (int, float)) and opt_oi > 0) else 0.0

                # ===== IMPROVED QUALITY SCORE ALIGNED WITH STRATEGY SCORING =====

                # 1. ROI Potential (35% weight in strategy)
                # Optimize for IV in 25-40% range; degrade below 20% and above 50%
                if iv_pct < 20:
                    roi_score = 0.45  # too little premium likely
                elif iv_pct <= 40:
                    roi_score = 1.0   # optimal premium vs risk
                elif iv_pct <= 50:
                    roi_score = 0.9   # still good but elevated risk
                elif iv_pct <= 70:
                    # linearly fade from 0.9 at 50% to ~0.5 at 70%
                    roi_score = 0.9 - ((iv_pct - 50.0) / 20.0) * 0.4
                else:
                    # very high IV -> keep a soft floor to avoid total dismissal
                    roi_score = 0.45
                roi_score = max(0.3, min(roi_score, 1.0))

                # 2. Theta/Gamma Optimization (30% weight in strategy)
                # Optimize for HV in 20-35% range; penalize too low or too high
                if hv_30 < 20:
                    tg_score = 0.35  # low premium regime
                elif hv_30 <= 35:
                    tg_score = 1.0
                elif hv_30 <= 50:
                    # fade from 1.0 at 35% to 0.8 at 50%
                    tg_score = 1.0 - ((hv_30 - 35.0) / 15.0) * 0.2
                else:
                    # elevated HV beyond 50%: downweight further but keep a floor
                    tg_score = 0.2
                tg_score = max(0.2, min(tg_score, 1.0))

                # 3. Liquidity Score (20% weight in strategy)
                # Based on spread, volume, OI, AND vol/oi ratio
                spread_score = max(0.0, 1.0 - (spread_pct / 20.0))  # Perfect at 0%, zero at 20%
                volume_score = min((opt_volume or 0) / 200, 1.0)  # Max at 200 contracts
                oi_score = min((opt_oi or 0) / 1000, 1.0)         # Max at 1000 OI

                # Apply Vol/OI ratio penalty (matches strategy penalties)
                if vol_oi_ratio < 0.25:
                    vol_oi_penalty = 0.65  # Stale OI - 35% reduction
                elif vol_oi_ratio < 0.5:
                    vol_oi_penalty = 0.85  # Moderate - 15% reduction
                else:
                    vol_oi_penalty = 1.0
                liq_score = (0.5 * spread_score + 0.3 * volume_score + 0.2 * oi_score) * vol_oi_penalty

                # 4. Cushion/Safety Score (15% weight in strategy)
                # Use average volume and ATR% (14) as a light-weight stability proxy
                vol_score = min(avg_volume / 2_000_000, 1.0)  # cap at 2M avg volume

                try:
                    highs = hist['High'].to_numpy(dtype=float, copy=False)
                    lows = hist['Low'].to_numpy(dtype=float, copy=False)
                    closes = hist['Close'].to_numpy(dtype=float, copy=False)
                    prev_close = np.roll(closes, 1)
                    tr = np.maximum(
                        highs - lows,
                        np.maximum(np.abs(highs - prev_close), np.abs(lows - prev_close))
                    )
                    tr = tr[1:]  # drop first (prev_close invalid)
                    if len(tr) >= 14:
                        atr14 = pd.Series(tr).rolling(14).mean().iloc[-1]
                        close_ref = closes[-1] if len(closes) > 0 else np.nan
                        atr_pct = (atr14 / close_ref) * 100.0 if (close_ref == close_ref and close_ref > 0) else np.nan
                    else:
                        atr_pct = float('nan')
                except Exception:
                    atr_pct = float('nan')

                if atr_pct == atr_pct:
                    # Scale: ATR% ~2% -> strong (close to 1), 10% -> weak (floor)
                    stability_score = max(0.3, 1.0 - atr_pct / 10.0)
                else:
                    # Fallback to simple high-low range if ATR not available
                    price_range_pct = ((hist['High'].iloc[-20:].mean() - hist['Low'].iloc[-20:].mean()) /
                                       hist['Close'].iloc[-20:].mean() * 100.0)
                    stability_score = max(0.3, 1.0 - price_range_pct / 10.0)

                cushion_score = 0.6 * vol_score + 0.4 * stability_score

                # ===== IMPROVEMENT #4: Add earnings proximity check =====
                earnings_penalty = 1.0
                days_to_earnings = None
                try:
                    # Quick earnings check (uses yfinance cache)
                    earnings = stock.calendar
                    if earnings is not None and 'Earnings Date' in earnings:
                        next_earnings = earnings['Earnings Date'][0]
                        if isinstance(next_earnings, str):
                            next_earnings = pd.to_datetime(next_earnings).date()
                        elif hasattr(next_earnings, 'date'):
                            next_earnings = next_earnings.date()

                        days_to_earnings = (next_earnings - datetime.now().date()).days

                        # More lenient: only hard filter if ≤3 days (matches strategy)
                        # Don't pre-filter on longer windows - let penalties handle it
                        if 0 <= days_to_earnings <= 3:
                            # Intolerable - would be hard filtered in strategy
                            return None
                        elif 0 <= days_to_earnings <= 45:  # Within scan window
                            # Downweight proportionally: 45 days = 1.0x, 3 days would be 0.6x
                            # Linear scale: penalty = 0.6 + (days - 3) / 42 * 0.4
                            earnings_penalty = max(0.7, 0.6 + ((days_to_earnings - 3) / 42.0) * 0.4)
                except Exception:
                    # Don't fail pre-screen if earnings lookup fails
                    pass

                # ===== WEIGHTED QUALITY SCORE (aligned with strategy weights) =====
                # Compute display-rounded components and use them in final score for consistency
                roi_disp = round(roi_score, 2)
                tg_disp = round(tg_score, 2)
                liq_disp = round(liq_score, 2)
                safe_disp = round(cushion_score, 2)
                earn_pen_disp = round(earnings_penalty, 2)

                quality_score = (0.35 * roi_disp +      # ROI potential
                                 0.30 * tg_disp +        # Theta/Gamma optimization
                                 0.20 * liq_disp +       # Liquidity
                                 0.15 * safe_disp)       # Safety/cushion
                # Apply earnings penalty (display-rounded) to overall score
                quality_score *= earn_pen_disp

                # IV/HV ratio for additional insight
                # Ideal: 1.0-1.5 (IV slightly elevated vs HV = good premium without crazy risk)
                iv_rank_proxy = "HIGH" if iv_hv_ratio > 1.3 else (
                    "NORMAL" if iv_hv_ratio > 0.8 else "LOW")

                # ---------------- Data quality validation ----------------
                data_warnings: list[str] = []
                if iv_source == 'hv_proxy':
                    data_warnings.append('IV_HV_PROXY')
                elif iv_source == 'yfinance':
                    data_warnings.append('IV_FROM_YF')
                if opt_vol_src == 'yfinance':
                    data_warnings.append('VOLUME_FROM_YF')
                if used_default_spread:
                    data_warnings.append('SPREAD_DEFAULT')
                if sweet_spot_count == 0:
                    data_warnings.append('NO_SWEET_DTES')
                # Sanity ranges for IV/HV (percentage units)
                if not (5.0 <= iv_pct <= 200.0):
                    data_warnings.append('IV_OUT_OF_RANGE')
                if not (5.0 <= hv_30 <= 200.0):
                    data_warnings.append('HV_OUT_OF_RANGE')

                # Compute a conservative data quality score 0..1
                dq = 1.0
                if iv_source == 'hv_proxy':
                    dq -= 0.25
                elif iv_source == 'yfinance':
                    dq -= 0.10
                if opt_vol_src == 'yfinance':
                    dq -= 0.05
                if used_default_spread:
                    dq -= 0.10
                if sweet_spot_count == 0:
                    dq -= 0.05
                if ('IV_OUT_OF_RANGE' in data_warnings) or ('HV_OUT_OF_RANGE' in data_warnings):
                    dq -= 0.15
                data_quality_score = max(0.0, min(1.0, dq))

                quality_score_data_adj = round(quality_score * data_quality_score, 3)

                return {
                    'Ticker': ticker,
                    'Price': round(current_price, 2),
                    'Avg_Volume': int(avg_volume),
                    'HV_30d%': round(hv_30, 1),
                    'IV%': round(iv_pct, 1),
                    'IV/HV': round(iv_hv_ratio, 2),
                    'IV_Rank': iv_rank_proxy,
                    'IV_Source': iv_source,
                    'Spread%': round(spread_pct, 1),
                    'Spread_SampleCount': int(spread_sample_count),
                    'Opt_Volume': int(opt_volume) if isinstance(opt_volume, (int, float)) and opt_volume == opt_volume else 0,
                    'Opt_OI': int(opt_oi) if isinstance(opt_oi, (int, float)) and opt_oi == opt_oi else 0,
                    'Vol/OI': round(vol_oi_ratio, 2),
                    'OptVolSrc': opt_vol_src,
                    'Expirations': len(expirations),
                    'Sweet_Spot_DTEs': sweet_spot_count,  # Number of expirations in 21-60 DTE range
                    'Days_To_Earnings': int(days_to_earnings) if isinstance(days_to_earnings, (int, float)) else days_to_earnings,
                    'Quality_Score': round(quality_score, 3),
                    'Data_Quality_Score': round(data_quality_score, 3),
                    'Quality_Score_DataAdj': quality_score_data_adj,
                    'Data_Warnings': ','.join(data_warnings) if data_warnings else '',
                    # Component scores for transparency
                    'ROI_Score': roi_disp,
                    'TG_Score': tg_disp,
                    'Liq_Score': liq_disp,
                    'Safe_Score': safe_disp,
                    'Earnings_Penalty': earn_pen_disp
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
    sort_col = 'Quality_Score_DataAdj' if 'Quality_Score_DataAdj' in df.columns else 'Quality_Score'
    df = df.sort_values(sort_col, ascending=False).reset_index(drop=True)
    return df
