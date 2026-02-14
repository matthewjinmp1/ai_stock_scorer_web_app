#!/usr/bin/env python3
"""
Rate a company (by ticker) 0-100 on ambition/innovation traits using OpenRouter (Mimo v2 flash).
Prompts for a ticker, looks up company name from top_companies.db, then runs the rating prompt.
"""

import os
import sys
import sqlite3
import re
from typing import Optional, Tuple, Dict, Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import TOP_COMPANIES_DB
import openai

# OpenRouter: Mimo v2 flash (paid)
MODEL = "xiaomi/mimo-v2-flash"

# Paid pricing for Mimo v2 flash — used for cost display
INPUT_COST_PER_1M = 0.1   # $ per 1M input tokens
OUTPUT_COST_PER_1M = 0.3   # $ per 1M output tokens

PROMPT_TEMPLATE = """Rate from 0 to 100 how well this company ({company_name}, ticker: {ticker}) matches this description:

Highly innovative. Highly ambitious. Disrupts industries rather than waiting to get disrupted. Attracts world class talent. Ambitious and super smart people want to work here. Is not afraid to break the status quo. Executes boldly and rapidly on goals. Thinks long term. Eager to solve customer pains points. Obsessed with the customer. Builds amazing products that people are passionate about. Trailblazer. Disruptive innovator. Sets big goals and executes on them. Always improving. Hungry. Fierce. Bold. Able to adapt rapidly to changing conditions. Desire to make a major impact on the world. It is ok if the company makes mistakes, as long as it gets back up and fights. It is ok if the company is controversial, as long as it keeps fighting and striving.

It does not matter how big the company is, as long as it has these traits.

Be radically unbiased. No hype. If a company deserves a 0, give it a 0. If a company deserves a 100, give it a 100.

Respond with exactly two lines:
1. Score: [number from 0 to 100]
2. Explanation: [one or two short sentences explaining why]"""


def get_company_name_by_ticker(ticker: str) -> Optional[str]:
    """Look up company name from top_companies.db by ticker. Returns None if not found."""
    if not ticker or not os.path.exists(TOP_COMPANIES_DB):
        return None
    ticker_upper = ticker.strip().upper()
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT name FROM companies_metadata WHERE UPPER(ticker) = ? LIMIT 1",
            (ticker_upper,),
        ).fetchone()
        return row["name"] if row else None
    finally:
        conn.close()


