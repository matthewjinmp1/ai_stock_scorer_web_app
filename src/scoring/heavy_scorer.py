#!/usr/bin/env python3
"""
Heavy Scorer - Score companies with heavy model and run correlations
Gets Grok to rate companies using the main Grok 4 model and compares with light scores.
Usage: python heavy_scorer.py
Then enter ticker(s) to score, or commands: 'view', 'correl TICKER1 TICKER2 ...', 'clear', or 'quit'
"""

import sys
import os
# Add parent directory to path to import config and clients
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
# Import necessary constants and functions from scorer
from src.scoring.scorer import (
    SCORE_DEFINITIONS, SCORE_WEIGHTS, HEAVY_SCORES_FILE, SCORES_FILE,
    TICKER_FILE, MODEL_PRICING,
    load_ticker_lookup, load_scores, calculate_total_score,
    calculate_percentile_rank, format_total_score, query_all_scores_async,
    calculate_token_cost
)
from src.clients.grok_client import GrokClient
from config import XAI_API_KEY
import json
import os


def load_heavy_scores():
    """Load existing heavy scores from JSON file."""
    if os.path.exists(HEAVY_SCORES_FILE):
        try:
            with open(HEAVY_SCORES_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"companies": {}}
    return {"companies": {}}


def save_heavy_scores(scores_data):
    """Save heavy scores to JSON file."""
    with open(HEAVY_SCORES_FILE, 'w') as f:
        json.dump(scores_data, f, indent=2)


