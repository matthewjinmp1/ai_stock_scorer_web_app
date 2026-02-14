#!/usr/bin/env python3
"""Show distribution of AI confidence scores (ai_knowledge_score) from top_scores.db (latest per ticker)."""
import os
import sys
import sqlite3
import statistics

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import TOP_SCORES_DB

def main():
    if not os.path.exists(TOP_SCORES_DB):
        print(f"Error: Database not found at {TOP_SCORES_DB}")
        sys.exit(1)
    conn = sqlite3.connect(TOP_SCORES_DB)
    conn.row_factory = sqlite3.Row
    # Latest ai_knowledge_score per ticker
    query = """
        SELECT s1.ai_knowledge_score AS score
        FROM scores s1
        INNER JOIN (
            SELECT ticker, MAX(timestamp) AS max_ts FROM scores GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
        WHERE s1.ai_knowledge_score IS NOT NULL
    """
    rows = conn.execute(query).fetchall()
    conn.close()
    values = [float(r["score"]) for r in rows]
    if not values:
        print("No ai_knowledge_score values in top_scores.db.")
        return
    n = len(values)
    # ai_knowledge_score is 0-10; buckets 0, 1, 2, ... 10
    buckets = [0] * 11
    for v in values:
        v = max(0, min(10, round(v)))
        buckets[int(v)] += 1
    mean = statistics.mean(values)
    median = statistics.median(values)
    stdev = statistics.stdev(values) if n > 1 else 0
    mn = min(values)
    mx = max(values)
    print("AI confidence (ai_knowledge_score) distribution — top_scores.db (latest per ticker)")
    print("=" * 60)
    print(f"  N = {n}")
    print(f"  Mean:   {mean:.2f}")
    print(f"  Median: {median:.2f}")
    print(f"  Std:    {stdev:.2f}")
    print(f"  Min:    {mn:.2f}")
    print(f"  Max:    {mx:.2f}")
    print()
    print("  Score (0-10)  Count  Bar")
    print("-" * 60)
    max_count = max(buckets) or 1
    for i in range(11):
        label = f"  {i}"
        bar = "#" * (int(40 * buckets[i] / max_count)) if max_count else ""
        print(f"  {label:>10}  {buckets[i]:>5}  {bar}")
    print("=" * 60)

if __name__ == "__main__":
    main()
