import sys
import os

# Ensure the project root is in the path for absolute imports
# Calculate paths relative to this file
_file_dir = os.path.dirname(os.path.abspath(__file__))  # .../src/web/
_src_dir = os.path.dirname(_file_dir)  # .../src/
_project_root = os.path.dirname(_src_dir)  # .../ (project root)

# Add project root to sys.path so 'src' module can be found
# This handles cases where the app is run from different directories
if _project_root and _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Double-check: verify config exists at expected location
# If not, the path calculation might be wrong
_config_path = os.path.join(_src_dir, 'core', 'config.py')
if not os.path.exists(_config_path):
    # Try to find config.py by searching up the directory tree
    current = _project_root
    while current and current != os.path.dirname(current):
        test_path = os.path.join(current, 'src', 'core', 'config.py')
        if os.path.exists(test_path):
            if current not in sys.path:
                sys.path.insert(0, current)
            break
        current = os.path.dirname(current)

import sqlite3
import json
import shutil
import re
from flask import Flask, render_template, request
from src.core.config import TOP_SCORES_DB, PEERS_DB, TOP_COMPANIES_DB, AI_RELEVANCE_DB, GLASSDOOR_JSON

app = Flask(__name__)

# Base directory for relative paths in templates if needed
WEB_APP_DIR = os.path.dirname(os.path.abspath(__file__))

def get_db_connection():
    """Get database connection with error handling."""
    try:
        conn = sqlite3.connect(TOP_SCORES_DB)
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
    return {"status": "ok"}, 200

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/rankings')
def index():
    conn = get_db_connection()
    max_score = get_max_possible_score()
    
    page = request.args.get('page', 1, type=int)
    search_query_raw = request.args.get('search', '')
    search_query = search_query_raw.strip()
    per_page = 100
    
    base_query = """
        SELECT s1.*
        FROM scores s1
        JOIN (
            SELECT ticker, MAX(timestamp) as max_ts
            FROM scores
            GROUP BY ticker
        ) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
    """
    
    if search_query:
        search_upper = search_query.upper()
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
            base_query += " WHERE UPPER(s1.ticker) = ?"
            base_query += " ORDER BY s1.total_score DESC"
            rows = conn.execute(base_query, (search_upper,)).fetchall()
        else:
            search_prefix = f"{search_upper}%"
            base_query += " WHERE s1.ticker LIKE ? OR UPPER(s1.company_name) LIKE ?"
            base_query += " ORDER BY s1.total_score DESC"
            rows = conn.execute(base_query, (search_prefix, search_prefix)).fetchall()
    else:
        base_query += " ORDER BY s1.total_score DESC"
        rows = conn.execute(base_query).fetchall()
    
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
    global_ranks = {row['ticker']: rank for rank, row in enumerate(global_rank_rows, start=1)}
    
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
    
    total_companies = len(rows)
    total_pages = (total_companies + per_page - 1) // per_page
    if page < 1: page = 1
    elif page > total_pages and total_pages > 0: page = total_pages
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_rows = rows[start_idx:end_idx]
    
    companies = []
    for row in paginated_rows:
        company_dict = dict(row)
        total_score = float(company_dict.get('total_score', 0))
        company_dict['score_percentage'] = min(int((total_score / max_score) * 100), 100)
        company_dict['percentile'] = calculate_percentile_rank(total_score, all_scores)
        company_dict['global_rank'] = global_ranks.get(company_dict.get('ticker', ''), 0)
        companies.append(company_dict)
        
    pagination = {
        'page': page, 'per_page': per_page, 'total': total_companies,
        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
        'prev_page': page - 1 if page > 1 else None,
        'next_page': page + 1 if page < total_pages else None
    }
    return render_template('index.html', companies=companies, pagination=pagination, total_companies=total_all_companies, search_results_count=total_companies, search_query=search_query_raw, search_query_stripped=search_query)

