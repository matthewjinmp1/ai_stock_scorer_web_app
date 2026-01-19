import os
import sys
import time
import sqlite3
import json
import threading
from concurrent.futures import ThreadPoolExecutor

# Add project root and old_stuff to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, 'old_stuff'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'old_stuff', 'src'))

try:
    from src.scoring.scorer import get_api_client, calculate_token_cost
    from src.clients.openrouter_client import SmartRateLimiter
except ImportError:
    get_api_client = None
    calculate_token_cost = None
    SmartRateLimiter = None

# Configuration
MIMO_MODEL = "xiaomi/mimo-v2-flash:free"
TOP_COMPANIES_DB = os.path.join(REPO_ROOT, 'web_app', 'top_companies.db')
SCORES_DB = os.path.join(REPO_ROOT, 'web_app', 'top_scores.db')
CACHE_DB = os.path.join(REPO_ROOT, "web_app", "ai_relevance_scores.db")
RESULTS_FILE = os.path.join(SCRIPT_DIR, "scored_relevance_results.json")

# Stats tracking
TOTAL_STATS = {
    'prompt_tokens': 0,
    'completion_tokens': 0,
    'thinking_tokens': 0,
    'total_tokens': 0,
    'count': 0,
    'cache_hits': 0
}
STATS_LOCK = threading.Lock()
PRINT_LOCK = threading.Lock()
DB_LOCK = threading.Lock()

def initialize_cache():
    """Create the cache table if it doesn't exist."""
    with DB_LOCK:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS relevance_scores (
                ticker TEXT PRIMARY KEY,
                score INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

def get_cached_score(ticker):
    """Retrieve a score from the cache."""
    with DB_LOCK:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT score FROM relevance_scores WHERE ticker = ?", (ticker,))
        row = cursor.fetchone()
        conn.close()
        return row

def save_to_cache(ticker, score):
    """Save a score to the cache."""
    with DB_LOCK:
        conn = sqlite3.connect(CACHE_DB)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO relevance_scores (ticker, score)
            VALUES (?, ?)
        ''', (ticker, score))
        conn.commit()
        conn.close()

def load_top_companies(n):
    """Load the top N companies from top_companies.db."""
    if not os.path.exists(TOP_COMPANIES_DB):
        print(f"Error: {TOP_COMPANIES_DB} not found.")
        return []
    
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT ticker, name, rank
        FROM companies_metadata
        ORDER BY rank
        LIMIT ?
    ''', (n,))
    
    companies = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return companies

