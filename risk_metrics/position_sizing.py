"""Kelly Criterion Position Sizing Calculator.

Implements optimal position sizing based on edge and win probability:
- Full Kelly Criterion
- Fractional Kelly (safer, reduced volatility)
- Strategy-specific win rate estimation
- Risk-adjusted position recommendations

References:
- Kelly, J. L. (1956). "A New Interpretation of Information Rate"
- Thorp, E. O. (2008). "The Kelly Capital Growth Investment Criterion"
- Fortune's Formula (Poundstone, 2005)

Author: Options Strategy Lab
Created: 2025-11-15
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class KellyResult:
    """Kelly Criterion calculation result."""
    
    full_kelly: float  # Full Kelly fraction (0-1)
    recommended_fraction: float  # Fractional Kelly (typically 0.25-0.5 of full)
    recommended_size: float  # Dollar amount to risk
    win_probability: float  # Estimated P(win)
    avg_win: float  # Average winning amount
    avg_loss: float  # Average losing amount
    expected_value: float  # Expected profit per trade
    kelly_multiplier: float  # How aggressive (0.25 = quarter Kelly)
    
    # Risk metrics
    risk_of_ruin: float  # Probability of catastrophic loss
    volatility_estimate: float  # Portfolio volatility impact
    
    # Context
    strategy_type: str
    current_capital: float
    calculated_at: Optional[str] = None


def calculate_full_kelly(
    win_prob: float,
    avg_win: float,
    avg_loss: float
) -> float:
    """Calculate full Kelly Criterion fraction.
    
    Args:
        win_prob: Probability of winning (0-1)
        avg_win: Average winning amount (absolute)
        avg_loss: Average losing amount (absolute, positive)
        
    Returns:
        Kelly fraction (0-1), or 0 if negative expectation
    """
    if win_prob <= 0 or win_prob >= 1:
        return 0.0
    
    if avg_win <= 0 or avg_loss <= 0:
        return 0.0
    
    loss_prob = 1.0 - win_prob
    
    # Kelly formula: f* = (p*W - q*L) / W
    # where p = win prob, q = loss prob, W = avg win, L = avg loss
    kelly = (win_prob * avg_win - loss_prob * avg_loss) / avg_win
    
    # Kelly can be negative (negative expectation) or > 1 (huge edge)
    # Cap at reasonable bounds
    return max(0.0, min(kelly, 1.0))


def estimate_win_rate_from_strategy(
    strategy_type: str,
    probability_itm: float,
    pop: float,
    current_iv: float = 0.25,
    historical_iv: float = 0.25
) -> Tuple[float, float, float]:
    """Estimate win probability and avg win/loss for a strategy.
    
    Args:
        strategy_type: Type of strategy (CSP, CC, IRON_CONDOR, etc.)
        probability_itm: Probability of ending ITM at expiration
        pop: Probability of profit from simulation
        current_iv: Current implied volatility
        historical_iv: Historical average IV
        
    Returns:
        (win_probability, avg_win_pct, avg_loss_pct)
    """
    # Base estimates by strategy type
    strategy_defaults = {
        'CSP': {
            'base_win_rate': 0.70,  # Cash-secured puts typically win 70%
            'avg_win_pct': 0.60,    # Keep 60% of max gain on wins
            'avg_loss_pct': 1.20,   # Lose 120% of initial credit on losses
        },
        'CC': {
            'base_win_rate': 0.75,  # Covered calls win more often
            'avg_win_pct': 0.65,
            'avg_loss_pct': 0.80,   # Smaller losses (stock appreciation)
        },
        'IRON_CONDOR': {
            'base_win_rate': 0.65,  # More volatile, lower win rate
            'avg_win_pct': 0.50,    # Often close early at 50% max
            'avg_loss_pct': 1.50,   # Can lose more than credit
        },
        'VERTICAL_SPREAD': {
            'base_win_rate': 0.60,
            'avg_win_pct': 0.70,
            'avg_loss_pct': 1.00,   # Defined risk
        },
        'BULL_PUT_SPREAD': {
            'base_win_rate': 0.68,
            'avg_win_pct': 0.65,
            'avg_loss_pct': 1.10,
        },
        'BEAR_CALL_SPREAD': {
            'base_win_rate': 0.68,
            'avg_win_pct': 0.65,
            'avg_loss_pct': 1.10,
        },
    }
    
    defaults = strategy_defaults.get(strategy_type, {
        'base_win_rate': 0.65,
        'avg_win_pct': 0.60,
        'avg_loss_pct': 1.20,
    })
    
    # Adjust win rate based on POP and probability ITM
    # POP is more reliable than prob_itm for actual profit
    if pop > 0:
        win_prob = 0.7 * pop + 0.3 * defaults['base_win_rate']
    else:
        # Fall back to ITM probability estimate
        win_prob = 0.6 * (1 - probability_itm) + 0.4 * defaults['base_win_rate']
    
    # Adjust for IV environment
    iv_ratio = current_iv / historical_iv if historical_iv > 0 else 1.0
    if iv_ratio > 1.2:
        # High IV -> more risk, slightly lower win rate
        win_prob *= 0.95
    elif iv_ratio < 0.8:
        # Low IV -> tighter range, slightly higher win rate
        win_prob *= 1.05
    
    # Clamp to reasonable bounds
    win_prob = max(0.45, min(win_prob, 0.85))
    
    return (
        win_prob,
        defaults['avg_win_pct'],
        defaults['avg_loss_pct']
    )


def calculate_position_size(
    capital: float,
    strategy_type: str,
    expected_credit: float,
    max_loss: float,
    probability_itm: float = 0.30,
    pop: float = 0.0,
    kelly_multiplier: float = 0.25,
    current_iv: float = 0.25,
    historical_iv: float = 0.25,
    min_position_size: float = 100.0,
    max_position_size: Optional[float] = None
) -> KellyResult:
    """Calculate recommended position size using Kelly Criterion.
    
    Args:
        capital: Available trading capital
        strategy_type: Type of strategy (CSP, CC, IRON_CONDOR, etc.)
        expected_credit: Expected credit received (per contract)
        max_loss: Maximum loss per contract
        probability_itm: Probability of ending ITM
        pop: Probability of profit from simulation
        kelly_multiplier: Fraction of full Kelly to use (0.25 = quarter Kelly)
        current_iv: Current implied volatility
        historical_iv: Historical average IV
        min_position_size: Minimum position size (dollars)
        max_position_size: Maximum position size (dollars), optional
        
    Returns:
        KellyResult with recommended position size
    """
    from datetime import datetime
    
    # Estimate win probability and payoffs
    win_prob, avg_win_pct, avg_loss_pct = estimate_win_rate_from_strategy(
        strategy_type=strategy_type,
        probability_itm=probability_itm,
        pop=pop,
        current_iv=current_iv,
        historical_iv=historical_iv
    )
    
    # Calculate average win and loss amounts
    # Win: Keep a fraction of the credit
    # Loss: Lose a multiple of the credit (can be > 100%)
    avg_win = expected_credit * avg_win_pct
    avg_loss = expected_credit * avg_loss_pct
    
    # Ensure avg_loss doesn't exceed max_loss
    if max_loss > 0:
        avg_loss = min(avg_loss, max_loss)
    
    # Calculate expected value
    loss_prob = 1.0 - win_prob
    expected_value = win_prob * avg_win - loss_prob * avg_loss
    
    # Calculate full Kelly
    full_kelly = calculate_full_kelly(win_prob, avg_win, avg_loss)
    
    # Apply fractional Kelly multiplier
    recommended_fraction = full_kelly * kelly_multiplier
    
    # Calculate dollar size
    # Kelly fraction applies to the amount at risk (max_loss), not capital
    if max_loss > 0:
        # Position size = kelly_fraction * capital / (max_loss_per_contract / expected_credit)
        # Simplified: How much capital to allocate
        risk_per_unit = max_loss if max_loss > expected_credit else expected_credit * 2
        position_size = (recommended_fraction * capital)
        
        # Don't risk more than we can afford
        position_size = min(position_size, capital * 0.20)  # Max 20% of capital
    else:
        position_size = min_position_size
    
    # Apply bounds
    if position_size < min_position_size:
        position_size = 0.0  # Too small, skip
    
    if max_position_size and position_size > max_position_size:
        position_size = max_position_size
    
    # Estimate risk of ruin (simplified)
    # Risk of ruin increases with Kelly fraction
    if recommended_fraction > 0.5:
        risk_of_ruin = 0.10  # High risk
    elif recommended_fraction > 0.25:
        risk_of_ruin = 0.05  # Moderate risk
    else:
        risk_of_ruin = 0.02  # Low risk
    
    # Estimate volatility contribution
    # Higher Kelly = more volatile
    volatility_estimate = recommended_fraction * 0.15  # Rough estimate
    
    return KellyResult(
        full_kelly=full_kelly,
        recommended_fraction=recommended_fraction,
        recommended_size=position_size,
        win_probability=win_prob,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expected_value=expected_value,
        kelly_multiplier=kelly_multiplier,
        risk_of_ruin=risk_of_ruin,
        volatility_estimate=volatility_estimate,
        strategy_type=strategy_type,
        current_capital=capital,
        calculated_at=datetime.now().isoformat()
    )


def kelly_batch_analysis(
    capital: float,
    opportunities: List[Dict],
    kelly_multiplier: float = 0.25,
    max_total_allocation: float = 0.50
) -> List[Tuple[Dict, KellyResult]]:
    """Analyze multiple opportunities and recommend allocation.
    
    Args:
        capital: Available trading capital
        opportunities: List of opportunity dicts with strategy details
        kelly_multiplier: Fraction of full Kelly (0.25 = quarter Kelly)
        max_total_allocation: Max fraction of capital to deploy (0.50 = 50%)
        
    Returns:
        List of (opportunity, KellyResult) tuples, sorted by recommended size
    """
    results = []
    
    for opp in opportunities:
        kelly_result = calculate_position_size(
            capital=capital,
            strategy_type=opp.get('strategy_type', 'CSP'),
            expected_credit=opp.get('credit', 0.0),
            max_loss=opp.get('max_loss', 0.0),
            probability_itm=opp.get('probability_itm', 0.30),
            pop=opp.get('pop', 0.0),
            kelly_multiplier=kelly_multiplier,
            current_iv=opp.get('current_iv', 0.25),
            historical_iv=opp.get('historical_iv', 0.25)
        )
        
        results.append((opp, kelly_result))
    
    # Sort by recommended size (descending)
    results.sort(key=lambda x: x[1].recommended_size, reverse=True)
    
    # Apply total allocation cap
    total_allocated = 0.0
    max_allocation = capital * max_total_allocation
    
    filtered_results = []
    for opp, kelly_result in results:
        if total_allocated + kelly_result.recommended_size <= max_allocation:
            filtered_results.append((opp, kelly_result))
            total_allocated += kelly_result.recommended_size
        else:
            # Reduce size to fit within cap
            remaining = max_allocation - total_allocated
            if remaining > 100:  # Minimum viable size
                adjusted_result = KellyResult(
                    full_kelly=kelly_result.full_kelly,
                    recommended_fraction=kelly_result.recommended_fraction,
                    recommended_size=remaining,
                    win_probability=kelly_result.win_probability,
                    avg_win=kelly_result.avg_win,
                    avg_loss=kelly_result.avg_loss,
                    expected_value=kelly_result.expected_value,
                    kelly_multiplier=kelly_result.kelly_multiplier,
                    risk_of_ruin=kelly_result.risk_of_ruin,
                    volatility_estimate=kelly_result.volatility_estimate,
                    strategy_type=kelly_result.strategy_type,
                    current_capital=kelly_result.current_capital,
                    calculated_at=kelly_result.calculated_at
                )
                filtered_results.append((opp, adjusted_result))
            break
    
    return filtered_results


def format_kelly_recommendation(kelly: KellyResult) -> str:
    """Format Kelly result as human-readable recommendation.
    
    Args:
        kelly: KellyResult instance
        
    Returns:
        Formatted recommendation string
    """
    lines = []
    lines.append(f"📊 Kelly Position Sizing for {kelly.strategy_type}")
    lines.append(f"{'='*60}")
    lines.append(f"Available Capital:     ${kelly.current_capital:,.2f}")
    lines.append(f"Full Kelly Fraction:   {kelly.full_kelly*100:.1f}%")
    lines.append(f"Recommended Fraction:  {kelly.recommended_fraction*100:.1f}% ({kelly.kelly_multiplier*100:.0f}% of full Kelly)")
    lines.append(f"Recommended Size:      ${kelly.recommended_size:,.2f}")
    lines.append("")
    lines.append("Risk/Reward Estimates:")
    lines.append(f"  Win Probability:     {kelly.win_probability*100:.1f}%")
    lines.append(f"  Avg Win:             ${kelly.avg_win:,.2f}")
    lines.append(f"  Avg Loss:            ${kelly.avg_loss:,.2f}")
    lines.append(f"  Expected Value:      ${kelly.expected_value:,.2f}")
    lines.append("")
    lines.append("Risk Metrics:")
    lines.append(f"  Risk of Ruin:        {kelly.risk_of_ruin*100:.1f}%")
    lines.append(f"  Volatility Impact:   {kelly.volatility_estimate*100:.1f}%")
    lines.append("")
    
    if kelly.recommended_size == 0:
        lines.append("⚠️  Position too small - consider skipping or increasing capital")
    elif kelly.recommended_fraction < 0.10:
        lines.append("✅ Conservative sizing - low risk")
    elif kelly.recommended_fraction < 0.25:
        lines.append("✅ Moderate sizing - balanced risk/reward")
    else:
        lines.append("⚠️  Aggressive sizing - higher volatility expected")
    
    return "\n".join(lines)
