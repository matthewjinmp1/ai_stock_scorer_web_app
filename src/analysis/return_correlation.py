#!/usr/bin/env python3
"""
Calculate correlation between total scores and ranked stock returns
Loads returns from returns.json and scores from scores.json
Correlates total scores with ranked returns (not raw returns)
"""

import json
import os
from scipy.stats import pearsonr, rankdata, percentileofscore
import numpy as np

SCORES_FILE = "data/scores.json"
RETURNS_FILE = "data/returns.json"
TICKER_DEFINITIONS_FILE = "data/ticker_definitions.json"

# Score weightings - must match scorer.py
SCORE_WEIGHTS = {
    'moat_score': 10,
    'barriers_score': 10,
    'disruption_risk': 10,
    'switching_cost': 10,
    'brand_strength': 10, 
    'competition_intensity': 10,
    'network_effect': 10,
    'product_differentiation': 10,
    'innovativeness_score': 10,
    'growth_opportunity': 10,
    'riskiness_score': 10,
    'pricing_power': 10,
    'ambition_score': 10,
    'bargaining_power_of_customers': 10,
    'bargaining_power_of_suppliers': 10,
    'product_quality_score': 10,
    'culture_employee_satisfaction_score': 10,
    'trailblazer_score': 10,
    'management_quality_score': 10,
    'ai_knowledge_score': 0,
    'size_well_known_score': 0,
}

# Score definitions - must match scorer.py (only need is_reverse flag)
SCORE_DEFINITIONS = {
    'moat_score': {'is_reverse': False},
    'barriers_score': {'is_reverse': False},
    'disruption_risk': {'is_reverse': True},
    'switching_cost': {'is_reverse': False},
    'brand_strength': {'is_reverse': False},
    'competition_intensity': {'is_reverse': True},
    'network_effect': {'is_reverse': False},
    'product_differentiation': {'is_reverse': False},
    'innovativeness_score': {'is_reverse': False},
    'growth_opportunity': {'is_reverse': False},
    'riskiness_score': {'is_reverse': True},
    'pricing_power': {'is_reverse': False},
    'ambition_score': {'is_reverse': False},
    'bargaining_power_of_customers': {'is_reverse': True},
    'bargaining_power_of_suppliers': {'is_reverse': True},
    'product_quality_score': {'is_reverse': False},
    'culture_employee_satisfaction_score': {'is_reverse': False},
    'trailblazer_score': {'is_reverse': False},
    'management_quality_score': {'is_reverse': False},
    'ai_knowledge_score': {'is_reverse': False},
    'size_well_known_score': {'is_reverse': False},
}


def calculate_max_score():
    """Calculate the maximum possible total score.
    
    Returns:
        float: Maximum possible score (sum of all weights * 10, excluding weights of 0)
    """
    max_score = 0
    for score_key in SCORE_DEFINITIONS:
        weight = SCORE_WEIGHTS.get(score_key, 1.0)
        if weight > 0:  # Only include metrics with non-zero weights
            max_score += 10 * weight
    return max_score


def calculate_total_score(scores_dict):
    """Calculate total score from a dictionary of scores.
    
    Args:
        scores_dict: Dictionary with score keys and their string values
        
    Returns:
        float: The total weighted score (handling reverse scores appropriately)
    """
    total = 0
    for score_key in SCORE_DEFINITIONS:
        score_def = SCORE_DEFINITIONS[score_key]
        weight = SCORE_WEIGHTS.get(score_key, 1.0)  # Default to 1.0 if weight not found
        try:
            score_value = float(scores_dict.get(score_key, 0))
            # For reverse scores, invert to get "goodness" value
            if score_def['is_reverse']:
                total += (10 - score_value) * weight
            else:
                total += score_value * weight
        except (ValueError, TypeError):
            pass
    return total


def calculate_total_score_percent(scores_dict, max_score):
    """Calculate total score as a percentage of maximum possible score.
    
    Args:
        scores_dict: Dictionary with score keys and their string values
        max_score: Maximum possible score
        
    Returns:
        float: Total score as a percentage (0-100)
    """
    total = calculate_total_score(scores_dict)
    if max_score > 0:
        return (total / max_score) * 100
    return 0.0


def load_scores():
    """Load scores from scores.json."""
    if not os.path.exists(SCORES_FILE):
        print(f"Error: {SCORES_FILE} not found.")
        return None
    
    try:
        with open(SCORES_FILE, 'r') as f:
            data = json.load(f)
        return data.get("companies", {})
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error loading {SCORES_FILE}: {e}")
        return None


