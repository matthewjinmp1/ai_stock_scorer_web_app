import os
import sqlite3
import json
from flask import Flask, render_template, request

import shutil

app = Flask(__name__)

# Base directory
WEB_APP_DIR = os.path.dirname(os.path.abspath(__file__))
# Use environment variable for DB path if available (for Render persistent storage),
# otherwise default to the local file.
DB_PATH = os.getenv('DB_PATH', os.path.join(WEB_APP_DIR, 'top_500_scores.db'))

# Production trick: If we are using a persistent volume and the DB isn't there yet,
# copy the initial version from the repository.
repo_db_path = os.path.join(WEB_APP_DIR, 'top_500_scores.db')
if DB_PATH != repo_db_path and not os.path.exists(DB_PATH) and os.path.exists(repo_db_path):
    print(f"Initializing persistent database at {DB_PATH} from {repo_db_path}...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    shutil.copy2(repo_db_path, DB_PATH)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def calculate_percentile_rank(score, all_scores):
    """Calculate percentile rank (0-100)."""
    if not all_scores:
        return 0
    scores_less_or_equal = sum(1 for s in all_scores if s <= score)
    return int((scores_less_or_equal / len(all_scores)) * 100)

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
    
    # Get latest scores for all companies joined with metadata
    query = """
        SELECT s1.*, m.name as metadata_name, m.market_cap, m.rank as market_rank
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
        LEFT JOIN companies_metadata m ON s1.ticker = m.ticker
        ORDER BY s1.total_score DESC
    """
    rows = conn.execute(query).fetchall()
    conn.close()
    
    all_scores = [row['total_score'] for row in rows]
    
    companies = []
    for row in rows:
        company_dict = dict(row)
        # Use metadata name if available
        if company_dict.get('metadata_name'):
            company_dict['company_name'] = company_dict['metadata_name']
            
        # Calculate percentage of total possible score
        total_score = float(company_dict.get('total_score', 0))
        company_dict['score_percentage'] = int((total_score / max_score) * 100)
            
        # Calculate percentile
        company_dict['percentile'] = calculate_percentile_rank(total_score, all_scores)
        companies.append(company_dict)
        
    return render_template('index.html', companies=companies)

@app.route('/company/<ticker>')
def company_detail(ticker):
    conn = get_db_connection()
    ticker_upper = ticker.upper()
    max_score = get_max_possible_score()
    
    # Get latest entry for the ticker with metadata
    query = """
        SELECT s.*, m.name as metadata_name, m.market_cap, m.rank as market_rank, m.price, m.country
        FROM scores s
        LEFT JOIN companies_metadata m ON s.ticker = m.ticker
        WHERE s.ticker = ? 
        ORDER BY s.timestamp DESC 
        LIMIT 1
    """
    row = conn.execute(query, (ticker_upper,)).fetchone()
    
    if not row:
        conn.close()
        return "Company not found", 404
        
    company = dict(row)
    if company.get('metadata_name'):
        company['company_name'] = company['metadata_name']
    
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
    all_scores = [float(r['total_score']) for r in all_rows]
    company['percentile'] = calculate_percentile_rank(total_score, all_scores)

    # Get history
    history_rows = conn.execute("SELECT * FROM scores WHERE ticker = ? ORDER BY timestamp DESC", (ticker_upper,)).fetchall()
    conn.close()
    
    history = [dict(h) for h in history_rows]
    for h in history:
        if company.get('metadata_name'):
            h['company_name'] = company['metadata_name']
        
    return render_template('detail.html', company=company, history=history)

if __name__ == '__main__':
    app.run(debug=True, port=5001)

