import json

# Score definitions - reverse scores where lower is better
REVERSE_SCORES = {
    'disruption_risk',
    'competition_intensity',
    'riskiness_score',
    'bargaining_power_of_customers',
    'bargaining_power_of_suppliers'
}

# Score weights (all are 10)
SCORE_WEIGHT = 10

# Score definitions from scorer.py (simplified - we only need the keys)
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
    'trailblazer_score'
]

SCORE_WEIGHTS = {key: 10 for key in SCORE_DEFINITIONS_KEYS}

SCORE_DEFINITIONS = {
    key: {'is_reverse': key in REVERSE_SCORES} 
    for key in SCORE_DEFINITIONS_KEYS
}


def calculate_total_score(scores_dict):
    """Calculate total score from a dictionary of scores.
    
    Args:
        scores_dict: Dictionary with score keys and their string values
        
    Returns:
        float: The total weighted score (handling reverse scores appropriately)
    """
    total = 0
    for score_key in SCORE_DEFINITIONS_KEYS:
        score_def = SCORE_DEFINITIONS[score_key]
        weight = SCORE_WEIGHTS.get(score_key, 10)
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


def normalize_ticker(ticker):
    """Normalize ticker to uppercase for comparison."""
    return ticker.upper()


def main():
    """Find correlation between scores.json and scores_heavy.json total scores."""
    
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
    
    # Calculate total scores for each common ticker
    light_scores = []
    heavy_scores = []
    ticker_list = []
    
    for ticker_norm in sorted(common_tickers_normalized):
        ticker_light = tickers_light_normalized[ticker_norm]
        ticker_heavy = tickers_heavy_normalized[ticker_norm]
        
        light_data = companies_light[ticker_light]
        heavy_data_item = companies_heavy[ticker_heavy]
        
        light_total = calculate_total_score(light_data)
        heavy_total = calculate_total_score(heavy_data_item)
        
        light_scores.append(light_total)
        heavy_scores.append(heavy_total)
        ticker_list.append(ticker_norm)
    
    # Calculate correlation using Pearson correlation coefficient
    if len(light_scores) < 2:
        print(f"Only {len(light_scores)} common ticker(s) found. Need at least 2 for correlation.")
        return
    
    def calculate_pearson_correlation(x, y):
        """Calculate Pearson correlation coefficient manually."""
        n = len(x)
        if n != len(y) or n < 2:
            return 0.0, 1.0
        
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
            return 0.0, 1.0
        
        denominator = (sum_sq_diff_x * sum_sq_diff_y) ** 0.5
        
        correlation = numerator / denominator if denominator != 0 else 0.0
        
        # Simple p-value approximation (not exact, but good enough for this use case)
        # For small samples, this is a rough approximation
        if n > 2:
            t_stat = correlation * ((n - 2) / (1 - correlation ** 2)) ** 0.5
            # Rough p-value approximation (would need scipy.stats for exact)
            p_value = 0.05  # Placeholder - actual calculation would require t-distribution
        else:
            p_value = 1.0
        
        return correlation, p_value
    
    correlation, p_value = calculate_pearson_correlation(light_scores, heavy_scores)
    
    # Display results
    print("\n" + "="*80)
    print("CORRELATION ANALYSIS: scores.json vs scores_heavy.json")
    print("="*80)
    print(f"\nCommon tickers found: {len(ticker_list)}")
    print(f"\nPearson Correlation Coefficient: {correlation:.4f}")
    print(f"Note: P-value calculation requires scipy for exact values")
    
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
    
    # Display detailed scores
    print("\n" + "-"*80)
    print(f"{'Ticker':<12} {'Light Score':>15} {'Heavy Score':>15} {'Diff (pts)':>15}")
    print("-"*80)
    
    max_score = sum(SCORE_WEIGHTS.values()) * 10
    for ticker, light, heavy in zip(ticker_list, light_scores, heavy_scores):
        diff = heavy - light
        light_pct = (light / max_score) * 100
        heavy_pct = (heavy / max_score) * 100
        print(f"{ticker:<12} {light_pct:>13.1f}% {heavy_pct:>13.1f}% {diff:>13.1f}")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    main()

