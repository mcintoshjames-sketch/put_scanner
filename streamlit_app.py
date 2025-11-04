# streamlit_app.py — Interactive dashboard for multi-strategy options scanner
import warnings
import logging

# Suppress Streamlit's ScriptRunContext warnings in worker threads
warnings.filterwarnings('ignore', message='.*ScriptRunContext.*')
logging.getLogger('streamlit.runtime.scriptrunner').setLevel(logging.ERROR)

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from typing import List, Dict, Tuple
from datetime import datetime

# Import the multi-strategy scanner from strategy_lab
from strategy_lab import run_scans

st.set_page_config(page_title="Multi-Strategy Options Scanner", layout="wide")

st.title("� Multi-Strategy Options Scanner")

with st.sidebar:
    st.header("Settings")
    
    # Strategy Selection
    st.subheader("Strategies")
    strategies = st.multiselect(
        "Select strategies to scan",
        ["CSP", "CC", "Collar", "IC", "Bull Put", "Bear Call"],
        default=["CSP"]
    )
    
    # Tickers
    tickers_str = st.text_input(
        "Tickers (comma-separated)",
        value="BA,META"
    )
    
    st.subheader("Common Parameters")
    col1, col2 = st.columns(2)
    with col1:
        min_days = st.slider("Min Days to Expiry", 0, 30, 0, step=1)
        days_limit = st.slider("Max Days to Expiry", 7, 90, 45, step=1)
        min_oi = st.slider("Min Open Interest", 0, 2000, 200, step=50)
        earn_window = st.slider("Earnings Window (± days)", 0, 14, 5, step=1)
    with col2:
        max_spread = st.slider("Max Spread % of Mid", 1.0, 30.0, 10.0, step=0.5)
        risk_free = st.number_input("Risk-free rate (decimal)", value=0.00, step=0.01, format="%.4f")
        bill_yield = st.number_input("T-Bill yield (decimal)", value=0.00, step=0.01, format="%.4f")
    
    # CSP Parameters
    if "CSP" in strategies:
        st.subheader("CSP Parameters")
        col1, col2 = st.columns(2)
        with col1:
            min_otm_csp = st.slider("CSP: Min OTM %", 0.0, 35.0, 12.0, step=0.5, key="otm_csp")
            min_roi_csp = st.slider("CSP: Min Ann. ROI", 0.00, 0.50, 0.05, step=0.01, key="roi_csp")
        with col2:
            min_cushion = st.slider("CSP: Min Sigma Cushion", 0.0, 3.0, 1.0, step=0.1)
            min_poew = st.slider("CSP: Min POEW", 0.50, 0.95, 0.65, step=0.01)
        per_contract_cap = st.number_input("CSP: Per-Contract Cap ($, 0=no cap)", min_value=0, value=0, step=1000)
        per_contract_cap = None if per_contract_cap == 0 else float(per_contract_cap)
    else:
        min_otm_csp = 12.0
        min_roi_csp = 0.05
        min_cushion = 1.0
        min_poew = 0.65
        per_contract_cap = None
    
    # CC Parameters
    if "CC" in strategies:
        st.subheader("CC Parameters")
        col1, col2 = st.columns(2)
        with col1:
            min_otm_cc = st.slider("CC: Min OTM %", 0.0, 35.0, 5.0, step=0.5, key="otm_cc")
            min_roi_cc = st.slider("CC: Min Ann. ROI", 0.00, 0.50, 0.05, step=0.01, key="roi_cc")
        with col2:
            include_div_cc = st.checkbox("CC: Include Dividends in ROI", value=True)
    else:
        min_otm_cc = 5.0
        min_roi_cc = 0.05
        include_div_cc = True
    
    # Collar Parameters
    if "Collar" in strategies:
        st.subheader("Collar Parameters")
        col1, col2 = st.columns(2)
        with col1:
            call_delta_tgt = st.slider("Collar: Call Delta Target", 0.1, 0.5, 0.30, step=0.05, key="call_delta")
            put_delta_tgt = st.slider("Collar: Put Delta Target", 0.1, 0.5, 0.20, step=0.05, key="put_delta")
        with col2:
            min_net_credit = st.number_input("Collar: Min Net Credit", value=0.0, step=0.10, key="net_credit")
            min_net_credit = None if min_net_credit == 0.0 else float(min_net_credit)
            include_div_col = st.checkbox("Collar: Include Dividends", value=True, key="div_col")
    else:
        call_delta_tgt = 0.30
        put_delta_tgt = 0.20
        min_net_credit = None
        include_div_col = True
    
    # IC Parameters
    if "IC" in strategies:
        st.subheader("Iron Condor Parameters")
        col1, col2 = st.columns(2)
        with col1:
            ic_min_roi = st.slider("IC: Min ROI %", 0.0, 50.0, 10.0, step=1.0, key="ic_roi")
            ic_min_cushion = st.slider("IC: Min Cushion", 0.0, 3.0, 0.5, step=0.1, key="ic_cushion")
        with col2:
            ic_spread_width_put = st.number_input("IC: Put Spread Width", value=5.0, step=1.0, key="ic_put_width")
            ic_spread_width_call = st.number_input("IC: Call Spread Width", value=5.0, step=1.0, key="ic_call_width")
        ic_target_delta = st.slider("IC: Target Delta (short strikes)", 0.05, 0.30, 0.16, step=0.01, key="ic_delta")
    else:
        ic_min_roi = 10.0
        ic_min_cushion = 0.5
        ic_spread_width_put = 5.0
        ic_spread_width_call = 5.0
        ic_target_delta = 0.16
    
    # Credit Spread Parameters
    if "Bull Put" in strategies or "Bear Call" in strategies:
        st.subheader("Credit Spread Parameters")
        col1, col2 = st.columns(2)
        with col1:
            cs_min_roi = st.slider("CS: Min ROI %", 0.0, 50.0, 10.0, step=1.0, key="cs_roi")
            cs_spread_width = st.number_input("CS: Spread Width", value=5.0, step=1.0, key="cs_width")
        with col2:
            cs_target_delta = st.slider("CS: Target Delta (short strike)", 0.05, 0.30, 0.16, step=0.01, key="cs_delta")
    else:
        cs_min_roi = 10.0
        cs_spread_width = 5.0
        cs_target_delta = 0.16

    run_btn = st.button("🔎 Scan All Strategies")


