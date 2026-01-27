#!/usr/bin/env python3
"""
Fetch institutional 13F filers directly from the SEC EDGAR quarterly master index.

Why this approach:
- Official SEC source (no third-party websites).
- Much faster than checking every company for 13F forms.
- We scan EDGAR's quarterly `master.idx` files and collect unique filers (CIKs)
  that submitted 13F forms (13F-HR, 13F-HR/A, 13F-NT, 13F-NT/A).

Behavior:
- Automatically scans backward (default 80 quarters / 20 years).
- Collects ALL unique filers found.
- Supports optional --limit and --quarters arguments.

Output:
- scripts/13f/data/filers.db (SQLite database)

SEC policy:
- The SEC requires a descriptive User-Agent. Set env var SEC_USER_AGENT, e.g.:
  SEC_USER_AGENT="AI_stock_scorer (your.email@example.com)"
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import requests


import random

SEC_DELAY_SECONDS = 2.0  # very conservative
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/full-index"

FORM_TYPES_13F = {"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"}


def _load_env_file(path: str) -> None:
    """
    Minimal .env loader (no external dependencies).
    Supports lines like:
      KEY=value
      KEY="value with spaces"
    Ignores blank lines and comments starting with #.
    """
    if not os.path.exists(path):
        return
    try:
        with open(path, "r") as f:
            for raw in f.readlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        # Never fail startup due to env parsing
        return


def load_local_env() -> None:
    """Load `.env` from repo root if present (for persistence without shell export)."""
    # Current file is in scripts/13f/, project root is 2 levels up
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _load_env_file(os.path.join(repo_root, ".env"))


def sec_headers() -> Dict[str, str]:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        # Still works sometimes, but SEC explicitly asks for a descriptive UA.
        ua = "AI_stock_scorer (set SEC_USER_AGENT with contact email)"
    return {
        "User-Agent": ua,
        "Accept": "text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Accept-Encoding": "gzip, deflate",
    }


def current_year_quarter(now: Optional[datetime] = None) -> Tuple[int, int]:
    now = now or datetime.utcnow()
    q = (now.month - 1) // 3 + 1
    return now.year, q


def iter_quarters_back(start_year: int, start_quarter: int) -> Iterable[Tuple[int, int]]:
    """Yield (year, quarter) starting at start_year/QTRstart_quarter, then going backward."""
    year, quarter = start_year, start_quarter
    while year >= 1993:  # EDGAR full-index goes back far; 13F in practice later
        yield year, quarter
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1


def master_index_url(year: int, quarter: int) -> str:
    return f"{SEC_ARCHIVES_BASE}/{year}/QTR{quarter}/master.idx"


@dataclass
class FilerAgg:
    cik: str
    name: str
    filings_count: int = 0
    most_recent_filing_date: str = ""

    def update(self, company_name: str, filing_date: str) -> None:
        self.filings_count += 1
        # Use the longest/most descriptive name we see (crude but works)
        if company_name and (len(company_name) > len(self.name)):
            self.name = company_name
        if filing_date and (not self.most_recent_filing_date or filing_date > self.most_recent_filing_date):
            self.most_recent_filing_date = filing_date


def download_master_idx(year: int, quarter: int, session: requests.Session) -> str:
    url = master_index_url(year, quarter)
    # Add random jitter to avoid hitting SEC limit simultaneously across multiple terminals
    sleep_time = SEC_DELAY_SECONDS + random.uniform(0, 0.5)
    time.sleep(sleep_time)
    resp = session.get(url, headers=sec_headers(), timeout=30)
    if resp.status_code == 403:
        raise PermissionError(
            "SEC returned 403 Forbidden. This is commonly caused by missing/insufficient "
            "User-Agent identification. Set SEC_USER_AGENT (ideally via a .env file) "
            "to something like: AI_stock_scorer (your.email@example.com), then rerun."
        )
    resp.raise_for_status()
    return resp.text


def parse_master_idx(text: str) -> Iterable[Tuple[str, str, str]]:
    """
    Parse master.idx returning (cik, company_name, filing_date) for 13F forms.

    master.idx format: header lines then pipe-delimited rows:
      CIK|Company Name|Form Type|Date Filed|Filename
    """
    lines = text.splitlines()
    # Data starts after a line of dashes, usually:
    # -------------------------------------------------------------------------------
    start = 0
    for i, line in enumerate(lines):
        if line.startswith("----"):
            start = i + 1
            break

    for line in lines[start:]:
        if "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        cik_raw, company_name, form_type, date_filed, _filename = parts[:5]
        form_type = form_type.strip()
        if form_type not in FORM_TYPES_13F:
            continue
        cik = str(cik_raw).strip().zfill(10)
        yield cik, company_name.strip(), date_filed.strip()


def fetch_13f_filers_from_sec(target_count: Optional[int] = None, max_quarters: int = 80) -> List[Dict]:
    """
    Scan quarterly master.idx files backwards until we collect target_count unique filers
    or hit max_quarters (default ~20 years). If target_count is None, collect ALL unique filers.
    """
    year, quarter = current_year_quarter()
    filers: Dict[str, FilerAgg] = {}

    session = requests.Session()

    scanned = 0
    for y, q in iter_quarters_back(year, quarter):
        if scanned >= max_quarters:
            break
        scanned += 1

        url = master_index_url(y, q)
        print(f"Scanning {y} QTR{q} ({url}) ...")
        try:
            txt = download_master_idx(y, q, session=session)
        except PermissionError as e:
            # No point continuing if SEC is blocking requests.
            print(f"  ✖ {e}")
            break
        except requests.HTTPError as e:
            # Some very recent quarters may not exist yet; skip.
            print(f"  ⚠ Skipping {y} QTR{q}: {e}")
            continue
        except requests.RequestException as e:
            print(f"  ⚠ Network error on {y} QTR{q}: {e}")
            continue

        added_this_quarter = 0
        for cik, name, date_filed in parse_master_idx(txt):
            if cik not in filers:
                filers[cik] = FilerAgg(cik=cik, name=name)
                added_this_quarter += 1
            filers[cik].update(name, date_filed)

        print(f"  +{added_this_quarter} new filers (total unique: {len(filers)})")

        if target_count is not None and len(filers) >= target_count:
            break

    # Sort by most recent filing date desc, then filings count desc
    ordered = sorted(
        filers.values(),
        key=lambda f: (f.most_recent_filing_date or "", f.filings_count),
        reverse=True,
    )
    if target_count is not None:
    ordered = ordered[:target_count]

    return [
        {
            "cik": f.cik,
            "name": f.name,
            "total_13f_filings": f.filings_count,
            "most_recent_filing_date": f.most_recent_filing_date,
            "source": "sec_master_idx",
        }
        for f in ordered
    ]


def write_to_database(filers: List[Dict], db_path: str) -> None:
    """Write filers to SQLite database, replacing existing data."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS filers (
            cik TEXT PRIMARY KEY,
            name TEXT,
            total_13f_filings INTEGER,
            most_recent_filing_date TEXT
        )
    """)
    
    # Create index for fast searching
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_filer_name ON filers(name)")
    
    # Clear existing data and insert new
    cursor.execute("DELETE FROM filers")
    
    data_to_insert = [
        (f['cik'], f['name'], f['total_13f_filings'], f['most_recent_filing_date'])
        for f in filers
    ]
    
    cursor.executemany(
        "INSERT INTO filers (cik, name, total_13f_filings, most_recent_filing_date) VALUES (?, ?, ?, ?)",
        data_to_insert
    )
    
    conn.commit()
    conn.close()
    print(f"\nSaved {len(filers)} filers to database: {db_path}")

def write_outputs(filers: List[Dict]) -> None:
    """Write filers to database only."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "data", "filers.db")
    write_to_database(filers, db_path)


