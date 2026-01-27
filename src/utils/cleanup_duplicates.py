#!/usr/bin/env python3
"""
Script to clean up duplicate rows in scores.db.
Keeps only the most recent entry for each ticker+model pair.
"""

import sqlite3
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db_manager import DBManager

def cleanup_duplicates(db_path):
    """Remove duplicate rows, keeping only the most recent for each ticker+model pair."""
    print(f"Cleaning up duplicates in {db_path}...")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # First, get count of duplicates
    cursor.execute('''
        SELECT ticker, model, COUNT(*) as count 
        FROM scores 
        GROUP BY ticker, model 
        HAVING count > 1
    ''')
    duplicates = cursor.fetchall()
    
    if not duplicates:
        print("No duplicates found!")
        conn.close()
        return
    
    total_duplicates = sum(row['count'] - 1 for row in duplicates)
    print(f"Found {len(duplicates)} ticker+model pairs with duplicates")
    print(f"Total duplicate rows to remove: {total_duplicates}")
    
    # Get total rows before cleanup
    cursor.execute("SELECT COUNT(*) FROM scores")
    total_before = cursor.fetchone()[0]
    print(f"Total rows before cleanup: {total_before}")
    
    # Delete duplicates, keeping only the most recent for each ticker+model pair
    # Strategy: For each ticker+model, find the max timestamp, then keep the row with max id for that timestamp
    cursor.execute('''
        DELETE FROM scores
        WHERE id NOT IN (
            SELECT s1.id
            FROM scores s1
            INNER JOIN (
                SELECT ticker, model, MAX(timestamp) as max_ts
                FROM scores
                GROUP BY ticker, model
            ) s2 ON s1.ticker = s2.ticker 
                 AND s1.model = s2.model 
                 AND s1.timestamp = s2.max_ts
            WHERE s1.id = (
                SELECT MAX(id)
                FROM scores s3
                WHERE s3.ticker = s1.ticker
                  AND s3.model = s1.model
                  AND s3.timestamp = s1.timestamp
            )
        )
    ''')
    
    deleted_count = cursor.rowcount
    conn.commit()
    
    # Get total rows after cleanup
    cursor.execute("SELECT COUNT(*) FROM scores")
    total_after = cursor.fetchone()[0]
    
    print(f"Deleted {deleted_count} duplicate rows")
    print(f"Total rows after cleanup: {total_after}")
    print(f"Reduction: {total_before - total_after} rows ({((total_before - total_after) / total_before * 100):.1f}%)")
    
    # Verify no duplicates remain
    cursor.execute('''
        SELECT ticker, model, COUNT(*) as count 
        FROM scores 
        GROUP BY ticker, model 
        HAVING count > 1
    ''')
    remaining_duplicates = cursor.fetchall()
    
    if remaining_duplicates:
        print(f"WARNING: {len(remaining_duplicates)} duplicate pairs still remain!")
    else:
        print("✓ All duplicates removed successfully!")
    
    # Vacuum to reclaim space
    print("\nRunning VACUUM to reclaim disk space...")
    conn.execute("VACUUM")
    conn.commit()
    conn.close()
    
    print("Cleanup complete!")

if __name__ == "__main__":
    # Default to the main scores.db
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Get the default database path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(project_root, "data", "scores.db")
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)
    
    # Confirm before proceeding
    print(f"This will remove duplicate rows from: {db_path}")
    response = input("Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Aborted.")
        sys.exit(0)
    
    cleanup_duplicates(db_path)

