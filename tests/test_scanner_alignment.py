import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import numpy as np
import types

import strategy_analysis as sa
import data_fetching as df
import options_math as om


def _make_exp(days):
    return (datetime.now(timezone.utc).date() + timedelta(days=days)).strftime("%Y-%m-%d")


def test_bull_put_spread_alignment(monkeypatch):
    # Synthetic market
    S = 100.0
    days = 30
    exp = _make_exp(days)
    spread_width = 5.0
    Ks = 90.0  # short put strike (OTM)
    Kl = Ks - spread_width  # long put strike

    # Short leg quotes (wider OI => should improve credit)
    sbid, sask, slast = 1.00, 1.20, 1.10
    sOI, sVol = 5000, 1000
    sIV = 0.30

    # Long leg quotes
    lbid, lask, llast = 0.40, 0.60, 0.50
    lOI, lVol = 5000, 1000
    lIV = 0.32

    chain_rows = [
        {"type": "put", "strike": Ks, "bid": sbid, "ask": sask, "last": slast, "openInterest": sOI, "volume": sVol, "impliedVolatility": sIV},
        {"type": "put", "strike": Kl, "bid": lbid, "ask": lask, "last": llast, "openInterest": lOI, "volume": lVol, "impliedVolatility": lIV},
    ]
    chain_df = pd.DataFrame(chain_rows)

    # Monkeypatch data fetchers
    monkeypatch.setattr(df, "fetch_price", lambda ticker: S)
    monkeypatch.setattr(df, "fetch_expirations", lambda ticker: [exp])
    monkeypatch.setattr(df, "fetch_chain", lambda ticker, e: chain_df)

    # Neutralize earnings/dividends
    monkeypatch.setattr(sa, "get_earnings_date", lambda stock: None)
    monkeypatch.setattr(sa, "trailing_dividend_info", lambda stock, S: (0.0, 0.0))

    # Run analyzer
    res = sa.analyze_bull_put_spread(
        ticker="TEST",
        min_days=1,
        days_limit=60,
        min_oi=10,
        max_spread=100.0,
        min_roi=0.0,
        min_cushion=0.0,
        min_poew=0.0,
        earn_window=0,
        risk_free=0.0,
        spread_width=spread_width,
        target_delta_short=0.20,
        bill_yield=0.0,
    )

    assert not res.empty, "Expected one BPS candidate"
    row = res.iloc[0]

    # Expected net credit using same pricing logic used by analyzer
    short_credit = df.effective_credit(sbid, sask, slast, oi=sOI, volume=sVol, dte=days)
    long_debit = df.effective_debit(lbid, lask, llast, oi=lOI, volume=lVol, dte=days)
    expected_nc = short_credit - long_debit

    assert math.isclose(float(row["NetCredit"]), expected_nc, rel_tol=1e-6, abs_tol=1e-6)

    # ROI alignment
    max_loss = spread_width - expected_nc
    roi_cycle = expected_nc / max_loss
    roi_ann = roi_cycle * (365.0 / days)
    assert math.isclose(float(row["ROI%_ann"]) / 100.0, roi_ann, rel_tol=1e-3)


