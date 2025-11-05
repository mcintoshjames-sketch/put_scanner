import numpy as np
from options_math import mc_pnl, safe_annualize_roi


def test_bull_put_spread_deep_otm_deterministic():
    # Deep OTM spread -> near-certain max profit; deterministic ROI
    params = {
        "S0": 390.0,
        "sell_strike": 240.0,
        "buy_strike": 235.0,
        "net_credit": 0.50,
        "days": 45,
        "iv": 0.25,
    }
    out = mc_pnl("BULL_PUT_SPREAD", params, n_paths=10000, mu=0.0, seed=42, rf=0.0)
    # Capital = (spread - credit) * 100 = (5 - 0.5) * 100 = 450
    assert abs(out["collateral"] - 450.0) < 1e-6
    # P&L should be ~50 across paths
    for k in ("pnl_expected", "pnl_p5", "pnl_p50", "pnl_p95", "pnl_min"):
        assert abs(out[k] - 50.0) < 1e-3
    # Annualized ROI should match helper computation closely
    roi_cycle = 50.0 / 450.0
    roi_ann_expected = float(safe_annualize_roi(roi_cycle, 45))
    assert abs(out["roi_ann_expected"] - roi_ann_expected) < 1e-9
