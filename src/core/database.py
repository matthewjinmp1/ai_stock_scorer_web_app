import sqlite3
import os
from .config import TOP_COMPANIES_DB, TOP_SCORES_DB

def get_top_100_weighted_data():
    """Join top_companies and top_scores to get tickers and their AI weights."""
    if not os.path.exists(TOP_COMPANIES_DB) or not os.path.exists(TOP_SCORES_DB):
        return []
    
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    cursor = conn.cursor()
    try:
        cursor.execute(f"ATTACH DATABASE '{TOP_SCORES_DB}' AS scores_db")
        
        query = """
            SELECT 
                c.ticker, 
                c.name, 
                s.total_score 
            FROM companies_metadata c
            JOIN scores_db.scores s ON c.ticker = s.ticker
            WHERE c.rank <= 100
            ORDER BY c.rank ASC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        return [{'ticker': r[0], 'name': r[1], 'score': r[2]} for r in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()

def get_top_scored_stocks(limit=10):
    """Fetch top scored stocks from the local database."""
    if not os.path.exists(TOP_SCORES_DB):
        return []
    
    conn = sqlite3.connect(TOP_SCORES_DB)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ticker, company_name, total_score FROM scores ORDER BY total_score DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [{'ticker': r[0], 'name': r[1], 'score': r[2]} for r in rows]
    except sqlite3.Error:
        return []
    finally:
        conn.close()
