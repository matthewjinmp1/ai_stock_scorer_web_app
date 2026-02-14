#!/usr/bin/env python3
"""
Run the same relevance prompt twice per ticker: once with "score + explanation"
and once with "score only". Shows both for comparison (e.g. to see if the
model gives different scores when asked to explain vs not).
Same flow as ask_relevance_score.py: pick prompt, then enter tickers (q/menu to go back).
Requires OPENROUTER_KEY.
"""

import os
import sys
import re
import sqlite3
from typing import Optional, Tuple, Dict, Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import TOP_COMPANIES_DB
from src.core.relevance_prompts import (
    RELEVANCE_PROMPT_BODIES,
    ENDING_WITH_EXPLANATION,
    ENDING_SCORE_ONLY,
)
import openai

MODEL = "xiaomi/mimo-v2-flash"

SYSTEM_WITH_EXPLANATION = (
    "Respond with exactly two lines: 1) Score: [0-100]. 2) Explanation: [one or two short sentences]."
)
SYSTEM_SCORE_ONLY = (
    "Reply with only one number: an integer from 0 to 100. No explanation, no other words."
)


def get_company_name_by_ticker(ticker: str) -> Optional[str]:
    """Look up company name from top_companies DB. Returns None if not found."""
    if not ticker or not os.path.exists(TOP_COMPANIES_DB):
        return None
    ticker_upper = ticker.strip().upper()
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    try:
        row = conn.execute(
            "SELECT name FROM companies_metadata WHERE UPPER(ticker) = ? LIMIT 1",
            (ticker_upper,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def parse_score_and_explanation(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Extract score (0-100) and explanation from model response. Returns (score, explanation)."""
    if text is None or not str(text).strip():
        return None, None
    text = str(text).strip()
    score = None
    for pattern in (
        r"[Ss]core\s*:?\s*(\d{1,3})",
        r"^(\d{1,3})\s*[\.\)]\s*",
        r"^\s*(\d{1,3})\b",
        r"\b(100|\d{1,2})\b",
    ):
        match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        if match:
            val = int(match.group(1))
            if 0 <= val <= 100:
                score = str(val)
                break
    if score is None:
        return None, None
    explanation = None
    expl_match = re.search(r"[Ee]xplanation\s*:?\s*(.+?)(?:\n\n|\Z)", text, re.DOTALL | re.IGNORECASE)
    if expl_match:
        explanation = expl_match.group(1).strip()
    if not explanation:
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if len(lines) >= 2:
            explanation = " ".join(lines[1:]).strip()
    if explanation:
        explanation = " ".join(explanation.split())[:500]
    return score, explanation or None


def parse_score_only(text: Optional[str]) -> Optional[str]:
    """Extract a single 0-100 score from a score-only response."""
    if not text or not str(text).strip():
        return None
    text = str(text).strip()
    for pattern in (r"[Ss]core\s*:?\s*(\d{1,3})", r"^\s*(\d{1,3})\b", r"\b(100|\d{1,2})\b"):
        match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        if match:
            val = int(match.group(1))
            if 0 <= val <= 100:
                return str(val)
    return None


def load_api_key() -> Optional[str]:
    key = os.getenv("OPENROUTER_KEY")
    if key:
        return key
    try:
        import config
        return getattr(config, "OPENROUTER_KEY", None)
    except ImportError:
        return None


def call_mimo(
    api_key: str, prompt: str, system_hint: str, max_tokens: int = 400
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Call Mimo via OpenRouter. Returns (content, usage_dict)."""
    client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    messages = [
        {"role": "system", "content": system_hint},
        {"role": "user", "content": prompt},
    ]
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=max_tokens,
    )
    usage = {}
    if getattr(resp, "usage", None):
        u = resp.usage
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
        }
    content = None
    if resp.choices:
        msg = resp.choices[0].message
        content = getattr(msg, "content", None) or getattr(msg, "reasoning_content", None)
    if content:
        content = str(content).strip()
    return content, usage


def main():
    api_key = load_api_key()
    if not api_key:
        print("Error: OPENROUTER_KEY not set (config.py or environment).")
        sys.exit(1)

    # Build menu list: same keys/names as other scripts, with body for both endings
    prompts = [
        {"key": p["key"], "name": p["name"], "body": p["body"]}
        for p in RELEVANCE_PROMPT_BODIES
    ]

    print("Relevance score comparison – same prompt, two modes (with explanation vs score only)")
    print("Choose a prompt, then enter tickers. For each ticker we call the model twice and show both.\n")

    while True:
        print("Select score / prompt:")
        for i, s in enumerate(prompts, 1):
            print(f"  {i}. {s['name']}")
        print("  q. Quit")
        try:
            choice = input(f"\nChoice (1–{len(prompts)} or q): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break
        if choice in ("q", "quit", ""):
            print("Bye.")
            break
        idx = None
        try:
            idx = int(choice)
            if 1 <= idx <= len(prompts):
                idx -= 1
            else:
                idx = None
        except ValueError:
            pass
        if idx is None:
            print(f"Invalid choice. Enter 1–{len(prompts)} or q.\n")
            continue

        score_def = prompts[idx]
        preview_with = score_def["body"].format(company_name="[Company Name]", ticker="[TICKER]") + ENDING_WITH_EXPLANATION
        print("\n" + "=" * 60)
        print(f"Prompt: {score_def['name']}")
        print("=" * 60)
        print("(1) With explanation:")
        print(preview_with[:500] + ("..." if len(preview_with) > 500 else ""))
        print("\n(2) Score only:")
        print(score_def["body"].format(company_name="[Company Name]", ticker="[TICKER]")[:200] + "..." + ENDING_SCORE_ONLY)
        print("=" * 60)
        print("Enter tickers one at a time; 'q' or 'menu' returns to prompt selection.\n")

        while True:
            try:
                ticker = input("Enter ticker: ").strip().upper()
            except (KeyboardInterrupt, EOFError):
                print("\n")
                break
            if not ticker:
                continue
            if ticker in ("Q", "QUIT", "EXIT", "MENU", "M", "BACK"):
                print("Back to menu.\n")
                break

            company_name = get_company_name_by_ticker(ticker)
            if not company_name:
                print(f"  Ticker '{ticker}' not found in companies DB. Try another.\n")
                continue

            prompt_with_expl = score_def["body"].format(company_name=company_name, ticker=ticker) + ENDING_WITH_EXPLANATION
            prompt_score_only = score_def["body"].format(company_name=company_name, ticker=ticker) + ENDING_SCORE_ONLY

            print(f"\n{score_def['name']}: {ticker} ({company_name})")
            print("-" * 50)

            # Call 1: with explanation
            print("  (1) With explanation...")
            try:
                content1, usage1 = call_mimo(api_key, prompt_with_expl, SYSTEM_WITH_EXPLANATION)
            except Exception as e:
                print(f"  Error: {e}\n")
                continue
            score1, expl1 = parse_score_and_explanation(content1) if content1 else (None, None)
            if score1 is not None:
                print(f"      Score: {score1}")
                if expl1:
                    print(f"      Explanation: {expl1}")
            else:
                print(f"      (Parse failed) Raw: {(content1 or '')[:300]}")
            if usage1:
                print(f"      Tokens: {usage1.get('prompt_tokens', 0)} in, {usage1.get('completion_tokens', 0)} out")

            # Call 2: score only
            print("  (2) Score only...")
            try:
                content2, usage2 = call_mimo(api_key, prompt_score_only, SYSTEM_SCORE_ONLY, max_tokens=16)
            except Exception as e:
                print(f"  Error: {e}\n")
                continue
            score2 = parse_score_only(content2) if content2 else None
            if score2 is not None:
                print(f"      Score: {score2}")
            else:
                print(f"      (Parse failed) Raw: {(content2 or '')[:100]}")
            if usage2:
                print(f"      Tokens: {usage2.get('prompt_tokens', 0)} in, {usage2.get('completion_tokens', 0)} out")

            # Comparison
            print("-" * 50)
            if score1 is not None and score2 is not None:
                if score1 == score2:
                    print(f"  Match: same score ({score1})")
                else:
                    print(f"  Match: DIFFERENT (with explanation={score1}, score only={score2})")
            else:
                print("  Match: (could not compare – one or both failed to parse)")
            print()


if __name__ == "__main__":
    main()
