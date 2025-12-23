import sqlite3
import os
import sys

# Define the project root relative to this script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "scores.db")

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

def show_model_discrepancies(limit=50):
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get latest Grok scores
        cursor.execute("""
            SELECT * FROM scores s1
            WHERE model = 'grok-4-1-fast-reasoning'
            AND timestamp = (
                SELECT MAX(timestamp) 
                FROM scores s2 
                WHERE s2.ticker = s1.ticker 
                AND s2.model = 'grok-4-1-fast-reasoning'
            )
        """)
        grok_data = {row['ticker']: dict(row) for row in cursor.fetchall()}
        
        # Get latest Mimo scores (any variant)
        mimo_variants = "('xiaomi/mimo-v2-flash', 'xiaomimimo/mimo-v2-flash', 'xiaomi/mimo-v2-flash:free')"
        cursor.execute(f"""
            SELECT * FROM scores s1
            WHERE model IN {mimo_variants}
            AND timestamp = (
                SELECT MAX(timestamp) 
                FROM scores s2 
                WHERE s2.ticker = s1.ticker 
                AND s2.model IN {mimo_variants}
            )
        """)
        mimo_data = {row['ticker']: dict(row) for row in cursor.fetchall()}
        
        common_tickers = set(grok_data.keys()) & set(mimo_data.keys())
        
        if not common_tickers:
            print("No common tickers found between Grok and Mimo.")
            return

        discrepancies = []
        
        for ticker in common_tickers:
            g_row = grok_data[ticker]
            m_row = mimo_data[ticker]
            company_name = g_row.get('company_name') or m_row.get('company_name') or ticker
            
            for metric in METRICS:
                g_val = g_row.get(metric)
                m_val = m_row.get(metric)
                
                if g_val is not None and m_val is not None:
                    diff = abs(float(g_val) - float(m_val))
                    discrepancies.append({
                        'ticker': ticker,
                        'company': company_name,
                        'metric': metric.replace('_', ' ').title(),
                        'grok': float(g_val),
                        'mimo': float(m_val),
                        'diff': diff
                    })

        # Sort by difference descending
        discrepancies.sort(key=lambda x: x['diff'], reverse=True)

        print(f"\nTop {limit} Model Discrepancies: Grok vs Mimo")
        print("=" * 105)
        print(f"{'Ticker':<8} {'Metric':<30} {'Grok':<8} {'Mimo':<8} {'Diff':<8} {'Company'}")
        print("-" * 105)
        
        for d in discrepancies[:limit]:
            print(f"{d['ticker']:<8} {d['metric']:<30} {d['grok']:<8.1f} {d['mimo']:<8.1f} {d['diff']:<8.1f} {d['company']}")
            
        print("=" * 105)
        
        # 1. Bucket Analysis
        buckets = {i: 0 for i in range(11)}  # 0 to 10
        for d in discrepancies:
            # Round difference to nearest integer for bucketing
            diff_val = round(d['diff'])
            if diff_val in buckets:
                buckets[diff_val] += 1
            elif diff_val > 10:
                buckets[10] += 1

        print("\nDifference Distribution (Buckets 0-10)")
        print("-" * 45)
        print(f"{'Difference':<15} | {'Count':<10} | {'Percentage':<10}")
        print("-" * 45)
        total_metrics = len(discrepancies)
        for i in range(11):
            count = buckets[i]
            percentage = (count / total_metrics) * 100 if total_metrics > 0 else 0
            label = f"{i}.0" if i < 10 else "10.0+"
            print(f"{label:<15} | {count:<10} | {percentage:>8.1f}%")
        print("-" * 45)
        
        print(f"Total metrics compared across {len(common_tickers)} companies: {len(discrepancies)}")
        
        conn.close()
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    show_model_discrepancies()