@st.cache_data(show_spinner=True, ttl=120)
def run_multi_strategy_scan(tickers: List[str], params: dict) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    """Run multi-strategy scan using strategy_lab"""
    return run_scans(tickers, params)


# --- Persist last scan so the page can render even before running again ---
if "scan_results" not in st.session_state:
    st.session_state["scan_results"] = {
        "csp": pd.DataFrame(),
        "cc": pd.DataFrame(),
        "collar": pd.DataFrame(),
        "ic": pd.DataFrame(),
        "bull_put": pd.DataFrame(),
        "bear_call": pd.DataFrame(),
        "counters": {}
    }

if run_btn:
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
    
    if not tickers:
        st.error("Please enter at least one ticker symbol")
    else:
        params = {
            "min_days": int(min_days),
            "days_limit": int(days_limit),
            "min_oi": int(min_oi),
            "max_spread": float(max_spread),
            "earn_window": int(earn_window),
            "risk_free": float(risk_free),
            "bill_yield": float(bill_yield),
            # CSP params
            "min_otm_csp": float(min_otm_csp),
            "min_roi_csp": float(min_roi_csp),
            "min_cushion": float(min_cushion),
            "min_poew": float(min_poew),
            "per_contract_cap": per_contract_cap,
            # CC params
            "min_otm_cc": float(min_otm_cc),
            "min_roi_cc": float(min_roi_cc),
            "include_div_cc": bool(include_div_cc),
            # Collar params
            "call_delta_tgt": float(call_delta_tgt),
            "put_delta_tgt": float(put_delta_tgt),
            "min_net_credit": min_net_credit,
            "include_div_col": bool(include_div_col),
            # IC params
            "ic_min_roi": float(ic_min_roi),
            "ic_min_cushion": float(ic_min_cushion),
            "ic_spread_width_put": float(ic_spread_width_put),
            "ic_spread_width_call": float(ic_spread_width_call),
            "ic_target_delta": float(ic_target_delta),
            # Credit spread params
            "cs_min_roi": float(cs_min_roi),
            "cs_spread_width": float(cs_spread_width),
            "cs_target_delta": float(cs_target_delta),
        }

        with st.spinner("Scanning option chains for all strategies..."):
            df_csp, df_cc, df_col, df_ic, df_bps, df_bcs, counters = run_multi_strategy_scan(tickers, params)
        
        # Save to session
        st.session_state["scan_results"] = {
            "csp": df_csp.copy() if not df_csp.empty else pd.DataFrame(),
            "cc": df_cc.copy() if not df_cc.empty else pd.DataFrame(),
            "collar": df_col.copy() if not df_col.empty else pd.DataFrame(),
            "ic": df_ic.copy() if not df_ic.empty else pd.DataFrame(),
            "bull_put": df_bps.copy() if not df_bps.empty else pd.DataFrame(),
            "bear_call": df_bcs.copy() if not df_bcs.empty else pd.DataFrame(),
            "counters": counters
        }
        st.session_state["selected_strategies"] = strategies

