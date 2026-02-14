#!/usr/bin/env python3
"""
Relevance ranking score prompter: choose one of the relevance scores (AI, Robotics, Disruptive Innovators, Tech Disruptor, Tandem, All-Weather, etc.),
see the prompt, enter a ticker, then get Mimo's score and explanation via OpenRouter (xiaomi/mimo-v2-flash).
Uses same prompt bodies as batch_relevance_scores.py, with an "also give an explanation" ending.
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
from src.core.relevance_prompts import build_prompts_for_single
import openai

MODEL = "xiaomi/mimo-v2-flash"

# Single source of truth: same prompts as batch, but with "also give an explanation" ending
RELEVANCE_SCORES = build_prompts_for_single()


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


def parse_score_final(content: Optional[str], reasoning: Optional[str]) -> Optional[str]:
    """Use the last 'Score: N' in reasoning (model's conclusion), else from content."""
    for text in (reasoning, content):
        if not (text and text.strip()):
            continue
        matches = list(re.finditer(r"[Ss]core\s*:?\s*(\d{1,3})\b", text, re.IGNORECASE))
        for m in reversed(matches):
            val = int(m.group(1))
            if 0 <= val <= 100:
                return str(val)
    return None


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
        elif len(lines) == 1 and len(lines[0]) > 4:
            after_num = re.sub(r"^\s*\d{1,3}\s*[\.\)]\s*", "", lines[0], count=1)
            if after_num.strip():
                explanation = after_num.strip()
    if explanation:
        explanation = " ".join(explanation.split())[:500]
    return score, explanation or None


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
    api_key: str,
    prompt: str,
    system_hint: str,
    *,
    enable_reasoning: bool = True,
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """Call Mimo via OpenRouter. Returns (content, reasoning_content, usage_dict).
    When enable_reasoning=True, requests reasoning tokens; when False, plain completion only (score in content).
    """
    client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    messages = [
        {"role": "system", "content": system_hint},
        {"role": "user", "content": prompt},
    ]
    kwargs = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 8192,
    }
    if enable_reasoning:
        kwargs["extra_body"] = {
            "reasoning": {"enabled": True, "effort": "high"},
        }
    resp = client.chat.completions.create(**kwargs)
    usage = {}
    if getattr(resp, "usage", None):
        u = resp.usage
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
        }
        cost = getattr(u, "cost", None)
        if cost is not None:
            usage["cost"] = cost
        reasoning_tokens = 0
        if hasattr(u, "completion_tokens_details") and getattr(u, "completion_tokens_details", None):
            reasoning_tokens = getattr(u.completion_tokens_details, "reasoning_tokens", 0) or 0
        if not reasoning_tokens and hasattr(u, "reasoning_tokens"):
            reasoning_tokens = getattr(u, "reasoning_tokens", 0) or 0
        if reasoning_tokens:
            usage["reasoning_tokens"] = reasoning_tokens
    content = None
    reasoning = None
    if resp.choices:
        msg = resp.choices[0].message
        raw_content = getattr(msg, "content", None)
        # Handle list content (e.g. OpenAI-style list of blocks)
        if isinstance(raw_content, list):
            for block in raw_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    raw_content = block.get("text") or raw_content
                    break
                if hasattr(block, "type") and getattr(block, "text", None):
                    raw_content = getattr(block, "text", None)
                    break
            else:
                raw_content = None
        content = raw_content
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
        if reasoning is None:
            reasoning = _reasoning_from_details(getattr(msg, "reasoning_details", None))
        if content:
            content = str(content).strip() or None
        if reasoning:
            reasoning = str(reasoning).strip()
        # If still no content but we have reasoning, use last line of reasoning as output when it's just a number
        if not content and reasoning and reasoning.strip():
            last_line = reasoning.strip().split("\n")[-1].strip()
            if re.match(r"^(Score:\s*)?\d{1,3}$", last_line, re.IGNORECASE):
                content = last_line
    return content, reasoning, usage


def _reasoning_from_details(details: Any) -> Optional[str]:
    """Build reasoning text from OpenRouter reasoning_details array (reasoning.text / reasoning.summary / any with text)."""
    if not details or not isinstance(details, (list, tuple)):
        return None
    parts = []
    for item in details:
        if item is None:
            continue
        kind = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
        text = getattr(item, "text", None) or (item.get("text") if isinstance(item, dict) else None)
        summary = getattr(item, "summary", None) or (item.get("summary") if isinstance(item, dict) else None)
        if kind == "reasoning.text" and text:
            parts.append(str(text).strip())
        elif kind == "reasoning.summary" and summary:
            parts.append(str(summary).strip())
        elif text and kind != "reasoning.encrypted":
            parts.append(str(text).strip())
    return "\n".join(parts).strip() or None


