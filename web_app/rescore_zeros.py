import json
import os
import sys
import time
import threading
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.db_manager import DBManager
import src.scoring.scorer as scorer
from src.clients.openrouter_client import SmartRateLimiter

# Define paths
WEB_APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(WEB_APP_DIR, "top_500_scores.db")
STRANGE_RESPONSES_PATH = os.path.join(WEB_APP_DIR, "strange_responses.json")

METRICS = [
    'moat_score', 'barriers_score', 'disruption_risk', 'switching_cost',
    'brand_strength', 'competition_intensity', 'network_effect',
    'product_differentiation', 'innovativeness_score', 'growth_opportunity',
    'riskiness_score', 'pricing_power', 'ambition_score',
    'bargaining_power_of_customers', 'bargaining_power_of_suppliers',
    'product_quality_score', 'culture_employee_satisfaction_score',
    'trailblazer_score', 'management_quality_score', 'ai_knowledge_score',
    'size_well_known_score', 'ethical_healthy_environmental_score',
    'long_term_orientation_score'
]

def rescore_nulls(workers=5, rpm=150):
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    # 1. Initialize DB and redirect scorer
    db = DBManager(DB_PATH)
    scorer.db = db
    scorer.SCORES_DB = DB_PATH
    
    # 2. Find all entries with NULL metrics
    print(f"Searching for NULL metrics in {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get latest entry for each ticker
    query = """
        SELECT s1.*
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
    """
    
    rows = cursor.execute(query).fetchall()
    conn.close()

    ticker_groups = {} # ticker -> { 'name': company_name, 'metrics': set() }
    total_nulls = 0
    
    for row in rows:
        ticker = row['ticker']
        company_name = row['company_name'] or ticker
        
        null_metrics = []
        for metric in METRICS:
            if row[metric] is None:
                null_metrics.append(metric)
        
        if null_metrics:
            ticker_groups[ticker] = {
                'name': company_name,
                'metrics': null_metrics
            }
            total_nulls += len(null_metrics)

    if not ticker_groups:
        print("No NULL metrics found in the database.")
        return

    targets = [] # List of (ticker, company_name, [metrics_to_rescore])
    for ticker, info in ticker_groups.items():
        targets.append((ticker, info['name'], info['metrics']))

    print(f"Found {total_nulls} NULL metrics across {len(targets)} companies.")
    
    # 3. Clear the strange responses file before starting
    # This ensures that after the run, the file only contains NEW strange responses
    if os.path.exists(STRANGE_RESPONSES_PATH):
        print(f"Clearing {STRANGE_RESPONSES_PATH} to capture only new strange responses...")
        try:
            with getattr(scorer, 'STRANGE_LOG_LOCK', threading.Lock()):
                with open(STRANGE_RESPONSES_PATH, 'w') as f:
                    json.dump([], f)
        except Exception as e:
            print(f"Warning: Could not clear strange responses file: {e}")

    print(f"Starting rescore with {workers} workers and {rpm} RPM limit...")
    print("=" * 80)

    rate_limiter = SmartRateLimiter(requests_per_minute=rpm)
    api_client = scorer.get_api_client(rate_limiter=rate_limiter)
    
    success_count = 0
    
    def process_target(ticker, company_name, metrics_to_fix):
        print(f"Rescoring {len(metrics_to_fix)} NULL metrics for {ticker} ({company_name})...")
        try:
            # We use query_all_scores_async directly to target only the specific metrics
            # This will trigger log_strange_response in scorer.py IF they fail again
            results, tokens, usage, model = scorer.query_all_scores_async(
                api_client, 
                company_name, 
                metrics_to_fix, 
                batch_mode=True, 
                silent=True, 
                ticker=ticker
            )
            
            # Get the current full record to update it
            current_full_data = db.get_score(ticker)
            if not current_full_data:
                # This shouldn't happen as we just pulled it from the DB
                return f"  [ERROR] {ticker}: Record disappeared from database.", False
            
            # Update the specific metrics we just got results for
            for m, val in results.items():
                current_full_data[m] = val
            
            # Recalculate total
            current_full_data['total_score'] = scorer.calculate_total_score(current_full_data)
            current_full_data['model'] = model
            
            # Save as a new version (history)
            db.save_score(ticker, current_full_data, company_name=company_name)
            return f"  [DONE] {ticker}: Fixed {len(metrics_to_fix)} metrics.", True
        except Exception as e:
            return f"  [ERROR] {ticker}: {str(e)}", False

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_target, t, name, m): t for t, name, m in targets}
        for future in as_completed(futures):
            msg, success = future.result()
            print(msg)
            if success:
                success_count += 1

    duration = time.time() - start_time
    print("=" * 80)
    print(f"Rescore Complete in {duration/60:.2f} minutes.")
    print(f"Successfully processed {success_count}/{len(targets)} companies.")
    
    # Check final state of strange responses
    if os.path.exists(STRANGE_RESPONSES_PATH):
        try:
            with getattr(scorer, 'STRANGE_LOG_LOCK', threading.Lock()):
                with open(STRANGE_RESPONSES_PATH, 'r') as f:
                    final_strange = json.load(f)
                    if final_strange:
                        print(f"⚠️  {len(final_strange)} strange responses were generated during NULL rescoring.")
                        print(f"Check {STRANGE_RESPONSES_PATH} for details.")
                    else:
                        print(f"✨ All NULL metrics were resolved successfully!")
        except Exception:
            pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--rpm", type=int, default=150)
    args = parser.parse_args()
    
    rescore_nulls(workers=args.workers, rpm=args.rpm)

