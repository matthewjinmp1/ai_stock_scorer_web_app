#!/usr/bin/env python3
"""
Fetch clean stock tickers with company names
Uses SEC data for clean company names and NASDAQ FTP for exchange info
"""

import requests
import csv
import json
import re
from datetime import datetime

# Data sources
SEC_URL = "https://www.sec.gov/files/company_tickers.json"
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

def clean_company_name(name):
    """Remove share class descriptors and extra info from company names."""
    if not name:
        return name
    
    # Common patterns to remove
    patterns_to_remove = [
        r'\s+Common\s+Stock.*$',
        r'\s+Class\s+[A-Z1-9]\s+Common\s+Stock.*$',
        r'\s+American\s+Depositary\s+Shares.*$',
        r'\s+Depositary\s+Shares.*$',
        r'\s+\(.*Depositary.*Shares.*\)$',
        r'\s+Class\s+[A-Z1-9].*$',
        r'\s+Series\s+[A-Z1-9].*$',
        r'\s+Preference\s+Shares.*$',
        r'\s+Preferred\s+Stock.*$',
        r'\s+each\s+representing.*$',
        r'\s+Unit[s]?$',
        r'\s+Warrant[s]?$',
        r'\s+Right[s]?$',
        r'\s+Ordinary\s+Share[s]?$',
        r'\s+Red[e]?eemable\s+Securities.*$',
        r'\s+Convertible\s+Note[s]?$',
        r'\s+PIPEs?.*$',
        r'\s+SPAC.*$',
    ]
    
    cleaned = name
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up extra whitespace and trailing commas
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r',$', '', cleaned)
    cleaned = cleaned.strip(' .')
    
    # If we accidentally removed everything, return original
    if not cleaned or len(cleaned) < 2:
        return name
    
    return cleaned

def fetch_sec_companies():
    """Fetch company data from SEC with proper headers."""
    print("Fetching SEC company data...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
    }
    
    try:
        response = requests.get(SEC_URL, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        sec_companies = {}
        
        # SEC data is stored as a dict with numeric keys
        for item in data.values():
            ticker = item.get('ticker', '').strip()
            name = item.get('title', '').strip()
            
            if ticker and name:
                sec_companies[ticker] = name
        
        print(f"  Found {len(sec_companies)} companies from SEC")
        return sec_companies
    except Exception as e:
        print(f"  Could not fetch SEC data: {e}")
        return {}

def fetch_nasdaq_locations():
    """Fetch which exchange each ticker is on."""
    print("Fetching exchange information...")
    
    all_locations = {}
    
    # NASDAQ listed
    try:
        response = requests.get(NASDAQ_URL)
        response.raise_for_status()
        lines = response.text.strip().split('\n')
        reader = csv.DictReader(lines, delimiter='|')
        
        for row in reader:
            ticker = row.get('Symbol', '').strip()
            security_name = row.get('Security Name', '').strip()
            
            if ticker and row.get('Test Issue', '').strip() == 'N':
                # Use SEC data for clean name if available, otherwise this one
                all_locations[ticker] = {
                    'exchange': 'NASDAQ',
                    'name': security_name
                }
        
        print(f"  Found {len([k for k in all_locations.keys() if all_locations[k]['exchange'] == 'NASDAQ'])} NASDAQ tickers")
    except Exception as e:
        print(f"  Error fetching NASDAQ: {e}")
    
    # Other exchanges (NYSE, etc.)
    try:
        response = requests.get(OTHER_URL)
        response.raise_for_status()
        lines = response.text.strip().split('\n')
        reader = csv.DictReader(lines, delimiter='|')
        
        exchange_map = {
            'A': 'NYSE MKT',
            'N': 'NYSE',
            'P': 'NYSE ARCA',
            'Z': 'BATS',
            'V': 'IEXG'
        }
        
        for row in reader:
            ticker = row.get('NASDAQ Symbol', '').strip() or row.get('Symbol', '').strip()
            security_name = row.get('Security Name', '').strip()
            exchange_code = row.get('Exchange', '').strip()
            
            if ticker and row.get('Test Issue', '').strip() == 'N':
                exchange = exchange_map.get(exchange_code, exchange_code)
                all_locations[ticker] = {
                    'exchange': exchange,
                    'name': security_name
                }
        
        print(f"  Found {len([k for k in all_locations.keys() if all_locations[k]['exchange'] != 'NASDAQ'])} other exchange tickers")
    except Exception as e:
        print(f"  Error fetching other exchanges: {e}")
    
    return all_locations

def combine_data():
    """Combine SEC clean names with exchange data."""
    print("\n" + "=" * 60)
    print("Fetching and Cleaning Stock Tickers")
    print("=" * 60)
    
    # Fetch both data sources
    sec_companies = fetch_sec_companies()
    all_locations = fetch_nasdaq_locations()
    
    print("\nMerging data sources...")
    
    # Combine data
    companies = []
    tickers_found = set()
    
    # Start with exchange data (more comprehensive)
    for ticker, info in all_locations.items():
        if ticker in tickers_found:
            continue
        
        exchange = info['exchange']
        
        # Try to get clean name from SEC first
        clean_name = sec_companies.get(ticker, info['name'])
        
        # Clean the name
        cleaned_name = clean_company_name(clean_name)
        
        companies.append({
            'ticker': ticker,
            'name': cleaned_name,
            'exchange': exchange
        })
        
        tickers_found.add(ticker)
    
    # Add any SEC companies not in location data (use original name as fallback)
    for ticker, name in sec_companies.items():
        if ticker not in tickers_found:
            companies.append({
                'ticker': ticker,
                'name': clean_company_name(name),
                'exchange': 'UNKNOWN'
            })
    
    return sorted(companies, key=lambda x: x['ticker'])

def save_to_json(companies, filename='data/stock_tickers_clean.json'):
    """Save companies to JSON file."""
    output = {
        'last_updated': datetime.now().isoformat(),
        'total_count': len(companies),
        'companies': companies
    }
    
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nSaved {len(companies)} tickers to {filename}")
    print(f"Last updated: {output['last_updated']}")
    
    # Print statistics
    print("\n" + "=" * 60)
    print("Statistics by Exchange:")
    exchange_counts = {}
    for stock in companies:
        ex = stock['exchange']
        exchange_counts[ex] = exchange_counts.get(ex, 0) + 1
    
    for exchange, count in sorted(exchange_counts.items()):
        print(f"  {exchange}: {count}")
    
    print("\n" + "=" * 60)
    print("Sample of cleaned names:")
    print("=" * 60)
    for i, stock in enumerate(companies[:10]):
        print(f"  {stock['ticker']:6} - {stock['name']} ({stock['exchange']})")

def main():
    """Main function."""
    try:
        companies = combine_data()
        save_to_json(companies)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
