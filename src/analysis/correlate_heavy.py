#!/usr/bin/env python3
"""
Correlate Metrics - Calculate correlation between light and heavy model scores

This program analyzes the correlation between individual metric scores from:
- scores.json (light model scores using grok-4-fast)
- scores_heavy.json (heavy model scores using grok-4-latest)

It calculates:
1. Overall correlation across all metric scores for all common tickers
2. Correlation breakdown by individual metric (e.g., moat_score, barriers_score, etc.)
3. Correlation breakdown by individual ticker

This helps understand how consistent the light and heavy models are in their scoring.
"""

import json

# Score definitions - reverse scores where lower is better
REVERSE_SCORES = {
    'disruption_risk',
    'competition_intensity',
    'riskiness_score',
    'bargaining_power_of_customers',
    'bargaining_power_of_suppliers'
}

# Score definitions from scorer.py - all metric keys
SCORE_DEFINITIONS_KEYS = [
    'moat_score',
    'barriers_score',
    'disruption_risk',
    'switching_cost',
    'brand_strength',
    'competition_intensity',
    'network_effect',
    'product_differentiation',
    'innovativeness_score',
    'growth_opportunity',
    'riskiness_score',
    'pricing_power',
    'ambition_score',
    'bargaining_power_of_customers',
    'bargaining_power_of_suppliers',
    'product_quality_score',
    'culture_employee_satisfaction_score',
    'trailblazer_score',
    'management_quality_score',
    'ai_knowledge_score'
]


def normalize_ticker(ticker):
    """Normalize ticker to uppercase for comparison."""
    return ticker.upper()


def calculate_pearson_correlation(x, y):
    """Calculate Pearson correlation coefficient manually."""
    n = len(x)
    if n != len(y) or n < 2:
        return 0.0
    
    # Calculate means
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    
    # Calculate numerator (covariance)
    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    
    # Calculate denominators (standard deviations)
    sum_sq_diff_x = sum((x[i] - mean_x) ** 2 for i in range(n))
    sum_sq_diff_y = sum((y[i] - mean_y) ** 2 for i in range(n))
    
    # Avoid division by zero
    if sum_sq_diff_x == 0 or sum_sq_diff_y == 0:
        return 0.0
    
    denominator = (sum_sq_diff_x * sum_sq_diff_y) ** 0.5
    
    correlation = numerator / denominator if denominator != 0 else 0.0
    return correlation


