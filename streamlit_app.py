# streamlit_app.py — Interactive dashboard for your short-put scanner
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from typing import List
from datetime import datetime
from app import analyze_puts, mc_short_put_loss_prob

# Import the analyzer from app.py
# (Safe because app.py has a proper __main__ guard)
from app import analyze_puts

st.set_page_config(page_title="OTM Short Put Scanner", layout="wide")

st.title("📉 OTM Short Put Scanner (Cash-Secured)")

with st.sidebar:
    st.header("Settings")
    tickers_str = st.text_input(
        "Tickers (comma-separated)",
        value="AAPL,MSFT,SPY,TSLA,QQQ,KO,IBM,NVDA,AMZN"
    )
    col1, col2 = st.columns(2)
    with col1:
        days_limit = st.slider("Max Days to Expiry", 7, 90, 45, step=1)
        min_otm = st.slider("Min OTM %", 0.0, 35.0, 12.0, step=0.5)
        min_oi = st.slider("Min Open Interest", 0, 2000, 200, step=50)
        earn_window = st.slider("Earnings Window (± days)", 0, 14, 5, step=1)
    with col2:
        max_spread = st.slider("Max Spread % of Mid",
                               1.0, 30.0, 10.0, step=0.5)
        min_roi = st.slider("Min Ann. ROI (decimal)",
                            0.00, 0.50, 0.12, step=0.01)
        min_cushion = st.slider("Min Sigma Cushion", 0.0, 3.0, 1.0, step=0.1)
        min_poew = st.slider(
            "Min POEW (Prob Expire Worthless)", 0.50, 0.95, 0.65, step=0.01)

    risk_free = st.number_input(
        "Risk-free rate (annualized, decimal)", value=0.00, step=0.01, format="%.4f")
    per_contract_cap = st.number_input(
        "Per-Contract Collateral Cap ($, 0 = no cap)", min_value=0, value=0, step=1000
    )
    per_contract_cap = None if per_contract_cap == 0 else float(
        per_contract_cap)

    st.caption("Tip: Widen the right-side table columns by dragging headers.")

    run_btn = st.button("🔎 Scan")
    st.divider()
    st.subheader("Monte Carlo")
    do_mc = st.checkbox("Enable Monte Carlo on a selected contract", value=True)
    paths = st.slider("MC paths", 5_000, 200_000, 50_000, step=5_000)
    loss_frac = st.slider("Loss threshold (% of collateral)",
                      1, 50, 10, step=1) / 100.0
    mc_drift = st.number_input("Annual drift (decimal)",
                           value=0.00, step=0.01, format="%.2f")
    mc_seed = st.number_input("Random seed (optional)",
                          value=0, min_value=0, step=1)
    use_seed = None if mc_seed == 0 else int(mc_seed)


@st.cache_data(show_spinner=True, ttl=120)
def run_scan(tickers: List[str], opts: dict) -> pd.DataFrame:
    all_results = []
    for t in tickers:
        df = analyze_puts(
            t,
            days_limit=opts["days_limit"],
            min_otm_pct=opts["min_otm"],
            min_oi=opts["min_oi"],
            max_spread_pct=opts["max_spread"],
            min_roi_ann=opts["min_roi"],
            min_cushion_sigma=opts["min_cushion"],
            min_poew=opts["min_poew"],
            earn_window_days=opts["earn_window"],
            per_contract_collateral_cap=opts["per_contract_cap"],
            risk_free_rate=opts["risk_free"],
        )
        if not df.empty:
            all_results.append(df)
    if not all_results:
        return pd.DataFrame()
    out = pd.concat(all_results, ignore_index=True)
    out = out.sort_values(["Score", "ROI%_ann"], ascending=[
                          False, False]).reset_index(drop=True)
    return out



# --- Persist last scan so the page can render even before running again ---
if "scan_df" not in st.session_state:
    st.session_state["scan_df"] = pd.DataFrame()
if "view_df" not in st.session_state:
    st.session_state["view_df"] = pd.DataFrame()

if run_btn:
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
    opts = dict(
        days_limit=int(days_limit),
        min_otm=float(min_otm),
        min_oi=int(min_oi),
        max_spread=float(max_spread),
        min_roi=float(min_roi),
        min_cushion=float(min_cushion),
        min_poew=float(min_poew),
        earn_window=int(earn_window),
        risk_free=float(risk_free),
        per_contract_cap=per_contract_cap,
    )

    with st.spinner("Scanning option chains…"):
        df = run_scan(tickers, opts)

    # Save to session (so later code can read it safely)
    st.session_state["scan_df"] = df.copy()

# ----- Always read from session; this avoids NameError when not run yet -----
df = st.session_state["scan_df"]

if df.empty:
    st.warning("No candidates found with current filters. Try loosening OTM%, ROI, OI, spread, or earnings window.")