def test_iron_condor_alignment(monkeypatch):
    # Synthetic market
    S = 100.0
    days = 30
    exp = _make_exp(days)

    # Strikes
    Kps = 90.0
    Kpl = 85.0
    Kcs = 110.0
    Kcl = 115.0

    # Quotes and OI/vol
    ps_bid, ps_ask, ps_last, ps_oi, ps_vol, ps_iv = 1.00, 1.20, 1.10, 5000, 1000, 0.28
    pl_bid, pl_ask, pl_last, pl_oi, pl_vol, pl_iv = 0.40, 0.60, 0.50, 5000, 1000, 0.30
    cs_bid, cs_ask, cs_last, cs_oi, cs_vol, cs_iv = 1.30, 1.50, 1.40, 5000, 1000, 0.27
    cl_bid, cl_ask, cl_last, cl_oi, cl_vol, cl_iv = 0.50, 0.70, 0.60, 5000, 1000, 0.29

    chain_rows = [
        {"type": "put", "strike": Kps, "bid": ps_bid, "ask": ps_ask, "last": ps_last, "openInterest": ps_oi, "volume": ps_vol, "impliedVolatility": ps_iv},
        {"type": "put", "strike": Kpl, "bid": pl_bid, "ask": pl_ask, "last": pl_last, "openInterest": pl_oi, "volume": pl_vol, "impliedVolatility": pl_iv},
        {"type": "call", "strike": Kcs, "bid": cs_bid, "ask": cs_ask, "last": cs_last, "openInterest": cs_oi, "volume": cs_vol, "impliedVolatility": cs_iv},
        {"type": "call", "strike": Kcl, "bid": cl_bid, "ask": cl_ask, "last": cl_last, "openInterest": cl_oi, "volume": cl_vol, "impliedVolatility": cl_iv},
    ]
    chain_df = pd.DataFrame(chain_rows)

    # Monkeypatch data
    monkeypatch.setattr(df, "fetch_price", lambda ticker: S)
    monkeypatch.setattr(df, "fetch_expirations", lambda ticker: [exp])
    monkeypatch.setattr(df, "fetch_chain", lambda ticker, e: chain_df)

    # Neutralize earnings/dividends
    monkeypatch.setattr(sa, "get_earnings_date", lambda stock: None)
    monkeypatch.setattr(sa, "trailing_dividend_info", lambda stock, S: (0.0, 0.0))

    # Fix RNG seed for deterministic MC inside analyzer and in this test
    orig_default_rng = np.random.default_rng
    monkeypatch.setattr(om.np.random, "default_rng", lambda seed=None, _orig=orig_default_rng: _orig(42))

    res = sa.analyze_iron_condor(
        ticker="TEST",
        min_days=1,
        days_limit=60,
        min_oi=10,
        max_spread=100.0,
        min_roi=0.0,
        min_cushion=0.0,
        earn_window=0,
        risk_free=0.0,
        spread_width_put=(Kps - Kpl),
        spread_width_call=(Kcl - Kcs),
        target_delta_short=0.16,
        bill_yield=0.0,
    )

    assert not res.empty, "Expected one IC candidate"
    row = res.iloc[0]

    # Expected net credit
    ps_credit = df.effective_credit(ps_bid, ps_ask, ps_last, oi=ps_oi, volume=ps_vol, dte=days)
    pl_debit = df.effective_debit(pl_bid, pl_ask, pl_last, oi=pl_oi, volume=pl_vol, dte=days)
    cs_credit = df.effective_credit(cs_bid, cs_ask, cs_last, oi=cs_oi, volume=cs_vol, dte=days)
    cl_debit = df.effective_debit(cl_bid, cl_ask, cl_last, oi=cl_oi, volume=cl_vol, dte=days)
    expected_nc = ps_credit - pl_debit + cs_credit - cl_debit

    assert math.isclose(float(row["NetCredit"]), expected_nc, rel_tol=1e-6, abs_tol=1e-6)

    # ROI alignment (max spread width between wings)
    max_spread = max(Kps - Kpl, Kcl - Kcs)
    max_loss = max_spread - expected_nc
    roi_cycle = expected_nc / max_loss
    roi_ann = roi_cycle * (365.0 / days)
    assert math.isclose(float(row["ROI%_ann"]) / 100.0, roi_ann, rel_tol=1e-3)

    # MC alignment: recompute with same parameters as analyzer
    iv_avg = (ps_iv + cs_iv) / 2.0
    mc_res = om.mc_pnl(
        "IRON_CONDOR",
        {
            "S0": S,
            "days": days,
            "iv": iv_avg,
            "put_short_strike": Kps,
            "put_long_strike": Kpl,
            "call_short_strike": Kcs,
            "call_long_strike": Kcl,
            "net_credit": expected_nc,
        },
        n_paths=1000,
        mu=0.0,
        seed=None,
        rf=0.0,
    )
    assert math.isclose(float(row.get("MC_ExpectedPnL", np.nan)), float(mc_res.get("pnl_expected", np.nan)), rel_tol=0.2)  # stochastic tolerance


