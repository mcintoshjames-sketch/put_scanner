"""
Quick test of Iron Condor implementation
"""
import sys
sys.path.insert(0, '/workspaces/put_scanner')

from strategy_lab import analyze_iron_condor
import pandas as pd

def test_iron_condor_basic():
    """Test Iron Condor analyzer with SPY"""
    print("\n" + "="*60)
    print("Testing Iron Condor Analyzer")
    print("="*60)
    
    # Test parameters
    ticker = "SPY"
    print(f"\nScanning {ticker} for Iron Condor opportunities...")
    
    try:
        df = analyze_iron_condor(
            ticker,
            min_days=30,
            days_limit=45,
            min_oi=100,
            max_spread=15.0,
            min_roi=0.10,  # 10% annualized
            min_cushion=0.3,  # 0.3 sigma minimum
            earn_window=7,
            risk_free=0.05,
            spread_width_put=5.0,
            spread_width_call=5.0,
            target_delta_short=0.16,
            bill_yield=0.05
        )
        
        if df.empty:
            print("❌ No Iron Condor opportunities found")
            print("   This could be due to:")
            print("   - No options chains available")
            print("   - Filters too strict")
            print("   - Market hours / data availability")
            return False
        
        print(f"✅ Found {len(df)} Iron Condor opportunities\n")
        
        # Display key columns
        display_cols = [
            "Ticker", "Exp", "Days", 
            "PutShortStrike", "PutLongStrike", "PutSpreadCredit",
            "CallShortStrike", "CallLongStrike", "CallSpreadCredit",
            "NetCredit", "MaxLoss", "ROI%_ann", 
            "PutCushionσ", "CallCushionσ", "Score"
        ]
        
        available_cols = [c for c in display_cols if c in df.columns]
        print(df[available_cols].head(3).to_string(index=False))
        
        # Validate structure
        print("\n" + "-"*60)
        print("Validation Checks:")
        print("-"*60)
        
        row = df.iloc[0]
        
        # Check 4-leg structure
        assert row["PutLongStrike"] < row["PutShortStrike"], "❌ Put spread inverted"
        print("✅ Put spread: Buy ${:.0f} / Sell ${:.0f}".format(
            row["PutLongStrike"], row["PutShortStrike"]))
        
        assert row["CallShortStrike"] < row["CallLongStrike"], "❌ Call spread inverted"
        print("✅ Call spread: Sell ${:.0f} / Buy ${:.0f}".format(
            row["CallShortStrike"], row["CallLongStrike"]))
        
        # Check net credit > 0
        assert row["NetCredit"] > 0, "❌ Net credit is negative"
        print("✅ Net credit: ${:.2f}".format(row["NetCredit"]))
        
        # Check max loss calculation
        put_width = row["PutShortStrike"] - row["PutLongStrike"]
        call_width = row["CallLongStrike"] - row["CallShortStrike"]
        expected_max_loss = max(put_width, call_width) - row["NetCredit"]
        assert abs(row["MaxLoss"] - expected_max_loss) < 0.01, "❌ Max loss calculation error"
        print("✅ Max loss: ${:.2f} (wing width ${:.0f} - credit ${:.2f})".format(
            row["MaxLoss"], max(put_width, call_width), row["NetCredit"]))
        
        # Check ROI calculation
        roi_cycle = row["NetCredit"] / row["MaxLoss"] if row["MaxLoss"] > 0 else 0
        expected_roi_ann = roi_cycle * (365.0 / row["Days"]) * 100.0
        assert abs(row["ROI%_ann"] - expected_roi_ann) < 1.0, "❌ ROI calculation error"
        print("✅ ROI: {:.1f}% annualized".format(row["ROI%_ann"]))
        
        # Check breakevens
        if "BreakevenLower" in df.columns and "BreakevenUpper" in df.columns:
            expected_be_lower = row["PutShortStrike"] - row["NetCredit"]
            expected_be_upper = row["CallShortStrike"] + row["NetCredit"]
            assert abs(row["BreakevenLower"] - expected_be_lower) < 0.01, "❌ Lower breakeven error"
            assert abs(row["BreakevenUpper"] - expected_be_upper) < 0.01, "❌ Upper breakeven error"
            print("✅ Breakevens: ${:.2f} - ${:.2f} (range: ${:.2f})".format(
                row["BreakevenLower"], row["BreakevenUpper"], 
                row["BreakevenUpper"] - row["BreakevenLower"]))
        
        # Check deltas are reasonable
        if "PutShortΔ" in df.columns:
            assert -0.5 < row["PutShortΔ"] < 0, "❌ Put delta out of range"
            print("✅ Put short Δ: {:.3f}".format(row["PutShortΔ"]))
        
        if "CallShortΔ" in df.columns:
            assert 0 < row["CallShortΔ"] < 0.5, "❌ Call delta out of range"
            print("✅ Call short Δ: {:.3f}".format(row["CallShortΔ"]))
        
        # Check cushions
        if row["PutCushionσ"] == row["PutCushionσ"]:  # not NaN
            print("✅ Put cushion: {:.2f}σ".format(row["PutCushionσ"]))
        if row["CallCushionσ"] == row["CallCushionσ"]:  # not NaN
            print("✅ Call cushion: {:.2f}σ".format(row["CallCushionσ"]))
        
        # Check balance
        if (row["PutCushionσ"] == row["PutCushionσ"] and 
            row["CallCushionσ"] == row["CallCushionσ"]):
            balance_ratio = min(row["PutCushionσ"], row["CallCushionσ"]) / max(row["PutCushionσ"], row["CallCushionσ"])
            print("✅ Wing balance: {:.1f}% (1.0 = perfect balance)".format(balance_ratio))
        
        print("\n" + "="*60)
        print("✅ All validation checks passed!")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\n❌ Error during test: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_iron_condor_basic()
    sys.exit(0 if success else 1)
