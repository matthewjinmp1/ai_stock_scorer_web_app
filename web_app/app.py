import os
import sqlite3
import json
from flask import Flask, render_template, request

import shutil

app = Flask(__name__)

# Base directory
WEB_APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Database paths
DB_PATH = os.getenv('DB_PATH', os.path.join(WEB_APP_DIR, 'top_scores.db'))

# Production trick: Initializing persistent database if it doesn't exist
repo_path = os.path.join(WEB_APP_DIR, 'top_scores.db')
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

@app.route('/health')
def health():
    """Simple health check endpoint for cron jobs."""
    return {"status": "ok"}, 200

@app.route('/')
def index():
    conn = get_db_connection()
    max_score = get_max_possible_score()
    
    # Pagination and search parameters
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()
    per_page = 100  # Companies per page
    
    # Get latest scores for all companies
    base_query = """
        SELECT s1.*
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
    """
    
    # Apply search filter if provided (using parameterized query to prevent SQL injection)
    # Only match prefixes (start of ticker or company name), not substrings
    if search_query:
        search_upper = f"{search_query.upper()}%"
        base_query += " WHERE s1.ticker LIKE ? OR UPPER(s1.company_name) LIKE ?"
        base_query += " ORDER BY s1.total_score DESC"
        rows = conn.execute(base_query, (search_upper, search_upper)).fetchall()
    else:
        base_query += " ORDER BY s1.total_score DESC"
        rows = conn.execute(base_query).fetchall()
    
    # Pre-sort scores once for O(1) percentile calculation inside the loop
    # We need all scores for percentile calculation, not just filtered ones
    all_scores_query = """
        SELECT total_score
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
    """
    all_scores_rows = conn.execute(all_scores_query).fetchall()
    all_scores = sorted([float(row['total_score']) for row in all_scores_rows])
    
    # Get all companies sorted by total_score to calculate global ranks
    global_rank_query = """
        SELECT s1.ticker, s1.total_score
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
        ORDER BY s1.total_score DESC
    """
    global_rank_rows = conn.execute(global_rank_query).fetchall()
    
    # Create a mapping of ticker -> global_rank (1-indexed)
    global_ranks = {}
    for rank, row in enumerate(global_rank_rows, start=1):
        global_ranks[row['ticker']] = rank
    
    # Get total companies count (without search filter) for header display
    total_all_companies_query = """
        SELECT COUNT(DISTINCT s1.ticker)
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
    """
    total_all_companies = conn.execute(total_all_companies_query).fetchone()[0]
    
    conn.close()
    
    # Calculate total companies (filtered) and pages
    total_companies = len(rows)
    total_pages = (total_companies + per_page - 1) // per_page  # Ceiling division
    
    # Validate page number
    if page < 1:
        page = 1
    elif page > total_pages and total_pages > 0:
        page = total_pages
    
    # Calculate pagination slice
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_rows = rows[start_idx:end_idx]
    
    companies = []
    for row in paginated_rows:
        company_dict = dict(row)
        # Calculate percentage of total possible score
        total_score = float(company_dict.get('total_score', 0))
        score_percentage = int((total_score / max_score) * 100)
        # Cap at 100% to handle data corruption issues
        company_dict['score_percentage'] = min(score_percentage, 100)
            
        # Calculate percentile using the pre-sorted list
        company_dict['percentile'] = calculate_percentile_rank(total_score, all_scores)
        
        # Add global rank (use ticker to look up rank)
        ticker = company_dict.get('ticker', '')
        company_dict['global_rank'] = global_ranks.get(ticker, 0)
        
        companies.append(company_dict)
    
    # Calculate pagination info
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_companies,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_page': page - 1 if page > 1 else None,
        'next_page': page + 1 if page < total_pages else None
    }
        
    return render_template('index.html', companies=companies, pagination=pagination, total_companies=total_all_companies, search_results_count=total_companies, search_query=search_query)

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
    score_percentage = int((total_score / max_score) * 100)
    # Cap at 100% to handle data corruption issues
    company['score_percentage'] = min(score_percentage, 100)
        
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