def test_bps_long_put_liquidity_impacts_netcredit(monkeypatch):
    # Synthetic market with two scenarios differing only in long-leg liquidity
    S = 100.0
    days = 30
    exp = _make_exp(days)
    spread_width = 5.0
    Ks = 90.0
    Kl = Ks - spread_width

    # Short leg fixed
    sbid, sask, slast = 1.00, 1.20, 1.10
    sOI, sVol = 5000, 1000

    # Long leg, scenario A (good liquidity)
    A_lbid, A_lask, A_llast = 0.40, 0.60, 0.50
    A_oi, A_vol = 5000, 1000
    # Long leg, scenario B (poor liquidity)
    B_lbid, B_lask, B_llast = 0.40, 0.60, 0.50
    B_oi, B_vol = 5, 1

    def run_chain(l_oi, l_vol):
        chain_rows = [
            {"type": "put", "strike": Ks, "bid": sbid, "ask": sask, "last": slast, "openInterest": sOI, "volume": sVol, "impliedVolatility": 0.30},
            {"type": "put", "strike": Kl, "bid": A_lbid, "ask": A_lask, "last": A_llast, "openInterest": l_oi, "volume": l_vol, "impliedVolatility": 0.32},
        ]
        chain_df = pd.DataFrame(chain_rows)
        monkeypatch.setattr(df, "fetch_price", lambda ticker: S)
        monkeypatch.setattr(df, "fetch_expirations", lambda ticker: [exp])
        monkeypatch.setattr(df, "fetch_chain", lambda ticker, e: chain_df)
        monkeypatch.setattr(sa, "get_earnings_date", lambda stock: None)
        monkeypatch.setattr(sa, "trailing_dividend_info", lambda stock, S: (0.0, 0.0))
        res = sa.analyze_bull_put_spread(
            ticker="TEST", min_days=1, days_limit=60, min_oi=1, max_spread=100.0,
            min_roi=0.0, min_cushion=0.0, min_poew=0.0, earn_window=0, risk_free=0.0,
            spread_width=spread_width, target_delta_short=0.20, bill_yield=0.0
        )
        assert not res.empty
        return float(res.iloc[0]["NetCredit"])

    nc_good = run_chain(A_oi, A_vol)
    nc_poor = run_chain(B_oi, B_vol)
    # Poor long-leg liquidity should worsen debit (closer to ask), thus reduce NetCredit
    assert nc_poor < nc_good


def test_bcs_long_call_liquidity_impacts_netcredit(monkeypatch):
    # Synthetic market with two scenarios differing in long call liquidity
    S = 100.0
    days = 30
    exp = _make_exp(days)
    spread_width = 5.0
    Ks = 110.0
    Kl = Ks + spread_width
    # Short leg fixed
    sbid, sask, slast = 1.30, 1.50, 1.40
    sOI, sVol = 5000, 1000
    # Long leg scenarios (same quotes, different OI/vol)
    lbid, lask, llast = 0.50, 0.70, 0.60
    good_oi, good_vol = 5000, 1000
    poor_oi, poor_vol = 5, 1

    def run_chain(l_oi, l_vol):
        chain_rows = [
            {"type": "call", "strike": Ks, "bid": sbid, "ask": sask, "last": slast, "openInterest": sOI, "volume": sVol, "impliedVolatility": 0.27},
            {"type": "call", "strike": Kl, "bid": lbid, "ask": lask, "last": llast, "openInterest": l_oi, "volume": l_vol, "impliedVolatility": 0.29},
        ]
        chain_df = pd.DataFrame(chain_rows)
        monkeypatch.setattr(df, "fetch_price", lambda ticker: S)
        monkeypatch.setattr(df, "fetch_expirations", lambda ticker: [exp])
        monkeypatch.setattr(df, "fetch_chain", lambda ticker, e: chain_df)
        monkeypatch.setattr(sa, "get_earnings_date", lambda stock: None)
        monkeypatch.setattr(sa, "trailing_dividend_info", lambda stock, S: (0.0, 0.0))
        res = sa.analyze_bear_call_spread(
            ticker="TEST", min_days=1, days_limit=60, min_oi=1, max_spread=100.0,
            min_roi=0.0, min_cushion=0.0, min_poew=0.0, earn_window=0, risk_free=0.0,
            spread_width=spread_width, target_delta_short=0.20, bill_yield=0.0
        )
        assert not res.empty
        return float(res.iloc[0]["NetCredit"])

    nc_good = run_chain(good_oi, good_vol)
    nc_poor = run_chain(poor_oi, poor_vol)
    assert nc_poor < nc_good