else:
    st.success(f"Found {len(df)} contracts")

    # Column chooser + sort controls
    default_cols = [
        "Ticker","Price","Strike","Exp","Days","Premium",
        "OTM%","ROI%_ann","IV","POEW","CushionSigma",
        "Spread%","OI","CostBasis","Collateral","Ownable","Score"
    ]
    available_cols = list(df.columns)
    cols_to_show = st.multiselect(
        "Columns",
        options=available_cols,
        default=[c for c in default_cols if c in available_cols]
    )

    sort_col = st.selectbox(
        "Sort by",
        options=cols_to_show or available_cols,
        index=(cols_to_show or available_cols).index("Score") if "Score" in (cols_to_show or available_cols) else 0
    )
    sort_asc = st.toggle("Ascending sort", value=False)

    # Quick display filters -> build dff
    fl_col1, fl_col2, fl_col3 = st.columns(3)
    with fl_col1:
        min_roi_show = st.slider("Display Min ROI%_ann", 0.0, 100.0, float(max(0.0, df["ROI%_ann"].min() if "ROI%_ann" in df else 0.0)), step=0.5)
    with fl_col2:
        min_poew_show = st.slider("Display Min POEW", 0.0, 1.0, float(max(0.0, df["POEW"].min() if "POEW" in df else 0.0)), step=0.01)
    with fl_col3:
        min_cush_show = st.slider("Display Min CushionSigma", 0.0, 3.0, float(min(1.0, df["CushionSigma"].min() if "CushionSigma" in df else 0.0)), step=0.1)

    dff = df.copy()
    if "ROI%_ann" in dff:
        dff = dff[dff["ROI%_ann"] >= min_roi_show]
    if "POEW" in dff:
        dff = dff[dff["POEW"] >= min_poew_show]
    if "CushionSigma" in dff:
        dff = dff[dff["CushionSigma"] >= min_cush_show]

    if sort_col in dff.columns:
        dff = dff.sort_values(sort_col, ascending=sort_asc).reset_index(drop=True)

    # Keep the latest view in session (optional, for other widgets)
    st.session_state["view_df"] = dff.copy()

    st.dataframe(dff[cols_to_show] if cols_to_show else dff, use_container_width=True, height=600)

    # Download button must live where dff exists
    if not dff.empty:
        csv = dff.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download CSV",
            data=csv,
            file_name="put_scanner_results.csv",
            mime="text/csv",
        )

    # ===================== MONTE CARLO SECTION =====================