def get_company_moat_score_heavy(input_str):
    """Get all scores for a company using SCORE_DEFINITIONS with the main Grok 4 model.
    
    Accepts either a ticker symbol or company name.
    Stores scores using ticker as key in scores_heavy.json.
    """
    try:
        # Strip leading/trailing spaces only
        input_stripped = input_str.strip()
        input_upper = input_stripped.upper()
        
        ticker = None
        company_name = None
        
        # Check if the exact string (after stripping outer spaces) is in ticker database
        ticker_lookup = load_ticker_lookup()
        if input_upper in ticker_lookup:
            # Found exact match in ticker database
            ticker = input_upper
            company_name = ticker_lookup[ticker]
        else:
            # Not found in ticker database - reject it
            print(f"\nError: '{input_upper}' is not a valid ticker symbol.")
            print("Please enter a valid NYSE or NASDAQ ticker symbol.")
            return
        
        # Display format: Ticker (Company Name)
        if ticker:
            display_name = f"{ticker.upper()} ({company_name})"
            print(f"Company: {company_name}")
        
        scores_data = load_heavy_scores()
        
        # Try to find existing scores (always check uppercase first, then lowercase for backwards compatibility)
        existing_data = None
        storage_key = None
        
        if ticker and ticker in scores_data["companies"]:
            existing_data = scores_data["companies"][ticker]
            storage_key = ticker
        elif ticker and ticker.lower() in scores_data["companies"]:
            # Backwards compatibility: migrate lowercase to uppercase
            existing_data = scores_data["companies"][ticker.lower()]
            storage_key = ticker  # Will migrate on save
        elif company_name.lower() in scores_data["companies"]:
            existing_data = scores_data["companies"][company_name.lower()]
            storage_key = company_name.lower()
        
        if existing_data:
            current_scores = {}
            for score_key in SCORE_DEFINITIONS:
                if score_key == 'moat_score':
                    current_scores[score_key] = existing_data.get(score_key, existing_data.get('score'))
                else:
                    current_scores[score_key] = existing_data.get(score_key)
            
            # Check if all scores exist (all values are not None)
            if all(v is not None for v in current_scores.values()):
                if ticker:
                    print(f"\n{ticker.upper()} ({company_name}) already scored (heavy):")
                else:
                    print(f"\n{company_name} already scored (heavy):")
                
                # Print scores in the order defined in SCORE_DEFINITIONS (matching scorer.py behavior)
                # Use 35 characters for metric name to accommodate "Bargaining Power of Customers" (31 chars)
                for score_key in SCORE_DEFINITIONS:
                    score_def = SCORE_DEFINITIONS[score_key]
                    score_val = current_scores.get(score_key, 'N/A')
                    display_name = score_def['display_name']
                    # Truncate if longer than 35 characters
                    truncated_name = display_name[:35] if len(display_name) <= 35 else display_name[:32] + "..."
                    print(f"{truncated_name:<35} {score_val:>8}")
                
                # Print total at the bottom
                total = calculate_total_score(current_scores)
                total_str = format_total_score(total)
                print(f"{'Total':<35} {total_str:>8}")
                return
            
            grok = GrokClient(api_key=XAI_API_KEY)
            
            # Get list of missing score keys
            missing_keys = [key for key in SCORE_DEFINITIONS if current_scores.get(key) is None]
            
            if missing_keys:
                print("Querying missing metrics in parallel (heavy model)...")
                # Query missing scores in parallel
                missing_scores, tokens_used, token_usage = query_all_scores_async(grok, company_name, missing_keys,
                                                        batch_mode=False, silent=False, model="grok-4-latest")
                # Update current_scores with the new scores
                current_scores.update(missing_scores)
                print(f"Total tokens used: {tokens_used}")
                cost = calculate_token_cost(tokens_used, model="grok-4-latest", token_usage=token_usage)
                cost_cents = cost * 100
                print(f"Total cost: {cost_cents:.4f} cents")
            
            # Always store tickers in uppercase
            storage_key = ticker if ticker else company_name.lower()
            # If old lowercase key exists, remove it
            if ticker and ticker.lower() in scores_data["companies"] and ticker != ticker.lower():
                del scores_data["companies"][ticker.lower()]
            scores_data["companies"][storage_key] = current_scores
            save_heavy_scores(scores_data)
            print(f"\nScores updated in {HEAVY_SCORES_FILE}")
            
            # Calculate and display total
            total = calculate_total_score(current_scores)
            total_str = format_total_score(total)
            print(f"Total Score: {total_str}")
            return
        
        if ticker:
            print(f"\nAnalyzing {ticker.upper()} ({company_name}) with heavy model...")
        else:
            print(f"\nAnalyzing {company_name} with heavy model...")
        print("Querying all metrics in parallel (heavy model)...")
        grok = GrokClient(api_key=XAI_API_KEY)
        
        # Query all scores in parallel
        all_scores, total_tokens, token_usage = query_all_scores_async(grok, company_name, list(SCORE_DEFINITIONS.keys()),
                                            batch_mode=False, silent=False, model="grok-4-latest")
        
        print(f"Total tokens used: {total_tokens}")
        cost = calculate_token_cost(total_tokens, model="grok-4-latest", token_usage=token_usage)
        cost_cents = cost * 100
        print(f"Total cost: {cost_cents:.4f} cents")
        
        # Always store tickers in uppercase
        storage_key = ticker if ticker else company_name.lower()
        # If old lowercase key exists, remove it
        if ticker and ticker.lower() in scores_data["companies"] and ticker != ticker.lower():
            del scores_data["companies"][ticker.lower()]
        scores_data["companies"][storage_key] = all_scores
        save_heavy_scores(scores_data)
        print(f"\nScores saved to {HEAVY_SCORES_FILE}")
        
        # Calculate and display total
        total = calculate_total_score(all_scores)
        total_str = format_total_score(total)
        print(f"Total Score: {total_str}")
        
    except ValueError as e:
        print(f"Error: {e}")
        print("\nTo fix this:")
        print("1. Get an API key from https://console.x.ai/")
        print("2. Set the XAI_API_KEY environment variable:")
        print("   export XAI_API_KEY='your_api_key_here'")
        
    except Exception as e:
        print(f"Error: {e}")