def test_collar_long_put_liquidity_impacts_netcredit(monkeypatch):
    # Synthetic market where long put liquidity varies
    S = 100.0
    days = 30
    exp = _make_exp(days)
    Kc = 110.0
    Kp = 95.0
    # Short call fixed
    cbid, cask, clast = 1.30, 1.50, 1.40
    coi, cvol = 5000, 1000
    # Long put quotes constant; vary liquidity
    pbid, pask, plast = 0.60, 0.80, 0.70
    good_oi, good_vol = 5000, 1000
    poor_oi, poor_vol = 5, 1

    def run_chain(p_oi, p_vol):
        chain_rows = [
            {"type": "call", "strike": Kc, "bid": cbid, "ask": cask, "last": clast, "openInterest": coi, "volume": cvol, "impliedVolatility": 0.27},
            {"type": "put", "strike": Kp, "bid": pbid, "ask": pask, "last": plast, "openInterest": p_oi, "volume": p_vol, "impliedVolatility": 0.32},
        ]
        chain_df = pd.DataFrame(chain_rows)
        monkeypatch.setattr(df, "fetch_price", lambda ticker: S)
        monkeypatch.setattr(df, "fetch_expirations", lambda ticker: [exp])
        monkeypatch.setattr(df, "fetch_chain", lambda ticker, e: chain_df)
        monkeypatch.setattr(sa, "get_earnings_date", lambda stock: None)
        monkeypatch.setattr(sa, "trailing_dividend_info", lambda stock, S: (0.0, 0.0))
        monkeypatch.setattr(df, "estimate_next_ex_div", lambda stock: (None, 0.0))
        res = sa.analyze_collar(
            ticker="TEST", min_days=1, days_limit=60, min_oi=1, max_spread=100.0,
            call_delta_target=0.16, put_delta_target=0.20, earn_window=0, risk_free=0.0,
            include_dividends=False, min_net_credit=None, bill_yield=0.0
        )
        assert not res.empty
        return float(res.iloc[0]["NetCredit"])

    nc_good = run_chain(good_oi, good_vol)
    nc_poor = run_chain(poor_oi, poor_vol)
    assert nc_poor < nc_good


def test_csp_cc_alignment_various_dte(monkeypatch):
    # Validate alignment holds across different DTE values
    S = 100.0
    Kp = 90.0
    Kc = 110.0
    bid_put, ask_put, last_put = 1.00, 1.20, 1.10
    bid_call, ask_call, last_call = 1.30, 1.50, 1.40
    oi, vol, ivp, ivc = 5000, 1000, 0.30, 0.27

    def run_once(days):
        exp = _make_exp(days)
        chain_rows = [
            {"type": "put", "strike": Kp, "bid": bid_put, "ask": ask_put, "last": last_put, "openInterest": oi, "volume": vol, "impliedVolatility": ivp},
            {"type": "call", "strike": Kc, "bid": bid_call, "ask": ask_call, "last": last_call, "openInterest": oi, "volume": vol, "impliedVolatility": ivc},
        ]
        chain_df = pd.DataFrame(chain_rows)
        monkeypatch.setattr(df, "fetch_price", lambda ticker: S)
        monkeypatch.setattr(df, "fetch_expirations", lambda ticker: [exp])
        monkeypatch.setattr(df, "fetch_chain", lambda ticker, e: chain_df)
        monkeypatch.setattr(sa, "get_earnings_date", lambda stock: None)
        monkeypatch.setattr(sa, "trailing_dividend_info", lambda stock, S: (0.0, 0.0))

        # CSP
        res_csp, _ = sa.analyze_csp(
            ticker="TEST", min_days=1, days_limit=60, min_otm=0.0, min_oi=1, max_spread=100.0,
            min_roi=0.0, min_cushion=0.0, min_poew=0.0, earn_window=0, risk_free=0.0,
            per_contract_cap=None, bill_yield=0.0
        )
        assert not res_csp.empty
        row_csp = res_csp.iloc[0]
        prem_csp = df.effective_credit(bid_put, ask_put, last_put, oi=oi, volume=vol, dte=days)
        roi_csp = (prem_csp / Kp) * (365.0 / days)
        assert math.isclose(float(row_csp["Premium"]), prem_csp, rel_tol=1e-6)
        assert math.isclose(float(row_csp["ROI%_ann"]) / 100.0, roi_csp, rel_tol=1e-4, abs_tol=5e-4)

        # CC
        res_cc = sa.analyze_cc(
            ticker="TEST", min_days=1, days_limit=60, min_otm=0.0, min_oi=1, max_spread=100.0,
            min_roi=0.0, earn_window=0, risk_free=0.0, include_dividends=False, bill_yield=0.0
        )
        assert not res_cc.empty
        row_cc = res_cc.iloc[0]
        prem_cc = df.effective_credit(bid_call, ask_call, last_call, oi=oi, volume=vol, dte=days)
        roi_cc = (prem_cc / S) * (365.0 / days)
        assert math.isclose(float(row_cc["Premium"]), prem_cc, rel_tol=1e-6)
        assert math.isclose(float(row_cc["ROI%_ann"]) / 100.0, roi_cc, rel_tol=1e-4, abs_tol=5e-4)

    for d in (15, 30, 45):
        run_once(d)


