#!/usr/bin/env python3
"""
Company Keywords Generator
Uses Grok API directly to generate 100 keywords/phrases about what a company does.

Example: If you input "Google", it will return keywords like:
- Search
- Cloud
- AI
- Information Technology
- Software
- etc.
"""

import os
import sys
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

# Add parent directory to path to import modules
# Script is now in company_keywords/ folder in root, so go up one level to root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from openai import OpenAI
    from config import XAI_API_KEY
    GROK_AVAILABLE = True
except ImportError:
    GROK_AVAILABLE = False
    print("Error: Could not import OpenAI client or XAI_API_KEY. Make sure dependencies are installed.")
    sys.exit(1)

# Import ticker lookup functionality
try:
    from src.scoring.scorer import load_ticker_lookup, resolve_to_company_name
except ImportError:
    print("Error: Could not import scorer module.")
    sys.exit(1)

# =============================================================================
# CONFIGURABLE SETTINGS
# =============================================================================

# Compounding weight for keyword matching
# Each keyword is weighted by position: word N has weight = COMPOUNDING_WEIGHT ^ (total_keywords - N)
# With 1.1, word 1 is ~10% more valuable than word 2, word 54 is ~10% more valuable than word 55
# Set to 1.0 for equal weighting (no position preference)
COMPOUNDING_WEIGHT = 1.0

# =============================================================================

# Grok API pricing (per million tokens)
# Reasoning tokens are charged at output rate
GROK_PRICING = {
    "grok-4-1-fast-reasoning": {"input": 0.20, "output": 0.50, "reasoning": 0.50},
    "grok-3-fast": {"input": 5.0, "output": 15.0, "reasoning": 15.0},
    "grok-3": {"input": 3.0, "output": 15.0, "reasoning": 15.0},
}

def calculate_grok_cost(token_usage: dict, model: str = "grok-4-1-fast-reasoning") -> float:
    """Calculate cost in dollars based on token usage including reasoning tokens."""
    pricing = GROK_PRICING.get(model, GROK_PRICING["grok-4-1-fast-reasoning"])
    input_tokens = token_usage.get('prompt_tokens', 0)
    output_tokens = token_usage.get('completion_tokens', 0)
    reasoning_tokens = token_usage.get('reasoning_tokens', 0)
    
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    reasoning_cost = (reasoning_tokens / 1_000_000) * pricing["reasoning"]
    
    return input_cost + output_cost + reasoning_cost


def calculate_weighted_match(keywords1: List[str], keywords2: List[str]) -> tuple[float, float, list]:
    """
    Calculate weighted match score between two keyword lists.
    
    Keywords earlier in the list have higher weight based on COMPOUNDING_WEIGHT.
    Word at position i has weight = COMPOUNDING_WEIGHT ^ (n - i) where n = total keywords.
    
    Returns:
        Tuple of (weighted_match_score, max_possible_score, list of matching keywords with weights)
    """
    n1 = len(keywords1)
    n2 = len(keywords2)
    
    # Create weighted dictionaries (keyword -> weight) for each list
    # Position 0 (first keyword) has highest weight
    weights1 = {}
    for i, kw in enumerate(keywords1):
        kw_lower = kw.lower()
        weight = COMPOUNDING_WEIGHT ** (n1 - 1 - i)  # First word: weight^(n-1), last word: weight^0 = 1
        weights1[kw_lower] = (weight, kw)  # Store weight and original case
    
    weights2 = {}
    for i, kw in enumerate(keywords2):
        kw_lower = kw.lower()
        weight = COMPOUNDING_WEIGHT ** (n2 - 1 - i)
        weights2[kw_lower] = (weight, kw)
    
    # Find matches and calculate weighted score
    matching_keywords = []
    weighted_score = 0.0
    
    for kw_lower in weights1:
        if kw_lower in weights2:
            w1, orig1 = weights1[kw_lower]
            w2, orig2 = weights2[kw_lower]
            # Use the smaller weight to ensure score never exceeds 100%
            min_weight = min(w1, w2)
            weighted_score += min_weight
            matching_keywords.append((orig1, min_weight))
    
    # Calculate max possible score (if all keywords matched)
    # Use the smaller list as base
    if n1 <= n2:
        max_score = sum(COMPOUNDING_WEIGHT ** (n1 - 1 - i) for i in range(n1))
    else:
        max_score = sum(COMPOUNDING_WEIGHT ** (n2 - 1 - i) for i in range(n2))
    
    # Sort matching keywords by weight (highest first)
    matching_keywords.sort(key=lambda x: x[1], reverse=True)
    
    return weighted_score, max_score, matching_keywords


