#!/usr/bin/env python3
"""
Enter a ticker; Mimo gives its best estimate for the 1-year return (from its knowledge cutoff).
Uses OpenRouter (xiaomi/mimo-v2-flash). Requires OPENROUTER_KEY.
"""

import os
import sys
import re
import sqlite3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import TOP_COMPANIES_DB
import openai

MODEL = "xiaomi/mimo-v2-flash"

PROMPT_TEMPLATE = """Given your knowledge cutoff date, what is your best estimate for the 1-year forward total return (in percent) for {ticker} ({company_name})?

Consider the company's fundamentals, competitive position, industry, and your knowledge as of your cutoff.

Provide only a single number: the expected 1-year return in percent (e.g. 15.5 for 15.5%, -5 for -5%). No explanation."""


def get_company_name(ticker: str):
    if not ticker or not os.path.exists(TOP_COMPANIES_DB):
        return ticker or "Unknown"
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    try:
        row = conn.execute(
            "SELECT name FROM companies_metadata WHERE UPPER(ticker) = ? LIMIT 1",
            (ticker.strip().upper(),),
        ).fetchone()
        return row[0] if row else ticker
    finally:
        conn.close()


def load_api_key():
    key = os.getenv("OPENROUTER_KEY")
    if key:
        return key
    try:
        import config
        return getattr(config, "OPENROUTER_KEY", None)
    except ImportError:
        return None


def parse_percent(text):
    if not text or not str(text).strip():
        return None
    text = re.sub(r"\s*%\s*$", "", str(text).strip())
    m = re.search(r"(-?\d+\.?\d*)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def ask_one(api_key: str, ticker: str) -> None:
    company_name = get_company_name(ticker)
    prompt = PROMPT_TEMPLATE.format(ticker=ticker, company_name=company_name)
    messages = [
        {"role": "system", "content": "Provide only a single number: the expected 1-year return in percent. No explanation."},
        {"role": "user", "content": prompt},
    ]
    print(f"\nAsking Mimo for 1-year return estimate: {ticker} ({company_name})...")
    client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=32,
        )
    except Exception as e:
        print(f"Error: {e}")
        return
    content = None
    if resp.choices:
        msg = resp.choices[0].message
        content = getattr(msg, "content", None) or getattr(msg, "reasoning_content", None)
    if content:
        content = str(content).strip()
    pct = parse_percent(content) if content else None
    print()
    if pct is not None:
        print(f"Mimo 1-year return estimate for {ticker}: {pct:+.1f}%")
    else:
        print(f"Raw response: {content or '(empty)'}")
    if content and pct is None:
        print("(Could not parse a number from the response.)")


def main():
    api_key = load_api_key()
    if not api_key:
        print("Error: OPENROUTER_KEY not set (config.py or environment).")
        sys.exit(1)
    print("Mimo 1-year return estimates (Ctrl+C or empty to quit)")
    print("-" * 50)
    while True:
        try:
            ticker = input("\nEnter ticker: ").strip().upper()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break
        if not ticker or ticker in ("QUIT", "Q", "EXIT"):
            print("Bye.")
            break
        ask_one(api_key, ticker)


if __name__ == "__main__":
    main()
