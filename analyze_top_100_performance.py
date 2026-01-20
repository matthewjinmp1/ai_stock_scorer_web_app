import json
import sqlite3
import os
import sys
import time
from datetime import datetime
import yfinance as yf
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
DB_PATH = 'web_app/top_scores.db'
MAX_WORKERS = 8  # Balanced for speed vs rate-limiting

def get_top_scored_stocks(limit=10):
    """Fetch top scored stocks from the local database."""
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return []
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ticker, company_name, total_score FROM scores ORDER BY total_score DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [{'ticker': r[0], 'name': r[1], 'score': r[2]} for r in rows]
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []
    finally:
        conn.close()

def fetch_yahoo_direct(ticker, start_date):
    """Fallback method using direct requests to Yahoo Finance API if yfinance fails."""
    try:
        # Convert date to timestamp
        start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
        end_ts = int(datetime.now().timestamp())
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start_ts}&period2={end_ts}&interval=1d"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        chart = data.get('chart', {}).get('result', [{}])[0]
        indicators = chart.get('indicators', {}).get('quote', [{}])[0]
        closes = indicators.get('close', [])
        
        # Filter out None values
        valid_closes = [c for c in closes if c is not None]
        
        if not valid_closes:
            return None, None, None
            
        start_price = valid_closes[0]
        end_price = valid_closes[-1]
        total_return = ((end_price / start_price) - 1) * 100
        
        return start_price, end_price, total_return
    except Exception:
        return None, None, None

def get_live_return(stock):
    """Fetch price at 2025-01-01 and current price for a stock dictionary."""
    ticker = stock['ticker']
    # Method 1: yfinance with custom session and suppressed errors
    try:
        yf_ticker = ticker
        if ticker == 'GOOG': yf_ticker = 'GOOGL'
        
        # Create a session with a browser-like user agent
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Suppress stderr per-thread
        with open(os.devnull, 'w') as fnull:
            old_stderr = sys.stderr
            sys.stderr = fnull
            try:
                data = yf.download(yf_ticker, start="2025-01-01", session=session, progress=False)
            finally:
                sys.stderr = old_stderr
        
        if not data.empty:
            start_price = float(data.iloc[0]['Close'])
            end_price = float(data.iloc[-1]['Close'])
            total_return = ((end_price / start_price) - 1) * 100
            stock.update({'start_price': start_price, 'current_price': end_price, 'return': total_return})
            return stock
    except Exception:
        pass
        
    # Method 2: Direct Yahoo Query
    start_p, end_p, ret = fetch_yahoo_direct(ticker, "2025-01-01")
    if ret is not None:
        stock.update({'start_price': start_p, 'current_price': end_p, 'return': ret})
        return stock
    
    return None

def run_analysis():
    try:
        user_input = input("Enter the number of top stocks to analyze (default 10): ").strip()
        num_to_analyze = int(user_input) if user_input else 10
    except ValueError:
        print("Invalid input. Using default of 10.")
        num_to_analyze = 10

    print(f"\nAI Stock Scorer: Automated Threaded Analysis")
    print(f"==============================================")
    print(f"Current Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"Analysis Period: 2025-01-01 to Present")
    print(f"Analyzing top {num_to_analyze} stocks using {MAX_WORKERS} threads...\n")

    top_stocks = get_top_scored_stocks(num_to_analyze)
    
    results = []
    missing = []
    completed = 0
    total = len(top_stocks)

    if total == 0:
        print("No stocks found in database.")
        return

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_stock = {executor.submit(get_live_return, stock): stock for stock in top_stocks}
        
        for future in as_completed(future_to_stock):
            stock = future_to_stock[future]
            completed += 1
            print(f"Progress: {completed}/{total} stocks processed...", end="\r")
            sys.stdout.flush()
            
            try:
                result = future.result()
                if result:
                    results.append(result)
                else:
                    missing.append(stock['ticker'])
            except Exception as e:
                missing.append(stock['ticker'])

    duration = time.time() - start_time
    print(" " * 60, end="\r") # Clear line
    print(f"Finished in {duration:.2f} seconds.\n")

    if not results:
        print("No automated data could be fetched for the top stocks. Please check network connectivity.")
        return

    results.sort(key=lambda x: x['return'], reverse=True)
    
    avg_return = sum(r['return'] for r in results) / len(results)
    pos_count = sum(1 for r in results if r['return'] > 0)

    print(f"SUMMARY STATISTICS (Top {num_to_analyze})")
    print(f"---------------------------")
    print(f"Stocks Analyzed:      {len(results)} / {num_to_analyze}")
    print(f"Average Total Return: {avg_return:.2f}%")
    print(f"Positive Returns:     {pos_count} ({pos_count/len(results)*100:.1f}%)")
    
    print(f"\nRANKED PERFORMERS (JAN 1 2025 - PRESENT)")
    print(f"{'Ticker':<10} {'Jan 1 Price':<12} {'Current':<12} {'Return':<10}")
    print(f"{'-'*50}")
    for r in results:
        print(f"{r['ticker']:<10} ${r['start_price']:<11.2f} ${r['current_price']:<11.2f} {r['return']:>8.1f}%")

    if missing:
        print(f"\nMissing Data for {len(missing)} Tickers (Private/Intl):")
        print(", ".join(missing))

if __name__ == "__main__":
    run_analysis()