def generate_company_keywords(company_name: str, ticker: Optional[str] = None) -> tuple[List[str], dict]:
    """
    Generate 100 keywords/phrases about what a company does using Grok API.
    
    Args:
        company_name: Name of the company
        ticker: Optional ticker symbol (for context)
        
    Returns:
        Tuple of (keywords_list, token_usage_dict)
    """
    if not GROK_AVAILABLE:
        raise Exception("Grok API client not available.")
    
    if not XAI_API_KEY:
        raise Exception("XAI_API_KEY not configured. Please set it in config.py or as an environment variable.")
    
    # Initialize xAI Grok client
    client = OpenAI(
        api_key=XAI_API_KEY,
        base_url="https://api.x.ai/v1"
    )
    
    # Create prompt
    ticker_context = f" (stock ticker: {ticker})" if ticker else ""
    prompt = f"""List exactly 100 industries and sectors that {company_name}{ticker_context} operates in or is related to.

Focus on:
- Primary industries the company operates in (e.g., "Semiconductors", "Software", "Retail")
- Sub-sectors and niches (e.g., "Cloud Computing", "Artificial Intelligence", "E-commerce")
- Adjacent industries they serve or partner with (e.g., "Automotive", "Healthcare", "Finance")
- Technology sectors (e.g., "Data Analytics", "Cybersecurity", "Internet of Things")
- Market segments (e.g., "Enterprise Software", "Consumer Electronics", "B2B Services")
- Business categories (e.g., "SaaS", "Digital Advertising", "Payment Processing")

IMPORTANT: Use GENERIC industry/sector terms only.
- Say "Email Services" NOT "Gmail"
- Say "Cloud Computing" NOT "Google Cloud"
- Say "Search Engine" NOT "Google Search"
- Say "Streaming Video" NOT "YouTube"

DO NOT include:
- Company-specific product names or brand names
- Proprietary terms or trademarks
- Individual product names

Return ONLY a comma-separated list of exactly 100 industries/sectors. No numbers, bullets, or formatting.

Example output format:
Information Technology, Software, Cloud Computing, Artificial Intelligence, Digital Advertising, Search Engine, Internet Services, Data Analytics, Machine Learning, Mobile Operating Systems, Web Browser, Enterprise Software, Consumer Electronics, E-commerce, Video Streaming, Email Services, Productivity Software, Cybersecurity, Data Centers, Autonomous Vehicles"""

    print(f"Querying Grok API to generate keywords for {company_name}...")
    
    # Call Grok API directly
    response = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are a financial analyst that identifies industries and sectors companies operate in. Always use GENERIC industry/sector terms, NOT company-specific product names or brands. For example, use 'Email Services' not 'Gmail', 'Cloud Computing' not 'Google Cloud'. Return exactly the requested number of industries/sectors in a clean, comma-separated format."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        model="grok-4-1-fast-reasoning",
        temperature=0.7,
        max_tokens=2000
    )
    
    response_text = response.choices[0].message.content
    
    # Capture all token usage including reasoning tokens
    token_usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens
    }
    
    # Check for reasoning tokens (reasoning models have additional token types)
    if hasattr(response.usage, 'completion_tokens_details') and response.usage.completion_tokens_details:
        details = response.usage.completion_tokens_details
        if hasattr(details, 'reasoning_tokens'):
            token_usage["reasoning_tokens"] = details.reasoning_tokens
        if hasattr(details, 'text_tokens'):
            token_usage["text_tokens"] = details.text_tokens
    
    # Calculate reasoning tokens from the difference if not provided
    if "reasoning_tokens" not in token_usage:
        calculated_reasoning = token_usage["total_tokens"] - token_usage["prompt_tokens"] - token_usage["completion_tokens"]
        if calculated_reasoning > 0:
            token_usage["reasoning_tokens"] = calculated_reasoning
    
    # Parse the response - extract keywords from comma-separated list
    keywords = []
    response_clean = response_text.strip()
    
    # Remove any leading/trailing text that might not be keywords
    # Look for the actual list (might have some intro text)
    lines = response_clean.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Remove common prefixes like "Keywords:", "Here are:", etc.
        for prefix in ["Keywords:", "Here are", "The keywords", "Keywords for", "1.", "-"]:
            if line.lower().startswith(prefix.lower()):
                line = line[len(prefix):].strip()
                # Remove leading colon if present
                if line.startswith(':'):
                    line = line[1:].strip()
                break
        
        # Split by comma and clean each keyword
        for keyword in line.split(','):
            keyword = keyword.strip()
            # Remove quotes if present
            if keyword.startswith('"') and keyword.endswith('"'):
                keyword = keyword[1:-1]
            if keyword.startswith("'") and keyword.endswith("'"):
                keyword = keyword[1:-1]
            # Remove trailing periods, colons, etc.
            keyword = keyword.rstrip('.;:')
            if keyword:
                keywords.append(keyword)
    
    # If we got fewer than 100, try to split more aggressively
    if len(keywords) < 50:
        # Maybe the response is all on one line with commas
        all_text = response_clean.replace('\n', ' ')
        keywords = [k.strip().rstrip('.;:') for k in all_text.split(',') if k.strip()]
    
    # Limit to 100 if we got more
    keywords = keywords[:100]
    
    return keywords, token_usage


