#!/usr/bin/env python3
"""
Compare the two Tech Disruptor relevance score sets:
  - Tech Disruptor / AI Innovator (tech_disruptor_ai) — asks Mimo to use digits other than 5 and 0
  - Tech Disruptor / AI Innovator (round scores) (tech_disruptor_ai_round) — no such instruction

Reports: score distributions, overlap of stocks, and score-vs-score comparison for overlapping stocks.
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

KEY_PRECISE = "tech_disruptor_ai"       # "Be precise... use other digits too"
KEY_ROUND = "tech_disruptor_ai_round"  # no precision instruction

LABEL_PRECISE = "Tech Disruptor (precise / use other digits)"
LABEL_ROUND = "Tech Disruptor (round scores)"


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
    """Compute min, max, mean, median, std, and percentile bins from a list of scores."""
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
        # 0-9.99 -> 0, 10-19.99 -> 1, ..., 90-100 -> 9
        idx = min(int(s / 10), 9)
        lo, hi = idx * 10, (idx + 1) * 10 if idx < 9 else 100
        hist[(lo, hi)] += 1
    return dict(hist)


def main():
    data_precise = load_scores_by_ticker(KEY_PRECISE)
    data_round = load_scores_by_ticker(KEY_ROUND)

    if not data_precise and not data_round:
        print("No Tech Disruptor score data found.")
        print(f"Expected unified cache: {UNIFIED_RELEVANCE_CACHE}")
        print("Run batch_relevance_scores.py for both prompt 4 and 5 to generate data.")
        return 1

    tickers_precise = set(data_precise.keys())
    tickers_round = set(data_round.keys())
    overlap = tickers_precise & tickers_round
    only_precise = tickers_precise - tickers_round
    only_round = tickers_round - tickers_precise

    # Scores restricted to overlapping stocks (for distribution and comparison)
    scores_precise = [data_precise[t]["score"] for t in overlap] if overlap else []
    scores_round = [data_round[t]["score"] for t in overlap] if overlap else []

    # ----- Overlap -----
    print("=" * 70)
    print("OVERLAP OF STOCKS")
    print("=" * 70)
    print(f"  {LABEL_PRECISE}:  {len(tickers_precise):,} stocks")
    print(f"  {LABEL_ROUND}:    {len(tickers_round):,} stocks")
    print(f"  In both:         {len(overlap):,} stocks")
    print(f"  Only in precise: {len(only_precise):,} stocks")
    print(f"  Only in round:   {len(only_round):,} stocks")
    if only_precise and len(only_precise) <= 30:
        print(f"\n  Tickers only in precise: {', '.join(sorted(only_precise))}")
    elif only_precise:
        print(f"\n  Tickers only in precise (first 30): {', '.join(sorted(only_precise)[:30])} ...")
    if only_round and len(only_round) <= 30:
        print(f"  Tickers only in round:   {', '.join(sorted(only_round))}")
    elif only_round:
        print(f"  Tickers only in round (first 30):   {', '.join(sorted(only_round)[:30])} ...")
    print()

    # ----- Distribution (overlapping stocks only) -----
    print("=" * 70)
    print("SCORE DISTRIBUTION (overlapping stocks only)")
    print("=" * 70)
    if not overlap:
        print("\n  No overlapping stocks; no distribution to show.")
    else:
        for label, scores, key in [
            (LABEL_PRECISE, scores_precise, KEY_PRECISE),
            (LABEL_ROUND, scores_round, KEY_ROUND),
        ]:
            print(f"\n  {label} ({key})")
            if not scores:
                print("    (no scores)")
                continue
            st = distribution_stats(scores)
            unique_count = len(set(scores))
            print(f"    n={st['n']:,}  unique values={unique_count:,}  min={st['min']}  max={st['max']}  mean={st['mean']}  median={st['median']}  std={st['std']}")
            print(f"    p10={st.get('p10')}  p25={st.get('p25')}  p75={st.get('p75')}  p90={st.get('p90')}")
            hist = score_histogram(scores)
            print("    Bins [0-10), [10-20), ..., [90-100]:")
            bin_str = "    "
            for (lo, hi), count in sorted(hist.items()):
                bin_str += f" [{lo}-{hi}):{count}"
            print(bin_str.rstrip())
    print()

    # ----- Compare values for overlapping stocks -----
    if not overlap:
        print("No overlapping stocks; cannot compare score values.")
        return 0

    print("=" * 70)
    print("SCORE COMPARISON (overlapping stocks only)")
    print("=" * 70)
    pairs = [(data_precise[t]["score"], data_round[t]["score"]) for t in overlap]
    precise_only = [p[0] for p in pairs]
    round_only = [p[1] for p in pairs]
    diffs = [p[0] - p[1] for p in pairs]
    abs_diffs = [abs(d) for d in diffs]

    n = len(pairs)
    mean_diff = sum(diffs) / n
    mean_abs_diff = sum(abs_diffs) / n
    max_diff = max(diffs)
    min_diff = min(diffs)
    # Correlation (Pearson)
    mean_a = sum(precise_only) / n
    mean_b = sum(round_only) / n
    cov = sum((a - mean_a) * (b - mean_b) for a, b in pairs) / n
    std_a = (sum((a - mean_a) ** 2 for a in precise_only) / n) ** 0.5
    std_b = (sum((b - mean_b) ** 2 for b in round_only) / n) ** 0.5
    corr = (cov / (std_a * std_b)) if (std_a and std_b) else 0

    print(f"  Overlapping stocks: {n:,}")
    print(f"  Score difference = precise - round")
    print(f"    mean diff:    {mean_diff:+.2f}")
    print(f"    mean |diff|: {mean_abs_diff:.2f}")
    print(f"    min diff:    {min_diff:+.2f}  max diff: {max_diff:+.2f}")
    print(f"  Correlation (precise vs round): {corr:.3f}")
    print()

    # Count same vs different
    same = sum(1 for a, b in pairs if a == b)
    different = n - same
    print(f"  Same score in both: {same:,}  ({100 * same / n:.1f}%)")
    print(f"  Different score:    {different:,}  ({100 * different / n:.1f}%)")
    print()

    # Show largest differences (precise - round)
    ranked_diffs = sorted(
        [(t, data_precise[t]["score"], data_round[t]["score"], data_precise[t]["score"] - data_round[t]["score"])
         for t in overlap],
        key=lambda x: -abs(x[3]),
    )
    print("  Top 15 largest |precise - round| (ticker, precise, round, diff):")
    for t, sp, sr, d in ranked_diffs[:15]:
        name = (data_precise[t].get("name") or t)[:20]
        print(f"    {t:8}  {sp:5.1f}  {sr:5.1f}  {d:+5.1f}  {name}")
    print()

    # Score value distribution of differences
    diff_hist = defaultdict(int)
    for d in diffs:
        bucket = int(d) if d == int(d) else int(d)
        diff_hist[bucket] += 1
    print("  Distribution of (precise - round) differences:")
    for b in sorted(diff_hist.keys(), reverse=True):
        print(f"    diff {b:+d}: {diff_hist[b]:,} stocks")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