def main():
    api_key = load_api_key()
    if not api_key:
        print("Error: OPENROUTER_KEY not set (config.py or environment).")
        sys.exit(1)

    print("Relevance ranking – Mimo score & explanation")
    print("Choose which score/prompt to use, then enter a ticker.\n")

    while True:
        print("Select score / prompt:")
        for i, s in enumerate(RELEVANCE_SCORES, 1):
            print(f"  {i}. {s['name']}")
        print("  q. Quit")
        try:
            choice = input(f"\nChoice (1–{len(RELEVANCE_SCORES)} or q): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break
        if choice in ("q", "quit", ""):
            print("Bye.")
            break
        idx = None
        try:
            idx = int(choice)
            if 1 <= idx <= len(RELEVANCE_SCORES):
                idx -= 1
            else:
                idx = None
        except ValueError:
            pass
        if idx is None:
            print(f"Invalid choice. Enter 1–{len(RELEVANCE_SCORES)} or q.\n")
            continue

        score_def = RELEVANCE_SCORES[idx]
        # Show model and attributes, then prompt with placeholder
        preview_prompt = score_def["prompt"].format(
            company_name="[Company Name]",
            ticker="[TICKER]",
        )
        print("\n" + "=" * 60)
        print("Model:", MODEL)
        print("  Reasoning: enabled, effort: high")
        print("  Prompt type:", "reason, score only in final answer" if score_def.get("score_only_no_reasoning") else "reason then score")
        print("=" * 60)
        print(f"Prompt: {score_def['name']}")
        print("=" * 60)
        print(preview_prompt)
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

            prompt = score_def["prompt"].format(company_name=company_name, ticker=ticker)
            system_hint = (
                "Use your reasoning (thinking) to analyze step-by-step how the company matches the description. "
                "Do not include any reasoning, analysis, or explanation in your response. "
                "Your response must be only the score: a single number from 0 to 100. Nothing else."
            )

            print(f"\nAsking Mimo for {score_def['name']}: {ticker} ({company_name})...")
            try:
                content, reasoning, usage = call_mimo(
                    api_key,
                    prompt,
                    system_hint,
                    enable_reasoning=True,
                )
            except Exception as e:
                print(f"  Error: {e}\n")
                continue

            if content or reasoning:
                if reasoning:
                    score = parse_score_final(content, reasoning)
                else:
                    score, _ = parse_score_and_explanation(content) if content else (None, None)
                print()
                if score is not None:
                    print(f"  Score: {score}")
                # Output = only the final answer; avoid repeating reasoning in Output when it matches.
                output_to_show = None
                if content and (not reasoning or content.strip() != reasoning.strip()):
                    output_to_show = content
                elif score is not None and (not content or (reasoning and content.strip() == reasoning.strip())):
                    output_to_show = f"Score: {score}"
                if output_to_show:
                    print("  Output:")
                    for line in output_to_show.split("\n"):
                        print(f"    {line}")
                if reasoning:
                    print("  " + "─" * 56)
                    print("  REASONING")
                    print("  " + "─" * 56)
                    for line in reasoning.split("\n"):
                        print(f"    {line}")
                    print("  " + "─" * 56)
                if not content and not reasoning:
                    print("  No response from model.")
                elif content and score is None:
                    print("  (Could not parse score from response.)")
            else:
                print("  No response from model.")
                if usage and (usage.get("completion_tokens") or 0) > 0:
                    print("  (API returned tokens but no content/reasoning; provider may use a different response format.)")

            if usage:
                pt = usage.get("prompt_tokens", 0)
                ct = usage.get("completion_tokens", 0)
                cost = usage.get("cost")
                # Split completion tokens by character proportion (reasoning vs output text)
                reasoning_chars = len(reasoning or "")
                output_chars = len(content or "")
                total_chars = reasoning_chars + output_chars
                if total_chars > 0:
                    reasoning_pct = reasoning_chars / total_chars
                    output_pct = output_chars / total_chars
                    rt_display = round(ct * reasoning_pct)
                    output_display = round(ct * output_pct)
                    token_line = f"  Input: {pt} | Reasoning: {rt_display} ({100*reasoning_pct:.0f}%) | Output: {output_display} ({100*output_pct:.0f}%)"
                else:
                    rt_display = 0
                    output_display = ct
                    token_line = f"  Input: {pt} | Reasoning: {rt_display} | Output: {output_display}"
                if cost is not None:
                    cents = float(cost) * 100
                    token_line += f" | Cost: {cents:.4f}¢"
                print(token_line)
            print()


if __name__ == "__main__":
    main()
