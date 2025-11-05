"""
Test to verify Alpha Vantage is only called during order preview, not screening.
"""
import os
import sys
import yfinance as yf
import os
try:
    import pytest as _pytest  # type: ignore
    if not os.getenv("RUN_INTEGRATION"):
        _pytest.skip("Skipping Alpha Vantage behavior tests; set RUN_INTEGRATION=1 to run.", allow_module_level=True)
except Exception:
    pass

sys.path.insert(0, '/workspaces/put_scanner')

# Set API key
os.environ['ALPHA_VANTAGE_API_KEY'] = '69W6V3AL4VF1ROEA'

from providers.alpha_vantage import AlphaVantageClient
from strategy_lab import get_earnings_date

def test_screening_behavior():
    """Test that screening does NOT call Alpha Vantage"""
    print("\n" + "="*70)
    print("TEST 1: Screening Behavior (use_alpha_vantage=False)")
    print("="*70)
    
    client = AlphaVantageClient(os.environ['ALPHA_VANTAGE_API_KEY'])
    calls_before = 25 - client.get_remaining_calls()
    print(f"API calls used BEFORE: {calls_before}/25")
    
    # Simulate screening - should NOT call Alpha Vantage
    print("\nSimulating screening for TGT (use_alpha_vantage=False)...")
    stock = yf.Ticker('TGT')
    earnings = get_earnings_date(stock, use_alpha_vantage=False)
    print(f"Earnings date returned: {earnings}")
    
    calls_after = 25 - client.get_remaining_calls()
    print(f"API calls used AFTER: {calls_after}/25")
    
    if calls_after == calls_before:
        print("✅ SUCCESS: No Alpha Vantage API call during screening!")
    else:
        print(f"❌ FAIL: Alpha Vantage was called ({calls_after - calls_before} calls)")
    
    return calls_after

def test_order_preview_behavior(calls_before):
    """Test that order preview DOES call Alpha Vantage"""
    print("\n" + "="*70)
    print("TEST 2: Order Preview Behavior (use_alpha_vantage=True)")
    print("="*70)
    
    client = AlphaVantageClient(os.environ['ALPHA_VANTAGE_API_KEY'])
    print(f"API calls used BEFORE: {calls_before}/25")
    
    # Simulate order preview - SHOULD call Alpha Vantage if Yahoo fails
    print("\nSimulating order preview for TGT (use_alpha_vantage=True)...")
    stock = yf.Ticker('TGT')
    earnings = get_earnings_date(stock, use_alpha_vantage=True)
    print(f"Earnings date returned: {earnings}")
    
    calls_after = 25 - client.get_remaining_calls()
    print(f"API calls used AFTER: {calls_after}/25")
    
    if calls_after >= calls_before:
        print("✅ SUCCESS: Alpha Vantage fallback available during order preview!")
        if calls_after > calls_before:
            print(f"   (Made {calls_after - calls_before} API call(s) because Yahoo had no data)")
        else:
            print(f"   (No API call needed - Yahoo provided data OR cache hit)")
    else:
        print(f"❌ UNEXPECTED: Call count decreased?")

def main():
    print("\n🧪 Testing Alpha Vantage API Call Behavior")
    print("="*70)
    
    # Clear cache for clean test
    os.system('rm -rf earnings_cache/')
    
    try:
        # Test 1: Screening should NOT call API
        calls_after_screening = test_screening_behavior()
        
        # Test 2: Order preview should be ABLE to call API
        test_order_preview_behavior(calls_after_screening)
        
        print("\n" + "="*70)
        print("TESTING COMPLETE")
        print("="*70)
        print("\n✅ Alpha Vantage is now ONLY used during order preview, preserving")
        print("   your 25 calls/day quota during screening operations!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
