#!/usr/bin/env python3
"""
Prompt Tester - For Testing Prompts
This tool scores multiple tickers with a single metric and displays statistics.
Scores are NOT saved - this is purely for testing prompts.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from src.clients.grok_client import GrokClient
from config import XAI_API_KEY
import json
import os
import time
import statistics
import math
from concurrent.futures import ThreadPoolExecutor, as_completed

# Stock ticker lookup file
TICKER_FILE = "data/stock_tickers_clean.json"

# Custom ticker definitions file
TICKER_DEFINITIONS_FILE = "data/ticker_definitions.json"

# Cache for ticker lookups
_ticker_cache = None

# Single metric definition - modify this prompt for testing
METRIC = {
    'key': 'moat_score',
    'display_name': 'Competitive Moat',
    'prompt': """Rate the competitive moat strength of {company_name} on a scale of 0-10, where:
- 0 = Low competitive advantage
- 5 = Strong competitive advantages
- 10 = Extremely strong moat

Consider factors like:
- Brand strength and customer loyalty
- Network effects
- Switching costs
- Economies of scale
- Patents/intellectual property
- Regulatory barriers
- Unique resources or capabilities

Respond with ONLY the numerical score (0-10), no explanation needed."""
}


def load_custom_ticker_definitions():
    """Load custom ticker definitions from JSON file.
    
    Returns:
        dict: Dictionary mapping ticker (uppercase) to company name
    """
    custom_definitions = {}
    
    try:
        if os.path.exists(TICKER_DEFINITIONS_FILE):
            with open(TICKER_DEFINITIONS_FILE, 'r') as f:
                data = json.load(f)
                
                for ticker, name in data.get('definitions', {}).items():
                    ticker_upper = ticker.strip().upper()
                    name_stripped = name.strip()
                    
                    if ticker_upper and name_stripped:
                        custom_definitions[ticker_upper] = name_stripped
    except Exception as e:
        print(f"Warning: Could not load custom ticker definitions: {e}")
    
    return custom_definitions


def load_ticker_lookup():
    """Load ticker to company name lookup.
    Custom definitions take precedence over main ticker file.
    """
    global _ticker_cache
    
    if _ticker_cache is not None:
        return _ticker_cache
    
    _ticker_cache = {}
    
    # First load from main ticker file
    try:
        if os.path.exists(TICKER_FILE):
            with open(TICKER_FILE, 'r') as f:
                data = json.load(f)
                
                for company in data.get('companies', []):
                    ticker = company.get('ticker', '').strip().upper()
                    name = company.get('name', '').strip()
                    
                    if ticker:
                        _ticker_cache[ticker] = name
        else:
            print(f"Warning: {TICKER_FILE} not found. Ticker lookups will not work.")
    except Exception as e:
        print(f"Warning: Could not load ticker file: {e}")
    
    # Then load custom definitions (these override main file)
    custom_definitions = load_custom_ticker_definitions()
    _ticker_cache.update(custom_definitions)
    
    return _ticker_cache


def score_ticker(ticker_str):
    """Score a single ticker and return the score value.
    
    Returns:
        tuple: (ticker, company_name, score_float, elapsed_time, total_tokens) or None if error
    """
    input_stripped = ticker_str.strip()
    input_upper = input_stripped.upper()
    
    ticker_lookup = load_ticker_lookup()
    if input_upper not in ticker_lookup:
        return (ticker_str, None, None, None, None, f"'{input_upper}' is not a valid ticker symbol")
    
    ticker = input_upper
    company_name = ticker_lookup[ticker]
    
    # Score the company
    grok = GrokClient(api_key=XAI_API_KEY)
    prompt = METRIC['prompt'].format(company_name=company_name)
    
    start_time = time.time()
        try:
            response, token_usage = grok.simple_query_with_tokens(prompt, model="grok-4-fast")
            
            # Log all responses if possible
            try:
                from src.scoring.scorer import log_ai_response
                log_ai_response(ticker, company_name, "prompt_test", response, "grok-4-fast")
            except ImportError:
                pass
                
            elapsed_time = time.time() - start_time
        total_tokens = token_usage.get('total_tokens', 0)
        
        score_str = response.strip()
        
        # Try to extract numeric score from response
        try:
            # Try to parse as float directly
            score_float = float(score_str)
        except ValueError:
            # Try to extract number from response
            import re
            numbers = re.findall(r'\d+\.?\d*', score_str)
            if numbers:
                score_float = float(numbers[0])
            else:
                return (ticker, company_name, None, elapsed_time, total_tokens, f"Could not parse score from response: {score_str}")
        
        # Validate score is in range 0-10
        warning = None
        if score_float < 0 or score_float > 10:
            warning = f"Score {score_float} is outside 0-10 range"
        
        return (ticker, company_name, score_float, elapsed_time, total_tokens, warning)
        
    except Exception as e:
        return (ticker, company_name, None, None, None, str(e))


def calculate_mean_absolute_deviation(scores):
    """Calculate Mean Absolute Deviation (MAD) - mean of absolute deviations from the mean."""
    if len(scores) < 1:
        return 0.0
    
    mean = statistics.mean(scores)
    deviations = [abs(score - mean) for score in scores]
    return statistics.mean(deviations)


def calculate_median_absolute_deviation(scores):
    """Calculate Median Absolute Deviation - median of absolute deviations from the median."""
    if len(scores) < 2:
        return 0.0
    
    median = statistics.median(scores)
    deviations = [abs(score - median) for score in scores]
    return statistics.median(deviations)


def calculate_quartiles(scores):
    """Calculate quartiles (Q1, Q2, Q3)."""
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    
    if n == 0:
        return None, None, None
    
    # Q2 is the median
    q2 = statistics.median(sorted_scores)
    
    if n == 1:
        return q2, q2, q2
    
    # Q1 is median of lower half
    lower_half = sorted_scores[:n//2]
    q1 = statistics.median(lower_half)
    
    # Q3 is median of upper half
    if n % 2 == 0:
        upper_half = sorted_scores[n//2:]
    else:
        upper_half = sorted_scores[n//2 + 1:]
    q3 = statistics.median(upper_half)
    
    return q1, q2, q3


def display_statistics(results):
    """Display statistics about the scored tickers."""
    if not results:
        print("\nNo valid scores to display statistics for.")
        return
    
    # Extract scores
    scores = [score for _, _, score in results]
    tickers = [ticker for ticker, _, _ in results]
    
    print("\n" + "=" * 80)
    print("SCORING STATISTICS")
    print("=" * 80)
    
    # Basic stats
    n = len(scores)
    mean = statistics.mean(scores)
    median = statistics.median(scores)
    min_score = min(scores)
    max_score = max(scores)
    range_score = max_score - min_score
    
    # Standard deviation
    if n > 1:
        stdev = statistics.stdev(scores)
    else:
        stdev = 0.0
    
    # Mean Absolute Deviation (mean of |x - mean|)
    mean_abs_dev = calculate_mean_absolute_deviation(scores)
    
    # Median Absolute Deviation (median of |x - median|)
    median_abs_dev = calculate_median_absolute_deviation(scores)
    
    # Quartiles
    q1, q2, q3 = calculate_quartiles(scores)
    
    # Display results
    print(f"\nSample Size: {n} ticker(s)")
    print(f"\n{'Metric':<30} {'Value':>15}")
    print("-" * 50)
    print(f"{'Mean (Average)':<30} {mean:>15.2f}")
    print(f"{'Median':<30} {median:>15.2f}")
    print(f"{'Standard Deviation':<30} {stdev:>15.2f}")
    print(f"{'Mean Absolute Deviation':<30} {mean_abs_dev:>15.2f}")
    print(f"{'Median Absolute Deviation':<30} {median_abs_dev:>15.2f}")
    print(f"{'Minimum':<30} {min_score:>15.2f}")
    print(f"{'Maximum':<30} {max_score:>15.2f}")
    print(f"{'Range':<30} {range_score:>15.2f}")
    
    if q1 is not None:
        print(f"\n{'Quartiles':<30}")
        print(f"{'  Q1 (25th percentile)':<30} {q1:>15.2f}")
        print(f"{'  Q2 (50th percentile)':<30} {q2:>15.2f}")
        print(f"{'  Q3 (75th percentile)':<30} {q3:>15.2f}")
        iqr = q3 - q1
        print(f"{'  IQR (Q3 - Q1)':<30} {iqr:>15.2f}")
    
    # Coefficient of variation
    if mean != 0:
        cv = (stdev / mean) * 100
        print(f"{'Coefficient of Variation (%)':<30} {cv:>15.2f}")
    
    # Display individual scores sorted
    print(f"\n{'Individual Scores (sorted)':<30}")
    print("-" * 50)
    sorted_results = sorted(results, key=lambda x: x[2], reverse=True)
    for ticker, company_name, score in sorted_results:
        company_display = company_name[:25] if len(company_name) > 25 else company_name
        print(f"  {ticker:<6} {company_display:<25} {score:>6.2f}")
    
    print("=" * 80)


def score_multiple_tickers(tickers_str):
    """Score multiple tickers in parallel and display statistics."""
    tickers = tickers_str.strip().split()
    
    if not tickers:
        print("No tickers provided.")
        return
    
    # Pre-load ticker lookup to avoid race conditions in parallel execution
    ticker_lookup = load_ticker_lookup()
    
    # Validate all tickers upfront
    valid_tickers = []
    invalid_tickers = []
    for ticker in tickers:
        ticker_upper = ticker.strip().upper()
        if ticker_upper in ticker_lookup:
            valid_tickers.append(ticker_upper)
        else:
            invalid_tickers.append(ticker_upper)
    
    if invalid_tickers:
        print(f"\nWarning: The following tickers are not found in the lookup:")
        for ticker in invalid_tickers:
            print(f"  - {ticker}")
        print(f"\nAvailable tickers in lookup: {len(ticker_lookup)} total")
        if invalid_tickers:
            print("\nSkipping invalid tickers and continuing with valid ones...")
    
    if not valid_tickers:
        print("No valid tickers to score.")
        return
    
    print(f"\nScoring {len(valid_tickers)} ticker(s) for {METRIC['display_name']} in parallel...")
    print("=" * 80)
    
    overall_start = time.time()
    results = []
    
    # Score all tickers in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(valid_tickers)) as executor:
        # Submit all tasks
        future_to_ticker = {executor.submit(score_ticker, ticker): ticker for ticker in valid_tickers}
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(future_to_ticker):
            completed += 1
            ticker_input = future_to_ticker[future]
            result = future.result()
            
            ticker, company_name, score_float, elapsed_time, total_tokens, error_or_warning = result
            
            if error_or_warning:
                if score_float is None:
                    # It's an error
                    print(f"  ✗ [{completed}/{len(valid_tickers)}] {ticker_input.upper()}: Error - {error_or_warning}")
                else:
                    # It's a warning
                    print(f"  ✓ [{completed}/{len(valid_tickers)}] {ticker} ({company_name}): {score_float:.1f}/10 "
                          f"({elapsed_time:.2f}s, {total_tokens} tokens) - Warning: {error_or_warning}")
                    results.append((ticker, company_name, score_float))
            elif score_float is not None:
                print(f"  ✓ [{completed}/{len(valid_tickers)}] {ticker} ({company_name}): {score_float:.1f}/10 "
                      f"({elapsed_time:.2f}s, {total_tokens} tokens)")
                results.append((ticker, company_name, score_float))
    
    overall_elapsed = time.time() - overall_start
    print(f"\nCompleted scoring {len(results)}/{len(valid_tickers)} tickers in {overall_elapsed:.2f}s")
    
    # Display statistics
    display_statistics(results)


def main():
    """Main function to run the prompt tester."""
    print("Prompt Tester - For Testing Prompts")
    print("=" * 50)
    print(f"Current Metric: {METRIC['display_name']}")
    print()
    print("Usage: Enter space-separated ticker symbols (e.g., AAPL MSFT GOOGL)")
    print("       Type 'quit' or 'exit' to stop")
    print("       Scores are NOT saved - this is for testing only")
    print()
    
    while True:
        try:
            user_input = input("Enter ticker list: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            if not user_input:
                print("Please enter at least one ticker symbol.")
                continue
            
            # Always treat as multiple tickers (even if just one)
            score_multiple_tickers(user_input)
            print()
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()