def test_bear_call_spread_alignment(monkeypatch):
    # Synthetic market
    S = 100.0
    days = 30
    exp = _make_exp(days)
    spread_width = 5.0
    Ks = 110.0  # short call strike (OTM)
    Kl = Ks + spread_width  # long call strike

    # Short leg quotes
    sbid, sask, slast = 1.30, 1.50, 1.40
    sOI, sVol = 5000, 1000
    sIV = 0.27

    # Long leg quotes
    lbid, lask, llast = 0.50, 0.70, 0.60
    lOI, lVol = 5000, 1000
    lIV = 0.29

    chain_rows = [
        {"type": "call", "strike": Ks, "bid": sbid, "ask": sask, "last": slast, "openInterest": sOI, "volume": sVol, "impliedVolatility": sIV},
        {"type": "call", "strike": Kl, "bid": lbid, "ask": lask, "last": llast, "openInterest": lOI, "volume": lVol, "impliedVolatility": lIV},
    ]
    chain_df = pd.DataFrame(chain_rows)

    # Monkeypatch data fetchers
    monkeypatch.setattr(df, "fetch_price", lambda ticker: S)
    monkeypatch.setattr(df, "fetch_expirations", lambda ticker: [exp])
    monkeypatch.setattr(df, "fetch_chain", lambda ticker, e: chain_df)

    # Neutralize earnings/dividends
    monkeypatch.setattr(sa, "get_earnings_date", lambda stock: None)
    monkeypatch.setattr(sa, "trailing_dividend_info", lambda stock, S: (0.0, 0.0))

    # Deterministic MC RNG
    orig_default_rng = np.random.default_rng
    monkeypatch.setattr(om.np.random, "default_rng", lambda seed=None, _orig=orig_default_rng: _orig(42))

    res = sa.analyze_bear_call_spread(
        ticker="TEST",
        min_days=1,
        days_limit=60,
        min_oi=10,
        max_spread=100.0,
        min_roi=0.0,
        min_cushion=0.0,
        min_poew=0.0,
        earn_window=0,
        risk_free=0.0,
        spread_width=spread_width,
        target_delta_short=0.20,
        bill_yield=0.0,
    )

    assert not res.empty, "Expected one BCS candidate"
    row = res.iloc[0]

    # Expected net credit using same pricing logic used by analyzer
    short_credit = df.effective_credit(sbid, sask, slast, oi=sOI, volume=sVol, dte=days)
    long_debit = df.effective_debit(lbid, lask, llast, oi=lOI, volume=lVol, dte=days)
    expected_nc = short_credit - long_debit

    assert math.isclose(float(row["NetCredit"]), expected_nc, rel_tol=1e-6, abs_tol=1e-6)

    # ROI alignment
    max_loss = spread_width - expected_nc
    roi_cycle = expected_nc / max_loss
    roi_ann = roi_cycle * (365.0 / days)
    assert math.isclose(float(row["ROI%_ann"]) / 100.0, roi_ann, rel_tol=1e-4)

    # MC alignment
    mc_res = om.mc_pnl(
        "BEAR_CALL_SPREAD",
        {
            "S0": S,
            "days": days,
            "iv": sIV,
            "sell_strike": Ks,
            "buy_strike": Kl,
            "net_credit": expected_nc,
        },
        n_paths=1000,
        mu=0.0,
        seed=None,
        rf=0.0,
    )
    assert math.isclose(float(row.get("MC_ExpectedPnL", np.nan)), float(mc_res.get("pnl_expected", np.nan)), rel_tol=0.2)


