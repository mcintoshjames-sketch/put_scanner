#!/usr/bin/env python3
"""Test suite for Kelly Criterion position sizing."""

import pytest
from risk_metrics.position_sizing import (
    calculate_full_kelly,
    estimate_win_rate_from_strategy,
    calculate_position_size,
    kelly_batch_analysis,
    format_kelly_recommendation,
)


def test_full_kelly_basic():
    """Test basic full Kelly calculation."""
    # Classic example: 60% win rate, 1:1 payoff
    kelly = calculate_full_kelly(
        win_prob=0.60,
        avg_win=100.0,
        avg_loss=100.0
    )
    # Kelly = (0.6 * 100 - 0.4 * 100) / 100 = 0.20 (20%)
    assert 0.19 < kelly < 0.21
    
    # 70% win rate, 1:1 payoff
    kelly = calculate_full_kelly(
        win_prob=0.70,
        avg_win=100.0,
        avg_loss=100.0
    )
    # Kelly = (0.7 * 100 - 0.3 * 100) / 100 = 0.40 (40%)
    assert 0.39 < kelly < 0.41


def test_full_kelly_asymmetric():
    """Test Kelly with asymmetric payoffs."""
    # High win rate, small wins, rare big losses
    kelly = calculate_full_kelly(
        win_prob=0.80,
        avg_win=50.0,
        avg_loss=200.0
    )
    # Kelly = (0.8 * 50 - 0.2 * 200) / 50 = 0.0 (negative expectation)
    assert kelly == pytest.approx(0.0, abs=1e-10)
    
    # Moderate win rate, big wins, small losses
    kelly = calculate_full_kelly(
        win_prob=0.55,
        avg_win=200.0,
        avg_loss=100.0
    )
    # Kelly = (0.55 * 200 - 0.45 * 100) / 200 = 0.325 (32.5%)
    assert 0.30 < kelly < 0.35


def test_full_kelly_edge_cases():
    """Test edge cases."""
    # Win prob = 0
    assert calculate_full_kelly(0.0, 100, 100) == 0.0
    
    # Win prob = 1
    assert calculate_full_kelly(1.0, 100, 100) == 0.0
    
    # Negative win/loss
    assert calculate_full_kelly(0.6, -100, 100) == 0.0
    assert calculate_full_kelly(0.6, 100, -100) == 0.0


def test_estimate_win_rate_csp():
    """Test win rate estimation for CSP."""
    win_prob, avg_win_pct, avg_loss_pct = estimate_win_rate_from_strategy(
        strategy_type='CSP',
        probability_itm=0.30,
        pop=0.72,
        current_iv=0.25,
        historical_iv=0.25
    )
    
    # CSP typically has 70% base win rate
    # With 72% POP, should be around 70-75%
    assert 0.65 < win_prob < 0.80
    assert avg_win_pct > 0
    assert avg_loss_pct > 1.0  # Losses > wins


def test_estimate_win_rate_iron_condor():
    """Test win rate estimation for Iron Condor."""
    win_prob, avg_win_pct, avg_loss_pct = estimate_win_rate_from_strategy(
        strategy_type='IRON_CONDOR',
        probability_itm=0.20,
        pop=0.65,
        current_iv=0.30,
        historical_iv=0.25
    )
    
    # Iron Condor typically lower win rate than CSP
    assert 0.55 < win_prob < 0.75
    assert avg_loss_pct > avg_win_pct  # Losses bigger than wins


def test_estimate_win_rate_high_iv():
    """Test win rate adjustment for high IV environment."""
    # Normal IV
    win_prob_normal, _, _ = estimate_win_rate_from_strategy(
        strategy_type='CSP',
        probability_itm=0.30,
        pop=0.70,
        current_iv=0.25,
        historical_iv=0.25
    )
    
    # High IV (50% higher)
    win_prob_high_iv, _, _ = estimate_win_rate_from_strategy(
        strategy_type='CSP',
        probability_itm=0.30,
        pop=0.70,
        current_iv=0.375,
        historical_iv=0.25
    )
    
    # High IV should slightly reduce win probability
    assert win_prob_high_iv < win_prob_normal


def test_calculate_position_size_basic():
    """Test basic position sizing."""
    result = calculate_position_size(
        capital=10000.0,
        strategy_type='CSP',
        expected_credit=100.0,
        max_loss=500.0,
        probability_itm=0.30,
        pop=0.70,
        kelly_multiplier=0.25
    )
    
    assert result.recommended_size > 0
    assert result.recommended_size < 10000.0  # Less than full capital
    assert 0 < result.win_probability < 1
    assert result.avg_win > 0
    assert result.avg_loss > 0
    assert result.kelly_multiplier == 0.25


def test_calculate_position_size_full_kelly():
    """Test full Kelly vs fractional Kelly."""
    # Quarter Kelly
    result_quarter = calculate_position_size(
        capital=10000.0,
        strategy_type='CSP',
        expected_credit=100.0,
        max_loss=500.0,
        probability_itm=0.30,
        pop=0.70,
        kelly_multiplier=0.25
    )
    
    # Half Kelly
    result_half = calculate_position_size(
        capital=10000.0,
        strategy_type='CSP',
        expected_credit=100.0,
        max_loss=500.0,
        probability_itm=0.30,
        pop=0.70,
        kelly_multiplier=0.50
    )
    
    # Full Kelly
    result_full = calculate_position_size(
        capital=10000.0,
        strategy_type='CSP',
        expected_credit=100.0,
        max_loss=500.0,
        probability_itm=0.30,
        pop=0.70,
        kelly_multiplier=1.0
    )
    
    # More aggressive Kelly should recommend larger size
    assert result_quarter.recommended_size < result_half.recommended_size
    assert result_half.recommended_size < result_full.recommended_size
    
    # Risk of ruin should increase or stay same (may be capped)
    assert result_quarter.risk_of_ruin <= result_full.risk_of_ruin