def handle_heavy_command(tickers_input):
    """Handle the heavy command - score companies with the main Grok 4 model.
    
    Args:
        tickers_input: Space-separated ticker symbols
    """
    if not tickers_input.strip():
        print("Please provide ticker symbols. Example: heavy AAPL MSFT GOOGL")
        return
    
    tickers_raw = tickers_input.strip().split()
    # Deduplicate tickers while preserving order (case-insensitive)
    seen = set()
    tickers = []
    for ticker in tickers_raw:
        ticker_upper = ticker.upper()
        if ticker_upper not in seen:
            seen.add(ticker_upper)
            tickers.append(ticker)
    
    if len(tickers) < len(tickers_raw):
        print(f"Note: Removed {len(tickers_raw) - len(tickers)} duplicate ticker(s).")
    
    for ticker in tickers:
        print(f"\n{'='*60}")
        get_company_moat_score_heavy(ticker)
        print()


def calculate_correlation(light_scores, heavy_scores):
    """Calculate Pearson correlation coefficient between two lists of scores.
    
    Args:
        light_scores: List of light score values (floats)
        heavy_scores: List of heavy score values (floats)
        
    Returns:
        float: Correlation coefficient between -1 and 1, or None if insufficient data
    """
    if len(light_scores) != len(heavy_scores) or len(light_scores) < 2:
        return None
    
    # Calculate means
    light_mean = sum(light_scores) / len(light_scores)
    heavy_mean = sum(heavy_scores) / len(heavy_scores)
    
    # Calculate numerator (covariance)
    numerator = sum((light_scores[i] - light_mean) * (heavy_scores[i] - heavy_mean) 
                   for i in range(len(light_scores)))
    
    # Calculate denominators (standard deviations)
    light_std = sum((x - light_mean) ** 2 for x in light_scores) ** 0.5
    heavy_std = sum((x - heavy_mean) ** 2 for x in heavy_scores) ** 0.5
    
    # Avoid division by zero
    if light_std == 0 or heavy_std == 0:
        return None
    
    # Pearson correlation coefficient
    correlation = numerator / (light_std * heavy_std)
    return correlation


