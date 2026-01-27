#!/usr/bin/env python3
"""
Calculate correlation between total score and market cap percentile rank.
Gets market cap for all companies in scores.json and calculates correlation.
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Add project root to path to allow imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    import yfinance as yf
except ImportError:
    print("Error: yfinance is required. Install it with: pip install yfinance")
    exit(1)

# Score weights (copied from scorer.py to avoid dependency on grok_client)
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
}


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
        weight = SCORE_WEIGHTS.get(score_key, 1.0)
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


def calculate_percentile_rank(score, all_scores):
    """Calculate percentile rank of a score among all scores.
    
    Args:
        score: The score to calculate percentile for (float)
        all_scores: List of all scores to compare against (list of floats)
        
    Returns:
        int: Percentile rank (0-100), or None if no scores to compare
    """
    if not all_scores or len(all_scores) == 0:
        return None
    
    # Count how many scores are less than or equal to this score
    scores_less_or_equal = sum(1 for s in all_scores if s <= score)
    
    # Percentile rank = (number of scores <= this score) / total scores * 100
    percentile = int((scores_less_or_equal / len(all_scores)) * 100)
    return percentile


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


def get_market_cap(ticker):
    """Get market cap for a ticker using yfinance.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        float: Market cap in USD, or None if not available
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Try different possible keys for market cap
        market_cap = info.get('marketCap') or info.get('totalMarketCap') or info.get('enterpriseValue')
        
        if market_cap:
            return float(market_cap)
        return None
    except Exception as e:
        # Silently fail for individual tickers
        return None


def process_ticker(ticker_key, scores_dict, excluded_tickers):
    """Process a single ticker: calculate score and fetch market cap.
    
    Args:
        ticker_key: Ticker key from scores.json
        scores_dict: Dictionary of scores for this ticker
        excluded_tickers: Set of tickers to exclude
        
    Returns:
        tuple: (ticker, total_score, market_cap) or None if excluded/failed
    """
    # Normalize ticker (handle lowercase keys)
    ticker = ticker_key.upper()
    
    # Skip tickers in ticker_definitions.json (not real tickers)
    if ticker in excluded_tickers:
        return None
    
    # Calculate total score
    total_score = calculate_total_score(scores_dict)
    
    # Get market cap
    market_cap = get_market_cap(ticker)
    
    if market_cap is not None:
        return {
            'ticker': ticker,
            'total_score': total_score,
            'market_cap': market_cap
        }
    return None


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


def main():
    """Main function to calculate correlation between total score and market cap percentile."""
    print("=" * 80)
    print("Market Cap vs Total Score Correlation Analysis")
    print("=" * 80)
    
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
    
    # Collect data for each company using multithreading
    print("\nFetching market cap data (using multithreading)...")
    print("(This may take a while for many companies)")
    
    company_data = []
    failed_tickers = []
    excluded_count = 0
    
    # Prepare list of tickers to process (excluding those in ticker_definitions.json)
    tickers_to_process = []
    for ticker_key, scores_dict in companies.items():
        ticker = ticker_key.upper()
        if ticker in excluded_tickers:
            excluded_count += 1
        else:
            tickers_to_process.append((ticker_key, scores_dict))
    
    if excluded_count > 0:
        print(f"Excluding {excluded_count} ticker(s) from ticker_definitions.json")
    
    # Use ThreadPoolExecutor to fetch market caps in parallel
    # Use a reasonable number of threads (yfinance API may rate limit, so don't go too high)
    max_workers = min(20, len(tickers_to_process))
    
    completed = 0
    total = len(tickers_to_process)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {
            executor.submit(process_ticker, ticker_key, scores_dict, excluded_tickers): ticker_key
            for ticker_key, scores_dict in tickers_to_process
        }
        
        # Process completed tasks as they finish
        for future in as_completed(future_to_ticker):
            completed += 1
            if completed % 10 == 0 or completed == total:
                print(f"  Progress: {completed}/{total}")
            
            try:
                result = future.result()
                if result is not None:
                    company_data.append(result)
                else:
                    ticker_key = future_to_ticker[future]
                    failed_tickers.append(ticker_key.upper())
            except Exception as e:
                ticker_key = future_to_ticker[future]
                failed_tickers.append(ticker_key.upper())
    
    if failed_tickers:
        print(f"\nWarning: Could not fetch market cap for {len(failed_tickers)} tickers:")
        print(f"  {', '.join(failed_tickers[:10])}" + ("..." if len(failed_tickers) > 10 else ""))
    
    if len(company_data) < 2:
        print(f"\nError: Need at least 2 companies with market cap data. Found {len(company_data)}")
        return
    
    print(f"\nSuccessfully fetched market cap for {len(company_data)} companies")
    
    # Extract market caps and calculate percentile ranks
    market_caps = [d['market_cap'] for d in company_data]
    
    # Calculate percentile rank for each company's market cap
    for data in company_data:
        percentile = calculate_percentile_rank(data['market_cap'], market_caps)
        data['market_cap_percentile'] = percentile
    
    # Extract total scores and market cap percentiles for correlation
    total_scores = [d['total_score'] for d in company_data]
    market_cap_percentiles = [d['market_cap_percentile'] for d in company_data]
    
    # Calculate correlation
    correlation, _ = calculate_pearson_correlation(total_scores, market_cap_percentiles)
    
    if correlation is None:
        print("\nError: Could not calculate correlation (insufficient data variance)")
        return
    
    # Display results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"\nNumber of companies analyzed: {len(company_data)}")
    print(f"\nPearson Correlation Coefficient: {correlation:.4f}")
    
    # Interpret correlation
    abs_corr = abs(correlation)
    if abs_corr >= 0.9:
        strength = "very strong"
    elif abs_corr >= 0.7:
        strength = "strong"
    elif abs_corr >= 0.5:
        strength = "moderate"
    elif abs_corr >= 0.3:
        strength = "weak"
    else:
        strength = "very weak"
    
    direction = "positive" if correlation > 0 else "negative"
    print(f"Interpretation: {strength} {direction} correlation")
    
    # Show some examples
    print("\n" + "=" * 80)
    print("Sample Data (Top 10 by Total Score)")
    print("=" * 80)
    
    # Sort by total score (descending)
    sorted_data = sorted(company_data, key=lambda x: x['total_score'], reverse=True)
    
    print(f"\n{'Rank':<6} {'Ticker':<8} {'Total Score':>15} {'Market Cap %':>15}")
    print("-" * 60)
    
    for rank, data in enumerate(sorted_data[:10], 1):
        ticker = data['ticker']
        total_score = data['total_score']
        market_cap_pct = data['market_cap_percentile']
        
        # Calculate percentage for total score
        max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS) * 10
        score_pct = int((total_score / max_score) * 100)
        
        print(f"{rank:<6} {ticker:<8} {score_pct:>13}% {market_cap_pct:>13}th")
    
    print("=" * 80)


if __name__ == "__main__":
    main()

