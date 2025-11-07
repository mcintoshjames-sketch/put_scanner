"""Basic unit tests for unified scoring methodology.

Focus:
 1. Negative MC expected P&L heavily penalized.
 2. Higher expected ROI and better tail risk increase score.
 3. Liquidity & cushion components behave monotonically.
"""
import pandas as pd
from scoring_utils import compute_unified_score, NEG_MC_PENALTY_FACTOR


def test_negative_mc_penalty():
    df = pd.DataFrame({
        'MC_ExpectedPnL': [100.0, -10.0],
        'MC_ROI_ann%': [50.0, 50.0],
        'ROI%_ann': [50.0, 50.0],
        'MC_PnL_p5': [-50.0, -50.0],
        'NetCredit': [1.00, 1.00],
        'Spread%': [5.0, 5.0],
        'Volume': [500, 500],
        'OI': [1000, 1000],
        'Width': [5.0, 5.0],
        'CushionSigma': [1.0, 1.0],
    })
    scores = compute_unified_score(df)
    assert scores.iloc[0] > scores.iloc[1] * 5, "Positive EV should dwarf penalized negative EV score"
    # Confirm penalty applied approximately
    assert scores.iloc[1] < 0.2, "Negative MC expected PnL should produce very low score"


def test_tail_risk_effect():
    df = pd.DataFrame({
        'MC_ExpectedPnL': [50.0, 50.0],
        'MC_ROI_ann%': [30.0, 30.0],
        'ROI%_ann': [30.0, 30.0],
        'MC_PnL_p5': [-10.0, -80.0],  # second row worse tail
        'NetCredit': [1.00, 1.00],
        'Spread%': [5.0, 5.0],
        'Volume': [500, 500],
        'OI': [1000, 1000],
        'Width': [5.0, 5.0],
        'CushionSigma': [1.0, 1.0],
    })
    scores = compute_unified_score(df)
    assert scores.iloc[0] > scores.iloc[1], "Worse p5 tail loss should reduce score"


def test_liquidity_spread_monotonic():
    df = pd.DataFrame({
        'MC_ExpectedPnL': [10.0, 10.0, 10.0],
        'MC_ROI_ann%': [20.0, 20.0, 20.0],
        'ROI%_ann': [20.0, 20.0, 20.0],
        'MC_PnL_p5': [-10.0, -10.0, -10.0],
        'NetCredit': [1.00, 1.00, 1.00],
        'Spread%': [2.0, 10.0, 18.0],  # worsening spreads
        'Volume': [500, 500, 500],
        'OI': [1000, 1000, 1000],
        'Width': [5.0, 5.0, 5.0],
        'CushionSigma': [1.0, 1.0, 1.0],
    })
    scores = compute_unified_score(df)
    assert scores.iloc[0] > scores.iloc[1] > scores.iloc[2], "Tighter spreads should improve score monotonically"


def test_cushion_effect():
    df = pd.DataFrame({
        'MC_ExpectedPnL': [10.0, 10.0],
        'MC_ROI_ann%': [20.0, 20.0],
        'ROI%_ann': [20.0, 20.0],
        'MC_PnL_p5': [-5.0, -5.0],
        'NetCredit': [1.00, 1.00],
        'Spread%': [5.0, 5.0],
        'Volume': [500, 500],
        'OI': [1000, 1000],
        'Width': [5.0, 5.0],
        'CushionSigma': [0.5, 2.0],  # more cushion second row
    })
    scores = compute_unified_score(df)
    assert scores.iloc[1] > scores.iloc[0], "Higher cushion should increase score"

def test_efficiency_component_credit_vs_capital():
    # Wider width increases capital, same credit lowers efficiency
    df = pd.DataFrame({
        'MC_ExpectedPnL': [10.0, 10.0],
        'MC_ROI_ann%': [20.0, 20.0],
        'ROI%_ann': [20.0, 20.0],
        'MC_PnL_p5': [-5.0, -5.0],
        'NetCredit': [1.00, 1.00],
        'Spread%': [5.0, 5.0],
        'Volume': [500, 500],
        'OI': [1000, 1000],
        'Width': [5.0, 10.0],  # second row double risk capital
        'CushionSigma': [1.0, 1.0],
    })
    scores = compute_unified_score(df)
    assert scores.iloc[0] > scores.iloc[1], "Lower capital for same credit should score higher (efficiency)"


def test_penalty_exact_factor():
    df = pd.DataFrame({
        'MC_ExpectedPnL': [-1.0, 1.0],
        'MC_ROI_ann%': [10.0, 10.0],
        'ROI%_ann': [10.0, 10.0],
        'MC_PnL_p5': [-1.0, -1.0],
        'NetCredit': [0.50, 0.50],
        'Spread%': [5.0, 5.0],
        'Volume': [500, 500],
        'OI': [1000, 1000],
        'Width': [5.0, 5.0],
        'CushionSigma': [1.0, 1.0],
    })
    scores = compute_unified_score(df)
    # Negative EV row should be near floor, positive should be meaningfully higher
    assert scores.iloc[0] < 0.2, "Negative EV row should be near floor"
    assert scores.iloc[1] > scores.iloc[0] * 3, "Penalty should drastically reduce score vs positive EV"