def handle_correl_command(tickers_input):
    """Handle the correl command - calculate correlation between light and heavy metric scores for each ticker.
    
    For each ticker, calculates the correlation between all its light metric scores and heavy metric scores.
    
    Args:
        tickers_input: Space-separated ticker symbols
    """
    if not tickers_input.strip():
        print("Please provide ticker symbols. Example: correl AAPL MSFT GOOGL")
        return
    
    tickers_raw = tickers_input.strip().split()
    # Deduplicate tickers while preserving order (case-insensitive)
    seen = set()
    tickers = []
    for ticker in tickers_raw:
        ticker_upper = ticker.upper()
        if ticker_upper not in seen:
            seen.add(ticker_upper)
            tickers.append(ticker)
    
    if len(tickers) < len(tickers_raw):
        print(f"Note: Removed {len(tickers_raw) - len(tickers)} duplicate ticker(s).")
    
    light_scores_data = load_scores()
    heavy_scores_data = load_heavy_scores()
    ticker_lookup = load_ticker_lookup()
    
    results = []
    
    for ticker_input in tickers:
        ticker_upper = ticker_input.strip().upper()
        
        # Validate ticker
        if ticker_upper not in ticker_lookup:
            print(f"Warning: '{ticker_upper}' is not a valid ticker symbol. Skipping.")
            continue
        
        company_name = ticker_lookup[ticker_upper]
        
        # Find light and heavy scores - try different keys independently
        # Try uppercase ticker first, then lowercase ticker, then lowercase company name
        light_data = None
        heavy_data = None
        light_lookup_key = None
        heavy_lookup_key = None
        
        # Find light scores
        if ticker_upper in light_scores_data["companies"]:
            light_data = light_scores_data["companies"][ticker_upper]
            light_lookup_key = ticker_upper
        elif ticker_upper.lower() in light_scores_data["companies"]:
            light_data = light_scores_data["companies"][ticker_upper.lower()]
            light_lookup_key = ticker_upper.lower()
        else:
            company_name_lower = company_name.lower()
            if company_name_lower in light_scores_data["companies"]:
                light_data = light_scores_data["companies"][company_name_lower]
                light_lookup_key = company_name_lower
        
        # Find heavy scores (try same keys)
        if ticker_upper in heavy_scores_data["companies"]:
            heavy_data = heavy_scores_data["companies"][ticker_upper]
            heavy_lookup_key = ticker_upper
        elif ticker_upper.lower() in heavy_scores_data["companies"]:
            heavy_data = heavy_scores_data["companies"][ticker_upper.lower()]
            heavy_lookup_key = ticker_upper.lower()
        else:
            company_name_lower = company_name.lower()
            if company_name_lower in heavy_scores_data["companies"]:
                heavy_data = heavy_scores_data["companies"][company_name_lower]
                heavy_lookup_key = company_name_lower
        
        if not light_data:
            print(f"Warning: '{ticker_upper}' has no light scores. Skipping.")
            continue
        
        if not heavy_data:
            print(f"Warning: '{ticker_upper}' has no heavy scores. Skipping.")
            continue
        
        # Collect all metric scores for this ticker
        light_metric_scores = []
        heavy_metric_scores = []
        metric_names = []
        score_keys_used = []  # Track which score_key corresponds to each metric
        
        try:
            for score_key in SCORE_DEFINITIONS:
                # Get light score
                light_score_str = light_data.get(score_key)
                if score_key == 'moat_score' and not light_score_str:
                    light_score_str = light_data.get('score')  # Backwards compatibility
                
                # Get heavy score
                heavy_score_str = heavy_data.get(score_key)
                if score_key == 'moat_score' and not heavy_score_str:
                    heavy_score_str = heavy_data.get('score')  # Backwards compatibility
                
                # Only include metrics that have both light and heavy scores
                if light_score_str and heavy_score_str:
                    try:
                        light_score = float(light_score_str)
                        heavy_score = float(heavy_score_str)
                        light_metric_scores.append(light_score)
                        heavy_metric_scores.append(heavy_score)
                        metric_names.append(SCORE_DEFINITIONS[score_key]['display_name'])
                        score_keys_used.append(score_key)  # Track the score_key for this metric
                    except (ValueError, TypeError):
                        continue
            
            # Need at least 2 metrics to calculate correlation
            if len(light_metric_scores) < 2:
                print(f"Warning: '{ticker_upper}' has insufficient metrics ({len(light_metric_scores)}) for correlation. Need at least 2.")
                continue
            
            # Calculate correlation for this ticker
            correlation = calculate_correlation(light_metric_scores, heavy_metric_scores)
            
            if correlation is None:
                print(f"Warning: Could not calculate correlation for '{ticker_upper}' (zero variance). Skipping.")
                continue
            
            # Calculate total scores for display - only use metrics that exist in both datasets
            # Track which score keys were actually used for comparison
            used_score_keys = []
            for score_key in SCORE_DEFINITIONS:
                light_score_str = light_data.get(score_key)
                if score_key == 'moat_score' and not light_score_str:
                    light_score_str = light_data.get('score')  # Backwards compatibility
                heavy_score_str = heavy_data.get(score_key)
                if score_key == 'moat_score' and not heavy_score_str:
                    heavy_score_str = heavy_data.get('score')  # Backwards compatibility
                if light_score_str and heavy_score_str:
                    used_score_keys.append(score_key)
            
            # Calculate totals using only the metrics that exist in both datasets
            # Use score_keys_used instead of used_score_keys to ensure consistency with displayed metrics
            light_total = 0
            heavy_total = 0
            for score_key in score_keys_used:  # Use score_keys_used which matches displayed metrics
                score_def = SCORE_DEFINITIONS[score_key]
                weight = SCORE_WEIGHTS.get(score_key, 1.0)
                try:
                    light_score_str = light_data.get(score_key)
                    if score_key == 'moat_score' and not light_score_str:
                        light_score_str = light_data.get('score')
                    heavy_score_str = heavy_data.get(score_key)
                    if score_key == 'moat_score' and not heavy_score_str:
                        heavy_score_str = heavy_data.get('score')
                    
                    light_value = float(light_score_str)
                    heavy_value = float(heavy_score_str)
                    
                    if score_def['is_reverse']:
                        light_total += (10 - light_value) * weight
                        heavy_total += (10 - heavy_value) * weight
                    else:
                        light_total += light_value * weight
                        heavy_total += heavy_value * weight
                except (ValueError, TypeError):
                    pass
            
            results.append({
                'ticker': ticker_upper,
                'company_name': company_name,
                'correlation': correlation,
                'num_metrics': len(light_metric_scores),
                'light_scores': light_metric_scores,
                'heavy_scores': heavy_metric_scores,
                'metric_names': metric_names,
                'score_keys_used': score_keys_used,  # Track which score_key each metric corresponds to
                'light_lookup_key': light_lookup_key,  # Store lookup keys for both files
                'heavy_lookup_key': heavy_lookup_key,
                'light_total': light_total,
                'heavy_total': heavy_total,
                'used_score_keys': used_score_keys  # Store for max_score calculation
            })
            
        except Exception as e:
            print(f"Warning: Error processing '{ticker_upper}': {e}. Skipping.")
            continue
    
    if not results:
        print("\nError: No tickers could be processed for correlation analysis.")
        print("Make sure all tickers have both light and heavy scores with at least 2 metrics each.")
        return
    
    # Display results
    print(f"\n{'='*80}")
    print("Correlation Analysis: Light vs Heavy Metric Scores (Per Ticker)")
    print(f"{'='*80}")
    print(f"\nTickers analyzed: {len(results)}")
    
    for result in results:
        ticker = result['ticker']
        company_name = result['company_name']
        correlation = result['correlation']
        num_metrics = result['num_metrics']
        light_scores = result['light_scores']
        heavy_scores = result['heavy_scores']
        metric_names = result['metric_names']
        score_keys_used = result.get('score_keys_used', [])
        
        # Re-read data using the lookup keys that were used during collection
        # This ensures we're reading from the correct entries in each file
        light_lookup_key = result.get('light_lookup_key')
        heavy_lookup_key = result.get('heavy_lookup_key')
        
        if light_lookup_key:
            light_data = light_scores_data["companies"].get(light_lookup_key)
        else:
            # Fallback to original logic if lookup_key not stored
            light_data = light_scores_data["companies"].get(ticker)
            if not light_data:
                light_data = light_scores_data["companies"].get(ticker.lower())
            if not light_data:
                company_name_lower = company_name.lower()
                light_data = light_scores_data["companies"].get(company_name_lower)
        
        if heavy_lookup_key:
            heavy_data = heavy_scores_data["companies"].get(heavy_lookup_key)
        else:
            # Fallback to original logic if lookup_key not stored
            heavy_data = heavy_scores_data["companies"].get(ticker)
            if not heavy_data:
                heavy_data = heavy_scores_data["companies"].get(ticker.lower())
            if not heavy_data:
                company_name_lower = company_name.lower()
                heavy_data = heavy_scores_data["companies"].get(company_name_lower)
        
        print(f"\n{'='*80}")
        print(f"{ticker} ({company_name})")
        print(f"{'='*80}")
        print(f"Number of metrics compared: {num_metrics}")
        print(f"\n{'Metric':<35} {'Light':>10} {'Heavy':>10} {'Diff':>10}")
        print("-" * 80)
        
        # Display scores using verified values from the data
        for i, metric_name in enumerate(metric_names):
            # Use score_key to read the correct value from the data
            if i < len(score_keys_used) and light_data and heavy_data:
                score_key = score_keys_used[i]
                # Re-read to ensure we're displaying the correct score
                light_score_str = light_data.get(score_key)
                if score_key == 'moat_score' and not light_score_str:
                    light_score_str = light_data.get('score')
                heavy_score_str = heavy_data.get(score_key)
                if score_key == 'moat_score' and not heavy_score_str:
                    heavy_score_str = heavy_data.get('score')
                
                if light_score_str and heavy_score_str:
                    try:
                        light_val = float(light_score_str)
                        heavy_val = float(heavy_score_str)
                        
                        # Verify: Check if the array values match what we're reading
                        # This helps catch any ordering or data mismatch bugs
                        if i < len(light_scores) and i < len(heavy_scores):
                            array_light = light_scores[i]
                            array_heavy = heavy_scores[i]
                            if abs(light_val - array_light) > 0.01 or abs(heavy_val - array_heavy) > 0.01:
                                # Mismatch detected - this indicates a bug!
                                print(f"  [DEBUG] Mismatch for {score_key}: array shows ({array_light}, {array_heavy}) but data shows ({light_val}, {heavy_val})")
                    except (ValueError, TypeError):
                        # Fallback to array values if conversion fails
                        light_val = light_scores[i] if i < len(light_scores) else 0
                        heavy_val = heavy_scores[i] if i < len(heavy_scores) else 0
                else:
                    # Fallback to array values if data not found
                    light_val = light_scores[i] if i < len(light_scores) else 0
                    heavy_val = heavy_scores[i] if i < len(heavy_scores) else 0
            else:
                # Fallback to array values if score_keys_used not available
                light_val = light_scores[i] if i < len(light_scores) else 0
                heavy_val = heavy_scores[i] if i < len(heavy_scores) else 0
            
            diff = heavy_val - light_val
            diff_str = f"{diff:+.1f}" if diff != 0 else "0.0"
            
            # Truncate long metric names
            display_name = metric_name[:33] if len(metric_name) <= 33 else metric_name[:30] + "..."
            print(f"{display_name:<35} {light_val:>10.1f} {heavy_val:>10.1f} {diff_str:>10}")
        
        # Recalculate totals based on displayed metrics to ensure consistency
        # This ensures totals match exactly what's displayed
        score_keys_used = result.get('score_keys_used', [])
        light_total_recalc = 0
        heavy_total_recalc = 0
        
        for i, score_key in enumerate(score_keys_used):
            if i < len(light_scores) and i < len(heavy_scores):
                score_def = SCORE_DEFINITIONS[score_key]
                weight = SCORE_WEIGHTS.get(score_key, 1.0)
                light_val = light_scores[i]
                heavy_val = heavy_scores[i]
                
                if score_def['is_reverse']:
                    light_total_recalc += (10 - light_val) * weight
                    heavy_total_recalc += (10 - heavy_val) * weight
                else:
                    light_total_recalc += light_val * weight
                    heavy_total_recalc += heavy_val * weight
        
        # Use recalculated totals
        light_total = light_total_recalc
        heavy_total = heavy_total_recalc
        
        # Calculate max_score based only on metrics that exist in both datasets and were used in calculation
        # Exclude metrics with weight 0 from max_score calculation
        if score_keys_used:
            max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in score_keys_used if SCORE_WEIGHTS.get(key, 1.0) > 0) * 10
        else:
            # Fallback: use used_score_keys if score_keys_used not available
            used_score_keys = result.get('used_score_keys', [])
            if used_score_keys:
                max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in used_score_keys if SCORE_WEIGHTS.get(key, 1.0) > 0) * 10
            else:
                # Final fallback: use all metrics
                max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS if SCORE_WEIGHTS.get(key, 1.0) > 0) * 10
        
        light_pct_raw = (light_total / max_score) * 100 if max_score > 0 else 0
        heavy_pct_raw = (heavy_total / max_score) * 100 if max_score > 0 else 0
        light_pct = int(light_pct_raw)
        heavy_pct = int(heavy_pct_raw)
        total_diff = heavy_total - light_total
        total_diff_pct = int((total_diff / max_score) * 100)
        total_diff_str = f"{total_diff_pct:+d}%" if total_diff != 0 else "0%"
        
        print("-" * 80)
        print(f"{'Total Score':<35} {light_pct:>9}% {heavy_pct:>9}% {total_diff_str:>10}")
        
        print(f"\nPearson Correlation Coefficient: {correlation:.4f}")
        
        # Interpret correlation
        abs_corr = abs(correlation)
        if abs_corr >= 0.9:
            strength = "Very strong"
        elif abs_corr >= 0.7:
            strength = "Strong"
        elif abs_corr >= 0.5:
            strength = "Moderate"
        elif abs_corr >= 0.3:
            strength = "Weak"
        else:
            strength = "Very weak"
        
        direction = "positive" if correlation > 0 else "negative"
        print(f"Interpretation: {strength} {direction} correlation")


