"""
Test to verify that Volume data is being captured and displayed in Best-Practice Fit.
"""

import sys
import pandas as pd
from strategy_lab import analyze_bear_call_spread, evaluate_fit, best_practices

def test_bear_call_spread_volume():
    """Test that Bear Call Spread captures volume data."""
    print("=" * 80)
    print("TEST: Bear Call Spread Volume Capture")
    print("=" * 80)
    
    # Run a scan for SPY (highly liquid)
    ticker = "SPY"
    print(f"\nScanning {ticker} for Bear Call Spread opportunities...")
    
    df = analyze_bear_call_spread(
        ticker,
        min_days=7,
        days_limit=60,
        min_oi=100,
        max_spread=15.0,
        min_roi=0.05,
        min_cushion=0.5,
        min_poew=0.60,
        earn_window=7,
        risk_free=0.045,
        spread_width=5.0,
        target_delta_short=0.20,
        bill_yield=0.0
    )
    
    if df.empty:
        print(f"❌ FAIL: No results returned for {ticker}")
        return False
    
    print(f"✅ Found {len(df)} opportunities")
    
    # Check if Volume column exists
    if "Volume" not in df.columns:
        print("❌ FAIL: 'Volume' column not found in results")
        return False
    
    print("✅ 'Volume' column exists in results")
    
    # Check first row
    row = df.iloc[0]
    volume = row.get("Volume", None)
    oi = row.get("OI", None)
    
    print(f"\nFirst opportunity:")
    print(f"  Ticker: {row.get('Ticker')}")
    print(f"  Exp: {row.get('Exp')}")
    print(f"  SellStrike: {row.get('SellStrike')}")
    print(f"  BuyStrike: {row.get('BuyStrike')}")
    print(f"  NetCredit: ${row.get('NetCredit')}")
    print(f"  OI: {oi}")
    print(f"  Volume: {volume}")
    
    if pd.isna(volume) or volume == 0:
        print("⚠️  WARNING: Volume is NaN or zero")
        print("    This may indicate volume data is not available from yfinance")
    else:
        print(f"✅ Volume data captured: {volume}")
        if oi and oi > 0:
            vol_oi_ratio = volume / oi
            print(f"✅ Volume/OI ratio: {vol_oi_ratio:.2f}")
    
    # Test Best-Practice Fit
    print("\n" + "-" * 80)
    print("Testing Best-Practice Fit evaluation...")
    print("-" * 80)
    
    thresholds = {
        "min_oi": 100,
        "max_spread": 15.0,
        "min_cushion": 0.5,
    }
    
    summary_df, flags = evaluate_fit(
        strategy="BEAR_CALL_SPREAD",
        row=row,
        thresholds=thresholds,
        risk_free=0.045,
        div_y=0.0,
        bill_yield=0.0
    )
    
    print("\nBest-Practice Fit Results:")
    print(summary_df.to_string(index=False))
    
    # Check if Volume/OI ratio is in the summary
    volume_checks = summary_df[summary_df.iloc[:, 0].str.contains("Volume/OI", na=False)]
    
    if volume_checks.empty:
        print("\n❌ FAIL: Volume/OI ratio check not found in Best-Practice Fit")
        return False
    
    volume_status = volume_checks.iloc[0, 1]  # Status column (✅/⚠️/❌)
    volume_note = volume_checks.iloc[0, 2]    # Notes column
    
    print(f"\n📊 Volume/OI ratio status: {volume_status}")
    print(f"   Note: {volume_note}")
    
    if "volume data missing" in volume_note.lower():
        print("❌ FAIL: Volume data is marked as missing in Best-Practice Fit")
        return False
    
    if "n/a" in volume_note.lower():
        print("⚠️  WARNING: Volume data shows as 'n/a' - this shouldn't happen for liquid stocks")
        print("    Possible causes:")
        print("    1. yfinance API not returning volume data")
        print("    2. After-hours scan when volume resets")
        print("    3. Data provider issue")
        return False
    
    print("✅ PASS: Volume/OI ratio is being calculated and displayed correctly")
    return True


def test_csp_volume():
    """Test that CSP also captures volume data."""
    print("\n" + "=" * 80)
    print("TEST: CSP Volume Capture (for comparison)")
    print("=" * 80)
    
    from strategy_lab import analyze_csp
    
    ticker = "SPY"
    print(f"\nScanning {ticker} for CSP opportunities...")
    
    df, _ = analyze_csp(
        ticker,
        min_days=7,
        days_limit=60,
        min_otm=5.0,
        min_oi=100,
        max_spread=15.0,
        min_roi=0.05,
        min_cushion=0.5,
        min_poew=0.60,
        earn_window=7,
        risk_free=0.045,
        bill_yield=0.0
    )
    
    if df.empty:
        print(f"❌ No CSP results for {ticker}")
        return False
    
    print(f"✅ Found {len(df)} CSP opportunities")
    
    if "Volume" not in df.columns:
        print("❌ FAIL: 'Volume' column not found in CSP results")
        return False
    
    row = df.iloc[0]
    volume = row.get("Volume", None)
    oi = row.get("OI", None)
    
    print(f"\nFirst CSP opportunity:")
    print(f"  Strike: {row.get('Strike')}")
    print(f"  Premium: ${row.get('Premium')}")
    print(f"  OI: {oi}")
    print(f"  Volume: {volume}")
    
    if pd.isna(volume) or volume == 0:
        print("⚠️  WARNING: Volume is NaN or zero for CSP")
    else:
        print(f"✅ CSP Volume data captured: {volume}")
        if oi and oi > 0:
            vol_oi_ratio = volume / oi
            print(f"✅ Volume/OI ratio: {vol_oi_ratio:.2f}")
    
    return True


if __name__ == "__main__":
    print("\n🔍 Volume Data Capture Test Suite")
    print("=" * 80)
    print("Testing that volume data is captured from option chains")
    print("and properly displayed in Best-Practice Fit evaluations.")
    print("=" * 80)
    
    results = []
    
    # Test Bear Call Spread (the reported issue)
    try:
        results.append(("Bear Call Spread", test_bear_call_spread_volume()))
    except Exception as e:
        print(f"\n❌ ERROR in Bear Call Spread test: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Bear Call Spread", False))
    
    # Test CSP for comparison
    try:
        results.append(("CSP", test_csp_volume()))
    except Exception as e:
        print(f"\n❌ ERROR in CSP test: {e}")
        import traceback
        traceback.print_exc()
        results.append(("CSP", False))
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("Volume data is being captured and displayed correctly.")
        sys.exit(0)
    else:
        print("\n⚠️  SOME TESTS FAILED")
        print("Review output above for details.")
        sys.exit(1)