def test_calculate_position_size_min_max():
    """Test min/max position size bounds."""
    # Very small Kelly should return 0
    result_small = calculate_position_size(
        capital=1000.0,
        strategy_type='CSP',
        expected_credit=10.0,
        max_loss=50.0,
        probability_itm=0.30,
        pop=0.50,
        kelly_multiplier=0.10,
        min_position_size=500.0
    )
    
    assert result_small.recommended_size == 0.0
    
    # Max size cap
    result_capped = calculate_position_size(
        capital=100000.0,
        strategy_type='CSP',
        expected_credit=500.0,
        max_loss=2000.0,
        probability_itm=0.20,
        pop=0.80,
        kelly_multiplier=0.50,
        max_position_size=5000.0
    )
    
    assert result_capped.recommended_size <= 5000.0


def test_kelly_batch_analysis():
    """Test batch analysis of multiple opportunities."""
    opportunities = [
        {
            'strategy_type': 'CSP',
            'credit': 150.0,
            'max_loss': 700.0,
            'probability_itm': 0.25,
            'pop': 0.75,
            'symbol': 'AAPL'
        },
        {
            'strategy_type': 'IRON_CONDOR',
            'credit': 100.0,
            'max_loss': 400.0,
            'probability_itm': 0.20,
            'pop': 0.68,
            'symbol': 'SPY'
        },
        {
            'strategy_type': 'CC',
            'credit': 80.0,
            'max_loss': 300.0,
            'probability_itm': 0.35,
            'pop': 0.72,
            'symbol': 'NVDA'
        }
    ]
    
    results = kelly_batch_analysis(
        capital=20000.0,
        opportunities=opportunities,
        kelly_multiplier=0.25,
        max_total_allocation=0.50
    )
    
    # Should return results
    assert len(results) > 0
    assert len(results) <= len(opportunities)
    
    # Should be sorted by size (descending)
    sizes = [r[1].recommended_size for r in results]
    assert sizes == sorted(sizes, reverse=True)
    
    # Total allocation should not exceed cap
    total_allocated = sum(r[1].recommended_size for r in results)
    assert total_allocated <= 20000.0 * 0.50


def test_kelly_batch_allocation_cap():
    """Test that batch analysis respects total allocation cap."""
    # Create many attractive opportunities
    opportunities = [
        {
            'strategy_type': 'CSP',
            'credit': 200.0,
            'max_loss': 800.0,
            'probability_itm': 0.20,
            'pop': 0.80,
            'symbol': f'STOCK{i}'
        }
        for i in range(10)
    ]
    
    results = kelly_batch_analysis(
        capital=10000.0,
        opportunities=opportunities,
        kelly_multiplier=0.50,
        max_total_allocation=0.40  # Max 40% = $4,000
    )
    
    total_allocated = sum(r[1].recommended_size for r in results)
    assert total_allocated <= 10000.0 * 0.40


def test_format_kelly_recommendation():
    """Test recommendation formatting."""
    result = calculate_position_size(
        capital=10000.0,
        strategy_type='CSP',
        expected_credit=120.0,
        max_loss=600.0,
        probability_itm=0.28,
        pop=0.72,
        kelly_multiplier=0.25
    )
    
    formatted = format_kelly_recommendation(result)
    
    # Check key elements are present
    assert 'Kelly Position Sizing' in formatted
    assert 'CSP' in formatted
    assert '$10,000' in formatted
    assert 'Win Probability' in formatted
    assert 'Risk of Ruin' in formatted
    assert len(formatted) > 100  # Should be a decent-sized report


def test_kelly_negative_expectation():
    """Test that negative expectation returns 0 Kelly."""
    # Low win rate, big losses
    result = calculate_position_size(
        capital=10000.0,
        strategy_type='CSP',
        expected_credit=50.0,
        max_loss=500.0,
        probability_itm=0.70,  # High prob of loss
        pop=0.30,              # Low prob of profit
        kelly_multiplier=0.25
    )
    
    # Should recommend very small or zero size
    assert result.recommended_size < 100.0 or result.full_kelly < 0.05


def test_kelly_various_strategies():
    """Test Kelly calculation for different strategy types."""
    strategies = ['CSP', 'CC', 'IRON_CONDOR', 'BULL_PUT_SPREAD', 'BEAR_CALL_SPREAD']
    
    for strategy in strategies:
        result = calculate_position_size(
            capital=10000.0,
            strategy_type=strategy,
            expected_credit=100.0,
            max_loss=400.0,
            probability_itm=0.30,
            pop=0.70,
            kelly_multiplier=0.25
        )
        
        # All strategies should return valid results
        assert result.recommended_size >= 0
        assert 0 <= result.win_probability <= 1
        assert result.strategy_type == strategy


if __name__ == '__main__':
    # Run tests with verbose output
    pytest.main([__file__, '-v', '--tb=short'])
