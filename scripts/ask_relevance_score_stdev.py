#!/usr/bin/env python3
"""
Run a relevance prompt multiple times for one ticker to get a sample of scores,
then compute sample mean, stdev, and the probability that a user-specified score
would be produced (empirical and normal approximation).
Flow: select prompt → enter ticker → run N times → enter score to check → show probability.
Uses score-only prompt (like batch) for consistency. Requires OPENROUTER_KEY.
"""

import math
import os
import re
import sys
import sqlite3
from typing import Optional, List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import TOP_COMPANIES_DB
from src.core.relevance_prompts import RELEVANCE_PROMPT_BODIES, ENDING_SCORE_ONLY
import openai

MODEL = "xiaomi/mimo-v2-flash"
SYSTEM_SCORE_ONLY = (
    "Reply with only one number: an integer from 0 to 100. No explanation, no other words."
)
DEFAULT_N_RUNS = 10


def get_company_name_by_ticker(ticker: str) -> Optional[str]:
    if not ticker or not os.path.exists(TOP_COMPANIES_DB):
        return None
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    try:
        row = conn.execute(
            "SELECT name FROM companies_metadata WHERE UPPER(ticker) = ? LIMIT 1",
            (ticker.strip().upper(),),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def parse_score(text: Optional[str]) -> Optional[int]:
    if not text or not str(text).strip():
        return None
    text = str(text).strip()
    for pattern in (r"[Ss]core\s*:?\s*(\d{1,3})", r"^\s*(\d{1,3})\b", r"\b(100|\d{1,2})\b"):
        match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        if match:
            val = int(match.group(1))
            if 0 <= val <= 100:
                return val
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


def call_mimo(api_key: str, prompt: str) -> Tuple[Optional[str], dict]:
    client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    messages = [
        {"role": "system", "content": SYSTEM_SCORE_ONLY},
        {"role": "user", "content": prompt},
    ]
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=16,
    )
    content = None
    if resp.choices:
        msg = resp.choices[0].message
        content = getattr(msg, "content", None) or getattr(msg, "reasoning_content", None)
    if content:
        content = str(content).strip()
    usage = {}
    if getattr(resp, "usage", None):
        u = resp.usage
        usage = {"prompt_tokens": getattr(u, "prompt_tokens", 0), "completion_tokens": getattr(u, "completion_tokens", 0)}
    return content, usage


def mean_and_stdev(samples: List[int]) -> Tuple[float, float]:
    """Sample mean and sample stdev (n-1). Returns (mean, stdev). stdev=0 if n<2."""
    n = len(samples)
    if n == 0:
        return float("nan"), 0.0
    mu = sum(samples) / n
    if n < 2:
        return mu, 0.0
    variance = sum((x - mu) ** 2 for x in samples) / (n - 1)
    return mu, math.sqrt(variance)


def std_normal_cdf(z: float) -> float:
    """Standard normal CDF using math.erf."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def normal_tail_probability(mu: float, sigma: float, score: int, right_tail: bool) -> float:
    """P(X >= score) if right_tail else P(X <= score). Uses continuity correction."""
    if sigma <= 0:
        if right_tail:
            return 1.0 if score <= mu else 0.0
        return 1.0 if score >= mu else 0.0
    if right_tail:
        # P(X >= score) ≈ P(X > score - 0.5) = 1 - Phi((score - 0.5 - mu) / sigma)
        return 1.0 - std_normal_cdf((score - 0.5 - mu) / sigma)
    # P(X <= score) ≈ P(X < score + 0.5) = Phi((score + 0.5 - mu) / sigma)
    return std_normal_cdf((score + 0.5 - mu) / sigma)


def main():
    api_key = load_api_key()
    if not api_key:
        print("Error: OPENROUTER_KEY not set (config.py or environment).")
        sys.exit(1)

    prompts = [
        {"key": p["key"], "name": p["name"], "body": p["body"]}
        for p in RELEVANCE_PROMPT_BODIES
    ]

    print("Relevance score – multiple runs for stdev & probability")
    print("Select prompt, enter ticker, we run the prompt N times, then you enter a score to check P(score).\n")

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
        print(f"\nPrompt: {score_def['name']}")

        try:
            ticker = input("Enter ticker: ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            print("\n")
            continue
        if not ticker or ticker in ("Q", "QUIT", "EXIT", "MENU", "M"):
            print("Back to menu.\n")
            continue

        company_name = get_company_name_by_ticker(ticker)
        if not company_name:
            print(f"  Ticker '{ticker}' not found in companies DB.\n")
            continue

        try:
            n_runs_input = input(f"Number of runs [{DEFAULT_N_RUNS}]: ").strip()
            n_runs = int(n_runs_input) if n_runs_input else DEFAULT_N_RUNS
        except (KeyboardInterrupt, EOFError):
            print("\n")
            continue
        if n_runs < 1 or n_runs > 50:
            print("  Use 1–50 runs.\n")
            continue

        prompt_text = score_def["body"].format(company_name=company_name, ticker=ticker) + ENDING_SCORE_ONLY
        print(f"\nRunning {n_runs} times for {ticker} ({company_name})...")

        scores: List[int] = []
        for i in range(n_runs):
            try:
                content, _ = call_mimo(api_key, prompt_text)
                s = parse_score(content)
                if s is not None:
                    scores.append(s)
                    print(f"  Run {i+1}: {s}")
                else:
                    print(f"  Run {i+1}: (parse failed) {str(content)[:60]}")
            except Exception as e:
                print(f"  Run {i+1}: Error – {e}")

        if not scores:
            print("  No valid scores; cannot compute stdev or probability.\n")
            continue

        mu, sigma = mean_and_stdev(scores)
        print()
        print("Sample:", sorted(scores))
        print(f"  n = {len(scores)},  mean = {mu:.2f},  stdev = {sigma:.2f}")

        try:
            score_to_check_input = input("\nEnter score to check probability for (0–100): ").strip()
            score_to_check = int(score_to_check_input)
        except (KeyboardInterrupt, EOFError):
            print("\n")
            continue
        except ValueError:
            print("  Invalid number.\n")
            continue
        if not 0 <= score_to_check <= 100:
            print("  Score must be 0–100.\n")
            continue

        # Tail: "this value or more extreme" = right tail if score >= mean, else left tail
        right_tail = score_to_check >= mu
        if right_tail:
            empirical_count = sum(1 for s in scores if s >= score_to_check)
            tail_label = f"score ≥ {score_to_check}"
        else:
            empirical_count = sum(1 for s in scores if s <= score_to_check)
            tail_label = f"score ≤ {score_to_check}"
        empirical_p = empirical_count / len(scores)
        normal_p = normal_tail_probability(mu, sigma, score_to_check, right_tail)

        print()
        print(f"  Score to check: {score_to_check}  (mean = {mu:.2f})")
        print(f"  Probability of {tail_label} (this value or more extreme):")
        print(f"    Empirical: {empirical_count}/{len(scores)} = {empirical_p:.2%}")
        print(f"    Normal approx: {normal_p:.2%}")
        print()


if __name__ == "__main__":
    main()
