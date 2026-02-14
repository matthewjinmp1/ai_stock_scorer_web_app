#!/usr/bin/env python3
"""
Rate companies (AI confidence ≥5 and market cap ≥$1B) on ambition/innovation traits.
Loads tickers from top_scores.db (ai_knowledge_score >= 5) joined with top_companies.db (market_cap from DB).
Uses score-only prompt. Stores results and prints ranking.
"""

import os
import sys
import sqlite3
import re
import json
import time
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import TOP_COMPANIES_DB, TOP_SCORES_DB, DATA_DIR
import openai

# Mimo v2 flash (OpenRouter, paid)
MODEL = "xiaomi/mimo-v2-flash"
INPUT_COST_PER_1M = 0.1   # $ per 1M input
OUTPUT_COST_PER_1M = 0.3  # $ per 1M output
OUTPUT_FILE = os.path.join(DATA_DIR, "trait_scores_confidence5_billion.json")
MIN_CONFIDENCE = 5        # ai_knowledge_score >= this (0-10)
MIN_MARKET_CAP = 1e9      # market cap >= $1B (USD)

# Fallback when OpenRouter key API doesn't return RPM (paid models have no documented max; set 0 = no limit)
# Override with OPENROUTER_RPM env (e.g. 200, 300, 500) to go faster if your key allows it.
REQUESTS_PER_MINUTE_DEFAULT = 200
MAX_WORKERS = 32
# Stay slightly below limit (e.g. 95% or limit - 2)
RATE_LIMIT_BUFFER = 0.95


def fetch_openrouter_rate_limit(api_key: str) -> Optional[int]:
    """GET OpenRouter key info and return requests-per-minute limit if present; else None."""
    for url in ("https://openrouter.ai/api/v1/auth/key", "https://openrouter.ai/api/v1/key"):
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                # Response may have data.rate_limit (deprecated but sometimes present) or similar
                inner = data.get("data", data)
                if isinstance(inner, dict):
                    rl = inner.get("rate_limit")
                    if isinstance(rl, dict) and "requests_per_minute" in rl:
                        return int(rl["requests_per_minute"])
                    if "requests_per_minute" in inner:
                        return int(inner["requests_per_minute"])
                # Check response headers (some APIs send limit in headers)
                for h in ("X-RateLimit-Limit-RequestsPerMinute", "X-RateLimit-Limit-RPM", "X-RateLimit-Limit"):
                    val = resp.headers.get(h)
                    if val and val.isdigit():
                        return int(val)
        except Exception:
            continue
    return None


class RateLimiter:
    """Thread-safe rate limiter: blocks until under requests_per_minute."""
    def __init__(self, requests_per_minute: int):
        self.rpm = requests_per_minute
        self.timestamps: List[float] = []
        self.lock = threading.Lock()

    def wait_if_needed(self) -> None:
        if self.rpm <= 0:
            return
        with self.lock:
            now = time.time()
            self.timestamps = [t for t in self.timestamps if now - t < 60]
            if len(self.timestamps) >= self.rpm:
                sleep_time = 60 - (now - self.timestamps[0]) + 0.2
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.time()
                    self.timestamps = [t for t in self.timestamps if now - t < 60]
            self.timestamps.append(now)

# Score-only prompt (no explanation) to minimize tokens.
PROMPT_TEMPLATE = """Rate from 0 to 100 how well this company ({company_name}, ticker: {ticker}) matches this description:

Highly innovative. Highly ambitious. Disrupts industries rather than waiting to get disrupted. Attracts world class talent. Ambitious and super smart people want to work here. Is not afraid to break the status quo. Executes boldly and rapidly on goals. Thinks long term. Eager to solve customer pains points. Obsessed with the customer. Builds amazing products that people are passionate about. Trailblazer. Disruptive innovator. Sets big goals and executes on them. Always improving. Hungry. Fierce. Bold. Able to adapt rapidly to changing conditions. Desire to make a major impact on the world. It is ok if the company makes mistakes, as long as it gets back up and fights. It is ok if the company is controversial, as long as it keeps fighting and striving.

It does not matter how big the company is, as long as it has these traits.

Be radically unbiased. No hype. If a company deserves a 0, give it a 0. If a company deserves a 100, give it a 100.

Reply with only a single number from 0 to 100. No explanation, no other text."""


