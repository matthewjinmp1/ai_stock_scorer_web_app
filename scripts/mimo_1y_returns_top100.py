#!/usr/bin/env python3
"""
For each stock in the top 100 companies (by size), ask Mimo to give its best
estimate for the next 1-year return from its knowledge cutoff date. Uses
OpenRouter (xiaomi/mimo-v2-flash). Results saved to data/mimo_1y_returns_top100.json.
"""

import os
import sys
import json
import re
import time
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import get_top_ranked_stocks
from src.core.settings import DATA_DIR
import openai

MODEL = "xiaomi/mimo-v2-flash"
OUTPUT_FILE = os.path.join(DATA_DIR, "mimo_1y_returns_top100.json")
MAX_WORKERS = 5
INPUT_COST_PER_1M = 0.1
OUTPUT_COST_PER_1M = 0.3

PROMPT_TEMPLATE = """Given your knowledge cutoff date, what is your best estimate for the 1-year forward total return (in percent) for {ticker} ({company_name})?

Consider the company's fundamentals, competitive position, industry, and your knowledge as of your cutoff. This is a forward-looking estimate from your cutoff date.

Provide only a single number: the expected 1-year return in percent (e.g. 15.5 for 15.5% return, -5 for -5%). No explanation, no other text."""


def _is_rate_limit_error(e: Exception) -> bool:
    msg = (getattr(e, "message", "") or str(e) or "").lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


