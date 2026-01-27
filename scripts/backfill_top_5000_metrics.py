import os
import sys
import sqlite3
import json
import time
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import importlib.util

# 1. Setup paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

# Add project root to sys.path
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.config import TOP_SCORES_DB, TOP_COMPANIES_DB
from src.scoring.scorer import (
    SCORE_DEFINITIONS, SCORE_WEIGHTS, calculate_total_score,
    get_api_client, load_ticker_lookup, query_all_scores_async
)
from src.utils.db_manager import DBManager
LIMIT = 5000
MAX_WORKERS = 20
DB_LOCK = threading.Lock()
# The 4 metrics we want to ensure are filled (including the missing Execution Ability)
NEW_METRICS = ['customer_obsession', 'adaptability_score', 'capital_allocation_score', 'execution_ability_score']

def get_top_ranked_stocks_local(limit=5000):
    """Local implementation of get_top_ranked_stocks to avoid import issues."""
    if not os.path.exists(TOP_COMPANIES_DB):
        return []
    
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    cursor = conn.cursor()
    try:
        # We don't need to attach the scores DB here, we just need the list of stocks to check
        query = """
            SELECT ticker, name, rank
            FROM companies_metadata
            ORDER BY rank ASC 
            LIMIT ?
        """
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        return [{'ticker': r[0], 'name': r[1], 'rank': r[2]} for r in rows]
    except Exception as e:
        print(f"Error fetching top stocks: {e}")
        return []
    finally:
        conn.close()

def get_latest_scores():
    if not os.path.exists(TOP_SCORES_DB): return {}
    conn = sqlite3.connect(TOP_SCORES_DB)
    # Don't use Row factory here, just get plain tuples and convert ourselves
    cursor = conn.cursor()
    
    # Get column names
    cursor.execute("PRAGMA table_info(scores)")
    columns = [col[1] for col in cursor.fetchall()]
    
    query = """
        SELECT s1.* FROM scores s1
        JOIN (SELECT ticker, MAX(timestamp) as max_ts FROM scores GROUP BY ticker) s2 
        ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    results = {}
    for row in rows:
        # Create a dict from the row tuple
        row_dict = {}
        for i, col_name in enumerate(columns):
            if i < len(row):
                row_dict[col_name] = row[i]
        
        ticker_val = row_dict.get('ticker')
        if ticker_val:
            results[ticker_val.upper()] = row_dict
            
    conn.close()
    return results

def process_company(ticker, company_name, existing_scores, db_manager):
    try:
        ticker_upper = ticker.upper()
        client = get_api_client()
        scores_to_save = {}
        metrics_needed = []
        is_new = False

        # Get the existing scores for this ticker (ensure we use uppercase key)
        current = existing_scores.get(ticker_upper)

        if current:
            # Check for missing metrics
            for m in NEW_METRICS:
                val = current.get(m)
                if val is None or val == 'N/A' or val == '':
                    metrics_needed.append(m)
            
            if not metrics_needed:
                return f"SKIP: {ticker_upper} already has all metrics."
            
            # Start with existing scores
            scores_to_save = current.copy()
            # Clean out the internal fields
            for field in ['id', 'timestamp']:
                if field in scores_to_save: scores_to_save.pop(field, None)
        else:
            # New company, need all metrics
            metrics_needed = list(SCORE_DEFINITIONS.keys())
            is_new = True
            scores_to_save = {'ticker': ticker_upper, 'company_name': company_name}

        # Fetch missing metrics
        new_results, tokens, usage, model = query_all_scores_async(
            client, company_name, metrics_needed, 
            batch_mode=True, silent=True, ticker=ticker_upper
        )
        
        if not new_results: return f"FAIL: {ticker_upper} - No scores."

        # Update and calculate total
        scores_to_save.update(new_results)
        scores_to_save['model'] = model
        scores_to_save['total_score'] = calculate_total_score(scores_to_save)
        
        with DB_LOCK:
            db_manager.save_score(ticker_upper, scores_to_save, company_name=company_name)
            
        action = "FULL SCORE" if is_new else f"FILLED {len(metrics_needed)}"
        return f"SUCCESS: {ticker_upper} - {action} (Model: {model})"
    except Exception as e:
        import traceback
        # traceback.print_exc() # Uncomment for deep debugging
        return f"ERROR: {ticker} - {str(e)}"

def main():
    print(f"Starting Backfill for Top {LIMIT} Stocks...")
    print(f"Scores DB: {TOP_SCORES_DB}")
    print(f"Companies DB: {TOP_COMPANIES_DB}")
    
    top_stocks = get_top_ranked_stocks_local(limit=LIMIT)
    if not top_stocks:
        print("No stocks found in companies database.")
        return
        
    existing_scores = get_latest_scores()
    db_manager = DBManager(TOP_SCORES_DB)

    to_process = []
    for stock in top_stocks:
        ticker = stock['ticker'].upper()
        current = existing_scores.get(ticker)
        
        if current:
            needs_fill = False
            for m in NEW_METRICS:
                val = current.get(m)
                if val is None or val == 'N/A' or val == '':
                    needs_fill = True
                    break
            if needs_fill: to_process.append(stock)
        else:
            to_process.append(stock)

    print(f"Total stocks to check: {len(top_stocks)}")
    print(f"Existing scored stocks: {len(existing_scores)}")
    print(f"Need to process (New or Missing Metrics): {len(to_process)}")
    
    if not to_process:
        print("Everything is up to date!")
        return

    start_time = time.time()
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_company, s['ticker'], s['name'], existing_scores, db_manager): s for s in to_process}
        for future in as_completed(futures):
            completed += 1
            print(f"[{completed}/{len(to_process)}] {future.result()}")

    print(f"\nFinished in {time.time() - start_time:.2f}s.")

if __name__ == "__main__":
    main()
