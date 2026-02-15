#!/usr/bin/env python3
"""
Batch relevance scoring: run one of the relevance prompts (AI, Robotics, Disruptive Innovators, Tech Disruptor, Tech Disruptor round)
on all stocks in the top companies DB that pass your filter (AI confidence ≥ X, market cap ≥ Y).
Uses Mimo (OpenRouter) for score only (no explanation). Asks for filter criteria, shows estimated cost, then runs.
Requires OPENROUTER_KEY.
"""

import os
import sys
import re
import json
import sqlite3
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import (
    TOP_COMPANIES_DB,
    TOP_SCORES_DB,
    DATA_DIR,
    DB_DIR,
    AI_RELEVANCE_DB,
    ROBOTICS_RELEVANCE_DB,
    TRAIT_SCORES_JSON,
)
from src.core.relevance_prompts import build_prompts_for_batch
import openai

MODEL = "xiaomi/mimo-v2-flash"
# OpenRouter paid pricing (approximate; update if needed)
INPUT_COST_PER_1M = 0.1   # $ per 1M input tokens
OUTPUT_COST_PER_1M = 0.3  # $ per 1M output tokens
# Token estimates per request (score-only: short completion)
# Input is derived from actual prompt length; output is fixed for "0-100" style reply.
EST_OUTPUT_TOKENS_PER_REQUEST = 5
# Reason-then-score prompt: model returns reasoning tokens + short score; billable as output.
EST_OUTPUT_TOKENS_REASON_THEN_SCORE = 2700
# Approximate chars per token for English (used when actual tokenizer not available)
CHARS_PER_TOKEN = 4
REASON_THEN_SCORE_PROMPT_KEY = "tech_disruptor_ai_round_reason_then_score"

# Concurrency: maximum throughput (paid plan; no rate limiting)
MAX_WORKERS = 128
REQUESTS_PER_MINUTE_DEFAULT = 0  # 0 = no limit; set OPENROUTER_RPM to cap if needed

# Single source of truth: prompts from src.core.relevance_prompts (score-only ending for batch)
RELEVANCE_PROMPTS = build_prompts_for_batch()

SYSTEM_HINT = "Reply with only one number: an integer from 0 to 100. No explanation, no other words."
SYSTEM_HINT_REASON_THEN_SCORE = (
    "Use your reasoning (thinking) to analyze step-by-step, then output only a single number from 0 to 100. Nothing else."
)


def _parse_market_cap_text(market_cap_raw: Optional[str]) -> Optional[float]:
    """Parse market_cap from top_companies.db (e.g. '$4.638 T', '$966.15 B', '$500 M') to USD."""
    if not market_cap_raw or not str(market_cap_raw).strip():
        return None
    s = str(market_cap_raw).strip().upper().replace(",", "")
    if s in ("N/A", "NA", "-", ""):
        return None
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
    return num if num >= 1e6 else num * 1e6


def get_stocks_filtered(
    min_confidence: float,
    min_market_cap_usd: float,
) -> List[Dict[str, Any]]:
    """Load tickers from top_scores (ai_knowledge_score >= min_confidence) joined with top_companies (market_cap >= min_market_cap_usd)."""
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
        rows = conn.execute(
            """
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
            """,
            (min_confidence,),
        ).fetchall()
    finally:
        conn.close()
    passed = []
    for r in rows:
        cap_dollars = _parse_market_cap_text(r["market_cap"])
        if cap_dollars is None or cap_dollars < min_market_cap_usd:
            continue
        ticker = (r["ticker"] or "").strip().upper()
        name = (r["name"] or r["ticker"] or "").strip()
        rank = r["rank"]
        passed.append({"ticker": ticker, "name": name, "rank": rank if rank is not None else (len(passed) + 1)})
    passed.sort(key=lambda x: (x["rank"] if isinstance(x["rank"], (int, float)) else 999999, x["ticker"]))
    for i, p in enumerate(passed):
        if p["rank"] is None or (isinstance(p["rank"], (int, float)) and p["rank"] != i + 1):
            p["rank"] = i + 1
    return passed