def test_csp_alignment(monkeypatch):
    # Synthetic market
    S = 100.0
    days = 30
    exp = _make_exp(days)
    K = 90.0
    bid, ask, last = 1.00, 1.20, 1.10
    oi, vol, iv = 5000, 1000, 0.30

    chain_rows = [
        {"type": "put", "strike": K, "bid": bid, "ask": ask, "last": last, "openInterest": oi, "volume": vol, "impliedVolatility": iv}
    ]
    chain_df = pd.DataFrame(chain_rows)

    # Monkeypatch data
    monkeypatch.setattr(df, "fetch_price", lambda ticker: S)
    monkeypatch.setattr(df, "fetch_expirations", lambda ticker: [exp])
    monkeypatch.setattr(df, "fetch_chain", lambda ticker, e: chain_df)

    # Neutralize earnings/dividends
    monkeypatch.setattr(sa, "get_earnings_date", lambda stock: None)
    monkeypatch.setattr(sa, "trailing_dividend_info", lambda stock, S: (0.0, 0.0))

    # Deterministic MC RNG
    orig_default_rng = np.random.default_rng
    monkeypatch.setattr(om.np.random, "default_rng", lambda seed=None, _orig=orig_default_rng: _orig(42))

    res_df, _ = sa.analyze_csp(
        ticker="TEST",
        min_days=1,
        days_limit=60,
        min_otm=0.0,
        min_oi=10,
        max_spread=100.0,
        min_roi=0.0,
        min_cushion=0.0,
        min_poew=0.0,
        earn_window=0,
        risk_free=0.0,
        per_contract_cap=None,
        bill_yield=0.0,
    )

    assert not res_df.empty, "Expected one CSP candidate"
    row = res_df.iloc[0]

    expected_prem = df.effective_credit(bid, ask, last, oi=oi, volume=vol, dte=days)
    assert math.isclose(float(row["Premium"]), expected_prem, rel_tol=1e-6)

    roi_ann = (expected_prem / K) * (365.0 / days)
    assert math.isclose(float(row["ROI%_ann"]) / 100.0, roi_ann, rel_tol=1e-4)

    mc_res = om.mc_pnl(
        "CSP",
        {"S0": S, "days": days, "iv": iv, "Kp": K, "put_premium": expected_prem, "div_ps_annual": 0.0, "use_net_collateral": False},
        n_paths=1000,
        mu=0.0,
        seed=None,
        rf=0.0,
    )
    assert math.isclose(float(row.get("MC_ExpectedPnL", np.nan)), float(mc_res.get("pnl_expected", np.nan)), rel_tol=0.2)


def test_cc_alignment(monkeypatch):
    # Synthetic market
    S = 100.0
    days = 30
    exp = _make_exp(days)
    K = 110.0
    bid, ask, last = 1.30, 1.50, 1.40
    oi, vol, iv = 5000, 1000, 0.27

    chain_rows = [
        {"type": "call", "strike": K, "bid": bid, "ask": ask, "last": last, "openInterest": oi, "volume": vol, "impliedVolatility": iv}
    ]
    chain_df = pd.DataFrame(chain_rows)

    # Monkeypatch data
    monkeypatch.setattr(df, "fetch_price", lambda ticker: S)
    monkeypatch.setattr(df, "fetch_expirations", lambda ticker: [exp])
    monkeypatch.setattr(df, "fetch_chain", lambda ticker, e: chain_df)

    # Neutralize earnings/dividends
    monkeypatch.setattr(sa, "get_earnings_date", lambda stock: None)
    monkeypatch.setattr(sa, "trailing_dividend_info", lambda stock, S: (0.0, 0.0))

    # Deterministic MC RNG
    orig_default_rng = np.random.default_rng
    monkeypatch.setattr(om.np.random, "default_rng", lambda seed=None, _orig=orig_default_rng: _orig(42))

    res = sa.analyze_cc(
        ticker="TEST",
        min_days=1,
        days_limit=60,
        min_otm=0.0,
        min_oi=10,
        max_spread=100.0,
        min_roi=0.0,
        earn_window=0,
        risk_free=0.0,
        include_dividends=False,  # simplify alignment
        bill_yield=0.0,
    )

    assert not res.empty, "Expected one CC candidate"
    row = res.iloc[0]

    expected_prem = df.effective_credit(bid, ask, last, oi=oi, volume=vol, dte=days)
    assert math.isclose(float(row["Premium"]), expected_prem, rel_tol=1e-6)

    roi_ann = (expected_prem / S) * (365.0 / days)
    assert math.isclose(float(row["ROI%_ann"]) / 100.0, roi_ann, rel_tol=1e-4)

    mc_res = om.mc_pnl(
        "CC",
        {"S0": S, "days": days, "iv": iv, "Kc": K, "call_premium": expected_prem, "div_ps_annual": 0.0},
        n_paths=1000,
        mu=0.07,
        seed=None,
        rf=0.0,
    )
    assert math.isclose(float(row.get("MC_ExpectedPnL", np.nan)), float(mc_res.get("pnl_expected", np.nan)), rel_tol=0.2)


