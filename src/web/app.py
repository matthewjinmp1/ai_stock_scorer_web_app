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

from src.core.settings import (
    TOP_SCORES_DB, PEERS_DB, TOP_COMPANIES_DB, DATA_DIR,
    AI_RELEVANCE_DB, ROBOTICS_RELEVANCE_DB, GLASSDOOR_JSON, TRAIT_SCORES_JSON,
)
UNIFIED_RELEVANCE_CACHE = os.path.join(DATA_DIR, 'batch_relevance_scores.json')
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


# Trailing legal/entity suffixes to strip (case-insensitive). Combined forms first, then single.
_FUND_NAME_SUFFIXES = [
    r',?\s+Co\.?,?\s*Ltd\.?\s*$',           # Co., Ltd. / Co, Ltd
    r',?\s+(Inc\.?|Incorporated)\s*$',
    r',?\s+(LLC\.?|L\.L\.C\.?)\s*$',
    r',?\s+(LLP\.?|L\.L\.P\.?)\s*$',
    r',?\s+(Corp\.?|Corporation)\s*$',
    r',?\s+Co\.?\s*$',                       # Co / Co. (company)
    r',?\s+(Ltd\.?|Limited)\s*$',
    r',?\s+L\.?P\.?\s*$',                    # LP (limited partnership)
    r',?\s+N\.?A\.?\s*$',                    # N.A. (e.g. Bank N.A.)
    r',?\s+S\.?A\.?\s*$',                    # S.A. (société anonyme)
    r',?\s+P\.?L\.?C\.?\s*$',                # PLC (UK)
    r',?\s+N\.?V\.?\s*$',                    # NV (Dutch)
    r',?\s+AG\s*$',                          # AG (German/Swiss)
    r',?\s+/DE/?\s*$',
    r',?\s+Company\s*$',
]


def normalize_fund_name(name):
    """Normalize fund name: title case and strip trailing legal/entity suffixes (Inc., LLC, Co., Ltd., Co., Ltd., etc.)."""
    if not name or not isinstance(name, str):
        return name or ''
    s = name.strip()
    while True:
        prev = s
        for pat in _FUND_NAME_SUFFIXES:
            s = re.sub(pat, '', s, flags=re.IGNORECASE)
        s = s.strip().rstrip(',').strip()
        if s == prev:
            break
    return s.title() if s else ''


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
    # When search is an exact ticker, show only that stock
    if search_query:
        search_upper = search_query.strip().upper()
        if CompanyRepository.get_company_detail(search_upper):
            companies = [c for c in companies if c.get('ticker', '').upper() == search_upper] or companies
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
    return_to = request.args.get('return_to', '')
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
                           return_to=return_to,
                           active_tab='rankings')

def _get_peers_data(search_query):
    """Shared logic: resolve company, fetch peers, return (company, peers_details, error). error is None on success."""
    if not search_query:
        return None, [], None
    company = CompanyRepository.get_company_detail(search_query)
    if not company:
        conn = CompanyRepository.get_db_connection(TOP_SCORES_DB)
        company_row = conn.execute("SELECT * FROM scores WHERE UPPER(company_name) LIKE ? ORDER BY total_score DESC LIMIT 1", (f"{search_query}%",)).fetchone()
        conn.close()
        if company_row:
            company = dict(company_row)
    if not company:
        return None, [], "Company not found"
    company_ticker = company['ticker']
    peer_names = CompanyRepository.get_peers(company_ticker)
    if not peer_names:
        return company, [], "No peers found"
    all_scores = CompanyRepository.get_all_latest_scores_only()
    max_score = calculate_max_score()
    all_companies = CompanyRepository.get_latest_scores()
    global_ranks = {c['ticker']: i for i, c in enumerate(all_companies, 1)}
    peers_details = []
    seen_tickers = {company_ticker}
    company_dict = dict(company)
    c_total = float(company_dict.get('total_score', 0))
    company_dict['score_percentage'] = min(int((c_total / max_score) * 100), 100)
    company_dict['percentile'] = ScoringService.calculate_percentile(c_total, all_scores)
    company_dict['global_rank'] = global_ranks.get(company_ticker.upper(), 0)
    company_dict['is_searched'] = True
    peers_details.append(company_dict)
    for peer_name in peer_names:
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
    peers_details.sort(key=lambda x: x.get('total_score', 0), reverse=True)
    return company, peers_details, None


