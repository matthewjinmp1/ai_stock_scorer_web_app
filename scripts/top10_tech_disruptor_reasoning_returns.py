#!/usr/bin/env python3
"""
Return of the top 10 stocks by Tech Disruptor (reasoning) score, from start of 2025 to now.
Uses unified cache for scores and price_fetcher for returns.
"""

import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import DATA_DIR
from src.core.price_fetcher import get_live_return

UNIFIED_CACHE = os.path.join(DATA_DIR, "batch_relevance_scores.json")
KEY_REASON = "tech_disruptor_ai_round_reason_then_score"
START_DATE = "2025-01-01"


def load_top10_by_reasoning_score():
    """Load top 10 tickers by Tech Disruptor reasoning score (highest first)."""
    if not os.path.exists(UNIFIED_CACHE):
        return []
    try:
        with open(UNIFIED_CACHE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    section = (data.get("prompts") or {}).get(KEY_REASON)
    scores = (section or {}).get("scores") or []
    out = []
    for r in scores:
        ticker = (r.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        s = r.get("score")
        if s is None:
            continue
        try:
            score = int(s) if isinstance(s, (int, float)) else int(float(s))
            if 0 <= score <= 100:
                name = (r.get("name") or ticker).strip()
                out.append({"ticker": ticker, "name": name, "score": score})
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: -x["score"])
    return out[:10]


def main():
    top10 = load_top10_by_reasoning_score()
    if not top10:
        print("No Tech Disruptor (reasoning) scores found. Run batch_relevance_scores.py for prompt 6.")
        return 1

    print("Top 10 by Tech Disruptor (reasoning) score – return from {} to now".format(START_DATE))
    print("=" * 78)
    print("  {:>2}  {:<10}  {:<24}  {:>5}  {:>10}  {:>10}  {:>8}".format(
        "#", "Ticker", "Company", "Score", "Start", "Current", "Return %"))
    print("  " + "-" * 74)

    for i, row in enumerate(top10, 1):
        ticker = row["ticker"]
        name_disp = (row["name"][:22] + "..") if len(row["name"]) > 24 else row["name"]
        result = get_live_return({"ticker": ticker}, start_date=START_DATE)
        if result and result.get("return") is not None:
            start_p = result.get("start_price")
            end_p = result.get("current_price")
            ret = result.get("return")
            print("  {:>2}  {:<10}  {:<24}  {:>5}  ${:>9.2f}  ${:>9.2f}  {:>7.1f}%".format(
                i, ticker, name_disp, row["score"], start_p, end_p, ret))
        else:
            print("  {:>2}  {:<10}  {:<24}  {:>5}  {:>10}  {:>10}  {:>8}".format(
                i, ticker, name_disp, row["score"], "—", "—", "—"))

    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
