#!/usr/bin/env python3
"""
Calculate correlation between total score (with size score weighted 0, others weighted 1) 
and the size/well-known score itself.
Uses binary search to find the weight of size_well_known_score that zeros out the correlation.
"""

import json
import os
import sys

# Add project root to path to allow imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Score weights (copied from scorer.py to match exactly)
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
    'ai_knowledge_score': 0,  # Not weighted - used for confidence assessment only
    'size_well_known_score': -19.31,  # Will be adjusted via binary search
}

# Score definitions (copied from scorer.py to avoid dependency on grok_client)
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


def load_excluded_tickers():
    """Load tickers from ticker_definitions.json that should be excluded.
    
    Returns:
        set: Set of ticker symbols (uppercase) to exclude
    """
    ticker_def_file = os.path.join(project_root, "data", "ticker_definitions.json")
    if not os.path.exists(ticker_def_file):
        return set()
    
    try:
        with open(ticker_def_file, 'r') as f:
            data = json.load(f)
            definitions = data.get("definitions", {})
            # Return set of uppercase ticker symbols
            return {ticker.upper() for ticker in definitions.keys()}
    except Exception as e:
        print(f"Warning: Could not load {ticker_def_file}: {e}")
        return set()


def calculate_total_score(scores_dict, size_weight=None):
    """Calculate total score from a dictionary of scores.
    
    Uses SCORE_WEIGHTS for all scores, including size_well_known_score (which has weight 0 by default).
    All scores in SCORE_DEFINITIONS are included in the calculation.
    
    Args:
        scores_dict: Dictionary with score keys and their string values
        size_weight: Optional weight for size_well_known_score (overrides SCORE_WEIGHTS if provided)
                     If None, uses SCORE_WEIGHTS['size_well_known_score'] which is 0
        
    Returns:
        float: The total weighted score (handling reverse scores appropriately)
    """
    total = 0
    for score_key in SCORE_DEFINITIONS:
        score_def = SCORE_DEFINITIONS[score_key]
        # Get weight from SCORE_WEIGHTS, with optional override for size score
        # Note: size_well_known_score is always included, but with weight 0 by default
        if score_key == 'size_well_known_score' and size_weight is not None:
            weight = size_weight
        else:
            weight = SCORE_WEIGHTS.get(score_key, 1.0)
        
        try:
            score_value = float(scores_dict.get(score_key, 0))
            # For reverse scores, invert to get "goodness" value
            # Even with weight 0, the score is still processed (just contributes 0 to total)
            if score_def['is_reverse']:
                total += (10 - score_value) * weight
            else:
                total += score_value * weight
        except (ValueError, TypeError):
            pass
    return total


def calculate_pearson_correlation(x, y):
    """Calculate Pearson correlation coefficient.
    
    Args:
        x: List of x values
        y: List of y values
        
    Returns:
        tuple: (correlation, p_value_approximation)
    """
    n = len(x)
    if n != len(y) or n < 2:
        return None, None
    
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
        return None, None
    
    denominator = (sum_sq_diff_x * sum_sq_diff_y) ** 0.5
    
    correlation = numerator / denominator if denominator != 0 else None
    
    return correlation, None