# ----- Always read from session -----
results = st.session_state["scan_results"]
selected_strategies = st.session_state.get("selected_strategies", ["CSP"])

# ----- Display results for each strategy -----
st.header("Scan Results")

# Summary metrics
col1, col2, col3, col4, col5, col6 = st.columns(6)
with col1:
    st.metric("CSP", len(results["csp"]))
with col2:
    st.metric("CC", len(results["cc"]))
with col3:
    st.metric("Collar", len(results["collar"]))
with col4:
    st.metric("IC", len(results["ic"]))
with col5:
    st.metric("Bull Put", len(results["bull_put"]))
with col6:
    st.metric("Bear Call", len(results["bear_call"]))

# Display each strategy's results
if "CSP" in selected_strategies and not results["csp"].empty:
    st.subheader("💰 Cash-Secured Puts (CSP)")
    st.success(f"Found {len(results['csp'])} CSP contracts")
    st.dataframe(results["csp"], use_container_width=True)
    st.download_button(
        "📥 Download CSP CSV",
        results["csp"].to_csv(index=False).encode("utf-8"),
        file_name=f"csp_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
elif "CSP" in selected_strategies:
    st.info("No CSP contracts found with current filters.")

if "CC" in selected_strategies and not results["cc"].empty:
    st.subheader("📈 Covered Calls (CC)")
    st.success(f"Found {len(results['cc'])} CC contracts")
    st.dataframe(results["cc"], use_container_width=True)
    st.download_button(
        "📥 Download CC CSV",
        results["cc"].to_csv(index=False).encode("utf-8"),
        file_name=f"cc_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
elif "CC" in selected_strategies:
    st.info("No CC contracts found with current filters.")

if "Collar" in selected_strategies and not results["collar"].empty:
    st.subheader("🔒 Collars")
    st.success(f"Found {len(results['collar'])} Collar contracts")
    st.dataframe(results["collar"], use_container_width=True)
    st.download_button(
        "📥 Download Collar CSV",
        results["collar"].to_csv(index=False).encode("utf-8"),
        file_name=f"collar_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
elif "Collar" in selected_strategies:
    st.info("No Collar contracts found with current filters.")

if "IC" in selected_strategies and not results["ic"].empty:
    st.subheader("🦅 Iron Condors (IC)")
    st.success(f"Found {len(results['ic'])} IC contracts")
    st.dataframe(results["ic"], use_container_width=True)
    st.download_button(
        "📥 Download IC CSV",
        results["ic"].to_csv(index=False).encode("utf-8"),
        file_name=f"ic_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
elif "IC" in selected_strategies:
    st.info("No IC contracts found with current filters.")

if "Bull Put" in selected_strategies and not results["bull_put"].empty:
    st.subheader("🐂 Bull Put Spreads")
    st.success(f"Found {len(results['bull_put'])} Bull Put Spread contracts")
    st.dataframe(results["bull_put"], use_container_width=True)
    st.download_button(
        "📥 Download Bull Put CSV",
        results["bull_put"].to_csv(index=False).encode("utf-8"),
        file_name=f"bull_put_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
elif "Bull Put" in selected_strategies:
    st.info("No Bull Put Spread contracts found with current filters.")

if "Bear Call" in selected_strategies and not results["bear_call"].empty:
    st.subheader("🐻 Bear Call Spreads")
    st.success(f"Found {len(results['bear_call'])} Bear Call Spread contracts")
    st.dataframe(results["bear_call"], use_container_width=True)
    st.download_button(
        "📥 Download Bear Call CSV",
        results["bear_call"].to_csv(index=False).encode("utf-8"),
        file_name=f"bear_call_results_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
elif "Bear Call" in selected_strategies:
    st.info("No Bear Call Spread contracts found with current filters.")
