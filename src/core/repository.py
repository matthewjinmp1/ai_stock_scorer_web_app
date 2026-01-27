import sqlite3
import os
from typing import List, Dict, Any, Optional
from src.core.settings import TOP_SCORES_DB, TOP_COMPANIES_DB, PEERS_DB

class CompanyRepository:
    """Repository for accessing company and score data."""
    
    @staticmethod
    def get_db_connection(db_path: str):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def get_latest_scores(cls, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches the latest scores for all companies, optionally filtered by search."""
        conn = cls.get_db_connection(TOP_SCORES_DB)
        
        base_query = """
            SELECT s1.*
            FROM scores s1
            JOIN (
                SELECT ticker, MAX(timestamp) as max_ts
                FROM scores
                GROUP BY ticker
            ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
        """
        
        params = []
        if search_query:
            search_upper = search_query.strip().upper()
            
            # Check for exact ticker match first
            exact_ticker_check = conn.execute(f"{base_query} WHERE UPPER(s1.ticker) = ? LIMIT 1", (search_upper,)).fetchone()
            
            if exact_ticker_check:
                query = f"{base_query} WHERE UPPER(s1.ticker) = ?"
                params = [search_upper]
            else:
                search_prefix = f"{search_upper}%"
                query = f"{base_query} WHERE s1.ticker LIKE ? OR UPPER(s1.company_name) LIKE ?"
                params = [search_prefix, search_prefix]
        else:
            query = base_query
            
        query += " ORDER BY s1.total_score DESC"
        
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @classmethod
    def get_all_latest_scores_only(cls) -> List[float]:
        """Returns a sorted list of all latest total scores for percentile calculations."""
        conn = cls.get_db_connection(TOP_SCORES_DB)
        query = """
            SELECT total_score
            FROM scores s1
            JOIN (
                SELECT ticker, MAX(timestamp) as max_ts
                FROM scores
                GROUP BY ticker
            ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
        """
        rows = conn.execute(query).fetchall()
        conn.close()
        return sorted([float(row['total_score']) for row in rows])

    @classmethod
    def get_company_detail(cls, ticker: str) -> Optional[Dict[str, Any]]:
        """Returns the latest score record for a specific ticker."""
        conn = cls.get_db_connection(TOP_SCORES_DB)
        query = "SELECT * FROM scores WHERE ticker = ? ORDER BY timestamp DESC LIMIT 1"
        row = conn.execute(query, (ticker.upper(),)).fetchone()
        conn.close()
        return dict(row) if row else None

    @classmethod
    def get_company_history(cls, ticker: str) -> List[Dict[str, Any]]:
        """Returns the full historical scores for a specific ticker."""
        conn = cls.get_db_connection(TOP_SCORES_DB)
        query = "SELECT * FROM scores WHERE ticker = ? ORDER BY timestamp DESC"
        rows = conn.execute(query, (ticker.upper(),)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    @classmethod
    def get_total_company_count(cls) -> int:
        """Returns total count of unique companies analyzed."""
        conn = cls.get_db_connection(TOP_SCORES_DB)
        query = """
            SELECT COUNT(DISTINCT ticker)
            FROM scores
        """
        count = conn.execute(query).fetchone()[0]
        conn.close()
        return count

    @classmethod
    def get_company_metadata(cls, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
        """Returns metadata (name, rank) for a list of tickers."""
        if not tickers:
            return {}
            
        conn = cls.get_db_connection(TOP_COMPANIES_DB)
        placeholders = ','.join(['?' for _ in tickers])
        query = f"SELECT ticker, name, rank FROM companies_metadata WHERE ticker IN ({placeholders})"
        rows = conn.execute(query, tickers).fetchall()
        conn.close()
        return {row['ticker']: dict(row) for row in rows}

    @classmethod
    def get_peers(cls, ticker: str) -> List[str]:
        """Returns list of peer names for a given ticker."""
        if not os.path.exists(PEERS_DB):
            return []
        conn = cls.get_db_connection(PEERS_DB)
        query = 'SELECT DISTINCT peer_name FROM company_peers WHERE ticker = ? ORDER BY peer_name'
        rows = conn.execute(query, (ticker.upper(),)).fetchall()
        conn.close()
        return [row['peer_name'] for row in rows]
