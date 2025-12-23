import json
import os
import sys
import time
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.db_manager import DBManager
import src.scoring.scorer as scorer
from src.clients.openrouter_client import SmartRateLimiter

# Define local paths
WEB_APP_DIR = os.path.dirname(os.path.abspath(__file__))
NEW_DB_PATH = os.path.join(WEB_APP_DIR, "top_500_scores.db")

def score_top_500(limit=None, workers=5, rpm=150):
    # 1. Initialize DB and redirect scorer
    print(f"Initializing database at {NEW_DB_PATH}...")
    new_db = DBManager(NEW_DB_PATH)
    scorer.db = new_db
    scorer.SCORES_DB = NEW_DB_PATH

    # 2. Load the companies from DB metadata table
    print("Loading companies from database metadata...")
    try:
        conn = sqlite3.connect(NEW_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM companies_metadata ORDER BY rank ASC")
        top_500 = [dict(row) for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        print(f"Error loading metadata from DB: {e}")
        return

    if not top_500:
        print("No companies found to score.")
        return
        
    if limit:
        top_500 = top_500[:limit]

    # 3. Ensure all tickers are in the lookup for scorer naming
    ticker_lookup = scorer.load_ticker_lookup()
    for company in top_500:
        ticker = company.get('ticker')
        name = company.get('name')
        if ticker and ticker != "UNKNOWN":
            ticker_lookup[ticker.upper()] = name

    # 4. Get existing scores to avoid duplicates
    existing_scores = new_db.get_all_scores()
    existing_tickers = set(existing_scores.keys())

    # 5. Initialize shared rate limiter
    rate_limiter = SmartRateLimiter(requests_per_minute=rpm)

    # 6. Score companies in parallel
    print(f"\nStarting scoring for {len(top_500)} companies with {workers} parallel workers...")
    if existing_tickers:
        print(f"Note: {len(existing_tickers)} companies already have scores and will be skipped.")
    print("=" * 80)
    
    start_time = time.time()
    success_count = 0
    fail_count = 0
    skip_count = 0
    
    def process_company(index, company):
        ticker = company.get('ticker')
        name = company.get('name')
        
        if not ticker or ticker == "UNKNOWN":
            return f"[{index}/{len(top_500)}] Skipping {name} - No valid ticker found.", False, False
            
        ticker_upper = ticker.upper()
        if ticker_upper in existing_tickers:
            return f"[{index}/{len(top_500)}] Skipping {ticker_upper} - Already scored.", False, True

        msg = f"[{index}/{len(top_500)}] Scoring {ticker_upper} ({name})..."
        try:
            # Pass the shared rate_limiter
            result = scorer.score_single_ticker(ticker_upper, silent=True, batch_mode=True, force_rescore=False, rate_limiter=rate_limiter)
            
            if result and result.get('success'):
                total_score = result.get('total', 0)
                return f"{msg}\n      Success! Total Score: {total_score:.2f}", True, False
            else:
                error = result.get('error', 'Unknown error') if result else "Failed to get result"
                return f"{msg}\n      FAILED: {error}", False, False
        except Exception as e:
            return f"{msg}\n      ERROR: {str(e)}", False, False

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_company, i, company): company for i, company in enumerate(top_500, 1)}
        
        for future in as_completed(futures):
            message, success, skipped = future.result()
            print(message)
            if success:
                success_count += 1
            elif skipped:
                skip_count += 1
            else:
                fail_count += 1
            
    end_time = time.time()
    duration = end_time - start_time
    
    print("\n" + "=" * 80)
    print(f"Scoring Complete!")
    print(f"Total Time: {duration/60:.2f} minutes")
    print(f"Successfully Scored: {success_count}")
    print(f"Skipped (Already Exist): {skip_count}")
    print(f"Failed: {fail_count}")
    print(f"Results saved to: {NEW_DB_PATH}")
    print("=" * 80)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of companies to score")
    parser.add_argument("--workers", type=int, default=5, help="Number of companies to score in parallel")
    parser.add_argument("--rpm", type=int, default=150, help="Maximum requests per minute for OpenRouter")
    args = parser.parse_args()
    
    score_top_500(limit=args.limit, workers=args.workers, rpm=args.rpm)

