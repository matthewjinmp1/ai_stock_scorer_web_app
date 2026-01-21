import requests
import json
import sys
import os
from datetime import datetime

def fetch_vic_reports(ticker):
    """
    Fetches investment ideas from Value Investors Club using the search autocomplete API.
    """
    url = "https://www.valueinvestorsclub.com/search"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
    }
    
    # The API expects a 'query' and an optional 'tab'
    data = {
        'query': ticker,
        'tab': ''
    }
    
    try:
        print(f"Searching VIC for: {ticker}...")
        response = requests.post(url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        
        # The API returns a JSON object with a 'result' list
        resp_json = response.json()
        if not resp_json.get('success'):
            print(f"API Error: {resp_json.get('message', 'Unknown error')}")
            return []
            
        results = resp_json.get('result', [])
        ideas = []
        
        for item in results:
            # item fields: idea_id, comp, symbol, link, add_date, l, d
            # l=1 seems to be Long (BUY), l=0 seems to be Short (SHORT)
            
            # Clean up company name
            company = item.get('comp', '').strip()
            symbol = item.get('symbol', '').strip()
            title = f"{company} ({symbol})" if symbol else company
            
            # Position type
            pos_type = "BUY/LONG"
            if item.get('l') == 0:
                pos_type = "SHORT"
                
            ideas.append({
                'title': title,
                'type': pos_type,
                'date': item.get('add_date', 'Unknown'),
                'url': f"https://www.valueinvestorsclub.com{item.get('link', '')}",
                'raw_date': item.get('add_date', '')
            })
            
        # Deduplicate and sort by date descending
        def sort_key(x):
            date_str = x['raw_date']
            if not date_str:
                return datetime.min
            try:
                # Format is M/D/YYYY
                return datetime.strptime(date_str, "%m/%d/%Y")
            except:
                return datetime.min
                
        ideas.sort(key=sort_key, reverse=True)
        return ideas

    except Exception as e:
        print(f"Error fetching data: {e}")
        # Fallback to HTML parsing could be implemented here if needed
        return []

def main():
    if len(sys.argv) < 2:
        ticker = input("Enter stock ticker: ").strip().upper()
    else:
        ticker = sys.argv[1].upper()
    
    if not ticker:
        print("No ticker provided.")
        return

    results = fetch_vic_reports(ticker)
    
    if not results:
        print(f"\nNo official 'Ideas & Companies' found on Value Investors Club for {ticker}.")
        print("Note: Try searching for the full company name if the ticker doesn't return results.")
        return

    print(f"\nFound {len(results)} official reports for {ticker}:")
    print("-" * 80)
    print(f"{'Date':<12} {'Position':<10} {'Company (Ticker)'}")
    print("-" * 80)
    
    for r in results:
        print(f"{r['date']:<12} {r['type']:<10} {r['title']}")
    
    print("-" * 80)
    print("Full reports usually require a VIC membership.")

if __name__ == "__main__":
    main()
