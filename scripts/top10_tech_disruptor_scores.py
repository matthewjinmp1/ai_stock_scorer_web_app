#!/usr/bin/env python3
"""
Print Tech Disruptor scores (regular + reasoning) for the top 10 largest companies by market cap.
Uses unified cache batch_relevance_scores.json and top_companies.db for market cap.
"""

import os
import re
import sys
import json
import sqlite3
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import DATA_DIR, DB_DIR, TOP_COMPANIES_DB

UNIFIED_CACHE = os.path.join(DATA_DIR, "batch_relevance_scores.json")
KEY_ROUND = "tech_disruptor_ai_round"
KEY_REASON = "tech_disruptor_ai_round_reason_then_score"


def _parse_market_cap_text(market_cap_raw: Optional[str]) -> Optional[float]:
    """Parse market_cap from top_companies.db (e.g. '$4.638 T', '$966.15 B') to USD."""
    if not market_cap_raw or not str(market_cap_raw).strip():
        return None
    s = str(market_cap_raw).strip().upper().replace(",", "")
    if s in ("N/A", "NA", "-", ""):
        return None
    match = re.search(r"[\$]?\s*([\d.]+)\s*([TBMK]?)\s*$", s, re.IGNORECASE)
    if not match:
        return None
    try:
        num = float(match.group(1))
    except ValueError:
        return None
    unit = (match.group(2) or " ").upper()
    if unit == "T":
        return num * 1e12
    if unit == "B":
        return num * 1e9
    if unit == "M" or unit == "K":
        return num * (1e6 if unit == "M" else 1e3)
    return num if num >= 1e6 else num * 1e6


def top10_by_market_cap():
    """Return list of (ticker, name, market_cap_usd) for top 10 companies by market cap."""
    if not os.path.exists(TOP_COMPANIES_DB):
        return []
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT ticker, COALESCE(name, ticker) AS name, market_cap FROM companies_metadata WHERE market_cap IS NOT NULL AND market_cap != '' AND market_cap NOT LIKE 'N/A%'"
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        cap = _parse_market_cap_text(r["market_cap"])
        if cap is None:
            continue
        out.append((r["ticker"].strip().upper(), (r["name"] or r["ticker"] or "").strip(), cap))
    out.sort(key=lambda x: -x[2])
    return out[:10]


def load_scores(prompt_key: str) -> dict:
    """Load ticker -> score from unified cache for one prompt key."""
    if not os.path.exists(UNIFIED_CACHE):
        return {}
    try:
        with open(UNIFIED_CACHE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    section = (data.get("prompts") or {}).get(prompt_key)
    scores = (section or {}).get("scores") or []
    out = {}
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
                out[ticker] = score
        except (TypeError, ValueError):
            continue
    return out


def main():
    top10 = top10_by_market_cap()
    if not top10:
        print("No companies found. Check top_companies.db and companies_metadata.")
        return 1

    round_scores = load_scores(KEY_ROUND)
    reason_scores = load_scores(KEY_REASON)

    print("Top 10 largest companies by market cap – Tech Disruptor scores")
    print("=" * 72)
    print(f"  {'#':>2}  {'Ticker':<12}  {'Company':<28}  {'Round':>5}  {'Reason':>6}")
    print("  " + "-" * 68)
    for i, (ticker, name, _cap) in enumerate(top10, 1):
        name_disp = (name[:25] + "...") if len(name) > 28 else name
        sr = round_scores.get(ticker)
        sre = reason_scores.get(ticker)
        round_str = str(sr) if sr is not None else "—"
        reason_str = str(sre) if sre is not None else "—"
        print(f"  {i:>2}  {ticker:<12}  {name_disp:<28}  {round_str:>5}  {reason_str:>6}")
    print("=" * 72)
    print("\nRound = Tech Disruptor / AI Innovator (round scores)")
    print("Reason = Tech Disruptor / AI Innovator (reason, score only in final answer)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