def get_completion(
    api_key: str,
    messages: list,
    model: str = MODEL,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Call OpenRouter; return (content, usage). On 429 returns (None, {'rate_limited': True})."""
    client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=32,
        )
    except Exception as e:
        if _is_rate_limit_error(e):
            return None, {"rate_limited": True}
        raise
    usage = {}
    if getattr(resp, "usage", None):
        u = resp.usage
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "total_tokens": getattr(u, "total_tokens", 0),
        }
    if not resp.choices:
        return None, usage
    msg = resp.choices[0].message
    content = getattr(msg, "content", None)
    if content is not None and str(content).strip():
        return str(content).strip(), usage
    r = getattr(msg, "reasoning_content", None)
    if r and str(r).strip():
        return str(r).strip(), usage
    try:
        msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else dict(msg)
        for key in ("content", "text", "message", "output"):
            val = msg_dict.get(key)
            if val and str(val).strip():
                return str(val).strip(), usage
    except Exception:
        pass
    return None, usage


def parse_1y_return(content: Optional[str]) -> Optional[float]:
    """Extract a single percent number from model response (e.g. 15.5, -3.2, 12%)."""
    if content is None or not str(content).strip():
        return None
    text = str(content).strip()
    # Remove trailing % and common suffixes
    text = re.sub(r"\s*%\s*$", "", text)
    text = re.sub(r"\s*percent\s*$", "", text, flags=re.I)
    # Match number: optional minus, digits, optional decimal part
    match = re.search(r"(-?\d+\.?\d*)", text)
    if match:
        try:
            val = float(match.group(1))
            return val
        except ValueError:
            pass
    return None


def cost_at_paid_rate(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens / 1e6 * INPUT_COST_PER_1M) + (completion_tokens / 1e6 * OUTPUT_COST_PER_1M)


def load_api_key() -> Optional[str]:
    key = os.getenv("OPENROUTER_KEY")
    if key:
        return key
    try:
        import config
        return getattr(config, "OPENROUTER_KEY", None)
    except ImportError:
        return None


def load_cache() -> Dict[str, Dict[str, Any]]:
    """Load cached estimates from OUTPUT_FILE. Key = ticker (upper). Only entries with estimated_1y_return_pct count."""
    if not os.path.exists(OUTPUT_FILE):
        return {}
    try:
        with open(OUTPUT_FILE, "r") as f:
            data = json.load(f)
        estimates = data.get("estimates") or []
        return {
            str(r.get("ticker", "")).upper(): r
            for r in estimates
            if r.get("ticker") and r.get("estimated_1y_return_pct") is not None
        }
    except Exception:
        return {}


def estimate_one(
    args: Tuple[int, Dict[str, Any], str, str],
) -> Tuple[int, Dict[str, Any], int, int]:
    """Worker: get 1y return estimate for one stock. Returns (index, result_dict, prompt_tokens, completion_tokens)."""
    index, row, api_key, model = args
    ticker = (row.get("ticker") or "").strip().upper()
    name = (row.get("name") or ticker or "").strip()
    rank = row.get("rank")
    prompt = PROMPT_TEMPLATE.format(ticker=ticker, company_name=name)
    messages = [
        {"role": "system", "content": "Provide only a single number: the expected 1-year return in percent (e.g. 15.5 or -5). No explanation."},
        {"role": "user", "content": prompt},
    ]
    prompt_tok = 0
    completion_tok = 0
    try:
        content, usage = get_completion(api_key, messages, model=model)
        if usage.get("rate_limited"):
            return index, {
                "ticker": ticker,
                "name": name,
                "rank": rank,
                "estimated_1y_return_pct": None,
                "raw_response": None,
                "rate_limited": True,
            }, 0, 0
        prompt_tok = usage.get("prompt_tokens", 0)
        completion_tok = usage.get("completion_tokens", 0)
        pct = parse_1y_return(content) if content else None
        return index, {
            "ticker": ticker,
            "name": name,
            "rank": rank,
            "estimated_1y_return_pct": pct,
            "raw_response": content,
        }, prompt_tok, completion_tok
    except Exception as e:
        if _is_rate_limit_error(e):
            return index, {
                "ticker": ticker,
                "name": name,
                "rank": rank,
                "estimated_1y_return_pct": None,
                "raw_response": None,
                "rate_limited": True,
            }, 0, 0
        return index, {
            "ticker": ticker,
            "name": name,
            "rank": rank,
            "estimated_1y_return_pct": None,
            "raw_response": None,
            "error": str(e),
        }, prompt_tok, completion_tok


def save_results(
    results_by_index: List[Optional[Dict[str, Any]]],
    stocks: List[Dict[str, Any]],
    model: str,
    total_prompt: int,
    total_completion: int,
) -> None:
    """Write current estimates to OUTPUT_FILE (merge order by stock list)."""
    results = []
    for i in range(len(stocks)):
        if i < len(results_by_index) and results_by_index[i] is not None:
            results.append(results_by_index[i])
        else:
            row = stocks[i]
            results.append({
                "ticker": (row.get("ticker") or "").upper(),
                "name": row.get("name") or row.get("ticker", ""),
                "rank": row.get("rank"),
                "estimated_1y_return_pct": None,
                "raw_response": None,
            })
    total_tokens = total_prompt + total_completion
    cost_usd = cost_at_paid_rate(total_prompt, total_completion)
    out = {
        "updated": datetime.utcnow().isoformat() + "Z",
        "model": model,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_tokens,
        "cost_paid_rate_usd": round(cost_usd, 6),
        "estimates": results,
    }
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, indent=2)


def main():
    api_key = load_api_key()
    if not api_key:
        print("Error: OPENROUTER_KEY not set (config.py or environment).")
        sys.exit(1)

    model = os.getenv("OPENROUTER_MODEL", MODEL)
    print("Loading top 100 companies by size (top_companies.db + top_scores.db)...")
    stocks = get_top_ranked_stocks(100)
    if not stocks:
        print("No top 100 stocks found.")
        sys.exit(1)

    cache = load_cache()
    results_by_index: List[Optional[Dict[str, Any]]] = [None] * len(stocks)
    total_prompt = 0
    total_completion = 0
    cached_count = 0
    for i, row in enumerate(stocks):
        ticker_upper = (row.get("ticker") or "").strip().upper()
        if ticker_upper in cache:
            results_by_index[i] = cache[ticker_upper]
            cached_count += 1

    to_fetch = [
        (i, row, api_key, model)
        for i, row in enumerate(stocks)
        if results_by_index[i] is None
    ]
    fetch_count = len(to_fetch)

    print(f"Top 100 companies loaded. Model: {model}")
    print(f"Cached: {cached_count} (skipped). To fetch: {fetch_count}.")
    print(f"On rate limit (429): pause 60s then retry. Results saved to {OUTPUT_FILE}\n")

    print_lock = threading.Lock()
    save_lock = threading.Lock()
    done_total = 0

    if not to_fetch:
        print("All estimates already cached.")
    else:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            while to_fetch:
                futures = {executor.submit(estimate_one, a): a for a in to_fetch}
                retry_list = []
                for future in as_completed(futures):
                    args = futures[future]
                    index = args[0]
                    try:
                        index, result, prompt_tok, completion_tok = future.result()
                        if result.get("rate_limited"):
                            retry_list.append((index, stocks[index], api_key, model))
                            continue
                        results_by_index[index] = result
                        total_prompt += prompt_tok
                        total_completion += completion_tok
                        done_total += 1
                        pct = result.get("estimated_1y_return_pct")
                        ticker = result.get("ticker", "")
                        name = result.get("name", "")
                        cost_cents = cost_at_paid_rate(prompt_tok, completion_tok) * 100
                        with print_lock:
                            if pct is not None:
                                print(f"  {done_total}/{fetch_count} {ticker} ({name}): {pct:+.1f}%  |  {cost_cents:.4f}¢")
                            else:
                                err = result.get("error", "no valid number")
                                print(f"  {done_total}/{fetch_count} {ticker} ({name}): {err}  |  {cost_cents:.4f}¢")
                        with save_lock:
                            save_results(results_by_index, stocks, model, total_prompt, total_completion)
                    except Exception as e:
                        with print_lock:
                            print(f"  Worker error for index {index}: {e}")
                        results_by_index[index] = {
                            "ticker": stocks[index].get("ticker", "").upper(),
                            "name": stocks[index].get("name") or stocks[index].get("ticker", ""),
                            "rank": stocks[index].get("rank"),
                            "estimated_1y_return_pct": None,
                            "raw_response": None,
                            "error": str(e),
                        }
                        with save_lock:
                            save_results(results_by_index, stocks, model, total_prompt, total_completion)
                if retry_list:
                    with print_lock:
                        print(f"\n  Rate limit hit. {len(retry_list)} request(s) will retry. Pausing 60s...")
                    for _ in range(60):
                        time.sleep(1)
                    with print_lock:
                        print(f"  Retrying {len(retry_list)} request(s).\n")
                    to_fetch = retry_list
                else:
                    break

    save_results(results_by_index, stocks, model, total_prompt, total_completion)
    total_tokens = total_prompt + total_completion
    cost_usd = cost_at_paid_rate(total_prompt, total_completion)
    print(f"\nSaved to {OUTPUT_FILE}")
    print(f"This run: {total_tokens} tokens | Cost (paid rate): {cost_usd * 100:.4f}¢")

    # Summary table
    results = [r for r in results_by_index if r is not None]
    with_estimate = [r for r in results if r.get("estimated_1y_return_pct") is not None]
    if with_estimate:
        ranked = sorted(with_estimate, key=lambda x: x["estimated_1y_return_pct"], reverse=True)
        print("\n" + "=" * 70)
        print("MIMO 1-YEAR RETURN ESTIMATES (from knowledge cutoff)")
        print("=" * 70)
        print(f"{'Rank':<6} {'Ticker':<12} {'Est. 1Y %':>12}  Company")
        print("-" * 70)
        for i, r in enumerate(ranked[:30], 1):
            ticker = (r.get("ticker") or "")[:12]
            pct = r.get("estimated_1y_return_pct")
            name = (r.get("name") or "")[:42]
            print(f"{i:<6} {ticker:<12} {pct:>+10.1f}%  {name}")
        if len(ranked) > 30:
            print(f"  ... and {len(ranked) - 30} more (see {OUTPUT_FILE})")
        print("-" * 70)


if __name__ == "__main__":
    main()