def main():
    """Find correlation between individual metric scores from scores.json and scores_heavy.json."""
    
    # Load both JSON files
    try:
        with open('data/scores.json', 'r') as f:
            scores_data = json.load(f)
    except FileNotFoundError:
        print("Error: data/scores.json not found")
        return
    
    try:
        with open('data/scores_heavy.json', 'r') as f:
            heavy_data = json.load(f)
    except FileNotFoundError:
        print("Error: data/scores_heavy.json not found")
        return
    
    # Get companies from both files
    companies_light = scores_data.get('companies', {})
    companies_heavy = heavy_data.get('companies', {})
    
    if not companies_light:
        print("No companies found in scores.json")
        return
    
    if not companies_heavy:
        print("No companies found in scores_heavy.json")
        return
    
    # Find common tickers (case-insensitive)
    tickers_light_normalized = {normalize_ticker(k): k for k in companies_light.keys()}
    tickers_heavy_normalized = {normalize_ticker(k): k for k in companies_heavy.keys()}
    
    common_tickers_normalized = set(tickers_light_normalized.keys()) & set(tickers_heavy_normalized.keys())
    
    if not common_tickers_normalized:
        print("No common tickers found between scores.json and scores_heavy.json")
        return
    
    # Collect all metric scores for common tickers
    light_scores = []
    heavy_scores = []
    metric_info = []  # Store (ticker, metric) pairs for reference
    
    for ticker_norm in sorted(common_tickers_normalized):
        ticker_light = tickers_light_normalized[ticker_norm]
        ticker_heavy = tickers_heavy_normalized[ticker_norm]
        
        light_data = companies_light[ticker_light]
        heavy_data_item = companies_heavy[ticker_heavy]
        
        # For each metric, collect scores (if present in both)
        for metric in SCORE_DEFINITIONS_KEYS:
            light_score_str = light_data.get(metric)
            heavy_score_str = heavy_data_item.get(metric)
            
            # Only include if both scores exist
            if light_score_str and heavy_score_str:
                try:
                    light_score = float(light_score_str)
                    heavy_score = float(heavy_score_str)
                    
                    light_scores.append(light_score)
                    heavy_scores.append(heavy_score)
                    metric_info.append((ticker_norm, metric))
                except (ValueError, TypeError):
                    # Skip invalid scores
                    continue
    
    # Calculate correlation
    if len(light_scores) < 2:
        print(f"Only {len(light_scores)} matching metric scores found. Need at least 2 for correlation.")
        return
    
    correlation = calculate_pearson_correlation(light_scores, heavy_scores)
    
    # Calculate statistics
    num_tickers = len(common_tickers_normalized)
    num_metrics = len(light_scores)
    
    # Display results
    print("\n" + "="*80)
    print("CORRELATION ANALYSIS: Individual Metric Scores")
    print("scores.json vs scores_heavy.json")
    print("="*80)
    print(f"\nCommon tickers: {num_tickers}")
    print(f"Total metric score pairs: {num_metrics}")
    print(f"\nPearson Correlation Coefficient: {correlation:.4f}")
    
    if abs(correlation) >= 0.9:
        strength = "very strong"
    elif abs(correlation) >= 0.7:
        strength = "strong"
    elif abs(correlation) >= 0.5:
        strength = "moderate"
    elif abs(correlation) >= 0.3:
        strength = "weak"
    else:
        strength = "very weak"
    
    direction = "positive" if correlation > 0 else "negative"
    print(f"Interpretation: {direction} {strength} correlation")
    
    # Show breakdown by metric
    print("\n" + "-"*80)
    print("Correlation breakdown by metric:")
    print("-"*80)
    
    metric_correlations = {}
    for metric in SCORE_DEFINITIONS_KEYS:
        metric_light_scores = []
        metric_heavy_scores = []
        
        for i, (ticker, met) in enumerate(metric_info):
            if met == metric:
                metric_light_scores.append(light_scores[i])
                metric_heavy_scores.append(heavy_scores[i])
        
        if len(metric_light_scores) >= 2:
            metric_corr = calculate_pearson_correlation(metric_light_scores, metric_heavy_scores)
            metric_correlations[metric] = (metric_corr, len(metric_light_scores))
    
    # Display metrics sorted by correlation
    sorted_metrics = sorted(metric_correlations.items(), key=lambda x: x[1][0], reverse=True)
    
    print(f"{'Metric':<35} {'Correlation':>12} {'Sample Size':>12}")
    print("-"*80)
    for metric, (corr, count) in sorted_metrics:
        metric_display = metric.replace('_', ' ').title()
        if len(metric_display) > 35:
            metric_display = metric_display[:32] + "..."
        print(f"{metric_display:<35} {corr:>12.4f} {count:>12}")
    
    # Show breakdown by ticker
    print("\n" + "-"*80)
    print("Correlation breakdown by ticker:")
    print("-"*80)
    
    ticker_correlations = {}
    for ticker_norm in sorted(common_tickers_normalized):
        ticker_light_scores = []
        ticker_heavy_scores = []
        
        for i, (tick, met) in enumerate(metric_info):
            if tick == ticker_norm:
                ticker_light_scores.append(light_scores[i])
                ticker_heavy_scores.append(heavy_scores[i])
        
        if len(ticker_light_scores) >= 2:
            ticker_corr = calculate_pearson_correlation(ticker_light_scores, ticker_heavy_scores)
            ticker_correlations[ticker_norm] = (ticker_corr, len(ticker_light_scores))
    
    # Display tickers sorted by correlation
    sorted_tickers = sorted(ticker_correlations.items(), key=lambda x: x[1][0], reverse=True)
    
    print(f"{'Ticker':<12} {'Correlation':>12} {'Metrics':>12}")
    print("-"*80)
    for ticker, (corr, count) in sorted_tickers:
        print(f"{ticker:<12} {corr:>12.4f} {count:>12}")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    main()