def estimate_prompt_tokens(prompt_template: str, company_name: str = "Example Corp", ticker: str = "AAPL") -> int:
    """Estimate input tokens for one request from the prompt template (with placeholders filled)."""
    try:
        text = prompt_template.format(company_name=company_name, ticker=ticker)
    except KeyError:
        text = prompt_template
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def estimate_cost_usd(
    num_requests: int,
    input_tokens_per_request: Optional[int] = None,
    output_tokens_per_request: Optional[int] = None,
) -> Tuple[float, int, int]:
    """Return (estimated_cost_usd, est_input_tokens, est_output_tokens).
    If input_tokens_per_request is None, uses a default (~320).
    If output_tokens_per_request is None, uses EST_OUTPUT_TOKENS_PER_REQUEST (score-only).
    Use EST_OUTPUT_TOKENS_REASON_THEN_SCORE for reason-then-score prompts (reasoning + score billed as output).
    """
    if input_tokens_per_request is None:
        input_tokens_per_request = 320
    if output_tokens_per_request is None:
        output_tokens_per_request = EST_OUTPUT_TOKENS_PER_REQUEST
    est_input = num_requests * input_tokens_per_request
    est_output = num_requests * output_tokens_per_request
    cost = (est_input / 1e6 * INPUT_COST_PER_1M) + (est_output / 1e6 * OUTPUT_COST_PER_1M)
    return round(cost, 4), est_input, est_output


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


def _normalize_score(score: Any) -> Optional[int]:
    """Coerce score to int in 0-100 if possible; else None."""
    if score is None:
        return None
    if isinstance(score, int):
        return score if 0 <= score <= 100 else None
    if isinstance(score, float):
        if 0 <= score <= 100 and score == int(score):
            return int(score)
        return None
    if isinstance(score, str):
        s = score.strip()
        if s.isdigit():
            val = int(s)
            return val if 0 <= val <= 100 else None
    return None


# Single unified cache file for all 4 prompt types (one place to look, works for all)
UNIFIED_CACHE_FILENAME = "batch_relevance_scores.json"


RELEVANCE_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS relevance_scores (
    ticker TEXT PRIMARY KEY,
    score INTEGER,
    timestamp TEXT DEFAULT (datetime('now'))
);
"""


def _insert_one_relevance_score(prompt_key: str, ticker: str, score: int) -> None:
    """Insert or replace a single score in the relevance DB. Call as each score is received so progress is persisted."""
    if not ticker or _normalize_score(score) is None:
        return
    os.makedirs(DB_DIR, exist_ok=True)
    path = os.path.join(DB_DIR, f"{prompt_key}_relevance_scores.db")
    try:
        conn = sqlite3.connect(path)
        conn.execute(RELEVANCE_DB_SCHEMA.strip())
        conn.execute(
            "INSERT OR REPLACE INTO relevance_scores (ticker, score) VALUES (?, ?)",
            (ticker.strip().upper(), int(score)),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _write_relevance_scores_to_db(prompt_key: str, scores_list: List[Dict[str, Any]]) -> None:
    """Write full scores list to data/db/<prompt_key>_relevance_scores.db (same schema app reads)."""
    os.makedirs(DB_DIR, exist_ok=True)
    path = os.path.join(DB_DIR, f"{prompt_key}_relevance_scores.db")
    conn = sqlite3.connect(path)
    conn.executescript("DROP TABLE IF EXISTS relevance_scores;" + RELEVANCE_DB_SCHEMA.strip())
    rows = []
    for r in scores_list:
        ticker = (r.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        score = _normalize_score(r.get("score"))
        if score is None:
            continue
        rows.append((ticker, score))
    conn.executemany("INSERT INTO relevance_scores (ticker, score) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def _save_unified_section(unified_path: str, prompt_key: str, out: Dict[str, Any]) -> None:
    """Update one prompt's section in the unified cache file."""
    data = {"prompts": {}}
    if os.path.exists(unified_path):
        try:
            with open(unified_path, "r") as f:
                data = json.load(f)
            if not isinstance(data.get("prompts"), dict):
                data["prompts"] = {}
        except Exception:
            data["prompts"] = {}
    section = {
        "scores": out.get("scores", []),
        "total_prompt_tokens": out.get("total_prompt_tokens", 0),
        "total_completion_tokens": out.get("total_completion_tokens", 0),
        "cost_usd": out.get("cost_usd", 0),
        "updated": out.get("updated", ""),
        "filter_min_confidence": out.get("filter_min_confidence"),
        "filter_min_market_cap_billions": out.get("filter_min_market_cap_billions"),
        "prompt_name": out.get("prompt_name", ""),
        "model": out.get("model", MODEL),
    }
    data["prompts"][prompt_key] = section
    with open(unified_path, "w") as f:
        json.dump(data, f, indent=2)


