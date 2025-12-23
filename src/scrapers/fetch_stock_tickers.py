#!/usr/bin/env python3
"""
Fetch all NYSE and NASDAQ stock tickers with company names
Downloads from NASDAQ's public FTP server and saves to JSON
"""

import requests
import csv
import json
from datetime import datetime

# NASDAQ FTP URLs (now accessible via HTTP)
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

def fetch_nasdaq_listed():
    """Fetch NASDAQ-listed stocks."""
    print("Fetching NASDAQ-listed stocks...")
    response = requests.get(NASDAQ_URL)
    response.raise_for_status()
    
    lines = response.text.strip().split('\n')
    reader = csv.DictReader(lines, delimiter='|')
    
    companies = []
    for row in reader:
        # Filter out test issues and ETFs, focus on regular stocks
        test_issue = row.get('Test Issue', '').strip()
        security_name = row.get('Security Name', '').strip()
        
        # Skip test issues and ETFs
        if test_issue == 'N' and 'ETF' not in security_name.upper():
            ticker = row.get('Symbol', '').strip()
            if ticker:
                companies.append({
                    'ticker': ticker,
                    'name': security_name,
                    'exchange': 'NASDAQ'
                })
    
    print(f"  Found {len(companies)} NASDAQ stocks")
    return companies

def fetch_other_listed():
    """Fetch NYSE and other exchange-listed stocks."""
    print("Fetching NYSE and other exchange stocks...")
    response = requests.get(OTHER_URL)
    response.raise_for_status()
    
    lines = response.text.strip().split('\n')
    reader = csv.DictReader(lines, delimiter='|')
    
    companies = []
    exchange_map = {
        'A': 'NYSE MKT',
        'N': 'NYSE',
        'P': 'NYSE ARCA',
        'Q': 'NASDAQ',
        'Z': 'BATS',
        'V': 'IEXG'
    }
    
    for row in reader:
        # Filter out test issues and ETFs
        test_issue = row.get('Test Issue', '').strip()
        security_name = row.get('Security Name', '').strip()
        
        # Skip test issues and ETFs
        if test_issue == 'N' and 'ETF' not in security_name.upper():
            exchange_code = row.get('Exchange', '').strip()
            exchange = exchange_map.get(exchange_code, 'UNKNOWN')
            
            # Try different possible column names for ticker
            ticker = row.get('NASDAQ Symbol', '').strip()
            if not ticker:
                ticker = row.get('Symbol', '').strip()
            
            if ticker:
                companies.append({
                    'ticker': ticker,
                    'name': security_name,
                    'exchange': exchange
                })
    
    print(f"  Found {len(companies)} NYSE and other stocks")
    return companies

def save_to_json(all_companies, filename='data/stock_tickers.json'):
    """Save companies to JSON file."""
    output = {
        'last_updated': datetime.now().isoformat(),
        'total_count': len(all_companies),
        'companies': sorted(all_companies, key=lambda x: x['ticker'])
    }
    
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nSaved {len(all_companies)} tickers to {filename}")
    print(f"Last updated: {output['last_updated']}")

def main():
    """Main function to fetch and save stock tickers."""
    print("=" * 60)
    print("Fetching NYSE and NASDAQ Stock Tickers")
    print("=" * 60)
    
    try:
        # Fetch NASDAQ stocks
        nasdaq_stocks = fetch_nasdaq_listed()
        
        # Fetch NYSE and other exchange stocks
        other_stocks = fetch_other_listed()
        
        # Combine and remove duplicates by ticker
        all_stocks = nasdaq_stocks + other_stocks
        
        # Remove duplicates keeping the first occurrence
        seen_tickers = set()
        unique_stocks = []
        for stock in all_stocks:
            if stock['ticker'] not in seen_tickers:
                unique_stocks.append(stock)
                seen_tickers.add(stock['ticker'])
        
        print(f"\nTotal unique tickers: {len(unique_stocks)}")
        
        # Save to JSON
        save_to_json(unique_stocks)
        
        # Print some statistics
        print("\n" + "=" * 60)
        print("Statistics by Exchange:")
        exchange_counts = {}
        for stock in unique_stocks:
            ex = stock['exchange']
            exchange_counts[ex] = exchange_counts.get(ex, 0) + 1
        
        for exchange, count in sorted(exchange_counts.items()):
            print(f"  {exchange}: {count}")
        
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
