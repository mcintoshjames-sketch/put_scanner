"""Value at Risk (VaR) and Conditional VaR (CVaR) Calculator.

Implements industry-standard risk metrics for portfolio management:
1. Parametric VaR - Assumes normal distribution of returns
2. Historical VaR - Uses actual historical price movements
3. Conditional VaR (CVaR) - Expected loss beyond VaR threshold
4. Portfolio VaR - Aggregate risk accounting for correlations

References:
- JP Morgan RiskMetrics (1996)
- Basel Committee on Banking Supervision guidelines
- Artzner et al. (1999) - Coherent Measures of Risk

Author: Options Strategy Lab
Created: 2025-11-15
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class VaRResult:
    """Value at Risk calculation result."""
    
    var_amount: float  # Dollar amount at risk
    var_percent: float  # Percentage of portfolio at risk
    confidence_level: float  # Confidence level (e.g., 0.95)
    time_horizon_days: int  # Time horizon in days
    method: str  # 'parametric', 'historical', or 'monte_carlo'
    
    # CVaR (Expected Shortfall)
    cvar_amount: Optional[float] = None
    cvar_percent: Optional[float] = None
    
    # Additional metrics
    volatility: Optional[float] = None
    mean_return: Optional[float] = None
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None
    
    # Breakdown by position (if available)
    position_contributions: Optional[Dict[str, float]] = None
    
    # Calculation metadata
    calculated_at: Optional[datetime] = None
    data_points: Optional[int] = None
    

def calculate_parametric_var(
    portfolio_value: float,
    volatility: float,
    mean_return: float = 0.0,
    confidence_level: float = 0.95,
    time_horizon_days: int = 1
) -> VaRResult:
    """Calculate parametric VaR assuming normal distribution.
    
    Formula: VaR = Portfolio Value * (μ - z * σ * sqrt(t))
    
    Where:
    - μ = expected return
    - z = z-score for confidence level (1.65 for 95%, 2.33 for 99%)
    - σ = volatility (standard deviation)
    - t = time horizon
    
    Args:
        portfolio_value: Current portfolio value
        volatility: Daily volatility (standard deviation of returns)
        mean_return: Expected daily return (default 0.0 for conservative)
        confidence_level: Confidence level (0.90, 0.95, or 0.99)
        time_horizon_days: Time horizon in days (typically 1 or 10)
        
    Returns:
        VaRResult with parametric VaR calculation
        
    Example:
        >>> var = calculate_parametric_var(
        ...     portfolio_value=100000,
        ...     volatility=0.02,  # 2% daily volatility
        ...     confidence_level=0.95,
        ...     time_horizon_days=1
        ... )
        >>> print(f"95% VaR (1-day): ${var.var_amount:,.2f}")
    """
    # Get z-score for confidence level
    z_score = stats.norm.ppf(confidence_level)
    
    # Scale volatility by time horizon (square root of time rule)
    scaled_volatility = volatility * np.sqrt(time_horizon_days)
    scaled_mean = mean_return * time_horizon_days
    
    # Calculate VaR (loss is positive)
    var_return = -(scaled_mean - z_score * scaled_volatility)
    var_amount = portfolio_value * var_return
    var_percent = var_return * 100.0
    
    # Estimate CVaR for normal distribution
    # CVaR = E[Loss | Loss > VaR] = μ + σ * φ(z) / (1 - Φ(z))
    # Where φ is PDF and Φ is CDF
    tail_prob = 1.0 - confidence_level
    pdf_at_z = stats.norm.pdf(z_score)
    cvar_return = -(scaled_mean + scaled_volatility * pdf_at_z / tail_prob)
    cvar_amount = portfolio_value * cvar_return
    cvar_percent = cvar_return * 100.0
    
    return VaRResult(
        var_amount=float(var_amount),
        var_percent=float(var_percent),
        confidence_level=confidence_level,
        time_horizon_days=time_horizon_days,
        method='parametric',
        cvar_amount=float(cvar_amount),
        cvar_percent=float(cvar_percent),
        volatility=float(volatility),
        mean_return=float(mean_return),
        calculated_at=datetime.now(),
        data_points=None
    )


def calculate_historical_var(
    portfolio_value: float,
    historical_returns: np.ndarray,
    confidence_level: float = 0.95,
    time_horizon_days: int = 1
) -> VaRResult:
    """Calculate historical VaR using actual return distribution.
    
    Uses empirical distribution of historical returns without assuming
    normality. More accurate when returns are skewed or fat-tailed.
    
    Args:
        portfolio_value: Current portfolio value
        historical_returns: Array of historical returns (daily)
        confidence_level: Confidence level (0.90, 0.95, or 0.99)
        time_horizon_days: Time horizon in days
        
    Returns:
        VaRResult with historical VaR calculation
        
    Example:
        >>> returns = np.array([0.01, -0.02, 0.015, -0.01, 0.005, ...])
        >>> var = calculate_historical_var(
        ...     portfolio_value=100000,
        ...     historical_returns=returns,
        ...     confidence_level=0.95
        ... )
    """
    if len(historical_returns) == 0:
        raise ValueError("historical_returns cannot be empty")
    
    # Scale returns for time horizon if needed
    if time_horizon_days > 1:
        # Use overlapping windows for time horizon
        scaled_returns = []
        for i in range(len(historical_returns) - time_horizon_days + 1):
            window_return = np.sum(historical_returns[i:i+time_horizon_days])
            scaled_returns.append(window_return)
        returns_to_use = np.array(scaled_returns)
    else:
        returns_to_use = historical_returns
    
    # Calculate percentile (lower tail = losses)
    percentile = (1.0 - confidence_level) * 100.0
    var_return = -np.percentile(returns_to_use, percentile)
    var_amount = portfolio_value * var_return
    var_percent = var_return * 100.0
    
    # Calculate CVaR (average of all losses beyond VaR)
    losses = -returns_to_use[returns_to_use <= -var_return]
    if len(losses) > 0:
        cvar_return = np.mean(losses)
        cvar_amount = portfolio_value * cvar_return
        cvar_percent = cvar_return * 100.0
    else:
        cvar_amount = var_amount
        cvar_percent = var_percent
    
    # Calculate distribution statistics
    volatility = np.std(returns_to_use)
    mean_return = np.mean(returns_to_use)
    skewness = stats.skew(returns_to_use)
    kurtosis = stats.kurtosis(returns_to_use)
    
    return VaRResult(
        var_amount=float(var_amount),
        var_percent=float(var_percent),
        confidence_level=confidence_level,
        time_horizon_days=time_horizon_days,
        method='historical',
        cvar_amount=float(cvar_amount),
        cvar_percent=float(cvar_percent),
        volatility=float(volatility),
        mean_return=float(mean_return),
        skewness=float(skewness),
        kurtosis=float(kurtosis),
        calculated_at=datetime.now(),
        data_points=len(historical_returns)
    )


def calculate_cvar(
    portfolio_value: float,
    historical_returns: np.ndarray,
    confidence_level: float = 0.95,
    time_horizon_days: int = 1
) -> Tuple[float, float]:
    """Calculate Conditional VaR (Expected Shortfall) directly.
    
    CVaR is the expected loss given that the loss exceeds VaR.
    It's a coherent risk measure (unlike VaR) and better captures tail risk.
    
    Args:
        portfolio_value: Current portfolio value
        historical_returns: Array of historical returns
        confidence_level: Confidence level
        time_horizon_days: Time horizon in days
        
    Returns:
        Tuple of (cvar_amount, cvar_percent)
    """
    var_result = calculate_historical_var(
        portfolio_value=portfolio_value,
        historical_returns=historical_returns,
        confidence_level=confidence_level,
        time_horizon_days=time_horizon_days
    )
    
    return var_result.cvar_amount or 0.0, var_result.cvar_percent or 0.0


def calculate_portfolio_var(
    positions: List[Dict],
    historical_prices: pd.DataFrame,
    confidence_level: float = 0.95,
    time_horizon_days: int = 1,
    method: str = 'historical'
) -> VaRResult:
    """Calculate portfolio-level VaR accounting for position correlations.
    
    Args:
        positions: List of position dicts with keys:
                   - symbol: str
                   - quantity: float
                   - current_price: float
                   - position_type: str ('STOCK', 'CALL', 'PUT')
        historical_prices: DataFrame with columns = symbols, rows = dates
        confidence_level: Confidence level (0.90, 0.95, or 0.99)
        time_horizon_days: Time horizon in days
        method: 'parametric' or 'historical'
        
    Returns:
        VaRResult with portfolio VaR and position contributions
    """
    if not positions:
        return VaRResult(
            var_amount=0.0,
            var_percent=0.0,
            confidence_level=confidence_level,
            time_horizon_days=time_horizon_days,
            method=method,
            calculated_at=datetime.now()
        )
    
    # Calculate portfolio value
    portfolio_value = sum(
        pos['quantity'] * pos['current_price'] * 
        (100 if pos.get('position_type') in ['CALL', 'PUT'] else 1)
        for pos in positions
    )
    
    if portfolio_value == 0:
        return VaRResult(
            var_amount=0.0,
            var_percent=0.0,
            confidence_level=confidence_level,
            time_horizon_days=time_horizon_days,
            method=method,
            calculated_at=datetime.now()
        )
    
    # Extract symbols from positions
    symbols = list(set(pos['symbol'] for pos in positions))
    
    # Calculate returns for each symbol
    returns_dict = {}
    for symbol in symbols:
        if symbol in historical_prices.columns:
            prices = historical_prices[symbol].dropna()
            if len(prices) > 1:
                returns = prices.pct_change().dropna().values
                returns_dict[symbol] = returns
    
    if not returns_dict:
        logger.warning("No historical price data available for VaR calculation")
        return VaRResult(
            var_amount=0.0,
            var_percent=0.0,
            confidence_level=confidence_level,
            time_horizon_days=time_horizon_days,
            method=method,
            calculated_at=datetime.now()
        )
    
    # Calculate portfolio returns (weighted by position value)
    # Get minimum common length
    min_length = min(len(returns) for returns in returns_dict.values())
    
    portfolio_returns = np.zeros(min_length)
    position_contributions = {}
    
    for pos in positions:
        symbol = pos['symbol']
        if symbol not in returns_dict:
            continue
            
        # Position value
        pos_value = pos['quantity'] * pos['current_price'] * \
                    (100 if pos.get('position_type') in ['CALL', 'PUT'] else 1)
        weight = pos_value / portfolio_value
        
        # Contribution to portfolio returns
        symbol_returns = returns_dict[symbol][-min_length:]
        portfolio_returns += weight * symbol_returns
        
        # Track contribution (for risk attribution)
        position_contributions[symbol] = weight * portfolio_value
    
    # Calculate VaR based on method
    if method == 'parametric':
        volatility = float(np.std(portfolio_returns))
        mean_return = float(np.mean(portfolio_returns))
        
        var_result = calculate_parametric_var(
            portfolio_value=portfolio_value,
            volatility=volatility,
            mean_return=mean_return,
            confidence_level=confidence_level,
            time_horizon_days=time_horizon_days
        )
    else:  # historical
        var_result = calculate_historical_var(
            portfolio_value=portfolio_value,
            historical_returns=portfolio_returns,
            confidence_level=confidence_level,
            time_horizon_days=time_horizon_days
        )
    
    # Add position contributions
    var_result.position_contributions = position_contributions
    
    return var_result


def format_var_report(var_result: VaRResult) -> str:
    """Format VaR result as a readable report.
    
    Args:
        var_result: VaRResult object
        
    Returns:
        Formatted string report
    """
    confidence_pct = var_result.confidence_level * 100
    
    report = f"""
