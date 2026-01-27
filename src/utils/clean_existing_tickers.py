#!/usr/bin/env python3
"""
Clean existing stock_tickers.json by removing share class descriptors
"""

import json
import re

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
    
    # Clean up extra whitespace and trailing commas/dashes
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r',$', '', cleaned)
    cleaned = cleaned.strip(' . -')
    
    # If we accidentally removed everything, return original
    if not cleaned or len(cleaned) < 2:
        return name
    
    return cleaned

def main():
    print("=" * 60)
    print("Cleaning Stock Ticker Names")
    print("=" * 60)
    
    # Load existing tickers
    try:
        with open('data/stock_tickers.json', 'r') as f:
            data = json.load(f)
        
        print(f"\nLoaded {len(data['companies'])} tickers")
        
        # Clean each company name
        cleaned_count = 0
        for company in data['companies']:
            original = company['name']
            cleaned = clean_company_name(original)
            
            if original != cleaned:
                cleaned_count += 1
            company['name'] = cleaned
        
        print(f"Cleaned {cleaned_count} company names")
        
        # Update metadata
        data['last_updated'] = data.get('last_updated', '')
        data['description'] = 'Clean company names without share class descriptors'
        
        # Save to new file
        output_filename = 'data/stock_tickers_clean.json'
        with open(output_filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\nSaved to {output_filename}")
        
        # Show statistics
        print("\n" + "=" * 60)
        print("Statistics by Exchange:")
        exchange_counts = {}
        for stock in data['companies']:
            ex = stock['exchange']
            exchange_counts[ex] = exchange_counts.get(ex, 0) + 1
        
        for exchange, count in sorted(exchange_counts.items()):
            print(f"  {exchange}: {count}")
        
        # Show samples
        print("\n" + "=" * 60)
        print("Sample Before/After Cleaning:")
        print("=" * 60)
        
        # Re-load original for comparison
        with open('data/stock_tickers.json', 'r') as f:
            original_data = json.load(f)
        
        sample_count = 0
        for i, company in enumerate(data['companies'][:20]):
            original_name = original_data['companies'][i]['name']
            if original_name != company['name']:
                print(f"\n  {company['ticker']}:")
                print(f"    Before: {original_name}")
                print(f"    After:  {company['name']}")
                sample_count += 1
                if sample_count >= 10:
                    break
        
    except FileNotFoundError:
        print("Error: data/stock_tickers.json not found. Please run fetch_stock_tickers.py first.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
