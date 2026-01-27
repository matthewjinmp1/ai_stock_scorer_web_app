import sqlite3
import pandas as pd
import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.config import DB_DIR, TOP_SCORES_DB

RETURNS_DB = os.path.join(DB_DIR, 'top_ranked_returns.db')

METRICS = [
    'moat_score', 'barriers_score', 'disruption_risk', 'switching_cost', 
    'brand_strength', 'competition_intensity', 'network_effect', 
    'product_differentiation', 'innovativeness_score', 'growth_opportunity', 
    'riskiness_score', 'pricing_power', 'ambition_score', 
    'bargaining_power_of_customers', 'bargaining_power_of_suppliers', 
    'product_quality_score', 'culture_employee_satisfaction_score', 
    'trailblazer_score', 'management_quality_score', 'ai_knowledge_score',
    'size_well_known_score', 'ethical_healthy_environmental_score',
    'long_term_orientation_score', 'execution_ability_score',
    'customer_obsession', 'adaptability_score', 'capital_allocation_score',
    'total_score'
]

REVERSE_METRICS = [
    'disruption_risk', 'competition_intensity', 'riskiness_score', 
    'bargaining_power_of_customers', 'bargaining_power_of_suppliers',
    'size_well_known_score'
]

def analyze_metric_correlations():
    if not os.path.exists(RETURNS_DB):
        print(f"Error: Database not found at {RETURNS_DB}")
        return
    if not os.path.exists(TOP_SCORES_DB):
        print(f"Error: Database not found at {TOP_SCORES_DB}")
        return

    # Load returns data
    conn = sqlite3.connect(RETURNS_DB)
    # We use LEFT JOIN to get scores for these tickers from the top_scores.db
    try:
        conn.execute(f"ATTACH DATABASE '{TOP_SCORES_DB}' AS scores_db")
        
        # We need to be careful with duplicate tickers in scores (use the latest one)
        metric_cols = ", ".join([f"s.{m}" for m in METRICS])
        query = f"""
            SELECT 
                r.ticker, 
                r.return_pct,
                {metric_cols}
            FROM top_ranked_returns r
            LEFT JOIN (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp DESC) as rn
                FROM scores_db.scores
            ) s ON r.ticker = s.ticker AND s.rn = 1
        """
        df = pd.read_sql_query(query, conn)
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return
    finally:
        conn.close()

    if df.empty:
        print("Error: No data found.")
        return

    print(f"Individual Metric vs Return Correlation Analysis")
    print(f"================================================")
    print(f"Sample size: {len(df)} companies\n")

    results = []
    for metric in METRICS:
        if metric not in df.columns:
            continue
            
        # Drop rows where metric is NaN for this calculation
        valid_df = df.dropna(subset=[metric, 'return_pct'])
        if len(valid_df) < 5:
            continue
            
        pearson = valid_df[metric].corr(valid_df['return_pct'])
        
        # Manual Spearman (Pearson of ranks)
        score_rank = valid_df[metric].rank()
        if metric in REVERSE_METRICS:
            # Flip rank: higher score becomes lower rank
            score_rank = (len(valid_df) + 1) - score_rank
            
        spearman = score_rank.corr(valid_df['return_pct'].rank())
        
        display_name = metric.replace('_', ' ').title()
        if metric in REVERSE_METRICS:
            display_name = f"{display_name} (Flipped)"
            
        results.append({
            'Metric': display_name,
            'Pearson': pearson,
            'Spearman': spearman
        })

    # Convert results to DataFrame for easy sorting
    results_df = pd.DataFrame(results)
    
    # Sort by Spearman correlation descending (most positive first)
    results_df = results_df.sort_values('Spearman', ascending=False)

    print(f"{'Metric':<40} {'Spearman (Ranked)':>20}")
    print("-" * 62)
    for _, row in results_df.iterrows():
        print(f"{row['Metric']:<40} {row['Spearman']:>20.4f}")

    print("\nSummary:")
    top_pos = results_df.iloc[0]
    top_neg = results_df.iloc[-1]
    
    print(f"Most Positive Rank Correlation: {top_pos['Metric']} ({top_pos['Spearman']:.4f})")
    print(f"Most Negative Rank Correlation: {top_neg['Metric']} ({top_neg['Spearman']:.4f})")

if __name__ == "__main__":
    analyze_metric_correlations()
