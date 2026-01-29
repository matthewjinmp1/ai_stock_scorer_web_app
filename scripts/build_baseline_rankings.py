"""
Precompute baseline rankings (all-metric total_score, score_percentage, percentile,
global_rank) from the latest scores and store them in baseline_rankings table.
Run this after scores are updated so rankings, watchlist, and company detail pages
can read from the DB instead of computing on every request.

Usage (from project root):
  python scripts/build_baseline_rankings.py
"""
import os
import sys
import sqlite3
import bisect
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import TOP_SCORES_DB
from src.core.metrics import get_max_possible_score


def _percentile(score: float, sorted_scores: list) -> int:
    if not sorted_scores:
        return 0
    count_less_or_equal = bisect.bisect_right(sorted_scores, score)
    return int((count_less_or_equal / len(sorted_scores)) * 100)


def build_baseline_rankings(db_path: str = None) -> int:
    if db_path is None:
        db_path = TOP_SCORES_DB
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get scores table columns and types (exclude id; we use ticker as primary key for baseline)
    cursor.execute("PRAGMA table_info(scores)")
    table_info = [(row[1], row[2]) for row in cursor.fetchall() if row[1] != 'id']
    score_columns = [name for name, _ in table_info]
    if not score_columns:
        conn.close()
        print("scores table has no columns")
        return 0

    # Latest score per ticker (same logic as CompanyRepository.get_latest_scores)
    base_query = """
        SELECT s1.*
        FROM scores s1
        INNER JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
        ORDER BY s1.total_score DESC
    """
    cursor.execute(base_query)
    rows = cursor.fetchall()
    if not rows:
        conn.close()
        print("No scores found")
        return 0

    all_scores_sorted = sorted([float(r['total_score']) for r in rows])
    max_possible = get_max_possible_score()
    computed_at = datetime.utcnow().isoformat() + 'Z'

    # Create baseline_rankings table: same columns as scores (except id) + computed columns
    col_defs = [f'"{name}" {col_type}' for name, col_type in table_info]
    col_defs.append('score_percentage INTEGER')
    col_defs.append('percentile INTEGER')
    col_defs.append('global_rank INTEGER')
    col_defs.append('computed_at TEXT')

    cursor.execute("DROP TABLE IF EXISTS baseline_rankings")
    cursor.execute(
        "CREATE TABLE baseline_rankings ("
        + ", ".join(col_defs)
        + ", PRIMARY KEY (ticker))"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_baseline_global_rank ON baseline_rankings(global_rank)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_baseline_ticker ON baseline_rankings(ticker)"
    )

    # Build insert: score columns + score_percentage, percentile, global_rank, computed_at
    placeholders = ', '.join(['?' for _ in score_columns] + ['?', '?', '?', '?'])
    columns_for_insert = ', '.join(f'"{c}"' for c in score_columns) + ', score_percentage, percentile, global_rank, computed_at'

    for rank, row in enumerate(rows, 1):
        total_score = float(row['total_score'])
        score_pct = min(int((total_score / max_possible) * 100), 100) if max_possible > 0 else 0
        percentile_val = _percentile(total_score, all_scores_sorted)
        row_values = [row[c] for c in score_columns]
        row_values.extend([score_pct, percentile_val, rank, computed_at])
        cursor.execute(
            f"INSERT INTO baseline_rankings ({columns_for_insert}) VALUES ({placeholders})",
            row_values,
        )

    conn.commit()
    count = len(rows)
    conn.close()
    print(f"Built baseline_rankings: {count} rows (computed_at={computed_at})")
    return count


if __name__ == '__main__':
    build_baseline_rankings()