@app.route('/peers')
def peers():
    search_query = request.args.get('search', '').strip().upper()
    if not search_query:
        return render_template('peers.html', peers=[], search_query='', company_name=None, company_ticker=None, active_tab='peers')
    company, peers_details, error = _get_peers_data(search_query)
    if error:
        return render_template('peers.html', peers=[], search_query=search_query,
                               company_name=company['company_name'] if company else None,
                               company_ticker=company['ticker'] if company else None,
                               error=error, active_tab='peers')
    peers_search_encoded = quote(search_query or '')
    return render_template('peers.html',
                           peers=peers_details,
                           search_query=search_query,
                           company_name=company['company_name'],
                           company_ticker=company['ticker'],
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

# Single source of truth for all relevance ranking tabs. Add a new entry here to add a new tab.
# display_name: page title / h1. nav_label: tab label in nav. accent: key for ACCENT_STYLES. subtitle: short description under h1.
#
# Turn off specific tabs in one place: add their keys here. Disabled tabs are hidden from nav and redirect to the first enabled tab.
RELEVANCE_TABS_DISABLED = set()  # e.g. {'robotics', 'tandem_company'} to hide those tabs

RELEVANCE_TYPES = [
    {
        'key': 'ai',
        'url_path': '/ai-relevance',
        'endpoint': 'ai_relevance',
        'source': 'db',
        'path': None,  # set below
        'empty_message': 'AI relevance database not found.',
        'display_name': 'AI Relevance',
        'nav_label': 'AI Relevance',
        'accent': 'blue',
        'subtitle': 'Companies Sorted by AI Relevance',
    },
    {
        'key': 'robotics',
        'url_path': '/robotics-relevance',
        'endpoint': 'robotics_relevance',
        'source': 'db',
        'path': None,
        'empty_message': 'Robotics relevance database not found.',
        'display_name': 'Robotics Relevance',
        'nav_label': 'Robotics Relevance',
        'accent': 'purple',
        'subtitle': 'Companies Sorted by Robotics Relevance',
    },
    {
        'key': 'company_score',
        'url_path': '/company-score',
        'endpoint': 'company_score_relevance',
        'source': 'trait_json',
        'path': None,
        'empty_message': 'Disruptive Innovators ranking not found. Run scripts/rate_top_100_traits.py to generate it.',
        'display_name': 'Disruptive Innovators',
        'nav_label': 'Disruptive Innovators',
        'accent': 'amber',
        'subtitle': 'Ambition & innovation trait scores',
    },
    {
        'key': 'tech_disruptor_ai',
        'url_path': '/tech-disruptor-relevance',
        'endpoint': 'tech_disruptor_relevance',
        'source': 'db',
        'path': None,
        'empty_message': 'Tech Disruptor scores not found. Run batch_relevance_scores.py or convert_relevance_json_to_db.py.',
        'display_name': 'Tech Disruptor',
        'nav_label': 'Tech Disruptor',
        'accent': 'teal',
        'subtitle': 'Tech disruptor / AI innovator',
    },
    {
        'key': 'tandem_company',
        'url_path': '/tandem-relevance',
        'endpoint': 'tandem_relevance',
        'source': 'db',
        'path': None,
        'empty_message': 'Tandem Company scores not found. Run batch_relevance_scores.py or convert_relevance_json_to_db.py.',
        'display_name': 'Tandem Companies',
        'nav_label': 'Tandem',
        'accent': 'indigo',
        'subtitle': 'Tandem company (consistent, disciplined, dividend-focused)',
    },
    {
        'key': 'all_weather',
        'url_path': '/all-weather-relevance',
        'endpoint': 'all_weather_relevance',
        'source': 'db',
        'path': None,
        'empty_message': 'All-Weather Company scores not found. Run batch_relevance_scores.py or convert_relevance_json_to_db.py.',
        'display_name': 'All-Weather',
        'nav_label': 'All-Weather',
        'accent': 'emerald',
        'subtitle': 'All-weather: consistent, low volatility, proven quality',
    },
    {
        'key': 'durable_advantage',
        'url_path': '/durable-advantage-relevance',
        'endpoint': 'durable_advantage_relevance',
        'source': 'db',
        'path': None,
        'empty_message': 'The Buffett scores not found. Run batch_relevance_scores.py or convert_relevance_json_to_db.py.',
        'display_name': 'The Buffett',
        'nav_label': 'The Buffett',
        'accent': 'violet',
        'subtitle': 'Wide moat, consistent financials, rational management, margin of safety',
    },
    {
        'key': 'ai_disruption_risk',
        'url_path': '/ai-disruption-risk-relevance',
        'endpoint': 'ai_disruption_risk_relevance',
        'source': 'db',
        'path': None,
        'empty_message': 'AI Disruption Risk scores not found. Run batch_relevance_scores.py or convert_relevance_json_to_db.py.',
        'display_name': 'AI Disruption Risk',
        'nav_label': 'AI Disruption Risk',
        'accent': 'rose',
        'subtitle': 'At risk of or currently being disrupted by AI (0–100)',
    },
]

# Tailwind classes per accent (nav=active tab, ticker=badge, gradient=h1/percentile, row=searched row).
ACCENT_STYLES = {
    'blue': {
        'nav': 'text-blue-400 border-b-2 border-blue-400 font-semibold',
        'ticker': 'bg-blue-900/50 text-blue-300 border-blue-700',
        'gradient': 'from-blue-400 to-emerald-400',
        'row': 'bg-blue-900/20',
    },
    'purple': {
        'nav': 'text-purple-400 border-b-2 border-purple-400 font-semibold',
        'ticker': 'bg-purple-900/50 text-purple-300 border-purple-700',
        'gradient': 'from-purple-400 to-blue-400',
        'row': 'bg-purple-900/20',
    },
    'amber': {
        'nav': 'text-amber-400 border-b-2 border-amber-400 font-semibold',
        'ticker': 'bg-amber-900/50 text-amber-300 border-amber-700',
        'gradient': 'from-amber-400 to-orange-400',
        'row': 'bg-amber-900/20',
    },
    'teal': {
        'nav': 'text-teal-400 border-b-2 border-teal-400 font-semibold',
        'ticker': 'bg-teal-900/50 text-teal-300 border-teal-700',
        'gradient': 'from-teal-400 to-cyan-400',
        'row': 'bg-teal-900/20',
    },
    'indigo': {
        'nav': 'text-indigo-400 border-b-2 border-indigo-400 font-semibold',
        'ticker': 'bg-indigo-900/50 text-indigo-300 border-indigo-700',
        'gradient': 'from-indigo-400 to-violet-400',
        'row': 'bg-indigo-900/20',
    },
    'emerald': {
        'nav': 'text-emerald-400 border-b-2 border-emerald-400 font-semibold',
        'ticker': 'bg-emerald-900/50 text-emerald-300 border-emerald-700',
        'gradient': 'from-emerald-400 to-green-400',
        'row': 'bg-emerald-900/20',
    },
    'violet': {
        'nav': 'text-violet-400 border-b-2 border-violet-400 font-semibold',
        'ticker': 'bg-violet-900/50 text-violet-300 border-violet-700',
        'gradient': 'from-violet-400 to-purple-400',
        'row': 'bg-violet-900/20',
    },
    'rose': {
        'nav': 'text-rose-400 border-b-2 border-rose-400 font-semibold',
        'ticker': 'bg-rose-900/50 text-rose-300 border-rose-700',
        'gradient': 'from-rose-400 to-red-400',
        'row': 'bg-rose-900/20',
    },
}

def _enabled_relevance_types():
    """Return list of relevance type configs that are not in RELEVANCE_TABS_DISABLED."""
    return [r for r in RELEVANCE_TYPES if r['key'] not in RELEVANCE_TABS_DISABLED]


def _first_enabled_relevance_key():
    """Return the key of the first enabled tab (for redirects when a disabled tab is requested)."""
    enabled = _enabled_relevance_types()
    return enabled[0]['key'] if enabled else 'ai'


def _relevance_nav_context(relevance_type):
    """Build nav list and current-accent context for relevance templates. Returns dict to merge into template context."""
    cfg = _relevance_config(relevance_type)
    if not cfg:
        return {}
    relevance_nav_list = [
        {'key': r['key'], 'url_path': r['url_path'], 'nav_label': r['nav_label'], 'accent': r['accent']}
        for r in _enabled_relevance_types()
    ]
    accent = cfg.get('accent', 'blue')
    return {
        'relevance_nav_list': relevance_nav_list,
        'accent_styles': ACCENT_STYLES,
        'current_accent': accent,
        'current_display_name': cfg.get('display_name', relevance_type),
        'current_subtitle': cfg.get('subtitle', ''),
    }

# Resolve DB paths (cannot reference at class-def time)
DB_DIR = os.path.join(DATA_DIR, 'db')
for _r in RELEVANCE_TYPES:
    if _r['key'] == 'ai':
        _r['path'] = AI_RELEVANCE_DB
    elif _r['key'] == 'robotics':
        _r['path'] = ROBOTICS_RELEVANCE_DB
    elif _r['key'] == 'company_score':
        _r['path'] = TRAIT_SCORES_JSON
    elif _r['key'] == 'tech_disruptor_ai':
        # Use round-scores DB for the Tech Disruptor tab
        _r['path'] = os.path.join(DB_DIR, 'tech_disruptor_ai_round_relevance_scores.db')
    elif _r.get('source') == 'db' and _r.get('path') is None:
        _r['path'] = os.path.join(DB_DIR, f"{_r['key']}_relevance_scores.db")

def _relevance_config(relevance_type):
    """Return config dict for a relevance type, or None if unknown."""
    for r in RELEVANCE_TYPES:
        if r['key'] == relevance_type:
            return r
    return None

def _relevance_url_path(relevance_type):
    """URL path prefix for a relevance tab."""
    cfg = _relevance_config(relevance_type)
    return cfg['url_path'] if cfg else f'/{relevance_type}-relevance'


def _market_cap_to_number(market_cap_raw):
    """Convert market_cap from top_companies.db (e.g. '$4.638 T', '$966.15 B', '$500 M') to USD number. T=trillion, B=billion, M=million. Returns 0.0 if missing/invalid."""
    if not market_cap_raw or not str(market_cap_raw).strip():
        return 0.0
    s = str(market_cap_raw).strip().upper().replace(",", "")
    if s in ("N/A", "NA", "-", ""):
        return 0.0
    match = re.search(r"[\$]?\s*([\d.]+)\s*([TBM])?\s*$", s)
    if not match:
        return 0.0
    try:
        num = float(match.group(1))
    except ValueError:
        return 0.0
    letter = (match.group(2) or "").upper()
    if letter == "T":
        return num * 1e12
    if letter == "B":
        return num * 1e9
    if letter == "M":
        return num * 1e6
    return num


def _load_all_market_caps_from_top_companies_db():
    """Load every ticker -> market_cap (as number) from top_companies.db companies_metadata. One query, no IN clause. Returns dict: UPPER(ticker) -> USD float; also keyed by canonical (dot->dash) so BRK.B finds BRK-B."""
    # Use PROJECT_ROOT so path is correct regardless of cwd (same as rest of app.py)
    path = os.path.join(PROJECT_ROOT, "data", "db", "top_companies.db")
    if not os.path.exists(path):
        path = TOP_COMPANIES_DB  # fallback to settings path
        if not os.path.exists(path):
            return {}
    result = {}
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("PRAGMA table_info(companies_metadata)")
        if "market_cap" not in [r[1] for r in cur.fetchall()]:
            conn.close()
            return {}
        rows = conn.execute("SELECT ticker, market_cap FROM companies_metadata").fetchall()
        conn.close()
        for row in rows:
            ticker = (row["ticker"] or "").strip()
            if not ticker:
                continue
            # sqlite3.Row has no .get(); use [] (raises if column missing)
            cap = _market_cap_to_number(row["market_cap"])
            key_upper = ticker.upper()
            result[key_upper] = cap
            result[key_upper.replace(".", "-")] = cap
    except Exception:
        pass
    return result


def _normalize_relevance_ranking(rows):
    """
    Build final ranking: fetch market caps from top companies DB, sort by score then market cap, then assign rank and percentile.
    rows = list of dicts with ticker, name, score (numeric). Tickers are used as-is for cap lookup (UPPER match).
    """
    if not rows:
        return []
    cleaned = []
    for r in rows:
        ticker = (r.get('ticker') or '').strip()
        if not ticker:
            continue
        score = r.get('score')
        if score is None:
            continue
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        name = (r.get('name') or ticker).strip()
        cleaned.append({'ticker': ticker, 'name': name, 'score': score})
    if not cleaned:
        return []

    # 1. Load all market caps from top companies DB (ticker -> number; T/B/M converted)
    market_caps = _load_all_market_caps_from_top_companies_db()

    # 2. Attach market cap number to each row (0 if ticker not in top companies)
    for c in cleaned:
        k = (c['ticker'] or '').upper()
        cap = market_caps.get(k, 0.0) or market_caps.get(k.replace(".", "-"), 0.0)
        c['market_cap_usd'] = cap

    # 3. Sort by score desc, then market cap desc (larger cap first), then ticker
    cleaned.sort(key=lambda x: (-x['score'], -x['market_cap_usd'], (x['ticker'] or '').upper()))

    # 4. Assign rank and percentile
    all_scores = sorted(c['score'] for c in cleaned)
    rank = 1
    prev_score = None
    result = []
    for i, c in enumerate(cleaned):
        if prev_score is not None and c['score'] != prev_score:
            rank = i + 1
        pct = ScoringService.calculate_percentile(c['score'], all_scores) if all_scores else 0
        result.append({
            'ticker': c['ticker'],
            'name': c['name'],
            'relevance_score': c['score'],
            'relevance_percentile': min(100, pct),
            'relevance_rank': rank,
        })
        prev_score = c['score']
    return result


def get_relevance_ranking(relevance_type):
    """Single source of truth: load ranking for a relevance type. Returns list of dicts with ticker, name, relevance_score, relevance_percentile, relevance_rank. Empty list if no data."""
    cfg = _relevance_config(relevance_type)
    if not cfg:
        return []

    if cfg['source'] == 'db':
        path = cfg.get('path')
        if not path or not os.path.exists(path):
            return []
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT ticker, score FROM relevance_scores WHERE score IS NOT NULL ORDER BY score DESC").fetchall()
        conn.close()
        tickers = [r['ticker'] for r in rows]
        company_map = CompanyRepository.get_company_metadata(tickers)
        raw = [{'ticker': r['ticker'], 'name': (company_map.get(r['ticker'], {}).get('name') or r['ticker']), 'score': float(r['score'])} for r in rows]
        return _normalize_relevance_ranking(raw)

    if cfg['source'] == 'unified_cache':
        prompt_key = cfg.get('prompt_key') or relevance_type
        if not os.path.exists(UNIFIED_RELEVANCE_CACHE):
            return []
        try:
            with open(UNIFIED_RELEVANCE_CACHE, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        section = (data.get('prompts') or {}).get(prompt_key)
        scores = (section or {}).get('scores') or []
        raw = [{'ticker': (r.get('ticker') or '').strip(), 'name': (r.get('name') or r.get('ticker') or '').strip(), 'score': r['score']} for r in scores if r.get('score') is not None and (r.get('ticker') or '').strip()]
        return _normalize_relevance_ranking(raw)

    if cfg['source'] == 'trait_json':
        path = cfg.get('path') or TRAIT_SCORES_JSON
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
        scores = data.get('scores') or []
        raw = []
        for r in scores:
            t = (r.get('ticker') or '').strip()
            if not t:
                continue
            s = r.get('trait_score')
            if s is None:
                continue
            try:
                s = float(s)
            except (TypeError, ValueError):
                continue
            raw.append({'ticker': t, 'name': (r.get('name') or t).strip(), 'score': s})
        return _normalize_relevance_ranking(raw)

    return []




def handle_relevance_ranking(relevance_type):
    """Single handler for all relevance ranking tabs. Uses get_relevance_ranking() as source of truth."""
    cfg = _relevance_config(relevance_type)
    if not cfg:
        return redirect(url_for('ai_relevance'))
    if relevance_type in RELEVANCE_TABS_DISABLED:
        first_cfg = _relevance_config(_first_enabled_relevance_key())
        return redirect(url_for(first_cfg['endpoint']))
    template_name = 'relevance_rankings.html'
    base_path = cfg['url_path']
    relevance_path = base_path
    peers_url = base_path + '/peers'
    groups_url = base_path + '/groups'
    watchlist_url = base_path + '/watchlist'
    pagination_endpoint = cfg['endpoint']
    empty_message = cfg.get('empty_message', 'No data for this ranking.')

    search_query = request.args.get('search', '').strip().upper()
    ticker_exact = request.args.get('ticker_exact', '0') == '1'
    page = request.args.get('page', 1, type=int)
    per_page = 100
    empty_pagination = {
        'page': 1, 'per_page': 100, 'total': 0,
        'total_pages': 0, 'has_prev': False, 'has_next': False,
        'prev_page': None, 'next_page': None
    }

    all_companies = get_relevance_ranking(relevance_type)
    nav_ctx = _relevance_nav_context(relevance_type)
    if not all_companies:
        return render_template(template_name, companies=[], pagination=empty_pagination, active_tab=relevance_type, ticker_exact=False, relevance_subtab='ranking', relevance_path=relevance_path, peers_url=peers_url, groups_url=groups_url, watchlist_url=watchlist_url, pagination_endpoint=pagination_endpoint, total_count=0, filtered_count=0, error=empty_message, **nav_ctx)

    if not search_query:
        filtered = all_companies
    elif ticker_exact:
        filtered = [c for c in all_companies if (c.get('ticker') or '').upper() == search_query]
    else:
        filtered = [c for c in all_companies if search_query in (c.get('ticker') or '').upper() or search_query in (c.get('name') or '').upper()]
    if search_query and any((c.get('ticker') or '').upper() == search_query for c in all_companies):
        filtered = [c for c in all_companies if (c.get('ticker') or '').upper() == search_query]
    total_pages = (len(filtered) + per_page - 1) // per_page
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    start_idx = (page - 1) * per_page

    pagination = {
        'page': page, 'total_pages': total_pages, 'per_page': per_page,
        'has_prev': page > 1, 'has_next': page < total_pages,
        'prev_page': page - 1, 'next_page': page + 1
    }
    return_to = request.full_path
    return_to_encoded = quote(return_to, safe='')
    return render_template(template_name,
                           companies=filtered[start_idx:start_idx+per_page],
                           search_query=search_query,
                           pagination=pagination,
                           active_tab=relevance_type,
                           app_context='relevance',
                           total_count=len(all_companies),
                           filtered_count=len(filtered),
                           ticker_exact=ticker_exact,
                           relevance_subtab='ranking',
                           relevance_path=relevance_path,
                           peers_url=peers_url,
                           groups_url=groups_url,
                           watchlist_url=watchlist_url,
                           pagination_endpoint=pagination_endpoint,
                           return_to=return_to,
                           return_to_encoded=return_to_encoded,
                           **nav_ctx)

@app.route('/ai-relevance')
def ai_relevance():
    return handle_relevance_ranking('ai')

@app.route('/robotics-relevance')
def robotics_relevance():
    return handle_relevance_ranking('robotics')


@app.route('/tech-disruptor-relevance')
def tech_disruptor_relevance():
    return handle_relevance_ranking('tech_disruptor_ai')


@app.route('/tandem-relevance')
def tandem_relevance():
    return handle_relevance_ranking('tandem_company')


@app.route('/all-weather-relevance')
def all_weather_relevance():
    return handle_relevance_ranking('all_weather')


@app.route('/durable-advantage-relevance')
def durable_advantage_relevance():
    return handle_relevance_ranking('durable_advantage')


@app.route('/ai-disruption-risk-relevance')
def ai_disruption_risk_relevance():
    return handle_relevance_ranking('ai_disruption_risk')


@app.route('/company-score')
def company_score_relevance():
    """Company (trait) score ranking tab: uses same handler as all relevance tabs."""
    return handle_relevance_ranking('company_score')


def _relevance_peers_route(active_tab):
    """Render peers view for a relevance ranking tab (ai, robotics, company_score, tech_disruptor_ai)."""
    if active_tab in RELEVANCE_TABS_DISABLED:
        first_cfg = _relevance_config(_first_enabled_relevance_key())
        return redirect(first_cfg['url_path'] + '/peers')
    base = _relevance_url_path(active_tab)
    relevance_path = base
    peers_path = base + '/peers'
    groups_path = base + '/groups'
    watchlist_path = base + '/watchlist'
    nav_ctx = _relevance_nav_context(active_tab)
    search_query = request.args.get('search', '').strip().upper()
    if not search_query:
        return render_template('relevance_peers.html',
                               peers=[], search_query='', company_name=None, company_ticker=None,
                               active_tab=active_tab, app_context='relevance', relevance_subtab='peers',
                               relevance_path=relevance_path, peers_path=peers_path, groups_path=groups_path, watchlist_path=watchlist_path, return_to=peers_path, return_to_encoded=quote(peers_path), peers_search_encoded='',
                               **nav_ctx)
    company, peers_details, error = _get_relevance_peers_data(search_query, active_tab)
    if error:
        return render_template('relevance_peers.html', peers=[], search_query=search_query,
                              company_name=company['company_name'] if company else None,
                              company_ticker=company['ticker'] if company else None,
                              error=error, active_tab=active_tab, app_context='relevance',
                              relevance_subtab='peers', relevance_path=relevance_path, peers_path=peers_path, groups_path=groups_path, watchlist_path=watchlist_path, return_to=peers_path, return_to_encoded=quote(peers_path), peers_search_encoded=quote(search_query),
                              **nav_ctx)
    peers_search_encoded = quote(search_query or '')
    return_to = peers_path + '?search=' + peers_search_encoded
    return_to_encoded = quote(return_to, safe='')
    return render_template('relevance_peers.html',
                          peers=peers_details, search_query=search_query,
                          company_name=company['company_name'], company_ticker=company['ticker'],
                          peers_search_encoded=peers_search_encoded, active_tab=active_tab,
                          app_context='relevance', relevance_subtab='peers', relevance_path=relevance_path, peers_path=peers_path,
                          groups_path=groups_path, watchlist_path=watchlist_path, return_to=return_to, return_to_encoded=return_to_encoded,
                          **nav_ctx)


@app.route('/ai-relevance/peers')
def ai_relevance_peers():
    return _relevance_peers_route('ai')


@app.route('/robotics-relevance/peers')
def robotics_relevance_peers():
    return _relevance_peers_route('robotics')


@app.route('/company-score/peers')
def company_score_peers():
    return _relevance_peers_route('company_score')


@app.route('/tech-disruptor-relevance/peers')
def tech_disruptor_relevance_peers():
    return _relevance_peers_route('tech_disruptor_ai')


@app.route('/tandem-relevance/peers')
def tandem_relevance_peers():
    return _relevance_peers_route('tandem_company')


@app.route('/all-weather-relevance/peers')
def all_weather_relevance_peers():
    return _relevance_peers_route('all_weather')


@app.route('/durable-advantage-relevance/peers')
def durable_advantage_relevance_peers():
    return _relevance_peers_route('durable_advantage')


@app.route('/ai-disruption-risk-relevance/peers')
def ai_disruption_risk_relevance_peers():
    return _relevance_peers_route('ai_disruption_risk')


def _get_relevance_peers_data(search_query, relevance_type):
    """Get peers for a company using the same peer list as main app, but score/rank/percentile from the given relevance ranking (ai, robotics, company_score). Returns (company, peers_details, error)."""
    if not search_query:
        return None, [], None
    company = CompanyRepository.get_company_detail(search_query)
    if not company:
        conn = CompanyRepository.get_db_connection(TOP_SCORES_DB)
        company_row = conn.execute("SELECT * FROM scores WHERE UPPER(company_name) LIKE ? ORDER BY total_score DESC LIMIT 1", (f"{search_query}%",)).fetchone()
        conn.close()
        if company_row:
            company = dict(company_row)
    if not company:
        return None, [], "Company not found"
    company_ticker = company['ticker']
    peer_names = CompanyRepository.get_peers(company_ticker)
    if not peer_names:
        return company, [], "No peers found"
    # Build list of tickers: company + peers (resolve peer names to tickers)
    all_tickers = [company_ticker]
    conn = CompanyRepository.get_db_connection(TOP_SCORES_DB)
    for peer_name in peer_names:
        peer_row = conn.execute("SELECT ticker FROM scores WHERE UPPER(company_name) = UPPER(?) ORDER BY timestamp DESC LIMIT 1", (peer_name,)).fetchone()
        if not peer_row:
            peer_row = conn.execute("SELECT ticker FROM scores WHERE UPPER(company_name) LIKE ? ORDER BY total_score DESC LIMIT 1", (f"%{peer_name}%",)).fetchone()
        if peer_row:
            pt = peer_row['ticker']
            if pt not in all_tickers:
                all_tickers.append(pt)
    conn.close()
    # Get relevance ranking data for these tickers (only those in the ranking)
    relevance_rows = _get_relevance_group_data(relevance_type, all_tickers)
    by_ticker = {r['ticker'].upper(): r for r in relevance_rows}
    company_map = CompanyRepository.get_company_metadata(all_tickers)
    peers_details = []
    for t in all_tickers:
        is_searched = (t.upper() == company_ticker.upper())
        meta = company_map.get(t.upper(), {})
        name = meta.get('name') or t
        if t.upper() in by_ticker:
            row = dict(by_ticker[t.upper()])
            row['company_name'] = name
            row['is_searched'] = is_searched
            # percentile may already be "85%"; ensure rank/score are usable for sort
            peers_details.append(row)
        else:
            peers_details.append({
                'ticker': t,
                'company_name': name,
                'global_rank': '—',
                'score_percentage': '—',
                'percentile': '—',
                'is_searched': is_searched,
            })
    # Sort by rank (ascending) so all stocks appear in rank order; unranked (—) at end
    def sort_key(r):
        rank = r.get('global_rank')
        if rank == '—':
            return (1, 0)
        try:
            return (0, int(rank))
        except (TypeError, ValueError):
            return (1, 0)
    peers_details.sort(key=sort_key)
    return company, peers_details, None


def _get_relevance_group_data(relevance_type, tickers):
    """Return list of dicts with ticker, company_name, global_rank, score_percentage, percentile. Uses get_relevance_ranking() as single source of truth."""
    if not tickers:
        return []
    all_companies = get_relevance_ranking(relevance_type)
    by_ticker = {(c.get('ticker') or '').upper(): c for c in all_companies}
    tickers_upper = [t.upper() if isinstance(t, str) else t for t in tickers]
    results = []
    for t in tickers_upper:
        c = by_ticker.get(t)
        if not c:
            continue
        ticker = c.get('ticker') or t
        name = c.get('name') or ticker
        score = c.get('relevance_score', 0)
        results.append({
            'ticker': ticker,
            'company_name': name,
            'global_rank': c.get('relevance_rank', 0),
            'score_percentage': str(int(score)) if score == int(score) else str(round(score, 1)),
            'percentile': str(c.get('relevance_percentile', 0)) + '%',
        })
    results.sort(key=lambda x: x['global_rank'])
    return results


@app.route('/api/relevance-group-data', methods=['POST'])
def relevance_group_data():
    """Return relevance ranking data for a list of tickers (same shape as watchlist-data: ticker, company_name, global_rank, score_percentage, percentile)."""
    data = request.json or {}
    tickers = data.get('tickers', [])
    relevance_type = data.get('relevance_type', 'ai')
    if not _relevance_config(relevance_type):
        relevance_type = 'ai'
    if not tickers:
        return jsonify([])
    results = _get_relevance_group_data(relevance_type, tickers)
    return jsonify(results)


def _relevance_groups_route(active_tab):
    """Render groups view for a relevance ranking tab (ai, robotics, company_score, tech_disruptor_ai)."""
    if active_tab in RELEVANCE_TABS_DISABLED:
        first_cfg = _relevance_config(_first_enabled_relevance_key())
        return redirect(first_cfg['url_path'] + '/groups')
    base = _relevance_url_path(active_tab)
    groups_path = base + '/groups'
    peers_path = base + '/peers'
    watchlist_path = base + '/watchlist'
    relevance_path = base
    nav_ctx = _relevance_nav_context(active_tab)
    return render_template('relevance_groups.html',
                          active_tab=active_tab,
                          app_context='relevance',
                          relevance_subtab='groups',
                          groups_path=groups_path,
                          peers_path=peers_path,
                          watchlist_path=watchlist_path,
                          relevance_path=relevance_path,
                          **nav_ctx)


@app.route('/ai-relevance/groups')
def ai_relevance_groups():
    return _relevance_groups_route('ai')


@app.route('/robotics-relevance/groups')
def robotics_relevance_groups():
    return _relevance_groups_route('robotics')


@app.route('/company-score/groups')
def company_score_groups():
    return _relevance_groups_route('company_score')


@app.route('/tech-disruptor-relevance/groups')
def tech_disruptor_relevance_groups():
    return _relevance_groups_route('tech_disruptor_ai')


@app.route('/tandem-relevance/groups')
def tandem_relevance_groups():
    return _relevance_groups_route('tandem_company')


@app.route('/all-weather-relevance/groups')
def all_weather_relevance_groups():
    return _relevance_groups_route('all_weather')


@app.route('/durable-advantage-relevance/groups')
def durable_advantage_relevance_groups():
    return _relevance_groups_route('durable_advantage')


@app.route('/ai-disruption-risk-relevance/groups')
def ai_disruption_risk_relevance_groups():
    return _relevance_groups_route('ai_disruption_risk')


def _relevance_watchlist_route(active_tab):
    """Render watchlist view for a relevance ranking tab (ai, robotics, company_score, tech_disruptor_ai); uses same localStorage watchlist as main app."""
    if active_tab in RELEVANCE_TABS_DISABLED:
        first_cfg = _relevance_config(_first_enabled_relevance_key())
        return redirect(first_cfg['url_path'] + '/watchlist')
    base = _relevance_url_path(active_tab)
    watchlist_path = base + '/watchlist'
    peers_path = base + '/peers'
    groups_path = base + '/groups'
    relevance_path = base
    nav_ctx = _relevance_nav_context(active_tab)
    return render_template('relevance_watchlist.html',
                          active_tab=active_tab,
                          app_context='relevance',
                          relevance_subtab='watchlist',
                          watchlist_path=watchlist_path,
                          peers_path=peers_path,
                          groups_path=groups_path,
                          relevance_path=relevance_path,
                          **nav_ctx)


@app.route('/ai-relevance/watchlist')
def ai_relevance_watchlist():
    return _relevance_watchlist_route('ai')


@app.route('/robotics-relevance/watchlist')
def robotics_relevance_watchlist():
    return _relevance_watchlist_route('robotics')


@app.route('/company-score/watchlist')
def company_score_watchlist():
    return _relevance_watchlist_route('company_score')


@app.route('/tech-disruptor-relevance/watchlist')
def tech_disruptor_relevance_watchlist():
    return _relevance_watchlist_route('tech_disruptor_ai')


@app.route('/tandem-relevance/watchlist')
def tandem_relevance_watchlist():
    return _relevance_watchlist_route('tandem_company')


@app.route('/all-weather-relevance/watchlist')
def all_weather_relevance_watchlist():
    return _relevance_watchlist_route('all_weather')


@app.route('/durable-advantage-relevance/watchlist')
def durable_advantage_relevance_watchlist():
    return _relevance_watchlist_route('durable_advantage')


@app.route('/ai-disruption-risk-relevance/watchlist')
def ai_disruption_risk_relevance_watchlist():
    return _relevance_watchlist_route('ai_disruption_risk')


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
    return jsonify([{'cik': r['cik'], 'name': normalize_fund_name(r.get('name', '') or '')} for r in rows])

@app.route('/api/funds/rankings')
def api_funds_rankings():
    """Return fund rankings as JSON. Computes total value from portfolio_history.db (sum of holdings per fund's latest filing)."""
    page = max(1, request.args.get('page', 1, type=int))
    per_page = max(1, min(500, request.args.get('per_page', 100, type=int)))
    empty = {
        'rankings': [],
        'total_count': 0,
        'total_pages': 0,
        'page': 1,
        'per_page': per_page,
    }
    try:
        merged = []
        if os.path.exists(PORTFOLIO_HISTORY_DB):
            conn = sqlite3.connect(PORTFOLIO_HISTORY_DB)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute("""
                    WITH latest_filing AS (
                        SELECT f.cik, MIN(f.id) AS filing_id, MAX(f.fund_name) AS fund_name, MAX(f.report_date) AS report_date
                        FROM filings f
                        WHERE f.report_date = '2025-09-30'
                        GROUP BY f.cik
                    ),
                    parsed AS (
                        SELECT l.cik, l.fund_name, l.report_date,
                               CAST(REPLACE(REPLACE(REPLACE(COALESCE(h.value,'0'), ',', ''), '$', ''), ' ', '') AS REAL) AS raw_val
                        FROM latest_filing l
                        JOIN holdings h ON h.filing_id = l.filing_id
                    ),
                    totals AS (
                        SELECT cik, fund_name, report_date,
                               CASE WHEN report_date < '2023-01-01' THEN SUM(raw_val) * 1000 ELSE SUM(raw_val) END AS raw_total
                        FROM parsed
                        GROUP BY cik
                    )
                    SELECT cik, fund_name, report_date, raw_total AS total_value FROM totals
                    ORDER BY total_value DESC, fund_name
                """).fetchall()
                merged = [
                    {'cik': r['cik'], 'name': normalize_fund_name(r['fund_name'] or ''), 'total_value': r['total_value'], 'report_date': r['report_date'] or '2025-09-30'}
                    for r in rows
                ]
            except sqlite3.OperationalError:
                pass
            conn.close()

        if merged:
            total_count = len(merged)
            total_pages = max(1, (total_count + per_page - 1) // per_page)
            start = (page - 1) * per_page
            rankings = merged[start:start + per_page]
            return jsonify({
                'rankings': rankings,
                'total_count': total_count,
                'total_pages': total_pages,
                'page': page,
                'per_page': per_page,
            })

        return jsonify(empty)
    except Exception as e:
        return jsonify({**empty, 'error': str(e)}), 200

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
