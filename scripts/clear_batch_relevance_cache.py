#!/usr/bin/env python3
"""Clear cached batch relevance scores for one prompt so the batch can re-score from scratch.

Usage:
  python3 scripts/clear_batch_relevance_cache.py [prompt_key]
  python3 scripts/clear_batch_relevance_cache.py tech_disruptor_ai_round_reason_then_score

If no prompt_key is given, clears tech_disruptor_ai_round_reason_then_score (prompt 11).
"""

import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import DATA_DIR, DB_DIR

UNIFIED_CACHE_FILENAME = "batch_relevance_scores.json"
DEFAULT_PROMPT_KEY = "tech_disruptor_ai_round_reason_then_score"


def clear_cache(prompt_key: str) -> None:
    unified_path = os.path.join(DATA_DIR, UNIFIED_CACHE_FILENAME)
    per_prompt_path = os.path.join(DATA_DIR, f"batch_relevance_{prompt_key}.json")
    db_path = os.path.join(DB_DIR, f"{prompt_key}_relevance_scores.db")

    # 1. Remove this prompt's section from unified cache
    if os.path.exists(unified_path):
        try:
            with open(unified_path, "r") as f:
                data = json.load(f)
            prompts = data.get("prompts") or {}
            if prompt_key in prompts:
                del prompts[prompt_key]
                data["prompts"] = prompts
                with open(unified_path, "w") as f:
                    json.dump(data, f, indent=2)
                print(f"Cleared {prompt_key} from {unified_path}")
            else:
                print(f"No section for {prompt_key} in unified cache.")
        except Exception as e:
            print(f"Error updating unified cache: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Unified cache not found: {unified_path}")

    # 2. Delete per-prompt JSON if present
    if os.path.exists(per_prompt_path):
        try:
            os.remove(per_prompt_path)
            print(f"Removed {per_prompt_path}")
        except Exception as e:
            print(f"Error removing per-prompt file: {e}", file=sys.stderr)

    # 3. Delete DB if present
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print(f"Removed {db_path}")
        except Exception as e:
            print(f"Error removing DB: {e}", file=sys.stderr)
    else:
        print(f"No DB at {db_path} (ok)")


def main():
    prompt_key = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT_KEY).strip()
    if not prompt_key:
        prompt_key = DEFAULT_PROMPT_KEY
    print(f"Clearing batch relevance cache for: {prompt_key}")
    clear_cache(prompt_key)
    print("Done. Re-run batch_relevance_scores.py and choose the same prompt to re-score.")


if __name__ == "__main__":
    main()