def view_heavy_scores():
    """Display all stored heavy scores ranked by total score with percentiles."""
    scores_data = load_heavy_scores()
    
    if not scores_data["companies"]:
        print("No heavy scores stored yet.")
        return
    
    # Helper function to calculate total score
    def get_total_score(item):
        data = item[1]
        total = 0
        for score_key, score_def in SCORE_DEFINITIONS.items():
            score_val = data.get(score_key, 'N/A')
            weight = SCORE_WEIGHTS.get(score_key, 1.0)
            if score_val == 'N/A':
                continue
            
            try:
                val = float(score_val)
                if score_def['is_reverse']:
                    total += (10 - val) * weight
                else:
                    total += val * weight
            except (ValueError, TypeError):
                pass
        return total
    
    sorted_companies = sorted(scores_data["companies"].items(), key=get_total_score, reverse=True)
    
    # Calculate all totals for percentile calculation
    all_totals = []
    company_totals = {}
    for company, data in sorted_companies:
        total = get_total_score((company, data))
        if total > 0:  # Only include companies with valid scores
            company_totals[company] = total
            all_totals.append(total)
    
    if not company_totals:
        print("No valid heavy scores found.")
        return
    
    print("\nHeavy Scores - Total Score Rankings:")
    print("=" * 80)
    print(f"Number of stocks scored: {len(company_totals)}")
    print()
    
    max_name_len = max([len(company.upper()) for company in company_totals.keys()]) if company_totals else 0
    
    # Print column headers
    print(f"{'Rank':<6} {'Ticker':<{min(max_name_len, 30)}} {'Total Score':>15} {'Percentile':>12}")
    print("-" * (6 + min(max_name_len, 30) + 15 + 12 + 3))
    
    # Display companies with rankings and percentiles
    for rank, (company, data) in enumerate(sorted_companies, 1):
        if company in company_totals:
            total = company_totals[company]
            max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS) * 10
            percentage = int((total / max_score) * 100)
            percentage_str = f"{percentage}%"
            
            percentile = calculate_percentile_rank(total, all_totals) if len(all_totals) > 1 else None
            if percentile is not None:
                percentile_str = f"{percentile}th"
            else:
                percentile_str = 'N/A'
            
            # Display ticker (uppercase for consistency)
            display_key = company.upper()
            if len(display_key) > 30:
                display_key = display_key[:30]
            print(f"{rank:<6} {display_key:<{min(max_name_len, 30)}} {percentage_str:>15} {percentile_str:>12}")


