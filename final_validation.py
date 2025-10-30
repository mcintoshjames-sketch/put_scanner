import sys
sys.path.insert(0, '/workspaces/put_scanner')
from strategy_lab import mc_pnl
import numpy as np

print('='*60)
print('IRON CONDOR MONTE CARLO - PRODUCTION VALIDATION')
print('='*60)

# Test Case: Well-structured Iron Condor on SPY
# SPY @ $450, 30 days, 20% IV
# Strikes at ~1 std dev (16% breach probability per wing)
params = {
    'S0': 450.0,
    'days': 30,
    'iv': 0.20,
    'put_short_strike': 425.0,   # $25 below (0.96 std dev)
    'put_long_strike': 415.0,    # $10 spread
    'call_short_strike': 475.0,  # $25 above (0.96 std dev)
    'call_long_strike': 485.0,   # $10 spread
    'net_credit': 2.00           # 20% of spread width
}

print(f'\nTest Parameters:')
print(f'  Underlying: ${params["S0"]:.0f}')
print(f'  Put Spread: {params["put_short_strike"]:.0f}/{params["put_long_strike"]:.0f}')
print(f'  Call Spread: {params["call_short_strike"]:.0f}/{params["call_long_strike"]:.0f}')
print(f'  Net Credit: ${params["net_credit"]:.2f}/share (${params["net_credit"]*100:.0f}/contract)')
print(f'  Days: {params["days"]}')
print(f'  IV: {params["iv"]*100:.0f}%')

# Run Monte Carlo
mc = mc_pnl('IRON_CONDOR', params, n_paths=20000, mu=0.0, seed=42)

# Calculate theoretical values
spread_width = 10.0
max_profit = params['net_credit'] * 100
max_loss = (spread_width - params['net_credit']) * 100
capital = max_loss

print(f'\nTheoretical Values:')
print(f'  Max Profit: ${max_profit:.0f}/contract')
print(f'  Max Loss: ${max_loss:.0f}/contract')
print(f'  Capital Required: ${capital:.0f}/contract')
print(f'  Max ROI: {(max_profit/capital)*100:.1f}%')

print(f'\nMonte Carlo Results ({mc["paths"]} paths):')
print(f'  Expected P&L: ${mc["pnl_expected"]:.2f}/contract')
print(f'  P&L Std Dev: ${mc["pnl_std"]:.2f}')
print(f'  P&L Range (P5-P95): ${mc["pnl_p5"]:.0f} to ${mc["pnl_p95"]:.0f}')
print(f'  Median P&L: ${mc["pnl_p50"]:.0f}')
print(f'  ROI (annualized): {mc["roi_ann_expected"]*100:.1f}%')
print(f'  Sharpe Ratio: {mc["sharpe"]:.2f}')

# Win rate analysis
S_T = mc['S_T']
winners = np.sum((S_T >= params['put_short_strike']) & (S_T <= params['call_short_strike']))
win_rate = winners / len(S_T) * 100

print(f'\nWin Rate Analysis:')
print(f'  Paths in profit zone: {winners:,} / {len(S_T):,} ({win_rate:.1f}%)')
print(f'  Put side breaches: {np.sum(S_T < params["put_long_strike"]):,} paths')
print(f'  Call side breaches: {np.sum(S_T > params["call_long_strike"]):,} paths')

# Validation
pnl_min = np.min(mc['pnl_paths'])
pnl_max = np.max(mc['pnl_paths'])
bounds_ok = (pnl_min >= -max_loss - 0.01) and (pnl_max <= max_profit + 0.01)
capital_ok = abs(mc['capital_per_share'] - (max_loss/100)) < 0.01
win_rate_ok = win_rate > 50

print(f'\nValidation:')
status_bounds = 'PASS' if bounds_ok else 'FAIL'
status_capital = 'PASS' if capital_ok else 'FAIL'
status_winrate = 'PASS' if win_rate_ok else 'FAIL'
print(f'  ✓ P&L bounds [{pnl_min:.0f}, {pnl_max:.0f}]: {status_bounds}')
print(f'  ✓ Capital calculation: {status_capital}')
print(f'  ✓ Win rate > 50%: {status_winrate}')

all_pass = bounds_ok and capital_ok and win_rate_ok
print('\n' + '='*60)
if all_pass:
    print('RESULT: ✅ IRON CONDOR MC IMPLEMENTATION VALIDATED')
else:
    print('RESULT: ⚠️ SOME TESTS FAILED')
print('='*60)
