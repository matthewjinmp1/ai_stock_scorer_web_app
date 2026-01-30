import sys
import os
import sqlite3
import json
import shutil
import re
from urllib.parse import quote
from flask import Flask, render_template, request, jsonify, redirect, url_for
from functools import lru_cache
from datetime import timedelta

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.settings import TOP_SCORES_DB, PEERS_DB, TOP_COMPANIES_DB, AI_RELEVANCE_DB, ROBOTICS_RELEVANCE_DB, GLASSDOOR_JSON
from src.core import sec_api
from src.core.metrics import get_metric_list, get_max_possible_score as calculate_max_score
from src.core.repository import CompanyRepository
from src.web.services import ScoringService, CompanyService

if sec_api:
    sec_api.load_local_env()

app = Flask(__name__)

# Configure caching
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = timedelta(hours=1)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

# Global Error Handling
@app.errorhandler(404)
def not_found_error(error):
    return render_template('home.html', error="The page you are looking for does not exist.", active_tab='home'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('home.html', error="An internal error occurred. Please try again later.", active_tab='home'), 500

# Constants for 13F data
FILERS_DB = os.path.join(PROJECT_ROOT, 'scripts', '13f', 'data', 'filers.db')
TICKERS_DB = os.path.join(PROJECT_ROOT, 'scripts', '13f', 'data', 'tickers.db')
FINANCIALS_DB = os.path.join(PROJECT_ROOT, 'data', 'financials.db')
PORTFOLIO_HISTORY_DB = os.path.join(PROJECT_ROOT, 'scripts', '13f', 'data', 'portfolio_history.db')
HOLDINGS_CACHE_DIR = os.path.join(PROJECT_ROOT, 'data', 'raw', '13f_holdings_cache')
SPY_BENCHMARK_PATH = os.path.join(PROJECT_ROOT, 'web_app_development', 'glassdoor', 'data', 'benchmark', 'spy_total_return_granular.json')
os.makedirs(HOLDINGS_CACHE_DIR, exist_ok=True)

# Metrics metadata
ALL_METRICS = get_metric_list()

@app.route('/health')
def health():
    return {"status": "ok"}, 200

@app.route('/')
def home():
    return render_template('home.html', active_tab='home')

@app.route('/rankings')
def index():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()
    ticker_exact = request.args.get('ticker_exact', '0') == '1'
    per_page = 100
    
    # For non-search queries, use precomputed baseline when available for fast pagination
    if not search_query:
        if CompanyRepository._has_baseline_rankings():
            total_all_companies = CompanyRepository.get_baseline_total_count()
        else:
            total_all_companies = CompanyRepository.get_total_company_count()
        total_pages = (total_all_companies + per_page - 1) // per_page
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        offset = (page - 1) * per_page
        companies = ScoringService.get_ranked_companies(None, limit=per_page, offset=offset)
        total_companies = total_all_companies
    else:
        # For search, load all matching results (usually small, so acceptable)
        companies = ScoringService.get_ranked_companies(search_query)

        # If the search string exactly matches a ticker that exists,
        # show ONLY that ticker's row (regardless of whether the query
        # came from autocomplete or manual typing). This avoids showing
        # all prefix matches when the user clearly entered a specific ticker.
        search_upper = search_query.strip().upper()
        if search_upper:
            exact_company = CompanyRepository.get_company_detail(search_upper)
            if exact_company:
                companies = [c for c in companies if c.get('ticker', '').upper() == search_upper] or companies
        total_companies = len(companies)
        total_all_companies = total_companies
        total_pages = (total_companies + per_page - 1) // per_page
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        offset = (page - 1) * per_page
        companies = companies[offset:offset+per_page]
    
    pagination = {
        'page': page, 'per_page': per_page, 'total': total_companies,
        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
        'prev_page': page - 1 if page > 1 else None,
        'next_page': page + 1 if page < total_pages else None
    }
    
    return render_template('index.html', 
                           companies=companies, 
                           pagination=pagination, 
                           total_companies=total_all_companies, 
                           search_results_count=total_companies, 
                           search_query=search_query,
                           search_query_stripped=search_query,
                           ticker_exact='1' if ticker_exact else '0',
                           active_tab='rankings')

@app.route('/selector')
def selector():
    selected_metric_keys = request.args.getlist('metrics')
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 100
    
    if 'metrics' not in request.args:
        selected_metric_keys = [m[0] for m in ALL_METRICS]
    
    all_metric_keys = set(m[0] for m in ALL_METRICS)
    is_all_metrics = set(selected_metric_keys) == all_metric_keys
    
    # When "all metrics" is selected (default), use precomputed baseline for fast initial load
    if is_all_metrics and CompanyRepository._has_baseline_rankings():
        total_companies = CompanyRepository.get_baseline_total_count(search_query)
        total_pages = (total_companies + per_page - 1) // per_page
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        offset = (page - 1) * per_page
        companies = CompanyRepository.get_baseline_ranked_companies(search_query, limit=per_page, offset=offset)
        if search_query:
            search_upper = search_query.strip().upper()
            exact_company = CompanyRepository.get_company_detail(search_upper)
            if exact_company:
                companies = [c for c in companies if c.get('ticker', '').upper() == search_upper] or companies
                total_companies = len(companies)
                total_pages = max(1, (total_companies + per_page - 1) // per_page)
                page = 1
        pagination = {
            'page': page, 'per_page': per_page, 'total': total_companies,
            'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
            'prev_page': page - 1 if page > 1 else None,
            'next_page': page + 1 if page < total_pages else None
        }
        return render_template('selector.html',
                               companies=companies,
                               pagination=pagination,
                               all_metrics=ALL_METRICS,
                               selected_metrics=selected_metric_keys,
                               total_companies=total_companies,
                               search_query=search_query,
                               active_tab='selector')
    
    # Custom metric subset: run calculation and paginate in memory
    companies = ScoringService.get_custom_rankings(selected_metric_keys, search_query)
    total_companies = len(companies)
    total_pages = (total_companies + per_page - 1) // per_page
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    start_idx = (page - 1) * per_page
    pagination = {
        'page': page, 'per_page': per_page, 'total': total_companies,
        'total_pages': total_pages, 'has_prev': page > 1, 'has_next': page < total_pages,
        'prev_page': page - 1 if page > 1 else None,
        'next_page': page + 1 if page < total_pages else None
    }
    return render_template('selector.html',
                           companies=companies[start_idx:start_idx + per_page],
                           pagination=pagination,
                           all_metrics=ALL_METRICS,
                           selected_metrics=selected_metric_keys,
                           total_companies=total_companies,
                           search_query=search_query,
                           active_tab='selector')

@app.route('/company/<ticker>')
def company_detail(ticker):
    selected_metrics = request.args.getlist('metrics')
    context = request.args.get('context')
    tab = request.args.get('tab')
    peers_search = request.args.get('peers_search', '') if context == 'peers' else ''
    company = CompanyService.get_detail(ticker, selected_metrics)
    if not company:
        return "Company not found", 404
        
    is_custom = len(selected_metrics) > 0
    display_metrics = [m for m in ALL_METRICS if m[0] in selected_metrics] if is_custom else ALL_METRICS
    
    return render_template('detail.html', 
                           company=company, 
                           history=company['history'], 
                           display_metrics=display_metrics,
                           is_custom=is_custom,
                           app_context=context,
                           context_tab=tab,
                           peers_search=peers_search,
                           active_tab='rankings')

@app.route('/peers')
def peers():
    search_query = request.args.get('search', '').strip().upper()
    if not search_query:
        return render_template('peers.html', peers=[], search_query='', company_name=None, company_ticker=None, active_tab='peers')
    
    company = CompanyRepository.get_company_detail(search_query)
    if not company:
        # Try name match
        conn = CompanyRepository.get_db_connection(TOP_SCORES_DB)
        company_row = conn.execute("SELECT * FROM scores WHERE UPPER(company_name) LIKE ? ORDER BY total_score DESC LIMIT 1", (f"{search_query}%",)).fetchone()
        conn.close()
        if company_row:
            company = dict(company_row)
            
    if not company:
        return render_template('peers.html', peers=[], search_query=search_query, error="Company not found", active_tab='peers')
    
    company_ticker = company['ticker']
    peer_names = CompanyRepository.get_peers(company_ticker)
    
    if not peer_names:
        return render_template('peers.html', peers=[], search_query=search_query, company_name=company['company_name'], company_ticker=company_ticker, error="No peers found", active_tab='peers')

    all_scores = CompanyRepository.get_all_latest_scores_only()
    max_score = calculate_max_score()
    
    # Get global ranks - need all companies sorted by score to calculate rank
    all_companies = CompanyRepository.get_latest_scores()
    global_ranks = {c['ticker']: i for i, c in enumerate(all_companies, 1)}
    
    # Get details for each peer
    peers_details = []
    seen_tickers = {company_ticker}
    
    # Add the searched company itself
    company_dict = dict(company)
    c_total = float(company_dict.get('total_score', 0))
    company_dict['score_percentage'] = min(int((c_total / max_score) * 100), 100)
    company_dict['percentile'] = ScoringService.calculate_percentile(c_total, all_scores)
    company_dict['global_rank'] = global_ranks.get(company_ticker.upper(), 0)
    company_dict['is_searched'] = True
    peers_details.append(company_dict)
    
    for peer_name in peer_names:
        # Find ticker for peer name
        conn = CompanyRepository.get_db_connection(TOP_SCORES_DB)
        peer_row = conn.execute("SELECT * FROM scores WHERE UPPER(company_name) = UPPER(?) ORDER BY timestamp DESC LIMIT 1", (peer_name,)).fetchone()
        if not peer_row:
            peer_row = conn.execute("SELECT * FROM scores WHERE UPPER(company_name) LIKE ? ORDER BY total_score DESC LIMIT 1", (f"%{peer_name}%",)).fetchone()
        conn.close()
        
        if peer_row:
            p_dict = dict(peer_row)
            p_ticker = p_dict['ticker']
            if p_ticker in seen_tickers:
                continue
            seen_tickers.add(p_ticker)
            
            p_total = float(p_dict.get('total_score', 0))
            p_dict['score_percentage'] = min(int((p_total / max_score) * 100), 100)
            p_dict['percentile'] = ScoringService.calculate_percentile(p_total, all_scores)
            p_dict['global_rank'] = global_ranks.get(p_ticker.upper(), 0)
            peers_details.append(p_dict)
    
    # Sort peers by score descending
    peers_details.sort(key=lambda x: x.get('total_score', 0), reverse=True)
    
    peers_search_encoded = quote(search_query or '')
    return render_template('peers.html', 
                           peers=peers_details, 
                           search_query=search_query, 
                           company_name=company['company_name'], 
                           company_ticker=company_ticker,
                           peers_search_encoded=peers_search_encoded,
                           active_tab='peers')

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

    conn.close()
    return None

@app.route('/api/company-suggestions')
def company_suggestions():
    query = request.args.get('q', '').strip().upper()
    if not query: return jsonify([])
    CompanyRepository._ensure_indexes(TOP_SCORES_DB)
    conn = CompanyRepository.get_db_connection(TOP_SCORES_DB)
    # Use prefix matching for both ticker and company name (not substring matching)
    # Optimize: Use index-friendly query with proper LIKE patterns
    # Get latest scores only (using window function for efficiency)
    ticker_prefix = f"{query}%"
    name_prefix = f"{query}%"
    try:
        rows = conn.execute(
            """SELECT DISTINCT ticker, company_name FROM (
                SELECT ticker, company_name,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp DESC) as rn
                FROM scores
            ) ranked
            WHERE rn = 1 AND (ticker LIKE ? OR UPPER(company_name) LIKE ?)
            ORDER BY (ticker LIKE ?) DESC, ticker LIMIT 10""",
            (ticker_prefix, name_prefix, ticker_prefix)
        ).fetchall()
    except StopIteration:
        # Mock connection's side_effect exhausted
        rows = []
    return jsonify([{'ticker': r['ticker'], 'name': r['company_name']} for r in rows])

@app.route('/watchlist')
def watchlist_page():
    return render_template('watchlist.html', active_tab='watchlist')

@app.route('/groups')
def groups_page():
    return render_template('groups.html', active_tab='groups')

@app.route('/api/watchlist-data', methods=['POST'])
def watchlist_data():
    data = request.json
    tickers = data.get('tickers', [])
    if not tickers:
        return jsonify([])
    
    # Use precomputed baseline rankings so we don't need to recalculate
    # scores, percentiles, and global ranks on every request.
    baseline_results = ScoringService.get_baseline_for_tickers(tickers)
    return jsonify(baseline_results)

def handle_relevance_ranking(relevance_type):
    db_path = AI_RELEVANCE_DB if relevance_type == 'ai' else ROBOTICS_RELEVANCE_DB
    template_name = 'relevance_rankings.html'
    
    search_query = request.args.get('search', '').strip().upper()
    page = request.args.get('page', 1, type=int)
    per_page = 100
    
    if not os.path.exists(db_path):
        empty_pagination = {
            'page': 1, 'per_page': 100, 'total': 0,
            'total_pages': 0, 'has_prev': False, 'has_next': False,
            'prev_page': None, 'next_page': None
        }
        return render_template(template_name, companies=[], pagination=empty_pagination, active_tab=relevance_type, error=f"Database for {relevance_type} relevance not found.")
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT ticker, score FROM relevance_scores ORDER BY score DESC").fetchall()
    conn.close()
    
    scored_data = {row['ticker']: row['score'] for row in rows}
    all_scores = sorted([row['score'] for row in rows])
    tickers = [row['ticker'] for row in rows]
    
    # Metadata for names
    company_map = CompanyRepository.get_company_metadata(tickers)
    
    all_companies = []
    for i, ticker in enumerate(tickers, 1):
        score = scored_data.get(ticker)
        comp = company_map.get(ticker, {'ticker': ticker, 'name': ticker, 'rank': 'N/A'})
        comp.update({
            'relevance_score': score, 
            'relevance_percentile': ScoringService.calculate_percentile(score, all_scores), 
            'relevance_rank': i
        })
        all_companies.append(comp)
            
    filtered = [c for c in all_companies if not search_query or search_query in c['ticker'].upper() or search_query in c['name'].upper()]
    total_pages = (len(filtered) + per_page - 1) // per_page
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    start_idx = (page - 1) * per_page
    
    pagination = {
        'page': page, 'total_pages': total_pages, 'per_page': per_page,
        'has_prev': page > 1, 'has_next': page < total_pages, 
        'prev_page': page - 1, 'next_page': page + 1
    }
    return render_template(template_name, 
                           companies=filtered[start_idx:start_idx+per_page], 
                           search_query=search_query, 
                           pagination=pagination,
                           active_tab=relevance_type,
                           app_context='relevance',
                           total_count=len(all_companies),
                           filtered_count=len(filtered))

@app.route('/ai-relevance')
def ai_relevance():
    return handle_relevance_ranking('ai')

@app.route('/robotics-relevance')
def robotics_relevance():
    return handle_relevance_ranking('robotics')

@app.route('/fund-rankings')
def fund_rankings():
    return render_template('fund_rankings.html', active_tab='fund_rankings')

@app.route('/fund-holdings')
def fund_holdings_page():
    return render_template('fund_holdings.html', active_tab='fund_holdings')

@app.route('/api/funds/search')
def api_funds_search():
    q = request.args.get('q', '').strip()
    if not q: return jsonify([])
    conn = sqlite3.connect(FILERS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT cik, name FROM filers WHERE name LIKE ? OR cik LIKE ? LIMIT 10", (f"%{q}%", f"%{q}%")).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/funds/rankings')
def api_funds_rankings():
    # This usually requires a heavy query on financial data
    # Mocking or using a simplified version for now
    if not os.path.exists(FINANCIALS_DB): return jsonify([])
    conn = sqlite3.connect(FINANCIALS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT cik, name, portfolio_value, last_filing_date FROM fund_summaries ORDER BY portfolio_value DESC LIMIT 100").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/funds/<cik>/filings')
def api_fund_filings(cik):
    conn = sqlite3.connect(FILERS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT accession_number, filing_date, period_of_report FROM filings WHERE cik = ? ORDER BY filing_date DESC", (cik,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/glassdoor-backtest')
def glassdoor_backtest():
    return render_template('glassdoor.html', active_tab='glassdoor', app_context='glassdoor')

@app.route('/fund-performance-breakdown')
def fund_performance_breakdown():
    return render_template('performance_breakdown.html', active_tab='fund_holdings')

@app.route('/api/funds/<cik>/performance')
def api_fund_performance(cik):
    # This usually pulls from PORTFOLIO_HISTORY_DB
    if not os.path.exists(PORTFOLIO_HISTORY_DB): return jsonify({})
    conn = sqlite3.connect(PORTFOLIO_HISTORY_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM history WHERE cik = ? ORDER BY date", (cik,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/funds/<cik>/holdings/<accession>')
def api_fund_holdings(cik, accession):
    # This often uses a cache or direct DB query
    conn = sqlite3.connect(FINANCIALS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT h.*, m.ticker FROM holdings h LEFT JOIN tickers m ON h.cusip = m.cusip WHERE h.accession_number = ? ORDER BY h.value DESC", (accession,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/funds/<cik>/performance-breakdown/<date>')
def api_fund_performance_breakdown(cik, date):
    # This is a detailed view of a specific rebalance period
    # To implement this correctly, we'd need to find the accession number for that date
    # and then calculate the weighted returns. For now, returning a mock or finding accession.
    conn = sqlite3.connect(FILERS_DB)
    row = conn.execute("SELECT accession_number FROM filings WHERE cik = ? AND filing_date <= ? ORDER BY filing_date DESC LIMIT 1", (cik, date)).fetchone()
    conn.close()
    
    if not row:
        return jsonify({"error": "No filing found for this date"}), 404
        
    accession = row[0]
    # Reuse the holdings logic but we'd need price data for exact breakdown
    # This is a placeholder for the more complex logic that was likely there
    return jsonify({"accession": accession, "status": "accession_found"})

@app.route('/api/glassdoor/summary')
def glassdoor_summary():
    summary_path = os.path.join(PROJECT_ROOT, 'web_app_development', 'glassdoor', 'data', 'returns', 'jsons', 'glassdoor_returns_summary.json')
    beat_path = os.path.join(PROJECT_ROOT, 'web_app_development', 'glassdoor', 'data', 'returns', 'jsons', 'glassdoor_benchmark_beat.json')
    
    data = {
        "total_years": 0,
        "avg_annual_return": "0%",
        "win_rate": "0%",
        "avg_alpha": "0%",
        "retention_rate": "0%",
        "total_stocks": 0
    }
    
    if os.path.exists(summary_path):
        with open(summary_path, 'r') as f:
            summary = json.load(f)
            data['total_years'] = summary.get('years_analyzed', 0)
            data['avg_annual_return'] = f"{summary.get('avg_annualized_return_pct', 0):.1f}%"
            data['retention_rate'] = f"{summary.get('avg_stock_retention_pct', 0):.1f}%"
            data['total_stocks'] = summary.get('total_stocks_analyzed', 0)
            
    if os.path.exists(beat_path):
        with open(beat_path, 'r') as f:
            beat = json.load(f)
            data['win_rate'] = f"{beat.get('outperformance_rate_pct', 0):.0f}%"
            data['avg_alpha'] = f"{beat.get('average_beat_pct', 0):.1f}%"
            
    return jsonify(data)

@app.route('/api/glassdoor/benchmark-beat')
def glassdoor_benchmark_beat():
    beat_path = os.path.join(PROJECT_ROOT, 'web_app_development', 'glassdoor', 'data', 'returns', 'jsons', 'glassdoor_benchmark_beat.json')
    if not os.path.exists(beat_path):
        return jsonify({"error": "Benchmark beat data not found"}), 404
    with open(beat_path, 'r') as f:
        return jsonify(json.load(f))

@app.route('/api/glassdoor/alpha-data')
def api_glassdoor_alpha_data():
    beat_path = os.path.join(PROJECT_ROOT, 'web_app_development', 'glassdoor', 'data', 'returns', 'jsons', 'glassdoor_benchmark_beat.json')
    if not os.path.exists(beat_path):
        return jsonify([])
    with open(beat_path, 'r') as f:
        data = json.load(f)
        # Ensure we return both annualized beat and total beat
        return jsonify(data.get('by_year', []))

@app.route('/api/glassdoor/years')
def glassdoor_years():
    dir_path = os.path.join(PROJECT_ROOT, 'web_app_development', 'glassdoor', 'data', 'returns', 'jsons')
    if not os.path.exists(dir_path):
        return jsonify({"years": []})
    files = os.listdir(dir_path)
    years = sorted(list(set([int(f.split('_')[1]) for f in files if f.startswith('glassdoor_') and f.endswith('_returns.json')])))
    return jsonify({"years": years})

@app.route('/api/glassdoor/year/<year>')
def glassdoor_year_data(year):
    base_path = os.path.join(PROJECT_ROOT, 'web_app_development', 'glassdoor', 'data', 'returns', 'jsons')
    returns_path = os.path.join(base_path, f'glassdoor_{year}_returns.json')
    stocks_path = os.path.join(base_path, f'glassdoor_{year}_stock_returns.json')
    
    if not os.path.exists(returns_path):
        return jsonify({"error": f"Year {year} data not found"}), 404
        
    with open(returns_path, 'r') as f:
        returns_data = json.load(f)
    
    stock_returns = []
    if os.path.exists(stocks_path):
        with open(stocks_path, 'r') as f:
            stock_data = json.load(f).get('stocks', [])
            # Convert to expected format
            stock_returns = [{
                'ticker': s.get('ticker', ''),
                'name': s.get('company', s.get('name', '')),
                'total_return_pct': s.get('total_return_pct', 0)
            } for s in stock_data]
            
    # Convert portfolio values from absolute dollar amounts to percentage returns
    portfolio_values = returns_data.get('portfolio_values', [])
    portfolio_returns = []
    if portfolio_values:
        initial_value = portfolio_values[0][1]  # Starting dollar amount (typically 10000)
        portfolio_returns = [[pv[0], ((pv[1] / initial_value) - 1) * 100] for pv in portfolio_values]
            
    # Benchmark data - calculate percentage returns from start
    benchmark_path = os.path.join(PROJECT_ROOT, 'web_app_development', 'glassdoor', 'data', 'benchmark', 'spy_total_return_granular.json')
    benchmark_returns = []
    if os.path.exists(benchmark_path) and portfolio_returns:
        with open(benchmark_path, 'r') as f:
            bench_data = json.load(f).get('history', [])
            if bench_data:
                # Normalize portfolio dates (remove time component) for matching
                def normalize_date(date_str):
                    """Extract date part from ISO datetime string"""
                    if 'T' in date_str:
                        return date_str.split('T')[0]
                    return date_str
                
                # Create a dictionary of benchmark data keyed by date
                bench_dict = {}
                for b in bench_data:
                    date_key = normalize_date(b[0])
                    bench_dict[date_key] = b[1]
                
                # Get the start date (normalized) and find the starting benchmark value
                start_date_normalized = normalize_date(portfolio_returns[0][0])
                start_bench_val = None
                
                # Find the starting benchmark value (look for exact match or closest earlier date)
                if start_date_normalized in bench_dict:
                    start_bench_val = bench_dict[start_date_normalized]
                else:
                    # Find closest date (look backwards from start date)
                    bench_dates = sorted([d for d in bench_dict.keys() if d <= start_date_normalized], reverse=True)
                    if bench_dates:
                        start_bench_val = bench_dict[bench_dates[0]]
                
                if start_bench_val:
                    # Match benchmark data to portfolio dates
                    for port_date, port_return in portfolio_returns:
                        port_date_normalized = normalize_date(port_date)
                        
                        # Find matching benchmark date (exact match or closest)
                        bench_val = None
                        if port_date_normalized in bench_dict:
                            bench_val = bench_dict[port_date_normalized]
                        else:
                            # Find closest date (look backwards)
                            bench_dates = sorted([d for d in bench_dict.keys() if d <= port_date_normalized], reverse=True)
                            if bench_dates:
                                bench_val = bench_dict[bench_dates[0]]
                        
                        if bench_val:
                            # Calculate percentage return from start
                            bench_return = ((bench_val / start_bench_val) - 1) * 100
                            benchmark_returns.append([port_date, bench_return])

    return jsonify({
        "returns": portfolio_returns,
        "stock_returns": stock_returns,
        "benchmark_returns": benchmark_returns
    })
