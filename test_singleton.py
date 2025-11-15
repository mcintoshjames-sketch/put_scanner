#!/usr/bin/env python3
"""Quick singleton test."""

from portfolio_manager import PortfolioManager, get_portfolio_manager

print("Testing singleton pattern...")

# Get singleton instance
pm1 = get_portfolio_manager()
print(f"pm1 id: {id(pm1)}")

# Get it again
pm2 = get_portfolio_manager()
print(f"pm2 id: {id(pm2)}")

# Check they're the same object
if pm1 is pm2:
    print("✅ Singleton working correctly - both references point to same object")
else:
    print("❌ Singleton broken - different objects")
    exit(1)

# Verify they share state
pm1.positions = ["test"]
if pm2.positions == ["test"]:
    print("✅ Shared state confirmed")
else:
    print("❌ State not shared")
    exit(1)

print("\n✅ All singleton tests passed!")
