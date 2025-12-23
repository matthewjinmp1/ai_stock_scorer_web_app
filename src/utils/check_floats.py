import sqlite3
import os

# Define the project root relative to this script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "scores.db")

def check_for_floats():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

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

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        print(f"Checking {len(metrics)} metric columns for non-integer values...")
        
        found_any = False
        non_integer_counts = {}
        model_counts = {}
        examples = []

        for metric in metrics:
            # SQL check: value is not equal to its integer cast
            query = f"SELECT id, ticker, {metric}, model FROM scores WHERE {metric} != CAST({metric} AS INT)"
            cursor.execute(query)
            rows = cursor.fetchall()
            
            if rows:
                found_any = True
                non_integer_counts[metric] = len(rows)
                for row in rows:
                    model = row['model']
                    model_counts[model] = model_counts.get(model, 0) + 1
                    
                    if len([ex for ex in examples if ex['metric'] == metric]) < 3: # Keep first 3 examples per metric
                        examples.append({
                            'metric': metric,
                            'ticker': row['ticker'],
                            'value': row[metric],
                            'model': model,
                            'id': row['id']
                        })

        if not found_any:
            print("\nSUCCESS: All metric scores in the database are whole numbers (integers).")
        else:
            print(f"\nFOUND non-integer values in {len(non_integer_counts)} different metrics.")
            
            print("\nNon-integer counts by Model:")
            print("-" * 50)
            print(f"{'Model':<35} | {'Count'}")
            print("-" * 50)
            for model, count in sorted(model_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"{model:<35} | {count}")

            print("\nNon-integer counts by Metric:")
            print("-" * 50)
            print(f"{'Metric':<35} | {'Count'}")
            print("-" * 50)
            for metric, count in sorted(non_integer_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"{metric:<35} | {count}")
            
            print("\nExample Non-Integer Values:")
            print("-" * 80)
            print(f"{'Ticker':<10} | {'Metric':<30} | {'Value':<8} | {'Model'}")
            print("-" * 80)
            for ex in examples[:20]:
                print(f"{ex['ticker']:<10} | {ex['metric']:<30} | {ex['value']:<8} | {ex['model']}")

        conn.close()
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    check_for_floats()

