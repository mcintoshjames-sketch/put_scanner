"""
Unit tests for liquidity-aware pricing helpers to increase fill likelihood.
Validates dynamic behavior of effective_credit/effective_debit via data_fetching
(which now delegates to utils for centralized logic).
"""

import math

from data_fetching import effective_credit, effective_debit


def test_effective_credit_dynamic_tight_vs_wide():
    # Tight spread (near-mid fills more feasible)
    b1, a1 = 1.00, 1.02  # ~2% of mid
    tight = effective_credit(b1, a1)

    # Wide spread (quote quality poor -> price closer to bid to fill)
    b2, a2 = 1.00, 1.30  # very wide
    wide = effective_credit(b2, a2)

    assert math.isfinite(tight) and math.isfinite(wide)
    # Both should be within [bid, ask]
    assert b1 <= tight <= a1
    assert b2 <= wide <= a2
    # Compare relative position within each spread
    tight_pos = (tight - b1) / (a1 - b1)
    wide_pos = (wide - b2) / (a2 - b2)
    # Tight should be relatively closer to ask than wide
    assert tight_pos > wide_pos


def test_effective_debit_dynamic_tight_vs_wide():
    # Tight spread (BUY debit closer to mid)
    b1, a1 = 2.00, 2.02
    tight = effective_debit(b1, a1)

    # Wide spread (BUY debit should lean closer to ask but still benefit from dynamic alpha)
    b2, a2 = 2.00, 2.30
    wide = effective_debit(b2, a2)

    assert math.isfinite(tight) and math.isfinite(wide)
    # For debits, result should be within [bid, ask]
    assert b1 <= tight <= a1
    assert b2 <= wide <= a2
    # Tight should be lower than wide (easier to improve price when spread is tight)
    assert tight < wide


def test_credit_increases_with_higher_oi_same_spread():
    b, a = 1.00, 1.10  # 10c spread
    low_oi = effective_credit(b, a, oi=50)
    high_oi = effective_credit(b, a, oi=5000)

    # Both within [bid, ask]
    assert b <= low_oi <= a
    assert b <= high_oi <= a
    # Higher OI should allow slightly more aggressive pricing
    assert high_oi > low_oi


def test_debit_decreases_with_higher_oi_same_spread():
    b, a = 2.00, 2.30
    low_oi = effective_debit(b, a, oi=50)
    high_oi = effective_debit(b, a, oi=5000)

    assert b <= low_oi <= a
    assert b <= high_oi <= a
    # For debits, higher OI should get slightly closer to mid/ask improvement
    assert high_oi < low_oi


def test_bps_net_credit_increases_with_short_leg_oi():
    # Short leg quotes
    sb, sa = 1.00, 1.20
    # Long leg quotes
    lb, la = 0.40, 0.60

    net_low_oi = effective_credit(sb, sa, oi=50) - effective_debit(lb, la)
    net_high_oi = effective_credit(sb, sa, oi=5000) - effective_debit(lb, la)

    assert net_high_oi > net_low_oi


def test_bps_net_credit_lower_when_short_leg_spread_wider():
    # Same mid ≈ 1.10 for short, but different spreads
    sb_tight, sa_tight = 1.05, 1.15
    sb_wide, sa_wide = 1.00, 1.20

    # Long leg fixed
    lb, la = 0.40, 0.60

    net_tight = effective_credit(sb_tight, sa_tight) - effective_debit(lb, la)
    net_wide = effective_credit(sb_wide, sa_wide) - effective_debit(lb, la)

    assert net_tight > net_wide