def _parse_market_cap_text(market_cap_raw: Optional[str]) -> Optional[float]:
    """Parse market_cap from top_companies.db (e.g. '$4.638 T', '$966.15 B', '$500 M') to USD."""
    if not market_cap_raw or not str(market_cap_raw).strip():
        return None
    s = str(market_cap_raw).strip().upper().replace(",", "")
    if s in ("N/A", "NA", "-", ""):
        return None
    # Match number (with optional decimals) and optional unit T/B/M
    match = re.search(r"[\$]?\s*([\d.]+)\s*([TBMK]?)\s*$", s, re.IGNORECASE)
    if not match:
        return None
    try:
        num = float(match.group(1))
    except ValueError:
        return None
    unit = (match.group(2) or " ").upper()
    if unit == "T":
        return num * 1e12
    if unit == "B":
        return num * 1e9
    if unit == "M" or unit == "K":
        return num * (1e6 if unit == "M" else 1e3)
    # No unit: assume dollars if huge, else assume millions (common in data)
    return num if num >= 1e6 else num * 1e6


def get_stocks_confidence5_plus_billion() -> List[Dict[str, Any]]:
    """Load tickers from top_scores.db (ai_knowledge_score >= MIN_CONFIDENCE) joined with top_companies.db (market_cap from DB >= MIN_MARKET_CAP)."""
    if not os.path.exists(TOP_SCORES_DB):
        print(f"Error: {TOP_SCORES_DB} not found.")
        return []
    if not os.path.exists(TOP_COMPANIES_DB):
        print(f"Error: {TOP_COMPANIES_DB} not found.")
        return []
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("ATTACH DATABASE ? AS scores_db", (os.path.abspath(TOP_SCORES_DB),))
        # Join on UPPER(ticker) so case differences don't drop matches. market_cap is text (e.g. '$1.5 B') so filter in Python.
        rows = conn.execute("""
            SELECT c.ticker, COALESCE(c.name, c.ticker) AS name, c.rank, c.market_cap
            FROM companies_metadata c
            INNER JOIN (
                SELECT s1.ticker
                FROM scores_db.scores s1
                INNER JOIN (
                    SELECT ticker, MAX(timestamp) AS max_ts FROM scores_db.scores GROUP BY ticker
                ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
                WHERE s1.ai_knowledge_score >= ? AND s1.ai_knowledge_score IS NOT NULL
            ) s ON UPPER(c.ticker) = UPPER(s.ticker)
            WHERE c.market_cap IS NOT NULL AND c.market_cap != '' AND c.market_cap NOT LIKE 'N/A%'
            ORDER BY c.rank ASC, c.ticker
        """, (MIN_CONFIDENCE,)).fetchall()
    finally:
        conn.close()
    passed = []
    for r in rows:
        cap_str = r["market_cap"]
        cap_dollars = _parse_market_cap_text(cap_str)
        if cap_dollars is None or cap_dollars < MIN_MARKET_CAP:
            continue
        ticker = (r["ticker"] or "").strip().upper()
        name = (r["name"] or r["ticker"] or "").strip()
        rank = r["rank"]
        passed.append({"ticker": ticker, "name": name, "rank": rank if rank is not None else (len(passed) + 1)})
    # Re-sort by rank then ticker for stable order
    passed.sort(key=lambda x: (x["rank"] if isinstance(x["rank"], (int, float)) else 999999, x["ticker"]))
    for i, p in enumerate(passed):
        if p["rank"] is None or (isinstance(p["rank"], (int, float)) and p["rank"] != i + 1):
            p["rank"] = i + 1
    print(f"  Found {len(passed)} companies with AI confidence ≥{MIN_CONFIDENCE} and market cap ≥${MIN_MARKET_CAP/1e9:.0f}B (from top_companies.db).")
    return passed


def parse_score(text: Optional[str]) -> Optional[int]:
    """Extract a single 0-100 integer from the model response."""
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


def cost_at_paid_rate(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens / 1e6 * INPUT_COST_PER_1M) + (completion_tokens / 1e6 * OUTPUT_COST_PER_1M)


def _is_rate_limit_error(e: Exception) -> bool:
    """True if the exception indicates HTTP 429 / rate limit."""
    if getattr(e, "status_code", None) == 429:
        return True
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
            max_tokens=16,   # score-only: need only 1–3 digits
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
    # Some models put text in reasoning_content or other fields
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


