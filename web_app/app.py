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
PEERS_DB = os.path.join(WEB_APP_DIR, 'peers.db')
TOP_COMPANIES_DB = os.path.join(WEB_APP_DIR, 'top_companies.db')

# Production trick: Initializing persistent database if it doesn't exist
repo_path = os.path.join(WEB_APP_DIR, 'top_scores.db')
try:
    if DB_PATH != repo_path and not os.path.exists(DB_PATH) and os.path.exists(repo_path):
        print(f"Initializing persistent database at {DB_PATH} from {repo_path}...")
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        shutil.copy2(repo_path, DB_PATH)
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")
    # Continue anyway - the app should still start

def get_db_connection():
    """Get database connection with error handling."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        raise

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
        'ethical_healthy_environmental_score': 10, 'long_term_orientation_score': 10,
        'execution_ability_score': 10
    }
    return sum(weights.values()) * 10

@app.route('/health')
def health():
    """Simple health check endpoint for cron jobs - lightweight and fast."""
    # Just return OK - health checks should be fast and not depend on DB
    # If the app is running and can respond, it's healthy
    return {"status": "ok"}, 200

@app.route('/')
def index():
    conn = get_db_connection()
    max_score = get_max_possible_score()
    
    # Pagination and search parameters
    page = request.args.get('page', 1, type=int)
    search_query_raw = request.args.get('search', '')  # Keep raw for display
    search_query = search_query_raw.strip()  # Strip only when searching
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
    
    # Apply search filter if provided
    # Check if search query exactly matches a ticker (case-insensitive)
    # If yes, do exact match. Otherwise, do prefix matching.
    if search_query:
        search_upper = search_query.upper()
        # Check if this is an exact ticker match in latest scores
        exact_ticker_check = conn.execute("""
            SELECT s1.ticker
            FROM scores s1
            JOIN (
                SELECT ticker, MAX(timestamp) as max_ts
                FROM scores
                GROUP BY ticker
            ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
            WHERE UPPER(s1.ticker) = ?
            LIMIT 1
        """, (search_upper,)).fetchone()
        
        if exact_ticker_check:
            # Exact ticker match - show only this ticker
            base_query += " WHERE UPPER(s1.ticker) = ?"
            base_query += " ORDER BY s1.total_score DESC"
            rows = conn.execute(base_query, (search_upper,)).fetchall()
        else:
            # Prefix matching for ticker or company name
            search_prefix = f"{search_upper}%"
            base_query += " WHERE s1.ticker LIKE ? OR UPPER(s1.company_name) LIKE ?"
            base_query += " ORDER BY s1.total_score DESC"
            rows = conn.execute(base_query, (search_prefix, search_prefix)).fetchall()
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
        
    return render_template('index.html', companies=companies, pagination=pagination, total_companies=total_all_companies, search_results_count=total_companies, search_query=search_query_raw, search_query_stripped=search_query)

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

def get_peers_for_ticker(ticker):
    """Get peer company names for a given ticker from peers.db."""
    if not os.path.exists(PEERS_DB):
        return []
    
    conn = sqlite3.connect(PEERS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT DISTINCT peer_name
        FROM company_peers
        WHERE ticker = ?
        ORDER BY peer_name
    ''', (ticker.upper(),))
    
    peers = [row['peer_name'] for row in cursor.fetchall()]
    conn.close()
    
    return peers

def find_company_in_top_companies(company_name):
    """Find a company in top_companies.db by name (improved fuzzy matching)."""
    if not os.path.exists(TOP_COMPANIES_DB):
        return None
    
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Try exact match first (case-insensitive)
    cursor.execute('''
        SELECT ticker, name, rank
        FROM companies_metadata
        WHERE UPPER(name) = UPPER(?)
        LIMIT 1
    ''', (company_name,))
    
    result = cursor.fetchone()
    if result:
        conn.close()
        return {
            'ticker': result['ticker'],
            'name': result['name'],
            'rank': result['rank']
        }
    
    # Try matching without common suffixes
    suffixes = [' Communications', ' Inc', ' Inc.', ' Corporation', ' Corp', ' Corp.', 
                ' Company', ' Co', ' Co.', ' Limited', ' Ltd', ' Ltd.', ' LLC', ' L.L.C.',
                ' Technologies', ' Technology', ' Group', ' Electronics', ' Devices']
    
    base_name = company_name
    for suffix in suffixes:
        if company_name.endswith(suffix):
            base_name = company_name[:-len(suffix)].strip()
            break
    
    # Try matching with base name (without suffix)
    if base_name != company_name:
        cursor.execute('''
            SELECT ticker, name, rank
            FROM companies_metadata
            WHERE UPPER(name) = UPPER(?)
            LIMIT 1
        ''', (base_name,))
        
        result = cursor.fetchone()
        if result:
            conn.close()
            return {
                'ticker': result['ticker'],
                'name': result['name'],
                'rank': result['rank']
            }
    
    # Try partial match
    cursor.execute('''
        SELECT ticker, name, rank
        FROM companies_metadata
        WHERE UPPER(name) LIKE '%' || UPPER(?) || '%'
        ORDER BY 
            CASE 
                WHEN UPPER(name) = UPPER(?) THEN 1
                WHEN UPPER(name) LIKE UPPER(?) || '%' THEN 2
                WHEN UPPER(name) LIKE '%' || UPPER(?) THEN 3
                ELSE 4
            END,
            rank
        LIMIT 1
    ''', (company_name, company_name, company_name, company_name))
    
    result = cursor.fetchone()
    if result:
        result_name_lower = result['name'].lower()
        search_name_lower = company_name.lower()
        base_name_lower = base_name.lower()
        
        is_good_match = (
            search_name_lower in result_name_lower or 
            result_name_lower in search_name_lower or
            base_name_lower in result_name_lower or
            result_name_lower in base_name_lower
        )
        
        if is_good_match:
            conn.close()
            return {
                'ticker': result['ticker'],
                'name': result['name'],
                'rank': result['rank']
            }
    
    # Try matching base name (without suffix) as partial match
    if base_name != company_name:
        cursor.execute('''
            SELECT ticker, name, rank
            FROM companies_metadata
            WHERE UPPER(name) LIKE '%' || UPPER(?) || '%'
            ORDER BY 
                CASE 
                    WHEN UPPER(name) = UPPER(?) THEN 1
                    WHEN UPPER(name) LIKE UPPER(?) || '%' THEN 2
                    WHEN UPPER(name) LIKE '%' || UPPER(?) THEN 3
                    ELSE 4
                END,
                rank
            LIMIT 1
        ''', (base_name, base_name, base_name, base_name))
        
        result = cursor.fetchone()
        if result:
            result_name_lower = result['name'].lower()
            base_name_lower = base_name.lower()
            
            is_good_match = (
                base_name_lower in result_name_lower or 
                result_name_lower in base_name_lower
            )
            
            if is_good_match:
                conn.close()
                return {
                    'ticker': result['ticker'],
                    'name': result['name'],
                    'rank': result['rank']
                }
    
    conn.close()
    return None

@app.route('/api/company-suggestions')
def company_suggestions():
    """API endpoint to get company suggestions for autocomplete."""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 1:
        return json.dumps([])
    
    query_upper = query.upper()
    conn = get_db_connection()
    
    # Search for companies matching the query (ticker or name)
    # Prioritize exact ticker matches first, then ticker prefix, then exact name, then name contains
    search_query = """
        SELECT DISTINCT ticker, company_name
        FROM scores
        WHERE ticker = ? OR ticker LIKE ? OR UPPER(company_name) = ? OR UPPER(company_name) LIKE ?
        ORDER BY 
            CASE 
                WHEN ticker = ? THEN 1
                WHEN ticker LIKE ? AND ticker != ? THEN 2
                WHEN UPPER(company_name) = ? THEN 3
                WHEN UPPER(company_name) LIKE ? AND UPPER(company_name) != ? THEN 4
                ELSE 5
            END,
            ticker
        LIMIT 10
    """
    
    ticker_prefix = f"{query_upper}%"
    name_exact = query_upper
    name_pattern = f"%{query_upper}%"
    
    results = conn.execute(
        search_query,
        (query_upper, ticker_prefix, name_exact, name_pattern, 
         query_upper, ticker_prefix, query_upper, name_exact, name_pattern, name_exact)
    ).fetchall()
    
    conn.close()
    
    suggestions = [
        {
            'ticker': row['ticker'],
            'name': row['company_name']
        }
        for row in results
    ]
    
    return json.dumps(suggestions)

@app.route('/peers')
def peers():
    """Show peers for a given ticker/company name."""
    conn = get_db_connection()
    max_score = get_max_possible_score()
    
    search_query = request.args.get('search', '').strip().upper()
    
    if not search_query:
        conn.close()
        return render_template('peers.html', peers=[], search_query='', company_name=None, company_ticker=None)
    
    # Try to find the company by ticker or name
    # Prioritize exact ticker match first, then exact name match, then name prefix
    company_query = """
        SELECT ticker, company_name
        FROM scores
        WHERE ticker = ? OR UPPER(company_name) = ? OR UPPER(company_name) LIKE ?
        ORDER BY 
            CASE 
                WHEN ticker = ? THEN 1
                WHEN UPPER(company_name) = ? THEN 2
                WHEN UPPER(company_name) LIKE ? THEN 3
                ELSE 4
            END,
            timestamp DESC
        LIMIT 1
    """
    search_upper = search_query.upper()
    name_prefix = f'{search_upper}%'
    company_row = conn.execute(company_query, (
        search_query, search_upper, name_prefix,
        search_query, search_upper, name_prefix
    )).fetchone()
    
    if not company_row:
        conn.close()
        return render_template('peers.html', peers=[], search_query=search_query, company_name=None, company_ticker=None, error="Company not found")
    
    company_ticker = company_row['ticker']
    company_name = company_row['company_name']
    
    # Get peers from peers.db
    peer_names = get_peers_for_ticker(company_ticker)
    
    if not peer_names:
        conn.close()
        return render_template('peers.html', peers=[], search_query=search_query, company_name=company_name, company_ticker=company_ticker, error="No peers found for this company")
    
    # Get all scores for percentile and rank calculation (do this once)
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
    all_scores = sorted([float(r['total_score']) for r in all_scores_rows])
    
    # Get global ranks (do this once)
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
    global_ranks = {}
    for rank, row in enumerate(global_rank_rows, start=1):
        global_ranks[row['ticker']] = rank
    
    # Add the searched company itself to the list
    company_score_query = """
        SELECT *
        FROM scores
        WHERE ticker = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """
    company_score_row = conn.execute(company_score_query, (company_ticker,)).fetchone()
    
    peers_with_scores = []
    
    # Add the searched company first (marked as the searched company)
    if company_score_row:
        company_dict = dict(company_score_row)
        total_score = float(company_dict.get('total_score', 0))
        score_percentage = int((total_score / max_score) * 100)
        company_dict['score_percentage'] = min(score_percentage, 100)
        company_dict['percentile'] = calculate_percentile_rank(total_score, all_scores)
        company_dict['global_rank'] = global_ranks.get(company_ticker, 0)
        company_dict['peer_name'] = company_name  # Use company name as peer name for display
        company_dict['is_searched_company'] = True
        company_dict['has_score'] = True
        peers_with_scores.append(company_dict)
    
    # Find each peer in top_companies.db and get their scores
    for peer_name in peer_names:
        company_info = find_company_in_top_companies(peer_name)
        if company_info:
            # Get score for this ticker
            score_query = """
                SELECT *
                FROM scores
                WHERE ticker = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """
            score_row = conn.execute(score_query, (company_info['ticker'],)).fetchone()
            
            if score_row:
                # Peer has a score - include it with full data
                peer_dict = dict(score_row)
                total_score = float(peer_dict.get('total_score', 0))
                score_percentage = int((total_score / max_score) * 100)
                peer_dict['score_percentage'] = min(score_percentage, 100)
                peer_dict['percentile'] = calculate_percentile_rank(total_score, all_scores)
                peer_dict['global_rank'] = global_ranks.get(company_info['ticker'], 0)
                peer_dict['peer_name'] = peer_name
                peer_dict['is_searched_company'] = False
                peer_dict['has_score'] = True
                peers_with_scores.append(peer_dict)
            else:
                # Peer found in top_companies.db but no score yet - still show it
                peer_dict = {
                    'ticker': company_info['ticker'],
                    'company_name': company_info['name'],
                    'total_score': 0,
                    'score_percentage': 0,
                    'percentile': 0,
                    'global_rank': 0,
                    'peer_name': peer_name,
                    'is_searched_company': False,
                    'has_score': False
                }
                peers_with_scores.append(peer_dict)
    
    # Sort by total_score descending
    peers_with_scores.sort(key=lambda x: float(x.get('total_score', 0)), reverse=True)
    
    conn.close()
    
    return render_template('peers.html', peers=peers_with_scores, search_query=search_query, company_name=company_name, company_ticker=company_ticker)

@app.route('/watchlist')
def watchlist():
    """Display the watchlist page."""
    return render_template('watchlist.html')

@app.route('/groups')
def groups():
    """Display the groups page."""
    return render_template('groups.html')

@app.route('/api/watchlist-data', methods=['POST'])
def watchlist_data():
    """API endpoint to get company data for watchlist tickers."""
    import json
    data = request.get_json()
    tickers = data.get('tickers', [])
    
    if not tickers:
        return json.dumps([])
    
    conn = get_db_connection()
    max_score = get_max_possible_score()
    
    # Get all scores for percentile and rank calculation
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
    all_scores = sorted([float(r['total_score']) for r in all_scores_rows])
    
    # Get global ranks
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
    global_ranks = {}
    for rank, row in enumerate(global_rank_rows, start=1):
        global_ranks[row['ticker']] = rank
    
    # Build query to get latest scores for requested tickers
    placeholders = ','.join(['?' for _ in tickers])
    scores_query = f"""
        SELECT s1.*
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            WHERE ticker IN ({placeholders})
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
        WHERE s1.ticker IN ({placeholders})
    """
    
    rows = conn.execute(scores_query, tickers + tickers).fetchall()
    
    companies = []
    for row in rows:
        company_dict = dict(row)
        total_score = float(company_dict.get('total_score', 0))
        score_percentage = int((total_score / max_score) * 100) if total_score > 0 else 0
        company_dict['score_percentage'] = min(score_percentage, 100)
        company_dict['percentile'] = calculate_percentile_rank(total_score, all_scores)
        company_dict['global_rank'] = global_ranks.get(company_dict['ticker'], 0)
        companies.append(company_dict)
    
    conn.close()
    
    return json.dumps(companies)

if __name__ == '__main__':
    app.run(debug=True, port=5001)