def format_keywords_output(keywords: List[str], format_type: str = "list") -> str:
    """
    Format keywords for output.
    
    Args:
        keywords: List of keywords
        format_type: "list" (one per line), "comma" (comma-separated), or "json" (JSON array)
        
    Returns:
        Formatted string
    """
    if format_type == "json":
        return json.dumps(keywords, indent=2)
    elif format_type == "comma":
        return ", ".join(keywords)
    else:  # list
        return "\n".join(keywords)


def load_cached_keywords():
    """Load cached keywords from JSON file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, "keywords.json")
    
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"companies": {}}


def compare_tickers(ticker1, ticker2, ticker_lookup):
    """Compare keywords between two tickers and calculate match percentage."""
    cached_data = load_cached_keywords()
    companies = cached_data.get("companies", {})
    
    # Resolve ticker1
    ticker1_upper = ticker1.strip().upper()
    if ticker1_upper in ticker_lookup:
        key1 = ticker1_upper
    else:
        key1 = ticker1_upper
    
    # Resolve ticker2
    ticker2_upper = ticker2.strip().upper()
    if ticker2_upper in ticker_lookup:
        key2 = ticker2_upper
    else:
        key2 = ticker2_upper
    
    # Check if both tickers are cached
    if key1 not in companies:
        print(f"Error: {key1} not found in cache. Run it first to generate keywords.")
        return
    if key2 not in companies:
        print(f"Error: {key2} not found in cache. Run it first to generate keywords.")
        return
    
    # Get keywords
    data1 = companies[key1]
    data2 = companies[key2]
    keywords1 = data1.get("keywords", [])
    keywords2 = data2.get("keywords", [])
    name1 = data1.get("company_name", key1)
    name2 = data2.get("company_name", key2)
    
    # Calculate weighted match
    weighted_score, max_score, matching_keywords = calculate_weighted_match(keywords1, keywords2)
    
    # Calculate weighted percentage
    if max_score == 0:
        weighted_percent = 0.0
    else:
        weighted_percent = (weighted_score / max_score) * 100
    
    # Display results
    print()
    print("=" * 80)
    print(f"Keyword Comparison: {key1} vs {key2}")
    print("=" * 80)
    print(f"  {key1} ({name1}): {len(keywords1)} keywords")
    print(f"  {key2} ({name2}): {len(keywords2)} keywords")
    print()
    print(f"  Matching keywords: {len(matching_keywords)}")
    print(f"  Weighted score:    {weighted_score:.2f} / {max_score:.2f}")
    print(f"  Weighted match:    {weighted_percent:.1f}%")
    print(f"  (Compounding weight: {COMPOUNDING_WEIGHT})")
    print()
    
    if matching_keywords:
        print("Matching keywords (sorted by weight):")
        print("-" * 80)
        for i, (keyword, weight) in enumerate(matching_keywords, 1):
            print(f"  {i:3d}. {keyword} (weight: {weight:.2f})")
    
    print()


def compare_one_vs_all(ticker):
    """Compare one ticker against all other cached tickers and rank by weighted match score."""
    cached_data = load_cached_keywords()
    companies = cached_data.get("companies", {})
    
    ticker_upper = ticker.strip().upper()
    
    if ticker_upper not in companies:
        print(f"Error: {ticker_upper} not found in cache. Run it first to generate keywords.")
        return
    
    other_tickers = [t for t in companies.keys() if t != ticker_upper]
    
    if len(other_tickers) == 0:
        print("Error: No other tickers in cache to compare against.")
        return
    
    # Get the target ticker's keywords
    data1 = companies[ticker_upper]
    keywords1 = data1.get("keywords", [])
    name1 = data1.get("company_name", ticker_upper)
    
    print()
    print("=" * 80)
    print(f"Comparing {ticker_upper} ({name1}) against {len(other_tickers)} other tickers")
    print(f"(Compounding weight: {COMPOUNDING_WEIGHT})")
    print("=" * 80)
    print()
    
    # Calculate comparisons
    comparisons = []
    
    for other_ticker in other_tickers:
        data2 = companies[other_ticker]
        keywords2 = data2.get("keywords", [])
        name2 = data2.get("company_name", other_ticker)
        
        weighted_score, max_score, matching_keywords = calculate_weighted_match(keywords1, keywords2)
        
        if max_score == 0:
            weighted_percent = 0.0
        else:
            weighted_percent = (weighted_score / max_score) * 100
        
        comparisons.append({
            'ticker': other_ticker,
            'name': name2,
            'matches': len(matching_keywords),
            'weighted_score': weighted_score,
            'max_score': max_score,
            'percent': weighted_percent
        })
    
    # Sort by weighted percentage (descending)
    comparisons.sort(key=lambda x: x['percent'], reverse=True)
    
    # Display results
    print(f"{'Rank':<6} {'Ticker':<10} {'Company':<30} {'Match %':<10} {'Matches':<10}")
    print("-" * 80)
    
    for rank, comp in enumerate(comparisons, 1):
        name_truncated = comp['name'][:28] + '..' if len(comp['name']) > 30 else comp['name']
        print(f"{rank:<6} {comp['ticker']:<10} {name_truncated:<30} {comp['percent']:.1f}%{'':<5} {comp['matches']}")
    
    print()
    if comparisons:
        avg_match = sum(c['percent'] for c in comparisons) / len(comparisons)
        print(f"Average weighted match with {ticker_upper}: {avg_match:.1f}%")
    print()


def compare_all_tickers():
    """Compare all pairs of cached tickers and rank by weighted match score."""
    cached_data = load_cached_keywords()
    companies = cached_data.get("companies", {})
    
    tickers = list(companies.keys())
    
    if len(tickers) < 2:
        print("Error: Need at least 2 tickers in cache to compare.")
        return
    
    print()
    print("=" * 80)
    print(f"Comparing all {len(tickers)} tickers ({len(tickers) * (len(tickers) - 1) // 2} pairs)")
    print(f"(Compounding weight: {COMPOUNDING_WEIGHT})")
    print("=" * 80)
    print()
    
    # Calculate all pair comparisons
    comparisons = []
    
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            key1 = tickers[i]
            key2 = tickers[j]
            
            data1 = companies[key1]
            data2 = companies[key2]
            keywords1 = data1.get("keywords", [])
            keywords2 = data2.get("keywords", [])
            
            weighted_score, max_score, matching_keywords = calculate_weighted_match(keywords1, keywords2)
            
            if max_score == 0:
                weighted_percent = 0.0
            else:
                weighted_percent = (weighted_score / max_score) * 100
            
            comparisons.append({
                'ticker1': key1,
                'ticker2': key2,
                'matches': len(matching_keywords),
                'percent': weighted_percent
            })
    
    # Sort by weighted percentage (descending)
    comparisons.sort(key=lambda x: x['percent'], reverse=True)
    
    # Display top 100 and bottom 100
    print(f"{'Rank':<6} {'Ticker 1':<10} {'Ticker 2':<10} {'Match %':<10} {'Matches':<10}")
    print("-" * 80)
    
    # Top 100
    print("TOP 100 MATCHES:")
    for rank, comp in enumerate(comparisons[:100], 1):
        print(f"{rank:<6} {comp['ticker1']:<10} {comp['ticker2']:<10} {comp['percent']:.1f}%{'':<5} {comp['matches']}")
    
    if len(comparisons) > 200:
        print()
        print(f"... {len(comparisons) - 200} more comparisons ...")
        print()
    
    # Bottom 100
    if len(comparisons) > 100:
        print("-" * 80)
        print("BOTTOM 100 MATCHES:")
        bottom_100 = comparisons[-100:]
        start_rank = len(comparisons) - 99
        for i, comp in enumerate(bottom_100):
            rank = start_rank + i
            print(f"{rank:<6} {comp['ticker1']:<10} {comp['ticker2']:<10} {comp['percent']:.1f}%{'':<5} {comp['matches']}")
    
    print()
    print(f"Total comparisons: {len(comparisons)}")
    if comparisons:
        avg_match = sum(c['percent'] for c in comparisons) / len(comparisons)
        print(f"Average weighted match: {avg_match:.1f}%")
    
    # Save results to JSON
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, "comparisons.json")
    
    results_data = {
        "compounding_weight": COMPOUNDING_WEIGHT,
        "total_tickers": len(tickers),
        "total_comparisons": len(comparisons),
        "average_match_percent": avg_match if comparisons else 0.0,
        "comparisons": comparisons
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved to {filepath}")
    print()


def redo_all_tickers(ticker_lookup, max_workers=5):
    """Regenerate keywords for all cached tickers using multithreading."""
    cached_data = load_cached_keywords()
    companies = cached_data.get("companies", {})
    
    tickers = list(companies.keys())
    
    if len(tickers) == 0:
        print("Error: No tickers in cache to regenerate.")
        return
    
    start_time = time.time()
    
    print()
    print("=" * 80)
    print(f"Regenerating keywords for {len(tickers)} tickers ({max_workers} threads)")
    print("=" * 80)
    print()
    
    # Thread-safe counters and lock
    results_lock = threading.Lock()
    results = []
    completed_count = [0]  # Use list for mutable counter in closure
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, "keywords.json")
    
    def process_single_ticker(ticker):
        """Process a single ticker in a thread."""
        try:
            company_name = companies[ticker].get("company_name", ticker)
            
            # Generate new keywords (API call)
            keywords, token_usage = generate_company_keywords(company_name, ticker)
            
            # Calculate cost
            cost = calculate_grok_cost(token_usage, model="grok-4-1-fast-reasoning")
            cost_cents = cost * 100
            
            return {
                "ticker": ticker,
                "company_name": company_name,
                "keywords": keywords,
                "token_usage": token_usage,
                "cost": cost,
                "cost_cents": cost_cents,
                "success": True,
                "error": None
            }
        except Exception as e:
            return {
                "ticker": ticker,
                "success": False,
                "error": str(e)
            }
    
    # Run in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {executor.submit(process_single_ticker, ticker): ticker for ticker in tickers}
        
        # Process results as they complete
        for future in as_completed(future_to_ticker):
            result = future.result()
            ticker = result["ticker"]
            
            with results_lock:
                completed_count[0] += 1
                count = completed_count[0]
                
                if result["success"]:
                    print(f"[{count}/{len(tickers)}] ✓ {ticker}: {len(result['keywords'])} keywords, {result['cost_cents']:.4f} cents")
                    results.append(result)
                else:
                    print(f"[{count}/{len(tickers)}] ✗ {ticker}: {result['error']}")
    
    # Save all results to file at once
    print()
    print("Saving results...")
    
    # Reload current data
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            all_data = json.load(f)
    else:
        all_data = {"companies": {}}
    
    # Update with all successful results
    for result in results:
        all_data["companies"][result["ticker"]] = {
            "company_name": result["company_name"],
            "ticker": result["ticker"],
            "keywords": result["keywords"],
            "count": len(result["keywords"]),
            "token_usage": result["token_usage"],
            "cost": {
                "dollars": result["cost"],
                "cents": result["cost_cents"]
            },
            "model": "grok-4-1-fast-reasoning"
        }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    
    # Summary
    total_cost = sum(r["cost_cents"] for r in results)
    success_count = len(results)
    fail_count = len(tickers) - success_count
    elapsed_time = time.time() - start_time
    
    print()
    print("=" * 80)
    print(f"Completed: {success_count}/{len(tickers)} tickers")
    if fail_count > 0:
        print(f"Failed: {fail_count}")
    print(f"Total cost: {total_cost:.4f} cents")
    print(f"Total time: {elapsed_time:.1f}s")
    print("=" * 80)
    print()


def run_all_tickers(ticker_lookup, max_workers=20):
    """Generate keywords for all tickers that have been scored (from scores.json)."""
    cached_data = load_cached_keywords()
    cached_tickers = set(cached_data.get("companies", {}).keys())
    
    # Get tickers from scores.json (not from the full ticker lookup)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    scores_file = os.path.join(script_dir, "..", "data", "scores.json")
    
    try:
        with open(scores_file, 'r', encoding='utf-8') as f:
            scores_data = json.load(f)
        all_tickers = list(scores_data.get("companies", {}).keys())
    except Exception as e:
        print(f"Error loading scores.json: {e}")
        return
    
    # Find tickers that need keywords generated
    tickers_to_process = [t for t in all_tickers if t not in cached_tickers]
    
    if len(tickers_to_process) == 0:
        print(f"\nAll {len(all_tickers)} tickers already have cached keywords.")
        print(f"Use 'redoall' to regenerate existing ones.")
        return
    
    start_time = time.time()
    
    print()
    print("=" * 80)
    print(f"Generating keywords for {len(tickers_to_process)} new tickers ({max_workers} threads)")
    print(f"(Skipping {len(cached_tickers)} already cached)")
    print(f"(Total in scores.json: {len(all_tickers)})")
    print("=" * 80)
    print()
    
    # Thread-safe counters and lock
    results_lock = threading.Lock()
    results = []
    completed_count = [0]
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, "keywords.json")
    
    def process_single_ticker(ticker):
        """Process a single ticker in a thread."""
        try:
            ticker_start = time.time()
            company_name = ticker_lookup.get(ticker, ticker)
            
            # Generate new keywords (API call)
            keywords, token_usage = generate_company_keywords(company_name, ticker)
            
            # Calculate cost
            cost = calculate_grok_cost(token_usage, model="grok-4-1-fast-reasoning")
            cost_cents = cost * 100
            elapsed = time.time() - ticker_start
            
            return {
                "ticker": ticker,
                "company_name": company_name,
                "keywords": keywords,
                "token_usage": token_usage,
                "cost": cost,
                "cost_cents": cost_cents,
                "elapsed": elapsed,
                "success": True,
                "error": None
            }
        except Exception as e:
            return {
                "ticker": ticker,
                "success": False,
                "error": str(e)
            }
    
    # Run in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {executor.submit(process_single_ticker, ticker): ticker for ticker in tickers_to_process}
        
        for future in as_completed(future_to_ticker):
            result = future.result()
            ticker = result["ticker"]
            
            with results_lock:
                completed_count[0] += 1
                count = completed_count[0]
                
                if result["success"]:
                    print(f"[{count}/{len(tickers_to_process)}] ✓ {ticker}: {len(result['keywords'])} keywords, {result['cost_cents']:.4f} cents, {result['elapsed']:.1f}s")
                    results.append(result)
                else:
                    print(f"[{count}/{len(tickers_to_process)}] ✗ {ticker}: {result['error']}")
    
    # Save all results to file at once
    print()
    print("Saving results...")
    
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            all_data = json.load(f)
    else:
        all_data = {"companies": {}}
    
    for result in results:
        all_data["companies"][result["ticker"]] = {
            "company_name": result["company_name"],
            "ticker": result["ticker"],
            "keywords": result["keywords"],
            "count": len(result["keywords"]),
            "token_usage": result["token_usage"],
            "cost": {
                "dollars": result["cost"],
                "cents": result["cost_cents"]
            },
            "model": "grok-4-1-fast-reasoning"
        }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    
    # Summary
    total_cost = sum(r["cost_cents"] for r in results)
    success_count = len(results)
    fail_count = len(tickers_to_process) - success_count
    elapsed_time = time.time() - start_time
    
    print()
    print("=" * 80)
    print(f"Completed: {success_count}/{len(tickers_to_process)} new tickers")
    if fail_count > 0:
        print(f"Failed: {fail_count}")
    print(f"Total cost: {total_cost:.4f} cents")
    print(f"Total time: {elapsed_time:.1f}s")
    print(f"Total cached: {len(all_data['companies'])}")
    print("=" * 80)
    print()


def process_ticker(input_str, ticker_lookup, force_refresh=False):
    """Process a single ticker/company and generate keywords."""
    # Try to resolve to company name and ticker
    input_upper = input_str.strip().upper()
    
    ticker = None
    company_name = None
    
    # Check if it's a ticker
    if input_upper in ticker_lookup:
        ticker = input_upper
        company_name = ticker_lookup[ticker]
        print(f"Found ticker: {ticker} = {company_name}")
    else:
        # Try to resolve it
        resolved_name, resolved_ticker = resolve_to_company_name(input_str)
        if resolved_ticker:
            ticker = resolved_ticker
            company_name = resolved_name
            print(f"Resolved: {ticker} = {company_name}")
        else:
            print(f"Error: '{input_str}' is not a valid ticker symbol.")
            return
    
    # Determine cache key
    if ticker:
        cache_key = ticker
    else:
        cache_key = company_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
        cache_key = ''.join(c for c in cache_key if c.isalnum() or c in ('_', '-'))
    
    # Check cache
    cached_data = load_cached_keywords()
    if cache_key in cached_data.get("companies", {}) and not force_refresh:
        cached_entry = cached_data["companies"][cache_key]
        keywords = cached_entry.get("keywords", [])
        
        print(f"\n✓ Using cached keywords for {cache_key} ({len(keywords)} keywords)")
        print("=" * 80)
        print()
        
        # Display keywords
        print("Keywords (cached):")
        print("-" * 80)
        for i, keyword in enumerate(keywords, 1):
            print(f"{i:3d}. {keyword}")
        
        print()
        print("(Use 'redo <ticker>' to regenerate keywords)")
        return
    
    print()
    
    # Generate keywords (not cached or force refresh)
    start_time = time.time()
    keywords, token_usage = generate_company_keywords(company_name, ticker)
    elapsed_time = time.time() - start_time
    
    print(f"\nGenerated {len(keywords)} keywords for {company_name}")
    print("=" * 80)
    print()
    
    # Display keywords
    print("Keywords:")
    print("-" * 80)
    for i, keyword in enumerate(keywords, 1):
        print(f"{i:3d}. {keyword}")
    
    print()
    print("=" * 80)
    print("Token Usage:")
    print(f"  Input tokens:     {token_usage.get('prompt_tokens', 0):,}")
    print(f"  Output tokens:    {token_usage.get('completion_tokens', 0):,}")
    if 'reasoning_tokens' in token_usage:
        print(f"  Reasoning tokens: {token_usage['reasoning_tokens']:,}")
    print(f"  Total tokens:     {token_usage.get('total_tokens', 0):,}")
    if 'cached_tokens' in token_usage:
        print(f"  Cached tokens:    {token_usage['cached_tokens']:,}")
    
    # Calculate and display cost
    cost = calculate_grok_cost(token_usage, model="grok-4-1-fast-reasoning")
    cost_cents = cost * 100
    cost_dollars = cost
    print()
    print(f"Cost: {cost_cents:.4f} cents")
    print(f"Time: {elapsed_time:.2f}s")
    
    # Automatically save to single JSON file in the same directory as the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, "keywords.json")
    
    # Load existing data or create new structure
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            all_data = json.load(f)
    else:
        all_data = {"companies": {}}
    
    # Use ticker as key if available, otherwise use sanitized company name
    if ticker:
        key = ticker
    else:
        key = company_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
        key = ''.join(c for c in key if c.isalnum() or c in ('_', '-'))
    
    # Add/update the company's keywords
    all_data["companies"][key] = {
        "company_name": company_name,
        "ticker": ticker,
        "keywords": keywords,
        "count": len(keywords),
        "token_usage": token_usage,
        "cost": {
            "dollars": cost_dollars,
            "cents": cost_cents
        },
        "model": "grok-4-1-fast-reasoning"
    }
    
    # Save back to file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved {len(keywords)} keywords for {key}")
    print(f"  Total companies in file: {len(all_data['companies'])}")


def main():
    """Main function to generate company keywords."""
    print("=" * 80)
    print("Company Keywords Generator")
    print("Uses Grok API (grok-4-1-fast-reasoning)")
    print("=" * 80)
    print("Commands:")
    print("  <ticker>              - Get keywords (uses cache if available)")
    print("  redo <ticker>         - Force regenerate keywords")
    print("  redoall               - Regenerate keywords for all cached tickers")
    print("  runall                - Generate keywords for all scorer tickers (skips cached)")
    print("  compare <ticker>      - Compare ticker against all others")
    print("  compare <t1> <t2>     - Compare keywords between two tickers")
    print("  all                   - Compare all pairs and rank by match %")
    print("  exit                  - Exit the program")
    print()
    
    if not GROK_AVAILABLE:
        print("Error: Grok API client not available.")
        sys.exit(1)
    
    if not XAI_API_KEY:
        print("Error: XAI_API_KEY not configured.")
        print("Please set it in config.py or as an environment variable.")
        sys.exit(1)
    
    # Load ticker lookup once
    ticker_lookup = load_ticker_lookup()
    
    # Process command line argument first if provided
    if len(sys.argv) > 1:
        input_str = " ".join(sys.argv[1:])
        force_refresh = input_str.lower().startswith('redo ')
        if force_refresh:
            input_str = input_str[5:].strip()
        try:
            process_ticker(input_str, ticker_lookup, force_refresh=force_refresh)
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()
        print()
    
    # Continuous loop
    while True:
        try:
            input_str = input("\nEnter ticker (or 'exit' to quit): ").strip()
            
            if not input_str:
                continue
            
            if input_str.lower() == 'exit':
                print("Goodbye!")
                break
            
            # Check for all command
            if input_str.lower() == 'all':
                compare_all_tickers()
                continue
            
            # Check for redoall command
            if input_str.lower() == 'redoall':
                redo_all_tickers(ticker_lookup)
                continue
            
            # Check for runall command
            if input_str.lower() == 'runall':
                run_all_tickers(ticker_lookup)
                continue
            
            # Check for compare command
            if input_str.lower().startswith('compare '):
                parts = input_str[8:].strip().split()
                if len(parts) >= 2:
                    compare_tickers(parts[0], parts[1], ticker_lookup)
                elif len(parts) == 1:
                    compare_one_vs_all(parts[0])
                else:
                    print("Usage: compare <ticker> or compare <ticker1> <ticker2>")
                continue
            
            # Check for redo command
            force_refresh = input_str.lower().startswith('redo ')
            if force_refresh:
                input_str = input_str[5:].strip()
            
            process_ticker(input_str, ticker_lookup, force_refresh=force_refresh)
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()
            print("\nContinuing...")  # Don't exit on error, just continue


if __name__ == "__main__":
    main()
