"""
Validation Plan for Multi-Strategy Scoring System

This script validates that the weighted scoring system provides reliable
cross-strategy comparisons for risk-reward evaluation.

Validation Objectives:
1. Component Independence: Verify score components measure distinct aspects
2. Weight Sensitivity: Test how weight changes affect rankings
3. Correlation Analysis: Check if scores correlate with realized outcomes
4. Edge Case Robustness: Test extreme scenarios
5. Cross-Strategy Fairness: Ensure no systematic bias toward any strategy
6. Real-World Alignment: Compare scores with trader intuition/best practices
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from scipy.stats import spearmanr, pearsonr
import seaborn as sns

# Scoring formula (same across all strategies):
# score = 0.35 * roi + 0.15 * cushion + 0.30 * tg_score + 0.20 * liq_score

def calculate_score(roi, cushion, tg_score, liq_score):
    """Calculate score using current weights."""
    cushion_norm = min(cushion, 3.0) / 3.0 if cushion > 0 else 0
    return (0.35 * roi + 
            0.15 * cushion_norm + 
            0.30 * tg_score + 
            0.20 * liq_score)

def generate_synthetic_opportunities():
    """
    Generate synthetic trading opportunities across strategies.
    These represent realistic parameter ranges from actual market data.
    """
    np.random.seed(42)
    n = 100
    
    opportunities = []
    
    # Cash Secured Puts
    for i in range(n):
        roi = np.random.uniform(0.10, 0.50)  # 10-50% annualized
        cushion = np.random.uniform(0.5, 3.5)  # 0.5-3.5 sigma
        tg_ratio = np.random.uniform(0.5, 8.0)  # Theta/Gamma ratio
        spread_pct = np.random.uniform(2.0, 15.0)  # 2-15% spread
        
        # Convert to scores
        if tg_ratio < 0.5:
            tg_score = 0.0
        elif tg_ratio < 0.8:
            tg_score = tg_ratio / 0.8
        elif tg_ratio <= 3.0:
            tg_score = 1.0
        elif tg_ratio <= 5.0:
            tg_score = 1.0 - (tg_ratio - 3.0) * 0.25
        elif tg_ratio <= 10.0:
            tg_score = 0.5 - (tg_ratio - 5.0) * 0.06
        else:
            tg_score = 0.1
        
        liq_score = max(0.0, 1.0 - min(spread_pct, 20.0) / 20.0)
        
        score = calculate_score(roi, cushion, tg_score, liq_score)
        
        # Simulate "true quality" - what an expert would rate this (0-100)
        # Higher ROI, cushion, good TG ratio, good liquidity = higher quality
        true_quality = (
            30 * roi +  # ROI most important
            20 * min(cushion / 3.0, 1.0) +  # Cushion
            25 * tg_score +  # Risk profile
            15 * liq_score +  # Liquidity
            np.random.normal(0, 5)  # Expert variation
        )
        true_quality = max(0, min(100, true_quality))
        
        opportunities.append({
            'strategy': 'CSP',
            'roi': roi,
            'cushion': cushion,
            'tg_ratio': tg_ratio,
            'tg_score': tg_score,
            'spread_pct': spread_pct,
            'liq_score': liq_score,
            'score': score,
            'true_quality': true_quality,
            'capital': 10000,
            'max_profit': roi * 10000,
            'max_loss': 10000
        })
    
    # Bull Put Spreads (credit spreads with capped ROI)
    for i in range(n):
        roi_raw = np.random.uniform(0.50, 2.50)  # 50-250% raw
        roi = min(roi_raw, 1.0)  # Capped at 100% for scoring
        cushion = np.random.uniform(0.5, 3.5)
        tg_ratio = np.random.uniform(0.5, 8.0)
        spread_pct = np.random.uniform(3.0, 20.0)  # Usually wider spreads
        
        if tg_ratio < 0.5:
            tg_score = 0.0
        elif tg_ratio < 0.8:
            tg_score = tg_ratio / 0.8
        elif tg_ratio <= 3.0:
            tg_score = 1.0
        elif tg_ratio <= 5.0:
            tg_score = 1.0 - (tg_ratio - 3.0) * 0.25
        elif tg_ratio <= 10.0:
            tg_score = 0.5 - (tg_ratio - 5.0) * 0.06
        else:
            tg_score = 0.1
        
        liq_score = max(0.0, 1.0 - min(spread_pct, 20.0) / 20.0)
        
        score = calculate_score(roi, cushion, tg_score, liq_score)
        
        # True quality considers raw ROI but with diminishing returns
        roi_for_quality = min(roi_raw / 2.0, 0.8)  # Cap at 80% for quality
        true_quality = (
            30 * roi_for_quality +
            20 * min(cushion / 3.0, 1.0) +
            25 * tg_score +
            15 * liq_score +
            np.random.normal(0, 5)
        )
        true_quality = max(0, min(100, true_quality))
        
        capital = 500  # Max loss on spread
        opportunities.append({
            'strategy': 'BullPutSpread',
            'roi': roi,
            'roi_raw': roi_raw,
            'cushion': cushion,
            'tg_ratio': tg_ratio,
            'tg_score': tg_score,
            'spread_pct': spread_pct,
            'liq_score': liq_score,
            'score': score,
            'true_quality': true_quality,
            'capital': capital,
            'max_profit': roi_raw * capital,
            'max_loss': capital
        })
    
    # Covered Calls
    for i in range(n):
        roi = np.random.uniform(0.08, 0.35)  # 8-35% annualized
        cushion = np.random.uniform(1.0, 4.0)  # Usually more OTM
        tg_ratio = np.random.uniform(0.8, 10.0)
        spread_pct = np.random.uniform(2.0, 12.0)
        
        if tg_ratio < 0.5:
            tg_score = 0.0
        elif tg_ratio < 0.8:
            tg_score = tg_ratio / 0.8
        elif tg_ratio <= 3.0:
            tg_score = 1.0
        elif tg_ratio <= 5.0:
            tg_score = 1.0 - (tg_ratio - 3.0) * 0.25
        elif tg_ratio <= 10.0:
            tg_score = 0.5 - (tg_ratio - 5.0) * 0.06
        else:
            tg_score = 0.1
        
        liq_score = max(0.0, 1.0 - min(spread_pct, 20.0) / 20.0)
        
        score = calculate_score(roi, cushion, tg_score, liq_score)
        
        true_quality = (
            30 * roi +
            20 * min(cushion / 4.0, 1.0) +  # CCs can be further OTM
            25 * tg_score +
            15 * liq_score +
            np.random.normal(0, 5)
        )
        true_quality = max(0, min(100, true_quality))
        
        opportunities.append({
            'strategy': 'CoveredCall',
            'roi': roi,
            'cushion': cushion,
            'tg_ratio': tg_ratio,
            'tg_score': tg_score,
            'spread_pct': spread_pct,
            'liq_score': liq_score,
            'score': score,
            'true_quality': true_quality,
            'capital': 10000,
            'max_profit': roi * 10000,
            'max_loss': 10000  # (plus upside cap)
        })
    
    # Iron Condors
    for i in range(n):
        roi_raw = np.random.uniform(0.60, 3.00)  # 60-300% raw
        roi = min(roi_raw, 1.0)  # Capped
        cushion = np.random.uniform(0.8, 3.0)  # Tighter than single spreads
        tg_ratio = np.random.uniform(0.6, 7.0)
        spread_pct = np.random.uniform(5.0, 25.0)  # Often wider
        
        if tg_ratio < 0.5:
            tg_score = 0.0
        elif tg_ratio < 0.8:
            tg_score = tg_ratio / 0.8
        elif tg_ratio <= 3.0:
            tg_score = 1.0
        elif tg_ratio <= 5.0:
            tg_score = 1.0 - (tg_ratio - 3.0) * 0.25
        elif tg_ratio <= 10.0:
            tg_score = 0.5 - (tg_ratio - 5.0) * 0.06
        else:
            tg_score = 0.1
        
        liq_score = max(0.0, 1.0 - min(spread_pct, 20.0) / 20.0)
        
        score = calculate_score(roi, cushion, tg_score, liq_score)
        
        roi_for_quality = min(roi_raw / 2.5, 0.7)
        true_quality = (
            30 * roi_for_quality +
            20 * min(cushion / 3.0, 1.0) +
            25 * tg_score +
            15 * liq_score +
            np.random.normal(0, 7)  # More variation (complex strategy)
        )
        true_quality = max(0, min(100, true_quality))
        
        capital = 1000
        opportunities.append({
            'strategy': 'IronCondor',
            'roi': roi,
            'roi_raw': roi_raw,
            'cushion': cushion,
            'tg_ratio': tg_ratio,
            'tg_score': tg_score,
            'spread_pct': spread_pct,
            'liq_score': liq_score,
            'score': score,
            'true_quality': true_quality,
            'capital': capital,
            'max_profit': roi_raw * capital,
            'max_loss': capital
        })
    
    return pd.DataFrame(opportunities)


def test_component_independence(df):
    """
    Test 1: Component Independence
    Verify that score components measure distinct aspects.
    """
    print("\n" + "="*70)
    print("TEST 1: COMPONENT INDEPENDENCE")
    print("="*70)
    print("\nChecking correlations between score components...")
    
    components = ['roi', 'cushion', 'tg_score', 'liq_score']
    corr_matrix = df[components].corr()
    
    print("\nCorrelation Matrix:")
    print(corr_matrix.round(3))
    
    # Check for high correlations (>0.7 is concerning)
    high_corr = []
    for i in range(len(components)):
        for j in range(i+1, len(components)):
            corr = abs(corr_matrix.iloc[i, j])
            if corr > 0.7:
                high_corr.append((components[i], components[j], corr))
    
    if high_corr:
        print("\n⚠️  WARNING: High correlations detected:")
        for c1, c2, corr in high_corr:
            print(f"   {c1} <-> {c2}: {corr:.3f}")
        result = "CONCERN"
    else:
        print("\n✅ All components show low correlation (<0.7)")
        print("   Components are measuring independent aspects")
        result = "PASS"
    
    return {
        'test': 'Component Independence',
        'result': result,
        'max_correlation': corr_matrix.values[np.triu_indices_from(corr_matrix.values, k=1)].max(),
        'details': corr_matrix
    }


def test_weight_sensitivity(df):
    """
    Test 2: Weight Sensitivity Analysis
    Test how changes to weights affect strategy rankings.
    """
    print("\n" + "="*70)
    print("TEST 2: WEIGHT SENSITIVITY ANALYSIS")
    print("="*70)
    
    # Current weights
    base_weights = {'roi': 0.35, 'cushion': 0.15, 'tg': 0.30, 'liq': 0.20}
    
    # Test alternative weight schemes
    weight_schemes = {
        'Current': base_weights,
        'ROI-Heavy': {'roi': 0.50, 'cushion': 0.15, 'tg': 0.20, 'liq': 0.15},
        'Risk-Heavy': {'roi': 0.25, 'cushion': 0.25, 'tg': 0.35, 'liq': 0.15},
        'Balanced': {'roi': 0.25, 'cushion': 0.25, 'tg': 0.25, 'liq': 0.25},
    }
    
    results = []
    for scheme_name, weights in weight_schemes.items():
        scores = []
        for _, row in df.iterrows():
            cushion_norm = min(row['cushion'], 3.0) / 3.0
            score = (weights['roi'] * row['roi'] + 
                    weights['cushion'] * cushion_norm +
                    weights['tg'] * row['tg_score'] +
                    weights['liq'] * row['liq_score'])
            scores.append(score)
        
        df[f'score_{scheme_name}'] = scores
        
        # Get top 10 by strategy
        top_10 = df.nlargest(10, f'score_{scheme_name}')
        strategy_dist = top_10['strategy'].value_counts()
        
        results.append({
            'scheme': scheme_name,
            'top_10_distribution': strategy_dist.to_dict(),
            'mean_score': np.mean(scores),
            'std_score': np.std(scores)
        })
    
    print("\nTop 10 Strategy Distribution by Weight Scheme:")
    print("-" * 70)
    for r in results:
        print(f"\n{r['scheme']}:")
        for strat, count in sorted(r['top_10_distribution'].items(), key=lambda x: -x[1]):
            print(f"  {strat}: {count}")
    
    # Check stability - how much do rankings change?
    base_rank = df['score_Current'].rank(ascending=False)
    rank_correlations = {}
    for scheme in weight_schemes.keys():
        if scheme != 'Current':
            scheme_rank = df[f'score_{scheme}'].rank(ascending=False)
            corr, _ = spearmanr(base_rank, scheme_rank)
            rank_correlations[scheme] = corr
    
    print("\n\nRank Correlation with Current Weights:")
    print("-" * 70)
    for scheme, corr in rank_correlations.items():
        print(f"  {scheme}: {corr:.3f}")
    
    min_corr = min(rank_correlations.values())
    if min_corr > 0.85:
        print("\n✅ Rankings are stable across weight schemes (>0.85)")
        result = "PASS"
    elif min_corr > 0.70:
        print(f"\n⚠️  Moderate sensitivity detected (min={min_corr:.3f})")
        result = "CONCERN"
    else:
        print(f"\n❌ High sensitivity - rankings change significantly (min={min_corr:.3f})")
        result = "FAIL"
    
    return {
        'test': 'Weight Sensitivity',
        'result': result,
        'min_correlation': min_corr,
        'details': results
    }


def test_score_quality_correlation(df):
    """
    Test 3: Score vs True Quality Correlation
    Check if scores correlate with "true quality" (expert assessment).
    """
    print("\n" + "="*70)
    print("TEST 3: SCORE VS TRUE QUALITY CORRELATION")
    print("="*70)
    
    # Overall correlation
    corr_pearson, p_pearson = pearsonr(df['score'], df['true_quality'])
    corr_spearman, p_spearman = spearmanr(df['score'], df['true_quality'])
    
    print(f"\nOverall Correlation:")
    print(f"  Pearson:  r={corr_pearson:.3f}, p={p_pearson:.4f}")
    print(f"  Spearman: ρ={corr_spearman:.3f}, p={p_spearman:.4f}")
    
    # Per-strategy correlation
    print("\n\nPer-Strategy Correlation:")
    print("-" * 70)
    strategy_corrs = []
    for strategy in df['strategy'].unique():
        strat_df = df[df['strategy'] == strategy]
        corr, p = pearsonr(strat_df['score'], strat_df['true_quality'])
        strategy_corrs.append(corr)
        print(f"  {strategy:15s}: r={corr:.3f}, p={p:.4f}")
    
    min_strategy_corr = min(strategy_corrs)
    
    if corr_pearson > 0.70 and min_strategy_corr > 0.60:
        print("\n✅ Strong correlation between scores and quality")
        result = "PASS"
    elif corr_pearson > 0.50 and min_strategy_corr > 0.40:
        print("\n⚠️  Moderate correlation - acceptable but could improve")
        result = "CONCERN"
    else:
        print("\n❌ Weak correlation - scores don't reflect true quality")
        result = "FAIL"
    
    return {
        'test': 'Score-Quality Correlation',
        'result': result,
        'pearson_r': corr_pearson,
        'spearman_rho': corr_spearman,
        'min_strategy_corr': min_strategy_corr
    }


def test_cross_strategy_fairness(df):
    """
    Test 4: Cross-Strategy Fairness
    Ensure no systematic bias toward any strategy.
    """
    print("\n" + "="*70)
    print("TEST 4: CROSS-STRATEGY FAIRNESS")
    print("="*70)
    
    # Analyze score distributions by strategy
    print("\nScore Statistics by Strategy:")
    print("-" * 70)
    
    stats = []
    for strategy in df['strategy'].unique():
        strat_df = df[df['strategy'] == strategy]
        mean = strat_df['score'].mean()
        median = strat_df['score'].median()
        std = strat_df['score'].std()
        
        stats.append({
            'strategy': strategy,
            'mean': mean,
            'median': median,
            'std': std,
            'count': len(strat_df)
        })
        
        print(f"\n{strategy}:")
        print(f"  Mean:   {mean:.4f}")
        print(f"  Median: {median:.4f}")
        print(f"  Std:    {std:.4f}")
        print(f"  Count:  {len(strat_df)}")
    
    stats_df = pd.DataFrame(stats)
    
    # Check if means are within reasonable range (±20%)
    overall_mean = df['score'].mean()
    max_deviation = stats_df['mean'].apply(lambda x: abs(x - overall_mean) / overall_mean).max()
    
    print(f"\n\nOverall Mean Score: {overall_mean:.4f}")
    print(f"Max Deviation: {max_deviation*100:.1f}%")
    
    # Check representation in top percentiles
    print("\n\nStrategy Distribution in Top Percentiles:")
    print("-" * 70)
    
    percentiles = [90, 95, 99]
    top_dist = []
    for pct in percentiles:
        threshold = df['score'].quantile(pct / 100)
        top_df = df[df['score'] >= threshold]
        dist = top_df['strategy'].value_counts(normalize=True) * 100
        
        print(f"\nTop {100-pct}% (score >= {threshold:.4f}):")
        for strat, pct_val in dist.items():
            print(f"  {strat:15s}: {pct_val:.1f}%")
        
        top_dist.append(dist.to_dict())
    
    # Fairness check: each strategy should appear roughly equally (±15%)
    if max_deviation < 0.15:
        print("\n✅ No systematic bias - mean scores within 15%")
        result = "PASS"
    elif max_deviation < 0.25:
        print(f"\n⚠️  Moderate bias detected - max deviation {max_deviation*100:.1f}%")
        result = "CONCERN"
    else:
        print(f"\n❌ Significant bias - max deviation {max_deviation*100:.1f}%")
        result = "FAIL"
    
    return {
        'test': 'Cross-Strategy Fairness',
        'result': result,
        'max_deviation': max_deviation,
        'stats': stats_df,
        'top_distributions': top_dist
    }


def test_edge_cases(df):
    """
    Test 5: Edge Case Robustness
    Test extreme scenarios.
    """
    print("\n" + "="*70)
    print("TEST 5: EDGE CASE ROBUSTNESS")
    print("="*70)
    
    edge_cases = [
        {
            'name': 'Perfect Opportunity',
            'roi': 0.50,
            'cushion': 3.0,
            'tg_score': 1.0,
            'liq_score': 1.0,
            'expected_high': True
        },
        {
            'name': 'High ROI, High Risk',
            'roi': 1.0,
            'cushion': 0.5,
            'tg_score': 0.1,
            'liq_score': 0.3,
            'expected_high': False
        },
        {
            'name': 'Low ROI, Low Risk',
            'roi': 0.10,
            'cushion': 3.0,
            'tg_score': 1.0,
            'liq_score': 0.9,
            'expected_high': False
        },
        {
            'name': 'Zero Everything',
            'roi': 0.0,
            'cushion': 0.0,
            'tg_score': 0.0,
            'liq_score': 0.0,
            'expected_high': False
        },
        {
            'name': 'Illiquid High ROI',
            'roi': 0.80,
            'cushion': 2.0,
            'tg_score': 0.8,
            'liq_score': 0.1,
            'expected_high': False
        }
    ]
    
    print("\nEdge Case Scores:")
    print("-" * 70)
    
    issues = []
    for case in edge_cases:
        score = calculate_score(case['roi'], case['cushion'], 
                              case['tg_score'], case['liq_score'])
        
        # Check if score matches expectation
        high_score = score > 0.70
        matches_expectation = high_score == case['expected_high']
        
        status = "✅" if matches_expectation else "❌"
        print(f"\n{status} {case['name']}:")
        print(f"   ROI: {case['roi']:.2f}, Cushion: {case['cushion']:.2f}")
        print(f"   TG: {case['tg_score']:.2f}, Liq: {case['liq_score']:.2f}")
        print(f"   Score: {score:.4f}")
        print(f"   Expected {'high' if case['expected_high'] else 'not high'}: {matches_expectation}")
        
        if not matches_expectation:
            issues.append(case['name'])
    
    if not issues:
        print("\n✅ All edge cases behave as expected")
        result = "PASS"
    else:
        print(f"\n❌ Issues with: {', '.join(issues)}")
        result = "FAIL"
    
    return {
        'test': 'Edge Case Robustness',
        'result': result,
        'issues': issues
    }


def test_real_world_alignment():
    """
    Test 6: Real-World Alignment
    Compare with options trading best practices.
    """
    print("\n" + "="*70)
    print("TEST 6: REAL-WORLD ALIGNMENT")
    print("="*70)
    
    # Test scenarios based on actual trader preferences
    scenarios = [
        {
            'name': 'Conservative CSP (Best Practice)',
            'strategy': 'CSP',
            'roi': 0.25,  # 25% annual
            'cushion': 2.5,  # 2.5 sigma
            'tg_ratio': 1.5,  # Sweet spot
            'spread_pct': 3.0,
            'should_rank': 'high'
        },
        {
            'name': 'Aggressive Credit Spread (Risky)',
            'strategy': 'BullPutSpread',
            'roi': 2.0,  # 200% (capped to 100%)
            'cushion': 0.8,  # Tight
            'tg_ratio': 0.4,  # Gamma risk
            'spread_pct': 15.0,
            'should_rank': 'low'
        },
        {
            'name': 'Conservative IC (Good)',
            'strategy': 'IronCondor',
            'roi': 1.5,  # 150% (capped to 100%)
            'cushion': 2.0,
            'tg_ratio': 2.0,
            'spread_pct': 8.0,
            'should_rank': 'high'
        },
        {
            'name': 'Illiquid High Premium (Bad)',
            'strategy': 'CSP',
            'roi': 0.45,
            'cushion': 1.5,
            'tg_ratio': 1.2,
            'spread_pct': 22.0,  # Very wide
            'should_rank': 'low'
        }
    ]
    
    print("\nReal-World Scenario Rankings:")
    print("-" * 70)
    
    scenario_scores = []
    for scenario in scenarios:
        # Calculate theta/gamma score
        tg_ratio = scenario['tg_ratio']
        if tg_ratio < 0.5:
            tg_score = 0.0
        elif tg_ratio < 0.8:
            tg_score = tg_ratio / 0.8
        elif tg_ratio <= 3.0:
            tg_score = 1.0
        elif tg_ratio <= 5.0:
            tg_score = 1.0 - (tg_ratio - 3.0) * 0.25
        else:
            tg_score = 0.5
        
        # Liquidity score
        liq_score = max(0.0, 1.0 - min(scenario['spread_pct'], 20.0) / 20.0)
        
        # ROI (capped for credit spreads)
        roi = min(scenario['roi'], 1.0) if scenario['strategy'] in ['BullPutSpread', 'IronCondor'] else scenario['roi']
        
        score = calculate_score(roi, scenario['cushion'], tg_score, liq_score)
        
        scenario_scores.append({
            'name': scenario['name'],
            'score': score,
            'should_rank': scenario['should_rank']
        })
        
        print(f"\n{scenario['name']}:")
        print(f"  Strategy: {scenario['strategy']}")
        print(f"  Score: {score:.4f}")
        print(f"  Should rank: {scenario['should_rank']}")
    
    # Sort by score
    scenario_scores.sort(key=lambda x: x['score'], reverse=True)
    
    print("\n\nRanking Order:")
    print("-" * 70)
    for i, s in enumerate(scenario_scores, 1):
        expected_high = s['should_rank'] == 'high'
        actual_high = i <= 2
        status = "✅" if expected_high == actual_high else "❌"
        print(f"{i}. {status} {s['name']:40s} (score: {s['score']:.4f})")
    
    # Check alignment
    high_ranked_correctly = sum(1 for i, s in enumerate(scenario_scores, 1) 
                                if (s['should_rank'] == 'high') == (i <= 2))
    
    if high_ranked_correctly >= 3:
        print("\n✅ Scoring aligns with trading best practices")
        result = "PASS"
    elif high_ranked_correctly >= 2:
        print("\n⚠️  Partial alignment with best practices")
        result = "CONCERN"
    else:
        print("\n❌ Poor alignment with trading best practices")
        result = "FAIL"
    
    return {
        'test': 'Real-World Alignment',
        'result': result,
        'correct_rankings': high_ranked_correctly,
        'total_scenarios': len(scenarios)
    }


def main():
    """Execute validation plan and generate report."""
    print("\n" + "="*70)
    print("MULTI-STRATEGY SCORING VALIDATION")
    print("="*70)
    print("\nGenerating synthetic trading opportunities...")
    
    df = generate_synthetic_opportunities()
    print(f"✓ Generated {len(df)} opportunities across {df['strategy'].nunique()} strategies")
    
    # Run all tests
    results = []
    results.append(test_component_independence(df))
    results.append(test_weight_sensitivity(df))
    results.append(test_score_quality_correlation(df))
    results.append(test_cross_strategy_fairness(df))
    results.append(test_edge_cases(df))
    results.append(test_real_world_alignment())
    
    # Summary Report
    print("\n\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)
    
    print("\nTest Results:")
    print("-" * 70)
    
    pass_count = sum(1 for r in results if r['result'] == 'PASS')
    concern_count = sum(1 for r in results if r['result'] == 'CONCERN')
    fail_count = sum(1 for r in results if r['result'] == 'FAIL')
    
    for r in results:
        status_symbol = {
            'PASS': '✅',
            'CONCERN': '⚠️ ',
            'FAIL': '❌'
        }[r['result']]
        print(f"{status_symbol} {r['test']:35s}: {r['result']}")
    
    print(f"\n\nOverall: {pass_count} passed, {concern_count} concerns, {fail_count} failed")
    
    # Recommendations
    print("\n\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)
    
    if fail_count == 0 and concern_count == 0:
        print("\n✅ SCORING SYSTEM IS RELIABLE")
        print("\nThe weighted scoring system provides:")
        print("  • Independent component measurements")
        print("  • Stable rankings across weight variations")
        print("  • Strong correlation with quality assessments")
        print("  • Fair treatment of all strategies")
        print("  • Robust behavior in edge cases")
        print("  • Alignment with trading best practices")
        print("\n→ No changes recommended. System is production-ready.")
    
    elif fail_count == 0:
        print("\n⚠️  SCORING SYSTEM IS GENERALLY RELIABLE WITH MINOR CONCERNS")
        print("\nRecommendations:")
        for r in results:
            if r['result'] == 'CONCERN':
                print(f"\n• {r['test']}:")
                if 'Weight Sensitivity' in r['test']:
                    print("  - Consider documenting weight rationale")
                    print("  - Monitor if rankings change unexpectedly")
                elif 'Fairness' in r['test']:
                    print("  - Monitor strategy distribution in production")
                    print("  - Consider per-strategy score normalization")
                elif 'Correlation' in r['test']:
                    print("  - Validate with real trade outcomes")
                    print("  - Consider adding success rate tracking")
        
        print("\n→ System is usable but should be monitored.")
    
    else:
        print("\n❌ SCORING SYSTEM NEEDS IMPROVEMENT")
        print("\nCritical Issues:")
        for r in results:
            if r['result'] == 'FAIL':
                print(f"\n• {r['test']}:")
                if 'Independence' in r['test']:
                    print("  → Recommendation: Revise component definitions")
                    print("    High correlation suggests redundancy")
                elif 'Sensitivity' in r['test']:
                    print("  → Recommendation: Stabilize weights")
                    print("    Rankings should not change dramatically")
                elif 'Correlation' in r['test']:
                    print("  → Recommendation: Adjust weight ratios")
                    print("    Score should predict quality better")
                elif 'Fairness' in r['test']:
                    print("  → Recommendation: Normalize by strategy")
                    print("    Ensure equal opportunity for all strategies")
                elif 'Edge' in r['test']:
                    print("  → Recommendation: Add boundary checks")
                    print("    Handle extreme cases explicitly")
                elif 'Real-World' in r['test']:
                    print("  → Recommendation: Recalibrate weights")
                    print("    Align with trader experience")
        
        print("\n→ Address critical issues before production use.")
    
    print("\n" + "="*70)
    
    return results, df


if __name__ == "__main__":
    results, df = main()
    
    # Save results
    print("\n💾 Saving validation data to 'scoring_validation_results.csv'")
    df.to_csv('/workspaces/put_scanner/scoring_validation_results.csv', index=False)
    print("✓ Data saved")
