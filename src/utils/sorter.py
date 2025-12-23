#!/usr/bin/env python3
"""
Efficient Moat Score Sorter using Grok API
Uses merge sort (O(n log n)) to rank companies by moat strength.
Each comparison is done by asking Grok which company has a stronger moat.
Expected API calls: ~n*log2(n) = ~33 calls for 10 companies
"""

from grok_client import GrokClient
from config import XAI_API_KEY
import time
import sys

# Import ticker lookup functions from scorer.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
try:
    from src.scoring.scorer import load_ticker_lookup, resolve_to_company_name
except ImportError:
    print("Error: Could not import ticker lookup functions from scorer.py")
    print("Make sure scorer.py is in the same directory.")
    sys.exit(1)

# Track API calls
api_call_count = 0

def compare_companies_grok(grok, company1, company2):
    """
    Ask Grok which company has a stronger competitive moat.
    
    Args:
        grok: GrokClient instance
        company1: Tuple of (ticker, company_name)
        company2: Tuple of (ticker, company_name)
        
    Returns:
        -1 if company1 has stronger moat (company1 < company2 in sort order)
         1 if company2 has stronger moat (company2 < company1 in sort order)
         0 if equal (shouldn't happen, but handle gracefully)
    """
    global api_call_count
    
    ticker1, name1 = company1
    ticker2, name2 = company2
    
    prompt = f"""Compare the competitive moat strength of these two companies:

Company 1: {name1} ({ticker1})
Company 2: {name2} ({ticker2})

Which company has a STRONGER competitive moat? Consider factors like:
- Brand strength and customer loyalty
- Network effects
- Switching costs
- Economies of scale
- Patents/intellectual property
- Regulatory barriers
- Unique resources or capabilities

Respond with ONLY:
- "1" if {name1} ({ticker1}) has a stronger moat
- "2" if {name2} ({ticker2}) has a stronger moat
- "equal" if they have equally strong moats (very rare)

Just respond with the number or "equal", nothing else."""

    api_call_count += 1
    print(f"  [Call #{api_call_count}] Comparing {ticker1} vs {ticker2}...", end=" ", flush=True)
    
    try:
        response, _ = grok.simple_query_with_tokens(prompt, model="grok-4-fast")
        
        # Log all responses if possible
        try:
            from src.scoring.scorer import log_ai_response
            log_ai_response(f"{ticker1}_vs_{ticker2}", f"{name1}_vs_{name2}", "moat_comparison", response, "grok-4-fast")
        except ImportError:
            pass
            
        response = response.strip().lower()
        
        if "1" in response or ticker1.lower() in response:
            print(f"→ {ticker1} stronger")
            return -1  # company1 has stronger moat (should come first)
        elif "2" in response or ticker2.lower() in response:
            print(f"→ {ticker2} stronger")
            return 1   # company2 has stronger moat (should come first)
        else:
            # Default to company1 if unclear (shouldn't happen often)
            print(f"→ unclear, defaulting to {ticker1}")
            return -1
    except Exception as e:
        print(f"→ Error: {e}, defaulting to {ticker1}")
        return -1


def merge_sort_companies(grok, companies):
    """
    Merge sort implementation using Grok comparisons.
    
    Args:
        grok: GrokClient instance
        companies: List of (ticker, company_name) tuples
        
    Returns:
        Sorted list of companies (strongest moat first)
    """
    if len(companies) <= 1:
        return companies
    
    # Split the list in half
    mid = len(companies) // 2
    left = merge_sort_companies(grok, companies[:mid])
    right = merge_sort_companies(grok, companies[mid:])
    
    # Merge the two sorted halves
    return merge(grok, left, right)


def merge(grok, left, right):
    """
    Merge two sorted lists using Grok comparisons.
    
    Args:
        grok: GrokClient instance
        left: Sorted list of companies
        right: Sorted list of companies
        
    Returns:
        Merged sorted list
    """
    result = []
    i = j = 0
    
    while i < len(left) and j < len(right):
        # Compare using Grok
        comparison = compare_companies_grok(grok, left[i], right[j])
        
        if comparison <= 0:  # left[i] has stronger or equal moat
            result.append(left[i])
            i += 1
        else:  # right[j] has stronger moat
            result.append(right[j])
            j += 1
    
    # Add remaining elements
    result.extend(left[i:])
    result.extend(right[j:])
    
    return result


