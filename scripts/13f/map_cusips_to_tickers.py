#!/usr/bin/env python3
"""
Map CUSIPs to Tickers using the OpenFIGI API.
Processes CUSIPs in batches of 100.
"""

import os
import sqlite3
import time
import requests
import json
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

def load_dotenv():
    """Simple helper to load .env file from project root."""
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    dotenv_path = os.path.join(project_root, ".env")
    
    if os.path.exists(dotenv_path):
        with open(dotenv_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Handle cases where multiple vars might be on one line due to bad formatting
                if '="' in line and '"OPENFIGI' in line:
                    # Very specific fix for the user's previous corrupted .env
                    parts = line.split('"')
                    for p in parts:
                        if "OPENFIGI_API_KEY=" in p:
                            k, v = p.split("=", 1)
                            os.environ[k.strip()] = v.strip()
                elif "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
        return True
    return False

# Load environment variables before setting API_KEY
if load_dotenv():
    print("✓ Loaded .env file.")
else:
    print("⚠ Could not find .env file.")

# OpenFIGI API details
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
# Priority: Argument > Environment Variable
API_KEY = os.environ.get("OPENFIGI_API_KEY")

def calculate_cusip_check_digit(cusip8: str) -> str:
# ... (rest of the function remains same)
    """Calculate the 9th digit of a CUSIP."""
    if len(cusip8) != 8:
        return ""
    
    total = 0
    for i, char in enumerate(cusip8):
        if char.isdigit():
            val = int(char)
        elif char.isalpha():
            # A=10, B=11, ...
            val = ord(char.upper()) - ord('A') + 10
        elif char == '*':
            val = 36
        elif char == '@':
            val = 37
        elif char == '#':
            val = 38
        else:
            return ""
            
        if i % 2 != 0:
            val *= 2
            
        total += (val // 10) + (val % 10)
        
    return str((10 - (total % 10)) % 10)

def get_unique_cusips_to_map(portfolio_db: str, tickers_db: str) -> List[Tuple[str, str]]:
    """Get unique CUSIPs from portfolio_db that are not in tickers_db."""
    conn_p = sqlite3.connect(portfolio_db)
    cursor_p = conn_p.cursor()
    
    # Get unique CUSIPs and metadata, ordered by total value in the RECENT quarters
    # We filter out non-stock items at the source row level.
    cursor_p.execute("""
        SELECT cusip, MAX(name_of_issuer), MAX(title_of_class), MAX(ssh_prnamt_type), MAX(put_call),
               SUM(CASE WHEN report_date >= '2024-01-01' THEN CAST(REPLACE(REPLACE(REPLACE(value, ',', ''), '$', ''), ' ', '') AS FLOAT) ELSE 0 END) as recent_val
        FROM holdings 
        WHERE cusip IS NOT NULL AND cusip != '' 
          AND (put_call IS NULL OR put_call = '' OR put_call = ' ')
          AND (ssh_prnamt_type IS NULL OR ssh_prnamt_type != 'PRN')
        GROUP BY cusip
        HAVING recent_val > 0
        ORDER BY recent_val DESC
    """)
    raw_data = cursor_p.fetchall()
    conn_p.close()
    
    # Get already mapped CUSIPs
    conn_t = sqlite3.connect(tickers_db)
    cursor_t = conn_t.cursor()
    cursor_t.execute("SELECT cusip FROM tickers")
    mapped_cusips = {row[0] for row in cursor_t.fetchall()}
    conn_t.close()
    
    to_map = []
    seen = set()
    skipped_non_stock = 0
    
    for row in raw_data:
        c, name, title, amt_type, put_call, total_val = row
        if not c: continue
        c_orig = c.strip().upper()
        
        # 1. Filter out options (redundant now due to SQL but safe)
        if put_call and put_call.strip():
            skipped_non_stock += 1
            continue
            
        # 2. Filter out debt (PRN = Principal Amount)
        if amt_type and amt_type.strip().upper() == 'PRN':
            skipped_non_stock += 1
            continue
            
        # 3. Filter by title of class keywords
        if title:
            title_upper = title.upper()
            non_stock_keywords = ['BOND', 'NOTE', 'DEBT', 'PUT', 'CALL', 'WTS', 'WARRANT']
            if any(k in title_upper for k in non_stock_keywords):
                skipped_non_stock += 1
                continue

        # 4. Filter out CUSIPs with invalid characters (dashes, etc.)
        if not c_orig.isalnum():
            skipped_non_stock += 1
            continue

        # 5. Smart Normalization for Lookup
        # We keep the ORIGINAL CUSIP for the database, but clean it for the API lookup
        c_lookup = c_orig
        
        # If it's not exactly 9 digits, try to fix it
        if len(c_orig) != 9:
            stripped = c_orig.lstrip('0')
            if len(stripped) == 8: # Likely missing a leading zero or check digit
                c_lookup = stripped.zfill(8)
                check_digit = calculate_cusip_check_digit(c_lookup)
                if check_digit:
                    c_lookup = c_lookup + check_digit
            elif len(stripped) < 8:
                c_lookup = stripped.zfill(8)
                check_digit = calculate_cusip_check_digit(c_lookup)
                if check_digit:
                    c_lookup = c_lookup + check_digit
        
        # Final safety check: OpenFIGI REQUIRES 9 characters for ID_CUSIP
        if len(c_lookup) != 9:
            skipped_non_stock += 1
            continue

        if c_orig not in mapped_cusips and c_orig not in seen:
            to_map.append((c_orig, name, c_lookup, total_val))
            seen.add(c_orig)
            
    print(f"Total unique CUSIPs in portfolio: {len(raw_data)}")
    print(f"Skipped non-stock items (options, bonds, etc.): {skipped_non_stock}")
    print(f"Already mapped in tickers.db: {len(mapped_cusips)}")
    print(f"New CUSIPs to process: {len(to_map)}")
    
    if to_map:
        print(f"Sample of new CUSIPs (High Value First):")
        for orig, name, lookup, val in to_map[:10]:
            print(f"  {orig} ({name}) -> {lookup} | Val: ${val:,.0f}")
    
    return to_map

def map_cusips_to_tickers(batch_data: List[Tuple[str, str, str]]) -> List[Dict]:
    """Map a batch of CUSIPs to tickers using OpenFIGI."""
    headers = {'Content-Type': 'application/json'}
    if API_KEY:
        headers['X-OPENFIGI-APIKEY'] = API_KEY

    # We prepare two jobs for each identifier if it starts with a letter (CINS)
    # OpenFIGI returns results in the same order as jobs.
    jobs = []
    job_map = [] # Track which result index belongs to which original CUSIP
    
    for i, item in enumerate(batch_data):
        orig_cusip, name, lookup_val, _ = item
        if lookup_val[0].isalpha():
            # Letter-based CUSIPs are often CINS
            jobs.append({"idType": "ID_CINS", "idValue": lookup_val})
            job_map.append(i)
        else:
            jobs.append({"idType": "ID_CUSIP", "idValue": lookup_val})
            job_map.append(i)
    
    results = []
    try:
        response = requests.post(OPENFIGI_URL, headers=headers, json=jobs, timeout=30)
        if response.status_code == 200:
            data = response.json()
            for i, result in enumerate(data):
                orig_index = job_map[i]
                orig_sec_cusip = batch_data[orig_index][0]
                
                if 'data' in result and result['data']:
                    # Filter for US exchanges first
                    us_matches = [e for e in result['data'] if e.get('exchCode') in ['US', 'UW', 'UN', 'UA', 'UP']]
                    pool = us_matches if us_matches else result['data']
                    
                    best_match = None
                    for entry in pool:
                        if entry.get('securityType2') in ['Common Stock', 'ADR']:
                            best_match = entry
                            break
                    
                    if not best_match:
                        best_match = pool[0]
                        
                    ticker = best_match.get('ticker')
                    if ticker:
                        clean_ticker = ticker.split()[0]
                        # Special handling for Flutter (PPB -> FLUT)
                        if clean_ticker == 'PPB' and 'FLUTTER' in best_match.get('name', '').upper():
                            clean_ticker = 'FLUT'
                            
                        results.append({
                            "cusip": orig_sec_cusip,
                            "ticker": clean_ticker,
                            "company_name": best_match.get("name")
                        })
        elif response.status_code == 429:
            print("Rate limit hit. Waiting 60s...")
            time.sleep(60)
    except Exception as e:
        print(f"Request failed: {e}")
    
    return results

def save_to_tickers_db(db_path: str, results: List[Dict]):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    all_updates = []
    for r in results:
        # Save the original SEC version
        all_updates.append((r['cusip'], r['ticker'], r['company_name']))
        
        # Also save an 8-character version if the original is 9
        if len(r['cusip']) == 9:
            all_updates.append((r['cusip'][:8], r['ticker'], r['company_name']))
            
    cursor.executemany("""
        INSERT OR REPLACE INTO tickers (cusip, ticker, company_name)
        VALUES (?, ?, ?)
    """, all_updates)
    
    conn.commit()
    conn.close()
    return len(results)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of CUSIPs to process")
    parser.add_argument("--key", type=str, help="OpenFIGI API Key")
    parser.add_argument("--workers", type=int, default=5, help="Number of parallel workers (default: 5)")
    args = parser.parse_args()

    global API_KEY
    # Check env again after load_dotenv
    if not API_KEY:
        API_KEY = os.environ.get("OPENFIGI_API_KEY")
        
    if args.key:
        API_KEY = args.key

    script_dir = os.path.dirname(os.path.abspath(__file__))
    portfolio_db = os.path.join(script_dir, "data", "portfolio_history.db")
    tickers_db = os.path.join(script_dir, "data", "tickers.db")
    
    if not os.path.exists(portfolio_db):
        print(f"Portfolio database not found at {portfolio_db}")
        return

    # Ensure tickers.db exists
    conn = sqlite3.connect(tickers_db)
    conn.execute("CREATE TABLE IF NOT EXISTS tickers (cusip TEXT, ticker TEXT, company_name TEXT)")
    conn.close()

    to_map = get_unique_cusips_to_map(portfolio_db, tickers_db)
    if not to_map:
        print("All CUSIPs already mapped.")
        return

    if args.limit:
        to_map = to_map[:args.limit]
        print(f"Limiting to first {args.limit} CUSIPs.")

    batch_size = 100 if API_KEY else 10
    total_updated = 0
    # Higher rate limits with key: 250 req/min vs 25 req/min
    delay = 0.2 if API_KEY else 2.5
    
    cusips_only = [item[0] for item in to_map]
    batches = [to_map[i:i + batch_size] for i in range(0, len(to_map), batch_size)]
    
    print(f"Processing {len(to_map)} CUSIPs in {len(batches)} batches using {args.workers} workers...")
    if API_KEY:
        print("Using API Key: Rate limits increased (Batch size: 100).")
    else:
        print("No API Key: Using slow mode (Batch size: 10).")

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_batch = {executor.submit(map_cusips_to_tickers, batch): i for i, batch in enumerate(batches)}
        
        for future in as_completed(future_to_batch):
            batch_idx = future_to_batch[future]
            try:
                results = future.result()
                if results:
                    updated = save_to_tickers_db(tickers_db, results)
                    total_updated += updated
                    print(f"  ✓ Batch {batch_idx+1}/{len(batches)}: Added {len(results)} tickers.")
                else:
                    print(f"  ⚠ Batch {batch_idx+1}/{len(batches)}: No matches found.")
                
                # Small delay to respect rate limits even with parallel workers
                if not API_KEY:
                    time.sleep(delay)
            except Exception as e:
                print(f"  ✗ Batch {batch_idx+1} failed: {e}")

    print(f"\nFinished. Total unique CUSIPs added to tickers.db: {total_updated}")

if __name__ == "__main__":
    main()
