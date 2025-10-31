#!/usr/bin/env python3
import sys
sys.path.insert(0, '/workspaces/put_scanner')
from strategy_lab import prescreen_tickers

test_tickers = ['AAPL', 'MSFT', 'SPY', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA']
print(f"Testing pre-screen with {len(test_tickers)} tickers...")
results = prescreen_tickers(test_tickers, min_hv=10.0)

print(f'\n✅ Passed pre-screen: {len(results)}/{len(test_tickers)}')
if not results.empty:
    print(f'\nResults:')
    print(results[['Ticker', 'Price', 'HV_30d%', 'IV%', 'IV/HV', 'Quality_Score']].to_string(index=False))
else:
    print('No tickers passed')
