#!/usr/bin/env python3
# app.py — OTM short put scanner with risk/return scoring (cash-secured puts, 100% margin)

import argparse
import math
import numpy as np

from datetime import datetime, timedelta

import pandas as pd
# Import provider factory
from providers import get_provider


def _safe_float(x, default=float("nan")):
    try:
        v = float(x)
        return v
    except Exception:
        return default


def _bs_d1_d2(S, K, r, sigma, T):
    # Black–Scholes d1/d2 for probability approximations (risk-neutral)
    # Guard for invalids
    if S <= 0 or K <= 0 or sigma <= 0 or T <= 0:
        return float("nan"), float("nan")
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / \
            (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return d1, d2
    except Exception:
        return float("nan"), float("nan")


def _norm_cdf(x):
    # Standard normal CDF
    try:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    except Exception:
        return float("nan")


def analyze_puts(
    ticker,
    days_limit=45,
    min_otm_pct=10.0,
    min_oi=200,
    max_spread_pct=10.0,
    min_roi_ann=0.12,      # 12% annualized ROI threshold (on collateral)
    min_cushion_sigma=1.0,  # >= 1σ away
    min_poew=0.65,         # probability of expiring worthless
    earn_window_days=5,    # skip expirations within +/- earn_window_days of earnings
    weights=None,          # dict of weights for score
    # e.g., 20000 means skip collateral > $20k per contract
    per_contract_collateral_cap=None,
    risk_free_rate=0.00,   # BS r (annualized). For short horizons, 0 is fine.
    provider=None,         # Allow passing a provider instance
):
    # Get provider if not passed
    if provider is None:
        provider = get_provider()
    
    # Current price
    try:
        price = provider.last_price(ticker)
    except Exception:
        return pd.DataFrame()

    # Get expirations
    try:
        expirations = provider.expirations(ticker)
    except Exception:
        return pd.DataFrame()
    
    if not expirations:
        return pd.DataFrame()

    # Technicals for "ownability" checks
    sma200, yr_low, yr_high = provider.get_technicals(ticker)

    # Earnings date guard
    earn_date = provider.get_earnings_date(ticker)

    rows = []

    default_weights = dict(
        yield_w=0.45,    # ROI on collateral
        poew_w=0.25,     # probability of expiring worthless
        cushion_w=0.25,  # sigma cushion to strike
        liq_w=0.05,      # liquidity (spread-based)
        ownable_bonus=0.05,  # small boost if cost basis < SMA200 and < 75% of 52w high
    )
    if weights:
        default_weights.update(weights)
    w = default_weights

    for exp in expirations:
        try:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
        except Exception:
            continue
        days_to_exp = (exp_date - datetime.utcnow().date()).days
        if days_to_exp <= 0 or days_to_exp > int(days_limit):
            continue

        # Earnings guard
        if earn_date is not None and abs((earn_date - exp_date).days) <= int(earn_window_days):
            # skip expirations too close to earnings
            continue

        try:
            opt = provider.chain_snapshot_df(ticker, exp)
        except Exception:
            continue

        for _, row in opt.iterrows():
            K = _safe_float(row.get("strike"))
            if not (K == K):  # NaN check
                continue

            bid = _safe_float(row.get("bid"))
            ask = _safe_float(row.get("ask"))
            last = _safe_float(row.get("lastPrice"), 0.0)
            # mid-price fallback heuristic
            if bid == bid and ask == ask and bid > 0 and ask > 0:
                P = (bid + ask) / 2.0
            else:
                P = last if last == last and last > 0 else _safe_float(
                    row.get("mark"), 0.0)

            # Basic derived measures
            otm_pct = (price - K) / price * 100.0
            if otm_pct < float(min_otm_pct):
                continue

            # Annualized ROI on collateral (cash-secured put; collateral per share ~ strike)
            roi_ann = (P / K) * (365.0 / days_to_exp) if (K >
                                                          0 and days_to_exp > 0) else float("nan")
            if roi_ann != roi_ann or roi_ann < float(min_roi_ann):
                continue

            # IV (decimal), OI, spread
            iv = _safe_float(row.get("impliedVolatility"))
            oi = int(_safe_float(row.get("openInterest"), 0))
            if oi < int(min_oi):
                continue

            mid = P
            spread_pct = float("inf")
            if bid == bid and ask == ask and mid > 0:
                spread_pct = ((ask - bid) / mid) * 100.0
            if spread_pct > float(max_spread_pct):
                continue

            # Black–Scholes probability S_T > K ≈ N(d2) — that is POEW for a short put
            # T in years; iv already decimal (e.g., 0.35)
            T = days_to_exp / 365.0
            d1, d2 = _bs_d1_d2(price, K, float(risk_free_rate), iv, T) if iv == iv else (
                float("nan"), float("nan"))
            poew = _norm_cdf(d2) if d2 == d2 else float(
                "nan")  # Prob(Expire Worthless) ~ N(d2)

            if poew == poew and poew < float(min_poew):
                continue

            # Expected move & sigma cushion
            exp_move = price * iv * \
                math.sqrt(T) if (iv == iv and T > 0) else float("nan")
            cushion_sigma = ((price - K) / exp_move) if (exp_move ==
                                                         exp_move and exp_move > 0) else float("nan")
            if cushion_sigma == cushion_sigma and cushion_sigma < float(min_cushion_sigma):
                continue

            # Downside cost basis if assigned; collateral; optional cap check
            cost_basis = K - P
            collateral = K * 100.0
            if per_contract_collateral_cap is not None and collateral > float(per_contract_collateral_cap):
                continue

            # Ownability heuristic (optional): cost basis below SMA200 and < 75% of 52w high
            ownable = False
            if cost_basis == cost_basis:
                cond1 = (sma200 == sma200 and cost_basis <= sma200)
                cond2 = (yr_high == yr_high and cost_basis <= 0.75 * yr_high)
                ownable = bool(cond1 and cond2)

            # Liquidity score (0..1): 1 if very tight, 0 if very wide (cap at 20%)
            liq_score = max(0.0, 1.0 - min(spread_pct, 20.0) /
                            20.0) if spread_pct == spread_pct else 0.0

            # Score (transparent, tunable)
            # Cap cushion at 3σ to avoid letting extreme values dominate
            cushion_capped = min(
                cushion_sigma, 3.0) if cushion_sigma == cushion_sigma else 0.0
            score = (
                w["yield_w"] * roi_ann
                + w["poew_w"] * (poew if poew == poew else 0.0)
                + w["cushion_w"] * (cushion_capped / 3.0)
                + w["liq_w"] * liq_score
                + (w["ownable_bonus"] if ownable else 0.0)
            )

            rows.append(
                {
                    "Ticker": ticker,
                    "Price": round(price, 2),
                    "Strike": float(K),
                    "Exp": exp,
                    "Days": int(days_to_exp),
                    "Premium": round(P, 2),
                    "OTM%": round(otm_pct, 2),
                    "ROI%_ann": round(roi_ann * 100.0, 2),
                    "IV": round(iv * 100.0, 2) if iv == iv else float("nan"),
                    "POEW": round(poew, 3) if poew == poew else float("nan"),
                    "CushionSigma": round(cushion_sigma, 2) if cushion_sigma == cushion_sigma else float("nan"),
                    "Spread%": round(spread_pct, 2) if spread_pct == spread_pct else float("nan"),
                    "OI": int(oi),
                    "CostBasis": round(cost_basis, 2) if cost_basis == cost_basis else float("nan"),
                    "Collateral": int(collateral),
                    "Ownable": ownable,
                    "SMA200": round(sma200, 2) if sma200 == sma200 else float("nan"),
                    "52W_Low": round(yr_low, 2) if yr_low == yr_low else float("nan"),
                    "52W_High": round(yr_high, 2) if yr_high == yr_high else float("nan"),
                    "Score": round(score, 6),
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Sort by score descending, then by ROI
    df = df.sort_values(["Score", "ROI%_ann"], ascending=[
                        False, False]).reset_index(drop=True)
    return df


def parse_args():
    p = argparse.ArgumentParser(
        description="Scan OTM puts for cash-secured short-put strategy.")
    p.add_argument("--tickers", type=str,
                   default="AAPL,MSFT,SPY,TSLA", help="Comma-separated tickers")
    p.add_argument("--days-limit", type=int, default=45,
                   help="Max days to expiration")
    p.add_argument("--min-otm", type=float,
                   default=10.0, help="Min OTM percent")
    p.add_argument("--min-oi", type=int, default=200, help="Min open interest")
    p.add_argument("--max-spread", type=float, default=10.0,
                   help="Max bid-ask spread %% of mid")
    p.add_argument("--min-roi", type=float, default=0.12,
                   help="Min annualized ROI on collateral (e.g., 0.12 = 12%)")
    p.add_argument("--min-cushion", type=float, default=1.0,
                   help="Min sigma cushion to strike")
    p.add_argument("--min-poew", type=float, default=0.65,
                   help="Min probability of expiring worthless")
    p.add_argument("--earn-window", type=int, default=5,
                   help="Skip expiries within +/-N days of earnings")
    p.add_argument("--risk-free", type=float, default=0.00,
                   help="Risk-free rate for BS calc (annualized)")
    p.add_argument("--per-contract-cap", type=float, default=None,
                   help="Skip contracts with collateral > this ($)")
    p.add_argument("--mc", action="store_true",
                   help="Run Monte Carlo on the single top-scoring contract")
    p.add_argument("--paths", type=int, default=20000,
                   help="Monte Carlo paths")
    p.add_argument("--loss-frac", type=float, default=0.10,
                   help="Loss threshold as fraction of collateral (0.10 = 10%)")
    p.add_argument("--mc-drift", type=float, default=0.00,
                   help="Annualized drift for GBM (0.00 is conservative)")
    p.add_argument("--mc-seed", type=int, default=None,
                   help="Random seed for reproducibility")

    p.add_argument("--top", type=int, default=25, help="Show top N per run")
    p.add_argument("--export", type=str, default="",
                   help="CSV filename to export results")
    return p.parse_args()


def main():
    args = parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    all_results = []

    for t in tickers:
        print(f"Scanning {t} ...")
        df = analyze_puts(
            t,
            days_limit=args.days_limit,
            min_otm_pct=args.min_otm,
            min_oi=args.min_oi,
            max_spread_pct=args.max_spread,
            min_roi_ann=args.min_roi,
            min_cushion_sigma=args.min_cushion,
            min_poew=args.min_poew,
            earn_window_days=args.earn_window,
            per_contract_collateral_cap=args.per_contract_cap,
            risk_free_rate=args.risk_free,
        )
        if not df.empty:
            all_results.append(df)

    if not all_results:
        print("No candidates found with current filters.")
        return

    out = pd.concat(all_results, ignore_index=True).sort_values(
        ["Score", "ROI%_ann"], ascending=[False, False])
    # Pretty print top N
    cols = [
        "Ticker", "Price", "Strike", "Exp", "Days", "Premium",
        "OTM%", "ROI%_ann", "IV", "POEW", "CushionSigma",
        "Spread%", "OI", "CostBasis", "Collateral", "Ownable", "Score"
    ]
    show = [c for c in cols if c in out.columns]
    print("\nTop candidates:")
    print(out[show].head(args.top).to_string(index=False))

    if args.export:
        out.to_csv(args.export, index=False)
        print(f"\nSaved CSV: {args.export}")
    if args.mc and not out.empty:
        top_row = out.iloc[0]
        print("\nMonte Carlo on top contract:")
        print(top_row[["Ticker", "Price", "Strike", "Exp",
              "Days", "Premium", "IV", "Score"]].to_string())

        mc = mc_short_put_loss_prob(
            top_row,
            loss_frac=args.loss_frac,
            n_paths=args.paths,
            mu=args.mc_drift,
            seed=args.mc_seed
        )

        print(
            f"\nAssumptions: IV={mc['iv_used']*100:.2f}%  Days={mc['days']}  Drift={args.mc_drift:.2%}  Paths={mc['paths']:,}")
        print(f"Collateral (invested capital): ${mc['collateral']:,.0f}")
        print(
            f"Loss threshold (>{args.loss_frac:.0%} of capital): ${mc['loss_threshold']:,.0f}")

        print("\nMonte Carlo results:")
        print(
            f" • Probability(loss worse than threshold): {mc['prob_loss_over']:.2%}")
        print(f" • Expected P&L: ${mc['expected_pnl']:,.0f} per contract")
        print(
            f" • PNL percentiles: 5%=${mc['pnl_p5']:,.0f}, 50%=${mc['pnl_p50']:,.0f}, 95%=${mc['pnl_p95']:,.0f}")
        print(f" • Worst path: ${mc['pnl_min']:,.0f}")


def gbm_terminal_prices(S0, mu, sigma, T_years, n_paths, rng=None):
    """
    Geometric Brownian Motion terminal prices.
    S_T = S0 * exp( (mu - 0.5*sigma^2)*T + sigma*sqrt(T)*Z )
    """
    rng = rng or np.random.default_rng()
    Z = rng.standard_normal(n_paths)
    drift = (mu - 0.5 * sigma**2) * T_years
    vol_term = sigma * np.sqrt(T_years)
    return S0 * np.exp(drift + vol_term * Z)


def mc_short_put_loss_prob(row, loss_frac=0.10, n_paths=20000, mu=0.0, seed=None):
    """
    Monte Carlo on one short put contract (row from analyzer DataFrame).
    Returns dict of summary stats + entire P&L path array for plotting.
    """
    S0 = float(row["Price"])
    K = float(row["Strike"])
    P = float(row["Premium"])
    days = int(row["Days"])
    iv_pct = float(
        row["IV"]) if "IV" in row and row["IV"] == row["IV"] else np.nan
    iv = 0.20 if (np.isnan(iv_pct) or iv_pct <= 0) else iv_pct / 100.0

    T = days / 365.0
    rng = np.random.default_rng(seed)
    S_T = gbm_terminal_prices(S0, mu, iv, T, n_paths, rng)

    # Short put payoff per share at expiry: +P - max(0, K - S_T)
    pnl_per_share = P - np.maximum(0.0, K - S_T)
    pnl = 100.0 * pnl_per_share

    collateral = 100.0 * K
    loss_threshold = -loss_frac * collateral

    prob_loss_over = float(np.mean(pnl < loss_threshold))
    exp_pnl = float(np.mean(pnl))
    p5, p50, p95 = [float(np.percentile(pnl, q)) for q in (5, 50, 95)]
    worst = float(np.min(pnl))

    return {
        "collateral": collateral,
        "loss_threshold": loss_threshold,
        "prob_loss_over": prob_loss_over,
        "expected_pnl": exp_pnl,
        "pnl_p5": p5,
        "pnl_p50": p50,
        "pnl_p95": p95,
        "pnl_min": worst,
        "iv_used": iv,
        "days": days,
        "strike": K,
        "premium": P,
        "price0": S0,
        "paths": int(n_paths),
        "pnl_paths": pnl,  # array (for plotting in Streamlit)
    }


if __name__ == "__main__":
    main()
