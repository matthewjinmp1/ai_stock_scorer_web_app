#!/usr/bin/env python3
"""
Consolidate NASDAQ and NYSE JSONL files into a single SQLite database.
Only includes raw financial data.
"""

import os
import sqlite3
import json
from datetime import datetime

def migrate_jsonl_to_db():
    # Paths
    source_dir = "/Users/matthewjohnson/Downloads/stock_analysis/cursor_ignore/data"
    target_db = "/Users/matthewjohnson/Downloads/stock_analysis/AI_stock_scorer/data/financials.db"
    
    files_to_process = [
        ("nasdaq_data.jsonl", "NASDAQ"),
        ("nyse_data.jsonl", "NYSE")
    ]
    
    # Ensure target directory exists
    os.makedirs(os.path.dirname(target_db), exist_ok=True)
    
    # Initialize database
    conn = sqlite3.connect(target_db)
    cursor = conn.cursor()
    
    print(f"Initializing database at {target_db}...")
    cursor.execute("DROP TABLE IF EXISTS financials")
    cursor.execute("""
        CREATE TABLE financials (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            exchange TEXT,
            data_json TEXT,
            updated_at TEXT
        )
    """)
    
    cursor.execute("CREATE INDEX idx_financials_ticker ON financials(ticker)")
    cursor.execute("CREATE INDEX idx_financials_exchange ON financials(exchange)")
    conn.commit()
    
    total_processed = 0
    start_time = datetime.now()
    
    # Process Financials
    for filename, exchange in files_to_process:
        filepath = os.path.join(source_dir, filename)
        if not os.path.exists(filepath):
            print(f"Warning: File not found: {filepath}")
            continue
            
        print(f"Processing {filename} ({exchange})...")
        
        with open(filepath, 'r') as f:
            batch = []
            batch_size = 100
            
            for line in f:
                try:
                    record = json.loads(line)
                    ticker = record.get("symbol")
                    if not ticker:
                        continue
                        
                    company_name = record.get("company_name")
                    data_json = json.dumps(record.get("data", {}))
                    updated_at = datetime.now().isoformat()
                    
                    batch.append((ticker, company_name, exchange, data_json, updated_at))
                    
                    if len(batch) >= batch_size:
                        cursor.executemany("""
                            INSERT OR REPLACE INTO financials (ticker, company_name, exchange, data_json, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                        """, batch)
                        conn.commit()
                        total_processed += len(batch)
                        batch = []
                        
                except Exception as e:
                    print(f"Error processing line: {e}")
            
            if batch:
                cursor.executemany("""
                    INSERT OR REPLACE INTO financials (ticker, company_name, exchange, data_json, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, batch)
                conn.commit()
                total_processed += len(batch)

    end_time = datetime.now()
    duration = end_time - start_time
    
    print(f"\nMigration complete!")
    print(f"Total tickers processed: {total_processed}")
    print(f"Database location: {target_db}")
    print(f"Time taken: {duration}")
    
    conn.close()

if __name__ == "__main__":
    migrate_jsonl_to_db()