def load_cache() -> Dict[str, Dict[str, Any]]:
    """Load cached scores from OUTPUT_FILE. Key = ticker (upper). Only entries with a valid trait_score count as cached."""
    if not os.path.exists(OUTPUT_FILE):
        return {}
    try:
        with open(OUTPUT_FILE, "r") as f:
            data = json.load(f)
        scores = data.get("scores") or []
        return {
            str(r.get("ticker", "")).upper(): r
            for r in scores
            if r.get("ticker") and r.get("trait_score") is not None
        }
    except Exception:
        return {}


def load_api_key() -> Optional[str]:
    key = os.getenv("OPENROUTER_KEY")
    if key:
        return key
    try:
        import config
        return getattr(config, "OPENROUTER_KEY", None)
    except ImportError:
        return None


def rate_one(
    args: Tuple[int, Dict[str, Any], str, str],
) -> Tuple[int, Dict[str, Any], int, int]:
    """Worker: rate one stock. Returns (index, result_dict, prompt_tokens, completion_tokens). On rate limit, result has rate_limited=True."""
    index, row, api_key, model = args
    ticker = row["ticker"].upper()
    name = row["name"] or ticker
    rank = row["rank"]
    prompt = PROMPT_TEMPLATE.format(company_name=name, ticker=ticker)
    messages = [
        {"role": "system", "content": "Reply with only one number: an integer from 0 to 100. No explanation, no other words."},
        {"role": "user", "content": prompt},
    ]
    prompt_tok = 0
    completion_tok = 0
    try:
        content, usage = get_completion(api_key, messages, model=model)
        if usage.get("rate_limited"):
            return index, {"ticker": ticker, "name": name, "rank": rank, "trait_score": None, "rate_limited": True}, 0, 0
        score = parse_score(content) if content else None
        prompt_tok = usage.get("prompt_tokens", 0)
        completion_tok = usage.get("completion_tokens", 0)
        if score is not None:
            return index, {"ticker": ticker, "name": name, "rank": rank, "trait_score": score}, prompt_tok, completion_tok
        return index, {"ticker": ticker, "name": name, "rank": rank, "trait_score": None}, prompt_tok, completion_tok
    except Exception as e:
        if _is_rate_limit_error(e):
            return index, {"ticker": ticker, "name": name, "rank": rank, "trait_score": None, "rate_limited": True}, 0, 0
        return index, {"ticker": ticker, "name": name, "rank": rank, "trait_score": None, "error": str(e)}, prompt_tok, completion_tok


