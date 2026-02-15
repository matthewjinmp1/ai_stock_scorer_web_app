#!/usr/bin/env python3
"""
Compare overlapping scores from:
  - Prompt 5:  Tech Disruptor / AI Innovator (round scores)           — tech_disruptor_ai_round
  - Prompt 11: Tech Disruptor / AI Innovator (reason, score only)      — tech_disruptor_ai_round_reason_then_score

Reports: overlap counts, score distributions, and score-vs-score comparison for overlapping tickers.
"""

import os
import sys
import json
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import DATA_DIR

UNIFIED_RELEVANCE_CACHE = os.path.join(DATA_DIR, "batch_relevance_scores.json")

KEY_ROUND = "tech_disruptor_ai_round"
KEY_REASON = "tech_disruptor_ai_round_reason_then_score"

LABEL_ROUND = "Tech Disruptor (round scores)"
LABEL_REASON = "Tech Disruptor (reason, score only in final answer)"


def load_scores_by_ticker(prompt_key: str) -> dict:
    """Load ticker -> {ticker, name, score} from unified cache for one prompt key."""
    if not os.path.exists(UNIFIED_RELEVANCE_CACHE):
        return {}
    try:
        with open(UNIFIED_RELEVANCE_CACHE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    section = (data.get("prompts") or {}).get(prompt_key)
    scores = (section or {}).get("scores") or []
    out = {}
    for r in scores:
        ticker = (r.get("ticker") or "").strip()
        if not ticker:
            continue
        s = r.get("score")
        if s is None:
            continue
        try:
            score = float(s)
            if 0 <= score <= 100:
                out[ticker.upper()] = {
                    "ticker": r.get("ticker", ticker),
                    "name": (r.get("name") or ticker).strip(),
                    "score": score,
                }
        except (TypeError, ValueError):
            continue
    return out


def distribution_stats(scores: list) -> dict:
    """Compute min, max, mean, median, std, percentiles from a list of scores."""
    if not scores:
        return {"n": 0}
    sorted_s = sorted(scores)
    n = len(sorted_s)
    mean = sum(sorted_s) / n
    variance = sum((x - mean) ** 2 for x in sorted_s) / n
    std = variance ** 0.5
    median = sorted_s[n // 2] if n % 2 else (sorted_s[n // 2 - 1] + sorted_s[n // 2]) / 2
    p10 = sorted_s[int(0.10 * n)] if n else None
    p25 = sorted_s[int(0.25 * n)] if n else None
    p75 = sorted_s[int(0.75 * n)] if n else None
    p90 = sorted_s[int(0.90 * n)] if n else None
    return {
        "n": n,
        "min": min(scores),
        "max": max(scores),
        "mean": round(mean, 2),
        "median": round(median, 2),
        "std": round(std, 2),
        "p10": p10,
        "p25": p25,
        "p75": p75,
        "p90": p90,
    }


def score_histogram(scores: list) -> dict:
    """Count scores in bins: 0-9, 10-19, ..., 90-100."""
    hist = defaultdict(int)
    for s in scores:
        idx = min(int(s / 10), 9)
        lo, hi = idx * 10, (idx + 1) * 10 if idx < 9 else 100
        hist[(lo, hi)] += 1
    return dict(hist)


def main():
    data_round = load_scores_by_ticker(KEY_ROUND)
    data_reason = load_scores_by_ticker(KEY_REASON)

    if not data_round and not data_reason:
        print("No score data found.")
        print(f"Expected unified cache: {UNIFIED_RELEVANCE_CACHE}")
        print("Run batch_relevance_scores.py for prompt 5 and prompt 11 to generate data.")
        return 1

    tickers_round = set(data_round.keys())
    tickers_reason = set(data_reason.keys())
    overlap = tickers_round & tickers_reason
    only_round = tickers_round - tickers_reason
    only_reason = tickers_reason - tickers_round

    scores_round = [data_round[t]["score"] for t in overlap] if overlap else []
    scores_reason = [data_reason[t]["score"] for t in overlap] if overlap else []

    # ----- Overlap -----
    print("=" * 70)
    print("OVERLAP OF STOCKS")
    print("=" * 70)
    print(f"  {LABEL_ROUND} (prompt 5):  {len(tickers_round):,} stocks")
    print(f"  {LABEL_REASON} (prompt 11): {len(tickers_reason):,} stocks")
    print(f"  In both:         {len(overlap):,} stocks")
    print(f"  Only in round:   {len(only_round):,} stocks")
    print(f"  Only in reason:  {len(only_reason):,} stocks")
    if only_round and len(only_round) <= 30:
        print(f"\n  Tickers only in round:  {', '.join(sorted(only_round))}")
    elif only_round:
        print(f"\n  Tickers only in round (first 30):  {', '.join(sorted(only_round)[:30])} ...")
    if only_reason and len(only_reason) <= 30:
        print(f"  Tickers only in reason: {', '.join(sorted(only_reason))}")
    elif only_reason:
        print(f"  Tickers only in reason (first 30): {', '.join(sorted(only_reason)[:30])} ...")
    print()

    # ----- Distribution (overlapping stocks only) -----
    print("=" * 70)
    print("SCORE DISTRIBUTION (overlapping stocks only)")
    print("=" * 70)
    if not overlap:
        print("\n  No overlapping stocks; no distribution to show.")
    else:
        for label, scores, key in [
            (LABEL_ROUND, scores_round, KEY_ROUND),
            (LABEL_REASON, scores_reason, KEY_REASON),
        ]:
            print(f"\n  {label} ({key})")
            if not scores:
                print("    (no scores)")
                continue
            st = distribution_stats(scores)
            unique_count = len(set(scores))
            print(f"    n={st['n']:,}  unique={unique_count:,}  min={st['min']}  max={st['max']}  mean={st['mean']}  median={st['median']}  std={st['std']}")
            print(f"    p10={st.get('p10')}  p25={st.get('p25')}  p75={st.get('p75')}  p90={st.get('p90')}")
            hist = score_histogram(scores)
            bin_str = "    Bins:"
            for (lo, hi), count in sorted(hist.items()):
                bin_str += f" [{lo}-{hi}):{count}"
            print(bin_str)
    print()

    if not overlap:
        print("No overlapping stocks; cannot compare score values.")
        return 0

    # ----- Score comparison -----
    print("=" * 70)
    print("SCORE COMPARISON (round vs reason, overlapping stocks)")
    print("=" * 70)
    pairs = [(data_round[t]["score"], data_reason[t]["score"]) for t in overlap]
    diffs = [p[1] - p[0] for p in pairs]  # reason - round
    abs_diffs = [abs(d) for d in diffs]

    n = len(pairs)
    mean_diff = sum(diffs) / n
    mean_abs_diff = sum(abs_diffs) / n
    max_diff = max(diffs)
    min_diff = min(diffs)

    # Correlation (Pearson)
    round_vals = [p[0] for p in pairs]
    reason_vals = [p[1] for p in pairs]
    mean_r = sum(round_vals) / n
    mean_re = sum(reason_vals) / n
    cov = sum((a - mean_r) * (b - mean_re) for a, b in pairs) / n
    std_r = (sum((a - mean_r) ** 2 for a in round_vals) / n) ** 0.5
    std_re = (sum((b - mean_re) ** 2 for b in reason_vals) / n) ** 0.5
    corr = (cov / (std_r * std_re)) if (std_r and std_re) else 0

    print(f"  Overlapping stocks: {n:,}")
    print(f"  Difference = reason - round")
    print(f"    mean diff:     {mean_diff:+.2f}")
    print(f"    mean |diff|:   {mean_abs_diff:.2f}")
    print(f"    min diff:      {min_diff:+.2f}  max diff: {max_diff:+.2f}")
    print(f"  Correlation (round vs reason): {corr:.3f}")
    print()

    same = sum(1 for a, b in pairs if a == b)
    within_5 = sum(1 for a, b in pairs if abs(b - a) <= 5)
    print(f"  Same score:        {same:,}  ({100 * same / n:.1f}%)")
    print(f"  Within ±5:         {within_5:,}  ({100 * within_5 / n:.1f}%)")
    print(f"  Different:         {n - same:,}  ({100 * (n - same) / n:.1f}%)")
    print()

    # Largest |reason - round| as table
    ranked = sorted(
        [
            (t, data_round[t]["score"], data_reason[t]["score"], data_reason[t]["score"] - data_round[t]["score"])
            for t in overlap
        ],
        key=lambda x: -abs(x[3]),
    )
    rows = ranked[:20]
    col_ticker = max(10, max(len(t) for t, _, _, _ in rows) if rows else 10)
    col_name = max(4, max(len((data_round[t].get("name") or t)[:30]) for t, _, _, _ in rows) if rows else 20)
    sep = f"  +{'-' * (col_ticker + 2)}+--------+--------+{'-' * (col_name + 2)}+"
    print("  Top 20 largest |reason - round|:")
    print(sep)
    print(f"  | {'Ticker':<{col_ticker}} | {'Round':>6} | {'Reason':>6} | {'Company':<{col_name}} |")
    print(sep)
    for t, sr, sre, d in rows:
        name = (data_round[t].get("name") or t)[:col_name]
        print(f"  | {t:<{col_ticker}} | {sr:6.1f} | {sre:6.1f} | {name:<{col_name}} |")
    print(sep)
    print()

    diff_hist = defaultdict(int)
    for d in diffs:
        bucket = int(round(d))
        diff_hist[bucket] += 1
    print("  Distribution of (reason - round) differences:")
    for b in sorted(diff_hist.keys(), reverse=True):
        print(f"    diff {b:+d}: {diff_hist[b]:,} stocks")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
