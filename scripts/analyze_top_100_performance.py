import sys
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.database import get_top_scored_stocks
from src.core.price_fetcher import get_live_return

# --- CONFIGURATION ---
MAX_WORKERS = 8 

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
            except Exception:
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
