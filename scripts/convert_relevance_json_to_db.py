#!/usr/bin/env python3
"""
Convert all relevance score JSONs to SQLite DBs.
Reads from:
  - data/batch_relevance_scores.json (unified: prompts.<key>.scores)
  - data/batch_relevance_<key>.json (per-prompt: scores array)
Writes data/db/<key>_relevance_scores.db for each prompt key with scores.
Schema matches existing ai_relevance_scores.db: relevance_scores(ticker, score, timestamp).
"""

import json
import os
import sqlite3
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import DATA_DIR, DB_DIR

UNIFIED_PATH = os.path.join(DATA_DIR, "batch_relevance_scores.json")
SCHEMA = """
CREATE TABLE IF NOT EXISTS relevance_scores (
    ticker TEXT PRIMARY KEY,
    score INTEGER,
    timestamp TEXT DEFAULT (datetime('now'))
);
"""


def _scores_from_unified(prompt_key: str) -> list:
    if not os.path.exists(UNIFIED_PATH):
        return []
    try:
        with open(UNIFIED_PATH, "r") as f:
            data = json.load(f)
        section = (data.get("prompts") or {}).get(prompt_key)
        return section.get("scores", []) if section else []
    except Exception:
        return []


def _scores_from_per_prompt(prompt_key: str) -> list:
    path = os.path.join(DATA_DIR, f"batch_relevance_{prompt_key}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data.get("scores", [])
    except Exception:
        return []


def get_scores_for_key(prompt_key: str) -> list:
    """Return list of {ticker, score} from unified first, else per-prompt JSON."""
    rows = _scores_from_unified(prompt_key)
    if not rows:
        rows = _scores_from_per_prompt(prompt_key)
    out = []
    for r in rows:
        ticker = (r.get("ticker") or "").strip()
        if not ticker:
            continue
        score = r.get("score")
        if score is None:
            continue
        try:
            score = int(score)
        except (TypeError, ValueError):
            continue
        if not 0 <= score <= 100:
            continue
        out.append({"ticker": ticker.upper(), "score": score})
    return out


def write_db(prompt_key: str, rows: list) -> str:
    """Write relevance_scores to data/db/<prompt_key>_relevance_scores.db. Returns path."""
    os.makedirs(DB_DIR, exist_ok=True)
    path = os.path.join(DB_DIR, f"{prompt_key}_relevance_scores.db")
    conn = sqlite3.connect(path)
    conn.executescript("DROP TABLE IF EXISTS relevance_scores;" + SCHEMA.strip())
    conn.executemany(
        "INSERT INTO relevance_scores (ticker, score) VALUES (?, ?)",
        [(r["ticker"], r["score"]) for r in rows],
    )
    conn.commit()
    conn.close()
    return path


def main():
    # All known prompt keys (unified + per-prompt filenames)
    prompt_keys = [
        "ai",
        "robotics",
        "disruptive",
        "tech_disruptor_ai",
        "tech_disruptor_ai_round",
        "tandem_company",
        "all_weather",
        "durable_advantage",
        "ai_disruption_risk",
    ]
    converted = 0
    for key in prompt_keys:
        rows = get_scores_for_key(key)
        if not rows:
            print(f"  {key}: no scores (skipped)")
            continue
        path = write_db(key, rows)
        print(f"  {key}: {len(rows)} rows -> {path}")
        converted += 1
    print(f"\nConverted {converted} relevance score sets to DBs in {DB_DIR}.")
    return 0 if converted else 1


if __name__ == "__main__":
    sys.exit(main())