def main() -> int:
    import argparse
    load_local_env()
    print("=" * 60)
    print("SEC 13F Filer Fetcher (from EDGAR master.idx)")
    print("=" * 60)
    print("Tip: set SEC_USER_AGENT to include your email (SEC requirement).")
    if os.environ.get("SEC_USER_AGENT"):
        print("SEC_USER_AGENT is set (from shell or .env).")
    else:
        print("SEC_USER_AGENT is NOT set. Requests may be blocked/rate-limited by SEC.")
    print()

    parser = argparse.ArgumentParser(description="Fetch institutional 13F filers from SEC EDGAR")
    parser.add_argument("--limit", type=int, default=None,
                       help="Maximum number of unique funds to collect")
    parser.add_argument("--quarters", type=int, default=80,
                       help="Number of quarters to scan backward (default: 80)")
    args = parser.parse_args()

    if args.limit:
        print(f"Collecting up to {args.limit} unique 13F filers across {args.quarters} quarters...")
    else:
        print(f"Collecting ALL unique 13F filers across {args.quarters} quarters...")

    filers = fetch_13f_filers_from_sec(target_count=args.limit, max_quarters=args.quarters)
    print(f"\nDone. Found {len(filers)} 13F filers.")
    if filers:
        print("Top 10 (most recent filing):")
        for i, f in enumerate(filers[:10], 1):
            print(f"  {i}. {f['name']} (CIK {f['cik']}) — last {f['most_recent_filing_date']}")

    write_outputs(filers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
