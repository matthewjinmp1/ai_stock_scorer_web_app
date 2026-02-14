#!/usr/bin/env python3
"""
Show the unique count of score values for each relevance ranking (AI, Robotics,
Disruptive Innovators, Tech Disruptor). Uses the same data sources as the web app.
"""

import os
import sys
import json
import sqlite3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import (
    DATA_DIR,
    AI_RELEVANCE_DB,
    ROBOTICS_RELEVANCE_DB,
    TRAIT_SCORES_JSON,
)
UNIFIED_RELEVANCE_CACHE = os.path.join(DATA_DIR, "batch_relevance_scores.json")


def _scores_from_db(path: str) -> list:
    """Read numeric scores from relevance_scores table. Returns list of floats."""
    if not path or not os.path.exists(path):
        return []
    out = []
    conn = sqlite3.connect(path)
    rows = conn.execute(
        "SELECT score FROM relevance_scores WHERE score IS NOT NULL"
    ).fetchall()
    conn.close()
    for (score,) in rows:
        try:
            out.append(float(score))
        except (TypeError, ValueError):
            continue
    return out


def _scores_from_unified_cache(prompt_key: str) -> list:
    """Read scores from unified cache for one prompt key. Returns list of floats."""
    if not os.path.exists(UNIFIED_RELEVANCE_CACHE):
        return []
    try:
        with open(UNIFIED_RELEVANCE_CACHE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    section = (data.get("prompts") or {}).get(prompt_key)
    scores = (section or {}).get("scores") or []
    out = []
    for r in scores:
        s = r.get("score")
        if s is None:
            continue
        try:
            out.append(float(s))
        except (TypeError, ValueError):
            continue
    return out


def _scores_from_trait_json() -> list:
    """Read trait_score from Disruptive Innovators JSON. Returns list of floats."""
    if not TRAIT_SCORES_JSON or not os.path.exists(TRAIT_SCORES_JSON):
        return []
    try:
        with open(TRAIT_SCORES_JSON, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    scores_list = data.get("scores") or []
    out = []
    for r in scores_list:
        s = r.get("trait_score")
        if s is None:
            continue
        try:
            out.append(float(s))
        except (TypeError, ValueError):
            continue
    return out


def main():
    rankings = []

    # AI Relevance (DB)
    scores = _scores_from_db(AI_RELEVANCE_DB)
    rankings.append(("AI Relevance", scores, AI_RELEVANCE_DB))

    # Robotics Relevance (DB)
    scores = _scores_from_db(ROBOTICS_RELEVANCE_DB)
    rankings.append(("Robotics Relevance", scores, ROBOTICS_RELEVANCE_DB))

    # Disruptive Innovators (trait JSON)
    scores = _scores_from_trait_json()
    rankings.append(("Disruptive Innovators", scores, TRAIT_SCORES_JSON))

    # Tech Disruptor (unified cache)
    scores = _scores_from_unified_cache("tech_disruptor_ai")
    rankings.append(("Tech Disruptor", scores, UNIFIED_RELEVANCE_CACHE))

    # Report
    name_width = max(len(r[0]) for r in rankings) + 1
    print("Relevance ranking          Total    Unique scores   Source")
    print("-" * (name_width + 12 + 18 + 50))
    for name, scores, source in rankings:
        total = len(scores)
        unique = len(set(scores)) if scores else 0
        src_short = os.path.basename(source) if source else "—"
        print(f"{name:<{name_width}} {total:>6}    {unique:>14}   {src_short}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
