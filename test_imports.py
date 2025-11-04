#!/usr/bin/env python3
"""Test imports to verify no circular dependency"""

import sys
sys.path.insert(0, '/workspaces/put_scanner')

try:
    from strategy_analysis import (
        analyze_csp,
        analyze_cc,
        analyze_collar,
        analyze_iron_condor,
        analyze_bull_put_spread,
        analyze_bear_call_spread,
        prescreen_tickers
    )
    print("✅ All imports successful!")
    print(f"   - analyze_csp: {analyze_csp}")
    print(f"   - analyze_cc: {analyze_cc}")
    print(f"   - analyze_collar: {analyze_collar}")
    print(f"   - analyze_iron_condor: {analyze_iron_condor}")
    print(f"   - analyze_bull_put_spread: {analyze_bull_put_spread}")
    print(f"   - analyze_bear_call_spread: {analyze_bear_call_spread}")
    print(f"   - prescreen_tickers: {prescreen_tickers}")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