def parse_score_and_explanation(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Extract score (0-100) and short explanation from the model response. Returns (score, explanation)."""
    if text is None or not str(text).strip():
        return None, None
    text = str(text).strip()
    score = None
    # Try "Score: 85" or "1. Score: 85" or leading number
    for pattern in (
        r"[Ss]core\s*:?\s*(\d{1,3})",
        r"^(\d{1,3})\s*[\.\)]\s*",  # "85. " or "85) "
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
    # Explanation: after "Explanation:" or after first newline, or rest of text after score line
    explanation = None
    expl_match = re.search(r"[Ee]xplanation\s*:?\s*(.+?)(?:\n\n|\Z)", text, re.DOTALL | re.IGNORECASE)
    if expl_match:
        explanation = expl_match.group(1).strip()
    if not explanation:
        # Fallback: everything after the first line (score line)
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if len(lines) >= 2:
            explanation = " ".join(lines[1:]).strip()
        elif len(lines) == 1 and len(lines[0]) > 4:
            # Single line with score and text, e.g. "85. Strong execution..."
            after_num = re.sub(r"^\s*\d{1,3}\s*[\.\)]\s*", "", lines[0], count=1)
            if after_num.strip():
                explanation = after_num.strip()
    if explanation:
        explanation = " ".join(explanation.split())[:500]  # one line, cap length
    return score, explanation or None


def cost_at_paid_rate(prompt_tokens: int, completion_tokens: int) -> float:
    """Cost in USD at standard (paid) Mimo v2 flash rates."""
    return (prompt_tokens / 1e6 * INPUT_COST_PER_1M) + (completion_tokens / 1e6 * OUTPUT_COST_PER_1M)


def get_completion_content(
    api_key: str, messages: list, model: str = MODEL
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """Call OpenRouter and return (content, finish_reason, usage). Handles alternate response shapes."""
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        max_tokens=400,  # score + short explanation
    )
    usage = {}
    if getattr(resp, "usage", None):
        u = resp.usage
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "total_tokens": getattr(u, "total_tokens", 0),
        }

    if not resp.choices:
        return None, None, usage
    choice = resp.choices[0]
    msg = choice.message
    finish = getattr(choice, "finish_reason", None)

    # Standard field
    content = getattr(msg, "content", None)
    if content is not None and str(content).strip():
        return str(content).strip(), finish, usage
    # Some models put text elsewhere (e.g. reasoning then answer)
    if hasattr(msg, "reasoning_content") and getattr(msg, "reasoning_content", None):
        return (getattr(msg, "reasoning_content") or "").strip() or None, finish, usage
    # Debug: try to get content from message dict
    try:
        msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else dict(msg)
        for key in ("content", "text", "message", "output"):
            val = msg_dict.get(key)
            if val and str(val).strip():
                return str(val).strip(), finish, usage
    except Exception:
        pass
    return None, finish, usage


def main():
    try:
        api_key = os.getenv("OPENROUTER_KEY")
        if not api_key:
            try:
                import config
                api_key = getattr(config, "OPENROUTER_KEY", None)
            except ImportError:
                pass
        if not api_key:
            print("Error: OPENROUTER_KEY not set. Set it in config.py or environment.")
            sys.exit(1)

        model = os.getenv("OPENROUTER_MODEL", MODEL)
        total_prompt = 0
        total_completion = 0
        total_cost_usd = 0.0

        print("Rate company traits (0-100). Enter a ticker, or press Enter to quit.")
        print("Cost shown at standard (paid) Mimo v2 flash rate; you may be on free tier.\n")

        pending_tickers = list(sys.argv[1:]) if len(sys.argv) > 1 else []

        while True:
            if pending_tickers:
                ticker = pending_tickers.pop(0).strip()
            else:
                ticker = input("Ticker: ").strip()
            if not ticker:
                break
            ticker_upper = ticker.upper()

            company_name = get_company_name_by_ticker(ticker)
            if not company_name:
                print(f"  Ticker '{ticker_upper}' not found in top companies DB. Try another.\n")
                continue

            prompt = PROMPT_TEMPLATE.format(company_name=company_name, ticker=ticker_upper)
            messages = [
                {"role": "system", "content": "Respond with exactly two lines: 1) Score: [0-100]. 2) Explanation: [one or two short sentences]."},
                {"role": "user", "content": prompt},
            ]

            response, finish_reason, usage = get_completion_content(api_key, messages, model=model)

            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)
            cost_usd = cost_at_paid_rate(prompt_tokens, completion_tokens)

            total_prompt += prompt_tokens
            total_completion += completion_tokens
            total_cost_usd += cost_usd

            score, explanation = parse_score_and_explanation(response) if response else (None, None)
            if score is not None:
                print(f"  Score: {score}")
                if explanation:
                    print(f"  Explanation: {explanation}")
            else:
                print("  Model did not return a clear 0-100 score.")
                if response:
                    print("  Raw response:", response[:400])
                else:
                    if finish_reason:
                        print("  Finish reason:", finish_reason)

            cost_cents = cost_usd * 100
            total_cents = total_cost_usd * 100
            print(f"  Tokens: {prompt_tokens} in, {completion_tokens} out (total {total_tokens}) | Cost (paid rate): {cost_cents:.4f}¢")
            print(f"  Session total: {total_prompt + total_completion} tokens | {total_cents:.4f}¢\n")

        if total_prompt or total_completion:
            print(f"Session summary: {total_prompt + total_completion} tokens, {(total_cost_usd * 100):.4f}¢ at paid rate.")
        print("Bye.")

    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