def load_returns():
    """Load returns from returns.json."""
    if not os.path.exists(RETURNS_FILE):
        print(f"Error: {RETURNS_FILE} not found.")
        print("Please run returns.py first to generate returns data.")
        return None
    
    try:
        with open(RETURNS_FILE, 'r') as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error loading {RETURNS_FILE}: {e}")
        return None


def load_excluded_tickers():
    """Load tickers to exclude from ticker_definitions.json."""
    excluded = set()
    if os.path.exists(TICKER_DEFINITIONS_FILE):
        try:
            with open(TICKER_DEFINITIONS_FILE, 'r') as f:
                data = json.load(f)
            definitions = data.get("definitions", {})
            # Extract all ticker symbols and convert to uppercase
            excluded = {ticker.upper() for ticker in definitions.keys()}
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Warning: Could not load {TICKER_DEFINITIONS_FILE}: {e}")
    return excluded


def main():
    """Main function to calculate and display correlation."""
    print("=" * 60)
    print("Score-Return Correlation Analysis")
    print("=" * 60)
    print()
    
    # Load scores
    print("Loading scores from scores.json...")
    scores_data = load_scores()
    if scores_data is None:
        return
    
    print(f"Found {len(scores_data)} companies in scores.json")
    
    # Load returns
    print("Loading returns from returns.json...")
    returns_data = load_returns()
    if returns_data is None:
        return
    
    returns_dict = returns_data.get("returns", {})
    print(f"Found {len(returns_dict)} companies in returns.json")
    
    # Get date range from returns file
    start_date = returns_data.get("start_date", "Unknown")
    end_date = returns_data.get("end_date", "Unknown")
    print(f"Returns period: {start_date} to {end_date}")
    print()
    
    # Load excluded tickers
    excluded_tickers = load_excluded_tickers()
    if excluded_tickers:
        print(f"Excluding {len(excluded_tickers)} tickers from ticker_definitions.json")
    
    # Calculate maximum possible score
    max_score = calculate_max_score()
    
    # Match companies and calculate total scores
    print("Calculating total scores and matching with returns...")
    matched_data = []
    excluded_count = 0
    no_return_data_count = 0
    failed_return_count = 0
    
    for ticker, scores_dict in scores_data.items():
        ticker_upper = ticker.upper()
        
        # Skip if ticker is in excluded list
        if ticker_upper in excluded_tickers:
            excluded_count += 1
            continue
        
        # Check if this ticker has return data
        if ticker_upper in returns_dict:
            return_info = returns_dict[ticker_upper]
            
            # Only include successful returns
            if return_info.get("status") == "success" and return_info.get("return") is not None:
                total_score = calculate_total_score(scores_dict)
                total_score_percent = calculate_total_score_percent(scores_dict, max_score)
                return_pct = return_info.get("return")
                
                matched_data.append({
                    'ticker': ticker_upper,
                    'total_score': total_score,
                    'total_score_percent': total_score_percent,
                    'return': return_pct,
                    'scores_dict': scores_dict  # Store scores dict for individual metric analysis
                })
            else:
                failed_return_count += 1
        else:
            no_return_data_count += 1
    
    # Print diagnostic information
    print()
    print("=" * 60)
    print("FILTERING SUMMARY")
    print("=" * 60)
    print(f"Total tickers in scores.json: {len(scores_data)}")
    if excluded_count > 0:
        print(f"Excluded by ticker_definitions.json: {excluded_count}")
    print(f"Missing return data in returns.json: {no_return_data_count}")
    if failed_return_count > 0:
        print(f"Return data exists but status != 'success': {failed_return_count}")
    print(f"Successfully matched: {len(matched_data)}")
    print()
    
    if len(matched_data) < 2:
        print("Error: Need at least 2 companies with both scores and returns to calculate correlation.")
        return
    
    # Extract arrays for correlation calculation
    total_scores = [d['total_score'] for d in matched_data]
    total_scores_percent = [d['total_score_percent'] for d in matched_data]
    returns = [d['return'] for d in matched_data]
    
    # Calculate percentile ranks for both total scores and returns
    # Percentile rank: percentage of values that are below this value (0-100)
    # Using 'mean' method: average of 'strict' and 'weak' percentiles for ties
    percentile_total_scores = [percentileofscore(total_scores, score, kind='mean') for score in total_scores]
    percentile_returns = [percentileofscore(returns, ret, kind='mean') for ret in returns]
    
    # Add percentile rank values to each matched_data item for later display
    for i, item in enumerate(matched_data):
        item['percentile_total_score'] = percentile_total_scores[i]
        item['percentile_return'] = percentile_returns[i]
    
    # Calculate correlation between percentile-ranked total scores and percentile-ranked returns
    # This is essentially a Spearman rank correlation using percentile ranks
    correlation, p_value = pearsonr(percentile_total_scores, percentile_returns)
    
    # Display results
    print("=" * 60)
    print("CORRELATION RESULTS")
    print("=" * 60)
    print("Note: Correlation is calculated using PERCENTILE-RANKED total scores vs PERCENTILE-RANKED returns")
    print("      (This is equivalent to Spearman rank correlation using percentile ranks)")
    print(f"Pearson Correlation Coefficient: {correlation:.4f}")
    print(f"P-value: {p_value:.6f}")
    print()
    
    # Interpret correlation
    abs_corr = abs(correlation)
    if abs_corr < 0.1:
        strength = "negligible"
    elif abs_corr < 0.3:
        strength = "weak"
    elif abs_corr < 0.5:
        strength = "moderate"
    elif abs_corr < 0.7:
        strength = "strong"
    else:
        strength = "very strong"
    
    direction = "positive" if correlation > 0 else "negative"
    
    print(f"Interpretation: {strength.capitalize()} {direction} correlation")
    if p_value < 0.05:
        print(f"Statistically significant (p < 0.05)")
    else:
        print(f"Not statistically significant (p >= 0.05)")
    print()
    
    # Display statistics
    print("=" * 60)
    print("STATISTICS")
    print("=" * 60)
    print(f"Number of companies: {len(matched_data)}")
    print()
    print("Total Scores (% of max):")
    print(f"  Mean: {np.mean(total_scores_percent):.2f}%")
    print(f"  Median: {np.median(total_scores_percent):.2f}%")
    print(f"  Min: {min(total_scores_percent):.2f}%")
    print(f"  Max: {max(total_scores_percent):.2f}%")
    print(f"  Std Dev: {np.std(total_scores_percent):.2f}%")
    print()
    print("Returns (%):")
    print(f"  Mean: {np.mean(returns):+.2f}%")
    print(f"  Median: {np.median(returns):+.2f}%")
    print(f"  Min: {min(returns):+.2f}%")
    print(f"  Max: {max(returns):+.2f}%")
    print(f"  Std Dev: {np.std(returns):.2f}%")
    print()
    print("Percentile-Ranked Total Scores (%):")
    print(f"  Mean: {np.mean(percentile_total_scores):.2f}%")
    print(f"  Median: {np.median(percentile_total_scores):.2f}%")
    print(f"  Min: {min(percentile_total_scores):.2f}%")
    print(f"  Max: {max(percentile_total_scores):.2f}%")
    print(f"  Std Dev: {np.std(percentile_total_scores):.2f}%")
    print()
    print("Percentile-Ranked Returns (%):")
    print(f"  Mean: {np.mean(percentile_returns):.2f}%")
    print(f"  Median: {np.median(percentile_returns):.2f}%")
    print(f"  Min: {min(percentile_returns):.2f}%")
    print(f"  Max: {max(percentile_returns):.2f}%")
    print(f"  Std Dev: {np.std(percentile_returns):.2f}%")
    print()
    
    # 10-Bucket Analysis: Split stocks by score percentiles
    print("=" * 60)
    print("10-BUCKET ANALYSIS BY SCORE PERCENTILE")
    print("=" * 60)
    print("Stocks are split into 10 buckets based on their total score percentile rank")
    print("Each bucket shows the median return for stocks in that score range")
    print()
    
    # Create buckets: 0-10, 10-20, 20-30, ..., 90-100
    buckets = [[] for _ in range(10)]
    
    for item in matched_data:
        # Use percentile rank (0-100) to determine bucket
        # This is the percentile rank of the score among all scores
        score_percentile_rank = item['percentile_total_score']
        # Determine which bucket (0-9) this stock belongs to
        # Bucket 0: [0, 10), Bucket 1: [10, 20), ..., Bucket 9: [90, 100]
        # For 100%, we want it in bucket 9 (90-100%)
        if score_percentile_rank >= 100:
            bucket_index = 9
        else:
            bucket_index = int(score_percentile_rank / 10)
        buckets[bucket_index].append(item)
    
    # Display results
    print(f"{'Bucket':<10} {'Score Range':<20} {'Count':<10} {'Median Return %':<20}")
    print("-" * 60)
    
    bucket_medians = []
    for i in range(10):
        bucket = buckets[i]
        if len(bucket) > 0:
            bucket_returns = [item['return'] for item in bucket]
            median_return = np.median(bucket_returns)
            bucket_medians.append(median_return)
            score_min = i * 10
            score_max = (i + 1) * 10
            if i == 9:
                score_range = f"{score_min}-{score_max}%"
            else:
                score_range = f"{score_min}-{score_max}%"
            print(f"{i+1:<10} {score_range:<20} {len(bucket):<10} {median_return:>+8.2f}%")
        else:
            bucket_medians.append(None)
            score_min = i * 10
            score_max = (i + 1) * 10
            if i == 9:
                score_range = f"{score_min}-{score_max}%"
            else:
                score_range = f"{score_min}-{score_max}%"
            print(f"{i+1:<10} {score_range:<20} {0:<10} {'N/A':<20}")
    
    print()
    
    # Show trend analysis
    valid_medians = [m for m in bucket_medians if m is not None]
    if len(valid_medians) >= 2:
        # Calculate correlation between bucket number and median return
        bucket_numbers = [i for i, m in enumerate(bucket_medians) if m is not None]
        bucket_corr, bucket_p = pearsonr(bucket_numbers, valid_medians)
        print(f"Correlation between score bucket and median return: {bucket_corr:+.4f} (p={bucket_p:.6f})")
        if bucket_corr > 0:
            print("Trend: Higher score buckets tend to have higher returns")
        elif bucket_corr < 0:
            print("Trend: Higher score buckets tend to have lower returns")
        else:
            print("Trend: No clear relationship between score buckets and returns")
    print()
    
    # Show top and bottom performers
    print("=" * 60)
    print("TOP 10 BY TOTAL SCORE")
    print("=" * 60)
    sorted_by_score = sorted(matched_data, key=lambda x: x['total_score'], reverse=True)
    print(f"{'Ticker':<10} {'Score %':<15} {'Return %':<15}")
    print("-" * 60)
    for item in sorted_by_score[:10]:
        print(f"{item['ticker']:<10} {item['total_score_percent']:>11.2f}%    {item['return']:>+8.2f}%")
    print()
    
    print("=" * 60)
    print("TOP 10 BY RETURN")
    print("=" * 60)
    sorted_by_return = sorted(matched_data, key=lambda x: x['return'], reverse=True)
    print(f"{'Ticker':<10} {'Score %':<15} {'Return %':<15}")
    print("-" * 60)
    for item in sorted_by_return[:10]:
        print(f"{item['ticker']:<10} {item['total_score_percent']:>11.2f}%    {item['return']:>+8.2f}%")
    print()
    
    # Show scatter plot data points (top and bottom)
    print("=" * 60)
    print("EXAMPLES: High Score, High Return")
    print("=" * 60)
    # Find companies with both high score and high return
    high_score_high_return = [d for d in matched_data if d['total_score_percent'] > np.median(total_scores_percent) and d['return'] > np.median(returns)]
    high_score_high_return.sort(key=lambda x: x['total_score_percent'] + x['return'], reverse=True)
    print(f"{'Ticker':<10} {'Score %':<15} {'Return %':<15}")
    print("-" * 60)
    for item in high_score_high_return[:5]:
        print(f"{item['ticker']:<10} {item['total_score_percent']:>11.2f}%    {item['return']:>+8.2f}%")
    print()
    
    print("=" * 60)
    print("EXAMPLES: Low Score, Low Return")
    print("=" * 60)
    # Find companies with both low score and low return
    low_score_low_return = [d for d in matched_data if d['total_score_percent'] < np.median(total_scores_percent) and d['return'] < np.median(returns)]
    low_score_low_return.sort(key=lambda x: x['total_score_percent'] + x['return'])
    print(f"{'Ticker':<10} {'Score %':<15} {'Return %':<15}")
    print("-" * 60)
    for item in low_score_low_return[:5]:
        print(f"{item['ticker']:<10} {item['total_score_percent']:>11.2f}%    {item['return']:>+8.2f}%")
    print()
    
    # Calculate correlations for individual metrics
    print("=" * 60)
    print("INDIVIDUAL METRIC CORRELATIONS WITH RETURNS")
    print("=" * 60)
    print("Note: Correlations are between PERCENTILE-RANKED metric scores and PERCENTILE-RANKED returns")
    print()
    
    metric_correlations = []
    
    # Create display name mapping for better readability
    display_name_map = {
        'moat_score': 'Competitive Moat',
        'barriers_score': 'Barriers to Entry',
        'disruption_risk': 'Disruption Risk',
        'switching_cost': 'Switching Cost',
        'brand_strength': 'Brand Strength',
        'competition_intensity': 'Competition Intensity',
        'network_effect': 'Network Effect',
        'product_differentiation': 'Product Differentiation',
        'innovativeness_score': 'Innovativeness',
        'growth_opportunity': 'Growth Opportunity',
        'riskiness_score': 'Riskiness',
        'pricing_power': 'Pricing Power',
        'ambition_score': 'Ambition',
        'bargaining_power_of_customers': 'Bargaining Power of Customers',
        'bargaining_power_of_suppliers': 'Bargaining Power of Suppliers',
        'product_quality_score': 'Product / Service Quality',
        'culture_employee_satisfaction_score': 'Culture / Employee Satisfaction',
        'trailblazer_score': 'Trailblazer',
        'management_quality_score': 'Management Quality',
        'ai_knowledge_score': 'AI Knowledge / Confidence',
        'size_well_known_score': 'Size / Well Known',
    }
    
    for score_key in SCORE_DEFINITIONS:
        score_def = SCORE_DEFINITIONS[score_key]
        display_name = display_name_map.get(score_key, score_key.replace('_', ' ').title())
        
        # Extract metric scores for all companies
        metric_scores = []
        valid_indices = []  # Track which companies have valid scores for this metric
        
        for i, item in enumerate(matched_data):
            scores_dict = item['scores_dict']
            score_value_str = scores_dict.get(score_key)
            
            # Handle moat_score backwards compatibility
            if score_key == 'moat_score' and not score_value_str:
                score_value_str = scores_dict.get('score')
            
            if score_value_str:
                try:
                    score_value = float(score_value_str)
                    # For reverse scores, invert to get "goodness" value
                    if score_def['is_reverse']:
                        score_value = 10 - score_value
                    metric_scores.append(score_value)
                    valid_indices.append(i)
                except (ValueError, TypeError):
                    continue
        
        # Need at least 2 companies with valid scores for this metric
        if len(metric_scores) < 2:
            continue
        
        # Calculate percentile ranks for this metric
        percentile_metric_scores = [percentileofscore(metric_scores, score, kind='mean') for score in metric_scores]
        
        # Get corresponding return percentiles for companies with valid metric scores
        corresponding_return_percentiles = [percentile_returns[i] for i in valid_indices]
        
        # Calculate correlation
        if len(percentile_metric_scores) >= 2 and len(corresponding_return_percentiles) >= 2:
            try:
                corr, p_val = pearsonr(percentile_metric_scores, corresponding_return_percentiles)
                metric_correlations.append({
                    'metric': score_key,
                    'display_name': display_name,
                    'correlation': corr,
                    'p_value': p_val,
                    'n': len(percentile_metric_scores)
                })
            except:
                continue
    
    # Sort by absolute correlation (strongest first)
    metric_correlations.sort(key=lambda x: abs(x['correlation']), reverse=True)
    
    # Display results
    print(f"{'Metric':<40} {'Correlation':<15} {'P-value':<15} {'N':<10} {'Significant':<15}")
    print("-" * 95)
    
    for metric_info in metric_correlations:
        corr = metric_info['correlation']
        p_val = metric_info['p_value']
        n = metric_info['n']
        display_name = metric_info['display_name']
        
        # Truncate long metric names
        if len(display_name) > 38:
            display_name = display_name[:35] + "..."
        
        significant = "Yes" if p_val < 0.05 else "No"
        corr_str = f"{corr:+.4f}"
        p_val_str = f"{p_val:.6f}"
        
        print(f"{display_name:<40} {corr_str:<15} {p_val_str:<15} {n:<10} {significant:<15}")
    
    print()
    
    # Show all tickers ranked by total score
    print("=" * 60)
    print("ALL TICKERS RANKED BY TOTAL SCORE")
    print("=" * 60)
    sorted_by_score = sorted(matched_data, key=lambda x: x['total_score'], reverse=True)
    print(f"{'Rank':<6} {'Ticker':<10} {'Score %':<15} {'Return %':<15} {'Score Pctile':<15} {'Return Pctile':<15}")
    print("-" * 85)
    for rank, item in enumerate(sorted_by_score, 1):
        print(f"{rank:<6} {item['ticker']:<10} {item['total_score_percent']:>11.2f}%    {item['return']:>+8.2f}%    {item['percentile_total_score']:>12.2f}%    {item['percentile_return']:>12.2f}%")
    print()


if __name__ == "__main__":
    main()

