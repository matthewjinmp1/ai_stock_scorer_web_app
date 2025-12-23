import sqlite3
import os

# Define paths
WEB_APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(WEB_APP_DIR, "top_500_scores.db")

METRICS = [
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

def remove_zeros():
    if not os.path.exists(DB_FILE):
        print(f"Error: {DB_FILE} not found.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Construct the WHERE clause: any metric is 0.0
    where_conditions = [f"{m} = 0.0" for m in METRICS]
    where_clause = " OR ".join(where_conditions)
    
    # Count rows before deletion
    cursor.execute("SELECT COUNT(*) FROM scores")
    initial_count = cursor.fetchone()[0]
    
    # Count rows that will be deleted
    cursor.execute(f"SELECT COUNT(*) FROM scores WHERE {where_clause}")
    to_delete_count = cursor.fetchone()[0]
    
    print(f"Total rows in scores table: {initial_count}")
    print(f"Rows with at least one 0.0 score: {to_delete_count}")
    
    if to_delete_count > 0:
        print(f"Removing {to_delete_count} rows...")
        cursor.execute(f"DELETE FROM scores WHERE {where_clause}")
        conn.commit()
        print("Deletion complete.")
    else:
        print("No rows found with 0.0 scores.")

    conn.close()

if __name__ == "__main__":
    remove_zeros()

