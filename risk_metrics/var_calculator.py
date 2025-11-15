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
from math import log, sqrt, exp

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

# Standard US equity options contract multiplier
CONTRACT_MULTIPLIER = 100


def _bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Calculate Black-Scholes call option price.
    
    Args:
        S: Current underlying price
        K: Strike price
        T: Time to expiration in years
        r: Risk-free rate
        sigma: Implied volatility
        
    Returns:
        Call option price per share
    """
    if T <= 0:
        return max(S - K, 0.0)
    
    if sigma <= 0:
        # Zero vol case: immediate payoff
        return max(S - K, 0.0)
    
    d1 = (log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    
    return S * stats.norm.cdf(d1) - K * exp(-r * T) * stats.norm.cdf(d2)


def _bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Calculate Black-Scholes put option price.
    
    Args:
        S: Current underlying price
        K: Strike price
        T: Time to expiration in years
        r: Risk-free rate
        sigma: Implied volatility
        
    Returns:
        Put option price per share
    """
    if T <= 0:
        return max(K - S, 0.0)
    
    if sigma <= 0:
        # Zero vol case: immediate payoff
        return max(K - S, 0.0)
    
    d1 = (log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    
    return K * exp(-r * T) * stats.norm.cdf(-d2) - S * stats.norm.cdf(-d1)


def _implied_vol_call_simple(C0: float, S: float, K: float, T: float, r: float) -> float:
    """Estimate implied volatility for a call option using simple search.
    
    Args:
        C0: Current call price
        S: Current underlying price
        K: Strike price
        T: Time to expiration in years
        r: Risk-free rate
        
    Returns:
        Estimated implied volatility
    """
    if T <= 0 or C0 <= 0:
        return 0.30  # Default 30% vol
    
    # Intrinsic value
    intrinsic = max(S - K, 0.0)
    if C0 <= intrinsic + 0.01:
        return 0.10  # Very low vol for deep ITM
    
    # For ATM/OTM options, use approximation as initial guess
    # C ≈ 0.4 * S * σ * sqrt(T) for ATM
    time_value = C0 - intrinsic
    if time_value > 0 and T > 0:
        sigma_guess = time_value / (0.4 * S * np.sqrt(T))
        # Sanity check the guess
        if 0.05 <= sigma_guess <= 2.0:
            # Use the approximation directly if reasonable
            return sigma_guess
    
    # Simple bisection search as fallback
    vol_low, vol_high = 0.01, 3.0
    
    for iteration in range(30):  # Increase iterations
        vol_mid = (vol_low + vol_high) / 2.0
        price_mid = _bs_call_price(S, K, T, r, vol_mid)
        
        if abs(price_mid - C0) < 0.001:  # Tighter tolerance
            return vol_mid
        
        if price_mid < C0:
            vol_low = vol_mid
        else:
            vol_high = vol_mid
    
    # If bisection didn't converge, return midpoint but warn if it's extreme
    result = (vol_low + vol_high) / 2.0
    if result < 0.10:
        logger.warning(f"IV solver returned very low vol {result:.4f} for C0=${C0:.2f}, S=${S:.2f}, K=${K:.2f}, T={T:.4f}")
        # Use approximation as fallback
        if time_value > 0 and T > 0:
            result = max(time_value / (0.4 * S * np.sqrt(T)), 0.20)  # Minimum 20% vol
    return result


def _implied_vol_put_simple(P0: float, S: float, K: float, T: float, r: float) -> float:
    """Estimate implied volatility for a put option using simple search.
    
    Args:
        P0: Current put price
        S: Current underlying price
        K: Strike price
        T: Time to expiration in years
        r: Risk-free rate
        
    Returns:
        Estimated implied volatility
    """
    if T <= 0 or P0 <= 0:
        return 0.30  # Default 30% vol
    
    # Intrinsic value
    intrinsic = max(K - S, 0.0)
    if P0 <= intrinsic + 0.01:
        return 0.10  # Very low vol for deep ITM
    
    # For ATM/OTM options, use approximation as initial guess
    time_value = P0 - intrinsic
    if time_value > 0 and T > 0:
        sigma_guess = time_value / (0.4 * S * np.sqrt(T))
        # Sanity check the guess
        if 0.05 <= sigma_guess <= 2.0:
            return sigma_guess
    
    # Simple bisection search as fallback
    vol_low, vol_high = 0.01, 3.0
    
    for iteration in range(30):  # Increase iterations
        vol_mid = (vol_low + vol_high) / 2.0
        price_mid = _bs_put_price(S, K, T, r, vol_mid)
        
        if abs(price_mid - P0) < 0.001:  # Tighter tolerance
            return vol_mid
        
        if price_mid < P0:
            vol_low = vol_mid
        else:
            vol_high = vol_mid
    
    # If bisection didn't converge, return midpoint but warn if it's extreme
    result = (vol_low + vol_high) / 2.0
    if result < 0.10:
        logger.warning(f"IV solver returned very low vol {result:.4f} for P0=${P0:.2f}, S=${S:.2f}, K=${K:.2f}, T={T:.4f}")
        # Use approximation as fallback
        if time_value > 0 and T > 0:
            result = max(time_value / (0.4 * S * np.sqrt(T)), 0.20)  # Minimum 20% vol
    return result


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
    """Calculate portfolio-level VaR with proper risk modeling for each position type.
    
    Uses scenario-based simulation:
    - For stocks: P&L = quantity * price * return
    - For options: P&L = delta * quantity * 100 * underlying_price * return
    - For long options: Cap max loss at premium paid
    - For short options: No cap on losses
    
    Args:
        positions: List of position dicts with keys:
                   - symbol: str (underlying ticker)
                   - quantity: float (signed: + long, - short)
                   - underlying_price: float (current underlying price)
                   - position_type: str ('STOCK', 'CALL', 'PUT')
                   - market_value: float (current position value)
                   For options additionally:
                   - option_price: float (current option premium per share)
                   - delta: float (option delta)
                   - strike: float (strike price)
                   - expiration: str (YYYY-MM-DD)
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
    
    # Calculate total portfolio value (sum of absolute market values)
    portfolio_value = 0.0
    for pos in positions:
        if 'market_value' in pos:
            portfolio_value += abs(pos['market_value'])
        else:
            # Calculate market value based on position type
            if pos.get('position_type') in ['CALL', 'PUT']:
                # Options: quantity (contracts) * option_price (per share) * CONTRACT_MULTIPLIER
                pos_value = abs(pos['quantity']) * pos.get('option_price', 0) * CONTRACT_MULTIPLIER
            else:
                # Stock: quantity * stock_price
                pos_value = abs(pos['quantity']) * pos.get('underlying_price', 0)
            portfolio_value += pos_value
    
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
    
    # Get minimum common length across all return series
    # Get minimum common length across all return series
    min_length = min(len(returns) for returns in returns_dict.values())
    
    # Build scenario-based P&L in dollar space using proper option repricing
    # For options: reprice under each scenario using Black-Scholes
    # For stocks: use linear P&L = quantity * price * return
    portfolio_pnl = np.zeros(min_length)
    position_contributions = {}
    
    # Constants for option pricing
    RISK_FREE_RATE = 0.03  # 3% risk-free rate
    TRADING_DAYS_PER_YEAR = 252.0
    
    for pos in positions:
        symbol = pos['symbol']
        if symbol not in returns_dict:
            continue
        
        symbol_returns = returns_dict[symbol][-min_length:]
        quantity = pos['quantity']  # Signed: + for long, - for short
        underlying_price = pos['underlying_price']
        position_type = pos['position_type']
        
        # Calculate position market value (consistent units)
        if position_type in ['CALL', 'PUT']:
            option_price = pos.get('option_price', 0.0)
            position_value = abs(quantity) * option_price * CONTRACT_MULTIPLIER
        else:
            position_value = abs(quantity) * underlying_price
        
        if position_type == 'STOCK':
            # Stock P&L: quantity * spot price * return
            position_pnl = quantity * underlying_price * symbol_returns
            
        else:  # CALL or PUT option - use Black-Scholes repricing
            option_price = pos.get('option_price', 0.0)
            strike = pos.get('strike', underlying_price)
            expiration_str = pos.get('expiration', '')
            
            logger.info(f"Processing {position_type} option: {symbol}")
            logger.info(f"  Underlying price: ${underlying_price:.2f}")
            logger.info(f"  Option price: ${option_price:.2f}/share")
            logger.info(f"  Strike: ${strike:.2f}")
            logger.info(f"  Expiration: {expiration_str}")
            logger.info(f"  Quantity: {quantity}")
            
            # Validate data integrity
            if abs(underlying_price - strike) < 0.01:
                logger.warning(
                    f"⚠️ Underlying price (${underlying_price:.2f}) equals strike (${strike:.2f}). "
                    f"This is suspicious and likely indicates the underlying price fetch failed. "
                    f"VaR calculation will be inaccurate!"
                )
            
            # Calculate time to expiration in years
            try:
                exp_date = datetime.strptime(expiration_str, '%Y-%m-%d')
                days_to_exp = (exp_date - datetime.now()).days
                T0 = max(days_to_exp / TRADING_DAYS_PER_YEAR, 1.0 / TRADING_DAYS_PER_YEAR)
                logger.info(f"  Days to expiration: {days_to_exp}, T0: {T0:.4f} years")
            except Exception as e:
                T0 = 30.0 / TRADING_DAYS_PER_YEAR  # Default 30 days
                logger.warning(f"  Could not parse expiration '{expiration_str}': {e}, using T0={T0:.4f}")
            
            # Estimate implied volatility from current option price
            if position_type == 'CALL':
                sigma = _implied_vol_call_simple(option_price, underlying_price, strike, T0, RISK_FREE_RATE)
            else:  # PUT
                sigma = _implied_vol_put_simple(option_price, underlying_price, strike, T0, RISK_FREE_RATE)
            
            logger.info(f"  Implied volatility: {sigma:.4f} ({sigma*100:.2f}%)")
            
            # For each scenario, reprice the option
            position_pnl = np.zeros(len(symbol_returns))
            
            for i, ret in enumerate(symbol_returns):
                # New underlying price under this scenario
                S1 = underlying_price * (1 + ret)
                
                # Time to expiration reduced by 1 day
                T1 = max(T0 - 1.0 / TRADING_DAYS_PER_YEAR, 0.0)
                
                # Reprice option
                if position_type == 'CALL':
                    C1 = _bs_call_price(S1, strike, T1, RISK_FREE_RATE, sigma)
                else:  # PUT
                    C1 = _bs_put_price(S1, strike, T1, RISK_FREE_RATE, sigma)
                
                # P&L = change in option value * contracts * multiplier
                # Note: (C1 - option_price) is per-share change
                position_pnl[i] = quantity * (C1 - option_price) * CONTRACT_MULTIPLIER
            
            logger.info(f"  Position P&L range: ${position_pnl.min():.2f} to ${position_pnl.max():.2f}")
            logger.info(f"  95th percentile loss: ${-np.percentile(position_pnl, 5):.2f}")
            
            # No need to cap losses - Black-Scholes naturally bounds option prices at zero
        
        # Accumulate to portfolio P&L (in dollars)
        portfolio_pnl += position_pnl
        
        # Track position contribution (for risk attribution)
        position_contributions[symbol] = position_value
    
    # Now portfolio_pnl[t] is the dollar P&L for each historical day
    # Convert to losses (positive = loss, negative = gain)
    losses = -portfolio_pnl
    
    # Scale for multi-day horizon if needed
    if time_horizon_days > 1:
        # Use overlapping windows
        scaled_losses = []
        for i in range(len(losses) - time_horizon_days + 1):
            window_loss = np.sum(losses[i:i+time_horizon_days])
            scaled_losses.append(window_loss)
        losses = np.array(scaled_losses)
    
    # Calculate VaR as percentile of loss distribution
    # VaR should always be positive (representing a loss amount)
    percentile_level = confidence_level * 100.0
    var_dollar = float(np.percentile(losses, percentile_level))
    
    # Ensure VaR is non-negative (can't have negative loss)
    if var_dollar < 0:
        logger.warning(
            f"VaR calculation resulted in negative value (${var_dollar:.2f}), "
            f"indicating most scenarios show gains. Setting VaR to $0. "
            f"This may indicate data issues (e.g., wrong underlying price)."
        )
        var_dollar = 0.0
    
    # Debug logging
    logger.info(f"VaR Calculation Debug:")
    logger.info(f"  Portfolio value: ${portfolio_value:.2f}")
    logger.info(f"  Number of scenarios: {len(losses)}")
    logger.info(f"  Loss distribution: min=${losses.min():.2f}, max=${losses.max():.2f}, mean=${losses.mean():.2f}")
    logger.info(f"  VaR (95th percentile): ${var_dollar:.2f}")
    logger.info(f"  Positions: {len(positions)}")
    for pos in positions:
        logger.info(f"    {pos['symbol']}: {pos['position_type']}, qty={pos['quantity']}, price=${pos.get('option_price', pos['underlying_price']):.2f}")
    
    var_percent = (var_dollar / portfolio_value) * 100.0 if portfolio_value > 0 else 0.0
    
    # Calculate CVaR (average of losses at or beyond VaR threshold)
    tail_losses = losses[losses >= var_dollar]
    cvar_dollar = float(np.mean(tail_losses)) if len(tail_losses) > 0 else var_dollar
    cvar_percent = (cvar_dollar / portfolio_value) * 100.0 if portfolio_value > 0 else 0.0
    
    # Calculate statistics (convert P&L to returns for volatility/mean)
    returns_for_stats = portfolio_pnl / portfolio_value if portfolio_value > 0 else portfolio_pnl
    volatility = float(np.std(returns_for_stats))
    mean_return = float(np.mean(returns_for_stats))
    
    # Create result
    var_result = VaRResult(
        var_amount=var_dollar,
        var_percent=var_percent,
        confidence_level=confidence_level,
        time_horizon_days=time_horizon_days,
        method='historical',
        cvar_amount=cvar_dollar,
        cvar_percent=cvar_percent,
        volatility=volatility,
        mean_return=mean_return,
        calculated_at=datetime.now(),
        data_points=len(portfolio_pnl),
        position_contributions=position_contributions
    )
    
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
