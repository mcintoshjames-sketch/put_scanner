import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from strategy_analysis import unified_risk_reward_score


def main():
    ok = True
    # Baseline
    base = unified_risk_reward_score(expected_roi_ann_dec=0.2, p5_pnl=-50.0, capital=500.0,
                                     spread_pct=5.0, oi=1000, volume=500, cushion_sigma=1.5)
    print('base', base)

    # ROI monotonicity
    roi_better = unified_risk_reward_score(expected_roi_ann_dec=0.5, p5_pnl=-50.0, capital=500.0,
                                           spread_pct=5.0, oi=1000, volume=500, cushion_sigma=1.5)
    print('roi_better', roi_better)
    ok &= roi_better > base

    # p5 downside monotonicity
    p5_worse = unified_risk_reward_score(expected_roi_ann_dec=0.2, p5_pnl=-400.0, capital=500.0,
                                         spread_pct=5.0, oi=1000, volume=500, cushion_sigma=1.5)
    print('p5_worse', p5_worse)
    ok &= p5_worse < base

    # Liquidity: spread effect
    liq_worse = unified_risk_reward_score(expected_roi_ann_dec=0.2, p5_pnl=-50.0, capital=500.0,
                                          spread_pct=18.0, oi=1000, volume=500, cushion_sigma=1.5)
    print('liq_worse', liq_worse)
    ok &= liq_worse < base

    # Vol/OI effect
    voloi_worse = unified_risk_reward_score(expected_roi_ann_dec=0.2, p5_pnl=-50.0, capital=500.0,
                                            spread_pct=5.0, oi=2000, volume=100, cushion_sigma=1.5)
    print('voloi_worse', voloi_worse)
    ok &= voloi_worse < base

    # Cushion effect
    cush_better = unified_risk_reward_score(expected_roi_ann_dec=0.2, p5_pnl=-50.0, capital=500.0,
                                            spread_pct=5.0, oi=1000, volume=500, cushion_sigma=2.5)
    print('cush_better', cush_better)
    ok &= cush_better > base

    # Boundaries best
    best = unified_risk_reward_score(expected_roi_ann_dec=1.0, p5_pnl=50.0, capital=500.0,
                                     spread_pct=0.0, oi=5000, volume=4000, cushion_sigma=3.0)
    print('best', best)
    ok &= (0.95 <= best <= 1.0)

    # Boundaries worst
    worst = unified_risk_reward_score(expected_roi_ann_dec=0.0, p5_pnl=-500.0, capital=500.0,
                                      spread_pct=25.0, oi=0, volume=0, cushion_sigma=0.0)
    print('worst', worst)
    ok &= (0.0 <= worst <= 0.2)

    # NaN handling
    nan_case = unified_risk_reward_score(expected_roi_ann_dec=float('nan'), p5_pnl=float('nan'), capital=float('nan'),
                                         spread_pct=float('nan'), oi=float('nan'), volume=float('nan'), cushion_sigma=float('nan'))
    print('nan_case', nan_case)
    ok &= (0.0 <= nan_case <= 1.0)

    if not ok:
        raise SystemExit('Checks FAILED')
    print('Checks PASSED')


if __name__ == '__main__':
    main()
