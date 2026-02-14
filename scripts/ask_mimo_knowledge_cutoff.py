#!/usr/bin/env python3
"""Ask Mimo (via OpenRouter) for its knowledge cutoff date. Requires OPENROUTER_KEY."""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import openai

MODEL = "xiaomi/mimo-v2-flash"


def load_api_key():
    key = os.getenv("OPENROUTER_KEY")
    if key:
        return key
    try:
        import config
        return getattr(config, "OPENROUTER_KEY", None)
    except ImportError:
        return None


def main():
    api_key = load_api_key()
    if not api_key:
        print("Error: OPENROUTER_KEY not set (config.py or environment).")
        sys.exit(1)

    client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    messages = [
        {"role": "user", "content": "What is your knowledge cutoff date? Reply with only the date (e.g. a specific date or month/year)."},
    ]

    print("Asking Mimo for knowledge cutoff date...")
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
        max_tokens=200,
    )

    if resp.choices:
        content = resp.choices[0].message.content
        if content:
            print("Response:", content.strip())
        else:
            print("No content in response.")
    else:
        print("No response from model.")

    if getattr(resp, "usage", None):
        u = resp.usage
        print("Tokens:", getattr(u, "prompt_tokens", 0), "in,", getattr(u, "completion_tokens", 0), "out")


if __name__ == "__main__":
    main()
