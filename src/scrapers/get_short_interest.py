#!/usr/bin/env python3
"""
Batch Short Float Scraper
Scrapes Finviz for "Short Float" metric for tickers that are in both scores.json and stock_tickers_clean.json
Saves results to short_interest.json
"""

import json
import os
import sys
import time
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from src.scrapers.finviz_scraper import HEADERS
import requests
from bs4 import BeautifulSoup

# File paths
SCORES_FILE = "data/scores.json"
TICKER_FILE = "data/stock_tickers_clean.json"
SHORT_INTEREST_FILE = "data/short_interest.json"
TICKER_DEFINITIONS_FILE = "data/ticker_definitions.json"

# Rate limiting - delay between requests (in seconds)
REQUEST_DELAY = 1.0  # 1 second delay between requests to be respectful

# Batch processing
BATCH_SIZE = 100  # Save progress every N tickers
SAVE_INTERVAL = 10  # Save progress every N successful scrapes


def load_scored_tickers():
    """
    Load tickers from scores.json.
    
    Returns:
        set: Set of ticker symbols (uppercase)
    """
    if not os.path.exists(SCORES_FILE):
        print(f"Error: {SCORES_FILE} not found.")
        return None
    
    try:
        with open(SCORES_FILE, 'r') as f:
            data = json.load(f)
        
        # Get all ticker keys from companies dict
        tickers = set()
        for ticker in data.get('companies', {}).keys():
            ticker_upper = ticker.strip().upper()
            if ticker_upper:
                tickers.add(ticker_upper)
        
        return tickers
    except Exception as e:
        print(f"Error loading tickers from {SCORES_FILE}: {e}")
        return None


def load_custom_ticker_definitions():
    """
    Load custom ticker definitions from ticker_definitions.json.
    These are OTC or private companies that should be excluded.
    
    Returns:
        set: Set of ticker symbols (uppercase) to exclude
    """
    excluded_tickers = set()
    
    try:
        if os.path.exists(TICKER_DEFINITIONS_FILE):
            with open(TICKER_DEFINITIONS_FILE, 'r') as f:
                data = json.load(f)
                
                for ticker in data.get('definitions', {}).keys():
                    ticker_upper = ticker.strip().upper()
                    if ticker_upper:
                        excluded_tickers.add(ticker_upper)
    except Exception as e:
        print(f"Warning: Could not load custom ticker definitions: {e}")
    
    return excluded_tickers


def load_us_tickers():
    """
    Load all US-listed tickers from stock_tickers_clean.json.
    
    Returns:
        dict: Dictionary mapping ticker (uppercase) to (company_name, exchange) tuple
    """
    if not os.path.exists(TICKER_FILE):
        print(f"Error: {TICKER_FILE} not found.")
        return None
    
    try:
        with open(TICKER_FILE, 'r') as f:
            data = json.load(f)
        
        ticker_dict = {}
        for company in data.get('companies', []):
            ticker = company.get('ticker', '').strip().upper()
            name = company.get('name', '').strip()
            exchange = company.get('exchange', '').strip()
            
            # Only include US exchanges (NYSE, NASDAQ)
            if ticker and name and exchange in ['NYSE', 'NASDAQ']:
                ticker_dict[ticker] = (name, exchange)
        
        return ticker_dict
    except Exception as e:
        print(f"Error loading tickers from {TICKER_FILE}: {e}")
        return None


def get_tickers_to_scrape():
    """
    Get tickers that are in both scores.json and stock_tickers_clean.json,
    excluding tickers from ticker_definitions.json (OTC/private companies).
    
    Returns:
        list: List of (ticker, company_name, exchange) tuples
    """
    # Load tickers from scores.json
    print(f"Loading tickers from {SCORES_FILE}...")
    scored_tickers = load_scored_tickers()
    if scored_tickers is None:
        return None
    
    print(f"Found {len(scored_tickers)} tickers in {SCORES_FILE}")
    
    # Load US-listed tickers from stock_tickers_clean.json
    print(f"Loading US-listed tickers from {TICKER_FILE}...")
    us_tickers = load_us_tickers()
    if us_tickers is None:
        return None
    
    print(f"Found {len(us_tickers)} US-listed tickers in {TICKER_FILE}")
    
    # Load custom ticker definitions to exclude (OTC/private companies)
    print(f"Loading custom ticker definitions from {TICKER_DEFINITIONS_FILE}...")
    excluded_tickers = load_custom_ticker_definitions()
    print(f"Found {len(excluded_tickers)} tickers in {TICKER_DEFINITIONS_FILE} (will exclude these)")
    
    # Find intersection - tickers in both files, excluding custom definitions
    tickers_to_scrape = []
    excluded_count = 0
    for ticker in scored_tickers:
        if ticker in us_tickers:
            # Exclude if in custom ticker definitions (OTC/private)
            if ticker in excluded_tickers:
                excluded_count += 1
                continue
            name, exchange = us_tickers[ticker]
            tickers_to_scrape.append((ticker, name, exchange))
    
    if excluded_count > 0:
        print(f"Excluded {excluded_count} ticker(s) from {TICKER_DEFINITIONS_FILE} (OTC/private)")
    print(f"Found {len(tickers_to_scrape)} tickers to scrape (after exclusions)")
    
    return tickers_to_scrape


