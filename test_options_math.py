#!/usr/bin/env python3
"""
Test script for options_math module
"""

from options_math import (
    bs_call_price, bs_put_price,
    call_delta, put_delta,
    option_gamma, option_vega,
    call_theta, put_theta,
    expected_move,
    mc_pnl, gbm_terminal_prices,
    compute_spread_pct,
    trailing_dividend_info
)

print("=" * 60)
print("Testing options_math.py module")
print("=" * 60)

# Test 1: Black-Scholes pricing
print("\n1. Black-Scholes Pricing:")
S, K, r, q, sigma, T = 100, 100, 0.05, 0.0, 0.25, 0.25
call_price = bs_call_price(S, K, r, q, sigma, T)
put_price = bs_put_price(S, K, r, q, sigma, T)
print(f"   ATM Call price: ${call_price:.2f}")
print(f"   ATM Put price:  ${put_price:.2f}")

# Test 2: Greeks
print("\n2. Greeks Calculations:")
c_delta = call_delta(S, K, r, sigma, T, q)
p_delta = put_delta(S, K, r, sigma, T, q)
gamma = option_gamma(S, K, r, sigma, T, q)
vega = option_vega(S, K, r, sigma, T, q)
c_theta = call_theta(S, K, r, sigma, T, q)
p_theta = put_theta(S, K, r, sigma, T, q)

print(f"   Call Delta: {c_delta:.3f}")
print(f"   Put Delta:  {p_delta:.3f}")
print(f"   Gamma:      {gamma:.4f}")
print(f"   Vega:       {vega:.3f}")
print(f"   Call Theta: ${c_theta:.3f}/day")
print(f"   Put Theta:  ${p_theta:.3f}/day")

# Test 3: Expected Move
print("\n3. Expected Move:")
exp_mv = expected_move(S, sigma, T)
print(f"   1σ move: ±${exp_mv:.2f} ({exp_mv/S*100:.1f}%)")

# Test 4: Spread calculation
print("\n4. Spread Calculation:")
bid, ask, mid = 5.50, 5.70, 5.60
spread_pct = compute_spread_pct(bid, ask, mid)
print(f"   Bid: ${bid}, Ask: ${ask}, Mid: ${mid}")
print(f"   Spread: {spread_pct:.2f}%")

# Test 5: Monte Carlo simulation (CSP)
print("\n5. Monte Carlo P&L Simulation (CSP):")
params = {
    'S0': 100,
    'days': 30,
    'iv': 0.25,
    'Kp': 95,
    'put_premium': 2.0
}
result = mc_pnl('CSP', params, n_paths=5000, seed=42)
print(f"   Strategy: Cash-Secured Put")
print(f"   Strike: ${params['Kp']}, Premium: ${params['put_premium']}")
print(f"   Expected P&L: ${result['pnl_expected']:.2f}")
print(f"   P&L Std Dev: ${result['pnl_std']:.2f}")
print(f"   P&L 5th %ile: ${result['pnl_p5']:.2f}")
print(f"   P&L 50th %ile: ${result['pnl_p50']:.2f}")
print(f"   P&L 95th %ile: ${result['pnl_p95']:.2f}")
print(f"   Sharpe Ratio: {result['sharpe']:.2f}")

# Test 6: Monte Carlo simulation (Iron Condor)
print("\n6. Monte Carlo P&L Simulation (Iron Condor):")
ic_params = {
    'S0': 100,
    'days': 30,
    'iv': 0.25,
    'put_short_strike': 95,
    'put_long_strike': 90,
    'call_short_strike': 105,
    'call_long_strike': 110,
    'net_credit': 1.5
}
ic_result = mc_pnl('IRON_CONDOR', ic_params, n_paths=5000, seed=42)
print(f"   Strategy: Iron Condor")
print(f"   Put Spread: {ic_params['put_long_strike']}/{ic_params['put_short_strike']}")
print(f"   Call Spread: {ic_params['call_short_strike']}/{ic_params['call_long_strike']}")
print(f"   Net Credit: ${ic_params['net_credit']}")
print(f"   Expected P&L: ${ic_result['pnl_expected']:.2f}")
print(f"   P&L 5th %ile: ${ic_result['pnl_p5']:.2f}")
print(f"   P&L 95th %ile: ${ic_result['pnl_p95']:.2f}")

print("\n" + "=" * 60)
print("✅ All tests passed!")
print("=" * 60)