def parse_tickers_input(input_str):
    """
    Parse space-separated tickers and convert to (ticker, company_name) tuples.
    
    Args:
        input_str: Space-separated ticker symbols (e.g., "AAPL MSFT GOOGL")
        
    Returns:
        List of (ticker, company_name) tuples, or None if there are errors
    """
    if not input_str or not input_str.strip():
        return None
    
    tickers_raw = input_str.strip().split()
    
    if not tickers_raw:
        return None
    
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
    
    # Load ticker lookup
    ticker_lookup = load_ticker_lookup()
    
    # Convert tickers to company names
    companies = []
    invalid_tickers = []
    
    for ticker in tickers:
        ticker_upper = ticker.strip().upper()
        
        # Check if it's a valid ticker
        if ticker_upper in ticker_lookup:
            company_name = ticker_lookup[ticker_upper]
            companies.append((ticker_upper, company_name))
        else:
            # Try resolve_to_company_name as fallback
            company_name, resolved_ticker = resolve_to_company_name(ticker)
            if resolved_ticker:
                companies.append((resolved_ticker, company_name))
            else:
                invalid_tickers.append(ticker_upper)
    
    if invalid_tickers:
        print(f"\nError: The following ticker(s) are not valid: {', '.join(invalid_tickers)}")
        print("Please enter valid NYSE or NASDAQ ticker symbols.")
        return None
    
    if not companies:
        print("Error: No valid tickers provided.")
        return None
    
    return companies


def main():
    """Main function to sort companies by moat strength."""
    global api_call_count
    
    print("=" * 80)
    print("Grok-Powered Moat Score Sorter")
    print("=" * 80)
    print("\nEnter ticker symbols separated by spaces (e.g., AAPL MSFT GOOGL)")
    print("Or press Enter to use default companies")
    print()
    
    # Get user input
    user_input = input("Enter tickers (or press Enter for defaults): ").strip()
    
    # Parse tickers or use defaults
    if user_input:
        companies = parse_tickers_input(user_input)
        if companies is None:
            print("\nUsing default companies instead...")
            companies = [
                ("AAPL", "Apple Inc"),
                ("MSFT", "Microsoft Corporation"),
                ("GOOGL", "Alphabet Inc"),
                ("AMZN", "Amazon.com Inc"),
                ("NVDA", "NVIDIA Corporation"),
                ("META", "Meta Platforms Inc"),
                ("TSLA", "Tesla Inc"),
                ("JPM", "JPMorgan Chase & Co"),
                ("V", "Visa Inc"),
                ("JNJ", "Johnson & Johnson"),
            ]
    else:
        # Use default companies
        companies = [
            ("AAPL", "Apple Inc"),
            ("MSFT", "Microsoft Corporation"),
            ("GOOGL", "Alphabet Inc"),
            ("AMZN", "Amazon.com Inc"),
            ("NVDA", "NVIDIA Corporation"),
            ("META", "Meta Platforms Inc"),
            ("TSLA", "Tesla Inc"),
            ("JPM", "JPMorgan Chase & Co"),
            ("V", "Visa Inc"),
            ("JNJ", "Johnson & Johnson"),
        ]
    
    print(f"\nRanking {len(companies)} companies by competitive moat strength...")
    print("Using merge sort (O(n log n)) with Grok API comparisons")
    print(f"Expected API calls: ~{len(companies)} * log2({len(companies)}) ≈ {int(len(companies) * __import__('math').log2(len(companies)))}")
    print()
    
    # Initialize Grok client
    try:
        grok = GrokClient(api_key=XAI_API_KEY)
    except Exception as e:
        print(f"Error initializing Grok client: {e}")
        print("\nTo fix this:")
        print("1. Get an API key from https://console.x.ai/")
        print("2. Set the XAI_API_KEY environment variable:")
        print("   export XAI_API_KEY='your_api_key_here'")
        return
    
    # Reset API call counter
    api_call_count = 0
    
    # Start timing
    start_time = time.time()
    
    # Sort companies using merge sort
    print("Starting merge sort with Grok comparisons...\n")
    sorted_companies = merge_sort_companies(grok, companies.copy())
    
    # End timing
    elapsed_time = time.time() - start_time
    
    # Display results
    print("\n" + "=" * 80)
    print("Ranking Results (Strongest Moat First)")
    print("=" * 80)
    print()
    
    for rank, (ticker, company_name) in enumerate(sorted_companies, 1):
        print(f"{rank:2}. {ticker:6} - {company_name}")
    
    print()
    print("=" * 80)
    print(f"Total Grok API calls: {api_call_count}")
    print(f"Expected calls (n*log2(n)): {int(len(companies) * __import__('math').log2(len(companies)))}")
    print(f"Time elapsed: {elapsed_time:.2f} seconds")
    print("=" * 80)


if __name__ == "__main__":
    main()

