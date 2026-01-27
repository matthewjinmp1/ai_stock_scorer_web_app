#!/usr/bin/env python3
"""
Finviz Short Interest Scraper
Scrapes Finviz.com for short interest information for a given ticker symbol.
Uses GOOGL as an example.
"""

import requests
from bs4 import BeautifulSoup
import time
import sys

# User agent to avoid being blocked
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def get_finviz_quote_url(ticker):
    """
    Get the Finviz quote URL for a ticker.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'GOOGL')
        
    Returns:
        str: URL to the Finviz quote page
    """
    ticker_upper = ticker.strip().upper()
    return f"https://finviz.com/quote.ashx?t={ticker_upper}"


def scrape_short_interest(ticker):
    """
    Scrape short interest information from Finviz for a given ticker.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'GOOGL')
        
    Returns:
        dict: Dictionary containing short interest data, or None if error
    """
    ticker_upper = ticker.strip().upper()
    url = get_finviz_quote_url(ticker_upper)
    
    print(f"Fetching data for {ticker_upper} from Finviz...")
    print(f"URL: {url}")
    
    try:
        # Make request with headers to avoid being blocked
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the snapshot table (contains fundamental data)
        # Finviz displays data in a table with class 'snapshot-table2'
        snapshot_table = soup.find('table', class_='snapshot-table2')
        
        if not snapshot_table:
            print(f"Error: Could not find data table for {ticker_upper}")
            return None
        
        # Extract all table rows
        rows = snapshot_table.find_all('tr')
        
        # Dictionary to store all found data
        data = {}
        
        # Parse table rows - Finviz uses a 2-column format
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 2:
                # Process pairs of cells (label, value)
                for i in range(0, len(cells) - 1, 2):
                    label = cells[i].get_text(strip=True)
                    value = cells[i + 1].get_text(strip=True)
                    
                    if label and value:
                        data[label] = value
        
        # Look for short interest related fields
        short_interest_data = {}
        
        # Common short interest field names on Finviz
        short_interest_fields = [
            'Short Interest',
            'Short Float',
            'Short Ratio',
            'Short Interest / Float',
            'Short % of Float',
            'Short % of Shares Outstanding'
        ]
        
        for field in short_interest_fields:
            if field in data:
                short_interest_data[field] = data[field]
        
        # Also store all data for reference
        short_interest_data['_all_data'] = data
        
        return {
            'ticker': ticker_upper,
            'url': url,
            'short_interest': short_interest_data,
            'all_data': data
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None
    except Exception as e:
        print(f"Error parsing data: {e}")
        return None


def display_short_interest(result):
    """
    Display short interest information in a formatted way.
    
    Args:
        result: Dictionary returned from scrape_short_interest()
    """
    if not result:
        print("No data to display.")
        return
    
    ticker = result['ticker']
    short_interest = result['short_interest']
    all_data = result['all_data']
    
    print("\n" + "=" * 80)
    print(f"Short Interest Data for {ticker}")
    print("=" * 80)
    
    # Display short interest specific fields
    if len(short_interest) > 1:  # More than just _all_data
        print("\nShort Interest Information:")
        print("-" * 80)
        for field, value in short_interest.items():
            if field != '_all_data':
                print(f"  {field:<40} {value}")
    else:
        print("\nNo specific short interest fields found.")
        print("Searching all data for short-related fields...")
        print("-" * 80)
        
        # Search for any field containing "short" (case-insensitive)
        found_short_fields = False
        for field, value in all_data.items():
            if 'short' in field.lower():
                print(f"  {field:<40} {value}")
                found_short_fields = True
        
        if not found_short_fields:
            print("  No short interest related fields found in the data.")
    
    # Optionally display all available data
    print("\n" + "-" * 80)
    print("All Available Data Fields:")
    print("-" * 80)
    for field, value in sorted(all_data.items()):
        print(f"  {field:<40} {value}")
    
    print("\n" + "=" * 80)


def main():
    """Main function to scrape short interest data."""
    print("=" * 80)
    print("Finviz Short Interest Scraper")
    print("=" * 80)
    print()
    
    # Default to GOOGL as example, but allow command line argument
    if len(sys.argv) > 1:
        ticker = sys.argv[1]
    else:
        ticker = "GOOGL"
        print(f"Using GOOGL as example (you can pass a ticker as argument: python {sys.argv[0]} TICKER)")
        print()
    
    # Scrape the data
    result = scrape_short_interest(ticker)
    
    if result:
        display_short_interest(result)
    else:
        print(f"\nFailed to scrape short interest data for {ticker}")
        print("\nPossible reasons:")
        print("  - Ticker symbol not found on Finviz")
        print("  - Network connection issue")
        print("  - Finviz website structure may have changed")
        print("  - Rate limiting or blocking (try again later)")
        sys.exit(1)
    
    # Be respectful - add a small delay
    print("\nNote: Please be respectful of Finviz's servers.")
    print("      Add delays between requests if scraping multiple tickers.")


if __name__ == "__main__":
    main()

