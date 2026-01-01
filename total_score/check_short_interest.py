#!/usr/bin/env python3
"""
Interactive tool to check short interest for a single ticker from Finviz.
"""

import requests
from bs4 import BeautifulSoup
import re

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
    
    Returns a dictionary with short interest data or error message.
    """
    url = f"{FINVIZ_BASE_URL}{ticker.upper()}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return {
            'ticker': ticker.upper(),
            'error': f"Request error: {str(e)}"
        }
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the snapshot table (contains most financial metrics)
    snapshot_table = soup.find('table', class_='snapshot-table2')
    if not snapshot_table:
        return {
            'ticker': ticker.upper(),
            'error': "Could not find snapshot table on Finviz page"
        }
    
    # Parse the table - Finviz uses a grid layout with alternating label/value cells
    data = {'ticker': ticker.upper()}
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

def main():
    """Main interactive loop."""
    print("=" * 80)
    print("SHORT INTEREST CHECKER")
    print("=" * 80)
    print("Enter a ticker symbol to check its short interest (as % of float)")
    print("Type 'quit' or 'exit' to stop")
    print("-" * 80)
    print()
    
    while True:
        ticker = input("Enter ticker: ").strip().upper()
        
        if not ticker:
            continue
        
        if ticker in ['QUIT', 'EXIT', 'Q']:
            print("Goodbye!")
            break
        
        print(f"\nFetching short interest data for {ticker}...")
        
        data = scrape_finviz_short_interest(ticker)
        
        if data.get('error'):
            print(f"✗ Error: {data['error']}")
        elif data.get('short_interest_percent') is not None:
            print(f"✓ Short Interest: {data['short_interest_percent']:.2f}% of float")
        else:
            print(f"✗ No short interest data found for {ticker}")
            print("  This may mean:")
            print("  - The ticker doesn't exist on Finviz")
            print("  - Short interest data is not available for this stock")
            print("  - The page structure may have changed")
        
        print()
        print("-" * 80)
        print()

if __name__ == "__main__":
    main()

