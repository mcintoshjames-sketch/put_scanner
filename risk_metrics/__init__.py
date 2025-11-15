"""Risk Metrics Package - VaR, CVaR, and Risk Analytics.

This package provides industry-standard risk metrics for portfolio management:
- Value at Risk (VaR) - Parametric and Historical methods
- Conditional Value at Risk (CVaR) - Expected shortfall
- Position-level risk contributions
- Stress testing scenarios

Author: Options Strategy Lab
Created: 2025-11-15
"""

from .var_calculator import (
    calculate_parametric_var,
    calculate_historical_var,
    calculate_cvar,
    calculate_portfolio_var,
    VaRResult,
)

__all__ = [
    'calculate_parametric_var',
    'calculate_historical_var',
    'calculate_cvar',
    'calculate_portfolio_var',
    'VaRResult',
]

__version__ = '1.0.0'