def score_single_company(company, client):
    """Ask MIMO to score a single company's AI relevance, checking cache first."""
    ticker = company['ticker']
    name = company['name']
    
    # Check cache first
    cached = get_cached_score(ticker)
    if cached:
        score = cached[0]
        with STATS_LOCK:
            TOTAL_STATS['cache_hits'] += 1
            TOTAL_STATS['count'] += 1
        with PRINT_LOCK:
            print(f"⚡ #{company['rank']:<4d} {ticker:7s}: {score}/100 (from cache)")
        return {
            'ticker': ticker,
            'name': name,
            'score': score,
            'rank': company['rank']
        }

    prompt = f"""
    Analyze the company {name} (Ticker: {ticker}) and provide a score from 0 to 100 on how relevant they are to the AI revolution.
    
    Consider:
    1. How much they benefit from AI growth.
    2. Their direct involvement in AI development or hardware.
    3. Their implementation of AI to improve their core business.
    4. Their competitive position in the AI landscape.
    
    Return ONLY a JSON object with:
    {{
        "score": <integer 0-100>
    }}
    """
    
    max_retries = 5
    retry_delay = 5  # seconds
    
    for attempt in range(max_retries):
        start_time = time.time()
        try:
            response_text, token_usage = client.chat_completion_with_tokens(
                [{"role": "user", "content": prompt}],
                model=MIMO_MODEL,
                temperature=0.1
            )
            duration = time.time() - start_time
            
            if not response_text:
                return None
                
            content = response_text.strip()
            if content.startswith('```json'):
                content = content[7:-3].strip()
            elif content.startswith('```'):
                content = content[3:-3].strip()
                
            data = json.loads(content)
            score = data.get('score', 0)
            
            # Save to cache
            save_to_cache(ticker, score)
            
            # Track stats
            if token_usage:
                with STATS_LOCK:
                    TOTAL_STATS['prompt_tokens'] += token_usage.get('prompt_tokens', 0)
                    TOTAL_STATS['completion_tokens'] += token_usage.get('completion_tokens', 0)
                    TOTAL_STATS['thinking_tokens'] += token_usage.get('thinking_tokens', 0)
                    TOTAL_STATS['total_tokens'] += token_usage.get('total_tokens', 0)
                    TOTAL_STATS['count'] += 1
                    
            with PRINT_LOCK:
                print(f"✓ #{company['rank']:<4d} {ticker:7s}: {score}/100 ({duration:.2f}s)")
                
            return {
                'ticker': ticker,
                'name': name,
                'score': score,
                'rank': company['rank']
            }
            
        except Exception as e:
            error_msg = str(e)
            if "Rate limit exceeded" in error_msg and attempt < max_retries - 1:
                wait_time = retry_delay * (attempt + 1)
                with PRINT_LOCK:
                    print(f"⏳ #{company['rank']:<4d} Rate limit for {ticker}. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            
            with PRINT_LOCK:
                print(f"✗ #{company['rank']:<4d} Error scoring {ticker}: {e}")
            return None
    return None

def main():
    if not get_api_client:
        print("Error: Could not import get_api_client. Check project structure.")
        return

    initialize_cache()

    print("=" * 60)
    print("TOP X AI RELEVANCE BATCH SCORER")
    print("=" * 60)
    
    try:
        x = int(input("How many top companies to score? "))
    except ValueError:
        print("Please enter a valid number.")
        return

    companies = load_top_companies(x)
    if not companies:
        print("No companies found.")
        return

    print(f"\nScoring top {len(companies)} companies using MIMO...")
    print("This will process in parallel (max 10 threads).")
    print("-" * 60)

    rate_limiter = SmartRateLimiter(requests_per_minute=150)
    client = get_api_client(rate_limiter=rate_limiter)
    
    results = []
    start_total_time = time.time()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(score_single_company, c, client) for c in companies]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)

    # Sort results by score (highest first)
    results.sort(key=lambda x: x['score'], reverse=True)
    
    total_duration = time.time() - start_total_time

    # Save to file
    with open(RESULTS_FILE, 'w') as f:
        json.dump(results, f, indent=4)

    print("\n" + "=" * 80)
    print("FINAL AI RELEVANCE RANKING")
    print("=" * 80)
    print(f"{'#':3s} | {'Ticker':10s} | {'Score':9s} | {'Company Name'}")
    print("-" * 80)
    for i, res in enumerate(results, 1):
        print(f"{i:3d} | {res['ticker']:10s} | {res['score']:3d}/100    | {res['name']}")
    
    print("\n" + "=" * 80)
    print("EXECUTION SUMMARY")
    print("=" * 80)
    print(f"Total Companies Scored: {TOTAL_STATS['count']}")
    print(f"Cache Hits:            {TOTAL_STATS['cache_hits']}")
    print(f"Total Execution Time:   {total_duration:.2f}s")
    
    if TOTAL_STATS['total_tokens'] > 0:
        cost_usd = calculate_token_cost(TOTAL_STATS['total_tokens'], model=MIMO_MODEL, token_usage=TOTAL_STATS)
        print(f"Total Cost:             {cost_usd*100:.4f}¢")
    
    print(f"\nResults saved to: {RESULTS_FILE}")
    print("=" * 80)

if __name__ == "__main__":
    main()