def _scores_list_to_cache(scores: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], int, int]:
    """Build cache dict and token totals from a scores list. Returns (cache, prev_prompt_tokens, prev_completion_tokens)."""
    cache = {}
    for r in scores:
        ticker = (r.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        score = _normalize_score(r.get("score"))
        if score is not None:
            cache[ticker] = {
                "ticker": r.get("ticker", ticker),
                "name": r.get("name", ticker),
                "rank": r.get("rank"),
                "score": score,
            }
    return cache, 0, 0


def load_cache(
    prompt_key: str,
    out_file: str,
    fallback_paths: Optional[List[str]] = None,
    data_dir: str = "",
    project_root: str = "",
) -> Tuple[Dict[str, Dict[str, Any]], int, int, Optional[str]]:
    """Load existing scores for this prompt. Tries unified file first, then per-prompt files. Returns (cache, prev_prompt_tokens, prev_completion_tokens, path_loaded_from)."""
    cwd = os.getcwd()
    # Order: unified in DATA_DIR, unified in cwd, unified in cwd/data, then per-prompt canonical + fallbacks
    unified_in_data = os.path.join(data_dir, UNIFIED_CACHE_FILENAME) if data_dir else ""
    unified_cwd = os.path.join(cwd, UNIFIED_CACHE_FILENAME)
    unified_cwd_data = os.path.join(cwd, "data", UNIFIED_CACHE_FILENAME)
    per_prompt = out_file
    paths_to_try = []
    for p in [unified_in_data, unified_cwd, unified_cwd_data, per_prompt] + (fallback_paths or []):
        if not p or not os.path.exists(p):
            continue
        ap = os.path.abspath(p)
        if ap not in [os.path.abspath(x) for x in paths_to_try]:
            paths_to_try.append(p)
    for path in paths_to_try:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception:
            continue
        is_unified = os.path.basename(path) == UNIFIED_CACHE_FILENAME
        if is_unified:
            prompts = data.get("prompts") or {}
            section = prompts.get(prompt_key)
            if not section:
                continue
            scores = section.get("scores") or []
            prev_prompt = int(section.get("total_prompt_tokens", 0) or 0)
            prev_completion = int(section.get("total_completion_tokens", 0) or 0)
        else:
            scores = data.get("scores") or []
            prev_prompt = int(data.get("total_prompt_tokens", 0) or 0)
            prev_completion = int(data.get("total_completion_tokens", 0) or 0)
        cache = {}
        for r in scores:
            ticker = (r.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            score = _normalize_score(r.get("score"))
            if score is not None:
                cache[ticker] = {
                    "ticker": r.get("ticker", ticker),
                    "name": r.get("name", ticker),
                    "rank": r.get("rank"),
                    "score": score,
                }
        return cache, prev_prompt, prev_completion, path
    return {}, 0, 0, None


def _get_ticker_names(tickers: List[str]) -> Dict[str, str]:
    """Return dict of ticker (upper) -> name from top_companies. Missing tickers get ticker as name."""
    if not tickers or not os.path.exists(TOP_COMPANIES_DB):
        return {t.upper(): t for t in tickers} if tickers else {}
    result = {t.upper(): t for t in tickers}
    try:
        conn = sqlite3.connect(TOP_COMPANIES_DB)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(tickers))
        rows = conn.execute(
            f"SELECT ticker, name FROM companies_metadata WHERE UPPER(ticker) IN ({placeholders})",
            [t.upper() for t in tickers],
        ).fetchall()
        conn.close()
        for r in rows:
            t = (r["ticker"] or "").strip().upper()
            if t:
                result[t] = (r["name"] or r["ticker"] or t).strip()
    except Exception:
        pass
    return result


def _scores_from_relevance_db(db_path: str) -> List[Dict[str, Any]]:
    """Read relevance_scores table (ticker, score). Returns list of {ticker, score}."""
    if not db_path or not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT ticker, score FROM relevance_scores WHERE score IS NOT NULL").fetchall()
        conn.close()
        return [{"ticker": r["ticker"], "score": _normalize_score(r["score"])} for r in rows if _normalize_score(r["score"]) is not None]
    except Exception:
        return []


def _scores_from_trait_json(path: str) -> List[Dict[str, Any]]:
    """Read trait_scores JSON; map trait_score -> score. Returns list of {ticker, name, rank, score}."""
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
        scores = data.get("scores") or []
        out = []
        for r in scores:
            ticker = (r.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            score = _normalize_score(r.get("trait_score"))
            if score is None:
                continue
            out.append({
                "ticker": r.get("ticker", ticker),
                "name": r.get("name", ticker),
                "rank": r.get("rank"),
                "score": score,
            })
        return out
    except Exception:
        return []


def _scores_from_per_prompt_json(path: str) -> List[Dict[str, Any]]:
    """Read batch_relevance_*.json scores list. Returns list of {ticker, name, rank, score}."""
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
        scores = data.get("scores") or []
        out = []
        for r in scores:
            ticker = (r.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            score = _normalize_score(r.get("score"))
            if score is None:
                continue
            out.append({
                "ticker": r.get("ticker", ticker),
                "name": r.get("name", ticker),
                "rank": r.get("rank"),
                "score": score,
            })
        return out
    except Exception:
        return []


def migrate_relevance_scores_to_unified_cache() -> None:
    """Migrate relevance scores from legacy DBs and per-prompt JSONs into the unified cache file."""
    cwd = os.getcwd()
    unified_path = os.path.join(DATA_DIR, UNIFIED_CACHE_FILENAME)
    data = {"prompts": {}}
    if os.path.exists(unified_path):
        try:
            with open(unified_path, "r") as f:
                data = json.load(f)
            if not isinstance(data.get("prompts"), dict):
                data["prompts"] = {}
        except Exception:
            data["prompts"] = {}

    prompt_keys = ["ai", "robotics", "disruptive", "tech_disruptor_ai", "tech_disruptor_ai_round", "tandem_company", "all_weather"]
    # Legacy DBs and trait JSON
    legacy_sources = {
        "ai": [("db", AI_RELEVANCE_DB)],
        "robotics": [("db", ROBOTICS_RELEVANCE_DB)],
        "disruptive": [("trait_json", TRAIT_SCORES_JSON)],
        "tech_disruptor_ai": [],
        "tech_disruptor_ai_round": [],
        "tandem_company": [],
        "all_weather": [],
    }
    # Per-prompt JSON paths (data dir, cwd, cwd/data)
    for key in prompt_keys:
        for base in [DATA_DIR, cwd, os.path.join(cwd, "data")]:
            if base and os.path.isdir(base):
                legacy_sources[key].append(("per_prompt", os.path.join(base, f"batch_relevance_{key}.json")))

    for prompt_key in prompt_keys:
        # Existing unified section (ticker -> row); first source wins
        merged = {}
        existing = (data.get("prompts") or {}).get(prompt_key) or {}
        for r in (existing.get("scores") or []):
            ticker = (r.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            score = _normalize_score(r.get("score"))
            if score is not None:
                merged[ticker] = {"ticker": r.get("ticker", ticker), "name": r.get("name", ticker), "rank": r.get("rank"), "score": score}

        # Legacy DB (ai, robotics)
        for kind, path in legacy_sources.get(prompt_key, []):
            if kind == "db":
                for row in _scores_from_relevance_db(path):
                    t = (row.get("ticker") or "").strip().upper()
                    if t and t not in merged:
                        merged[t] = {"ticker": row.get("ticker", t), "name": t, "rank": None, "score": row["score"]}
            elif kind == "trait_json":
                for row in _scores_from_trait_json(path):
                    t = (row.get("ticker") or "").strip().upper()
                    if t and t not in merged:
                        merged[t] = {"ticker": row.get("ticker", t), "name": row.get("name", t), "rank": row.get("rank"), "score": row["score"]}
            elif kind == "per_prompt":
                for row in _scores_from_per_prompt_json(path):
                    t = (row.get("ticker") or "").strip().upper()
                    if t and t not in merged:
                        merged[t] = {"ticker": row.get("ticker", t), "name": row.get("name", t), "rank": row.get("rank"), "score": row["score"]}

        if not merged:
            continue

        # Fill names from top_companies where missing or same as ticker
        need_names = [t for t, row in merged.items() if (row.get("name") or "").strip() in ("", row.get("ticker", t))]
        if need_names:
            names = _get_ticker_names(need_names)
            for t, name in names.items():
                if t in merged and merged[t].get("name") in ("", t, merged[t].get("ticker")):
                    merged[t]["name"] = name

        # Sort by score desc, then ticker; assign rank
        def _rank_key(row):
            return (-(row["score"] or 0), (row.get("ticker") or "").upper())
        sorted_rows = sorted(merged.values(), key=_rank_key)
        for i, row in enumerate(sorted_rows):
            row["rank"] = i + 1
        scores_list = sorted_rows

        # Preserve token/cost from existing section or default to 0
        prev_pt = int(existing.get("total_prompt_tokens", 0) or 0)
        prev_ct = int(existing.get("total_completion_tokens", 0) or 0)
        cost = float(existing.get("cost_usd", 0) or 0)
        prompt_name = existing.get("prompt_name") or next((p["name"] for p in RELEVANCE_PROMPTS if p["key"] == prompt_key), prompt_key)
        data.setdefault("prompts", {})[prompt_key] = {
            "scores": scores_list,
            "total_prompt_tokens": prev_pt,
            "total_completion_tokens": prev_ct,
            "cost_usd": round(cost, 4),
            "updated": existing.get("updated") or datetime.utcnow().isoformat() + "Z",
            "filter_min_confidence": existing.get("filter_min_confidence"),
            "filter_min_market_cap_billions": existing.get("filter_min_market_cap_billions"),
            "prompt_name": prompt_name,
            "model": existing.get("model") or MODEL,
        }

    if data.get("prompts"):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(unified_path, "w") as f:
            json.dump(data, f, indent=2)


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


def _is_rate_limit_error(e: Exception) -> bool:
    if getattr(e, "status_code", None) == 429:
        return True
    msg = (getattr(e, "message", "") or str(e) or "").lower()
    return "429" in msg or "rate limit" in msg or "too many requests" in msg


def load_api_key() -> Optional[str]:
    key = os.getenv("OPENROUTER_KEY")
    if key:
        return key
    try:
        import config
        return getattr(config, "OPENROUTER_KEY", None)
    except ImportError:
        return None


def _reasoning_from_details(details: Any) -> Optional[str]:
    """Build reasoning text from OpenRouter reasoning_details array."""
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


def call_mimo(api_key: str, prompt: str, *, enable_reasoning: bool = False) -> Tuple[Optional[str], Dict[str, Any]]:
    """Call Mimo via OpenRouter. Returns (content, usage_dict). On 429, usage has rate_limited=True.
    When enable_reasoning=True, requests reasoning then score; usage may include "reasoning_text" for token split.
    """
    client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    system = SYSTEM_HINT_REASON_THEN_SCORE if enable_reasoning else SYSTEM_HINT
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    kwargs = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 8192 if enable_reasoning else 16,
    }
    if enable_reasoning:
        kwargs["extra_body"] = {"reasoning": {"enabled": True, "effort": "high"}}
    try:
        resp = client.chat.completions.create(**kwargs)
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
        }
    content = None
    reasoning_text = None
    if resp.choices:
        msg = resp.choices[0].message
        content = getattr(msg, "content", None)
        if not content:
            content = getattr(msg, "reasoning_content", None)
        if enable_reasoning:
            reasoning_text = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
            if reasoning_text is None:
                reasoning_text = _reasoning_from_details(getattr(msg, "reasoning_details", None))
            if content and str(content).strip() == (str(reasoning_text).strip() if reasoning_text else ""):
                reasoning_text = None
        if content:
            content = str(content).strip()
    if reasoning_text:
        usage["reasoning_text"] = str(reasoning_text).strip()
    return content, usage


def _rate_one(
    args: Tuple[Dict[str, Any], str, str, Any, bool],
) -> Tuple[str, Dict[str, Any], int, int]:
    """Worker: rate one stock. Returns (ticker, result_dict, prompt_tokens, completion_tokens). On rate limit, result has rate_limited=True."""
    row, api_key, prompt_template, rate_limiter, enable_reasoning = args
    ticker = row["ticker"].upper()
    name = row.get("name") or ticker
    prompt = prompt_template.format(company_name=name, ticker=ticker)
    rate_limiter.wait_if_needed()
    pt, ct = 0, 0
    try:
        content, usage = call_mimo(api_key, prompt, enable_reasoning=enable_reasoning)
        if usage.get("rate_limited"):
            return ticker, {"ticker": ticker, "name": name, "rank": row.get("rank"), "score": None, "rate_limited": True}, 0, 0
        score = parse_score(content) if content else None
        pt = usage.get("prompt_tokens", 0)
        ct = usage.get("completion_tokens", 0)
        result = {"ticker": ticker, "name": name, "rank": row.get("rank"), "score": score}
        if enable_reasoning and ct and usage.get("reasoning_text") is not None:
            reasoning_chars = len(usage["reasoning_text"])
            output_chars = len(content or "")
            total_chars = reasoning_chars + output_chars
            if total_chars > 0:
                rt = round(ct * reasoning_chars / total_chars)
                ot = ct - rt
                result["_rt"], result["_ot"] = rt, ot
        return ticker, result, pt, ct
    except Exception as e:
        if _is_rate_limit_error(e):
            return ticker, {"ticker": ticker, "name": name, "rank": row.get("rank"), "score": None, "rate_limited": True}, 0, 0
        return ticker, {"ticker": ticker, "name": name, "rank": row.get("rank"), "score": None, "error": str(e)}, pt, ct


def main():
    api_key = load_api_key()
    if not api_key:
        print("Error: OPENROUTER_KEY not set (config.py or environment).")
        sys.exit(1)

    migrate_relevance_scores_to_unified_cache()

    print("Batch relevance scoring – all stocks (score only)")
    print("Select which prompt to run, then set filter criteria. You'll see estimated cost and confirm before run.\n")

    # --- Prompt choice ---
    print("Select score / prompt:")
    for i, p in enumerate(RELEVANCE_PROMPTS, 1):
        print(f"  {i}. {p['name']}")
    print("  q. Quit")
    try:
        choice = input(f"\nChoice (1–{len(RELEVANCE_PROMPTS)} or q): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nBye.")
        sys.exit(0)
    if choice in ("q", "quit", ""):
        print("Bye.")
        sys.exit(0)
    idx = None
    try:
        idx = int(choice)
        if 1 <= idx <= len(RELEVANCE_PROMPTS):
            idx -= 1
        else:
            idx = None
    except ValueError:
        pass
    if idx is None:
        print(f"Invalid choice. Enter 1–{len(RELEVANCE_PROMPTS)} or q.")
        sys.exit(1)

    score_def = RELEVANCE_PROMPTS[idx]
    print(f"\nSelected: {score_def['name']} ({score_def['key']})\n")
    # Show the prompt (with example placeholders)
    example_prompt = score_def["prompt"].format(company_name="Example Corp", ticker="AAPL")
    print("Prompt (example with company_name=Example Corp, ticker=AAPL):")
    print("-" * 60)
    print(example_prompt)
    print("-" * 60)

    # --- Filter: AI confidence ---
    print("Filter: include only stocks where AI confidence score (ai_knowledge_score, 0–10) is >= ?")
    print("  (e.g. 5 = same as Disruptive Innovators run)")
    try:
        conf_str = input("AI confidence >= [default 0]: ").strip() or "0"
        min_confidence = float(conf_str)
    except (ValueError, EOFError, KeyboardInterrupt):
        min_confidence = 0.0
    if min_confidence < 0:
        min_confidence = 0.0
    if min_confidence > 10:
        min_confidence = 10.0

    # --- Filter: Market cap ---
    print("\nFilter: include only stocks where market cap (USD) is >= ?")
    print("  Enter value in billions (e.g. 1 = $1B, 0.5 = $500M)")
    try:
        cap_str = input("Market cap (billions) >= [default 0]: ").strip() or "0"
        cap_billions = float(cap_str)
    except (ValueError, EOFError, KeyboardInterrupt):
        cap_billions = 0.0
    if cap_billions < 0:
        cap_billions = 0.0
    min_market_cap_usd = cap_billions * 1e9

    # --- Load filtered list ---
    stocks = get_stocks_filtered(min_confidence, min_market_cap_usd)
    if not stocks:
        print(f"\nNo stocks found with AI confidence >= {min_confidence} and market cap >= ${min_market_cap_usd/1e9:.2f}B.")
        sys.exit(1)

    # --- Output file and cache (skip tickers we already have a score for) ---
    os.makedirs(DATA_DIR, exist_ok=True)
    out_file = os.path.join(DATA_DIR, f"batch_relevance_{score_def['key']}.json")
    out_file_abs = os.path.abspath(out_file)
    cache_filename = f"batch_relevance_{score_def['key']}.json"
    cwd = os.getcwd()
    fallback_paths = [
        os.path.join(cwd, cache_filename),
        os.path.join(cwd, "data", cache_filename),
    ]
    unified_path = os.path.join(DATA_DIR, UNIFIED_CACHE_FILENAME)
    cache, prev_prompt_tokens, prev_completion_tokens, path_loaded = load_cache(
        score_def["key"], out_file, fallback_paths, data_dir=DATA_DIR
    )
    if path_loaded:
        path_loaded_abs = os.path.abspath(path_loaded)
        print(f"\nCache file: {path_loaded_abs}")
        if path_loaded_abs != out_file_abs and os.path.basename(path_loaded) != UNIFIED_CACHE_FILENAME:
            print(f"  (loaded from fallback; will save to unified + canonical per-prompt)")
        print(f"  Loaded {len(cache)} cached scores (valid 0-100).")
    else:
        print(f"\nCache file: {os.path.abspath(unified_path)} (not found; will create on save)")
        print(f"  (also checked: {unified_path}, {os.path.join(cwd, cache_filename)}, {os.path.join(cwd, 'data', cache_filename)})")
    to_fetch = [row for row in stocks if row["ticker"].upper() not in cache]
    cached_count = len(stocks) - len(to_fetch)

    n = len(to_fetch)
    prompt_template = score_def.get("prompt") or ""
    input_tokens_per_request = estimate_prompt_tokens(prompt_template) if prompt_template else 320
    is_reason_then_score = score_def.get("key") == REASON_THEN_SCORE_PROMPT_KEY
    output_tokens_per_request = EST_OUTPUT_TOKENS_REASON_THEN_SCORE if is_reason_then_score else None
    cost_est, est_in, est_out = estimate_cost_usd(
        n,
        input_tokens_per_request=input_tokens_per_request,
        output_tokens_per_request=output_tokens_per_request,
    )
    print(f"\nStocks passing filter: {len(stocks)}")
    print(f"  Already have score (cached): {cached_count}")
    print(f"  To score now: {n}")
    print(f"  (AI confidence >= {min_confidence}, market cap >= ${min_market_cap_usd/1e9:.2f}B)")
    if n > 0:
        out_label = "output (incl. reasoning)" if is_reason_then_score else "output"
        print(f"Estimated tokens: ~{est_in} input, ~{est_out} {out_label}")
        print(f"Estimated cost:   ${cost_est:.2f} USD (at ${INPUT_COST_PER_1M}/1M in, ${OUTPUT_COST_PER_1M}/1M out)")
    print("\nProceed with this run? (y/n)")
    try:
        confirm = input("Run? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        sys.exit(0)
    if confirm not in ("y", "yes"):
        print("Cancelled.")
        sys.exit(0)

    # --- Run: threaded with rate limiting; on 429 pause 60s and retry wave
    rpm = int(os.getenv("OPENROUTER_RPM", REQUESTS_PER_MINUTE_DEFAULT))
    rate_limiter = RateLimiter(rpm)
    merged = dict(cache)
    total_prompt = 0
    total_completion = 0
    total_reasoning = 0
    done = 0
    print(f"Using {MAX_WORKERS} workers" + (f", rate limit {rpm} req/min" if rpm > 0 else " (no rate limit)") + ".\n")
    print_lock = threading.Lock()
    save_lock = threading.Lock()

    def save_progress():
        stock_tickers_set = {row["ticker"].upper() for row in stocks}
        scores_list = [merged[row["ticker"].upper()] for row in stocks if row["ticker"].upper() in merged]
        for t in sorted(merged):
            if t not in stock_tickers_set:
                scores_list.append(merged[t])
        total_pt = prev_prompt_tokens + total_prompt
        total_ct = prev_completion_tokens + total_completion
        cost_usd = (total_pt / 1e6 * INPUT_COST_PER_1M) + (total_ct / 1e6 * OUTPUT_COST_PER_1M)
        out = {
            "updated": datetime.utcnow().isoformat() + "Z",
            "prompt_key": score_def["key"],
            "prompt_name": score_def["name"],
            "model": MODEL,
            "filter_min_confidence": min_confidence,
            "filter_min_market_cap_billions": min_market_cap_usd / 1e9,
            "total_stocks": len(scores_list),
            "total_prompt_tokens": total_pt,
            "total_completion_tokens": total_ct,
            "cost_usd": round(cost_usd, 4),
            "scores": scores_list,
        }
        with open(out_file, "w") as f:
            json.dump(out, f, indent=2)
        _save_unified_section(unified_path, score_def["key"], out)
        _write_relevance_scores_to_db(score_def["key"], scores_list)

    pending = list(to_fetch)
    while pending:
        enable_reasoning = score_def["key"] == REASON_THEN_SCORE_PROMPT_KEY
        task_args = [(row, api_key, score_def["prompt"], rate_limiter, enable_reasoning) for row in pending]
        retry_list: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_rate_one, a): a for a in task_args}
            for future in as_completed(futures):
                task_arg = futures[future]
                row = task_arg[0]
                try:
                    ticker, result, pt, ct = future.result()
                except Exception as e:
                    ticker = row["ticker"].upper()
                    result = {"ticker": ticker, "name": row.get("name") or ticker, "rank": row.get("rank"), "score": None, "error": str(e)}
                    pt, ct = 0, 0
                    with print_lock:
                        print(f"  {done + 1}/{n}  {ticker}  ERROR: {e}")
                if result.get("rate_limited"):
                    retry_list.append(row)
                    continue
                merged[ticker] = result
                total_prompt += pt
                total_completion += ct
                done += 1
                score = result.get("score")
                score_int = _normalize_score(score)
                if score_int is not None:
                    _insert_one_relevance_score(score_def["key"], ticker, score_int)
                if "_rt" in result:
                    total_reasoning += result["_rt"]
                with print_lock:
                    rt, ot = result.pop("_rt", None), result.pop("_ot", None)
                    if rt is not None and ot is not None:
                        print(f"  {done}/{n}  {ticker}  {score if score is not None else '—'}  ({pt} in | {rt} reasoning | {ot} out)")
                    else:
                        print(f"  {done}/{n}  {ticker}  {score if score is not None else '—'}  ({pt}+{ct} tok)")
                if done % 50 == 0 or done == n:
                    with save_lock:
                        save_progress()
        if retry_list:
            with print_lock:
                print(f"\n  Rate limit hit. {len(retry_list)} request(s) will retry. Pausing 60s...")
            time.sleep(60)
            pending = retry_list
        else:
            break

    # --- Build scores list: current run's stocks in order, then any other cached tickers ---
    stock_tickers = {row["ticker"].upper() for row in stocks}
    scores_list = [merged[row["ticker"].upper()] for row in stocks]
    for t in sorted(merged):
        if t not in stock_tickers:
            scores_list.append(merged[t])

    # --- Save (cumulative token totals if we had previous run) ---
    total_prompt_all = prev_prompt_tokens + total_prompt
    total_completion_all = prev_completion_tokens + total_completion
    actual_cost_this_run = (total_prompt / 1e6 * INPUT_COST_PER_1M) + (total_completion / 1e6 * OUTPUT_COST_PER_1M)
    total_cost_usd = (total_prompt_all / 1e6 * INPUT_COST_PER_1M) + (total_completion_all / 1e6 * OUTPUT_COST_PER_1M)
    out = {
        "updated": datetime.utcnow().isoformat() + "Z",
        "prompt_key": score_def["key"],
        "prompt_name": score_def["name"],
        "model": MODEL,
        "filter_min_confidence": min_confidence,
        "filter_min_market_cap_billions": min_market_cap_usd / 1e9,
        "total_stocks": len(scores_list),
        "total_prompt_tokens": total_prompt_all,
        "total_completion_tokens": total_completion_all,
        "cost_usd": round(total_cost_usd, 4),
        "scores": scores_list,
    }
    with open(out_file, "w") as f:
        json.dump(out, f, indent=2)
    _save_unified_section(unified_path, score_def["key"], out)
    _write_relevance_scores_to_db(score_def["key"], scores_list)
    db_path = os.path.join(DB_DIR, f"{score_def['key']}_relevance_scores.db")
    print(f"\nSaved to DB {db_path} ({len(scores_list)} rows), and to JSON {out_file} / unified {unified_path}")
    is_reason_run = score_def["key"] == REASON_THEN_SCORE_PROMPT_KEY and total_reasoning > 0
    if is_reason_run:
        total_output = total_completion - total_reasoning
        print(f"This run: ${actual_cost_this_run:.4f}  ({total_prompt} in | {total_reasoning} reasoning | {total_output} out)")
    else:
        print(f"This run: ${actual_cost_this_run:.4f}  ({total_prompt} in, {total_completion} out)")
    if prev_prompt_tokens or prev_completion_tokens:
        print(f"Cumulative in file: ${total_cost_usd:.4f}  ({total_prompt_all} in, {total_completion_all} out)")


if __name__ == "__main__":
    main()
