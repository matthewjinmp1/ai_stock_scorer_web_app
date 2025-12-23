#!/usr/bin/env python3
"""
Glassdoor Rating Scraper
Uses Grok 4.1 via OpenRouter with search RAG capabilities to get Glassdoor ratings for companies based on stock ticker symbols.
"""

import sys
import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
    from src.clients.openrouter_client import OpenRouterClient
    from config import OPENROUTER_KEY
    OPENROUTER_AVAILABLE = True
except ImportError:
    OPENROUTER_AVAILABLE = False
    print("Warning: openrouter_client not found. Make sure openrouter_client.py is in the same directory.")
    OPENROUTER_KEY = None


def get_company_name_from_ticker(ticker):
    """
    Get company name from ticker symbol.
    First checks ticker_definitions.json, then falls back to yfinance.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')
        
    Returns:
        str: Company name, or None if not found
    """
    ticker_upper = ticker.strip().upper()
    
    # First, check ticker_definitions.json
    try:
        with open('data/ticker_definitions.json', 'r') as f:
            definitions = json.load(f)
            if ticker_upper in definitions.get('definitions', {}):
                return definitions['definitions'][ticker_upper]
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Warning: Could not read ticker_definitions.json: {e}")
    
    # Fall back to yfinance
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker_upper)
        info = stock.info
        company_name = info.get('longName') or info.get('shortName') or info.get('name')
        if company_name:
            return company_name
    except Exception as e:
        print(f"Warning: Could not get company name from yfinance: {e}")
    
    return None


# Model pricing per 1M tokens (same as scorer.py)
# Format: (input_cost_per_1M_tokens, output_cost_per_1M_tokens, cached_input_cost_per_1M_tokens) in USD
MODEL_PRICING = {
    "grok-4-1-fast-reasoning": (0.20, 0.50, 0.05),  # $0.20 per 1M input tokens, $0.50 per 1M output tokens, $0.05 per 1M cached input tokens
}


def calculate_token_cost(total_tokens, model="grok-4-1-fast-reasoning", token_usage=None):
    """Calculate the cost of tokens used.
    
    This function calculates costs using separate rates for:
    - Regular input tokens (non-cached)
    - Cached input tokens (typically cheaper)
    - Output tokens
    
    Args:
        total_tokens: Total number of tokens used (fallback if token_usage not provided)
        model: Model name to get pricing for
        token_usage: Optional token_usage dict with token breakdown. Expected fields:
            - input_tokens or prompt_tokens: total input tokens
            - output_tokens or completion_tokens: output tokens
            - cached_tokens, cached_input_tokens, or prompt_cache_hit_tokens: cached input tokens
        
    Returns:
        float: Total cost in USD
    """
    if model not in MODEL_PRICING:
        return 0.0
    
    pricing = MODEL_PRICING[model]
    input_cost_per_1M = pricing[0]
    output_cost_per_1M = pricing[1]
    cached_input_cost_per_1M = pricing[2] if len(pricing) > 2 else input_cost_per_1M
    
    # If we have breakdown of input/output/cached tokens, use that for more accurate pricing
    if token_usage:
        # Get total input/prompt tokens (may be called input_tokens or prompt_tokens)
        total_input_tokens = token_usage.get('input_tokens') if 'input_tokens' in token_usage else token_usage.get('prompt_tokens', 0)
        # Get output tokens (may be called output_tokens or completion_tokens)
        output_tokens = token_usage.get('output_tokens') if 'output_tokens' in token_usage else token_usage.get('completion_tokens', 0)
        # Get cached tokens (may be called cached_tokens, cached_input_tokens, or prompt_cache_hit_tokens)
        cached_tokens = (token_usage.get('cached_tokens') if 'cached_tokens' in token_usage else
                        token_usage.get('cached_input_tokens') if 'cached_input_tokens' in token_usage else
                        token_usage.get('prompt_cache_hit_tokens', 0))
        
        if total_input_tokens > 0 or output_tokens > 0 or cached_tokens > 0:
            # Calculate regular (non-cached) input tokens
            # Standard API format: prompt_tokens = regular_input + cached_input
            regular_input_tokens = total_input_tokens - cached_tokens
            
            # Calculate costs
            regular_input_cost = (regular_input_tokens / 1_000_000) * input_cost_per_1M
            cached_input_cost = (cached_tokens / 1_000_000) * cached_input_cost_per_1M
            output_cost = (output_tokens / 1_000_000) * output_cost_per_1M
            
            total_cost = regular_input_cost + cached_input_cost + output_cost
            return total_cost
    
    # Fallback: use total_tokens with average cost if no breakdown available
    # Use average of input and output costs as approximation
    avg_cost_per_1M = (input_cost_per_1M + output_cost_per_1M) / 2
    return (total_tokens / 1_000_000) * avg_cost_per_1M