def main():
    """Main interactive loop for heavy scorer."""
    print("Heavy Scorer - Score companies with heavy model and run correlations")
    print("=" * 60)
    print("Commands:")
    print("  Enter ticker symbol(s) (e.g., AAPL or AAPL MSFT GOOGL) to score with heavy model")
    print("  Type 'view' to see heavy model scores ranked with percentiles")
    print("  Type 'correl TICKER1 TICKER2 ...' to see correlation between light and heavy metric scores per ticker")
    print("  Type 'clear' to clear the terminal")
    print("  Type 'quit' or 'exit' to stop")
    print()
    
    while True:
        try:
            user_input = input("Enter ticker(s) or command ('view'/'correl'/'clear'/'quit'): ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            elif user_input.lower() == 'clear':
                # Clear terminal - cross-platform
                os.system('cls' if os.name == 'nt' else 'clear')
                print()
            elif user_input.lower() == 'view':
                view_heavy_scores()
                print()
            elif user_input.lower() == 'correl':
                print("Please provide ticker symbols. Example: correl AAPL MSFT GOOGL")
                print()
            elif user_input.lower().startswith('correl '):
                tickers = user_input[7:].strip()  # Remove 'correl ' prefix
                handle_correl_command(tickers)
                print()
            elif user_input:
                # Assume it's ticker(s) - automatically score with heavy model
                handle_heavy_command(user_input)
                print()
            else:
                print("Please enter a ticker symbol or command.")
                print()
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()

