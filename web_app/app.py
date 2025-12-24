import os
import sqlite3
import json
from flask import Flask, render_template, request

import shutil

app = Flask(__name__)

# Base directory
WEB_APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Database paths
DB_PATH = os.getenv('DB_PATH', os.path.join(WEB_APP_DIR, 'top_500_scores.db'))

# Production trick: Initializing persistent database if it doesn't exist
repo_path = os.path.join(WEB_APP_DIR, 'top_500_scores.db')
if DB_PATH != repo_path and not os.path.exists(DB_PATH) and os.path.exists(repo_path):
    print(f"Initializing persistent database at {DB_PATH} from {repo_path}...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    shutil.copy2(repo_path, DB_PATH)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_percentile_rank(score, sorted_scores):
    """Calculate percentile rank (0-100) using pre-sorted scores for speed."""
    if not sorted_scores:
        return 0
    import bisect
    count_less_or_equal = bisect.bisect_right(sorted_scores, score)
    return int((count_less_or_equal / len(sorted_scores)) * 100)

def get_max_possible_score():
    """Calculate the maximum possible score based on definitions and weights."""
    # These values are mirrors of those in src/scoring/scorer.py
    weights = {
        'moat_score': 10, 'barriers_score': 10, 'disruption_risk': 10,
        'switching_cost': 10, 'brand_strength': 10, 'competition_intensity': 10,
        'network_effect': 10, 'product_differentiation': 10, 'innovativeness_score': 10,
        'growth_opportunity': 10, 'riskiness_score': 10, 'pricing_power': 10,
        'ambition_score': 10, 'bargaining_power_of_customers': 10, 'bargaining_power_of_suppliers': 10,
        'product_quality_score': 10, 'culture_employee_satisfaction_score': 10, 'trailblazer_score': 10,
        'management_quality_score': 10, 'ai_knowledge_score': 10, 'size_well_known_score': 19.31,
        'ethical_healthy_environmental_score': 10, 'long_term_orientation_score': 10
    }
    return sum(weights.values()) * 10

@app.route('/')
def index():
    conn = get_db_connection()
    max_score = get_max_possible_score()
    
    # Get latest scores for all companies
    query = """
        SELECT s1.*
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
        ORDER BY s1.total_score DESC
    """
    rows = conn.execute(query).fetchall()
    conn.close()
    
    # Pre-sort scores once for O(1) percentile calculation inside the loop
    all_scores = sorted([float(row['total_score']) for row in rows])
    
    companies = []
    for row in rows:
        company_dict = dict(row)
        # Calculate percentage of total possible score
        total_score = float(company_dict.get('total_score', 0))
        company_dict['score_percentage'] = int((total_score / max_score) * 100)
            
        # Calculate percentile using the pre-sorted list
        company_dict['percentile'] = calculate_percentile_rank(total_score, all_scores)
        companies.append(company_dict)
        
    return render_template('index.html', companies=companies)

@app.route('/company/<ticker>')
def company_detail(ticker):
    conn = get_db_connection()
    ticker_upper = ticker.upper()
    max_score = get_max_possible_score()
    
    # Get latest entry for the ticker
    query = """
        SELECT *
        FROM scores
        WHERE ticker = ? 
        ORDER BY timestamp DESC 
        LIMIT 1
    """
    row = conn.execute(query, (ticker_upper,)).fetchone()
    
    if not row:
        conn.close()
        return "Company not found", 404
        
    company = dict(row)
    
    # Calculate score percentage for current company
    total_score = float(company.get('total_score', 0))
    company['score_percentage'] = int((total_score / max_score) * 100)
        
    # Get all latest scores for percentile calculation
    all_latest_query = """
        SELECT total_score
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
    """
    all_rows = conn.execute(all_latest_query).fetchall()
    all_scores = sorted([float(r['total_score']) for r in all_rows])
    company['percentile'] = calculate_percentile_rank(total_score, all_scores)

    # Get history
    history_rows = conn.execute("SELECT * FROM scores WHERE ticker = ? ORDER BY timestamp DESC", (ticker_upper,)).fetchall()
    conn.close()
    
    history = [dict(h) for h in history_rows]
        
    return render_template('detail.html', company=company, history=history)

if __name__ == '__main__':
    app.run(debug=True, port=5001)

