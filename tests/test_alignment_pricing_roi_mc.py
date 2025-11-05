"""
Alignment tests to validate that screens (pricing), ROI calculations, and Monte Carlo
share the same, more-realistic limit prices so results don't diverge.

We use deterministic cases (days=0) where MC outcomes collapse to a single value
and can be compared exactly to modeled net credits/debits.
"""

import math

from data_fetching import effective_credit, effective_debit
from options_math import mc_pnl


def test_bull_put_spread_alignment_days0():
    # Construct short/long leg quotes
    # Short leg: modest spread, decent OI => price leans toward mid
    sb, sa = 1.00, 1.12
    # Long leg: moderate spread
    lb, la = 0.38, 0.46

    # Modeled prices (includes liquidity-aware alpha)
    short_price = effective_credit(sb, sa, oi=2000, dte=10)
    long_price = effective_debit(lb, la, oi=1500, dte=10)
    net_credit = short_price - long_price

    # Deterministic MC: T=0 so S_T = S0 exactly, choose S well above strikes
    S0 = 100.0
    sell_strike = 90.0
    buy_strike = 85.0
    days = 0
    iv = 0.20

    params = dict(
        S0=S0,
        days=days,
        iv=iv,
        sell_strike=sell_strike,
        buy_strike=buy_strike,
        net_credit=net_credit,
    )
    mc = mc_pnl("BULL_PUT_SPREAD", params, n_paths=2000, mu=0.0, seed=42)

    # With S0 >> sell_strike and T=0, no loss; P&L = net_credit per share
    assert math.isfinite(net_credit) and net_credit > 0
    assert abs(mc["pnl_expected"] - net_credit * 100.0) < 1e-6

    # Capital per share equals spread width - net credit
    spread_width = sell_strike - buy_strike
    assert abs(mc["capital_per_share"] - (spread_width - net_credit)) < 1e-9


def test_iron_condor_alignment_days0():
    # Put side quotes
    pb, pa = 1.00, 1.10
    plb, pla = 0.45, 0.55
    # Call side quotes
    cb, ca = 1.05, 1.15
    clb, cla = 0.40, 0.50

    # Modeled credits/debits
    ps = effective_credit(pb, pa, oi=3000, dte=15)   # short put
    pl = effective_debit(plb, pla, oi=2000, dte=15)  # long put
    cs = effective_credit(cb, ca, oi=3000, dte=15)   # short call
    cl = effective_debit(clb, cla, oi=2000, dte=15)  # long call

    net_credit = (ps - pl) + (cs - cl)

    # Deterministic MC: pick S0 between short strikes
    put_short, put_long = 95.0, 90.0
    call_short, call_long = 105.0, 110.0
    S0 = 100.0

    params = dict(
        S0=S0,
        days=0,
        iv=0.20,
        put_short_strike=put_short,
        put_long_strike=put_long,
        call_short_strike=call_short,
        call_long_strike=call_long,
        net_credit=net_credit,
    )
    mc = mc_pnl("IRON_CONDOR", params, n_paths=2000, mu=0.0, seed=7)

    # No loss at S0 in the middle, so P&L = net_credit
    assert abs(mc["pnl_expected"] - net_credit * 100.0) < 1e-6

    # Capital per share is wider spread minus net_credit
    put_width = put_short - put_long
    call_width = call_long - call_short
    wider = max(put_width, call_width)
    assert abs(mc["capital_per_share"] - (wider - net_credit)) < 1e-9


def test_csp_alignment_days0():
    # Simple CSP: S0 above strike; T=0 so pnl equals premium; no rf carry
    b, a = 1.00, 1.06
    Pp = effective_credit(b, a, oi=1500, dte=7)

    S0 = 100.0
    K = 90.0
    params = dict(
        S0=S0,
        days=0,
        iv=0.20,
        Kp=K,
        put_premium=Pp,
        use_net_collateral=False,
        div_ps_annual=0.0,
    )
    mc = mc_pnl("CSP", params, n_paths=1000, mu=0.0, seed=1, rf=0.0)

    assert abs(mc["pnl_expected"] - Pp * 100.0) < 1e-6
    # Collateral default = strike
    assert abs(mc["capital_per_share"] - K) < 1e-9