def save_results(
    results_by_index: List[Optional[Dict[str, Any]]],
    stocks: List[Dict[str, Any]],
    model: str,
    total_prompt: int,
    total_completion: int,
) -> None:
    """Write current scores to OUTPUT_FILE (merge order by stock list)."""
    results = []
    for i in range(len(stocks)):
        if i < len(results_by_index) and results_by_index[i] is not None:
            results.append(results_by_index[i])
        else:
            row = stocks[i]
            results.append({
                "ticker": row["ticker"].upper(),
                "name": row.get("name") or row["ticker"],
                "rank": row["rank"],
                "trait_score": None,
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
        "scores": results,
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
    print("Loading companies: AI confidence ≥5 (top_scores.db) and market cap ≥$1B (top_companies.db)...")
    stocks = get_stocks_confidence5_plus_billion()
    if not stocks:
        print("No stocks found with ai_knowledge_score >= 5 and market cap >= $1B.")
        sys.exit(1)

    # Load cache: never re-fetch tickers we already have a score for
    cache = load_cache()

    # Preallocate; fill from cache so we skip those
    results_by_index: List[Optional[Dict[str, Any]]] = [None] * len(stocks)
    total_prompt = 0
    total_completion = 0
    cached_count = 0
    for i, row in enumerate(stocks):
        ticker_upper = row["ticker"].upper()
        if ticker_upper in cache:
            results_by_index[i] = cache[ticker_upper]
            cached_count += 1

    to_fetch: List[Tuple[int, Dict[str, Any], str, str]] = [
        (i, row, api_key, model)
        for i, row in enumerate(stocks)
        if results_by_index[i] is None
    ]
    fetch_count = len(to_fetch)

    print(f"Rating {len(stocks)} companies (AI confidence ≥5, market cap ≥$1B). Model: {model}")
    print(f"Cached: {cached_count} (skipped). To fetch: {fetch_count}.")
    print(f"Thread storm: {MAX_WORKERS} workers (no pre-limit); on 429 we pause 60s then retry. No stock skipped.")
    print(f"Results saved to {OUTPUT_FILE}\n")

    print_lock = threading.Lock()
    save_lock = threading.Lock()
    done_total = 0  # total successful + printed so far (for display)

    if not to_fetch:
        print("All scores already cached. Showing ranking.")
        results = [r for r in results_by_index if r is not None]
    else:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            while to_fetch:
                futures = {executor.submit(rate_one, a): a for a in to_fetch}
                retry_list: List[Tuple[int, Dict[str, Any], str, str]] = []
                wave_size = len(to_fetch)
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
                        score = result.get("trait_score")
                        ticker = result["ticker"]
                        name = result.get("name", "")
                        cost_cents = cost_at_paid_rate(prompt_tok, completion_tok) * 100
                        tok_str = f"{prompt_tok}+{completion_tok} tok"
                        with print_lock:
                            if score is not None:
                                print(f"  {done_total}/{fetch_count} {ticker} ({name}): {score}  |  {tok_str}  {cost_cents:.4f}¢")
                            else:
                                err = result.get("error", "no valid score")
                                print(f"  {done_total}/{fetch_count} {ticker} ({name}): {err}  |  {tok_str}  {cost_cents:.4f}¢")
                        with save_lock:
                            save_results(results_by_index, stocks, model, total_prompt, total_completion)
                    except Exception as e:
                        idx = args[0]
                        with print_lock:
                            print(f"  Worker error for index {idx}: {e}")
                        results_by_index[idx] = {
                            "ticker": stocks[idx]["ticker"].upper(),
                            "name": stocks[idx].get("name") or stocks[idx]["ticker"],
                            "rank": stocks[idx]["rank"],
                            "trait_score": None,
                            "error": str(e),
                        }
                        with save_lock:
                            save_results(results_by_index, stocks, model, total_prompt, total_completion)
                if retry_list:
                    with print_lock:
                        print(f"\n  Rate limit hit. {len(retry_list)} request(s) will retry. Pausing 60s (check every 1s)...")
                    for _ in range(60):
                        time.sleep(1)
                    with print_lock:
                        print(f"  Retrying {len(retry_list)} request(s).\n")
                    to_fetch = retry_list
                else:
                    break
        results = [r for r in results_by_index if r is not None]

    # Final save (full list + this run's token totals)
    save_results(results_by_index, stocks, model, total_prompt, total_completion)
    total_tokens = total_prompt + total_completion
    cost_usd = cost_at_paid_rate(total_prompt, total_completion)
    cost_cents = cost_usd * 100
    print(f"\nSaved to {OUTPUT_FILE}")
    print(f"This run: {total_tokens} tokens | Cost (paid rate): {cost_cents:.4f}¢\n")

    # Ranking: sort by trait_score descending (None last)
    ranked = sorted(
        [r for r in results if r.get("trait_score") is not None],
        key=lambda x: x["trait_score"],
        reverse=True,
    )
    failed = [r for r in results if r.get("trait_score") is None]

    width_rank = 6
    width_ticker = 14   # long tickers e.g. RELIANCE.NS, 005930.KS
    width_name = 44
    width_score = 6
    total_width = width_rank + 1 + width_ticker + 1 + width_name + 1 + width_score
    print("=" * total_width)
    print("RANKING BY TRAIT SCORE (0-100)")
    print("=" * total_width)
    print(f"{'Rank':<{width_rank}} {'Ticker':<{width_ticker}} {'Name':<{width_name}} {'Score':>{width_score}}")
    print("-" * total_width)
    for i, r in enumerate(ranked, 1):
        ticker_str = (r.get("ticker") or "")[:width_ticker]
        name = (r.get("name") or "")[:width_name]
        print(f"{i:<{width_rank}} {ticker_str:<{width_ticker}} {name:<{width_name}} {r['trait_score']:>{width_score}}")
    if failed:
        print("-" * total_width)
        print(f"(No score: {', '.join(r['ticker'] for r in failed)})")
    print("=" * total_width)


if __name__ == "__main__":
    main()
