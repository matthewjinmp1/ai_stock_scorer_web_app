#!/usr/bin/env python3
"""
Print the top 100 stocks for a selected relevance ranking.
Export to CSV for Google Sheets (File → Import or upload the file).
Uses the same ranking data as the web app (AI Relevance, Robotics, Disruptive Innovators, Tech Disruptor, Tandem, All-Weather).
Run from project root or ensure scripts/ is in path.
"""

import csv
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Use the app's single source of truth for rankings
from src.web.app import get_relevance_ranking, RELEVANCE_TYPES, RELEVANCE_TABS_DISABLED

TOP_N = 100


def main():
    enabled = [r for r in RELEVANCE_TYPES if r["key"] not in RELEVANCE_TABS_DISABLED]
    if not enabled:
        print("No rankings are enabled (RELEVANCE_TABS_DISABLED).")
        sys.exit(1)

    print("Select ranking (top {} will be printed):\n".format(TOP_N))
    for i, r in enumerate(enabled, 1):
        print("  {}. {}".format(i, r["display_name"]))
    print("  q. Quit")
    try:
        choice = input("\nChoice (1–{} or q): ".format(len(enabled))).strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nBye.")
        sys.exit(0)
    if choice in ("q", "quit", ""):
        print("Bye.")
        sys.exit(0)

    idx = None
    try:
        idx = int(choice)
        if 1 <= idx <= len(enabled):
            idx -= 1
        else:
            idx = None
    except ValueError:
        pass
    if idx is None:
        print("Invalid choice.")
        sys.exit(1)

    selected = enabled[idx]
    key = selected["key"]
    name = selected["display_name"]

    print("\nLoading {} ranking...".format(name))
    rows = get_relevance_ranking(key)
    if not rows:
        print("No data for this ranking. {}".format(selected.get("empty_message", "")))
        sys.exit(1)

    top = rows[:TOP_N]
    print("\nTop {} – {}\n".format(len(top), name))
    print("{:>5}  {:<8}  {:40}  {:>6}  {:>10}".format(
        "Rank", "Ticker", "Company", "Score", "Percentile"
    ))
    print("-" * 5 + "  " + "-" * 8 + "  " + "-" * 40 + "  " + "-" * 6 + "  " + "-" * 10)
    for r in top:
        rank = r.get("relevance_rank", "")
        ticker = (r.get("ticker") or "")[:8]
        company = (r.get("name") or "")[:40]
        score = r.get("relevance_score")
        score_str = str(int(score)) if score is not None and score == int(score) else str(score) if score is not None else "—"
        pct = r.get("relevance_percentile")
        pct_str = "{}%".format(int(pct)) if pct is not None else "—"
        print("{:>5}  {:<8}  {:40}  {:>6}  {:>10}".format(
            rank, ticker, company, score_str, pct_str
        ))
    print("\n(Total in ranking: {}.)".format(len(rows)))

    # Export to CSV for Google Sheets
    default_path = "top100_{}.csv".format(key)
    try:
        export = input("\nExport to CSV for Sheets? Enter path [{}]: ".format(default_path)).strip()
    except (KeyboardInterrupt, EOFError):
        export = ""
    if not export:
        export = default_path
    if export:
        try:
            with open(export, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Rank", "Ticker", "Company", "Score", "Percentile"])
                for r in top:
                    score = r.get("relevance_score")
                    score_str = str(int(score)) if score is not None and score == int(score) else str(score) if score is not None else ""
                    pct = r.get("relevance_percentile")
                    pct_str = "{}%".format(int(pct)) if pct is not None else ""
                    w.writerow([
                        r.get("relevance_rank", ""),
                        r.get("ticker", ""),
                        r.get("name", ""),
                        score_str,
                        pct_str,
                    ])
            print("Saved to {} (open in Google Sheets: File → Import → Upload).".format(os.path.abspath(export)))
        except OSError as e:
            print("Could not write file: {}.".format(e))


if __name__ == "__main__":
    main()
