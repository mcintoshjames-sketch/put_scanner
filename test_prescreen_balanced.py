#!/usr/bin/env python3
import sys
sys.path.insert(0, '/workspaces/put_scanner')
from strategy_lab import prescreen_tickers

# Test with more tickers
test_tickers = ['AAPL', 'MSFT', 'SPY', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 
                'JPM', 'V', 'WMT', 'MA', 'PG', 'HD', 'BAC', 'XOM', 'JNJ', 'COST',
                'ABBV', 'KO', 'PEP', 'MRK', 'CVX', 'AVGO', 'LLY', 'CSCO', 'ACN',
                'TMO', 'ABT', 'ADBE', 'NFLX', 'CRM', 'NKE', 'DIS', 'INTC']

print(f"Testing pre-screen with {len(test_tickers)} tickers...")
print(f"\nFilter parameters:")
print(f"  Min HV: 18%")
print(f"  Max HV: 70%")
print(f"  Min volume: 1,500,000")
print(f"  Min option volume: 150")
print(f"  Max spread: 30%")

results = prescreen_tickers(test_tickers, min_hv=18.0, max_hv=70.0, 
                           min_avg_volume=1_500_000, min_option_volume=150)

print(f'\n✅ Passed pre-screen: {len(results)}/{len(test_tickers)} ({len(results)/len(test_tickers)*100:.1f}%)')

if not results.empty:
    print(f'\nTop 10 by Quality Score:')
    top_10 = results.head(10)
    print(top_10[['Ticker', 'Price', 'HV_30d%', 'IV%', 'IV/HV', 'Spread%', 'Quality_Score']].to_string(index=False))
    
    print(f'\n\nAll passing tickers:')
    print(', '.join(results['Ticker'].tolist()))
    
    # Show HV distribution
    print(f'\n\nHV Distribution:')
    print(f'  Min HV: {results["HV_30d%"].min():.1f}%')
    print(f'  Max HV: {results["HV_30d%"].max():.1f}%')
    print(f'  Avg HV: {results["HV_30d%"].mean():.1f}%')
    print(f'  Median HV: {results["HV_30d%"].median():.1f}%')
else:
    print('\n❌ No tickers passed')
