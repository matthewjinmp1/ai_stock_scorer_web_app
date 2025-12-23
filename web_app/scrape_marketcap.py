import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time
import sqlite3

def scrape_top_companies(limit=500):
    base_url = "https://companiesmarketcap.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    companies = []
    page = 1
    
    while len(companies) < limit:
        url = base_url if page == 1 else f"{base_url}page/{page}/"
    print(f"Fetching data from {url}...")
        
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table', class_='default-table')
    if not table:
        table = soup.find('table')
        
    if not table:
            print(f"Could not find the companies table on page {page}.")
            break

    rows = table.find_all('tr')[1:]  # Skip header row
        if not rows:
            print(f"No more rows found on page {page}.")
            break

    for row in rows:
            if len(companies) >= limit:
            break
            
        cols = row.find_all('td')
        if len(cols) < 5:
            continue
            
        # Use the actual number of companies found as the rank
        rank = len(companies) + 1
        
        name_td = cols[2]
        name_div = name_td.find('div', class_='company-name')
        ticker_div = name_td.find('div', class_='company-code')
        
        if name_div and ticker_div:
            name = name_div.get_text(strip=True)
            ticker = ticker_div.get_text(strip=True)
        else:
            full_text = name_td.get_text(strip=True)
            match = re.search(r'^(.*?)([A-Z0-9\.-]{2,})$', full_text)
            if match:
                name = match.group(1).strip()
                ticker = match.group(2).strip()
                if ticker == "SR" and name.endswith("2222."):
                     name = name[:-5].strip()
                     ticker = "2222.SR"
            else:
                name = full_text
                ticker = "UNKNOWN"

        market_cap = cols[3].get_text(strip=True)
        price = cols[4].get_text(strip=True) if len(cols) > 4 else "N/A"
        
        country = "N/A"
        country_td = row.find('td', class_='responsive-hidden')
        if country_td:
            country_name_span = country_td.find('span', class_='country-name')
            if country_name_span:
                country = country_name_span.get_text(strip=True)
            else:
                country = country_td.get_text(strip=True)

        companies.append({
            "rank": rank,
            "name": name,
            "ticker": ticker,
            "market_cap": market_cap,
            "price": price,
            "country": country
        })

        print(f"Currently have {len(companies)} companies...")
        page += 1
        time.sleep(1) # Be polite

    # Save to DB
    db_path = os.path.join(os.path.dirname(__file__), "top_500_scores.db")
    print(f"Saving metadata to database at {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS companies_metadata (
                ticker TEXT PRIMARY KEY,
                rank INTEGER,
                name TEXT,
                market_cap TEXT,
                price TEXT,
                country TEXT
            )
        ''')
        
        # Insert data
        for c in companies:
            if c.get('ticker') and c.get('ticker') != "UNKNOWN":
                cursor.execute('''
                    INSERT OR REPLACE INTO companies_metadata (ticker, rank, name, market_cap, price, country)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    c['ticker'].upper(),
                    c['rank'],
                    c['name'],
                    c['market_cap'],
                    c['price'],
                    c['country']
                ))
        
        conn.commit()
        conn.close()
        print(f"Successfully saved metadata for {len(companies)} companies to DB.")
    except Exception as e:
        print(f"Error saving to DB: {e}")

    print(f"Successfully scraped {len(companies)} companies.")
    
    print(f"\nTop {len(companies)} Companies by Market Cap (Preview)")
    print("=" * 95)
    print(f"{'Rank':<5} {'Ticker':<12} {'Name':<40} {'Market Cap':<15} {'Price':<15}")
    print("-" * 95)
    for c in companies[:20]: # Show first 20 as preview
        rank = c.get('rank', 'N/A')
        ticker = c.get('ticker', 'N/A')
        name = c.get('name', 'N/A')
        market_cap = c.get('market_cap', 'N/A')
        price = c.get('price', 'N/A')
        
        display_name = (name[:37] + '...') if len(name) > 40 else name
        print(f"{rank:<5} {ticker:<12} {display_name:<40} {market_cap:<15} {price:<15}")
    print("...")
    print("-" * 95)
    print(f"Total companies listed: {len(companies)}")
    print("=" * 95)

if __name__ == "__main__":
    scrape_top_companies(500)
