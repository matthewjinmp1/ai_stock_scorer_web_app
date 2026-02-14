"""
Calculate the average return for the top X stocks from the Innovative Disruptor
(Disruptive Innovators) ranking. Uses trait_scores_confidence5_billion.json for
the ranking and fetches returns from the same period as store_top_100_performance.
Stores and caches results in top_ranked_returns.db (table: top_disruptor_returns).

Usage: python avg_return_top100_disruptors.py [X]
  X = number of top disruptors to include (default: 100)
"""
import sys
import os
import json
import sqlite3
import time
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.price_fetcher import get_live_return
from src.core.settings import TRAIT_SCORES_JSON, DB_DIR

ANALYSIS_PERIOD_START = "2025-01-01"
MAX_WORKERS = 10
TOP_N = 100
RETURNS_DB = os.path.join(DB_DIR, "top_ranked_returns.db")
TABLE_NAME = "top_disruptor_returns"
BENCHMARK_TABLE = "benchmark_returns"
SPY_TICKER = "SPY"


def _last_updated_timestamp():
    """Timestamp for when the returns were last computed."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    """Ensure the disruptor returns and benchmark tables exist."""
    os.makedirs(os.path.dirname(RETURNS_DB), exist_ok=True)
    conn = sqlite3.connect(RETURNS_DB)
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
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
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {BENCHMARK_TABLE} (
            ticker TEXT,
            period_start TEXT,
            return_pct REAL,
            last_updated TEXT,
            PRIMARY KEY (ticker, period_start)
        )
    """)
    conn.commit()
    conn.close()


def get_cached_spy_return(use_only_today=True):
    """Return cached SPY return for current period, or None if missing/stale."""
    if not os.path.exists(RETURNS_DB):
        return None
    conn = sqlite3.connect(RETURNS_DB)
    cursor = conn.cursor()
    try:
        if use_only_today:
            cursor.execute(
                f"""
                SELECT return_pct FROM {BENCHMARK_TABLE}
                WHERE ticker = ? AND period_start = ? AND date(last_updated) = date('now', 'localtime')
                """,
                (SPY_TICKER, ANALYSIS_PERIOD_START),
            )
        else:
            cursor.execute(
                f"""
                SELECT return_pct FROM {BENCHMARK_TABLE}
                WHERE ticker = ? AND period_start = ?
                """,
                (SPY_TICKER, ANALYSIS_PERIOD_START),
            )
        row = cursor.fetchone()
        return float(row[0]) if row is not None else None
    except (sqlite3.Error, TypeError, ValueError):
        return None
    finally:
        conn.close()


def store_spy_return(return_pct):
    """Cache SPY return for the current period."""
    conn = sqlite3.connect(RETURNS_DB)
    cursor = conn.cursor()
    cursor.execute(
        f"""
        INSERT OR REPLACE INTO {BENCHMARK_TABLE} (ticker, period_start, return_pct, last_updated)
        VALUES (?, ?, ?, ?)
        """,
        (SPY_TICKER, ANALYSIS_PERIOD_START, return_pct, _last_updated_timestamp()),
    )
    conn.commit()
    conn.close()


