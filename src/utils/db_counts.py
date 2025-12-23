import sqlite3
import os
import sys

# Define the project root relative to this script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "scores.db")

def show_db_counts():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Query to count rows per ticker and sort by count descending
        query = """
            SELECT ticker, COUNT(*) as row_count 
            FROM scores 
            GROUP BY ticker 
            ORDER BY row_count DESC
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            print("The database is empty.")
            return

        print(f"\nDatabase Row Counts per Ticker (Total unique: {len(rows)})")
        print("=" * 35)
        print(f"{'Ticker':<12} | {'Number of Rows':<15}")
        print("-" * 35)
        
        total_rows = 0
        for ticker, count in rows:
            print(f"{ticker:<12} | {count:<15}")
            total_rows += count
            
        print("-" * 35)
        print(f"{'TOTAL':<12} | {total_rows:<15}")
        print("=" * 35)
        
        conn.close()
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    show_db_counts()