def load_existing_short_interest():
    """
    Load existing short interest data if file exists.
    
    Returns:
        dict: Dictionary with existing short interest data
    """
    if os.path.exists(SHORT_INTEREST_FILE):
        try:
            with open(SHORT_INTEREST_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load existing {SHORT_INTEREST_FILE}: {e}")
            return {"tickers": {}, "last_updated": None, "total_scraped": 0}
    
    return {"tickers": {}, "last_updated": None, "total_scraped": 0}


def save_short_interest(data):
    """
    Save short interest data to JSON file.
    
    Args:
        data: Dictionary containing short interest data
    """
    try:
        data["last_updated"] = datetime.now().isoformat()
        with open(SHORT_INTEREST_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving {SHORT_INTEREST_FILE}: {e}")
        return False


def scrape_ticker_short_interest(ticker):
    """
    Scrape short float for a single ticker.
    Only extracts the "Short Float" metric from Finviz.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        dict: Short float data or None if error
    """
    ticker_upper = ticker.strip().upper()
    url = f"https://finviz.com/quote.ashx?t={ticker_upper}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        snapshot_table = soup.find('table', class_='snapshot-table2')
        
        if not snapshot_table:
            return None
        
        # Extract all data from table
        data = {}
        rows = snapshot_table.find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 2:
                for i in range(0, len(cells) - 1, 2):
                    label = cells[i].get_text(strip=True)
                    value = cells[i + 1].get_text(strip=True)
                    if label and value:
                        data[label] = value
        
        # Only extract "Short Float" metric
        short_float = None
        if 'Short Float' in data:
            short_float = data['Short Float']
        
        if short_float:
            return {
                'ticker': ticker_upper,
                'short_float': short_float,
                'scraped_at': datetime.now().isoformat()
            }
        else:
            # Return empty dict to indicate ticker was checked but no short float data found
            return {
                'ticker': ticker_upper,
                'short_float': None,
                'scraped_at': datetime.now().isoformat(),
                'note': 'No short float data available'
            }
        
    except requests.exceptions.RequestException as e:
        return None
    except Exception as e:
        return None


def main():
    """Main function to batch scrape short interest data."""
    print("=" * 80)
    print("Batch Short Interest Scraper")
    print("=" * 80)
    print("Scraping short interest for tickers in both scores.json and stock_tickers_clean.json")
    print("=" * 80)
    print()
    
    # Get tickers to scrape (intersection of scores.json and stock_tickers_clean.json)
    tickers = get_tickers_to_scrape()
    
    if not tickers:
        print("Error: Could not load tickers.")
        return
    
    if len(tickers) == 0:
        print("No tickers found in both files. Nothing to scrape.")
        return
    
    print()
    
    # Load existing data
    print(f"Loading existing data from {SHORT_INTEREST_FILE}...")
    short_interest_data = load_existing_short_interest()
    existing_tickers = set(short_interest_data.get("tickers", {}).keys())
    
    print(f"Already have data for {len(existing_tickers)} tickers")
    print()
    
    # Filter out already scraped tickers
    tickers_to_scrape = [(t, n, e) for t, n, e in tickers if t not in existing_tickers]
    
    if not tickers_to_scrape:
        print("All tickers have already been scraped!")
        print(f"Total tickers with data: {len(existing_tickers)}")
        return
    
    print(f"Need to scrape {len(tickers_to_scrape)} tickers")
    print(f"Estimated time: ~{len(tickers_to_scrape) * REQUEST_DELAY / 60:.1f} minutes")
    print()
    
    # Ask for confirmation
    response = input("Continue with scraping? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    print()
    print("Starting batch scraping...")
    print(f"Delay between requests: {REQUEST_DELAY} seconds")
    print("=" * 80)
    print()
    
    # Initialize counters
    success_count = 0
    error_count = 0
    no_data_count = 0
    start_time = time.time()
    
    # Scrape each ticker
    for i, (ticker, name, exchange) in enumerate(tickers_to_scrape, 1):
        print(f"[{i}/{len(tickers_to_scrape)}] Scraping {ticker} ({name})...", end=" ", flush=True)
        
        result = scrape_ticker_short_interest(ticker)
        
        if result:
            if result.get('short_float'):
                # Has short float data
                short_interest_data["tickers"][ticker] = {
                    'company_name': name,
                    'exchange': exchange,
                    'short_float': result['short_float'],
                    'scraped_at': result['scraped_at']
                }
                success_count += 1
                print(f"✓ Short Float: {result['short_float']}")
            else:
                # No short float data available
                short_interest_data["tickers"][ticker] = {
                    'company_name': name,
                    'exchange': exchange,
                    'short_float': None,
                    'scraped_at': result['scraped_at'],
                    'note': 'No short float data available'
                }
                no_data_count += 1
                print("✓ (no short float data)")
        else:
            error_count += 1
            print("✗ Error")
        
        # Save progress periodically
        if i % SAVE_INTERVAL == 0:
            short_interest_data["total_scraped"] = len(short_interest_data["tickers"])
            if save_short_interest(short_interest_data):
                print(f"  [Progress saved: {i}/{len(tickers_to_scrape)}]")
        
        # Rate limiting delay
        if i < len(tickers_to_scrape):  # Don't delay after last request
            time.sleep(REQUEST_DELAY)
    
    # Final save
    short_interest_data["total_scraped"] = len(short_interest_data["tickers"])
    save_short_interest(short_interest_data)
    
    # Display summary
    elapsed_time = time.time() - start_time
    print()
    print("=" * 80)
    print("Scraping Complete!")
    print("=" * 80)
    print(f"Total tickers processed: {len(tickers_to_scrape)}")
    print(f"  ✓ Success (with short float): {success_count}")
    print(f"  ✓ Success (no short float data): {no_data_count}")
    print(f"  ✗ Errors: {error_count}")
    print(f"Total time: {elapsed_time / 60:.1f} minutes")
    print(f"Data saved to: {SHORT_INTEREST_FILE}")
    print(f"Total tickers in file: {len(short_interest_data['tickers'])}")
    print("=" * 80)


if __name__ == "__main__":
    main()

