import sys
sys.path.insert(0, '/workspaces/put_scanner')
from strategy_lab import mc_pnl
import numpy as np

# More realistic Iron Condor: wider wings (1 std dev = $26 for 30 days @ 20% IV)
# Use $25 wide wings (roughly 1 std dev)
params_realistic = {
    "S0": 450.0,
    "days": 30,
    "iv": 0.20,
    "put_short_strike": 430.0,   # $20 below (0.78 std dev)
    "put_long_strike": 420.0,    # $10 wide spread
    "call_short_strike": 470.0,  # $20 above (0.78 std dev)
    "call_long_strike": 480.0,   # $10 wide spread
    "net_credit": 2.50            # Realistic credit for wider wings
}

print("=== REALISTIC IRON CONDOR (Wider Wings) ===")
print(f"Strikes: {params_realistic['put_long_strike']}/{params_realistic['put_short_strike']} puts, "
      f"{params_realistic['call_short_strike']}/{params_realistic['call_long_strike']} calls")
print(f"Net Credit: ${params_realistic['net_credit']:.2f}")

mc = mc_pnl("IRON_CONDOR", params_realistic, n_paths=10000, mu=0.0, seed=42)

# Calculate theoretical values
put_width = params_realistic['put_short_strike'] - params_realistic['put_long_strike']
call_width = params_realistic['call_long_strike'] - params_realistic['call_short_strike']
max_loss = max(put_width, call_width) - params_realistic['net_credit']
max_profit = params_realistic['net_credit']
capital = max_loss

print(f"\nTheoretical Values:")
print(f"  Max Profit: ${max_profit:.2f} per share (${max_profit*100:.2f} per contract)")
print(f"  Max Loss: ${-max_loss:.2f} per share (${-max_loss*100:.2f} per contract)")
print(f"  Capital: ${capital:.2f} per share (${capital*100:.2f} per contract)")

print(f"\nMonte Carlo Results:")
print(f"  Expected P&L: ${mc['pnl_expected']:.2f} per contract")
print(f"  P&L Std Dev: ${mc['pnl_std']:.2f}")
print(f"  P&L P5/P50/P95: ${mc['pnl_p5']:.2f} / ${mc['pnl_p50']:.2f} / ${mc['pnl_p95']:.2f}")
print(f"  ROI Ann (Expected): {mc['roi_ann_expected']*100:.1f}%")
print(f"  Sharpe Ratio: {mc['sharpe']:.3f}")

# Terminal price stats
S_T = mc['S_T']
print(f"\nTerminal Price Statistics:")
print(f"  Mean: ${np.mean(S_T):.2f}, Std Dev: ${np.std(S_T):.2f}")
print(f"  P5/P95: ${np.percentile(S_T, 5):.2f} / ${np.percentile(S_T, 95):.2f}")

# Price distribution
below_put_long = np.sum(S_T <= params_realistic['put_long_strike'])
between_put_strikes = np.sum((S_T > params_realistic['put_long_strike']) & (S_T < params_realistic['put_short_strike']))
in_profit_zone = np.sum((S_T >= params_realistic['put_short_strike']) & (S_T <= params_realistic['call_short_strike']))
between_call_strikes = np.sum((S_T > params_realistic['call_short_strike']) & (S_T < params_realistic['call_long_strike']))
above_call_long = np.sum(S_T >= params_realistic['call_long_strike'])

print(f"\nPrice Distribution:")
print(f"  Below Put Long (${params_realistic['put_long_strike']}): {below_put_long} paths ({below_put_long/100:.1f}%) - MAX LOSS")
print(f"  Between Put Strikes: {between_put_strikes} paths ({between_put_strikes/100:.1f}%) - PARTIAL LOSS")
print(f"  In Profit Zone (${params_realistic['put_short_strike']}-${params_realistic['call_short_strike']}): {in_profit_zone} paths ({in_profit_zone/100:.1f}%) - MAX PROFIT")
print(f"  Between Call Strikes: {between_call_strikes} paths ({between_call_strikes/100:.1f}%) - PARTIAL LOSS")
print(f"  Above Call Long (${params_realistic['call_long_strike']}): {above_call_long} paths ({above_call_long/100:.1f}%) - MAX LOSS")

# Validation
max_loss_contract = max_loss * 100
max_profit_contract = max_profit * 100
pnl_paths = mc['pnl_paths']
min_pnl = np.min(pnl_paths)
max_pnl = np.max(pnl_paths)

print(f"\n✅ VALIDATION:")
print(f"  Bounds check: [{min_pnl:.2f}, {max_pnl:.2f}] within [{-max_loss_contract:.2f}, {max_profit_contract:.2f}]: {'PASS' if (min_pnl >= -max_loss_contract - 0.01 and max_pnl <= max_profit_contract + 0.01) else 'FAIL'}")
print(f"  Expected P&L positive: {mc['pnl_expected']:.2f} > 0: {'PASS' if mc['pnl_expected'] > 0 else 'FAIL'}")
print(f"  Capital calc: ${mc['capital_per_share']:.2f} == ${capital:.2f}: {'PASS' if abs(mc['capital_per_share'] - capital) < 0.01 else 'FAIL'}")
