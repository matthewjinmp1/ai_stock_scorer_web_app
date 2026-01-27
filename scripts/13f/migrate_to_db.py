import sqlite3
import json
import os
import sys

# Define paths
_script_dir = os.path.dirname(os.path.abspath(__file__))
_json_path = os.path.join(_script_dir, "data", "raw", "13f_filers_sec_simple.json")
_db_path = os.path.join(_script_dir, "data", "filers.db")

def migrate():
    if not os.path.exists(_json_path):
        print(f"Error: JSON file not found at {_json_path}")
        return

    print(f"Reading data from {_json_path}...")
    with open(_json_path, 'r') as f:
        filers = json.load(f)

    print(f"Connecting to database at {_db_path}...")
    os.makedirs(os.path.dirname(_db_path), exist_ok=True)
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()

    # Create table with FTS (Full Text Search) for super fast searching
    cursor.execute("DROP TABLE IF EXISTS filers")
    cursor.execute("""
        CREATE TABLE filers (
            cik TEXT PRIMARY KEY,
            name TEXT,
            total_13f_filings INTEGER,
            most_recent_filing_date TEXT
        )
    """)
    
    # Create an index for name searching
    cursor.execute("CREATE INDEX idx_filer_name ON filers(name)")

    print(f"Inserting {len(filers)} records...")
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
    print("Migration complete!")

if __name__ == "__main__":
    migrate()

