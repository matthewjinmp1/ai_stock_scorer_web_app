#!/usr/bin/env python3
"""
Scrape short interest data from Finviz for stocks in top_scores.db
and store the data in a new database.
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import os
import time
import re
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Database paths
TOP_SCORES_DB = os.path.join(os.path.dirname(__file__), "top_scores.db")
SHORT_INTEREST_DB = os.path.join(os.path.dirname(__file__), "short_interest.db")

# Finviz base URL
FINVIZ_BASE_URL = "https://finviz.com/quote.ashx?t="

# Headers to mimic a browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

def init_short_interest_db():
    """Initialize the short interest database."""
    conn = sqlite3.connect(SHORT_INTEREST_DB)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS short_interest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT UNIQUE NOT NULL,
            short_interest_percent REAL,
            scraped_at TEXT,
            error TEXT
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ticker ON short_interest(ticker)')
    conn.commit()
    conn.close()
    print(f"Initialized short interest database: {SHORT_INTEREST_DB}")

def get_tickers_from_top_scores():
    """Get all unique tickers from top_scores.db."""
    if not os.path.exists(TOP_SCORES_DB):
        raise FileNotFoundError(f"top_scores.db not found at {TOP_SCORES_DB}")
    
    conn = sqlite3.connect(TOP_SCORES_DB)
    cursor = conn.cursor()
    
    # Get the most recent entry for each ticker
    cursor.execute('''
        SELECT DISTINCT ticker
        FROM scores
        ORDER BY ticker
    ''')
    
    tickers = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return tickers

def parse_short_interest_value(value_str):
    """
    Parse a string value that might be a number, percentage, or 'N/A'.
    Handles formats like "10.5M", "1.2B", "50.5%", etc.
    """
    if not value_str or value_str.strip().upper() in ['N/A', 'NAN', '']:
        return None
    
    # Remove commas and percentage signs
    cleaned = value_str.replace(',', '').replace('%', '').strip().upper()
    
    # Handle multipliers (M = million, B = billion, K = thousand)
    multiplier = 1
    if cleaned.endswith('M'):
        multiplier = 1e6
        cleaned = cleaned[:-1]
    elif cleaned.endswith('B'):
        multiplier = 1e9
        cleaned = cleaned[:-1]
    elif cleaned.endswith('K'):
        multiplier = 1e3
        cleaned = cleaned[:-1]
    
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None

def scrape_finviz_short_interest(ticker):
    """
    Scrape short interest data from Finviz for a given ticker.
    
    Returns a dictionary with short interest data or None if error.
    """
    url = f"{FINVIZ_BASE_URL}{ticker.upper()}"
    response = None
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            
            # Handle rate limit errors (429) with retry
            if response.status_code == 429:
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    time.sleep(wait_time)
                    continue  # Retry
                else:
                    return {
                        'ticker': ticker.upper(),
                        'scraped_at': datetime.now().isoformat(),
                        'error': f"Rate limit error (429) after {max_retries} retries"
                    }
            
            # Handle 404 errors (ticker not found) - don't retry
            if response.status_code == 404:
                return {
                    'ticker': ticker.upper(),
                    'scraped_at': datetime.now().isoformat(),
                    'error': f"Ticker not found (404)"
                }
            
            # Raise for other HTTP errors
            response.raise_for_status()
            
            # Success - parse the response
            break
            
        except requests.exceptions.HTTPError as e:
            # Check if it's a 429 error in the exception
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 429:
                    if attempt < max_retries:
                        wait_time = retry_delay * (2 ** attempt)
                        time.sleep(wait_time)
                        continue  # Retry
                    else:
                        return {
                            'ticker': ticker.upper(),
                            'scraped_at': datetime.now().isoformat(),
                            'error': f"Rate limit error (429) after {max_retries} retries"
                        }
            
            # For other HTTP errors on last attempt, return error
            if attempt >= max_retries:
                return {
                    'ticker': ticker.upper(),
                    'scraped_at': datetime.now().isoformat(),
                    'error': f"HTTP error: {str(e)}"
                }
            # Otherwise retry after a short delay
            time.sleep(retry_delay * (2 ** attempt))
            
        except requests.exceptions.RequestException as e:
            # For other errors on last attempt, return error
            if attempt >= max_retries:
                return {
                    'ticker': ticker.upper(),
                    'scraped_at': datetime.now().isoformat(),
                    'error': f"Request error: {str(e)}"
                }
            # Otherwise retry after a short delay
            time.sleep(retry_delay * (2 ** attempt))
    
    if response is None:
        return {
            'ticker': ticker.upper(),
            'scraped_at': datetime.now().isoformat(),
            'error': "Failed to get response after retries"
        }
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the snapshot table (contains most financial metrics)
    snapshot_table = soup.find('table', class_='snapshot-table2')
    if not snapshot_table:
        return {
            'ticker': ticker,
            'error': "Could not find snapshot table"
        }
    
    # Parse the table - Finviz uses a grid layout with alternating label/value cells
    data = {'ticker': ticker.upper(), 'scraped_at': datetime.now().isoformat()}
    all_cells = snapshot_table.find_all('td')
    
    # Finviz table structure: label, value, label, value, etc.
    for i in range(0, len(all_cells) - 1, 2):
        if i + 1 >= len(all_cells):
            break
            
        label = all_cells[i].get_text(strip=True)
        value = all_cells[i + 1].get_text(strip=True)
        
        # Only look for Short Float (percentage of float)
        if 'Short Float' in label:
            # Short Float percentage
            data['short_interest_percent'] = parse_short_interest_value(value)
            break  # Found what we need, no need to continue
    
    return data

def save_short_interest_data(data, skip_rate_limit_errors=False):
    """
    Save short interest data to the database.
    
    Args:
        data: Dictionary with ticker and result data
        skip_rate_limit_errors: If True, don't save 429 errors (so they can be retried)
    """
    # Don't save rate limit errors if flag is set (so they can be retried)
    if skip_rate_limit_errors:
        error = data.get('error', '')
        if '429' in str(error) or 'Rate limit' in str(error):
            return  # Don't save, so it can be retried
    
    conn = sqlite3.connect(SHORT_INTEREST_DB)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO short_interest (
            ticker, short_interest_percent, scraped_at, error
        ) VALUES (?, ?, ?, ?)
    ''', (
        data.get('ticker'),
        data.get('short_interest_percent'),
        data.get('scraped_at'),
        data.get('error')
    ))
    
    conn.commit()
    conn.close()

def scrape_single_ticker(ticker, delay=1.0, rate_limit_errors=None):
    """
    Scrape short interest for a single ticker. Used for multithreading.
    
    Args:
        ticker: Ticker symbol to scrape
        delay: Delay before making request (for rate limiting)
        rate_limit_errors: Shared list to track rate limit errors (for monitoring)
    
    Returns:
        Dictionary with ticker and result data
    """
    # Rate limiting delay
    if delay > 0:
        time.sleep(delay)
    
    data = scrape_finviz_short_interest(ticker)
    
    # Track rate limit errors if shared list provided
    if rate_limit_errors is not None and '429' in str(data.get('error', '')):
        rate_limit_errors.append(ticker)
    
    # Don't save rate limit errors - they should be retried
    # Only save if we got data or a non-rate-limit error
    skip_save = '429' in str(data.get('error', '')) or 'Rate limit' in str(data.get('error', ''))
    save_short_interest_data(data, skip_rate_limit_errors=skip_save)
    
    return data

def calculate_optimal_threads(delay, max_requests_per_second=10):
    """
    Calculate optimal number of threads based on delay to maximize throughput
    while staying within rate limits. Uses conservative default to avoid 429 errors.
    
    Args:
        delay: Delay between requests in seconds (per thread)
        max_requests_per_second: Maximum safe requests per second (default: 10, conservative)
    
    Returns:
        Optimal number of threads
    """
    if delay <= 0:
        return 1
    
    # With delay, each thread makes 1 request per (delay) seconds
    # So requests per second per thread = 1 / delay
    # Optimal threads = max_requests_per_second / requests_per_second_per_thread
    # = max_requests_per_second * delay
    
    optimal = int(max_requests_per_second * delay)
    
    # Ensure at least 1 thread, but cap at reasonable maximum (e.g., 30 for safety)
    optimal = max(1, min(optimal, 30))
    
    return optimal

def scrape_all_tickers(limit=None, delay=1.0, resume_from=None, max_workers=None):
    """
    Scrape short interest data for all tickers using multithreading.
    
    Args:
        limit: Maximum number of tickers to scrape (None for all)
        delay: Delay between requests in seconds (per thread)
        resume_from: Ticker to resume from (skip all before this)
        max_workers: Number of concurrent threads (None = auto-calculate based on delay)
    """
    print("=" * 80)
    print("FINVIZ SHORT INTEREST SCRAPER")
    print("=" * 80)
    print()
    
    # Calculate optimal thread count if not specified
    if max_workers is None:
        max_workers = calculate_optimal_threads(delay)
        print(f"Auto-calculated optimal threads: {max_workers} (based on {delay}s delay)")
    else:
        print(f"Using specified thread count: {max_workers}")
    
    # Calculate effective rate
    requests_per_second = max_workers / delay if delay > 0 else max_workers
    print(f"Effective rate: ~{requests_per_second:.1f} requests/second")
    print()
    
    # Initialize database
    init_short_interest_db()
    
    # Get tickers
    print("Loading tickers from top_scores.db...")
    tickers = get_tickers_from_top_scores()
    print(f"Found {len(tickers):,} tickers")
    
    if limit:
        tickers = tickers[:limit]
        print(f"Limiting to first {limit:,} tickers")
    
    # Resume from a specific ticker if provided
    if resume_from:
        try:
            start_idx = tickers.index(resume_from.upper())
            tickers = tickers[start_idx:]
            print(f"Resuming from ticker: {resume_from.upper()}")
        except ValueError:
            print(f"Warning: Ticker {resume_from} not found, starting from beginning")
    
    print()
    print("Starting scraping with multithreading...")
    print(f"Using {max_workers} concurrent threads")
    print(f"Delay per request: {delay} seconds")
    print("-" * 80)
    
    success_count = 0
    error_count = 0
    skipped_count = 0
    results_lock = threading.Lock()
    
    # Check which tickers are already in the database
    # Exclude tickers with 429 errors so they can be retried
    conn = sqlite3.connect(SHORT_INTEREST_DB)
    cursor = conn.cursor()
    # Get tickers that exist, but exclude those with rate limit errors (429)
    cursor.execute('''
        SELECT ticker FROM short_interest 
        WHERE error IS NULL OR error NOT LIKE '%429%' AND error NOT LIKE '%Rate limit%'
    ''')
    existing_tickers = set(row[0] for row in cursor.fetchall())
    
    # Count how many have valid data vs errors
    cursor.execute('SELECT COUNT(*) FROM short_interest WHERE short_interest_percent IS NOT NULL AND error IS NULL')
    valid_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM short_interest WHERE error IS NOT NULL OR short_interest_percent IS NULL')
    error_or_null_count = cursor.fetchone()[0]
    
    # Count rate limit errors that will be retried
    cursor.execute('SELECT COUNT(*) FROM short_interest WHERE error LIKE "%429%" OR error LIKE "%Rate limit%"')
    rate_limit_count = cursor.fetchone()[0]
    conn.close()
    
    print(f"Found {len(existing_tickers):,} tickers already in database (excluding rate limit errors)")
    print(f"  - With valid data: {valid_count:,}")
    print(f"  - With errors/null: {error_or_null_count:,}")
    if rate_limit_count > 0:
        print(f"  - Rate limit errors (will retry): {rate_limit_count:,}")
    print(f"Will skip existing tickers and retry rate-limited ones")
    print()
    
    # Filter out tickers already in database (excluding rate limit errors)
    # Also include tickers that have rate limit errors in the database
    conn = sqlite3.connect(SHORT_INTEREST_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT ticker FROM short_interest WHERE error LIKE "%429%" OR error LIKE "%Rate limit%"')
    rate_limited_tickers = set(row[0] for row in cursor.fetchall())
    conn.close()
    
    # Include tickers that are new OR have rate limit errors
    tickers_to_scrape = [t for t in tickers if t not in existing_tickers or t in rate_limited_tickers]
    skipped_count = len(tickers) - len(tickers_to_scrape)
    
    if skipped_count > 0:
        print(f"Skipping {skipped_count:,} tickers already in database")
    print(f"Scraping {len(tickers_to_scrape):,} new tickers")
    print()
    
    if len(tickers_to_scrape) == 0:
        print("No new tickers to scrape!")
        return
    
    # Use ThreadPoolExecutor for parallel processing
    completed = 0
    rate_limit_errors = []  # Track rate limit errors to monitor if we're hitting limits
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_ticker = {
            executor.submit(scrape_single_ticker, ticker, delay, rate_limit_errors): ticker
            for ticker in tickers_to_scrape
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_ticker):
            completed += 1
            ticker = future_to_ticker[future]
            
            try:
                data = future.result()
                
                with results_lock:
                    error_msg = data.get('error', '')
                    
                    # Check if it's a rate limit error
                    if '429' in error_msg or 'Rate limit' in error_msg:
                        error_count += 1
                        print(f"[{completed}/{len(tickers_to_scrape)}] ✗ {ticker}: {error_msg} (will retry later)")
                    elif data.get('error'):
                        error_count += 1
                        print(f"[{completed}/{len(tickers_to_scrape)}] ✗ {ticker}: {error_msg}")
                    else:
                        success_count += 1
                        if data.get('short_interest_percent') is not None:
                            print(f"[{completed}/{len(tickers_to_scrape)}] ✓ {ticker}: {data['short_interest_percent']:.2f}%")
                        else:
                            print(f"[{completed}/{len(tickers_to_scrape)}] ✓ {ticker}: No data found")
                
                # Progress update every 100 tickers
                if completed % 100 == 0:
                    with results_lock:
                        rate_limit_count = len(rate_limit_errors)
                        print(f"\nProgress: {completed}/{len(tickers_to_scrape)} ({completed/len(tickers_to_scrape)*100:.1f}%)")
                        print(f"  Success: {success_count}, Errors: {error_count} (Rate limits: {rate_limit_count})")
                        if rate_limit_count > 10:
                            print(f"  ⚠ Warning: High rate limit errors detected. Consider reducing threads or increasing delay.")
                        print("-" * 80)
                    
            except Exception as e:
                with results_lock:
                    error_count += 1
                    print(f"[{completed}/{len(tickers_to_scrape)}] ✗ {ticker}: Exception - {str(e)}")
    
    # Retry rate-limited tickers with longer delays
    if rate_limit_errors:
        print(f"\n{'=' * 80}")
        print(f"RETRYING {len(rate_limit_errors)} TICKERS THAT HIT RATE LIMITS")
        print(f"{'=' * 80}")
        print("Waiting 30 seconds before retrying...")
        time.sleep(30)
        
        retry_success = 0
        retry_errors = 0
        
        for ticker in rate_limit_errors:
            print(f"Retrying {ticker}...", end=' ', flush=True)
            # Use longer delay for retries
            data = scrape_finviz_short_interest(ticker, max_retries=5, retry_delay=10)
            
            # Save the result (including if it still fails)
            # Only skip saving if it's still a rate limit error
            skip_save = '429' in str(data.get('error', '')) or 'Rate limit' in str(data.get('error', ''))
            save_short_interest_data(data, skip_rate_limit_errors=skip_save)
            
            if data.get('error'):
                # Check if it's still a rate limit error
                if '429' in str(data.get('error', '')) or 'Rate limit' in str(data.get('error', '')):
                    retry_errors += 1
                    print(f"✗ Still rate limited - will retry on next run")
                else:
                    retry_errors += 1
                    print(f"✗ {data['error']}")
            else:
                retry_success += 1
                if data.get('short_interest_percent') is not None:
                    print(f"✓ {data['short_interest_percent']:.2f}%")
                else:
                    print(f"✓ No data found")
            
            time.sleep(2)  # Extra delay between retries
        
        print(f"\nRetry results: {retry_success} succeeded, {retry_errors} still failed")
        if retry_errors > 0:
            print(f"Note: Tickers that still have rate limit errors will be retried on the next run")
    
    # Final summary
    print()
    print("=" * 80)
    print("SCRAPING COMPLETE")
    print("=" * 80)
    print(f"Total tickers in source: {len(tickers):,}")
    print(f"  Already in database (skipped): {skipped_count:,}")
    print(f"  Newly scraped (success): {success_count:,}")
    print(f"  Newly scraped (errors): {error_count:,}")
    print()
    
    # Show final database stats
    conn = sqlite3.connect(SHORT_INTEREST_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM short_interest WHERE short_interest_percent IS NOT NULL AND error IS NULL')
    total_with_data = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM short_interest WHERE error IS NOT NULL')
    total_errors = cursor.fetchone()[0]
    conn.close()
    
    print(f"Database statistics:")
    print(f"  Total tickers with valid data: {total_with_data:,}")
    print(f"  Total tickers with errors: {total_errors:,}")
    print()
    print(f"Data saved to: {SHORT_INTEREST_DB}")
    

if __name__ == "__main__":
    import sys
    
    # Parse command line arguments
    limit = None
    delay = 1.0
    resume_from = None
    
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print(f"Invalid limit: {sys.argv[1]}")
            sys.exit(1)
    
    if len(sys.argv) > 2:
        try:
            delay = float(sys.argv[2])
        except ValueError:
            print(f"Invalid delay: {sys.argv[2]}")
            sys.exit(1)
    
    if len(sys.argv) > 3:
        resume_from = sys.argv[3]
    
    # max_workers can be overridden with 4th argument (None = auto-calculate)
    max_workers = None
    if len(sys.argv) > 4:
        if sys.argv[4].lower() == 'auto':
            max_workers = None
        else:
            try:
                max_workers = int(sys.argv[4])
            except ValueError:
                print(f"Invalid max_workers: {sys.argv[4]}, using auto-calculation")
                max_workers = None
    
    scrape_all_tickers(limit=limit, delay=delay, resume_from=resume_from, max_workers=max_workers)

