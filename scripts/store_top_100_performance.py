import sys
import os
import time
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.database import get_top_ranked_stocks
from src.core.price_fetcher import get_live_return
from src.core.settings import DB_DIR

# --- CONFIGURATION ---
MAX_WORKERS = 10
RETURNS_DB = os.path.join(DB_DIR, 'top_ranked_returns.db')
ANALYSIS_PERIOD_START = "2025-01-01"

def init_db():
    """Initialize the returns database."""
    os.makedirs(os.path.dirname(RETURNS_DB), exist_ok=True)
    conn = sqlite3.connect(RETURNS_DB)
    cursor = conn.cursor()
    # Create table if it doesn't exist (don't drop it anymore to preserve cache)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS top_ranked_returns (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            score REAL,
            rank INTEGER,
            start_price REAL,
            current_price REAL,
            return_pct REAL,
            period_start TEXT,
            last_updated TEXT
        )
    """)
    conn.commit()
    conn.close()

def store_returns(results):
    """Store the calculated returns in the database."""
    conn = sqlite3.connect(RETURNS_DB)
    cursor = conn.cursor()
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    data_to_insert = [
        (
            r['ticker'], 
            r['name'], 
            r.get('score', 0), 
            r.get('rank'),
            r['start_price'], 
            r['current_price'], 
            r['return'], 
            ANALYSIS_PERIOD_START,
            timestamp
        ) for r in results
    ]
    
    cursor.executemany("""
        INSERT OR REPLACE INTO top_ranked_returns 
        (ticker, company_name, score, rank, start_price, current_price, return_pct, period_start, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, data_to_insert)
    
    conn.commit()
    conn.close()

def get_cached_tickers():
    """Get a set of tickers that already have returns for the current period."""
    if not os.path.exists(RETURNS_DB):
        return set()
    conn = sqlite3.connect(RETURNS_DB)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ticker FROM top_ranked_returns WHERE period_start = ?", (ANALYSIS_PERIOD_START,))
        tickers = {row[0] for row in cursor.fetchall()}
        return tickers
    except sqlite3.Error:
        return set()
    finally:
        conn.close()

def main():
    print(f"Top 500 Performance Storer (By Size)")
    print(f"====================================")
    print(f"Period: {ANALYSIS_PERIOD_START} to Present")
    
    init_db()
    
    # Get already processed tickers
    cached_tickers = get_cached_tickers()
    if cached_tickers:
        print(f"Found {len(cached_tickers)} tickers already in cache.")
    
    # Fetch top 500 ranked stocks
    print(f"Fetching top 500 stocks by size from database...")
    top_stocks = get_top_ranked_stocks(500)
    
    # Filter out cached stocks
    top_stocks = [s for s in top_stocks if s['ticker'] not in cached_tickers]
    
    if not top_stocks:
        print("All stocks are already cached. Nothing to fetch.")
        return

    print(f"Calculating returns for {len(top_stocks)} new stocks using {MAX_WORKERS} threads...")
    
    results = []
    completed = 0
    total = len(top_stocks)
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_stock = {executor.submit(get_live_return, stock, ANALYSIS_PERIOD_START): stock for stock in top_stocks}
        
        for future in as_completed(future_to_stock):
            stock = future_to_stock[future]
            completed += 1
            print(f"Progress: {completed}/{total} stocks processed...", end="\r")
            
            try:
                result = future.result()
                if result and 'return' in result:
                    results.append(result)
            except Exception as e:
                print(f"\nError processing {stock['ticker']}: {e}")

    print("\n" + "=" * 30)
    if results:
        print(f"Successfully calculated returns for {len(results)} stocks.")
        print(f"Storing results in {RETURNS_DB}...")
        store_returns(results)
        
        avg_return = sum(r['return'] for r in results) / len(results)
        print(f"Average Return: {avg_return:.2f}%")
        print(f"Done. Process took {time.time() - start_time:.2f} seconds.")
    else:
        print("Failed to fetch any returns.")

if __name__ == "__main__":
    main()
