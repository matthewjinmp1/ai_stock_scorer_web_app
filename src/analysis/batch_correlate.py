#!/usr/bin/env python3
"""
Batch Correlation Calculator
Calculates correlations between all pairs of companies and saves to correls.json
Usage: python batch_correlate.py
"""

import json
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from src.scoring.scorer import (
    SCORE_DEFINITIONS,
    load_scores,
    load_ticker_lookup,
    SCORES_FILE
)

CORRELS_FILE = "data/correls.json"


def get_ticker_from_storage_key(storage_key, ticker_lookup):
    """Get ticker symbol from a storage key (which might be ticker or company name).
    
    Args:
        storage_key: The key used in scores.json (could be ticker or company name)
        ticker_lookup: Dictionary mapping ticker to company name
        
    Returns:
        str: Ticker symbol (uppercase) or None if not found
    """
    # Check if storage_key is already a ticker
    storage_upper = storage_key.upper()
    if storage_upper in ticker_lookup:
        return storage_upper
    
    # Check if storage_key is a lowercase ticker
    storage_lower = storage_key.lower()
    if storage_lower.upper() in ticker_lookup:
        return storage_lower.upper()
    
    # Try to find ticker by company name (reverse lookup)
    for ticker, name in ticker_lookup.items():
        if name.lower() == storage_key.lower():
            return ticker
    
    # If not found, return the storage_key as-is (might be a ticker not in lookup)
    if len(storage_key) <= 5 and storage_key.replace(' ', '').isalpha():
        return storage_key.upper()
    
    return None


def calculate_correlation_fast(scores1, scores2):
    """Calculate correlation between two score dictionaries (optimized version).
    
    Args:
        scores1: Dictionary of scores for first company
        scores2: Dictionary of scores for second company
        
    Returns:
        tuple: (correlation_coefficient, num_metrics_compared) or (None, 0) if error
    """
    # Extract numeric scores for metrics both companies have
    # Handle reverse scores by converting to "goodness" values
    values1 = []
    values2 = []
    
    for score_key in SCORE_DEFINITIONS:
        score_def = SCORE_DEFINITIONS[score_key]
        val1 = scores1.get(score_key)
        val2 = scores2.get(score_key)
        
        # Only include metrics where both companies have scores
        if val1 and val2:
            try:
                num1 = float(val1)
                num2 = float(val2)
                
                # Convert reverse scores to "goodness" values
                if score_def['is_reverse']:
                    num1 = 10 - num1
                    num2 = 10 - num2
                
                values1.append(num1)
                values2.append(num2)
            except (ValueError, TypeError):
                continue
    
    if len(values1) < 2:
        return None, 0
    
    # Calculate Pearson correlation coefficient
    # r = Σ((x - x̄)(y - ȳ)) / sqrt(Σ(x - x̄)² * Σ(y - ȳ)²)
    n = len(values1)
    mean1 = sum(values1) / n
    mean2 = sum(values2) / n
    
    numerator = sum((values1[i] - mean1) * (values2[i] - mean2) for i in range(n))
    sum_sq_diff1 = sum((values1[i] - mean1) ** 2 for i in range(n))
    sum_sq_diff2 = sum((values2[i] - mean2) ** 2 for i in range(n))
    
    denominator = (sum_sq_diff1 * sum_sq_diff2) ** 0.5
    
    if denominator == 0:
        # All values are the same (no variance)
        correlation = 1.0 if values1 == values2 else 0.0
    else:
        correlation = numerator / denominator
    
    return correlation, len(values1)


def calculate_all_correlations():
    """Calculate correlations between all pairs of companies.
    
    Returns:
        dict: Dictionary with correlation data
    """
    print("Loading scores and ticker lookup...")
    scores_data = load_scores()
    ticker_lookup = load_ticker_lookup()
    
    companies = scores_data.get("companies", {})
    
    if not companies:
        print("Error: No companies found in scores.json")
        return None
    
    print(f"Found {len(companies)} companies with scores")
    print("Calculating all pairwise correlations...")
    print("=" * 80)
    
    # Build mapping from storage keys to tickers
    storage_to_ticker = {}
    ticker_to_storage = {}
    
    for storage_key in companies.keys():
        ticker = get_ticker_from_storage_key(storage_key, ticker_lookup)
        if ticker:
            storage_to_ticker[storage_key] = ticker
            # Map ticker to storage key (use first one if multiple)
            if ticker not in ticker_to_storage:
                ticker_to_storage[ticker] = storage_key
    
    # Get list of all tickers (unique)
    all_tickers = sorted(set(storage_to_ticker.values()))
    
    print(f"Found {len(all_tickers)} unique tickers")
    print()
    
    # Calculate correlations
    correlations = {}
    total_pairs = len(all_tickers) * (len(all_tickers) - 1) // 2
    current_pair = 0
    start_time = time.time()
    
    for i, ticker1 in enumerate(all_tickers):
        if ticker1 not in ticker_to_storage:
            continue
        
        storage_key1 = ticker_to_storage[ticker1]
        scores1 = companies[storage_key1]
        
        correlations[ticker1] = {}
        
        for ticker2 in all_tickers[i+1:]:
            if ticker2 not in ticker_to_storage:
                continue
            
            storage_key2 = ticker_to_storage[ticker2]
            scores2 = companies[storage_key2]
            
            correlation, num_metrics = calculate_correlation_fast(scores1, scores2)
            
            if correlation is not None:
                correlations[ticker1][ticker2] = {
                    'correlation': round(correlation, 6),
                    'num_metrics': num_metrics
                }
            
            current_pair += 1
            if current_pair % 100 == 0:
                elapsed = time.time() - start_time
                rate = current_pair / elapsed if elapsed > 0 else 0
                remaining = (total_pairs - current_pair) / rate if rate > 0 else 0
                print(f"Progress: {current_pair}/{total_pairs} pairs ({current_pair*100//total_pairs}%) | "
                      f"Rate: {rate:.1f} pairs/sec | ETA: {remaining:.0f}s", end='\r')
    
    print()  # New line after progress updates
    print()
    
    elapsed_total = time.time() - start_time
    print(f"Completed {current_pair} correlations in {elapsed_total:.2f} seconds")
    print(f"Average rate: {current_pair/elapsed_total:.1f} correlations/second")
    
    return {
        'metadata': {
            'total_companies': len(all_tickers),
            'total_correlations': current_pair,
            'calculated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'scores_file': SCORES_FILE
        },
        'correlations': correlations
    }


def save_correlations(correlations_data):
    """Save correlations to JSON file.
    
    Args:
        correlations_data: Dictionary with correlation data
    """
    try:
        with open(CORRELS_FILE, 'w') as f:
            json.dump(correlations_data, f, indent=2)
        print(f"\nCorrelations saved to {CORRELS_FILE}")
        return True
    except Exception as e:
        print(f"\nError saving correlations: {e}")
        return False


def main():
    """Main function to calculate and save all correlations."""
    print("Batch Correlation Calculator")
    print("=" * 80)
    print()
    
    if not os.path.exists(SCORES_FILE):
        print(f"Error: {SCORES_FILE} not found. Please run scorer.py first to generate scores.")
        return
    
    correlations_data = calculate_all_correlations()
    
    if correlations_data:
        save_correlations(correlations_data)
        
        # Print summary
        print()
        print("Summary:")
        print(f"  Companies: {correlations_data['metadata']['total_companies']}")
        print(f"  Correlations calculated: {correlations_data['metadata']['total_correlations']}")
        print(f"  Output file: {CORRELS_FILE}")
    else:
        print("Error: Failed to calculate correlations.")


if __name__ == "__main__":
    main()