# ===================== MONTE CARLO SECTION =====================
if do_mc and not dff.empty:
    st.subheader("Monte Carlo Risk (per selected contract)")

    # Build selection dataset and key
    pick_df = dff.copy()
    key_col = "__KEY__"
    pick_df[key_col] = (
        pick_df["Ticker"].astype(str) + " | "
        + pick_df["Exp"].astype(str) + " | K="
        + pick_df["Strike"].astype(str) + " | Prem="
        + pick_df["Premium"].astype(str) + " | ROI%="
        + pick_df["ROI%_ann"].astype(str)
    )

    # Optional pre-selection filters
    f1, f2, f3 = st.columns(3)
    with f1:
        tick_filter = st.multiselect("Filter by ticker", sorted(pick_df["Ticker"].unique().tolist()))
    with f2:
        exp_filter = st.multiselect("Filter by expiry", sorted(pick_df["Exp"].unique().tolist()))
    with f3:
        min_roi_pick = st.slider("Min ROI%_ann (picker)", 0.0, 100.0, 0.0, step=0.5)

    if tick_filter:
        pick_df = pick_df[pick_df["Ticker"].isin(tick_filter)]
    if exp_filter:
        pick_df = pick_df[pick_df["Exp"].isin(exp_filter)]
    if "ROI%_ann" in pick_df:
        pick_df = pick_df[pick_df["ROI%_ann"] >= min_roi_pick]

    if pick_df.empty:
        st.info("No rows available for MC after picker filters — loosen filters.")
    else:
        choice = st.selectbox("Choose a contract", options=pick_df[key_col].tolist(), index=0)
        sel_row = pick_df[pick_df[key_col] == choice].iloc[0]

        # ---- Run MC on the selected row ----
        mc = mc_short_put_loss_prob(
            sel_row,
            loss_frac=loss_frac,
            n_paths=int(paths),
            mu=float(mc_drift),
            seed=use_seed
        )

        # Summary metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Prob(loss > threshold)", f"{mc['prob_loss_over']*100:.2f}%")
        c2.metric("Expected P&L / contract", f"${mc['expected_pnl']:,.0f}")
        c3.metric("P&L (5% / 50% / 95%)", f"${mc['pnl_p5']:,.0f} / ${mc['pnl_p50']:,.0f} / ${mc['pnl_p95']:,.0f}")
        c4.metric("Worst MC path", f"${mc['pnl_min']:,.0f}")

        st.caption(
            f"Selected: {sel_row['Ticker']} {sel_row['Exp']} K={sel_row['Strike']} • "
            f"Collateral=${mc['collateral']:,.0f} • "
            f"Loss threshold={loss_frac:.0%} → ${mc['loss_threshold']:,.0f} • "
            f"Days={mc['days']} • IV used={mc['iv_used']*100:.2f}% • Paths={mc['paths']:,}"
        )

        # Histogram
        pnl = mc["pnl_paths"]
        bins = np.histogram_bin_edges(pnl, bins="auto")
        hist, edges = np.histogram(pnl, bins=bins)
        chart_df = pd.DataFrame({"pnl": (edges[:-1] + edges[1:]) / 2.0, "count": hist})

        base = alt.Chart(chart_df).mark_bar().encode(
            x=alt.X("pnl:Q", title="P&L per contract (USD)"),
            y=alt.Y("count:Q", title="Frequency"),
            tooltip=["pnl", "count"]
        )
        rule_df = pd.DataFrame({"x": [mc["loss_threshold"]]})
        rule = alt.Chart(rule_df).mark_rule(strokeDash=[4,4]).encode(x="x:Q")
        st.altair_chart(base + rule, use_container_width=True)

        # ===================== AT-A-GLANCE SUMMARY =====================
        st.subheader("At-a-Glance: Trade Summary & Risk")

        def pct(x): 
            return f"{x*100:.2f}%"

        def ann_from_pnl(pnl, collateral, days):
            if collateral <= 0 or days <= 0:
                return float("nan")
            r = pnl / collateral
            try:
                return (1.0 + r) ** (365.0 / days) - 1.0
            except Exception:
                return float("nan")

        collateral = mc["collateral"]
        days = mc["days"]
        price0 = mc["price0"]
        strike = mc["strike"]
        premium = mc["premium"]
        loss_threshold = mc["loss_threshold"]
        prob_tail = mc["prob_loss_over"]
        iv_used = mc["iv_used"]
        p5, p50, p95 = mc["pnl_p5"], mc["pnl_p50"], mc["pnl_p95"]
        exp_pnl = mc["expected_pnl"]
        worst = mc["pnl_min"]

        cost_basis = strike - premium
        breakeven = cost_basis
        assign_prob = max(0.0, 1.0 - float(sel_row.get("POEW", 0.0)))
        cushion_sigma = float(sel_row.get("CushionSigma", float("nan")))
        otm_pct = float(sel_row.get("OTM%", float("nan")))
        max_loss = -(strike - premium) * 100.0

        summary_rows = [
            {"Scenario": "P5 (bear)",    "P&L ($/contract)": f"{p5:,.0f}",
             "Return on Collateral": pct(p5 / collateral),
             "Annualized ROI": pct(ann_from_pnl(p5, collateral, days))},
            {"Scenario": "Median (P50)", "P&L ($/contract)": f"{p50:,.0f}",
             "Return on Collateral": pct(p50 / collateral),
             "Annualized ROI": pct(ann_from_pnl(p50, collateral, days))},
            {"Scenario": "P95 (bull)",   "P&L ($/contract)": f"{p95:,.0f}",
             "Return on Collateral": pct(p95 / collateral),
             "Annualized ROI": pct(ann_from_pnl(p95, collateral, days))},
            {"Scenario": "Expected",     "P&L ($/contract)": f"{exp_pnl:,.0f}",
             "Return on Collateral": pct(exp_pnl / collateral),
             "Annualized ROI": pct(ann_from_pnl(exp_pnl, collateral, days))},
        ]
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Assignment Probability (≈ 1 − POEW)", pct(assign_prob))
        m2.metric("Tail Risk: Pr(P&L < threshold)", pct(prob_tail))
        m3.metric("Loss threshold", f"${loss_threshold:,.0f}")
        m4.metric("Worst MC path", f"${worst:,.0f}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Underlying Price", f"${price0:,.2f}")
        c2.metric("Strike / Premium", f"{strike:.2f} / {premium:.2f}")
        c3.metric("Breakeven (per share)", f"${breakeven:,.2f}")
        c4.metric("Max Loss (per contract)", f"${max_loss:,.0f}")

        c5, c6, c7 = st.columns(3)
        c5.metric("Days to Expiry", f"{days}d")
        c6.metric("OTM distance", f"{otm_pct:.2f}%")
        c7.metric("Cushion (σ to strike)", f"{cushion_sigma:.2f}σ")

        st.caption(
            f"IV used={iv_used*100:.2f}% • Collateral=${collateral:,.0f} • "
            f"Cost basis (if assigned)=${cost_basis:,.2f} • "
            "Annualize via (1 + Return)^(365/Days) - 1 on collateral."
        )





    # Download
csv = dff.to_csv(index=False).encode("utf-8")
st.download_button(
        "⬇️ Download CSV",
        data=csv,
        file_name=f"put_scanner_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

