#!/usr/bin/env python3
"""Remove analyzer functions while keeping helper functions"""

# Read the file
with open('/workspaces/put_scanner/strategy_lab.py', 'r') as f:
    lines = f.readlines()

# After adding 11 lines of imports, line numbers shifted by +11:
# Original line 815 -> now 826 (analyze_csp starts)
# Original line 2652 -> now 2663 (best_practices starts)
# Original line 3699 -> now 3710 (prescreen_tickers starts)
# Original line 4095 -> now 4106 (Streamlit UI comment)

# Need to find where prescreen_tickers ends
# Strategy: Keep everything before analyzers, keep helper functions, keep UI section
# Remove: 826-2662 (analyzers), 3710-4105 (prescreen_tickers)

# Build new file
new_lines = []
new_lines.extend(lines[:825])  # Lines 1-825 (before analyzers)
new_lines.extend(lines[2662:3709])  # Lines 2663-3709 (helper functions)
new_lines.extend(lines[4094:])  # Lines 4095+ (Streamlit UI section)

# Write back
with open('/workspaces/put_scanner/strategy_lab.py', 'w') as f:
    f.writelines(new_lines)

removed_count = (2662 - 825) + (4094 - 3709)  # Lines removed
print(f"✅ Successfully removed {removed_count} lines")
print(f"  - Removed 6 analyzer functions (lines 826-2662): {2662-825} lines")
print(f"  - Kept helper functions (lines 2663-3709): {3709-2662} lines")
print(f"  - Removed prescreen_tickers (lines 3710-4094): {4094-3709} lines")
print(f"  - New file length: {len(new_lines)} lines (was {len(lines)} lines)")