Value at Risk Report
{'=' * 60}
Method:             {var_result.method.title()}
Confidence Level:   {confidence_pct:.1f}%
Time Horizon:       {var_result.time_horizon_days} day(s)

VaR (Value at Risk):
  Dollar Amount:    ${var_result.var_amount:,.2f}
  Percentage:       {var_result.var_percent:.2f}%

CVaR (Conditional VaR / Expected Shortfall):
  Dollar Amount:    ${var_result.cvar_amount:,.2f} if var_result.cvar_amount else 'N/A'
  Percentage:       {var_result.cvar_percent:.2f}% if var_result.cvar_percent else 'N/A'

Interpretation:
  There is a {100 - confidence_pct:.1f}% chance of losing more than 
  ${var_result.var_amount:,.2f} ({var_result.var_percent:.2f}%) over the next
  {var_result.time_horizon_days} day(s).
"""
    
    if var_result.cvar_amount:
        report += f"""
  If losses exceed VaR, the expected loss is ${var_result.cvar_amount:,.2f}
  ({var_result.cvar_percent:.2f}%).
"""
    
    if var_result.volatility:
        report += f"""
Distribution Statistics:
  Volatility:       {var_result.volatility * 100:.2f}% per day
  Mean Return:      {(var_result.mean_return or 0) * 100:.2f}% per day
"""
    
    if var_result.skewness is not None:
        report += f"  Skewness:         {var_result.skewness:.3f}\n"
        report += f"  Kurtosis:         {var_result.kurtosis:.3f}\n"
    
    if var_result.position_contributions:
        report += f"\nPosition Contributions:\n"
        for symbol, contrib in sorted(
            var_result.position_contributions.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        ):
            report += f"  {symbol:8s} ${contrib:12,.2f}\n"
    
    report += f"\n{'=' * 60}\n"
    report += f"Calculated: {var_result.calculated_at.strftime('%Y-%m-%d %H:%M:%S') if var_result.calculated_at else 'N/A'}\n"
    if var_result.data_points:
        report += f"Data Points: {var_result.data_points}\n"
    
    return report
