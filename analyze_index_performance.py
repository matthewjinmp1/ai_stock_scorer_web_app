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
TOP_COMPANIES_DB = 'web_app/top_companies.db'
TOP_SCORES_DB = 'web_app/top_scores.db'
MAX_WORKERS = 10  # Slightly higher for 100 stocks

def get_top_100_weighted_data():
    """Join top_companies and top_scores to get tickers and their AI weights."""
    if not os.path.exists(TOP_COMPANIES_DB) or not os.path.exists(TOP_SCORES_DB):
        print("Error: Databases not found.")
        return []
    
    # We use a temporary connection to join across two database files
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    cursor = conn.cursor()
    try:
        cursor.execute(f"ATTACH DATABASE '{TOP_SCORES_DB}' AS scores_db")
        
        # Join companies_metadata with scores to get the top 100 by rank and their scores
        query = """
            SELECT 
                c.ticker, 
                c.name, 
                s.total_score 
            FROM companies_metadata c
            JOIN scores_db.scores s ON c.ticker = s.ticker
            WHERE c.rank <= 100
            ORDER BY c.rank ASC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        return [{'ticker': r[0], 'name': r[1], 'score': r[2]} for r in rows]
    except sqlite3.Error as e:
        print(f"Database error during join: {e}")
        return []
    finally:
        conn.close()

def fetch_yahoo_direct(ticker, start_date):
    """Fallback method using direct requests to Yahoo Finance API if yfinance fails."""
    try:
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
        
        valid_closes = [c for c in closes if c is not None]
        if not valid_closes:
            return None, None, None
            
        return valid_closes[0], valid_closes[-1], ((valid_closes[-1] / valid_closes[0]) - 1) * 100
    except Exception:
        return None, None, None

def get_live_return(stock):
    """Fetch price at 2025-01-01 and current price."""
    ticker = stock['ticker']
    try:
        yf_ticker = ticker
        if ticker == 'GOOG': yf_ticker = 'GOOGL'
        
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
        
    start_p, end_p, ret = fetch_yahoo_direct(ticker, "2025-01-01")
    if ret is not None:
        stock.update({'start_price': start_p, 'current_price': end_p, 'return': ret})
        return stock
    
    return None

def run_analysis():
    print(f"\nAI Stock Scorer: Index Performance Comparison (Top 100)")
    print(f"=======================================================")
    print(f"Current Date: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"Analysis Period: 2025-01-01 to Present\n")

    # 1. Data Retrieval
    print("Retrieving top 100 stocks and weights from databases...")
    stocks_data = get_top_100_weighted_data()
    if not stocks_data:
        print("No stock data found.")
        return

    # 2. Price Fetching
    print(f"Fetching live price data using {MAX_WORKERS} threads...")
    results = []
    missing = []
    completed = 0
    total = len(stocks_data)
    
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_stock = {executor.submit(get_live_return, stock): stock for stock in stocks_data}
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
            except Exception:
                missing.append(stock['ticker'])

    duration = time.time() - start_time
    print(" " * 60, end="\r") 
    print(f"Price fetching finished in {duration:.2f} seconds.\n")

    if not results:
        print("Error: Could not fetch returns for any stocks.")
        return

    # 3. Index Calculation
    print(f"Calculating index returns for {len(results)} stocks...")
    
    # Scale-Weighted Index (0.5x to 2.0x based on score)
    scores = [r['score'] for r in results]
    min_score = min(scores)
    max_score = max(scores)
    
    # If all scores are the same, weighting becomes equal weighting
    if max_score == min_score:
        mapped_weights = [1.0] * len(results)
    else:
        # Map scores to 0.5 - 2.0 range
        mapped_weights = []
        for r in results:
            # Linear mapping: f(x) = 0.5 + (x - min) * (2.0 - 0.5) / (max - min)
            mapped_val = 0.5 + (r['score'] - min_score) * (1.5) / (max_score - min_score)
            mapped_weights.append(mapped_val)
            
    total_weight_sum = sum(mapped_weights)
    weighted_return = 0
    for i, r in enumerate(results):
        normalized_weight = mapped_weights[i] / total_weight_sum
        weighted_return += r['return'] * normalized_weight
        r['weight'] = normalized_weight

    # Equal-Weighted Index
    equal_return = sum(r['return'] for r in results) / len(results)

    # 4. Reporting
    print(f"\nINDEX PERFORMANCE SUMMARY")
    print(f"-------------------------")
    print(f"Stocks Included:         {len(results)} / 100")
    print(f"AI Score-Weighted Index: {weighted_return:>8.2f}%")
    print(f"Equal-Weighted Index:    {equal_return:>8.2f}%")
    
    diff = weighted_return - equal_return
    print(f"Difference (Alpha):      {diff:>8.2f}% ({'OUTPERFORMED' if diff > 0 else 'UNDERPERFORMED'})")

    # Top Contributors to the Score-Weighted Index
    print(f"\nTOP 5 CONTRIBUTORS TO WEIGHTED RETURN")
    print(f"{'Ticker':<10} {'Name':<25} {'Weight':<8} {'Return':<10} {'Contrib.':<10}")
    print(f"{'-'*68}")
    
    # Sort by absolute contribution (weight * return)
    for r in results:
        r['contribution'] = r['weight'] * r['return']
    
    results.sort(key=lambda x: x['contribution'], reverse=True)
    for r in results[:5]:
        print(f"{r['ticker']:<10} {r['name'][:24]:<25} {r['weight']*100:>6.2f}% {r['return']:>8.1f}% {r['contribution']:>8.2f}%")

    print(f"\nBOTTOM 5 CONTRIBUTORS TO WEIGHTED RETURN")
    print(f"{'Ticker':<10} {'Name':<25} {'Weight':<8} {'Return':<10} {'Contrib.':<10}")
    print(f"{'-'*68}")
    for r in results[-5:][::-1]:
        print(f"{r['ticker']:<10} {r['name'][:24]:<25} {r['weight']*100:>6.2f}% {r['return']:>8.1f}% {r['contribution']:>8.2f}%")

    if missing:
        print(f"\nMissing Data for {len(missing)} Tickers:")
        print(", ".join(missing[:20]) + ("..." if len(missing) > 20 else ""))

    # Print all stock weights and returns
    print(f"\nFULL STOCK LIST (Sorted by AI Weight)")
    print(f"{'Ticker':<10} {'Name':<25} {'Weight':<8} {'Return':<10}")
    print(f"{'-'*55}")
    results.sort(key=lambda x: x['weight'], reverse=True)
    total_weight_check = 0
    for r in results:
        print(f"{r['ticker']:<10} {r['name'][:24]:<25} {r['weight']*100:>6.2f}% {r['return']:>8.1f}%")
        total_weight_check += r['weight']
    
    print(f"{'-'*55}")
    print(f"{'TOTAL':<36} {total_weight_check*100:>6.2f}%")

if __name__ == "__main__":
    run_analysis()
