import pandas as pd
import numpy as np

from compare_utils import build_compare_dataframe


def _mock_df(strategy: str, premium_per_share: float, mc_expected_contract: float) -> pd.DataFrame:
    # Provide minimal columns used by builder.
    rows = [{
        "Strategy": strategy,
        "Ticker": "MOCK",
        "Exp": "2025-12-19",
        "Days": 30,
        "Strike": 100.0,
        "Premium": premium_per_share,  # per share for CSP/CC prior to normalization
        "ROI%_ann": 25.0,
        "Score": 0.5,
        "MC_ROI_ann%": 40.0,
        "MC_ExpectedPnL": mc_expected_contract,  # already per contract from MC engine
        "MC_PnL_p5": mc_expected_contract * 0.2,
        "Collateral": 10000,
        "Capital": 10000,
    }]
    return pd.DataFrame(rows)


def test_compare_normalizes_premium_contract_level_cc():
    df_cc = _mock_df("CC", premium_per_share=6.10, mc_expected_contract=350.0)
    cmp_df = build_compare_dataframe(df_cc=df_cc)
    assert not cmp_df.empty
    prem = float(cmp_df.iloc[0]["Premium"])
    # Expect per share premium * 100
    assert abs(prem - 610.0) < 1e-6, f"Premium normalization failed: {prem}"
    # MC expected PnL should be same scale (contract-level) and not exceed plausible upper bound (premium + intrinsic cap)
    mc_pnl = float(cmp_df.iloc[0]["MC_ExpectedPnL"])
    assert mc_pnl <= prem * 5, "MC expected PnL unreasonably high relative to premium (sanity bound)"


def test_compare_normalizes_premium_contract_level_csp():
    df_csp = _mock_df("CSP", premium_per_share=1.55, mc_expected_contract=120.0)
    cmp_df = build_compare_dataframe(df_csp=df_csp)
    prem = float(cmp_df.iloc[0]["Premium"])
    assert abs(prem - 155.0) < 1e-6
    mc_pnl = float(cmp_df.iloc[0]["MC_ExpectedPnL"])
    assert mc_pnl <= prem * 3, "CSP MC expected PnL too large vs premium (sanity)"


def test_compare_premium_spread_credit():
    df_bcs = pd.DataFrame([{
        "Strategy": "BEAR_CALL_SPREAD",
        "Ticker": "MOCK",
        "Exp": "2025-12-19",
        "Days": 30,
        "SellStrike": 105.0,
        "BuyStrike": 110.0,
        "NetCredit": 1.80,  # per share credit
        "ROI%_ann": 40.0,
        "Score": 0.6,
        "MC_ROI_ann%": 55.0,
        "MC_ExpectedPnL": 130.0,
        "MC_PnL_p5": -250.0,
        "Capital": 320.0,
    }])
    cmp_df = build_compare_dataframe(df_bear_call_spread=df_bcs)
    prem = float(cmp_df.iloc[0]["Premium"])
    assert abs(prem - 180.0) < 1e-6
    mc_pnl = float(cmp_df.iloc[0]["MC_ExpectedPnL"])
    # Max profit = credit * 100 = 180; MC expected should not exceed that substantially
    assert mc_pnl <= prem * 1.2, f"Spread MC expected PnL exceeds plausible cap: {mc_pnl} vs {prem}"


def test_compare_premium_net_debit_pmcc():
    df_pmcc = pd.DataFrame([{
        "Strategy": "PMCC",
        "Ticker": "MOCK",
        "Exp": "2025-12-19",
        "Days": 45,
        "LongStrike": 80.0,
        "ShortStrike": 105.0,
        "NetDebit": 12.50,  # per share
        "ROI%_ann": 18.0,
        "Score": 0.55,
        "MC_ROI_ann%": 22.0,
        "MC_ExpectedPnL": 240.0,
        "MC_PnL_p5": -150.0,
    }])
    cmp_df = build_compare_dataframe(df_pmcc=df_pmcc)
    prem = float(cmp_df.iloc[0]["Premium"])
    assert abs(prem - 1250.0) < 1e-6, "PMCC net debit normalization failed"
    mc_pnl = float(cmp_df.iloc[0]["MC_ExpectedPnL"])
    # Sanity: MC expected PnL should not exceed net debit * 0.5 in typical conservative model (not enforced strictly, just upper bound)
    assert mc_pnl <= prem, "PMCC MC expected PnL exceeds net debit (unexpected)"


def test_compare_empty_returns_empty():
    cmp_df = build_compare_dataframe()
    assert cmp_df.empty