@app.route('/company/<ticker>')
def company_detail(ticker):
    conn = get_db_connection()
    ticker_upper = ticker.upper()
    max_score = get_max_possible_score()
    
    query = "SELECT * FROM scores WHERE ticker = ? ORDER BY timestamp DESC LIMIT 1"
    row = conn.execute(query, (ticker_upper,)).fetchone()
    if not row:
        conn.close()
        return "Company not found", 404
        
    company = dict(row)
    total_score = float(company.get('total_score', 0))
    company['score_percentage'] = min(int((total_score / max_score) * 100), 100)
        
    all_latest_query = """
        SELECT total_score FROM scores s1
        JOIN (SELECT ticker, MAX(timestamp) as max_ts FROM scores GROUP BY ticker) s2 
        ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
    """
    all_rows = conn.execute(all_latest_query).fetchall()
    all_scores = sorted([float(r['total_score']) for r in all_rows])
    company['percentile'] = calculate_percentile_rank(total_score, all_scores)

    history_rows = conn.execute("SELECT * FROM scores WHERE ticker = ? ORDER BY timestamp DESC", (ticker_upper,)).fetchall()
    conn.close()
    return render_template('detail.html', company=company, history=[dict(h) for h in history_rows])

def get_peers_for_ticker(ticker):
    if not os.path.exists(PEERS_DB): return []
    conn = sqlite3.connect(PEERS_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT peer_name FROM company_peers WHERE ticker = ? ORDER BY peer_name', (ticker.upper(),))
    peers = [row['peer_name'] for row in cursor.fetchall()]
    conn.close()
    return peers

def find_company_in_top_companies(company_name):
    if not os.path.exists(TOP_COMPANIES_DB): return None
    conn = sqlite3.connect(TOP_COMPANIES_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Exact match
    cursor.execute('SELECT ticker, name, rank FROM companies_metadata WHERE UPPER(name) = UPPER(?) LIMIT 1', (company_name,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return {'ticker': result['ticker'], 'name': result['name'], 'rank': result['rank']}
    
    # Strip common suffixes
    suffixes = [' Communications', ' Inc', ' Inc.', ' Corporation', ' Corp', ' Corp.', 
                ' Company', ' Co', ' Co.', ' Limited', ' Ltd', ' Ltd.', ' LLC', ' L.L.C.',
                ' Technologies', ' Technology', ' Group', ' Electronics', ' Devices']
    base_name = company_name
    for suffix in suffixes:
        if company_name.endswith(suffix):
            base_name = company_name[:-len(suffix)].strip()
            break
            
    # 2. Base name match (if suffix was stripped)
    if base_name != company_name:
        cursor.execute('SELECT ticker, name, rank FROM companies_metadata WHERE UPPER(name) = UPPER(?) LIMIT 1', (base_name,))
        result = cursor.fetchone()
        if result:
            conn.close()
            return {'ticker': result['ticker'], 'name': result['name'], 'rank': result['rank']}

    # 3. Partial match with original name
    cursor.execute("SELECT ticker, name, rank FROM companies_metadata WHERE UPPER(name) LIKE '%' || UPPER(?) || '%' ORDER BY rank LIMIT 1", (company_name,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return {'ticker': result['ticker'], 'name': result['name'], 'rank': result['rank']}

    # 4. Partial match with base name (if suffix was stripped)
    if base_name != company_name:
        cursor.execute("SELECT ticker, name, rank FROM companies_metadata WHERE UPPER(name) LIKE '%' || UPPER(?) || '%' ORDER BY rank LIMIT 1", (base_name,))
        result = cursor.fetchone()
        if result:
            conn.close()
            return {'ticker': result['ticker'], 'name': result['name'], 'rank': result['rank']}

    conn.close()
    return None

@app.route('/api/company-suggestions')
def company_suggestions():
    query = request.args.get('q', '').strip().upper()
    if not query: return json.dumps([])
    conn = get_db_connection()
    search_query = """
        SELECT DISTINCT ticker, company_name FROM scores
        WHERE ticker LIKE ? OR UPPER(company_name) LIKE ?
        ORDER BY ticker LIMIT 10
    """
    results = conn.execute(search_query, (f"{query}%", f"%{query}%")).fetchall()
    conn.close()
    return json.dumps([{'ticker': r['ticker'], 'name': r['company_name']} for r in results])

@app.route('/peers')
def peers():
    conn = get_db_connection()
    max_score = get_max_possible_score()
    search_query = request.args.get('search', '').strip().upper()
    if not search_query:
        conn.close()
        return render_template('peers.html', peers=[], search_query='', company_name=None, company_ticker=None)
    
    company_query = "SELECT ticker, company_name FROM scores WHERE ticker = ? OR UPPER(company_name) LIKE ? LIMIT 1"
    company_row = conn.execute(company_query, (search_query, f"{search_query}%")).fetchone()
    if not company_row:
        conn.close()
        return render_template('peers.html', peers=[], search_query=search_query, error="Company not found")
    
    company_ticker = company_row['ticker']
    company_name = company_row['company_name']
    peer_names = get_peers_for_ticker(company_ticker)
    
    if not peer_names:
        conn.close()
        return render_template('peers.html', peers=[], search_query=search_query, company_name=company_name, company_ticker=company_ticker, error="No peers found for this company")

    # Percentiles and ranks
    all_scores_query = "SELECT total_score FROM scores s1 JOIN (SELECT ticker, MAX(timestamp) as max_ts FROM scores GROUP BY ticker) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts"
    all_scores = sorted([float(r['total_score']) for r in conn.execute(all_scores_query).fetchall()])
    
    global_rank_query = "SELECT s1.ticker FROM scores s1 JOIN (SELECT ticker, MAX(timestamp) as max_ts FROM scores GROUP BY ticker) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts ORDER BY s1.total_score DESC"
    global_ranks = {row['ticker']: r for r, row in enumerate(conn.execute(global_rank_query).fetchall(), 1)}
    
    peers_with_scores = []
    
    # Add company itself
    company_score_query = "SELECT * FROM scores WHERE ticker = ? ORDER BY timestamp DESC LIMIT 1"
    company_score_row = conn.execute(company_score_query, (company_ticker,)).fetchone()
    if company_score_row:
        d = dict(company_score_row)
        ts = float(d['total_score'])
        d.update({
            'score_percentage': min(int((ts / max_score) * 100), 100),
            'percentile': calculate_percentile_rank(ts, all_scores),
            'global_rank': global_ranks.get(company_ticker, 0),
            'peer_name': company_name,
            'is_searched_company': True,
            'has_score': True
        })
        peers_with_scores.append(d)

    for p_name in peer_names:
        info = find_company_in_top_companies(p_name)
        if info:
            score_row = conn.execute("SELECT * FROM scores WHERE ticker = ? ORDER BY timestamp DESC LIMIT 1", (info['ticker'],)).fetchone()
            if score_row:
                d = dict(score_row)
                ts = float(d['total_score'])
                d.update({
                    'score_percentage': min(int((ts / max_score) * 100), 100),
                    'percentile': calculate_percentile_rank(ts, all_scores),
                    'global_rank': global_ranks.get(info['ticker'], 0),
                    'peer_name': p_name,
                    'is_searched_company': False,
                    'has_score': True
                })
                peers_with_scores.append(d)
            else:
                peers_with_scores.append({
                    'ticker': info['ticker'], 'company_name': info['name'], 'total_score': 0,
                    'score_percentage': 0, 'percentile': 0, 'global_rank': 0,
                    'peer_name': p_name, 'is_searched_company': False, 'has_score': False
                })
    
    peers_with_scores.sort(key=lambda x: float(x.get('total_score', 0)), reverse=True)
    conn.close()
    return render_template('peers.html', peers=peers_with_scores, search_query=search_query, company_name=company_name, company_ticker=company_ticker)

@app.route('/watchlist')
def watchlist():
    return render_template('watchlist.html')

@app.route('/groups')
def groups():
    return render_template('groups.html')

@app.route('/api/watchlist-data', methods=['POST'])
def watchlist_data():
    data = request.get_json()
    tickers = data.get('tickers', [])
    if not tickers: return json.dumps([])
    
    conn = get_db_connection()
    max_score = get_max_possible_score()
    
    all_scores_query = "SELECT total_score FROM scores s1 JOIN (SELECT ticker, MAX(timestamp) as max_ts FROM scores GROUP BY ticker) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts"
    all_scores = sorted([float(r['total_score']) for r in conn.execute(all_scores_query).fetchall()])
    
    global_rank_query = "SELECT s1.ticker FROM scores s1 JOIN (SELECT ticker, MAX(timestamp) as max_ts FROM scores GROUP BY ticker) s2 ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts ORDER BY s1.total_score DESC"
    global_ranks = {row['ticker']: r for r, row in enumerate(conn.execute(global_rank_query).fetchall(), 1)}
    
    placeholders = ','.join(['?' for _ in tickers])
    scores_query = f"""
        SELECT s1.* FROM scores s1
        JOIN (SELECT ticker, MAX(timestamp) as max_ts FROM scores WHERE ticker IN ({placeholders}) GROUP BY ticker) s2 
        ON s1.ticker = s2.ticker AND s1.timestamp = s2.max_ts
        WHERE s1.ticker IN ({placeholders})
    """
    rows = conn.execute(scores_query, tickers + tickers).fetchall()
    
    companies = []
    for row in rows:
        d = dict(row)
        ts = float(d['total_score'])
        d.update({
            'score_percentage': min(int((ts / max_score) * 100), 100),
            'percentile': calculate_percentile_rank(ts, all_scores),
            'global_rank': global_ranks.get(d['ticker'], 0)
        })
        companies.append(d)
    conn.close()
    return json.dumps(companies)

@app.route('/glassdoor-backtest')
def glassdoor_backtest():
    return render_template('glassdoor.html')

@app.route('/api/glassdoor/summary')
def get_glassdoor_summary():
    path = os.path.join(os.path.dirname(GLASSDOOR_JSON), 'glassdoor_returns_summary.json')
    if os.path.exists(path):
        with open(path, 'r') as f: return json.load(f)
    return {"error": "Summary data not found"}, 404

@app.route('/api/glassdoor/benchmark-beat')
def get_glassdoor_benchmark_beat():
    path = os.path.join(os.path.dirname(GLASSDOOR_JSON), 'glassdoor_benchmark_beat.json')
    if os.path.exists(path):
        with open(path, 'r') as f: return json.load(f)
    return {"error": "Benchmark beat data not found"}, 404

@app.route('/api/glassdoor/years')
def get_glassdoor_years():
    dir_path = os.path.dirname(GLASSDOOR_JSON)
    years = []
    if os.path.exists(dir_path):
        for f in os.listdir(dir_path):
            m = re.match(r'glassdoor_(\d{4})_returns\.json', f)
            if m: years.append(int(m.group(1)))
    return {"years": sorted(years)}

@app.route('/api/glassdoor/year/<int:year>')
def get_glassdoor_year_details(year):
    dir_path = os.path.dirname(GLASSDOOR_JSON)
    returns_path = os.path.join(dir_path, f'glassdoor_{year}_returns.json')
    stocks_path = os.path.join(dir_path, f'glassdoor_{year}_stock_returns.json')
    
    result = {}
    portfolio_values = []
    if os.path.exists(returns_path):
        with open(returns_path, 'r') as f:
            data = json.load(f)
            portfolio_values = data.get('portfolio_values', [])
            # Ensure initial_value is set - use first portfolio value if not present
            if 'initial_value' not in data or data['initial_value'] is None:
                if portfolio_values and len(portfolio_values) > 0 and len(portfolio_values[0]) > 1:
                    data['initial_value'] = portfolio_values[0][1]
            result['returns'] = data
    
    if os.path.exists(stocks_path):
        with open(stocks_path, 'r') as f:
            result['stock_returns'] = json.load(f)

    if portfolio_values and len(portfolio_values) > 0:
        benchmark_path = os.path.join(dir_path, '..', '..', 'benchmark', 'spy_total_return_granular.json')
        if os.path.exists(benchmark_path):
            with open(benchmark_path, 'r') as f:
                benchmark_data = json.load(f)
                all_points = benchmark_data.get('history', [])
                if all_points:
                    # Get the portfolio start date (first entry)
                    portfolio_start_date = portfolio_values[0][0]
                    # Handle both ISO format with time and date-only format
                    if 'T' in portfolio_start_date:
                        start_date_iso = portfolio_start_date.split('T')[0]
                    else:
                        start_date_iso = portfolio_start_date
                    
                    # Find the benchmark value at or just before the portfolio start date
                    # Sort points by date to ensure we're searching correctly
                    sorted_points = sorted(all_points, key=lambda x: x[0])
                    
                    # Find initial benchmark value - get the closest date at or before start
                    initial_benchmark = None
                    for point in reversed(sorted_points):
                        point_date = point[0].split('T')[0] if 'T' in str(point[0]) else point[0]
                        if point_date <= start_date_iso:
                            initial_benchmark = point[1]
                            break
                    
                    # Fallback to first point if we couldn't find one before start
                    if initial_benchmark is None:
                        initial_benchmark = sorted_points[0][1]
                    
                    if initial_benchmark and initial_benchmark > 0:
                        benchmark_returns = []
                        for idx, p_entry in enumerate(portfolio_values):
                            # Get date from portfolio entry
                            portfolio_date = p_entry[0]
                            if 'T' in portfolio_date:
                                p_date_iso = portfolio_date.split('T')[0]
                            else:
                                p_date_iso = portfolio_date
                            
                            # Find the benchmark value for this date (at or before, using same logic)
                            best_val = None
                            for point in reversed(sorted_points):
                                point_date = point[0].split('T')[0] if 'T' in str(point[0]) else point[0]
                                if point_date <= p_date_iso:
                                    best_val = point[1]
                                    break
                            
                            if best_val is not None and best_val > 0:
                                # Calculate percentage return from portfolio start date
                                benchmark_return_pct = (best_val / initial_benchmark - 1) * 100
                                benchmark_returns.append([p_date_iso, benchmark_return_pct])
                            elif idx == 0:
                                # First entry should always be 0% (portfolio start = benchmark start)
                                benchmark_returns.append([p_date_iso, 0.0])
                        
                        if benchmark_returns:
                            result['benchmark_returns'] = benchmark_returns
            
    if not result: return {"error": f"Data for year {year} not found"}, 404
    return result

@app.route('/ai-relevance')
def ai_relevance():
    if not os.path.exists(AI_RELEVANCE_DB):
        return render_template('ai_relevance.html', companies=[], pagination={'total_pages': 0}, error="No AI relevance cache found.")
    
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip().upper()
    per_page = 100

    try:
        conn = sqlite3.connect(AI_RELEVANCE_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT ticker, score FROM relevance_scores ORDER BY score DESC, ticker ASC").fetchall()
        scored_data = {row['ticker']: row['score'] for row in rows}
        tickers = [row['ticker'] for row in rows]
        all_ai_scores = sorted([row['score'] for row in rows])
        conn.close()
    except Exception as e:
        return render_template('ai_relevance.html', companies=[], pagination={'total_pages': 0}, error=f"Error loading scored ranking: {e}")

    if not tickers: return render_template('ai_relevance.html', companies=[], pagination={'total_pages': 0}, error="Ranking is empty.")

    conn = sqlite3.connect(TOP_COMPANIES_DB)
    conn.row_factory = sqlite3.Row
    placeholders = ','.join(['?' for _ in tickers])
    metadata_rows = conn.execute(f"SELECT ticker, name, rank FROM companies_metadata WHERE ticker IN ({placeholders})", tickers).fetchall()
    company_map = {row['ticker']: dict(row) for row in metadata_rows}
    conn.close()
    
    all_companies = []
    for i, ticker in enumerate(tickers, 1):
        score = scored_data.get(ticker)
        comp = company_map.get(ticker, {'ticker': ticker, 'name': ticker, 'rank': 'N/A'})
        comp.update({'ai_score': score, 'ai_percentile': calculate_percentile_rank(score, all_ai_scores), 'ai_rank': i})
        all_companies.append(comp)
            
    filtered = [c for c in all_companies if not search_query or search_query in c['ticker'].upper() or search_query in c['name'].upper()]
    total_pages = (len(filtered) + per_page - 1) // per_page
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    start_idx = (page - 1) * per_page
    
    pagination = {
        'page': page, 
        'total_pages': total_pages, 
        'per_page': per_page,
        'has_prev': page > 1, 
        'has_next': page < total_pages, 
        'prev_page': page - 1, 
        'next_page': page + 1
    }
    return render_template('ai_relevance.html', 
                           companies=filtered[start_idx:start_idx+per_page], 
                           search_query=search_query, 
                           pagination=pagination,
                           total_count=len(all_companies),
                           filtered_count=len(filtered))

if __name__ == '__main__':
    app.run(debug=True, port=5001)
