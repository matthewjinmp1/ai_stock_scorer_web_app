#!/usr/bin/env python3
"""
Calculate stock returns for tickers in scores.json
Calculates total return from December 1st to today for each ticker
"""

import json
import os
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import yfinance as yf

SCORES_FILE = "data/scores.json"
TICKER_FILE = "data/stock_tickers_clean.json"
RETURNS_FILE = "data/returns.json"


def load_scores():
    """Load scores from scores.json and extract tickers."""
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


def load_valid_tickers():
    """Load valid tickers from stock_tickers_clean.json."""
    if not os.path.exists(TICKER_FILE):
        print(f"Error: {TICKER_FILE} not found.")
        return set()
    
    try:
        with open(TICKER_FILE, 'r') as f:
            data = json.load(f)
        companies = data.get("companies", [])
        # Extract ticker symbols and convert to uppercase
        valid_tickers = {company.get("ticker", "").upper() for company in companies if company.get("ticker")}
        return valid_tickers
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error loading {TICKER_FILE}: {e}")
        return set()


def get_december_start_date():
    """Get December 1st of the current year, or previous year if we're before December."""
    today = date.today()
    # If we're in December or later, use this year's December
    # Otherwise use last year's December
    if today.month >= 12:
        return date(today.year, 12, 1)
    else:
        return date(today.year - 1, 12, 1)


def calculate_return(ticker):
    """Calculate total return for a ticker from December 1st to today."""
    try:
        # Get December start date
        start_date = get_december_start_date()
        end_date = date.today()
        
        # Download historical data
        stock = yf.Ticker(ticker)
        hist = stock.history(start=start_date, end=end_date)
        
        if hist.empty:
            return None, "No data available"
        
        # Get first and last closing prices
        first_price = hist.iloc[0]['Close']
        last_price = hist.iloc[-1]['Close']
        
        # Calculate return percentage
        if first_price == 0:
            return None, "Invalid price data"
        
        return_pct = ((last_price - first_price) / first_price) * 100
        
        return return_pct, None
        
    except Exception as e:
        return None, str(e)


def process_ticker(ticker, total, completed_lock, completed_count):
    """Wrapper function to process a ticker and update progress."""
    return_pct, error = calculate_return(ticker)
    
    # Thread-safe progress update
    with completed_lock:
        completed_count[0] += 1
        current = completed_count[0]
        if error:
            print(f"[{current}/{total}] {ticker}: Error - {error}")
        else:
            print(f"[{current}/{total}] {ticker}: {return_pct:.2f}%")
    
    return {
        'ticker': ticker,
        'return': return_pct,
        'error': error
    }


def main():
    """Main function to calculate and display returns."""
    print("=" * 60)
    print("Stock Returns Calculator")
    print("=" * 60)
    print()
    
    # Load scores and extract tickers
    print("Loading scores from scores.json...")
    scores_data = load_scores()
    if scores_data is None:
        return
    
    score_tickers = set(key.upper() for key in scores_data.keys())
    print(f"Found {len(score_tickers)} tickers in scores.json")
    
    # Load valid tickers
    print(f"Loading valid tickers from {TICKER_FILE}...")
    valid_tickers = load_valid_tickers()
    print(f"Found {len(valid_tickers)} valid tickers")
    
    # Filter to only tickers that are in both
    common_tickers = score_tickers.intersection(valid_tickers)
    print(f"\nFound {len(common_tickers)} tickers in both files")
    print()
    
    if not common_tickers:
        print("No common tickers found.")
        return
    
    # Get date range
    start_date = get_december_start_date()
    end_date = date.today()
    print(f"Calculating returns from {start_date} to {end_date}")
    print("Using multithreading to speed up processing...")
    print("=" * 60)
    print()
    
    # Calculate returns for each ticker using multithreading
    results = []
    total = len(common_tickers)
    sorted_tickers = sorted(common_tickers)
    
    # Thread-safe progress tracking
    completed_lock = Lock()
    completed_count = [0]
    
    # Use ThreadPoolExecutor with reasonable number of workers
    # Too many threads might overwhelm the API, 10-20 is usually good
    max_workers = min(20, total)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {
            executor.submit(process_ticker, ticker, total, completed_lock, completed_count): ticker
            for ticker in sorted_tickers
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_ticker):
            result = future.result()
            results.append(result)
    
    # Sort by return (highest first), with errors at the end
    results.sort(key=lambda x: (x['return'] is None, x['return'] or 0), reverse=True)
    
    # Display results
    print()
    print("=" * 60)
    print("RESULTS (sorted by return, highest first)")
    print("=" * 60)
    print(f"{'Ticker':<10} {'Return %':<15} {'Status':<20}")
    print("-" * 60)
    
    successful = 0
    failed = 0
    
    for result in results:
        ticker = result['ticker']
        if result['error']:
            print(f"{ticker:<10} {'N/A':<15} {result['error']:<20}")
            failed += 1
        else:
            return_pct = result['return']
            sign = "+" if return_pct >= 0 else ""
            print(f"{ticker:<10} {sign}{return_pct:>6.2f}%{'':<6} {'Success':<20}")
            successful += 1
    
    print("-" * 60)
    print(f"Total: {len(results)} tickers")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    
    # Calculate statistics
    successful_returns = [r['return'] for r in results if r['return'] is not None]
    if successful_returns:
        avg_return = sum(successful_returns) / len(successful_returns)
        positive_count = sum(1 for r in successful_returns if r > 0)
        negative_count = sum(1 for r in successful_returns if r < 0)
        
        print()
        print("=" * 60)
        print("STATISTICS")
        print("=" * 60)
        print(f"Average return: {avg_return:+.2f}%")
        print(f"Positive returns: {positive_count} ({positive_count/len(successful_returns)*100:.1f}%)")
        print(f"Negative returns: {negative_count} ({negative_count/len(successful_returns)*100:.1f}%)")
        if successful_returns:
            print(f"Best return: {max(successful_returns):+.2f}%")
            print(f"Worst return: {min(successful_returns):+.2f}%")
    
    # Save results to JSON file
    output_data = {
        "date_calculated": datetime.now().isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "returns": {}
    }
    
    for result in results:
        ticker = result['ticker']
        if result['return'] is not None:
            output_data["returns"][ticker] = {
                "return": result['return'],
                "status": "success"
            }
        else:
            output_data["returns"][ticker] = {
                "return": None,
                "status": "error",
                "error": result['error']
            }
    
    try:
        with open(RETURNS_FILE, 'w') as f:
            json.dump(output_data, f, indent=2)
        print()
        print("=" * 60)
        print(f"Results saved to {RETURNS_FILE}")
        print("=" * 60)
    except Exception as e:
        print(f"\nWarning: Could not save to {RETURNS_FILE}: {e}")


if __name__ == "__main__":
    main()

