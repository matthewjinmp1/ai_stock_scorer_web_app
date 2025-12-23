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

def show_zeros():
    if not os.path.exists(DB_FILE):
        print(f"Error: {DB_FILE} not found.")
        return

    print(f"Searching for metrics with score 0 or NULL in {DB_FILE}...")
    print("=" * 110)
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get latest entry for each ticker
    query = """
        SELECT s1.*
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
    """
    
    rows = cursor.execute(query).fetchall()
    
    instances = []
    
    for row in rows:
        ticker = row['ticker']
        company_name = row['company_name'] or "Unknown"
        
        for metric in METRICS:
            val = row[metric]
            if val == 0.0 or val is None:
                instances.append({
                    'ticker': ticker,
                    'company': company_name,
                    'metric': metric,
                    'value': "NULL" if val is None else val
                })

    if not instances:
        print("No metrics with score 0 or NULL found.")
    else:
        print(f"{'Ticker':<12} | {'Company':<35} | {'Metric':<35} | {'Score'}")
        print("-" * 110)
        for instance in instances:
            print(f"{instance['ticker']:<12} | {instance['company'][:35]:<35} | {instance['metric']:<35} | {instance['value']}")
        
        print("-" * 110)
        print(f"Total instances found: {len(instances)}")

    conn.close()

if __name__ == "__main__":
    show_zeros()

