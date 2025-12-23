import sqlite3
import os

# Define paths
WEB_APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(WEB_APP_DIR, "top_500_scores.db")

def reorder_columns():
    if not os.path.exists(DB_FILE):
        print(f"Error: {DB_FILE} not found.")
        return

    print(f"Connecting to database at {DB_FILE}...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        # 1. Create a new temporary table with the desired column order
        print("Creating new table with reordered columns...")
        cursor.execute('''
            CREATE TABLE scores_new (
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

        # 2. Copy data from the old table to the new one
        print("Migrating data to new table...")
        cursor.execute('''
            INSERT INTO scores_new (
                id, ticker, company_name, moat_score, barriers_score, disruption_risk, switching_cost,
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
                id, ticker, company_name, moat_score, barriers_score, disruption_risk, switching_cost,
                brand_strength, competition_intensity, network_effect,
                product_differentiation, innovativeness_score, growth_opportunity,
                riskiness_score, pricing_power, ambition_score,
                bargaining_power_of_customers, bargaining_power_of_suppliers,
                product_quality_score, culture_employee_satisfaction_score,
                trailblazer_score, management_quality_score, ai_knowledge_score,
                size_well_known_score, ethical_healthy_environmental_score,
                long_term_orientation_score, model, timestamp, total_score
            FROM scores
        ''')

        # 3. Drop the old table
        print("Dropping old table...")
        cursor.execute("DROP TABLE scores")

        # 4. Rename the new table to 'scores'
        print("Renaming new table to 'scores'...")
        cursor.execute("ALTER TABLE scores_new RENAME TO scores")

        # 5. Recreate indexes
        print("Recreating indexes...")
        cursor.execute("CREATE INDEX idx_ticker_timestamp ON scores (ticker, timestamp DESC)")

        conn.commit()
        print("Migration complete! Columns reordered.")

    except Exception as e:
        conn.rollback()
        print(f"An error occurred during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    reorder_columns()