def get_cached_returns(use_only_today=True):
    """
    Return dict ticker -> {name, score, rank, start_price, current_price, return, last_updated}
    for rows with period_start = ANALYSIS_PERIOD_START.
    If use_only_today, only include rows where last_updated is from today (same-day cache).
    """
    if not os.path.exists(RETURNS_DB):
        return {}
    conn = sqlite3.connect(RETURNS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        if use_only_today:
            # SQLite: date(last_updated) = date('now', 'localtime')
            cursor.execute(
                f"""
                SELECT ticker, company_name, score, rank, start_price, current_price, return_pct, last_updated
                FROM {TABLE_NAME}
                WHERE period_start = ? AND date(last_updated) = date('now', 'localtime')
                """,
                (ANALYSIS_PERIOD_START,),
            )
        else:
            cursor.execute(
                f"""
                SELECT ticker, company_name, score, rank, start_price, current_price, return_pct, last_updated
                FROM {TABLE_NAME}
                WHERE period_start = ?
                """,
                (ANALYSIS_PERIOD_START,),
            )
        rows = cursor.fetchall()
        out = {}
        for r in rows:
            out[r["ticker"]] = {
                "ticker": r["ticker"],
                "name": r["company_name"],
                "score": r["score"],
                "rank": r["rank"],
                "start_price": r["start_price"],
                "current_price": r["current_price"],
                "return": r["return_pct"],
                "last_updated": r["last_updated"],
            }
        return out
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def store_returns(results):
    """Persist disruptor returns to the cache table."""
    if not results:
        return
    conn = sqlite3.connect(RETURNS_DB)
    cursor = conn.cursor()
    timestamp = _last_updated_timestamp()
    data = [
        (
            r["ticker"],
            r["name"],
            r.get("score"),
            r.get("rank"),
            r["start_price"],
            r["current_price"],
            r["return"],
            ANALYSIS_PERIOD_START,
            timestamp,
        )
        for r in results
    ]
    cursor.executemany(
        f"""
        INSERT OR REPLACE INTO {TABLE_NAME}
        (ticker, company_name, score, rank, start_price, current_price, return_pct, period_start, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        data,
    )
    conn.commit()
    conn.close()


def load_top_disruptors(n=TOP_N):
    """Load top N companies by trait score from the Disruptive Innovators ranking JSON."""
    if not os.path.exists(TRAIT_SCORES_JSON):
        return []
    with open(TRAIT_SCORES_JSON, "r") as f:
        data = json.load(f)
    scores = data.get("scores") or []
    with_scores = [
        (r.get("trait_score"), r)
        for r in scores
        if r.get("trait_score") is not None and (r.get("ticker") or "").strip()
    ]
    with_scores.sort(key=lambda x: x[0], reverse=True)
    out = []
    for i, (score, r) in enumerate(with_scores[:n], 1):
        ticker = (r.get("ticker") or "").strip().upper()
        name = (r.get("name") or ticker or "").strip()
        out.append({"ticker": ticker, "name": name, "score": score, "rank": i})
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Average return for top X Innovative Disruptors (default: 100)."
    )
    parser.add_argument(
        "x",
        nargs="?",
        type=int,
        default=None,
        help=f"Number of top disruptors to include (default: {TOP_N}); prompts if omitted",
    )
    args = parser.parse_args()
    if args.x is not None:
        top_n = args.x
    else:
        try:
            raw = input(f"Enter number of top disruptors (default {TOP_N}): ").strip()
            top_n = int(raw) if raw else TOP_N
        except (ValueError, EOFError):
            top_n = TOP_N
            print(f"Using default: {top_n}")
    if top_n < 1:
        print("Error: x must be at least 1.")
        sys.exit(1)

    print(f"Average Return: Top {top_n} Innovative Disruptors")
    print("=" * 50)
    print(f"Ranking source: {os.path.basename(TRAIT_SCORES_JSON)}")
    print(f"Period: {ANALYSIS_PERIOD_START} to present")
    print(f"Cache: {RETURNS_DB} (table: {TABLE_NAME})")
    print()

    init_db()
    top = load_top_disruptors(top_n)
    if not top:
        print("No ranking data found. Run scripts/rate_company_traits.py (or rate_top_100_traits) to generate trait_scores_confidence5_billion.json.")
        return

    # Use cache when we have same-period returns updated today (only for tickers in top x)
    cache = get_cached_returns(use_only_today=True)
    to_fetch = [s for s in top if s["ticker"] not in cache]
    results = [cache[t["ticker"]] for t in top if t["ticker"] in cache]

    if to_fetch:
        print(f"Fetching returns for {len(to_fetch)} stocks (cached: {len(cache)} / {len(top)})...")
        start_time = time.time()
        completed = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_stock = {
                executor.submit(get_live_return, s, ANALYSIS_PERIOD_START): s
                for s in to_fetch
            }
            for future in as_completed(future_to_stock):
                stock = future_to_stock[future]
                completed += 1
                print(f"Progress: {completed}/{len(to_fetch)} stocks processed...", end="\r")
                try:
                    result = future.result()
                    if result and "return" in result:
                        results.append(result)
                except Exception as e:
                    print(f"\nError processing {stock['ticker']}: {e}")
        elapsed = time.time() - start_time
    else:
        print(f"Using cached returns for all {len(top)} stocks (updated today).")
        elapsed = 0

    print()
    print("=" * 50)

    if not results:
        print("No returns could be calculated.")
        return

    # Persist all results (cache + newly fetched) so next run can use them
    store_returns(results)
    # Average over the top x only (results are already only for top x tickers)
    avg_return = sum(r["return"] for r in results) / len(results)

    # SPY (S&P 500) return for same period (use cache if updated today)
    spy_return = get_cached_spy_return(use_only_today=True)
    if spy_return is not None:
        print("Using cached SPY (S&P 500) return.")
    else:
        print("Fetching SPY (S&P 500) return for comparison...")
        spy_result = get_live_return(SPY_TICKER, ANALYSIS_PERIOD_START)
        if isinstance(spy_result, dict):
            spy_return = spy_result.get("return")
        elif isinstance(spy_result, (tuple, list)) and len(spy_result) >= 3:
            spy_return = spy_result[2]
        else:
            spy_return = None
        if spy_return is not None:
            store_spy_return(spy_return)

    print()
    print(f"Stocks with valid returns: {len(results)} / {top_n}")
    print(f"Average return (top {top_n} disruptors): {avg_return:.2f}%")
    if spy_return is not None:
        print(f"SPY (S&P 500) return:                {spy_return:.2f}%")
        diff = avg_return - spy_return
        if diff > 0:
            print(f"Top {top_n} disruptors outperformed SPY by {diff:.2f}%")
        elif diff < 0:
            print(f"Top {top_n} disruptors underperformed SPY by {-diff:.2f}%")
        else:
            print(f"Top {top_n} disruptors matched SPY.")
    else:
        print("SPY return could not be fetched (comparison skipped).")
    print(f"Stored {len(results)} returns in {TABLE_NAME}.")
    if to_fetch:
        print(f"Time: {elapsed:.1f}s")

    # Show stocks and their returns (sorted by disruptor rank)
    results_by_rank = sorted(results, key=lambda r: (r.get("rank") or 999, r["ticker"]))
    print()
    print("Stocks and returns (by disruptor rank)")
    print("-" * 60)
    print(f"{'Rank':<6} {'Ticker':<10} {'Return %':>10}  Company")
    print("-" * 60)
    for r in results_by_rank:
        rank = r.get("rank") or ""
        ticker = (r.get("ticker") or "").strip()
        ret = r.get("return")
        name = (r.get("name") or "")[:40]
        ret_str = f"{ret:+.2f}%" if ret is not None else "N/A"
        print(f"{rank:<6} {ticker:<10} {ret_str:>10}  {name}")
    print("-" * 60)


if __name__ == "__main__":
    main()
