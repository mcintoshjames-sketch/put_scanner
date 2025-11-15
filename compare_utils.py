import numpy as np
import pandas as pd

try:
    from scoring_utils import apply_unified_score as _apply_unified_score
except Exception:
    _apply_unified_score = None


def build_compare_dataframe(
    df_csp: pd.DataFrame | None = None,
    df_cc: pd.DataFrame | None = None,
    df_pmcc: pd.DataFrame | None = None,
    df_synthetic_collar: pd.DataFrame | None = None,
    df_collar: pd.DataFrame | None = None,
    df_iron_condor: pd.DataFrame | None = None,
    df_bull_put_spread: pd.DataFrame | None = None,
    df_bear_call_spread: pd.DataFrame | None = None,
    apply_unified: bool = True,
) -> pd.DataFrame:
    """Assemble a comparable DataFrame across strategies for the Compare tab.

    Normalizes Premium to contract-level dollars and maps varying schemas to a common subset
    of columns. Does not perform sorting or additional annotations (Tail/EV labels).
    """
    pieces: list[pd.DataFrame] = []

    def _maybe_apply_unified(df: pd.DataFrame) -> pd.DataFrame:
        if apply_unified and _apply_unified_score is not None and not df.empty:
            try:
                return _apply_unified_score(df.copy())
            except Exception:
                return df
        return df

    if df_csp is not None and not df_csp.empty:
        tmp = _maybe_apply_unified(df_csp.copy())
        cols = [c for c in [
            "Strategy","Ticker","Exp","Days","Strike","Premium","ROI%_ann","Score",
            "UnifiedScore","MC_ROI_ann%","MC_ExpectedPnL","MC_PnL_p5","Collateral","Capital","Kelly%","KellySize"
        ] if c in tmp.columns]
        tmp = tmp[cols]
        if "Premium" in tmp.columns:
            tmp["Premium"] = pd.to_numeric(tmp["Premium"], errors="coerce") * 100.0
        tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + " | K=" + tmp["Strike"].astype(str)
        pieces.append(tmp)

    if df_cc is not None and not df_cc.empty:
        tmp = _maybe_apply_unified(df_cc.copy())
        cols = [c for c in [
            "Strategy","Ticker","Exp","Days","Strike","Premium","ROI%_ann","Score",
            "UnifiedScore","MC_ROI_ann%","MC_ExpectedPnL","MC_PnL_p5","Capital","Kelly%","KellySize"
        ] if c in tmp.columns]
        tmp = tmp[cols]
        if "Premium" in tmp.columns:
            tmp["Premium"] = pd.to_numeric(tmp["Premium"], errors="coerce") * 100.0
        tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + " | K=" + tmp["Strike"].astype(str)
        pieces.append(tmp)

    if df_pmcc is not None and not df_pmcc.empty:
        tmp = _maybe_apply_unified(df_pmcc.copy())
        tmp["Strike"] = tmp.get("ShortStrike", np.nan)
        # Present net debit per contract as Premium surrogate
        tmp["Premium"] = pd.to_numeric(tmp.get("NetDebit", np.nan), errors="coerce") * 100.0
        cols = [c for c in [
            "Strategy","Ticker","Exp","Days","LongStrike","ShortStrike","NetDebit","ROI%_ann",
            "Score","UnifiedScore","MC_ROI_ann%","MC_ExpectedPnL","MC_PnL_p5","Strike","Premium","Kelly%","KellySize"
        ] if c in tmp.columns]
        tmp = tmp[cols]
        tmp["Key"] = (
            tmp.get("Ticker", "") + " | " + tmp.get("Exp").astype(str)
            + " | Long=" + tmp.get("LongStrike").astype(str)
            + " | Short=" + tmp.get("ShortStrike").astype(str)
        )
        pieces.append(tmp)

    if df_synthetic_collar is not None and not df_synthetic_collar.empty:
        tmp = _maybe_apply_unified(df_synthetic_collar.copy())
        tmp["Strike"] = tmp.get("ShortStrike", np.nan)
        tmp["Premium"] = pd.to_numeric(tmp.get("NetDebit", np.nan), errors="coerce") * 100.0
        cols = [c for c in [
            "Strategy","Ticker","Exp","Days","LongStrike","PutStrike","ShortStrike","NetDebit",
            "ROI%_ann","Score","UnifiedScore","MC_ROI_ann%","MC_ExpectedPnL","MC_PnL_p5","Strike","Premium","Kelly%","KellySize"
        ] if c in tmp.columns]
        tmp = tmp[cols]
        tmp["Key"] = (
            tmp.get("Ticker", "") + " | " + tmp.get("Exp").astype(str)
            + " | Long=" + tmp.get("LongStrike").astype(str)
            + " | Put=" + tmp.get("PutStrike").astype(str)
            + " | Short=" + tmp.get("ShortStrike").astype(str)
        )
        pieces.append(tmp)

    if df_collar is not None and not df_collar.empty:
        tmp = _maybe_apply_unified(df_collar.copy())
        cols = [c for c in [
            "Strategy","Ticker","Exp","Days","CallStrike","PutStrike","NetCredit","ROI%_ann",
            "Score","UnifiedScore","MC_ROI_ann%","MC_ExpectedPnL","MC_PnL_p5","Capital","Kelly%","KellySize"
        ] if c in tmp.columns]
        tmp = tmp[cols]
        tmp = tmp.rename(columns={"CallStrike": "Strike"})
        tmp["Premium"] = pd.to_numeric(tmp.get("NetCredit"), errors="coerce") * 100.0
        tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + " | K=" + tmp["Strike"].astype(str)
        tmp["Strategy"] = "COLLAR"
        pieces.append(tmp)

    if df_iron_condor is not None and not df_iron_condor.empty:
        tmp = _maybe_apply_unified(df_iron_condor.copy())
        cols = [c for c in [
            "Strategy","Ticker","Exp","Days","CallShortStrike","PutShortStrike","NetCredit","ROI%_ann",
            "Score","UnifiedScore","MC_ROI_ann%","MC_ExpectedPnL","MC_PnL_p5","Capital","Kelly%","KellySize"
        ] if c in tmp.columns]
        tmp = tmp[cols]
        tmp = tmp.rename(columns={"CallShortStrike": "Strike"})
        tmp["Premium"] = pd.to_numeric(tmp.get("NetCredit"), errors="coerce") * 100.0
        tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + " | CS=" + tmp["Strike"].astype(str) + " | PS=" + tmp["PutShortStrike"].astype(str)
        pieces.append(tmp)

    if df_bull_put_spread is not None and not df_bull_put_spread.empty:
        tmp = _maybe_apply_unified(df_bull_put_spread.copy())
        cols = [c for c in [
            "Strategy","Ticker","Exp","Days","SellStrike","BuyStrike","NetCredit","ROI%_ann",
            "Score","UnifiedScore","MC_ROI_ann%","MC_ExpectedPnL","MC_PnL_p5","Capital","Kelly%","KellySize"
        ] if c in tmp.columns]
        tmp = tmp[cols]
        tmp = tmp.rename(columns={"SellStrike": "Strike"})
        tmp["Premium"] = pd.to_numeric(tmp.get("NetCredit"), errors="coerce") * 100.0
        tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + " | Sell=" + tmp["Strike"].astype(str) + " | Buy=" + tmp["BuyStrike"].astype(str)
        pieces.append(tmp)

    if df_bear_call_spread is not None and not df_bear_call_spread.empty:
        tmp = _maybe_apply_unified(df_bear_call_spread.copy())
        cols = [c for c in [
            "Strategy","Ticker","Exp","Days","SellStrike","BuyStrike","NetCredit","ROI%_ann",
            "Score","UnifiedScore","MC_ROI_ann%","MC_ExpectedPnL","MC_PnL_p5","Capital","Kelly%","KellySize"
        ] if c in tmp.columns]
        tmp = tmp[cols]
        tmp = tmp.rename(columns={"SellStrike": "Strike"})
        tmp["Premium"] = pd.to_numeric(tmp.get("NetCredit"), errors="coerce") * 100.0
        tmp["Key"] = tmp["Ticker"] + " | " + tmp["Exp"] + " | Sell=" + tmp["Strike"].astype(str) + " | Buy=" + tmp["BuyStrike"].astype(str)
        pieces.append(tmp)

    if not pieces:
        return pd.DataFrame()
    return pd.concat(pieces, ignore_index=True)
