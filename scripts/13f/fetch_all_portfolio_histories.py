#!/usr/bin/env python3
"""
Fetch 13F portfolio history for ALL funds from the filers database.
Records any errors encountered in a JSON file.
Optimized for speed using concurrency and batch processing.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure project root is in path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests
from src.core import sec_api

class SECRateLimiter:
    """Rate limiter to stay under 10 req/s across all threads."""
    def __init__(self, req_per_sec=9):
        self.delay = 1.0 / req_per_sec
        self.lock = threading.Lock()
        self.last_req_time = 0

    def wait(self):
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_req_time
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self.last_req_time = time.time()

# SEC limit is 10, we'll use 9.5 to be safe
rate_limiter = SECRateLimiter(req_per_sec=9.5)

def init_database(db_path: str) -> None:
    """Initialize the portfolio history database schema."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS filings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cik TEXT NOT NULL,
            fund_name TEXT NOT NULL,
            form TEXT,
            filing_date TEXT,
            report_date TEXT,
            accession TEXT UNIQUE NOT NULL,
            info_table_file TEXT,
            holdings_count INTEGER,
            fetch_date TEXT,
            UNIQUE(cik, accession)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filing_id INTEGER NOT NULL,
            report_date TEXT,
            name_of_issuer TEXT,
            title_of_class TEXT,
            cusip TEXT,
            value TEXT,
            ssh_prnamt TEXT,
            ssh_prnamt_type TEXT,
            put_call TEXT,
            investment_discretion TEXT,
            FOREIGN KEY (filing_id) REFERENCES filings(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_filings_cik ON filings(cik)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_filings_accession ON filings(accession)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_filings_report_date ON filings(report_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_filing_id ON holdings(filing_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_report_date ON holdings(report_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_cusip ON holdings(cusip)")
    
    conn.commit()
    conn.close()

def save_to_database(
    db_path: str,
    cik: str,
    fund_name: str,
    filings_data: List[dict],
    existing_accessions: set
) -> None:
    """Save portfolio history to database using batch inserts."""
    if not filings_data:
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    fetch_date = datetime.now().isoformat()
    
    for filing_data in filings_data:
        accession = filing_data["accession"]
        if not accession or accession in existing_accessions:
            continue
            
        cursor.execute("""
            INSERT INTO filings 
            (cik, fund_name, form, filing_date, report_date, accession, 
             info_table_file, holdings_count, fetch_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cik,
            fund_name,
            filing_data.get("form"),
            filing_data.get("filing_date"),
            filing_data.get("report_date"),
            accession,
            filing_data.get("info_table_file"),
            filing_data.get("holdings_count", 0),
            fetch_date
        ))
        filing_id = cursor.lastrowid
        existing_accessions.add(accession)
        
        report_date = filing_data.get("report_date")
        holdings = filing_data.get("holdings", [])
        if holdings:
            holdings_rows = [
                (filing_id, report_date, h.get("nameOfIssuer"), h.get("titleOfClass"), 
                 h.get("cusip"), h.get("value"), h.get("sshPrnamt"), 
                 h.get("sshPrnamtType"), h.get("putCall"), h.get("investmentDiscretion"))
                for h in holdings
            ]
            cursor.executemany("""
                INSERT INTO holdings 
                (filing_id, report_date, name_of_issuer, title_of_class, cusip, value,
                 ssh_prnamt, ssh_prnamt_type, put_call, investment_discretion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, holdings_rows)
    
    conn.commit()
    conn.close()

def fetch_single_filing(session, cik_10, f, idx, total_new):
    """Worker function to fetch and parse a single filing."""
    try:
        rate_limiter.wait()
        index_json, base_url = sec_api.get_filing_index_json(session, cik_10, f.accession)
        
        info_fn = sec_api.pick_info_table_file(index_json)
        if not info_fn:
            return None, {"type": "no_info_table", "accession": f.accession}
        
        info_url = f"{base_url}/{info_fn}"
        
        rate_limiter.wait()
        txt = sec_api.http_get_text(session, info_url)
        
        holdings = []
        if info_fn.lower().endswith(".xml"):
            holdings = sec_api.parse_infotable_xml(txt)
        elif info_fn.lower().endswith(".txt"):
            holdings = sec_api.parse_infotable_txt(txt)
        else:
            return None, {"type": "unknown_format", "accession": f.accession}
            
        print(f"    ✓ [{idx}/{total_new}] Parsed {len(holdings)} holdings for {f.accession}")
        
        return {
            "cik": cik_10,
            "form": f.form,
            "filing_date": f.filing_date,
            "report_date": f.report_date,
            "accession": f.accession,
            "info_table_file": info_fn,
            "holdings_count": len(holdings),
            "holdings": holdings,
        }, None
    except Exception as e:
        return None, {"type": "fetch_error", "accession": f.accession, "error": str(e)}

def fetch_fund_portfolio_history(
    cik_10: str,
    fund_name: str,
    limit: Optional[int],
    existing_accessions: set,
    session: requests.Session
) -> Dict:
    """Fetch a fund's history using parallel workers."""
    fund_errors = []
    results = []
    
    try:
        rate_limiter.wait()
        submissions = sec_api.get_submissions(session, cik_10)
    except Exception as e:
        return {"results": results, "errors": [{"type": "submissions_error", "error": str(e)}]}
    
    actual_fund_name = submissions.get("name") or fund_name
    filings = sec_api.extract_13f_filings(submissions)
    
    if limit is not None:
        filings = filings[:limit]
    
    new_filings = [f for f in filings if f.accession and f.accession not in existing_accessions]
    
    if not new_filings:
        print(f"  ✓ Found {len(filings)} filings (0 new, all already in DB)")
        return {"results": [], "errors": [], "fund_name": actual_fund_name}

    print(f"  Found {len(filings)} filings ({len(new_filings)} new). Fetching in parallel...")
    
    # Use ThreadPool to fetch filings in parallel
    # 5 workers is a good balance to stay under the 10 req/s limit with rate_limiter
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(fetch_single_filing, session, cik_10, f, idx, len(new_filings)) 
            for idx, f in enumerate(new_filings, 1)
        ]
        
        for future in as_completed(futures):
            res, err = future.result()
            if res:
                res["fund_name"] = actual_fund_name
                results.append(res)
            if err:
                fund_errors.append(err)
                
    return {"results": results, "errors": fund_errors, "fund_name": actual_fund_name}

def load_funds_from_database(filers_db_path: str, offset: int = 0, limit: Optional[int] = None) -> List[Dict]:
    """Load funds from the filers database."""
    conn = sqlite3.connect(filers_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    query = "SELECT cik, name FROM filers ORDER BY name"
    if limit: query += f" LIMIT {limit} OFFSET {offset}"
    elif offset: query += f" LIMIT -1 OFFSET {offset}"
    cursor.execute(query)
    funds = [{"cik": row["cik"], "name": row["name"]} for row in cursor.fetchall()]
    conn.close()
    return funds

def load_existing_accessions(db_path: str) -> set:
    """Pre-load all existing accessions for fast lookup."""
    if not os.path.exists(db_path): return set()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT accession FROM filings")
    accessions = {row[0] for row in cursor.fetchall()}
    conn.close()
    return accessions

def save_errors(errors: Dict, errors_path: str) -> None:
    os.makedirs(os.path.dirname(errors_path), exist_ok=True)
    with open(errors_path, "w") as f:
        json.dump(errors, f, indent=2)

def main() -> int:
    sec_api.load_local_env()
    print("=" * 60)
    print("13F Portfolio History Fetcher - OPTIMIZED")
    print("=" * 60)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filers_db = os.path.join(script_dir, "data", "filers.db")
    portfolio_db = os.path.join(script_dir, "data", "portfolio_history.db")
    errors_path = os.path.join(script_dir, "data", "fetch_errors.json")
    
    parser = argparse.ArgumentParser(description="Fetch 13F portfolio history. Default: first 1000 funds. Use --fund-limit 0 for all.")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--fund-limit", type=int, default=1000, help="Max funds to process (0 = all). Default 1000 for testing.")
    parser.add_argument("--filings-limit", type=int, default=None)
    args = parser.parse_args()
    
    init_database(portfolio_db)
    existing_accessions = load_existing_accessions(portfolio_db)
    fund_limit = None if args.fund_limit == 0 else args.fund_limit
    funds = load_funds_from_database(filers_db, offset=args.offset, limit=fund_limit)
    
    if not funds:
        print("No funds found.")
        return 1
    
    all_errors = {"fetch_date": datetime.now().isoformat(), "errors_by_fund": {}, "funds_processed": 0}
    session = requests.Session()
    total_filings = 0
    total_holdings = 0
    
    for idx, fund in enumerate(funds, 1):
        cik, name = fund["cik"], fund["name"]
        print(f"[{idx}/{len(funds)}] Processing {name} (CIK {cik})")
        
        try:
            result = fetch_fund_portfolio_history(cik, name, args.filings_limit, existing_accessions, session)
            filings_data = result.get("results", [])
            fund_errors = result.get("errors", [])
            
            if filings_data:
                save_to_database(portfolio_db, cik, result["fund_name"], filings_data, existing_accessions)
                total_filings += len(filings_data)
                total_holdings += sum(f["holdings_count"] for f in filings_data)
                print(f"  ✓ Saved {len(filings_data)} filings, {sum(f['holdings_count'] for f in filings_data)} holdings")
            
            if fund_errors:
                all_errors["errors_by_fund"][cik] = {"name": name, "errors": fund_errors}
                
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}", file=sys.stderr)
            all_errors["errors_by_fund"][cik] = {"name": name, "errors": [str(e)]}
        
        all_errors["funds_processed"] += 1
        if idx % 10 == 0:
            save_errors(all_errors, args.errors if hasattr(args, 'errors') else errors_path)
            
    print(f"\nFinished. Total: {total_filings} filings, {total_holdings} holdings.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
