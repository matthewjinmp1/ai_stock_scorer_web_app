#!/usr/bin/env python3
"""
Fetch a fund's 13F portfolio history directly from the SEC.
Updated to use src.core.sec_api.
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from typing import List, Optional

# Ensure project root is in path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests
from src.core import sec_api

def init_database(db_path: str) -> None:
    """Initialize the portfolio history database schema."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create filings table
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
    
    # Create holdings table
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
    
    # Add report_date column to existing holdings table if it doesn't exist
    try:
        cursor.execute("ALTER TABLE holdings ADD COLUMN report_date TEXT")
        # Backfill report_date for existing holdings
        cursor.execute("""
            UPDATE holdings 
            SET report_date = (
                SELECT report_date FROM filings WHERE filings.id = holdings.filing_id
            )
            WHERE report_date IS NULL
        """)
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass
    
    # Create indexes for faster queries
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
    filings_data: List[dict]
) -> None:
    """Save portfolio history to database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    fetch_date = datetime.now().isoformat()
    filings_saved = 0
    holdings_saved = 0
    
    for filing_data in filings_data:
        accession = filing_data["accession"]
        if not accession:
            continue
        
        # Check if filing already exists
        cursor.execute("SELECT id FROM filings WHERE accession = ?", (accession,))
        existing = cursor.fetchone()
        
        if existing:
            filing_id = existing[0]
            # Update existing filing
            cursor.execute("""
                UPDATE filings SET
                    cik = ?, fund_name = ?, form = ?, filing_date = ?,
                    report_date = ?, info_table_file = ?, holdings_count = ?, fetch_date = ?
                WHERE id = ?
            """, (
                cik,
                fund_name,
                filing_data.get("form"),
                filing_data.get("filing_date"),
                filing_data.get("report_date"),
                filing_data.get("info_table_file"),
                filing_data.get("holdings_count", 0),
                fetch_date,
                filing_id
            ))
            # Delete existing holdings for this filing
            cursor.execute("DELETE FROM holdings WHERE filing_id = ?", (filing_id,))
        else:
            # Insert new filing
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
        
        filings_saved += 1
        
        # Get report_date for holdings
        report_date = filing_data.get("report_date")
        
        # Insert holdings
        holdings = filing_data.get("holdings", [])
        for holding in holdings:
            cursor.execute("""
                INSERT INTO holdings 
                (filing_id, report_date, name_of_issuer, title_of_class, cusip, value,
                 ssh_prnamt, ssh_prnamt_type, put_call, investment_discretion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filing_id,
                report_date,
                holding.get("nameOfIssuer"),
                holding.get("titleOfClass"),
                holding.get("cusip"),
                holding.get("value"),
                holding.get("sshPrnamt"),
                holding.get("sshPrnamtType"),
                holding.get("putCall"),
                holding.get("investmentDiscretion"),
            ))
            holdings_saved += 1
    
    conn.commit()
    conn.close()
    print(f"\nSaved to database: {filings_saved} filings, {holdings_saved} holdings")


def fetch_portfolio_history(cik_10: str, limit: Optional[int], db_path: str) -> None:
    """Fetch a fund's 13F portfolio history and save to database."""
    sec_api.load_local_env()

    session = requests.Session()
    try:
        submissions = sec_api.get_submissions(session, cik_10)
    except Exception as e:
        print(f"Error fetching submissions for CIK {cik_10}: {e}", file=sys.stderr)
        return

    fund_name = submissions.get("name") or f"Fund (CIK {cik_10})"
    filings = sec_api.extract_13f_filings(submissions)
    if limit is not None:
        filings = filings[:limit]

    print(f"\nFetching portfolio history for: {fund_name}")
    print(f"Found {len(filings)} 13F filings\n")

    results = []

    for idx, f in enumerate(filings, 1):
        print(f"[{idx}/{len(filings)}] {f.form} filed {f.filing_date} (report {f.report_date}) {f.accession}")
        if not f.accession:
            continue
        
        try:
            index_json, base_url = sec_api.get_filing_index_json(session, cik_10, f.accession)
        except Exception as e:
            print(f"  ⚠ Could not fetch index.json: {e}", file=sys.stderr)
            continue

        info_fn = sec_api.pick_info_table_file(index_json)
        if not info_fn:
            print(f"  ⚠ No info table file found in index.json ({f.accession})", file=sys.stderr)
            continue

        info_url = f"{base_url}/{info_fn}"
        try:
            txt = sec_api.http_get_text(session, info_url)
        except Exception as e:
            print(f"  ⚠ Failed to download info table: {e}", file=sys.stderr)
            continue

        holdings = []
        if info_fn.lower().endswith(".xml"):
            try:
                holdings = sec_api.parse_infotable_xml(txt)
            except Exception as e:
                print(f"  ⚠ Failed to parse XML: {e}", file=sys.stderr)
        elif info_fn.lower().endswith(".txt"):
            try:
                holdings = sec_api.parse_infotable_txt(txt)
                if holdings:
                    print(f"  ✓ Parsed {len(holdings)} holdings from text format")
            except Exception as e:
                print(f"  ⚠ Failed to parse text format: {e}", file=sys.stderr)
        else:
            print(f"  ⚠ Unknown file format: {info_fn}", file=sys.stderr)

        results.append({
                "cik": cik_10,
                "fund_name": fund_name,
                "form": f.form,
                "filing_date": f.filing_date,
                "report_date": f.report_date,
                "accession": f.accession,
                "info_table_file": info_fn,
                "holdings_count": len(holdings),
                "holdings": holdings,
        })

    # Initialize database and save data
    init_database(db_path)
    save_to_database(db_path, cik_10, fund_name, results)

def main() -> int:
    sec_api.load_local_env()
    print("=" * 60)
    print("13F Portfolio History Fetcher")
    print("=" * 60)
    
    if not os.environ.get("SEC_USER_AGENT"):
        print("Note: SEC_USER_AGENT not set. You may get 403 Forbidden errors.")
        print()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_db = os.path.join(script_dir, "data", "portfolio_history.db")

    parser = argparse.ArgumentParser(description="Fetch 13F portfolio history from SEC")
    parser.add_argument("--cik", type=str, default="0001167483", 
                       help="CIK of the fund (default: Tiger Global)")
    parser.add_argument("--limit", type=int, default=None,
                       help="Limit number of filings to fetch")
    parser.add_argument("--db", default=default_db,
                       help="Path to database file")
    args = parser.parse_args()

    limit = args.limit
    if limit is None:
            try:
            raw = input(f"How many recent 13F filings to fetch? (Enter number or 'all'): ").strip().lower()
            limit = None if raw == 'all' else int(raw)
        except (ValueError, KeyboardInterrupt):
                print("\nCancelled.")
                return 0

    fetch_portfolio_history(cik_10=args.cik, limit=limit, db_path=args.db)
    return 0

if __name__ == "__main__":
    sys.exit(main())
