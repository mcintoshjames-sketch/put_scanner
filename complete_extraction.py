#!/usr/bin/env python3
"""Helper script to complete the strategy_analysis.py extraction"""

# Read strategy_lab.py and extract remaining functions
with open('/workspaces/put_scanner/strategy_lab.py', 'r') as f:
    lines = f.readlines()

# Extract Bull Put Spread (lines 1921-2284, 0-indexed: 1920-2283)
bull_put_lines = lines[1920:2284]

# Extract Bear Call Spread (lines 2287-2647, 0-indexed: 2286-2646)
bear_call_lines = lines[2286:2647]

# Extract prescreen_tickers (lines 3699-4082, 0-indexed: 3698-4081)
prescreen_lines = lines[3698:4082]

# Append to strategy_analysis.py
with open('/workspaces/put_scanner/strategy_analysis.py', 'a') as f:
    f.write('\n\n')
    f.writelines(bull_put_lines)
    f.write('\n\n')
    f.writelines(bear_call_lines)
    f.write('\n\n')
    f.writelines(prescreen_lines)

print("✅ Extraction complete!")
print(f"  - Added Bull Put Spread analyzer ({len(bull_put_lines)} lines)")
print(f"  - Added Bear Call Spread analyzer ({len(bear_call_lines)} lines)")  
print(f"  - Added prescreen_tickers function ({len(prescreen_lines)} lines)")
print(f"  - Total lines added: {len(bull_put_lines) + len(bear_call_lines) + len(prescreen_lines)}")
