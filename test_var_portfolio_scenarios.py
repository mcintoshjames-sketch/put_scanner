#!/usr/bin/env python3
"""
Comprehensive VaR validation tests using realistic portfolio scenarios.

Tests cover:
1. Mixed portfolios (stocks + options)
2. Hedged positions (long stock + protective put)
3. Spread strategies (bull call spread, iron condor)
4. Multi-underlying portfolios
5. Edge cases (expiring options, deep ITM/OTM)
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from risk_metrics.var_calculator import calculate_portfolio_var
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def generate_historical_prices(symbols, days=252, seed=42):
    """Generate synthetic correlated price histories."""
    np.random.seed(seed)
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    prices = {}
    for i, symbol in enumerate(symbols):
        # Base price
        if symbol == 'SPY':
            base = 450.0
            vol = 0.015  # 1.5% daily vol
        elif symbol == 'NVDA':
            base = 190.0
            vol = 0.025  # 2.5% daily vol
        elif symbol == 'AAPL':
            base = 180.0
            vol = 0.020  # 2.0% daily vol
        elif symbol == 'TSLA':
            base = 250.0
            vol = 0.035  # 3.5% daily vol
        else:
            base = 100.0
            vol = 0.020
        
        # Generate returns with some fat tails
        returns = np.random.normal(0.0, vol, days)
        # Add occasional jumps (10% of days)
        jump_indices = np.random.choice(days, int(0.1 * days), replace=False)
        returns[jump_indices] *= 2.0
        
        # Convert to prices
        prices[symbol] = base * np.cumprod(1 + returns)
    
    return pd.DataFrame(prices, index=dates)


class VaRTestCase:
    """Test case for VaR validation."""
    
    def __init__(self, name, positions, expected_var_range, description):
        self.name = name
        self.positions = positions
        self.expected_var_range = expected_var_range  # (min, max) in dollars
        self.description = description
        self.result = None
        self.passed = False
        self.message = ""


def test_case_1_long_stock():
    """Test: Long stock position - VaR should be linear with volatility."""
    positions = [{
        'symbol': 'SPY',
        'quantity': 100,  # 100 shares long
        'underlying_price': 450.0,
        'position_type': 'STOCK',
        'market_value': 45000.0
    }]
    
    # Portfolio value: $45,000
    # With 1.5% daily vol, 95% VaR ≈ 1.65 * σ * value = 1.65 * 0.015 * 45000 ≈ $1,114
    return VaRTestCase(
        name="Long Stock (SPY)",
        positions=positions,
        expected_var_range=(800, 1500),
        description="100 shares SPY @ $450. Should have VaR ~$1,100 (2.5% of portfolio)"
    )


def test_case_2_long_atm_put():
    """Test: Protective put - max loss should be capped at premium + distance to strike."""
    positions = [{
        'symbol': 'SPY',
        'quantity': 1,  # 1 contract
        'underlying_price': 450.0,
        'option_price': 5.00,  # $5/share = $500 total
        'position_type': 'PUT',
        'market_value': 500.0,
        'strike': 450.0,
        'expiration': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    }]
    
    # ATM put with 30 days, max loss ≈ premium ($500)
    # Realistic VaR with vol moves: $200-$400
    return VaRTestCase(
        name="Long ATM Put",
        positions=positions,
        expected_var_range=(150, 450),
        description="1 SPY 450 put @ $5. VaR should be < full premium ($500)"
    )


def test_case_3_covered_call():
    """Test: Covered call - long stock + short call."""
    positions = [
        {
            'symbol': 'AAPL',
            'quantity': 100,
            'underlying_price': 180.0,
            'position_type': 'STOCK',
            'market_value': 18000.0
        },
        {
            'symbol': 'AAPL',
            'quantity': -1,  # Short 1 call
            'underlying_price': 180.0,
            'option_price': 3.00,
            'position_type': 'CALL',
            'market_value': -300.0,
            'strike': 185.0,
            'expiration': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        }
    ]
    
    # Net portfolio: $17,700 (stock - call premium received)
    # Covered call reduces upside but also reduces downside slightly
    # VaR should be lower than naked stock
    return VaRTestCase(
        name="Covered Call (AAPL)",
        positions=positions,
        expected_var_range=(800, 1400),
        description="100 shares + 1 short 185 call. VaR slightly lower than naked stock"
    )


def test_case_4_protective_put():
    """Test: Hedged position - long stock + long put."""
    positions = [
        {
            'symbol': 'NVDA',
            'quantity': 100,
            'underlying_price': 190.0,
            'position_type': 'STOCK',
            'market_value': 19000.0
        },
        {
            'symbol': 'NVDA',
            'quantity': 1,  # Long put for protection
            'underlying_price': 190.0,
            'option_price': 4.00,
            'position_type': 'PUT',
            'market_value': 400.0,
            'strike': 180.0,  # 10 points below spot
            'expiration': (datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d')
        }
    ]
    
    # Total portfolio: $19,400
    # Max loss is capped at strike distance + put premium = (190-180)*100 + 400 = $1,400
    # VaR should be well below max loss
    return VaRTestCase(
        name="Protective Put (NVDA)",
        positions=positions,
        expected_var_range=(400, 1200),
        description="100 shares + 180 protective put. VaR capped by hedge"
    )


def test_case_5_bull_call_spread():
    """Test: Bull call spread - limited risk defined spread."""
    positions = [
        {
            'symbol': 'SPY',
            'quantity': 1,  # Long lower strike
            'underlying_price': 450.0,
            'option_price': 8.00,
            'position_type': 'CALL',
            'market_value': 800.0,
            'strike': 445.0,
            'expiration': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        },
        {
            'symbol': 'SPY',
            'quantity': -1,  # Short higher strike
            'underlying_price': 450.0,
            'option_price': 3.00,
            'position_type': 'CALL',
            'market_value': -300.0,
            'strike': 455.0,
            'expiration': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        }
    ]
    
    # Net debit: $500 (8 - 3) * 100
    # Max loss: $500 (the debit paid)
    # VaR should be close to max loss since it's a defined risk trade
    return VaRTestCase(
        name="Bull Call Spread (SPY)",
        positions=positions,
        expected_var_range=(200, 500),
        description="445/455 call spread. Max loss = net debit ($500)"
    )


def test_case_6_short_put():
    """Test: Short put - unlimited risk downside."""
    positions = [{
        'symbol': 'TSLA',
        'quantity': -1,  # Short put
        'underlying_price': 250.0,
        'option_price': 6.00,
        'position_type': 'PUT',
        'market_value': -600.0,
        'strike': 245.0,
        'expiration': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    }]
    
    # Short put: received $600 premium
    # Max loss = (strike - 0) * 100 = $24,500 if TSLA goes to zero
    # Realistic VaR with 3.5% vol: ~$500-$1,500
    return VaRTestCase(
        name="Short Put (TSLA)",
        positions=positions,
        expected_var_range=(300, 2000),
        description="1 short TSLA 245 put. Unlimited downside risk"
    )


def test_case_7_multi_stock_portfolio():
    """Test: Diversified stock portfolio - correlation effects."""
    positions = [
        {
            'symbol': 'SPY',
            'quantity': 50,
            'underlying_price': 450.0,
            'position_type': 'STOCK',
            'market_value': 22500.0
        },
        {
            'symbol': 'AAPL',
            'quantity': 100,
            'underlying_price': 180.0,
            'position_type': 'STOCK',
            'market_value': 18000.0
        },
        {
            'symbol': 'NVDA',
            'quantity': 50,
            'underlying_price': 190.0,
            'position_type': 'STOCK',
            'market_value': 9500.0
        }
    ]
    
    # Total portfolio: $50,000
    # Diversification should reduce VaR vs single position
    # Individual VaRs would sum to ~$2,500, portfolio VaR should be ~$1,800-$2,200
    return VaRTestCase(
        name="Multi-Stock Portfolio",
        positions=positions,
        expected_var_range=(1500, 2500),
        description="3 stocks diversified. VaR benefits from correlation < 1"
    )


def test_case_8_expiring_option():
    """Test: Option expiring in 1 day - high gamma/theta."""
    positions = [{
        'symbol': 'SPY',
        'quantity': 1,
        'underlying_price': 450.0,
        'option_price': 0.50,
        'position_type': 'CALL',
        'market_value': 50.0,
        'strike': 452.0,
        'expiration': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    }]
    
    # 1 day to expiration, slightly OTM
    # Max loss: $50 (full premium)
    # Likely VaR: $40-$50 due to rapid time decay
    return VaRTestCase(
        name="Expiring Call (1 DTE)",
        positions=positions,
        expected_var_range=(30, 50),
        description="1 DTE call. Very high theta, VaR ≈ full premium"
    )


def test_case_9_deep_itm_call():
    """Test: Deep ITM call - behaves like stock."""
    positions = [{
        'symbol': 'AAPL',
        'quantity': 1,
        'underlying_price': 180.0,
        'option_price': 35.00,  # Deep ITM
        'position_type': 'CALL',
        'market_value': 3500.0,
        'strike': 145.0,  # $35 ITM
        'expiration': (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
    }]
    
    # Deep ITM call: delta ≈ 1.0, moves like stock
    # Intrinsic: $35, time value: ~$0
    # VaR should be similar to owning 100 shares: ~$300-$600
    return VaRTestCase(
        name="Deep ITM Call",
        positions=positions,
        expected_var_range=(250, 700),
        description="Deep ITM call (delta≈1). VaR similar to stock position"
    )


def test_case_10_mixed_portfolio():
    """Test: Complex portfolio with stocks and options."""
    positions = [
        # Long stock position
        {
            'symbol': 'SPY',
            'quantity': 100,
            'underlying_price': 450.0,
            'position_type': 'STOCK',
            'market_value': 45000.0
        },
        # Protective put on SPY
        {
            'symbol': 'SPY',
            'quantity': 1,
            'underlying_price': 450.0,
            'option_price': 4.00,
            'position_type': 'PUT',
            'market_value': 400.0,
            'strike': 440.0,
            'expiration': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        },
        # Long NVDA call (speculative)
        {
            'symbol': 'NVDA',
            'quantity': 2,
            'underlying_price': 190.0,
            'option_price': 3.00,
            'position_type': 'CALL',
            'market_value': 600.0,
            'strike': 200.0,
            'expiration': (datetime.now() + timedelta(days=45)).strftime('%Y-%m-%d')
        }
    ]
    
    # Total portfolio: ~$46,000
    # SPY position hedged, NVDA calls add speculative exposure
    # VaR should reflect hedged downside on SPY but full loss potential on NVDA calls
    return VaRTestCase(
        name="Mixed Portfolio",
        positions=positions,
        expected_var_range=(800, 1800),
        description="Hedged stock + speculative calls. VaR < unhedged stock"
    )


def run_test_case(test_case, historical_prices):
    """Run a single VaR test case and validate results."""
    print(f"\n{'='*80}")
    print(f"TEST: {test_case.name}")
    print(f"{'='*80}")
    print(f"Description: {test_case.description}")
    print(f"\nPositions:")
    
    portfolio_value = 0.0
    for pos in test_case.positions:
        sign = "+" if pos['quantity'] > 0 else ""
        portfolio_value += abs(pos['market_value'])
        
        if pos['position_type'] == 'STOCK':
            print(f"  {sign}{pos['quantity']} shares {pos['symbol']} @ ${pos['underlying_price']:.2f} = ${pos['market_value']:,.2f}")
        else:
            strike = pos.get('strike', 0)
            expiry = pos.get('expiration', 'N/A')
            print(f"  {sign}{pos['quantity']} {pos['symbol']} {strike:.0f} {pos['position_type']} @ ${pos['option_price']:.2f} = ${pos['market_value']:,.2f}")
    
    print(f"\nTotal Portfolio Value: ${portfolio_value:,.2f}")
    
    try:
        # Calculate VaR
        result = calculate_portfolio_var(
            positions=test_case.positions,
            historical_prices=historical_prices,
            confidence_level=0.95,
            time_horizon_days=1,
            method='historical'
        )
        
        test_case.result = result
        
        # Display results
        print(f"\n{'─'*80}")
        print(f"VaR RESULTS (95% confidence, 1-day horizon)")
        print(f"{'─'*80}")
        print(f"VaR:  ${result.var_amount:,.2f} ({result.var_percent:.2f}% of portfolio)")
        print(f"CVaR: ${result.cvar_amount:,.2f} ({result.cvar_percent:.2f}% of portfolio)")
        
        # Validation
        expected_min, expected_max = test_case.expected_var_range
        print(f"\n{'─'*80}")
        print(f"VALIDATION")
        print(f"{'─'*80}")
        print(f"Expected VaR Range: ${expected_min:,.0f} - ${expected_max:,.0f}")
        print(f"Actual VaR:         ${result.var_amount:,.2f}")
        
        if expected_min <= result.var_amount <= expected_max:
            test_case.passed = True
            test_case.message = "✅ PASS - VaR within expected range"
            print(f"\n{test_case.message}")
        else:
            test_case.passed = False
            if result.var_amount < expected_min:
                test_case.message = f"❌ FAIL - VaR too low (${result.var_amount:.2f} < ${expected_min:.2f})"
            else:
                test_case.message = f"❌ FAIL - VaR too high (${result.var_amount:.2f} > ${expected_max:.2f})"
            print(f"\n{test_case.message}")
        
        # Additional validation checks
        checks_passed = []
        checks_failed = []
        
        # Check 1: CVaR >= VaR
        if result.cvar_amount >= result.var_amount:
            checks_passed.append("CVaR ≥ VaR")
        else:
            checks_failed.append(f"CVaR ({result.cvar_amount:.2f}) < VaR ({result.var_amount:.2f})")
        
        # Check 2: VaR >= 0
        if result.var_amount >= 0:
            checks_passed.append("VaR ≥ 0")
        else:
            checks_failed.append(f"VaR is negative ({result.var_amount:.2f})")
        
        # Check 3: VaR < portfolio value (for long-only or limited risk)
        has_unlimited_risk = any(pos['quantity'] < 0 and pos['position_type'] in ['CALL', 'PUT'] 
                                for pos in test_case.positions)
        if not has_unlimited_risk:
            if result.var_amount <= portfolio_value:
                checks_passed.append("VaR ≤ Portfolio Value")
            else:
                checks_failed.append(f"VaR ({result.var_amount:.2f}) > Portfolio ({portfolio_value:.2f})")
        
        if checks_passed:
            print(f"\nAdditional Checks Passed: {', '.join(checks_passed)}")
        if checks_failed:
            print(f"⚠️  Additional Checks Failed: {', '.join(checks_failed)}")
            test_case.passed = False
            
    except Exception as e:
        test_case.passed = False
        test_case.message = f"❌ ERROR - {str(e)}"
        print(f"\n{test_case.message}")
        import traceback
        print(traceback.format_exc())
    
    return test_case


def main():
    """Run all VaR validation tests."""
    print("="*80)
    print("VaR CALCULATOR - COMPREHENSIVE VALIDATION SUITE")
    print("="*80)
    print("\nGenerating synthetic historical price data...")
    
    # Generate historical prices for all symbols
    symbols = ['SPY', 'AAPL', 'NVDA', 'TSLA']
    historical_prices = generate_historical_prices(symbols, days=252)
    
    print(f"Generated {len(historical_prices)} days of price history for {len(symbols)} symbols")
    print(f"Date range: {historical_prices.index[0].date()} to {historical_prices.index[-1].date()}")
    
    # Define all test cases
    test_cases = [
        test_case_1_long_stock(),
        test_case_2_long_atm_put(),
        test_case_3_covered_call(),
        test_case_4_protective_put(),
        test_case_5_bull_call_spread(),
        test_case_6_short_put(),
        test_case_7_multi_stock_portfolio(),
        test_case_8_expiring_option(),
        test_case_9_deep_itm_call(),
        test_case_10_mixed_portfolio(),
    ]
    
    # Run all tests
    results = []
    for test_case in test_cases:
        result = run_test_case(test_case, historical_prices)
        results.append(result)
    
    # Summary
    print(f"\n\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    
    print(f"\nTotal Tests: {len(results)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    print(f"Success Rate: {passed/len(results)*100:.1f}%")
    
    print(f"\n{'─'*80}")
    print("DETAILED RESULTS")
    print(f"{'─'*80}")
    
    for i, result in enumerate(results, 1):
        status = "✅ PASS" if result.passed else "❌ FAIL"
        var_str = f"${result.result.var_amount:,.2f}" if result.result else "N/A"
        print(f"{i:2d}. {status} - {result.name:30s} VaR: {var_str}")
    
    print("\n" + "="*80)
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    exit(main())