def get_glassdoor_rating_with_grok(company_name, ticker, silent=False):
    """
    Use Grok 4.1 via OpenRouter with search RAG to get Glassdoor rating.
    
    Args:
        company_name: Name of the company to search for
        ticker: Stock ticker symbol
        silent: If True, suppress output messages
        
    Returns:
        dict: Dictionary containing rating data and snippet, or None if error
    """
    if not OPENROUTER_AVAILABLE:
        print("Error: OpenRouterClient not available.")
        return None
    
    try:
        # Initialize OpenRouter client with API key from config
        client = OpenRouterClient(api_key=OPENROUTER_KEY)
        
        # Create a prompt that asks Grok to search for Glassdoor rating
        # Grok 4.1 has built-in web search capabilities via tool calling
        prompt = f"""Search the web for the Glassdoor rating of {company_name} (stock ticker: {ticker}).

Please search for "{company_name} Glassdoor rating" and find the current overall rating from Glassdoor.

Extract and return:
1. The overall rating (out of 5.0)
2. The number of reviews (if available)
3. A brief snippet of the rating information
4. The Glassdoor URL if found

Format your response as JSON with the following structure:
{{
    "rating": <number between 0 and 5>,
    "num_reviews": <number or null>,
    "snippet": "<brief description>",
    "url": "<glassdoor url or null>"
}}

If you cannot find the rating, return null for the rating field."""

        if not silent:
            print(f"Querying Grok 4.1 (same model as scorer.py) to search for Glassdoor rating of {company_name}...")
        
        # Use the same model as scorer.py: grok-4-1-fast-reasoning
        # This maps to x-ai/grok-4.1-fast on OpenRouter
        # Grok 4.1 Fast is an agentic tool-calling model with built-in web search capabilities
        
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant with web search capabilities. When asked to find current information, you should use your web search tools to retrieve up-to-date data from the internet. Use search RAG (Retrieval-Augmented Generation) to find and cite accurate information."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Start timing
        start_time = time.time()
        
        # Call Grok 4.1 Fast with search RAG capabilities
        # Using the same model identifier as scorer.py: grok-4-1-fast-reasoning
        # Grok 4.1 Fast is an agentic tool-calling model that will use web search when needed
        # The prompt explicitly requests web search, so the model will use its search RAG capabilities
        response_text, token_usage = client.chat_completion_with_tokens(
            messages=messages,
            model="grok-4-1-fast-reasoning",  # Same model as scorer.py
            temperature=0.3,  # Lower temperature for more factual responses
            max_tokens=1000
            # Note: Grok 4.1 Fast automatically uses web search tools when the prompt
            # requests current/real-time information. The model is agentic and will
            # call search tools based on the context and prompt requirements.
        )
        
        # Calculate elapsed time
        elapsed_time = time.time() - start_time
        
        # Calculate cost
        total_cost = calculate_token_cost(
            total_tokens=token_usage.get('total_tokens', 0),
            model="grok-4-1-fast-reasoning",
            token_usage=token_usage
        )
        
        cost_cents = total_cost * 100
        if not silent:
            print(f"Time: {elapsed_time:.2f}s | Tokens: {token_usage.get('total_tokens', 0)} | Cost: {cost_cents:.4f} cents")
            print(f"\nGrok Response:\n{response_text}\n")
        
        # Try to parse JSON from the response
        # Grok might return JSON or natural language, so we'll try both
        rating_data = {
            "ticker": ticker,
            "company_name": company_name,
            "raw_response": response_text,
            "token_usage": token_usage,
            "elapsed_time": elapsed_time,
            "total_cost": total_cost
        }
        
        # Try to extract JSON from the response
        try:
            # Look for JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                parsed_data = json.loads(json_str)
                rating_data.update(parsed_data)
            else:
                # Try to extract rating from natural language
                import re
                rating_match = re.search(r'rating["\']?\s*[:=]\s*(\d+\.?\d*)', response_text, re.IGNORECASE)
                if rating_match:
                    rating_data["rating"] = float(rating_match.group(1))
                
                reviews_match = re.search(r'reviews?["\']?\s*[:=]\s*(\d+[,\d]*)', response_text, re.IGNORECASE)
                if reviews_match:
                    rating_data["num_reviews"] = int(reviews_match.group(1).replace(',', ''))
                
                url_match = re.search(r'https?://[^\s\)]+glassdoor[^\s\)]+', response_text, re.IGNORECASE)
                if url_match:
                    rating_data["url"] = url_match.group(0)
        except json.JSONDecodeError:
            # If JSON parsing fails, we'll use the raw response
            pass
        
        return rating_data
        
    except Exception as e:
        print(f"Error querying Grok: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_glassdoor_rating(ticker, silent=False):
    """
    Main function to get Glassdoor rating for a ticker using Grok 4.1 with search RAG.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')
        silent: If True, suppress output messages
        
    Returns:
        dict: Dictionary containing rating data and snippet, or None if error
    """
    ticker_upper = ticker.strip().upper()
    
    # Step 1: Get company name from ticker
    company_name = get_company_name_from_ticker(ticker_upper)
    if not company_name:
        if not silent:
            print(f"Error: Could not find company name for ticker {ticker_upper}")
        return None
    
    if not silent:
        print(f"Company name: {company_name}")
    
    # Step 2: Use Grok 4.1 with search RAG to get Glassdoor rating
    rating_data = get_glassdoor_rating_with_grok(company_name, ticker_upper, silent=silent)
    
    return rating_data


def display_snippet(result):
    """
    Display Glassdoor rating information from Grok search RAG in a formatted way.
    
    Args:
        result: Dictionary returned from get_glassdoor_rating()
    """
    if not result:
        print("No rating data to display.")
        return
    
    print("\n" + "=" * 80)
    print(f"Glassdoor Rating for {result.get('ticker', 'N/A')} (via Grok 4.1 Search RAG)")
    print("=" * 80)
    
    if 'company_name' in result:
        print(f"Company: {result['company_name']}")
    
    if 'rating' in result and result['rating'] is not None:
        rating = result['rating']
        print(f"\nOverall Rating: {rating:.2f} / 5.0")
        
        # Visual representation (using ASCII-safe characters for Windows compatibility)
        stars = int(rating)
        half_star = (rating - stars) >= 0.5
        star_chars = '*' * stars
        if half_star:
            star_chars += '.5'
        empty_stars = 5 - stars - (1 if half_star else 0)
        star_chars += '-' * empty_stars
        print(f"Stars: {star_chars} ({rating:.1f}/5.0)")
    else:
        print("\nRating: Not found in response")
    
    if 'num_reviews' in result and result.get('num_reviews'):
        print(f"Number of Reviews: {result['num_reviews']:,}")
    
    if 'url' in result and result.get('url'):
        print(f"\nGlassdoor URL: {result['url']}")
    
    if 'snippet' in result and result.get('snippet'):
        print(f"\nSnippet:")
        print("-" * 80)
        print(result['snippet'])
        print("-" * 80)
    
    if 'raw_response' in result:
        print(f"\nFull Grok Response:")
        print("-" * 80)
        print(result['raw_response'])
        print("-" * 80)
    
    if 'token_usage' in result:
        print(f"\nToken Usage:")
        print(json.dumps(result['token_usage'], indent=2))
    
    if 'elapsed_time' in result:
        print(f"\nFetch Time: {result['elapsed_time']:.2f} seconds")
    
    if 'total_cost' in result:
        cost_cents = result['total_cost'] * 100
        print(f"Total Cost: {cost_cents:.4f} cents")
    
    print("=" * 80)


def fetch_single_ticker(ticker, output_file, existing_data, lock):
    """
    Fetch Glassdoor rating for a single ticker and save it thread-safely.
    
    Args:
        ticker: Ticker symbol to fetch
        output_file: Path to output JSON file
        existing_data: Dictionary to store results (shared across threads)
        lock: Thread lock for safe file writing
        
    Returns:
        tuple: (ticker, success, result_dict or None)
    """
    # Fetch rating
    result = get_glassdoor_rating(ticker, silent=True)
    
    if result:
        # Prepare data to save
        ticker_data = {
            "rating": result.get("rating"),
            "num_reviews": result.get("num_reviews"),
            "snippet": result.get("snippet"),
            "url": result.get("url"),
            "company_name": result.get("company_name"),
            "token_usage": result.get("token_usage"),
            "elapsed_time": result.get("elapsed_time"),
            "total_cost": result.get("total_cost"),
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Thread-safe update
        with lock:
            existing_data["companies"][ticker] = ticker_data
            
            # Save to file
            try:
                with open(output_file, 'w') as f:
                    json.dump(existing_data, f, indent=2)
            except Exception as e:
                print(f"  ✗ Error saving {ticker}: {e}")
                return (ticker, False, None)
        
        return (ticker, True, ticker_data)
    else:
        return (ticker, False, None)


def fetch_all_glassdoor_ratings(scores_file="data/scores.json", output_file="data/glassdoor.json", max_workers=20):
    """
    Fetch Glassdoor ratings for all tickers in scores.json and save to glassdoor.json.
    Uses threading to fetch multiple tickers concurrently.
    
    Args:
        scores_file: Path to scores.json file
        output_file: Path to output glassdoor.json file
        max_workers: Maximum number of concurrent threads (default: 20)
    """
    print("=" * 80)
    print("Batch Glassdoor Rating Fetcher (via Grok 4.1 Search RAG)")
    print(f"Using {max_workers} concurrent threads")
    print("=" * 80)
    print()
    
    # Load scores.json to get all tickers
    try:
        with open(scores_file, 'r') as f:
            scores_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {scores_file} not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse {scores_file}: {e}")
        sys.exit(1)
    
    # Extract all tickers from scores.json
    companies = scores_data.get('companies', {})
    tickers = list(companies.keys())
    
    print(f"Found {len(tickers)} tickers in {scores_file}")
    print(f"Starting batch fetch with {max_workers} concurrent threads...\n")
    
    # Load existing glassdoor.json if it exists
    existing_data = {}
    try:
        with open(output_file, 'r') as f:
            existing_data = json.load(f)
    except FileNotFoundError:
        existing_data = {"companies": {}}
    except json.JSONDecodeError:
        existing_data = {"companies": {}}
    
    if "companies" not in existing_data:
        existing_data["companies"] = {}
    
    # Filter out tickers that already exist
    tickers_to_fetch = [t for t in tickers if t not in existing_data["companies"]]
    
    if not tickers_to_fetch:
        print(f"All {len(tickers)} tickers already exist in {output_file}")
        return
    
    skipped = len(tickers) - len(tickers_to_fetch)
    if skipped > 0:
        print(f"Skipping {skipped} tickers (already exist in {output_file})")
        print()
    
    print(f"Fetching {len(tickers_to_fetch)} tickers...\n")
    
    # Thread lock for safe file writing
    lock = threading.Lock()
    
    # Track statistics
    successful = 0
    failed = 0
    total_cost = 0.0
    total_time = 0.0
    start_time = time.time()
    
    # Process tickers with thread pool
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {
            executor.submit(fetch_single_ticker, ticker, output_file, existing_data, lock): ticker
            for ticker in tickers_to_fetch
        }
        
        # Process completed tasks
        completed = 0
        for future in as_completed(future_to_ticker):
            completed += 1
            ticker = future_to_ticker[future]
            
            try:
                ticker_result, success, data = future.result()
                
                if success and data:
                    successful += 1
                    total_cost += data.get("total_cost", 0)
                    total_time += data.get("elapsed_time", 0)
                    
                    rating = data.get("rating")
                    elapsed = data.get("elapsed_time", 0)
                    cost_cents = data.get("total_cost", 0) * 100
                    
                    if rating:
                        print(f"[{completed}/{len(tickers_to_fetch)}] ✓ {ticker}: {rating:.1f}/5.0 | {elapsed:.2f}s | {cost_cents:.4f} cents")
                    else:
                        print(f"[{completed}/{len(tickers_to_fetch)}] ✓ {ticker}: No rating found | {elapsed:.2f}s | {cost_cents:.4f} cents")
                else:
                    failed += 1
                    print(f"[{completed}/{len(tickers_to_fetch)}] ✗ {ticker}: Failed to fetch")
                    
            except Exception as e:
                failed += 1
                print(f"[{completed}/{len(tickers_to_fetch)}] ✗ {ticker}: Error - {e}")
    
    # Final summary
    elapsed_total = time.time() - start_time
    print()
    print("=" * 80)
    print("Batch Processing Complete")
    print("=" * 80)
    print(f"Total tickers: {len(tickers)}")
    print(f"  - Already existed: {skipped}")
    print(f"  - Fetched: {len(tickers_to_fetch)}")
    print(f"  - Successful: {successful}")
    print(f"  - Failed: {failed}")
    print(f"Total wall-clock time: {elapsed_total:.2f} seconds ({elapsed_total/60:.1f} minutes)")
    print(f"Total API time: {total_time:.2f} seconds")
    print(f"Total cost: {total_cost * 100:.4f} cents (${total_cost:.6f} USD)")
    print(f"\nResults saved to: {output_file}")


def main():
    """Main function to get Glassdoor rating via Grok 4.1 with search RAG."""
    # By default, fetch all tickers from scores.json
    # If a ticker is provided as argument, fetch only that ticker
    if len(sys.argv) > 1:
        # Single ticker mode
        ticker = sys.argv[1]
        print("=" * 80)
        print("Glassdoor Rating Fetcher (via Grok 4.1 Search RAG)")
        print("=" * 80)
        print()
        
        # Get the rating using Grok
        result = get_glassdoor_rating(ticker)
        
        if result:
            display_snippet(result)
        else:
            print(f"\nFailed to get Glassdoor rating for {ticker}")
            print("\nPossible reasons:")
            print("  - Company name not found for ticker")
            print("  - OpenRouter API key not configured (check OPENROUTER_KEY)")
            print("  - Network connection issue")
            print("  - OpenRouter API rate limiting")
            print("  - Grok could not find Glassdoor rating information")
            sys.exit(1)
        
        print("\nNote: This uses Grok 4.1's search RAG capabilities to find and extract the rating.")
    else:
        # Batch mode - fetch all tickers
        fetch_all_glassdoor_ratings()


if __name__ == "__main__":
    main()

