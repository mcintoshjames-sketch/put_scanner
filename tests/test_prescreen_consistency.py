import os
import math
import pandas as pd

# Ensure provider-independent path during tests
os.environ['OPTIONS_PROVIDER'] = 'unknown'

from strategy_analysis import prescreen_tickers


def _almost_equal(a, b, tol=1e-6):
    if (a is None) or (b is None):
        return False
    if isinstance(a, float) and math.isnan(a):
        return isinstance(b, float) and math.isnan(b)
    if isinstance(b, float) and math.isnan(b):
        return isinstance(a, float) and math.isnan(a)
    return abs(float(a) - float(b)) <= tol


def test_quality_score_matches_components():
    # Use a small stable basket; disable strict filters to ensure rows
    syms = ["AAPL", "GOOG", "META"]
    df = prescreen_tickers(
        syms,
        min_price=1,
        max_price=10000,
        min_avg_volume=1,
        min_hv=1,
        max_hv=500,
        min_option_volume=0,
        check_liquidity=False,
    )

    assert isinstance(df, pd.DataFrame)
    assert not df.empty, "prescreen_tickers returned empty DataFrame in test"

    # Required columns used in scoring
    required = [
        'ROI_Score', 'TG_Score', 'Liq_Score', 'Safe_Score',
        'Earnings_Penalty', 'Quality_Score'
    ]
    for c in required:
        assert c in df.columns, f"Missing column in output: {c}"

    # Recompute raw score from components and compare
    for _, r in df.iterrows():
        roi = float(r['ROI_Score'])
        tg = float(r['TG_Score'])
        liq = float(r['Liq_Score'])
        safe = float(r['Safe_Score'])
        earn_pen = float(r['Earnings_Penalty'])

        recomputed = (0.35 * roi + 0.30 * tg + 0.20 * liq + 0.15 * safe) * earn_pen
        assert _almost_equal(
            float(r['Quality_Score']), round(recomputed, 3), tol=2e-3
        ), (
            f"Quality_Score mismatch for {r.get('Ticker')}: "
            f"expected ~{round(recomputed,3)}, got {r['Quality_Score']}"
        )


def test_adjusted_quality_score_matches_data_quality():
    syms = ["AAPL", "GOOG", "META"]
    df = prescreen_tickers(
        syms,
        min_price=1,
        max_price=10000,
        min_avg_volume=1,
        min_hv=1,
        max_hv=500,
        min_option_volume=0,
        check_liquidity=False,
    )

    assert 'Data_Quality_Score' in df.columns
    assert 'Quality_Score_DataAdj' in df.columns

    for _, r in df.iterrows():
        q = float(r['Quality_Score'])
        dq = float(r['Data_Quality_Score'])
        expected = round(q * dq, 3)
        assert _almost_equal(
            float(r['Quality_Score_DataAdj']), expected, tol=2e-3
        ), (
            f"Adjusted quality mismatch for {r.get('Ticker')}: "
            f"expected ~{expected}, got {r['Quality_Score_DataAdj']}"
        )


def test_iv_hv_consistency_and_ratios():
    syms = ["AAPL", "GOOG", "META"]
    df = prescreen_tickers(
        syms,
        min_price=1,
        max_price=10000,
        min_avg_volume=1,
        min_hv=1,
        max_hv=500,
        min_option_volume=0,
        check_liquidity=False,
    )

    assert 'IV%' in df.columns and 'HV_30d%' in df.columns and 'IV/HV' in df.columns

    for _, r in df.iterrows():
        iv = float(r['IV%'])
        hv = float(r['HV_30d%'])
        ratio = float(r['IV/HV'])
        if hv > 0:
            expected_ratio = round(iv / hv, 2)
            assert _almost_equal(
                ratio, expected_ratio, tol=0.02
            ), (
                f"IV/HV ratio mismatch for {r.get('Ticker')}: "
                f"expected {expected_ratio}, got {ratio} (IV%={iv}, HV%={hv})"
            )


def test_data_warnings_flags_present_when_expected():
    syms = ["AAPL", "GOOG", "META"]
    df = prescreen_tickers(
        syms,
        min_price=1,
        max_price=10000,
        min_avg_volume=1,
        min_hv=1,
        max_hv=500,
        min_option_volume=0,
        check_liquidity=False,
    )

    assert 'Data_Warnings' in df.columns
    assert 'IV_Source' in df.columns
    assert 'OptVolSrc' in df.columns
    assert 'Spread_SampleCount' in df.columns

    for _, r in df.iterrows():
        warnings = (r['Data_Warnings'] or '').split(',') if isinstance(r['Data_Warnings'], str) else []
        iv_source = r['IV_Source']
        opt_vol_src = r['OptVolSrc']
        sample_count = int(r['Spread_SampleCount'])

        if iv_source == 'hv_proxy':
            assert 'IV_HV_PROXY' in warnings
        if iv_source == 'yfinance':
            assert 'IV_FROM_YF' in warnings
        if opt_vol_src == 'yfinance':
            assert 'VOLUME_FROM_YF' in warnings
        if sample_count < 2:
            assert 'SPREAD_DEFAULT' in warnings

