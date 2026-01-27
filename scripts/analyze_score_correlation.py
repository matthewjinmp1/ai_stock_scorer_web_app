import sqlite3
import pandas as pd
import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.settings import DB_DIR, TOP_SCORES_DB

RETURNS_DB = os.path.join(DB_DIR, 'top_ranked_returns.db')

def analyze_correlation():
    if not os.path.exists(RETURNS_DB):
        print(f"Error: Database not found at {RETURNS_DB}")
        print("Please run scripts/store_top_100_performance.py first.")
        return
    if not os.path.exists(TOP_SCORES_DB):
        print(f"Error: Database not found at {TOP_SCORES_DB}")
        return

    # Load data from the database
    conn = sqlite3.connect(RETURNS_DB)
    # Join with the scores database to get the LATEST total score calculation
    try:
        conn.execute(f"ATTACH DATABASE '{TOP_SCORES_DB}' AS scores_db")
        query = """
            SELECT 
                r.ticker, 
                s.total_score as score, 
                r.return_pct 
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
        print("Error: No data found in the returns database.")
        return
    
    # Filter out companies that don't have a score yet
    df = df.dropna(subset=['score'])

    print(f"Score vs Return Correlation Analysis")
    print(f"====================================")
    print(f"Sample size: {len(df)} companies\n")

    # Calculate Pearson Correlation
    pearson_corr = df['score'].corr(df['return_pct'])
    
    # Calculate Spearman Rank Correlation manually (Pearson of ranks)
    # This avoids a dependency on scipy which might be missing
    score_rank = df['score'].rank()
    return_rank = df['return_pct'].rank()
    spearman_corr = score_rank.corr(return_rank)
    
    # Calculate R-squared (Pearson)
    r_squared = pearson_corr ** 2

    print(f"Pearson Correlation (Linear):     {pearson_corr:.4f}")
    print(f"Spearman Correlation (Ranked):     {spearman_corr:.4f}")
    print(f"Coefficient of Determination (R²): {r_squared:.4f}")
    
    # Interpretation
    print("\nInterpretation (Ranked Correlation):")
    if abs(spearman_corr) < 0.1:
        strength = "negligible"
    elif abs(spearman_corr) < 0.3:
        strength = "weak"
    elif abs(spearman_corr) < 0.5:
        strength = "moderate"
    else:
        strength = "strong"
        
    direction = "positive" if spearman_corr > 0 else "negative"
    
    if abs(spearman_corr) < 0.1:
        print(f"There is {strength} ranked correlation between the AI score and the stock returns.")
    else:
        print(f"There is a {strength} {direction} ranked correlation between the AI score and the stock returns.")

    # Show top and bottom performers by score vs return
    print("\nTop 5 by AI Score:")
    print(df.sort_values('score', ascending=False).head(5)[['ticker', 'score', 'return_pct']].to_string(index=False))

    print("\nTop 5 by Return:")
    print(df.sort_values('return_pct', ascending=False).head(5)[['ticker', 'score', 'return_pct']].to_string(index=False))

if __name__ == "__main__":
    analyze_correlation()
