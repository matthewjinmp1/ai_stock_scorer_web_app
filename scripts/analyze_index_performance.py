import sys
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the project root to sys.path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.database import get_top_100_weighted_data
from src.core.price_fetcher import get_live_return

# --- CONFIGURATION ---
MAX_WORKERS = 10 

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
    
    if max_score == min_score:
        mapped_weights = [1.0] * len(results)
    else:
        mapped_weights = [0.5 + (r['score'] - min_score) * 1.5 / (max_score - min_score) for r in results]
            
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

    # Top Contributors
    print(f"\nTOP 5 CONTRIBUTORS TO WEIGHTED RETURN")
    print(f"{'Ticker':<10} {'Name':<25} {'Weight':<8} {'Return':<10} {'Contrib.':<10}")
    print(f"{'-'*68}")
    
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