def test_collar_alignment(monkeypatch):
    # Synthetic market
    S = 100.0
    days = 30
    exp = _make_exp(days)
    Kc = 110.0
    Kp = 95.0

    # Quotes
    cbid, cask, clast = 1.30, 1.50, 1.40
    coi, cvol, civ = 5000, 1000, 0.27
    pbid, pask, plast = 0.60, 0.80, 0.70
    poi, pvol, piv = 5000, 1000, 0.32

    chain_rows = [
        {"type": "call", "strike": Kc, "bid": cbid, "ask": cask, "last": clast, "openInterest": coi, "volume": cvol, "impliedVolatility": civ},
        {"type": "put", "strike": Kp, "bid": pbid, "ask": pask, "last": plast, "openInterest": poi, "volume": pvol, "impliedVolatility": piv},
    ]
    chain_df = pd.DataFrame(chain_rows)

    # Monkeypatch data
    monkeypatch.setattr(df, "fetch_price", lambda ticker: S)
    monkeypatch.setattr(df, "fetch_expirations", lambda ticker: [exp])
    monkeypatch.setattr(df, "fetch_chain", lambda ticker, e: chain_df)

    # Neutralize earnings/dividends and ex-div window
    monkeypatch.setattr(sa, "get_earnings_date", lambda stock: None)
    monkeypatch.setattr(sa, "trailing_dividend_info", lambda stock, S: (0.0, 0.0))
    monkeypatch.setattr(df, "estimate_next_ex_div", lambda stock: (None, 0.0))

    # Deterministic MC RNG
    orig_default_rng = np.random.default_rng
    monkeypatch.setattr(om.np.random, "default_rng", lambda seed=None, _orig=orig_default_rng: _orig(42))

    res = sa.analyze_collar(
        ticker="TEST",
        min_days=1,
        days_limit=60,
        min_oi=10,
        max_spread=100.0,
        call_delta_target=0.16,
        put_delta_target=0.20,
        earn_window=0,
        risk_free=0.0,
        include_dividends=False,
        min_net_credit=None,
        bill_yield=0.0,
    )

    assert not res.empty, "Expected one Collar candidate"
    row = res.iloc[0]

    call_credit = df.effective_credit(cbid, cask, clast, oi=coi, volume=cvol, dte=days)
    put_debit = df.effective_debit(pbid, pask, plast, oi=poi, volume=pvol, dte=days)
    expected_nc = call_credit - put_debit
    assert math.isclose(float(row["NetCredit"]), expected_nc, rel_tol=1e-6)

    roi_ann = (expected_nc / S) * (365.0 / days)
    assert math.isclose(float(row["ROI%_ann"]) / 100.0, roi_ann, rel_tol=1e-3)

    iv_mc = (civ + piv) / 2.0
    mc_res = om.mc_pnl(
        "COLLAR",
        {
            "S0": S,
            "days": days,
            "iv": iv_mc,
            "Kc": Kc,
            "call_premium": call_credit,
            "Kp": Kp,
            "put_premium": put_debit,
            "div_ps_annual": 0.0,
        },
        n_paths=1000,
        mu=0.0,
        seed=None,
        rf=0.0,
    )
    assert math.isclose(float(row.get("MC_ExpectedPnL", np.nan)), float(mc_res.get("pnl_expected", np.nan)), rel_tol=0.2)
