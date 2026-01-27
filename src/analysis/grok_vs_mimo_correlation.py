import sqlite3
import os
import math

# Define the project root relative to this script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "scores.db")

def calculate_pearson(x, y):
    if len(x) != len(y) or len(x) == 0:
        return 0
    
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    
    num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    den_x = sum((x[i] - mean_x)**2 for i in range(n))
    den_y = sum((y[i] - mean_y)**2 for i in range(n))
    
    if den_x == 0 or den_y == 0:
        return 0
        
    return num / math.sqrt(den_x * den_y)

def analyze_correlation():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get latest Grok scores
        cursor.execute("""
            SELECT ticker, total_score, timestamp 
            FROM scores s1
            WHERE model = 'grok-4-1-fast-reasoning'
            AND timestamp = (
                SELECT MAX(timestamp) 
                FROM scores s2 
                WHERE s2.ticker = s1.ticker 
                AND s2.model = 'grok-4-1-fast-reasoning'
            )
        """)
        grok_scores = {row['ticker']: row['total_score'] for row in cursor.fetchall()}
        
        # Get latest Mimo scores (any variant)
        mimo_variants = "('xiaomi/mimo-v2-flash', 'xiaomimimo/mimo-v2-flash', 'xiaomi/mimo-v2-flash:free')"
        cursor.execute(f"""
            SELECT ticker, total_score, timestamp 
            FROM scores s1
            WHERE model IN {mimo_variants}
            AND timestamp = (
                SELECT MAX(timestamp) 
                FROM scores s2 
                WHERE s2.ticker = s1.ticker 
                AND s2.model IN {mimo_variants}
            )
        """)
        mimo_scores = {row['ticker']: row['total_score'] for row in cursor.fetchall()}
        
        # Find common tickers
        common_tickers = sorted(list(set(grok_scores.keys()) & set(mimo_scores.keys())))
        
        if not common_tickers:
            print("No tickers found with both Grok 4.1 Fast and Mimo scores.")
            # Show what we do have
            print(f"Grok entries: {len(grok_scores)}")
            print(f"Mimo entries: {len(mimo_scores)}")
            return

        # 1. TOTAL SCORE CORRELATION
        x_total = [grok_scores[t] for t in common_tickers]
        y_total = [mimo_scores[t] for t in common_tickers]
        total_correlation = calculate_pearson(x_total, y_total)
        
        # 2. INDIVIDUAL METRIC CORRELATION
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
        
        # Fetch all metrics for common tickers
        placeholders = ', '.join(['?'] * len(common_tickers))
        
        # Get Grok metrics
        cursor.execute(f"""
            SELECT * FROM scores s1
            WHERE model = 'grok-4-1-fast-reasoning'
            AND ticker IN ({placeholders})
            AND timestamp = (
                SELECT MAX(timestamp) FROM scores s2 
                WHERE s2.ticker = s1.ticker AND s2.model = s1.model
            )
        """, common_tickers)
        grok_metrics_rows = {row['ticker']: dict(row) for row in cursor.fetchall()}
        
        # Get Mimo metrics
        cursor.execute(f"""
            SELECT * FROM scores s1
            WHERE model IN {mimo_variants}
            AND ticker IN ({placeholders})
            AND timestamp = (
                SELECT MAX(timestamp) FROM scores s2 
                WHERE s2.ticker = s1.ticker AND s2.model IN {mimo_variants}
            )
        """, common_tickers)
        mimo_metrics_rows = {row['ticker']: dict(row) for row in cursor.fetchall()}
        
        x_all_metrics = []
        y_all_metrics = []
        
        for t in common_tickers:
            g_row = grok_metrics_rows.get(t)
            m_row = mimo_metrics_rows.get(t)
            if g_row and m_row:
                for m in metrics:
                    val_g = g_row.get(m)
                    val_m = m_row.get(m)
                    if val_g is not None and val_m is not None:
                        x_all_metrics.append(float(val_g))
                        y_all_metrics.append(float(val_m))
        
        metrics_correlation = calculate_pearson(x_all_metrics, y_all_metrics)

        # 3. PER-STOCK METRIC CORRELATION
        per_stock_correlations = []
        for t in common_tickers:
            g_row = grok_metrics_rows.get(t)
            m_row = mimo_metrics_rows.get(t)
            if g_row and m_row:
                x_stock = []
                y_stock = []
                for m in metrics:
                    val_g = g_row.get(m)
                    val_m = m_row.get(m)
                    if val_g is not None and val_m is not None:
                        x_stock.append(float(val_g))
                        y_stock.append(float(val_m))
                
                if x_stock:
                    stock_correl = calculate_pearson(x_stock, y_stock)
                    per_stock_correlations.append((t, stock_correl))
        
        # Sort by correlation descending
        per_stock_correlations.sort(key=lambda x: x[1], reverse=True)

        print(f"\nCorrelation Analysis: Grok 4.1 Fast vs Mimo")
        print("=" * 60)
        print(f"Number of companies analyzed: {len(common_tickers)}")
        print(f"Total metrics data points: {len(x_all_metrics)}")
        print("-" * 60)
        print(f"Global Total Score Correlation:    {total_correlation:.4f}")
        print(f"Global Metric Correlation:         {metrics_correlation:.4f}")
        print("-" * 60)
        
        # Interpretation (using total score as primary)
        correlation = total_correlation
        if correlation >= 0.7:
            interp = "Strong Positive"
        elif correlation >= 0.4:
            interp = "Moderate Positive"
        elif correlation >= 0.1:
            interp = "Weak Positive"
        elif correlation > -0.1:
            interp = "Near Zero (No Correlation)"
        elif correlation > -0.4:
            interp = "Weak Negative"
        elif correlation > -0.7:
            interp = "Moderate Negative"
        else:
            interp = "Strong Negative"
            
        print(f"Interpretation: {interp} relationship (based on total score)")
        print("=" * 60)
        
        # Show Top 20 and Bottom 10 stocks by metric correlation
        print("\nRanking: Stocks with Highest Metric Correlation (Grok vs Mimo)")
        print("-" * 60)
        print(f"{'Rank':<5} {'Ticker':<10} {'Correlation':<15}")
        print("-" * 60)
        for i, (ticker, correl) in enumerate(per_stock_correlations[:20], 1):
            print(f"{i:<5} {ticker:<10} {correl:<15.4f}")
        
        print("\n...")
        
        print("\nRanking: Stocks with Lowest Metric Correlation (Grok vs Mimo)")
        print("-" * 60)
        print(f"{'Rank':<5} {'Ticker':<10} {'Correlation':<15}")
        print("-" * 60)
        total_count = len(per_stock_correlations)
        for i, (ticker, correl) in enumerate(per_stock_correlations[-10:], total_count - 9):
            print(f"{i:<5} {ticker:<10} {correl:<15.4f}")
        
        # Show top 5 examples for total score
        print("\n\nTop 5 Total Score Comparison Examples (Ticker: Grok vs Mimo)")
        for t in common_tickers[:5]:
            print(f" - {t:<6}: {grok_scores[t]:>8.2f} vs {mimo_scores[t]:>8.2f}")

        conn.close()
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    analyze_correlation()

