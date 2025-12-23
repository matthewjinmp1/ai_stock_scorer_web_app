import sqlite3
import os
import re
from datetime import datetime

class DBManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _clean_score(self, value):
        """Clean score string by removing non-numeric characters except decimal points.
        Returns None if no valid number is found.
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        
        # Remove markdown bolding, etc.
        cleaned = re.sub(r'[^\d.]', '', str(value))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if we need to migrate from ticker-as-primary-key to history-based schema
            cursor.execute("PRAGMA table_info(scores)")
            columns = cursor.fetchall()
            
            needs_migration = False
            if columns:
                # Check if 'ticker' is the primary key (pk column in pragma table_info is > 0)
                for col in columns:
                    if col[1] == 'ticker' and col[5] > 0:
                        needs_migration = True
                        break
            
            if needs_migration:
                print("Migrating database schema to support historical scores...")
                cursor.execute("ALTER TABLE scores RENAME TO scores_old")
                self._create_new_table(cursor)
                cursor.execute('''
                    INSERT INTO scores (
                        ticker, company_name, moat_score, barriers_score, disruption_risk, switching_cost,
                        brand_strength, competition_intensity, network_effect,
                        product_differentiation, innovativeness_score, growth_opportunity,
                        riskiness_score, pricing_power, ambition_score,
                        bargaining_power_of_customers, bargaining_power_of_suppliers,
                        product_quality_score, culture_employee_satisfaction_score,
                        trailblazer_score, management_quality_score, ai_knowledge_score,
                        size_well_known_score, ethical_healthy_environmental_score,
                        long_term_orientation_score, model, timestamp, total_score
                    )
                    SELECT 
                        ticker, NULL, moat_score, barriers_score, disruption_risk, switching_cost,
                        brand_strength, competition_intensity, network_effect,
                        product_differentiation, innovativeness_score, growth_opportunity,
                        riskiness_score, pricing_power, ambition_score,
                        bargaining_power_of_customers, bargaining_power_of_suppliers,
                        product_quality_score, culture_employee_satisfaction_score,
                        trailblazer_score, management_quality_score, ai_knowledge_score,
                        size_well_known_score, ethical_healthy_environmental_score,
                        long_term_orientation_score, model, timestamp, total_score
                    FROM scores_old
                ''')
                cursor.execute("DROP TABLE scores_old")
                print("Migration complete.")
            else:
                self._create_new_table(cursor)
                
                # Check for company_name column if table already existed
                cursor.execute("PRAGMA table_info(scores)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'company_name' not in columns:
                    print(f"Adding company_name column to {self.db_path}...")
                    cursor.execute("ALTER TABLE scores ADD COLUMN company_name TEXT")
            
            conn.commit()

    def _create_new_table(self, cursor):
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                company_name TEXT,
                moat_score REAL,
                barriers_score REAL,
                disruption_risk REAL,
                switching_cost REAL,
                brand_strength REAL,
                competition_intensity REAL,
                network_effect REAL,
                product_differentiation REAL,
                innovativeness_score REAL,
                growth_opportunity REAL,
                riskiness_score REAL,
                pricing_power REAL,
                ambition_score REAL,
                bargaining_power_of_customers REAL,
                bargaining_power_of_suppliers REAL,
                product_quality_score REAL,
                culture_employee_satisfaction_score REAL,
                trailblazer_score REAL,
                management_quality_score REAL,
                ai_knowledge_score REAL,
                size_well_known_score REAL,
                ethical_healthy_environmental_score REAL,
                long_term_orientation_score REAL,
                model TEXT,
                timestamp TEXT,
                total_score REAL
            )
        ''')
        # Create an index on ticker and timestamp for faster lookups of latest scores
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ticker_timestamp ON scores (ticker, timestamp DESC)")

    def save_score(self, ticker, scores_dict, company_name=None):
        """
        Save a company's scores as a new entry (preserves history).
        scores_dict should contain all metric keys and 'model' and 'total_score'.
        """
        metrics = [
            'moat_score', 'barriers_score', 'disruption_risk', 'switching_cost',
            'brand_strength', 'competition_intensity', 'network_effect',
            'product_differentiation', 'innovativeness_score', 'growth_opportunity',
            'riskiness_score', 'pricing_power', 'ambition_score',
            'bargaining_power_of_customers', 'bargaining_power_of_suppliers',
            'product_quality_score', 'culture_employee_satisfaction_score',
            'trailblazer_score', 'management_quality_score', 'ai_knowledge_score',
            'size_well_known_score', 'ethical_healthy_environmental_score',
            'long_term_orientation_score'
        ]
        
        # Prepare data for insertion
        data = {m: self._clean_score(scores_dict.get(m)) for m in metrics}
        data['ticker'] = ticker.upper()
        data['company_name'] = company_name
        data['model'] = scores_dict.get('model', 'unknown')
        data['timestamp'] = datetime.now().isoformat()
        data['total_score'] = self._clean_score(scores_dict.get('total_score', 0))

        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])

        query = f'''
            INSERT INTO scores ({columns})
            VALUES ({placeholders})
        '''

        with self._get_connection() as conn:
            conn.execute(query, list(data.values()))
            conn.commit()

    def get_score(self, ticker):
        """Get the most recent score for a ticker."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM scores 
                WHERE ticker = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''', (ticker.upper(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_versions(self, ticker):
        """Get all historical scores for a ticker."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM scores 
                WHERE ticker = ? 
                ORDER BY timestamp DESC
            ''', (ticker.upper(),))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_scores(self):
        """Get the most recent scores for all tickers."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # This query gets the latest entry for each ticker
            cursor.execute('''
                SELECT s1.*
                FROM scores s1
                JOIN (
                    SELECT ticker, MAX(timestamp) as max_ts
                    FROM scores
                    GROUP BY ticker
                ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
                ORDER BY s1.total_score DESC
            ''')
            return {row['ticker']: dict(row) for row in cursor.fetchall()}

    def delete_score(self, ticker):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM scores WHERE ticker = ?", (ticker.upper(),))
            conn.commit()

    def get_count(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM scores")
            return cursor.fetchone()[0]