def load_scores():
    """Load scores from scores.json."""
    # Get path relative to project root
    scores_file = os.path.join(project_root, "data", "scores.json")
    if not os.path.exists(scores_file):
        print(f"Error: {scores_file} not found")
        return None
    
    try:
        with open(scores_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {scores_file}: {e}")
        return None


def calculate_correlation_for_weight(company_data, size_weight):
    """Calculate correlation for a given size_well_known_score weight.
    
    Args:
        company_data: List of dicts with 'ticker', 'scores_dict', and 'size_score'
        size_weight: Weight to use for size_well_known_score
        
    Returns:
        float: Pearson correlation coefficient, or None if calculation fails
    """
    total_scores = []
    size_scores = []
    
    for data in company_data:
        total_score = calculate_total_score(data['scores_dict'], size_weight=size_weight)
        size_score = data['size_score']
        total_scores.append(total_score)
        size_scores.append(size_score)
    
    correlation, _ = calculate_pearson_correlation(total_scores, size_scores)
    return correlation


def binary_search_zero_correlation(company_data, tolerance=1e-6, max_iterations=100):
    """Use binary search to find the weight of size_well_known_score that zeros out correlation.
    
    Args:
        company_data: List of dicts with 'ticker', 'scores_dict', and 'size_score'
        tolerance: Convergence tolerance for correlation (default 1e-6)
        max_iterations: Maximum number of iterations (default 100)
        
    Returns:
        tuple: (optimal_weight, correlation_at_optimal, iterations)
    """
    # Start with a wide range - correlation could be positive or negative
    # Use a reasonable range based on other weights (most are 10)
    low_weight = -50.0
    high_weight = 50.0
    
    # Check initial bounds
    corr_low = calculate_correlation_for_weight(company_data, low_weight)
    corr_high = calculate_correlation_for_weight(company_data, high_weight)
    
    if corr_low is None or corr_high is None:
        return None, None, 0
    
    # If both have same sign, we need to expand the range
    if (corr_low > 0 and corr_high > 0) or (corr_low < 0 and corr_high < 0):
        # Try expanding range
        low_weight = -200.0
        high_weight = 200.0
        corr_low = calculate_correlation_for_weight(company_data, low_weight)
        corr_high = calculate_correlation_for_weight(company_data, high_weight)
        if corr_low is None or corr_high is None:
            return None, None, 0
        # If still same sign, correlation might not cross zero
        if (corr_low > 0 and corr_high > 0) or (corr_low < 0 and corr_high < 0):
            return None, None, 0
    
    # Binary search
    iterations = 0
    while iterations < max_iterations:
        mid_weight = (low_weight + high_weight) / 2.0
        corr_mid = calculate_correlation_for_weight(company_data, mid_weight)
        
        if corr_mid is None:
            return None, None, iterations
        
        # Check if we're close enough to zero
        if abs(corr_mid) < tolerance:
            return mid_weight, corr_mid, iterations
        
        # Determine which side to search based on sign changes
        # We know corr_low and corr_high have opposite signs (or we wouldn't be here)
        if (corr_low > 0 and corr_mid < 0) or (corr_low < 0 and corr_mid > 0):
            # Zero crossing is between low and mid
            high_weight = mid_weight
            corr_high = corr_mid
        elif (corr_high > 0 and corr_mid < 0) or (corr_high < 0 and corr_mid > 0):
            # Zero crossing is between mid and high
            low_weight = mid_weight
            corr_low = corr_mid
        else:
            # Same sign on both sides - this shouldn't happen if initial bounds are correct
            # But handle it by moving towards the side with smaller absolute correlation
            if abs(corr_low) < abs(corr_high):
                high_weight = mid_weight
                corr_high = corr_mid
            else:
                low_weight = mid_weight
                corr_low = corr_mid
        
        iterations += 1
    
    # Return the best we found
    final_weight = (low_weight + high_weight) / 2.0
    final_corr = calculate_correlation_for_weight(company_data, final_weight)
    return final_weight, final_corr, iterations


def main():
    """Main function to calculate correlation between total score and size score."""
    print("=" * 80)
    print("Size/Well-Known Score vs Total Score Correlation Analysis")
    print("=" * 80)
    print("\nNote: Using SCORE_WEIGHTS from scorer.py")
    print("      Binary search will find weight for size_well_known_score that zeros correlation")
    
    # Load scores
    print("\nLoading scores from scores.json...")
    scores_data = load_scores()
    if not scores_data:
        return
    
    # Load excluded tickers
    excluded_tickers = load_excluded_tickers()
    if excluded_tickers:
        print(f"Excluding {len(excluded_tickers)} tickers from ticker_definitions.json")
    
    companies = scores_data.get("companies", {})
    if not companies:
        print("No companies found in scores.json")
        return
    
    print(f"Found {len(companies)} companies")
    
    # Collect data for each company
    print("\nProcessing company scores...")
    
    company_data = []
    excluded_count = 0
    missing_size_score = []
    missing_total_score = []
    
    for i, (ticker_key, scores_dict) in enumerate(companies.items(), 1):
        # Normalize ticker (handle lowercase keys)
        ticker = ticker_key.upper()
        
        # Skip tickers in ticker_definitions.json (not real tickers)
        if ticker in excluded_tickers:
            excluded_count += 1
            continue
        
        # Get size score
        try:
            size_score = float(scores_dict.get('size_well_known_score', 0))
            if size_score == 0:
                # Check if it's actually missing or just zero
                if 'size_well_known_score' not in scores_dict:
                    missing_size_score.append(ticker)
                    continue
        except (ValueError, TypeError):
            missing_size_score.append(ticker)
            continue
        
        # Calculate total score (size_well_known_score is included but with weight 0 from SCORE_WEIGHTS)
        # Passing size_weight=None uses SCORE_WEIGHTS['size_well_known_score'] which is 0
        total_score = calculate_total_score(scores_dict, size_weight=None)
        
        # Only include if we have a valid total score
        if total_score > 0:
            company_data.append({
                'ticker': ticker,
                'scores_dict': scores_dict,  # Store full scores dict for binary search
                'total_score': total_score,  # Initial total score (size weight = 0)
                'size_score': size_score
            })
        else:
            missing_total_score.append(ticker)
    
    if excluded_count > 0:
        print(f"\nExcluded {excluded_count} ticker(s) from ticker_definitions.json")
    
    if missing_size_score:
        print(f"\nWarning: {len(missing_size_score)} companies missing size_well_known_score:")
        print(f"  {', '.join(missing_size_score[:10])}" + ("..." if len(missing_size_score) > 10 else ""))
    
    if missing_total_score:
        print(f"\nWarning: {len(missing_total_score)} companies missing valid total score")
    
    if len(company_data) < 2:
        print(f"\nError: Need at least 2 companies with both total score and size score. Found {len(company_data)}")
        return
    
    print(f"\nSuccessfully processed {len(company_data)} companies")
    
    # Calculate initial correlation (with size weight = 0)
    print("\n" + "=" * 80)
    print("INITIAL CORRELATION (size_well_known_score weight = 0)")
    print("=" * 80)
    
    total_scores = [d['total_score'] for d in company_data]
    size_scores = [d['size_score'] for d in company_data]
    
    initial_correlation, _ = calculate_pearson_correlation(total_scores, size_scores)
    
    if initial_correlation is None:
        print("\nError: Could not calculate correlation (insufficient data variance)")
        return
    
    print(f"\nNumber of companies analyzed: {len(company_data)}")
    print(f"Pearson Correlation Coefficient: {initial_correlation:.4f}")
    
    # Binary search for weight that zeros correlation
    print("\n" + "=" * 80)
    print("BINARY SEARCH: Finding weight that zeros correlation")
    print("=" * 80)
    
    optimal_weight, optimal_correlation, iterations = binary_search_zero_correlation(company_data)
    
    if optimal_weight is None:
        print("\nError: Could not find weight that zeros correlation.")
        print("       Correlation may not cross zero in the searchable range.")
        return
    
    print(f"\nOptimal weight for size_well_known_score: {optimal_weight:.6f}")
    print(f"Correlation at optimal weight: {optimal_correlation:.6f}")
    print(f"Iterations: {iterations}")
    
    # Show correlation at a few different weights for context
    print("\n" + "=" * 80)
    print("CORRELATION AT VARIOUS WEIGHTS")
    print("=" * 80)
    print(f"\n{'Weight':<15} {'Correlation':>15}")
    print("-" * 32)
    
    test_weights = [-20, -10, -5, 0, 5, 10, 20, optimal_weight]
    test_weights = sorted(set(test_weights))  # Remove duplicates and sort
    
    for weight in test_weights:
        corr = calculate_correlation_for_weight(company_data, weight)
        if corr is not None:
            marker = " <-- OPTIMAL" if abs(weight - optimal_weight) < 0.01 else ""
            print(f"{weight:>14.2f} {corr:>15.6f}{marker}")
    
    # Show some examples with optimal weight
    print("\n" + "=" * 80)
    print("Sample Data (Top 10 by Total Score with Optimal Weight)")
    print("=" * 80)
    
    # Recalculate total scores with optimal weight
    for data in company_data:
        data['total_score_optimal'] = calculate_total_score(data['scores_dict'], size_weight=optimal_weight)
    
    sorted_data = sorted(company_data, key=lambda x: x['total_score_optimal'], reverse=True)
    
    # Calculate max possible total score with optimal weight
    max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS if key != 'size_well_known_score') * 10
    max_score += optimal_weight * 10  # Add size score contribution
    
    print(f"\n{'Rank':<6} {'Ticker':<8} {'Total Score %':>18} {'Size Score':>12}")
    print("-" * 50)
    
    for rank, data in enumerate(sorted_data[:10], 1):
        ticker = data['ticker']
        total_score = data['total_score_optimal']
        size_score = data['size_score']
        
        # Calculate percentage for total score
        score_pct = int((total_score / max_score) * 100) if max_score > 0 else 0
        
        print(f"{rank:<6} {ticker:<8} {score_pct:>16}% {size_score:>10.1f}/10")
    
    print("=" * 80)


if __name__ == "__main__":
    main()

