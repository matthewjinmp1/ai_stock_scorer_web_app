#!/usr/bin/env python3
"""
Company Competitive Moat Scorer
Gets Grok to rate a company's competitive moat strength across multiple metrics (0-10 each):
- Competitive Moat
- Barriers to Entry
- Disruption Risk
- Switching Cost
- Brand Strength
- Competition Intensity
- Network Effect
- Innovativeness
- Growth Opportunity
- Product / Service Quality
- And more...
Usage: python scorer.py
Then enter ticker symbols or company names interactively
"""

# Score weightings - adjust these to change the relative importance of each metric
# All start at 1.0 (equal weight). Increase/decrease to emphasize certain metrics.
SCORE_WEIGHTS = {
    'moat_score': 10,
    'barriers_score': 10,
    'disruption_risk': 10,
    'switching_cost': 10,
    'brand_strength': 10, 
    'competition_intensity': 10,
    'network_effect': 10,
    'product_differentiation': 10,
    'innovativeness_score': 10,
    'growth_opportunity': 10,
    'riskiness_score': 10,
    'pricing_power': 10,
    'ambition_score': 10,
    'bargaining_power_of_customers': 10,
    'bargaining_power_of_suppliers': 10,
    'product_quality_score': 10,
    'culture_employee_satisfaction_score': 10,
    'trailblazer_score': 10,
    'management_quality_score': 10,
    'ai_knowledge_score': 10, 
    'size_well_known_score': 19.31,
    'ethical_healthy_environmental_score': 10,
    'long_term_orientation_score': 10,
}

import sys
import os
import json
import re
import threading
import sqlite3
# Add parent directory to path to import config and clients
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from src.clients.grok_client import GrokClient
from src.clients.openrouter_client import OpenRouterClient
from src.utils.db_manager import DBManager
from config import XAI_API_KEY, OPENROUTER_KEY
import time
import tempfile
import shutil
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

# Get project root directory (two levels up from this file: src/scoring/scorer.py -> project root)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

# =============================================================================
# API CONFIGURATION - Change these to switch between Grok API and OpenRouter
# =============================================================================

# Set to True to use Grok API directly, False to use OpenRouter
USE_GROK_API = False

# Model to use for all API calls
# For Grok API: "grok-4-1-fast-reasoning", "grok-3-fast", "grok-3"
# For OpenRouter: "xiaomi/mimo-v2-flash:free", etc.
DEFAULT_MODEL = "xiaomi/mimo-v2-flash:free"

def get_api_client(rate_limiter=None):
    """Get the configured API client (Grok or OpenRouter).
    
    Returns:
        API client instance (GrokClient or OpenRouterClient)
    """
    if USE_GROK_API:
        return GrokClient(api_key=XAI_API_KEY)
    else:
        return OpenRouterClient(api_key=OPENROUTER_KEY, rate_limiter=rate_limiter)

def get_model_for_ticker(ticker):
    """Get the model name to use for a given ticker.
    
    Args:
        ticker: Ticker symbol (uppercase)
        
    Returns:
        str: Model name configured in DEFAULT_MODEL
    """
    return DEFAULT_MODEL

# =============================================================================

# JSON file to store moat scores (paths relative to project root)
SCORES_FILE = os.path.join(PROJECT_ROOT, "data", "scores.json")
# Config file to store persistent settings
CONFIG_FILE = os.path.join(PROJECT_ROOT, "data", "config.json")

def load_db_path():
    """Load the persistently selected database path."""
    # First priority: environment variable
    env_path = os.getenv("SCORES_DB_PATH")
    if env_path:
        return env_path
        
    # Second priority: config file
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                config_path = config.get("selected_db")
                if config_path and os.path.exists(config_path):
                    return config_path
        except Exception:
            pass
            
    # Default: main scores.db
    return os.path.join(PROJECT_ROOT, "data", "scores.db")

def save_db_path(path):
    """Save the selected database path persistently."""
    try:
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        
        config["selected_db"] = path
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save database configuration: {e}")

def load_show_names():
    """Load the persistently selected show_names toggle."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get("show_names", False)
        except Exception:
            pass
    return False

def save_show_names(status):
    """Save the show_names toggle persistently."""
    try:
        config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        
        config["show_names"] = status
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save viewname configuration: {e}")

# Global toggle for showing company names instead of tickers
GLOBAL_SHOW_NAMES = load_show_names()

# Initialize database path
SCORES_DB = load_db_path()
HEAVY_SCORES_FILE = os.path.join(PROJECT_ROOT, "data", "scores_heavy.json")

# Initialize database manager
db = DBManager(SCORES_DB)

# Stock ticker lookup file
TICKER_FILE = os.path.join(PROJECT_ROOT, "data", "stock_tickers_clean.json")

# Log for strange AI responses
STRANGE_LOG_FILE = os.path.join(PROJECT_ROOT, "web_app", "strange_responses.json")
# Log for ALL AI responses
ALL_RESPONSES_LOG_FILE = os.path.join(PROJECT_ROOT, "data", "all_ai_responses.json")
STRANGE_LOG_LOCK = threading.Lock()
ALL_RESPONSES_LOG_LOCK = threading.Lock()

def log_ai_response(ticker, company_name, metric, response, model):
    """Log every AI response to a JSON file."""
    with ALL_RESPONSES_LOG_LOCK:
        try:
            log_data = []
            if os.path.exists(ALL_RESPONSES_LOG_FILE):
                with open(ALL_RESPONSES_LOG_FILE, 'r') as f:
                    try:
                        log_data = json.load(f)
                    except json.JSONDecodeError:
                        log_data = []
            
            # Add new entry
            log_data.append({
                "timestamp": datetime.now().isoformat(),
                "ticker": ticker,
                "company": company_name,
                "metric": metric,
                "model": model,
                "response": response
            })
            
            # Keep only last 5000 entries for all responses (larger buffer than strange log)
            if len(log_data) > 5000:
                log_data = log_data[-5000:]
                
            with open(ALL_RESPONSES_LOG_FILE, 'w') as f:
                json.dump(log_data, f, indent=2)
        except Exception:
            pass

def log_strange_response(ticker, company_name, metric, response, model):
    """Log AI responses that aren't simple numbers to a JSON file."""
    with STRANGE_LOG_LOCK:
        try:
            # Check if the response is actually strange
            res_clean = response.strip()
            # If it's just a number (int or float) between 0-10, it's not strange
            try:
                val = float(res_clean)
                if 0 <= val <= 10 and len(res_clean) <= 4:
                    return
            except ValueError:
                pass

            log_data = []
            if os.path.exists(STRANGE_LOG_FILE):
                with open(STRANGE_LOG_FILE, 'r') as f:
                    try:
                        log_data = json.load(f)
                    except json.JSONDecodeError:
                        log_data = []
            
            # Add new entry
            log_data.append({
                "timestamp": datetime.now().isoformat(),
                "ticker": ticker,
                "company": company_name,
                "metric": metric,
                "model": model,
                "response": response
            })
            
            # Keep only last 1000 entries
            if len(log_data) > 1000:
                log_data = log_data[-1000:]
                
            with open(STRANGE_LOG_FILE, 'w') as f:
                json.dump(log_data, f, indent=2)
                
            # Also print a notification to the console
            print(f"  [LOGGED] Strange response from {model} for {ticker} ({metric})")
        except Exception as e:
            # Don't let logging errors crash the main scorer
            pass

# Peers file
PEERS_FILE = os.path.join(PROJECT_ROOT, "data", "peers.json")

# Peer AI responses file
PEER_RESPONSES_FILE = os.path.join(PROJECT_ROOT, "data", "peer_responses.json")

# Ticker conversions file
TICKER_CONVERSIONS_FILE = os.path.join(PROJECT_ROOT, "data", "ticker_conversions.json")

# Model pricing per 1M tokens (update these based on current Grok API pricing)
# Format: (input_cost_per_1M_tokens, output_cost_per_1M_tokens, cached_input_cost_per_1M_tokens) in USD
MODEL_PRICING = {
    "grok-4-1-fast-reasoning": (0.20, 0.50, 0.05),  # $0.20 per 1M input tokens, $0.50 per 1M output tokens, $0.05 per 1M cached input tokens
    "minimax/minimax-01": (0.20, 1.10, 0.05),     # Estimated pricing for MiniMax o1
    "xiaomi/mimo-v2-flash": (0.01, 0.01, 0.01),     # Flash model pricing (estimated very low)
}


def calculate_token_cost(total_tokens, model="grok-4-1-fast-reasoning", token_usage=None):
    """Calculate the cost of tokens used.
    
    This function calculates costs using separate rates for:
    - Regular input tokens (non-cached)
    - Cached input tokens (typically cheaper)
    - Output tokens
    
    Args:
        total_tokens: Total number of tokens used (fallback if token_usage not provided)
        model: Model name to get pricing for
        token_usage: Optional token_usage dict with token breakdown. Expected fields:
            - input_tokens or prompt_tokens: total input tokens
            - output_tokens or completion_tokens: output tokens
            - cached_tokens, cached_input_tokens, or prompt_cache_hit_tokens: cached input tokens
        
    Returns:
        float: Total cost in USD
    """
    if model not in MODEL_PRICING:
        return 0.0
    
    pricing = MODEL_PRICING[model]
    input_cost_per_1M = pricing[0]
    output_cost_per_1M = pricing[1]
    cached_input_cost_per_1M = pricing[2] if len(pricing) > 2 else input_cost_per_1M
    
    # If we have breakdown of input/output/cached tokens, use that for more accurate pricing
    if token_usage:
        # Get total input/prompt tokens (may be called input_tokens or prompt_tokens)
        # Standard OpenAI format: prompt_tokens includes all prompt tokens (cached + non-cached)
        # Use explicit check instead of 'or' to handle 0 values correctly
        total_input_tokens = token_usage.get('input_tokens') if 'input_tokens' in token_usage else token_usage.get('prompt_tokens', 0)
        # Get output tokens (may be called output_tokens or completion_tokens)
        output_tokens = token_usage.get('output_tokens') if 'output_tokens' in token_usage else token_usage.get('completion_tokens', 0)
        # Get cached tokens (may be called cached_tokens, cached_input_tokens, or prompt_cache_hit_tokens)
        cached_tokens = (token_usage.get('cached_tokens') if 'cached_tokens' in token_usage else
                        token_usage.get('cached_input_tokens') if 'cached_input_tokens' in token_usage else
                        token_usage.get('prompt_cache_hit_tokens', 0))
        
        if total_input_tokens > 0 or output_tokens > 0 or cached_tokens > 0:
            # Calculate regular (non-cached) input tokens
            # Standard API format: prompt_tokens = regular_input + cached_input
            # So regular_input = prompt_tokens - cached_tokens
            regular_input_tokens = max(0, total_input_tokens - cached_tokens)
            
            regular_input_cost = (regular_input_tokens / 1_000_000) * input_cost_per_1M
            cached_input_cost = (cached_tokens / 1_000_000) * cached_input_cost_per_1M
            output_cost = (output_tokens / 1_000_000) * output_cost_per_1M
            
            # Debug: print token breakdown (can be removed later)
            # print(f"DEBUG: input={regular_input_tokens}, cached={cached_tokens}, output={output_tokens}")
            # print(f"DEBUG: input_cost=${regular_input_cost:.6f}, cached_cost=${cached_input_cost:.6f}, output_cost=${output_cost:.6f}")
            
            return regular_input_cost + cached_input_cost + output_cost
    
    # Fallback: use total tokens with average of input/output pricing
    # This is less accurate but works if we don't have breakdown
    avg_cost_per_1M = (input_cost_per_1M + output_cost_per_1M) / 2
    return (total_tokens / 1_000_000) * avg_cost_per_1M

# Custom ticker definitions file
TICKER_DEFINITIONS_FILE = os.path.join(PROJECT_ROOT, "data", "ticker_definitions.json")

# Cache for ticker lookups
_ticker_cache = None

def load_custom_ticker_definitions():
    """Load custom ticker definitions from JSON file.
    
    Returns:
        dict: Dictionary mapping ticker (uppercase) to company name
    """
    custom_definitions = {}
    
    try:
        if os.path.exists(TICKER_DEFINITIONS_FILE):
            with open(TICKER_DEFINITIONS_FILE, 'r') as f:
                data = json.load(f)
                
                for ticker, name in data.get('definitions', {}).items():
                    ticker_upper = ticker.strip().upper()
                    name_stripped = name.strip()
                    
                    if ticker_upper and name_stripped:
                        custom_definitions[ticker_upper] = name_stripped
    except Exception as e:
        print(f"Warning: Could not load custom ticker definitions: {e}")
    
    return custom_definitions

def save_custom_ticker_definitions(definitions):
    """Save custom ticker definitions to JSON file.
    
    Args:
        definitions: Dictionary mapping ticker to company name
    """
    try:
        data = {"definitions": definitions}
        with open(TICKER_DEFINITIONS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error: Could not save custom ticker definitions: {e}")
        return False

def load_ticker_lookup():
    """Load ticker to company name lookup.
    Custom definitions take precedence over main ticker file.
    """
    global _ticker_cache
    
    if _ticker_cache is not None:
        return _ticker_cache
    
    _ticker_cache = {}
    
    # First load from main ticker file
    try:
        if os.path.exists(TICKER_FILE):
            with open(TICKER_FILE, 'r') as f:
                data = json.load(f)
                
                for company in data.get('companies', []):
                    ticker = company.get('ticker', '').strip().upper()
                    name = company.get('name', '').strip()
                    
                    if ticker:
                        _ticker_cache[ticker] = name
        else:
            print(f"Warning: {TICKER_FILE} not found. Ticker lookups will not work.")
    except Exception as e:
        print(f"Warning: Could not load ticker file: {e}")
    
    # Then load custom definitions (these override main file)
    custom_definitions = load_custom_ticker_definitions()
    _ticker_cache.update(custom_definitions)
    
    return _ticker_cache

def get_current_display_name(ticker, company_name=None):
    """Get the display name for a company based on the GLOBAL_SHOW_NAMES toggle."""
    ticker_upper = ticker.strip().upper()
    
    # If showing names, ensure we have the best possible name
    if GLOBAL_SHOW_NAMES:
        if company_name is None:
            # 1. Try to get name from database (prioritize stored name)
            try:
                db_record = db.get_score(ticker_upper)
                if db_record and db_record.get('company_name'):
                    company_name = db_record.get('company_name')
            except:
                pass
                
            # 2. Fallback to ticker lookup file
            if not company_name:
                ticker_lookup = load_ticker_lookup()
                company_name = ticker_lookup.get(ticker_upper, ticker_upper)
        
        if company_name:
            # Clean up name: remove newlines and extra spaces
            company_name = ' '.join(company_name.split())
            
        return company_name
    
    # If not showing names, just return the ticker
    return ticker_upper

def resolve_to_company_name(input_str):
    """
    Resolve input to a company name.
    Returns (company_name, ticker) tuple.
    """
    input_upper = input_str.strip().upper()
    
    # 1. Check if it's a ticker symbol in ticker database
    ticker_lookup = load_ticker_lookup()
    if input_upper in ticker_lookup:
        return (ticker_lookup[input_upper], input_upper)
        
    # 2. Check in database metadata or scores
    db_paths = [
        SCORES_DB,
        os.path.join(PROJECT_ROOT, "web_app", "top_500_scores.db"),
        os.path.join(PROJECT_ROOT, "data", "scores.db")
    ]
    
    # Remove duplicates and None
    db_paths = list(dict.fromkeys([p for p in db_paths if p and os.path.exists(p)]))
    
    for db_path in db_paths:
        try:
            # Check metadata table
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Check if companies_metadata table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='companies_metadata'")
                if cursor.fetchone():
                    cursor.execute("SELECT name FROM companies_metadata WHERE ticker = ?", (input_upper,))
                    meta_row = cursor.fetchone()
                    if meta_row:
                        return (meta_row['name'], input_upper)
            
            # Then check scores table (if it's the active db, we can use the db manager)
            if db_path == SCORES_DB:
                db_record = db.get_score(input_upper)
                if db_record and db_record.get('company_name'):
                    return (db_record.get('company_name'), input_upper)
            else:
                # Manual check for other databases
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scores'")
                    if cursor.fetchone():
                        cursor.execute("SELECT company_name FROM scores WHERE ticker = ? ORDER BY timestamp DESC LIMIT 1", (input_upper,))
                        score_row = cursor.fetchone()
                        if score_row and score_row['company_name']:
                            return (score_row['company_name'], input_upper)
        except:
            continue
    
    # 3. If it looks like a ticker but not found, still return it as ticker but with None name
    # Tickers typically don't have spaces and are 1-10 characters
    if " " not in input_upper and len(input_upper) >= 1 and len(input_upper) <= 10 and (input_upper.isalpha() or any(c in input_upper for c in '.-0123456789')):
        return (None, input_upper)
    
    # Otherwise treat as company name
    return (input_str.strip(), None)

def get_ticker_from_company_name(company_name):
    """Reverse lookup: get ticker from company name using ticker JSON lookup."""
    ticker_lookup = load_ticker_lookup()
    
    company_lower = company_name.lower()
    
    # Try exact match (case insensitive)
    for ticker, name in ticker_lookup.items():
        if name.lower() == company_lower:
            return ticker
    
    # Try partial match
    for ticker, name in ticker_lookup.items():
        if company_lower in name.lower() or name.lower() in company_lower:
            return ticker
    
    return None

# Define all score metrics - add new scores here to automatically integrate them everywhere!
SCORE_DEFINITIONS = {
    'moat_score': {
        'display_name': 'Competitive Moat',
        'field_name': 'moat_score',
        'prompt': """Rate the competitive moat strength of {company_name} on a scale of 0-10, where:
- 0 = No competitive advantage, easily replaceable
- 5 = Moderate competitive advantages
- 10 = Extremely strong moat, nearly impossible to compete against

Consider factors like:
- Brand strength and customer loyalty
- Network effects
- Switching costs
- Economies of scale
- Patents/intellectual property
- Regulatory barriers
- Unique resources or capabilities

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'barriers_score': {
        'display_name': 'Barriers to Entry',
        'field_name': 'barriers_score',
        'prompt': """Rate the barriers to entry for {company_name} on a scale of 0-10, where:
- 0 = No barriers, extremely easy for competitors to enter
- 5 = Moderate barriers to entry
- 10 = Extremely high barriers, nearly impossible for new competitors to enter

Consider factors like:
- Capital requirements
- Regulatory and licensing requirements
- Technological complexity
- Distribution channel access
- Brand recognition and customer loyalty
- Network effects
- Resource advantages
- Switching costs for customers

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'disruption_risk': {
        'display_name': 'Disruption Risk',
        'field_name': 'disruption_risk',
        'prompt': """Rate the disruption risk for {company_name} on a scale of 0-10, where:
- 0 = No risk, very stable industry
- 5 = Moderate disruption risk
- 10 = Very high risk of being disrupted by new technology or competitors

Consider factors like:
- Technology disruption potential
- Regulatory risk
- Changing consumer preferences
- Emerging competitors with new business models
- Industry transformation trends
- Obsolescence risk
- Substitution threats

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': True
    },
    'switching_cost': {
        'display_name': 'Switching Cost',
        'field_name': 'switching_cost',
        'prompt': """Rate the switching costs for customers of {company_name} on a scale of 0-10, where:
- 0 = No switching costs, customers can easily leave
- 5 = Moderate switching costs
- 10 = Very high switching costs, customers are locked in

Consider factors like:
- Learning curve for new products
- Data migration complexity
- Contractual commitments
- Integration with existing systems
- Training requirements
- Financial switching costs
- Network effects making it hard to leave
- Compatibility issues

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'brand_strength': {
        'display_name': 'Brand Strength',
        'field_name': 'brand_strength',
        'prompt': """Rate the brand strength for {company_name} on a scale of 0-10, where:
- 0 = No brand recognition or loyalty
- 5 = Moderate brand strength
- 10 = Extremely strong brand with high customer loyalty and recognition

Consider factors like:
- Brand recognition and awareness
- Customer loyalty and emotional attachment
- Brand reputation and trust
- Ability to charge premium prices
- Brand value and differentiation
- Marketing effectiveness
- Brand longevity and consistency
- Global brand presence

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'competition_intensity': {
        'display_name': 'Competition Intensity',
        'field_name': 'competition_intensity',
        'prompt': """Rate the intensity of competition for {company_name} on a scale of 0-10, where:
- 0 = No competition, monopoly-like market
- 5 = Moderate competition
- 10 = Extremely intense competition with many aggressive competitors

Consider factors like:
- Number of competitors in the market
- Competitiveness of pricing strategies
- Aggressiveness of marketing and customer acquisition
- Market share fragmentation
- Barriers to market dominance
- Competitor capabilities and resources
- Frequency of competitive actions
- Market growth rate relative to competition

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': True
    },
    'network_effect': {
        'display_name': 'Network Effect',
        'field_name': 'network_effect',
        'prompt': """Rate the network effects for {company_name} on a scale of 0-10, where:
- 0 = No network effects, value doesn't increase with more users
- 5 = Moderate network effects
- 10 = Extremely strong network effects, value increases dramatically with more users

Consider factors like:
- Value increases as more users join the network
- User count creates competitive advantage
- Network density and interconnectedness
- Platform effects and ecosystem benefits
- Data network effects
- Social network effects
- Two-sided market effects
- Viral growth potential

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'product_differentiation': {
        'display_name': 'Product Differentiation',
        'field_name': 'product_differentiation',
        'prompt': """Rate the product differentiation (vs commoditization) for {company_name} on a scale of 0-10, where:
- 0 = Completely commoditized, interchangeable with competitors, price competition
- 5 = Some differentiation, moderate pricing power
- 10 = Highly differentiated, unique products/services with strong pricing power

Consider factors like:
- Product uniqueness and distinctiveness
- Ability to command premium prices
- Customer perception of differentiation
- Brand differentiation and positioning
- R&D and innovation creating uniqueness
- Proprietary features or technology
- Service or experience differentiation
- Market positioning and specialization

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'innovativeness_score': {
        'display_name': 'Innovativeness',
        'field_name': 'innovativeness_score',
        'prompt': """Rate the innovativeness of {company_name} on a scale of 0-10, where:
- 0 = Not innovative, relies on existing technologies and practices, minimal R&D
- 5 = Moderately innovative, some product improvements and incremental innovation
- 10 = Extremely innovative, breakthrough technologies, disruptive innovation, industry-leading R&D

Consider factors like:
- R&D investment and spending as percentage of revenue
- Patents, intellectual property, and technological breakthroughs
- Track record of introducing new products and services
- Innovation culture and ability to adapt to new technologies
- Leadership in developing new solutions or business models
- Speed of innovation cycles and time to market
- Investment in emerging technologies (AI, automation, etc.)
- Historical innovations and transformation initiatives

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'growth_opportunity': {
        'display_name': 'Growth Opportunity',
        'field_name': 'growth_opportunity',
        'prompt': """Rate the growth opportunity for {company_name} on a scale of 0-10, where:
- 0 = Minimal growth opportunity, mature/declining market, limited expansion potential
- 5 = Moderate growth opportunity, steady market growth, some expansion possibilities
- 10 = Exceptional growth opportunity, rapidly expanding market, multiple growth vectors, high scalability

Consider factors like:
- Market size and growth rate of industry
- Addressable market size (TAM/SAM/SOM)
- Geographic expansion opportunities
- Product/service expansion potential
- Market penetration potential in existing segments
- Adjacent market opportunities
- Demographic and macroeconomic trends favoring growth
- Ability to scale operations efficiently
- Customer acquisition and retention growth potential
- International expansion opportunities
- Pricing power and margin expansion opportunities

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'riskiness_score': {
        'display_name': 'Riskiness',
        'field_name': 'riskiness_score',
        'prompt': """Rate the overall riskiness of investing in {company_name} on a scale of 0-10, where:
- 0 = Very low risk, stable and predictable business model
- 5 = Moderate risk, some uncertainty in business outlook
- 10 = Very high risk, highly volatile or uncertain business model

Consider factors like:
- Financial risk and leverage/debt levels
- Business model stability and predictability
- Regulatory and legal risks
- Market volatility and cyclicality
- Management and execution risks
- Competitive and market position risks
- Technology and operational risks
- Macroeconomic sensitivity
- Dependency on key customers or suppliers
- Liquidity and financing risks
- Geographic and political risks
- Concentration risks

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': True
    },
    'pricing_power': {
        'display_name': 'Pricing Power',
        'field_name': 'pricing_power',
        'prompt': """Rate the pricing power of {company_name} on a scale of 0-10, where:
- 0 = No pricing power, commodity-like product with intense price competition
- 5 = Moderate pricing power, some ability to set prices above cost
- 10 = Exceptional pricing power, strong ability to raise prices without losing customers

Consider factors like:
- Ability to increase prices without significant demand loss
- Customer price sensitivity and elasticity
- Unique value proposition and differentiation
- Market position and competitive advantage
- Brand strength and customer loyalty
- Product/service necessity and switching costs
- Market concentration and competitive dynamics
- Substitution availability and alternatives
- Historical pricing power demonstrated
- Gross and operating margin trends
- Customer dependency and lock-in effects
- Regulatory or contractual pricing protections

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'ambition_score': {
        'display_name': 'Ambition',
        'field_name': 'ambition_score',
        'prompt': """Rate the company and culture ambition of {company_name} on a scale of 0-10, where:
- 0 = Low ambition, complacent, maintaining status quo, no transformative goals
- 5 = Moderate ambition, some growth and improvement goals, incremental progress
- 10 = Extremely high ambition, transformative vision, aggressive growth targets, industry-changing goals

Consider factors like:
- Vision and mission clarity and boldness
- Growth targets and expansion ambitions
- Investment in R&D and innovation initiatives
- Market leadership aspirations
- Strategic initiatives and transformation programs
- Culture of excellence and high standards
- Long-term strategic planning and vision
- Willingness to take calculated risks for growth
- Executive leadership ambition and drive
- Company culture of continuous improvement
- Market disruption and category creation goals
- Global expansion and market dominance ambitions
- Investment in talent and capability building

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'bargaining_power_of_customers': {
        'display_name': 'Bargaining Power of Customers',
        'field_name': 'bargaining_power_of_customers',
        'prompt': """Rate the bargaining power of customers for {company_name} on a scale of 0-10, where:
- 0 = Very low customer bargaining power, customers have no alternative options, company has strong pricing control
- 5 = Moderate customer bargaining power, some alternatives available, balanced negotiation power
- 10 = Very high customer bargaining power, many alternatives, customers can easily switch, strong price sensitivity

Consider factors like:
- Number of alternative suppliers and competitors available to customers
- Customer switching costs and ease of substitution
- Customer concentration and dependency on key accounts
- Product differentiation and uniqueness
- Price sensitivity and elasticity of demand
- Customer access to information and transparency
- Threat of backward integration by customers
- Importance of product/service to customer's business
- Standardization vs. customization of offerings
- Customer buying power and volume purchasing ability
- Availability of substitute products or services
- Market fragmentation vs. concentration of customers

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': True
    },
    'bargaining_power_of_suppliers': {
        'display_name': 'Bargaining Power of Suppliers',
        'field_name': 'bargaining_power_of_suppliers',
        'prompt': """Rate the bargaining power of suppliers for {company_name} on a scale of 0-10, where:
- 0 = Very low supplier bargaining power, many alternative suppliers available, company has strong negotiation control
- 5 = Moderate supplier bargaining power, some supplier concentration, balanced negotiation power
- 10 = Very high supplier bargaining power, few suppliers, suppliers have strong control, company is highly dependent

Consider factors like:
- Number of alternative suppliers and availability of substitutes
- Supplier concentration and market structure
- Switching costs to change suppliers
- Company's dependency on specific suppliers
- Supplier's control over critical inputs or resources
- Threat of forward integration by suppliers
- Uniqueness and differentiation of supplier inputs
- Importance of supplier inputs to company's operations
- Standardization vs. customization of supplier inputs
- Company's purchasing power and volume buying ability
- Availability of alternative supply sources or vertical integration options
- Market fragmentation vs. concentration of suppliers
- Supplier's ability to control prices or terms
- Criticality of supplier relationships to company's business model

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': True
    },
    'product_quality_score': {
        'display_name': 'Product / Service Quality',
        'field_name': 'product_quality_score',
        'prompt': """Rate the product or service quality for {company_name} on a scale of 0-10, where:
- 0 = Poor quality, frequent defects/errors, low reliability, high customer dissatisfaction
- 5 = Moderate quality, acceptable performance, some quality/service issues occasionally
- 10 = Exceptional quality, industry-leading standards, high reliability, exceptional customer satisfaction

Note: For software, financial, or holding companies, evaluate the quality of their primary platforms, services, or the businesses they own.

Consider factors like:
- Product/Service reliability and durability/uptime
- Defect rates, bug frequency, or service error rates
- Customer satisfaction, Net Promoter Score (NPS), and reviews
- Industry awards and quality/service certifications
- Warranty claims or service refund rates
- Quality of materials/craftsmanship or service professionalism
- Consistency of quality across different regions or units
- Quality assurance, testing, and service level agreements (SLAs)
- Comparison to industry standards and competitors
- Long-term performance and reliability
- Customer complaints and support resolution speed
- Investment in quality/service improvement initiatives

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'culture_employee_satisfaction_score': {
        'display_name': 'Culture / Employee Satisfaction',
        'field_name': 'culture_employee_satisfaction_score',
        'prompt': """Rate the quality of culture and employee satisfaction for {company_name} on a scale of 0-10, where:
- 0 = Poor culture, low employee satisfaction, high turnover, toxic work environment, poor employee morale
- 5 = Moderate culture, acceptable employee satisfaction, average retention, some cultural issues
- 10 = Exceptional culture, industry-leading employee satisfaction, low turnover, great work environment, high employee engagement

Consider factors like:
- Employee satisfaction scores and surveys
- Employee retention and turnover rates
- Glassdoor and employer review ratings
- Company culture and values alignment
- Work-life balance and employee benefits
- Diversity, equity, and inclusion practices
- Employee engagement and morale
- Leadership quality and management practices
- Opportunities for career growth and development
- Workplace safety and employee well-being
- Communication and transparency
- Recognition and reward systems
- Work environment and office culture
- Employee feedback mechanisms and responsiveness

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'trailblazer_score': {
        'display_name': 'Trailblazer',
        'field_name': 'trailblazer_score',
        'prompt': """Rate how much {company_name} challenges the status quo and pushes boundaries (trailblazer quality) on a scale of 0-10, where:
- 0 = Follows status quo, avoids risks, conventional approaches, minimal innovation, stays in established boundaries
- 5 = Some boundary-pushing, occasional calculated risks, moderate innovation beyond industry norms
- 10 = Extremely bold trailblazer, consistently challenges status quo, willing to take significant risks for big impact, pioneers new possibilities and transforms industries

Consider factors like:
- Willingness to challenge established industry norms and conventions
- Boldness in taking calculated risks for transformative impact
- Pioneering new markets, technologies, or business models
- Disruptive innovation that changes how industries operate
- Visionary leadership that pushes beyond current limitations
- Investment in moonshot projects and breakthrough initiatives
- History of breaking new ground and creating new categories
- Willingness to fail fast and learn from bold experiments
- Transformation of industries rather than incremental improvement
- Breaking conventional wisdom and traditional approaches
- Creating new paradigms and possibilities
- Revolutionary products, services, or business models
- Willingness to cannibalize existing businesses for future growth
- Aggressive pursuit of ambitious, transformative goals

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'management_quality_score': {
        'display_name': 'Management Quality',
        'field_name': 'management_quality_score',
        'prompt': """Rate the quality of management and leadership at {company_name} on a scale of 0-10, where:
- 0 = Poor management, weak execution, poor strategic decisions, low credibility, history of failures
- 5 = Adequate management, acceptable execution, some good decisions mixed with mistakes, moderate track record
- 10 = Exceptional management, outstanding execution, excellent strategic vision and decision-making, strong track record, highly respected leadership

Consider factors like:
- Track record of execution and delivering on promises
- Strategic vision and long-term planning quality
- Capital allocation decisions (M&A, dividends, buybacks, reinvestment)
- Operational efficiency and cost management
- Ability to adapt to changing market conditions
- Communication and transparency with investors
- Management credibility and reputation
- Success in navigating challenges and crises
- Talent acquisition and retention of key executives
- Corporate governance and ethical standards
- Historical financial performance under current management
- Innovation and transformation initiatives
- Market share gains and competitive positioning improvements
- Return on invested capital and shareholder value creation
- Consistency of results and predictability

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'ai_knowledge_score': {
        'display_name': 'AI Knowledge / Confidence',
        'field_name': 'ai_knowledge_score',
        'prompt': """Rate how much information and knowledge you (the AI model) have about {company_name} on a scale of 0-10, where:
- 0 = Very little information available, company is obscure or private, minimal public data, limited knowledge about the company
- 5 = Moderate information available, some public data and coverage, reasonable knowledge about the company's business and operations
- 10 = Extensive information available, well-documented company with abundant public data, comprehensive knowledge about the company's business model, history, financials, products, management, and competitive position

Consider factors like:
- Amount of publicly available information about the company
- Quality and depth of information in your training data
- Company's public profile and media coverage
- Availability of financial reports, SEC filings, and analyst coverage
- How well-documented the company's business model, products, and operations are
- Historical information and track record available
- Management team visibility and public information
- Industry coverage and research reports available
- News coverage and public discussion about the company
- Transparency and disclosure practices
- How confident you feel in your knowledge about this specific company

This score reflects YOUR confidence level in having sufficient information to accurately assess this company. Lower scores indicate you may have limited information, which could affect the reliability of other scores.

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'size_well_known_score': {
        'display_name': 'Size / Well Known',
        'field_name': 'size_well_known_score',
        'prompt': """Rate how large, popular, well-known, and information-rich {company_name} is on a scale of 0-10, where:
- 0 = Very small company, unknown, minimal public awareness, very little information available
- 5 = Moderate size company, some recognition, moderate public awareness, reasonable amount of information available
- 10 = Extremely large company, highly popular and well-known, widespread public awareness, abundant information readily available

Consider factors like:
- Company size (market capitalization, revenue, number of employees, number of customers)
- Popularity and brand recognition (household name status, brand awareness, public recognition)
- Well-known status (media coverage, public discussion, cultural presence, name recognition)
- Amount of information available (public financial disclosures, SEC filings, news coverage, analyst reports, research availability, Wikipedia presence, online information, transparency)
- Public company status and reporting requirements
- Media presence and coverage frequency
- Analyst coverage and research availability
- Public profile and awareness level
- Accessibility of company information and data

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': True
    },
    'ethical_healthy_environmental_score': {
        'display_name': 'Ethical / Healthy / Environmental',
        'field_name': 'ethical_healthy_environmental_score',
        'prompt': """Rate how ethical, healthy, and environmentally friendly {company_name} is on a scale of 0-10, where:
- 0 = Unethical practices, harmful to health, highly damaging to environment, poor corporate responsibility
- 5 = Moderate ethical standards, neutral health impact, some environmental concerns, average corporate responsibility
- 10 = Extremely ethical, promotes health and wellness, environmentally sustainable, exemplary corporate responsibility

Consider factors like:
- Ethical business practices (fair labor, supply chain ethics, human rights, animal welfare, transparency, anti-corruption)
- Health impact of products/services (promotes wellness, nutritional value, safety standards, public health contribution)
- Environmental sustainability (carbon footprint, renewable energy use, waste reduction, pollution control, resource conservation)
- Corporate social responsibility (CSR initiatives, community engagement, social impact, charitable giving)
- Environmental certifications and standards (LEED, B-Corp, carbon neutral, sustainability reporting)
- Ethical sourcing and supply chain management
- Product safety and health standards compliance
- Environmental impact of operations and products
- Social and environmental governance (ESG) performance
- Long-term sustainability commitments and goals
- Health and safety record for employees and consumers
- Environmental regulations compliance and beyond-compliance initiatives

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    },
    'long_term_orientation_score': {
        'display_name': 'Long Term Orientation',
        'field_name': 'long_term_orientation_score',
        'prompt': """Rate the long-term orientation of {company_name} on a scale of 0-10, where:
- 0 = Extremely short-term focused, prioritizes quarterly results over long-term value, reactive decision-making
- 5 = Moderate long-term orientation, balances short-term and long-term goals, some strategic planning
- 10 = Extremely long-term oriented, prioritizes sustainable growth and long-term value creation, strategic vision and patience

Consider factors like:
- Investment in R&D and innovation for future growth
- Willingness to sacrifice short-term profits for long-term competitive advantages
- Strategic planning horizon and vision (5+ years, 10+ years)
- Capital allocation decisions favoring long-term value creation
- Resistance to quarterly earnings pressure and short-term market expectations
- Building capabilities and moats that pay off over decades
- Patient capital and reinvestment in the business
- Focus on sustainable competitive advantages rather than quick wins
- Long-term customer relationships and brand building
- Investment in employee development and retention
- Strategic initiatives that may take years to pay off
- Avoidance of short-term cost-cutting that damages long-term prospects
- Building organizational capabilities and culture for the long run
- Long-term partnerships and supplier relationships
- Focus on creating enduring value rather than maximizing immediate returns

Respond with ONLY the numerical score (0-10), no explanation needed.""",
        'is_reverse': False
    }
}


def load_scores():
    """Load existing scores from SQLite database."""
    return {"companies": db.get_all_scores()}


def save_scores(scores_data, ticker=None):
    """Save scores to SQLite database.
    
    Args:
        scores_data: Dictionary with "companies" key.
        ticker: Optional. If provided, only this ticker will be saved.
                If None, this function does nothing to prevent massive duplication.
    """
    if ticker is None:
        # Legacy behavior would save EVERYTHING, which caused mass duplication.
        # We now require a specific ticker to be passed.
        return

    companies = scores_data.get("companies", {})
    if ticker not in companies:
        return

    scores = companies[ticker]
    ticker_lookup = load_ticker_lookup()
    
    # Ensure total_score is calculated if missing
    if 'total_score' not in scores:
        scores['total_score'] = calculate_total_score(scores)
    
    company_name = scores.get('company_name') or ticker_lookup.get(ticker.upper())
    db.save_score(ticker, scores, company_name=company_name)




def calculate_total_score(scores_dict):
    """Calculate total score from a dictionary of scores.
    
    Args:
        scores_dict: Dictionary with score keys and their values
        
    Returns:
        float: The total weighted score (handling reverse scores appropriately)
    """
    total = 0
    for score_key in SCORE_DEFINITIONS:
        score_def = SCORE_DEFINITIONS[score_key]
        weight = SCORE_WEIGHTS.get(score_key, 1.0)
        
        val = scores_dict.get(score_key)
        # Handle None or 'N/A' as 0.0 for calculation purposes
        if val is None or val == 'N/A':
            score_value = 0.0
        elif isinstance(val, (int, float)):
            score_value = float(val)
        else:
            # Remove non-numeric characters (except decimal) if it's a string
            cleaned = re.sub(r'[^\d.]', '', str(val))
            try:
                score_value = float(cleaned) if cleaned else 0.0
            except ValueError:
                score_value = 0.0
        
        # For reverse scores, invert to get "goodness" value
        if score_def['is_reverse']:
            total += (10 - score_value) * weight
        else:
            total += score_value * weight
            
    return total


def calculate_percentile_rank(score, all_scores):
    """Calculate percentile rank of a score among all scores.
    
    Args:
        score: The score to calculate percentile for (float)
        all_scores: List of all scores to compare against (list of floats)
        
    Returns:
        int: Percentile rank (0-100), or None if no scores to compare
    """
    if not all_scores or len(all_scores) == 0:
        return None
    
    # Count how many scores are less than or equal to this score
    scores_less_or_equal = sum(1 for s in all_scores if s <= score)
    
    # Percentile rank = (number of scores <= this score) / total scores * 100
    percentile = int((scores_less_or_equal / len(all_scores)) * 100)
    return percentile


def get_all_total_scores():
    """Get all total scores from all companies.
    
    Returns:
        list: List of all total scores (floats)
    """
    scores_data = load_scores()
    all_totals = []
    
    for company, data in scores_data["companies"].items():
        total = calculate_total_score(data)
        all_totals.append(total)
    
    return all_totals


def calculate_correlation(ticker1, ticker2):
    """Calculate correlation between two companies' scores.
    
    Args:
        ticker1: First ticker symbol
        ticker2: Second ticker symbol
        
    Returns:
        tuple: (correlation_coefficient, num_metrics_compared) or (None, 0) if error
    """
    scores_data = load_scores()
    ticker_lookup = load_ticker_lookup()
    
    # Normalize tickers
    ticker1_upper = ticker1.strip().upper()
    ticker2_upper = ticker2.strip().upper()
    
    # Get company names
    company1_name = ticker_lookup.get(ticker1_upper)
    company2_name = ticker_lookup.get(ticker2_upper)
    
    if not company1_name:
        print(f"Error: '{ticker1_upper}' is not a valid ticker symbol.")
        return None, 0
    
    if not company2_name:
        print(f"Error: '{ticker2_upper}' is not a valid ticker symbol.")
        return None, 0
    
    # Find scores for both companies
    scores1 = None
    scores2 = None
    
    # Try to find scores by ticker (uppercase, lowercase) or company name
    if ticker1_upper in scores_data["companies"]:
        scores1 = scores_data["companies"][ticker1_upper]
    elif ticker1_upper.lower() in scores_data["companies"]:
        scores1 = scores_data["companies"][ticker1_upper.lower()]
    elif company1_name.lower() in scores_data["companies"]:
        scores1 = scores_data["companies"][company1_name.lower()]
    
    if ticker2_upper in scores_data["companies"]:
        scores2 = scores_data["companies"][ticker2_upper]
    elif ticker2_upper.lower() in scores_data["companies"]:
        scores2 = scores_data["companies"][ticker2_upper.lower()]
    elif company2_name.lower() in scores_data["companies"]:
        scores2 = scores_data["companies"][company2_name.lower()]
    
    if not scores1:
        print(f"Error: No scores found for {ticker1_upper} ({company1_name}).")
        return None, 0
    
    if not scores2:
        print(f"Error: No scores found for {ticker2_upper} ({company2_name}).")
        return None, 0
    
    # Extract numeric scores for metrics both companies have
    # Handle reverse scores by converting to "goodness" values
    values1 = []
    values2 = []
    metric_names = []
    
    for score_key in SCORE_DEFINITIONS:
        score_def = SCORE_DEFINITIONS[score_key]
        val1 = scores1.get(score_key)
        val2 = scores2.get(score_key)
        
        # Only include metrics where both companies have scores (check for None explicitly)
        if val1 is not None and val2 is not None:
            try:
                num1 = float(val1)
                num2 = float(val2)
                
                # Convert reverse scores to "goodness" values
                if score_def['is_reverse']:
                    num1 = 10 - num1
                    num2 = 10 - num2
                
                values1.append(num1)
                values2.append(num2)
                metric_names.append(score_def['display_name'])
            except (ValueError, TypeError):
                continue
    
    if len(values1) < 2:
        print(f"Error: Need at least 2 common metrics to calculate correlation. Found {len(values1)}.")
        return None, 0
    
    # Calculate Pearson correlation coefficient
    # r = Σ((x - x̄)(y - ȳ)) / sqrt(Σ(x - x̄)² * Σ(y - ȳ)²)
    n = len(values1)
    mean1 = sum(values1) / n
    mean2 = sum(values2) / n
    
    numerator = sum((values1[i] - mean1) * (values2[i] - mean2) for i in range(n))
    sum_sq_diff1 = sum((values1[i] - mean1) ** 2 for i in range(n))
    sum_sq_diff2 = sum((values2[i] - mean2) ** 2 for i in range(n))
    
    denominator = (sum_sq_diff1 * sum_sq_diff2) ** 0.5
    
    if denominator == 0:
        # All values are the same (no variance)
        correlation = 1.0 if values1 == values2 else 0.0
    else:
        correlation = numerator / denominator
    
    return correlation, len(values1)


def show_correlation(ticker1, ticker2):
    """Display correlation between two companies' scores.
    
    Args:
        ticker1: First ticker symbol
        ticker2: Second ticker symbol
    """
    ticker_lookup = load_ticker_lookup()
    ticker1_upper = ticker1.strip().upper()
    ticker2_upper = ticker2.strip().upper()
    
    company1_name = ticker_lookup.get(ticker1_upper, ticker1_upper)
    company2_name = ticker_lookup.get(ticker2_upper, ticker2_upper)
    
    print(f"\nCorrelation Analysis: {ticker1_upper} vs {ticker2_upper}")
    print("=" * 80)
    print(f"{ticker1_upper}: {company1_name}")
    print(f"{ticker2_upper}: {company2_name}")
    print()
    
    correlation, num_metrics = calculate_correlation(ticker1, ticker2)
    
    if correlation is None:
        return
    
    print(f"Correlation Coefficient: {correlation:.4f}")
    print(f"Metrics Compared: {num_metrics}")
    print()
    
    # Interpretation
    if correlation >= 0.9:
        interpretation = "Very Strong Positive Correlation"
    elif correlation >= 0.7:
        interpretation = "Strong Positive Correlation"
    elif correlation >= 0.5:
        interpretation = "Moderate Positive Correlation"
    elif correlation >= 0.3:
        interpretation = "Weak Positive Correlation"
    elif correlation >= -0.3:
        interpretation = "Very Weak or No Correlation"
    elif correlation >= -0.5:
        interpretation = "Weak Negative Correlation"
    elif correlation >= -0.7:
        interpretation = "Moderate Negative Correlation"
    elif correlation >= -0.9:
        interpretation = "Strong Negative Correlation"
    else:
        interpretation = "Very Strong Negative Correlation"
    
    print(f"Interpretation: {interpretation}")
    print()
    print("Note: Correlation measures how similarly the two companies score across")
    print("      all metrics. High positive correlation means they have similar")
    print("      strengths and weaknesses. Negative correlation means they are")
    print("      strong in opposite areas.")


def format_total_score(total, percentile=None):
    """Format a total score as a percentage integer string with optional percentile.
    
    Args:
        total: The total weighted score (float)
        percentile: Optional percentile rank (int), if None will be calculated
        
    Returns:
        str: Formatted total score as percentage with percentile (e.g., "87 (75th percentile)")
    """
    # Calculate max possible score with weights
    max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS) * 10
    percentage = (total / max_score) * 100
    
    def get_suffix(n):
        if 11 <= (n % 100) <= 13:
            return 'th'
        return {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')

    if percentile is not None:
        return f"{int(percentage)} ({percentile}{get_suffix(percentile)} percentile)"
    else:
        # Calculate percentile automatically
        all_totals = get_all_total_scores()
        if len(all_totals) > 1:  # Need at least 2 scores to calculate percentile
            percentile = calculate_percentile_rank(total, all_totals)
            if percentile is not None:
                return f"{int(percentage)} ({percentile}{get_suffix(percentile)} percentile)"
        
        return f"{int(percentage)}"


def query_score(grok, company_name, score_key, show_timing=True, ticker=None):
    """Query a single score from Grok.
    
    Args:
        grok: OpenRouterClient instance
        company_name: Company name to score
        score_key: Score metric key
        show_timing: If True, print timing, token, and cost information
        ticker: Optional ticker symbol to determine model
    """
    score_def = SCORE_DEFINITIONS[score_key]
    prompt = score_def['prompt'].format(company_name=company_name)
    model = get_model_for_ticker(ticker) if ticker else DEFAULT_MODEL
    start_time = time.time()
    response, token_usage = grok.simple_query_with_tokens(prompt, model=model)
    elapsed_time = time.time() - start_time
    total_tokens = token_usage.get('total_tokens', 0)
    
    # Log all responses
    log_ai_response(ticker, company_name, score_key, response.strip(), model)
    
    if show_timing:
        cost = calculate_token_cost(total_tokens, model=model, token_usage=token_usage)
        cost_cents = cost * 100
        print(f"  Time: {elapsed_time:.2f}s | Tokens: {total_tokens} | Cost: {cost_cents:.4f}¢")
    return response.strip()


def query_score_heavy(grok, company_name, score_key):
    """Query a single score from Grok using the default model."""
    score_def = SCORE_DEFINITIONS[score_key]
    prompt = score_def['prompt'].format(company_name=company_name)
    model = DEFAULT_MODEL
    start_time = time.time()
    response, token_usage = grok.simple_query_with_tokens(prompt, model=model)
    elapsed_time = time.time() - start_time
    total_tokens = token_usage.get('total_tokens', 0)
    
    # Log all responses
    log_ai_response(None, company_name, score_key, response.strip(), model)
    
    cost = calculate_token_cost(total_tokens, model=model, token_usage=token_usage)
    cost_cents = cost * 100
    print(f"  Time: {elapsed_time:.2f}s | Tokens: {total_tokens} | Cost: {cost_cents:.4f}¢")
    return response.strip()


def query_all_scores_async(grok, company_name, score_keys, batch_mode=False, silent=False, model=None, ticker=None):
    """Query all scores in parallel using ThreadPoolExecutor.
    
    Args:
        grok: OpenRouterClient instance
        company_name: Company name to score
        score_keys: List of score metric keys to query
        batch_mode: If True, show compact metric names during scoring
        silent: If True, don't print progress messages
        model: Model to use for queries (if None, will be determined from ticker)
        ticker: Optional ticker symbol to determine model
        
    Returns:
        tuple: (dict mapping score_key to score value, total_tokens, combined_token_usage, model_name)
    """
    # Determine model if not provided
    if model is None:
        model = get_model_for_ticker(ticker) if ticker else DEFAULT_MODEL
    
    def query_single_score(score_key):
        """Helper function to query a single score."""
        score_def = SCORE_DEFINITIONS[score_key]
        prompt = score_def['prompt'].format(company_name=company_name)
        start_time = time.time()
        try:
            response, token_usage = grok.simple_query_with_tokens(prompt, model=model)
            elapsed_time = time.time() - start_time
            total_tokens = token_usage.get('total_tokens', 0)
            result = response.strip()
            
            # Log all responses
            log_ai_response(ticker, company_name, score_key, result, model)
            
            # Log strange responses (anything not a simple 0-10 number)
            log_strange_response(ticker, company_name, score_key, result, model)
            
            if not silent:
                if batch_mode:
                    print(f"  {score_def['display_name']}: {result}/10")
                else:
                    cost = calculate_token_cost(total_tokens, model=model, token_usage=token_usage)
                    cost_cents = cost * 100
                    print(f"Querying {score_def['display_name']}...")
                    print(f"  Time: {elapsed_time:.2f}s | Tokens: {total_tokens} | Cost: {cost_cents:.4f}¢")
                    print(f"{score_def['display_name']} Score: {result}/10")
                    print()
            
            return score_key, result, None, total_tokens, token_usage
        except Exception as e:
            return score_key, None, str(e), 0, None
    
    # Execute all queries in parallel
    all_scores = {}
    total_tokens = 0
    all_token_usages = []  # Store all token_usage dicts for accurate cost calculation
    with ThreadPoolExecutor(max_workers=len(score_keys)) as executor:
        # Submit all tasks
        future_to_key = {executor.submit(query_single_score, key): key for key in score_keys}
        
        # Collect results as they complete
        for future in as_completed(future_to_key):
            score_key, result, error, tokens, token_usage = future.result()
            total_tokens += tokens
            if token_usage:
                all_token_usages.append(token_usage)
            if error:
                if not silent:
                    print(f"Error querying {SCORE_DEFINITIONS[score_key]['display_name']}: {error}")
                all_scores[score_key] = None
            else:
                all_scores[score_key] = result
    
    # Combine all token usages for accurate cost calculation
    combined_token_usage = None
    if all_token_usages:
        # Get input tokens (use explicit check to handle 0 values)
        input_sum = sum(usage.get('input_tokens') if 'input_tokens' in usage else usage.get('prompt_tokens', 0) for usage in all_token_usages)
        # Get output tokens - completion_tokens should already include thinking tokens from grok_client
        output_sum = sum(usage.get('output_tokens') if 'output_tokens' in usage else usage.get('completion_tokens', 0) for usage in all_token_usages)
        # Get cached tokens
        cached_sum = sum(
            usage.get('cached_tokens') if 'cached_tokens' in usage else
            usage.get('cached_input_tokens') if 'cached_input_tokens' in usage else
            usage.get('prompt_cache_hit_tokens', 0)
            for usage in all_token_usages
        )
        # Get thinking tokens separately for display
        thinking_sum = sum(usage.get('thinking_tokens', 0) for usage in all_token_usages)
        
        combined_token_usage = {
            'input_tokens': input_sum,
            'output_tokens': output_sum,
            'cached_tokens': cached_sum,
            'thinking_tokens': thinking_sum,
            # Also preserve prompt_tokens and completion_tokens for compatibility
            'prompt_tokens': input_sum,
            'completion_tokens': output_sum,
        }
    
    return all_scores, total_tokens, combined_token_usage, model


def score_single_ticker(input_str, silent=False, batch_mode=False, force_rescore=False, rate_limiter=None):
    """Score a single ticker and return the result.
    
    Args:
        input_str: Ticker symbol or company name
        silent: If True, don't print progress messages (only errors)
        batch_mode: If True, show compact metric names during scoring (for batch processing)
        force_rescore: If True, rescore the ticker even if scores already exist
        rate_limiter: Optional SmartRateLimiter to share across threads
        
    Returns:
        dict with keys: 'ticker', 'company_name', 'scores', 'total', 'success', 'error'
        Returns None if ticker is invalid
    """
    try:
        # Resolve input to name and ticker
        company_name, ticker = resolve_to_company_name(input_str)
        
        if not ticker or not company_name:
            if not silent:
                input_upper = input_str.strip().upper()
                if not ticker:
                    print(f"\nError: '{input_upper}' is not a valid ticker symbol.")
                    print("Please enter a valid NYSE or NASDAQ ticker symbol.")
                else:
                    print(f"\nError: Could not resolve company name for '{ticker}'.")
                    print("Scoring cannot proceed without a valid company name.")
            return None
        
        scores_data = load_scores()
        
        # Try to find existing scores (skip if force_rescore is True)
        existing_data = None
        storage_key = None
        
        if not force_rescore:
            # Always check uppercase first (tickers are stored in uppercase), then lowercase for backwards compatibility
            if ticker and ticker in scores_data["companies"]:
                existing_data = scores_data["companies"][ticker]
                storage_key = ticker
            elif ticker and ticker.lower() in scores_data["companies"]:
                # Backwards compatibility: migrate lowercase to uppercase
                existing_data = scores_data["companies"][ticker.lower()]
                storage_key = ticker  # Will migrate on save
            elif company_name.lower() in scores_data["companies"]:
                existing_data = scores_data["companies"][company_name.lower()]
                storage_key = company_name.lower()
        
        if existing_data:
            display_name = get_current_display_name(ticker)
            current_scores = {}
            for score_key in SCORE_DEFINITIONS:
                if score_key == 'moat_score':
                    current_scores[score_key] = existing_data.get(score_key, existing_data.get('score'))
                else:
                    current_scores[score_key] = existing_data.get(score_key)
            # Preserve existing model if present
            if 'model' in existing_data:
                current_scores['model'] = existing_data['model']
            
            if all(v is not None for v in current_scores.values()):
                # All scores exist
                total = calculate_total_score(current_scores)
                return {
                    'ticker': ticker,
                    'company_name': company_name,
                    'scores': current_scores,
                    'total': total,
                    'success': True,
                    'already_scored': True,
                    'total_tokens': 0,
                    'token_usage': None,
                    'model_used': current_scores.get('model')
                }
            
            # Some scores missing, fill them in
            if not silent:
                display_name = get_current_display_name(ticker, company_name)
                print(f"\nFilling missing scores for {display_name}...")
                if not batch_mode:
                    print("Querying missing metrics in parallel...")
            grok = get_api_client(rate_limiter=rate_limiter)
            
            # Get list of missing score keys
            missing_keys = [key for key in SCORE_DEFINITIONS if current_scores.get(key) is None]
            
            # Preserve existing model or determine from ticker
            existing_model = current_scores.get('model')
            if not existing_model:
                existing_model = get_model_for_ticker(ticker) if ticker else "grok-4-1-fast-reasoning"
            
            if missing_keys:
                # Query missing scores in parallel
                missing_scores, tokens_used, token_usage, model_used = query_all_scores_async(grok, company_name, missing_keys,
                                                        batch_mode=batch_mode, silent=silent, ticker=ticker)
                # Update current_scores with the new scores
                current_scores.update(missing_scores)
                # Use the model from the query (should match existing_model, but use query result)
                current_scores['model'] = model_used
                if not silent and not batch_mode:
                    print(f"Total tokens used: {tokens_used}")
                    cost = calculate_token_cost(tokens_used, model=model_used, token_usage=token_usage)
                    cost_cents = cost * 100
                    print(f"Total cost: {cost_cents:.4f} cents")
            
            # Always store tickers in uppercase
            storage_key = ticker if ticker else company_name.lower()
            # If old lowercase key exists, remove it
            if ticker and ticker.lower() in scores_data["companies"] and ticker != ticker.lower():
                del scores_data["companies"][ticker.lower()]
            scores_data["companies"][storage_key] = current_scores
            save_scores(scores_data, ticker=storage_key)
            if not silent:
                model_name = current_scores.get('model', 'Unknown')
                print(f"\nScores updated in {SCORES_FILE} (Model: {model_name})")
            
            total = calculate_total_score(current_scores)
            if not silent:
                total_str = format_total_score(total)
                print(f"Total Score: {total_str}")
            return {
                'ticker': ticker,
                'company_name': company_name,
                'scores': current_scores,
                'total': total,
                'success': True,
                'already_scored': False,
                'total_tokens': tokens_used,
                'token_usage': token_usage,
                'model_used': model_used
            }
        
        # New scoring needed
        display_name = get_current_display_name(ticker, company_name)
        if not silent:
            print(f"\nAnalyzing {display_name}...")
            if not batch_mode:
                print("Querying all metrics in parallel...")
        grok = get_api_client(rate_limiter=rate_limiter)
        
        # Query all scores in parallel
        all_scores, total_tokens, token_usage, model_used = query_all_scores_async(grok, company_name, list(SCORE_DEFINITIONS.keys()), 
                                            batch_mode=batch_mode, silent=silent, ticker=ticker)
        
        # Explicitly set model name based on ticker (ensures correct model is saved when rescoring)
        model_to_save = get_model_for_ticker(ticker) if ticker else "grok-4-1-fast-reasoning"
        all_scores['model'] = model_to_save
        
        # Always store tickers in uppercase
        storage_key = ticker if ticker else company_name.lower()
        # If old lowercase key exists, remove it
        if ticker and ticker.lower() in scores_data["companies"] and ticker != ticker.lower():
            del scores_data["companies"][ticker.lower()]
        
        # Add company name to the scores dict so it's persisted in DB
        all_scores['company_name'] = company_name
            
        scores_data["companies"][storage_key] = all_scores
        save_scores(scores_data, ticker=storage_key)
        if not silent:
            if not batch_mode:
                print(f"Total tokens used: {total_tokens}")
                # Debug: show token breakdown if available
                if token_usage:
                    input_tokens = token_usage.get('input_tokens') if 'input_tokens' in token_usage else token_usage.get('prompt_tokens', 0)
                    output_tokens = token_usage.get('output_tokens') if 'output_tokens' in token_usage else token_usage.get('completion_tokens', 0)
                    cached_tokens = (token_usage.get('cached_tokens') if 'cached_tokens' in token_usage else
                                    token_usage.get('cached_input_tokens') if 'cached_input_tokens' in token_usage else
                                    token_usage.get('prompt_cache_hit_tokens', 0))
                    thinking_tokens = token_usage.get('thinking_tokens', 0)
                    if thinking_tokens > 0:
                        print(f"Token breakdown: input={input_tokens}, output={output_tokens} (includes {thinking_tokens} thinking), cached={cached_tokens}")
                    else:
                        print(f"Token breakdown: input={input_tokens}, output={output_tokens}, cached={cached_tokens}")
                cost = calculate_token_cost(total_tokens, model=model_to_save, token_usage=token_usage)
                cost_cents = cost * 100
                print(f"Total cost: {cost_cents:.4f} cents")
            print(f"\nScores saved to {SCORES_DB} (Model: {model_to_save})")
        
        total = calculate_total_score(all_scores)
        if not silent:
            total_str = format_total_score(total)
            print(f"Total Score: {total_str}")
        return {
            'ticker': ticker,
            'company_name': company_name,
            'scores': all_scores,
            'total': total,
            'success': True,
            'already_scored': False,
            'total_tokens': total_tokens,
            'token_usage': token_usage,
            'model_used': model_used
        }
        
    except ValueError as e:
        error_msg = str(e)
        if not silent:
            print(f"Error: {error_msg}")
            print("\nTo fix this:")
            print("1. Get an API key from https://console.x.ai/")
            print("2. Set the OPENROUTER_KEY environment variable:")
            print("   export OPENROUTER_KEY='your_api_key_here'")
        return {
            'ticker': input_str.upper() if input_str else None,
            'company_name': None,
            'scores': None,
            'total': None,
            'success': False,
            'error': error_msg
        }
    except Exception as e:
        error_msg = str(e)
        if not silent:
            print(f"Error: {error_msg}")
        return {
            'ticker': input_str.upper() if input_str else None,
            'company_name': None,
            'scores': None,
            'total': None,
            'success': False,
            'error': error_msg
        }


def score_multiple_tickers(input_str):
    """Score multiple tickers and display results grouped together.
    
    Args:
        input_str: Space-separated ticker symbols
    """
    tickers_raw = input_str.strip().split()
    
    if not tickers_raw:
        print("Please provide at least one ticker symbol.")
        return
    
    # Deduplicate tickers while preserving order (case-insensitive)
    seen = set()
    tickers = []
    for ticker in tickers_raw:
        ticker_upper = ticker.upper()
        if ticker_upper not in seen:
            seen.add(ticker_upper)
            tickers.append(ticker)
    
    if len(tickers) < len(tickers_raw):
        print(f"Note: Removed {len(tickers_raw) - len(tickers)} duplicate ticker(s).")
    
    print(f"\nProcessing {len(tickers)} ticker(s)...")
    print("=" * 80)
    
    results = []
    ticker_lookup = load_ticker_lookup()
    # Get all totals for percentile calculation (will be updated as we score)
    all_totals = get_all_total_scores()
    
    # Track totals for summary
    batch_start_time = time.time()
    batch_total_tokens = 0
    batch_total_cost = 0.0
    batch_token_usage_combined = {
        'input_tokens': 0,
        'output_tokens': 0,
        'cached_tokens': 0,
        'thinking_tokens': 0
    }
    newly_scored_count = 0
    
    for i, ticker in enumerate(tickers, 1):
        ticker_upper = ticker.strip().upper()
        company_name = ticker_lookup.get(ticker_upper, ticker_upper)
        print(f"\n[{i}/{len(tickers)}] Processing {ticker_upper} ({company_name})...")
        result = score_single_ticker(ticker, silent=True, batch_mode=True)
        if result:
            if result['success']:
                # Accumulate tokens and cost for newly scored tickers
                if not result.get('already_scored'):
                    newly_scored_count += 1
                    tokens = result.get('total_tokens', 0)
                    batch_total_tokens += tokens
                    token_usage = result.get('token_usage')
                    if token_usage:
                        batch_token_usage_combined['input_tokens'] += token_usage.get('input_tokens', token_usage.get('prompt_tokens', 0) or 0)
                        batch_token_usage_combined['output_tokens'] += token_usage.get('output_tokens', token_usage.get('completion_tokens', 0) or 0)
                        cached = token_usage.get('cached_tokens', 0) or token_usage.get('cached_input_tokens', 0) or token_usage.get('prompt_cache_hit_tokens', 0) or 0
                        batch_token_usage_combined['cached_tokens'] += cached
                        batch_token_usage_combined['thinking_tokens'] += token_usage.get('thinking_tokens', 0) or 0
                    model_used = result.get('model_used', get_model_for_ticker(ticker_upper))
                    cost = calculate_token_cost(tokens, model=model_used, token_usage=token_usage)
                    batch_total_cost += cost
                
                # Calculate and display total score and percentile
                total = result.get('total')
                if total is not None:
                    # Refresh all totals to include newly scored ticker
                    all_totals = get_all_total_scores()
                    percentile = calculate_percentile_rank(total, all_totals) if all_totals and len(all_totals) > 1 else None
                    total_str = format_total_score(total, percentile)
                    
                    model_name = result.get('scores', {}).get('model', 'Unknown') if result.get('scores') else 'Unknown'
                    if result.get('already_scored'):
                        print(f"  ✓ {ticker.upper()} already scored - {total_str} (Model: {model_name})")
                    else:
                        print(f"  ✓ {ticker.upper()} scored successfully - {total_str} (Model: {model_name})")
                else:
                    model_name = result.get('scores', {}).get('model', 'Unknown') if result.get('scores') else 'Unknown'
                    if result.get('already_scored'):
                        print(f"  ✓ {ticker.upper()} already scored (Model: {model_name})")
                    else:
                        print(f"  ✓ {ticker.upper()} scored successfully (Model: {model_name})")
            else:
                print(f"  ✗ Error scoring {ticker.upper()}: {result.get('error', 'Unknown error')}")
            results.append(result)
        else:
            print(f"  ✗ '{ticker}' is not a valid ticker. Skipping.")
    
    batch_elapsed_time = time.time() - batch_start_time
    
    if not results:
        print("\nNo valid tickers were processed.")
        return
    
    # Display grouped results
    print("\n" + "=" * 80)
    print("Group Results")
    print("=" * 80)
    
    # Get all totals for percentile calculation
    all_totals = get_all_total_scores()
    
    # Sort results by total score (descending)
    results.sort(key=lambda x: x['total'] if x['total'] is not None else -1, reverse=True)
    
    # Calculate max score for percentage
    max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS) * 10
    
    # Find max name length for formatting (just ticker, no company name)
    max_name_len = max([len(r['ticker']) for r in results if r['success']], default=0)
    max_name_len = min(max(max_name_len, 6), 20)  # At least 6, cap at 20
    
    print(f"\n{'Rank':<6} {'Ticker':<{max_name_len}} {'Total Score':>15} {'Percentile':>12}")
    print("-" * (6 + max_name_len + 15 + 12 + 3))
    
    for rank, result in enumerate(results, 1):
        if not result['success']:
            display_name = result['ticker'] or 'Unknown'
            print(f"{rank:<6} {display_name:<{max_name_len}} {'ERROR':>15} {'N/A':>12}")
            if result.get('error'):
                print(f"       Error: {result['error']}")
            continue
        
        ticker = result['ticker']
        total = result['total']
        
        display_name = ticker
        
        percentage = int((total / max_score) * 100) if total is not None else 0
        percentage_str = f"{percentage}%"
        
        # Calculate percentile
        percentile = None
        if all_totals and len(all_totals) > 1 and total is not None:
            percentile = calculate_percentile_rank(total, all_totals)
        
        if percentile is not None:
            percentile_str = f"{percentile}th"
        else:
            percentile_str = 'N/A'
        
        print(f"{rank:<6} {display_name:<{max_name_len}} {percentage_str:>15} {percentile_str:>12}")
    
    print("=" * 80)
    
    # Display summary of tokens and cost for newly scored tickers
    if newly_scored_count > 0:
        print(f"\nBatch Summary ({newly_scored_count} newly scored):")
        print(f"  Time: {batch_elapsed_time:.2f}s")
        print(f"  Total tokens: {batch_total_tokens:,}")
        if batch_token_usage_combined['thinking_tokens'] > 0:
            print(f"  Token breakdown: input={batch_token_usage_combined['input_tokens']:,}, output={batch_token_usage_combined['output_tokens']:,} (includes {batch_token_usage_combined['thinking_tokens']:,} thinking), cached={batch_token_usage_combined['cached_tokens']:,}")
        else:
            print(f"  Token breakdown: input={batch_token_usage_combined['input_tokens']:,}, output={batch_token_usage_combined['output_tokens']:,}, cached={batch_token_usage_combined['cached_tokens']:,}")
        batch_cost_cents = batch_total_cost * 100
        print(f"  Total cost: {batch_cost_cents:.4f} cents")
    else:
        print(f"\nBatch Summary: All {len(results)} tickers were already scored (no API calls needed)")
        print(f"  Time: {batch_elapsed_time:.2f}s")


def get_company_moat_score(input_str):
    """Get all scores for a company using SCORE_DEFINITIONS.
    
    Accepts either a ticker symbol or company name.
    Stores scores using ticker as key.
    """
    try:
        # Resolve input to name and ticker
        company_name, ticker = resolve_to_company_name(input_str)
        
        if not ticker or not company_name:
            # Not found in either - reject it
            input_upper = input_str.strip().upper()
            if not ticker:
                print(f"\nError: '{input_upper}' is not a valid ticker symbol.")
                print("Please enter a valid NYSE or NASDAQ ticker symbol.")
            else:
                print(f"\nError: Could not resolve company name for '{ticker}'.")
                print("Scoring cannot proceed without a valid company name.")
            return
        
        # Display format: Ticker (Company Name) or just Company Name
        display_name = get_current_display_name(ticker)
        print(f"Company: {company_name}")
        
        scores_data = load_scores()
        
        # Try to find existing scores (always check uppercase first, then lowercase for backwards compatibility)
        existing_data = None
        storage_key = None
        
        if ticker and ticker in scores_data["companies"]:
            existing_data = scores_data["companies"][ticker]
            storage_key = ticker
        elif ticker and ticker.lower() in scores_data["companies"]:
            # Backwards compatibility: migrate lowercase to uppercase
            existing_data = scores_data["companies"][ticker.lower()]
            storage_key = ticker  # Will migrate on save
        elif company_name.lower() in scores_data["companies"]:
            existing_data = scores_data["companies"][company_name.lower()]
            storage_key = company_name.lower()
        
        if existing_data:
            current_scores = {}
            for score_key in SCORE_DEFINITIONS:
                if score_key == 'moat_score':
                    current_scores[score_key] = existing_data.get(score_key, existing_data.get('score'))
                else:
                    current_scores[score_key] = existing_data.get(score_key)
            # Preserve existing model if present
            if 'model' in existing_data:
                current_scores['model'] = existing_data['model']
            
            if all(v is not None for v in current_scores.values()):
                model_name = current_scores.get('model', 'Unknown')
                display_name = get_current_display_name(ticker, company_name)
                print(f"\n{display_name} already scored (Model: {model_name}):")
                
                # Create list of scores with their values for sorting
                scores_list = []
                for score_key in SCORE_DEFINITIONS:
                    score_def = SCORE_DEFINITIONS[score_key]
                    score_val = current_scores.get(score_key, 'N/A')
                    metric_name = score_def['display_name']
                    
                    if score_val is None or score_val == 'N/A':
                        sort_value = -1  # Put N/A scores at the end
                    else:
                        try:
                            sort_value = float(score_val)
                        except (ValueError, TypeError):
                            sort_value = -1
                    
                    scores_list.append((sort_value, metric_name, score_val))
                
                # Sort by score value descending (highest scores first)
                scores_list.sort(reverse=True, key=lambda x: x[0])
                
                # Print sorted scores
                # Use 35 characters for metric name to accommodate "Bargaining Power of Customers" (31 chars)
                for sort_value, metric_name, score_val in scores_list:
                    # Truncate if longer than 35 characters
                    truncated_name = metric_name[:35] if len(metric_name) <= 35 else metric_name[:32] + "..."
                    print(f"{truncated_name:<35} {score_val:>8}")
                
                # Print total at the bottom
                total = calculate_total_score(current_scores)
                total_str = format_total_score(total)
                print(f"{'Total':<35} {total_str:>8}")
                return
            
            grok = get_api_client()
            
            # Get list of missing score keys
            missing_keys = [key for key in SCORE_DEFINITIONS if current_scores.get(key) is None]
            
            if missing_keys:
                print("Querying missing metrics in parallel...")
                # Query missing scores in parallel
                missing_scores, tokens_used, token_usage, model_used = query_all_scores_async(grok, company_name, missing_keys,
                                                        batch_mode=False, silent=False, ticker=ticker)
                # Update current_scores with the new scores
                current_scores.update(missing_scores)
                current_scores['model'] = model_used
                print(f"Total tokens used: {tokens_used}")
                cost = calculate_token_cost(tokens_used, model=model_used, token_usage=token_usage)
                cost_cents = cost * 100
                print(f"Total cost: {cost_cents:.4f} cents")
            
            # Always store tickers in uppercase
            storage_key = ticker if ticker else company_name.lower()
            # If old lowercase key exists, remove it
            if ticker and ticker.lower() in scores_data["companies"] and ticker != ticker.lower():
                del scores_data["companies"][ticker.lower()]
            scores_data["companies"][storage_key] = current_scores
            save_scores(scores_data, ticker=storage_key)
            model_name = current_scores.get('model', 'Unknown')
            print(f"\nScores updated in {SCORES_FILE} (Model: {model_name})")
            
            # Calculate and display total
            total = calculate_total_score(current_scores)
            total_str = format_total_score(total)
            print(f"Total Score: {total_str}")
            return
        
        if ticker:
            display_name = get_current_display_name(ticker, company_name)
            print(f"\nAnalyzing {display_name}...")
        else:
            print(f"\nAnalyzing {company_name}...")
        print("Querying all metrics in parallel...")
        grok = get_api_client()
        
        # Query all scores in parallel
        all_scores, total_tokens, token_usage, model_used = query_all_scores_async(grok, company_name, list(SCORE_DEFINITIONS.keys()),
                                            batch_mode=False, silent=False, ticker=ticker)
        
        # Add model name to scores
        all_scores['model'] = model_used
        
        print(f"Total tokens used: {total_tokens}")
        cost = calculate_token_cost(total_tokens, model=model_used, token_usage=token_usage)
        cost_cents = cost * 100
        print(f"Total cost: {cost_cents:.4f} cents")
        
        # Always store tickers in uppercase
        storage_key = ticker if ticker else company_name.lower()
        # If old lowercase key exists, remove it
        if ticker and ticker.lower() in scores_data["companies"] and ticker != ticker.lower():
            del scores_data["companies"][ticker.lower()]
        
        # Add company name to the scores dict so it's persisted in DB
        all_scores['company_name'] = company_name
            
        scores_data["companies"][storage_key] = all_scores
        save_scores(scores_data, ticker=storage_key)
        model_name = all_scores.get('model', 'Unknown')
        print(f"\nScores saved to {SCORES_DB} (Model: {model_name})")
        
        # Calculate and display total
        total = calculate_total_score(all_scores)
        total_str = format_total_score(total)
        print(f"Total Score: {total_str}")
        
    except ValueError as e:
        print(f"Error: {e}")
        print("\nTo fix this:")
        print("1. Get an API key from https://console.x.ai/")
        print("2. Set the XAI_API_KEY environment variable:")
        print("   export XAI_API_KEY='your_api_key_here'")
        
    except Exception as e:
        print(f"Error: {e}")





def handle_equal_command(score_val_str):
    """Handle the 'equal' command - show all ticker-metric pairs with a specific score.
    
    Args:
        score_val_str: The score value to search for as a string (e.g., "0" or "NULL")
    """
    if not score_val_str.strip():
        print("Usage: equal <score_value>")
        print("Example: equal 0  or  equal NULL")
        return

    score_input = score_val_str.strip().upper()
    is_null_search = score_input == 'NULL'
    
    try:
        if not is_null_search:
            score_target = float(score_input)
    except ValueError:
        print(f"Error: '{score_input}' is not a valid score value. Use a number or 'NULL'.")
        return

    print(f"\nSearching for metrics with score {'NULL' if is_null_search else score_input} in {SCORES_DB}...")
    print("=" * 110)

    # Get all latest entries
    all_latest = db.get_all_scores()
    
    matches = []
    
    for ticker, scores in all_latest.items():
        company_name = scores.get('company_name') or ticker
        
        for metric_key, score_def in SCORE_DEFINITIONS.items():
            val = scores.get(metric_key)
            
            if is_null_search:
                if val is None:
                    matches.append({
                        'ticker': ticker,
                        'company': company_name,
                        'metric': score_def['display_name'],
                        'value': "NULL"
                    })
            else:
                # Handle potential string-represented numbers
                if val is not None:
                    try:
                        num_val = float(val)
                        if num_val == score_target:
                            matches.append({
                                'ticker': ticker,
                                'company': company_name,
                                'metric': score_def['display_name'],
                                'value': num_val
                            })
                    except (ValueError, TypeError):
                        pass

    if not matches:
        print(f"No entries found with score {'NULL' if is_null_search else score_input}.")
    else:
        print(f"{'Ticker':<12} | {'Company':<35} | {'Metric':<35} | {'Score'}")
        print("-" * 110)
        for m in matches:
            company_disp = (m['company'][:32] + '...') if len(m['company']) > 35 else m['company']
            metric_disp = (m['metric'][:32] + '...') if len(m['metric']) > 35 else m['metric']
            print(f"{m['ticker']:<12} | {company_disp:<35} | {metric_disp:<35} | {m['value']}")
        
        print("-" * 110)
        print(f"Total instances found: {len(matches)}")


def handle_all_command(ticker_input):
    """Handle the 'all' command - show all historical database entries for a ticker.
    
    Args:
        ticker_input: Ticker symbol or company name
    """
    if not ticker_input.strip():
        print("Please provide a ticker symbol. Example: all GOOGL")
        return
    
    # Try to resolve to ticker
    resolved_name, ticker = resolve_to_company_name(ticker_input)
    if not ticker:
        ticker = ticker_input.strip().upper()
    
    versions = db.get_all_versions(ticker)
    
    if not versions:
        print(f"No entries found for {ticker} in the database.")
        return
    
    display_title = get_current_display_name(ticker, versions[0].get('company_name') if versions else resolved_name)
    print(f"\nAll database entries for {display_title}:")
    print("=" * 110)
    # Header
    print(f"{'ID':<6} {'Model':<35} {'Timestamp':<30} {'Total Score':<12}")
    print("-" * 110)
    
    for v in versions:
        model = v.get('model', 'unknown')
        timestamp = v.get('timestamp', 'unknown')
        total_score = v.get('total_score', 0)
        id_val = v.get('id', '-')
        
        # Format timestamp for better readability if it's ISO format
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp)
            display_ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            display_ts = timestamp
            
        print(f"{id_val:<6} {model:<35} {display_ts:<30} {total_score:<12.2f}")
    print("-" * 110)
    print(f"Total entries found: {len(versions)}")


def handle_compare_command(ticker_input):
    """Handle the 'compare' command - compare the last 2 entries from different models.
    
    Args:
        ticker_input: Ticker symbol or company name
    """
    if not ticker_input.strip():
        print("Please provide a ticker symbol. Example: compare GOOGL")
        return
    
    # Try to resolve to ticker
    resolved_name, ticker = resolve_to_company_name(ticker_input)
    if not ticker:
        ticker = ticker_input.strip().upper()
    
    versions = db.get_all_versions(ticker)
    
    if len(versions) < 2:
        print(f"Error: Found only {len(versions)} entry for {ticker}. Need at least 2 entries with different models to compare.")
        return
    
    # Find the last two entries with different models
    entry1 = versions[0]
    entry2 = None
    
    for v in versions[1:]:
        if v.get('model') != entry1.get('model'):
            entry2 = v
            break
            
    if not entry2:
        print(f"Error: Could not find two entries with different models for {ticker}.")
        print(f"Latest entries ({len(versions)} total) all use model: {entry1.get('model')}")
        return
    
    display_title = get_current_display_name(ticker, versions[0].get('company_name') if versions else resolved_name)
    print(f"\nComparing latest entries for {display_title} from different models:")
    print("=" * 110)
    
    # Header
    m1_name = entry1.get('model', 'Model 1')
    m2_name = entry2.get('model', 'Model 2')
    m1_ts = entry1.get('timestamp', '').split('T')[0]
    m2_ts = entry2.get('timestamp', '').split('T')[0]
    
    print(f"{'Metric':<40} | {m1_name[:30]:<30} | {m2_name[:30]:<30} | {'Diff':<8}")
    print(f"{'':<40} | {m1_ts:<30} | {m2_ts:<30} |")
    print("-" * 110)
    
    metrics = [
        ('moat_score', 'Moat Score'),
        ('barriers_score', 'Barriers Score'),
        ('disruption_risk', 'Disruption Risk'),
        ('switching_cost', 'Switching Cost'),
        ('brand_strength', 'Brand Strength'),
        ('competition_intensity', 'Competition Intensity'),
        ('network_effect', 'Network Effect'),
        ('product_differentiation', 'Product Differentiation'),
        ('innovativeness_score', 'Innovativeness'),
        ('growth_opportunity', 'Growth Opportunity'),
        ('riskiness_score', 'Riskiness'),
        ('pricing_power', 'Pricing Power'),
        ('ambition_score', 'Ambition'),
        ('bargaining_power_of_customers', 'Bargaining Power (Cust)'),
        ('bargaining_power_of_suppliers', 'Bargaining Power (Supp)'),
        ('product_quality_score', 'Product / Service Quality'),
        ('culture_employee_satisfaction_score', 'Culture/Satisfaction'),
        ('trailblazer_score', 'Trailblazer'),
        ('management_quality_score', 'Management Quality'),
        ('ai_knowledge_score', 'AI Knowledge'),
        ('size_well_known_score', 'Size / Well Known'),
        ('ethical_healthy_environmental_score', 'Ethical/Environmental'),
        ('long_term_orientation_score', 'Long Term Orientation')
    ]
    
    for key, label in metrics:
        v1 = entry1.get(key)
        v2 = entry2.get(key)
        
        v1_display = f"{v1:<30.1f}" if v1 is not None else f"{'N/A':<30}"
        v2_display = f"{v2:<30.1f}" if v2 is not None else f"{'N/A':<30}"
        
        if v1 is not None and v2 is not None:
            diff = v1 - v2
            diff_str = f"{diff:+.1f}" if diff != 0 else "0.0"
        else:
            diff_str = "N/A"
            
        print(f"{label:<40} | {v1_display} | {v2_display} | {diff_str:<8}")
        
    print("-" * 110)
    t1 = entry1.get('total_score', 0)
    t2 = entry2.get('total_score', 0)
    t_diff = t1 - t2
    t_diff_str = f"{t_diff:+.1f}" if t_diff != 0 else "0.0"
    print(f"{'TOTAL SCORE':<40} | {t1:<30.1f} | {t2:<30.1f} | {t_diff_str:<8}")
    print("=" * 110)


def handle_redo_command(tickers_input):
    """Handle the redo command - rescore ticker(s) even if they already have scores.
    
    Args:
        tickers_input: Space-separated ticker symbols to rescore
    """
    if not tickers_input.strip():
        print("Please provide ticker symbol(s). Example: redo AAPL or redo AAPL MSFT GOOGL")
        return
    
    tickers_raw = tickers_input.strip().split()
    # Deduplicate tickers while preserving order (case-insensitive)
    seen = set()
    tickers = []
    for ticker in tickers_raw:
        ticker_upper = ticker.upper()
        if ticker_upper not in seen:
            seen.add(ticker_upper)
            tickers.append(ticker)
    
    if len(tickers) < len(tickers_raw):
        print(f"Note: Removed {len(tickers_raw) - len(tickers)} duplicate ticker(s).")
    
    if len(tickers) == 1:
        # Single ticker - use existing behavior
        score_single_ticker(tickers[0], force_rescore=True)
    else:
        # Multiple tickers - process them in batch
        print(f"\nProcessing {len(tickers)} ticker(s) for rescoring...")
        print("=" * 80)
        
        # Track totals for summary
        batch_start_time = time.time()
        batch_total_tokens = 0
        batch_total_cost = 0.0
        batch_token_usage_combined = {
            'input_tokens': 0,
            'output_tokens': 0,
            'cached_tokens': 0,
            'thinking_tokens': 0
        }
        successful_count = 0
        
        for i, ticker in enumerate(tickers, 1):
            ticker_upper = ticker.strip().upper()
            # Try to resolve name from DB or lookup
            company_name, _ = resolve_to_company_name(ticker_upper)
            display_name = get_current_display_name(ticker_upper, company_name)
            print(f"\n[{i}/{len(tickers)}] Rescoring {display_name}...")
            result = score_single_ticker(ticker, silent=True, batch_mode=True, force_rescore=True)
            if result:
                if result['success']:
                    successful_count += 1
                    # Accumulate tokens and cost
                    tokens = result.get('total_tokens', 0)
                    batch_total_tokens += tokens
                    token_usage = result.get('token_usage')
                    if token_usage:
                        batch_token_usage_combined['input_tokens'] += token_usage.get('input_tokens', token_usage.get('prompt_tokens', 0) or 0)
                        batch_token_usage_combined['output_tokens'] += token_usage.get('output_tokens', token_usage.get('completion_tokens', 0) or 0)
                        cached = token_usage.get('cached_tokens', 0) or token_usage.get('cached_input_tokens', 0) or token_usage.get('prompt_cache_hit_tokens', 0) or 0
                        batch_token_usage_combined['cached_tokens'] += cached
                        batch_token_usage_combined['thinking_tokens'] += token_usage.get('thinking_tokens', 0) or 0
                    model_used = result.get('model_used', get_model_for_ticker(ticker_upper))
                    cost = calculate_token_cost(tokens, model=model_used, token_usage=token_usage)
                    batch_total_cost += cost
                    
                    total = result.get('total')
                    model_name = result.get('scores', {}).get('model', 'Unknown') if result.get('scores') else 'Unknown'
                    if total is not None:
                        all_totals = get_all_total_scores()
                        percentile = calculate_percentile_rank(total, all_totals) if all_totals and len(all_totals) > 1 else None
                        total_str = format_total_score(total, percentile)
                        print(f"  ✓ {ticker_upper} rescored successfully - {total_str} (Model: {model_name})")
                    else:
                        print(f"  ✓ {ticker_upper} rescored successfully (Model: {model_name})")
                else:
                    print(f"  ✗ Error rescoring {ticker_upper}: {result.get('error', 'Unknown error')}")
        
        # Display summary
        batch_elapsed_time = time.time() - batch_start_time
        print("\n" + "=" * 80)
        print(f"Redo Summary ({successful_count}/{len(tickers)} successful):")
        print(f"  Time: {batch_elapsed_time:.2f}s")
        print(f"  Total tokens: {batch_total_tokens:,}")
        if batch_token_usage_combined['thinking_tokens'] > 0:
            print(f"  Token breakdown: input={batch_token_usage_combined['input_tokens']:,}, output={batch_token_usage_combined['output_tokens']:,} (includes {batch_token_usage_combined['thinking_tokens']:,} thinking), cached={batch_token_usage_combined['cached_tokens']:,}")
        else:
            print(f"  Token breakdown: input={batch_token_usage_combined['input_tokens']:,}, output={batch_token_usage_combined['output_tokens']:,}, cached={batch_token_usage_combined['cached_tokens']:,}")
        batch_cost_cents = batch_total_cost * 100
        print(f"  Total cost: {batch_cost_cents:.4f} cents")


def handle_upgrade_command():
    """Handle the upgrade command - rescore all tickers that don't have the current model."""
    # Get the current model
    current_model = get_model_for_ticker("DUMMY")  # Get current model (doesn't depend on ticker)
    
    print(f"\nUpgrade: Rescoring all tickers not using current model '{current_model}'...")
    print("=" * 80)
    
    # Load all scores
    scores_data = load_scores()
    companies = scores_data.get("companies", {})
    
    if not companies:
        print("No companies found in scores.json")
        return
    
    # Find tickers that need upgrading
    tickers_to_upgrade = []
    ticker_lookup = load_ticker_lookup()
    
    for ticker, company_data in companies.items():
        ticker_upper = ticker.upper()
        # company_data IS the scores dict, not a dict containing a "scores" key
        existing_model = company_data.get("model")
        
        # If no model specified or model doesn't match current, add to upgrade list
        if not existing_model or existing_model != current_model:
            company_name = ticker_lookup.get(ticker_upper, ticker_upper)
            old_model = existing_model or "Unknown"
            tickers_to_upgrade.append((ticker_upper, company_name, old_model))
    
    if not tickers_to_upgrade:
        print(f"All tickers are already using the current model '{current_model}'.")
        print("No upgrade needed!")
        return
    
    print(f"Found {len(tickers_to_upgrade)} ticker(s) to upgrade:")
    for ticker, company_name, old_model in tickers_to_upgrade:
        display_name = get_current_display_name(ticker, company_name)
        print(f"  - {display_name}: {old_model} -> {current_model}")
    
    # Ask for confirmation
    print()
    confirm = input(f"Proceed with upgrading {len(tickers_to_upgrade)} ticker(s)? (y/n): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("Upgrade cancelled.")
        return
    
    # Rescore all tickers that need upgrading
    print(f"\nProcessing {len(tickers_to_upgrade)} ticker(s) for upgrade...")
    print("=" * 80)
    
    successful = 0
    failed = 0
    total_upgrade_tokens = 0
    total_upgrade_cost = 0.0
    
    for i, (ticker, company_name, old_model) in enumerate(tickers_to_upgrade, 1):
        display_name = get_current_display_name(ticker, company_name)
        print(f"\n[{i}/{len(tickers_to_upgrade)}] Upgrading {display_name}...")
        print(f"  Old model: {old_model} -> New model: {current_model}")
        
        # Track timing
        start_time = time.time()
        result = score_single_ticker(ticker, silent=True, batch_mode=True, force_rescore=True)
        elapsed_time = time.time() - start_time
        
        if result:
            if result['success']:
                total = result.get('total')
                model_name = result.get('scores', {}).get('model', 'Unknown') if result.get('scores') else 'Unknown'
                total_tokens = result.get('total_tokens', 0)
                token_usage = result.get('token_usage')
                model_used = result.get('model_used', current_model)
                
                # Calculate cost
                cost = 0.0
                if total_tokens > 0 and model_used:
                    cost = calculate_token_cost(total_tokens, model=model_used, token_usage=token_usage)
                    total_upgrade_tokens += total_tokens
                    total_upgrade_cost += cost
                
                # Format token breakdown
                token_info = f"{total_tokens:,} tokens"
                if token_usage:
                    input_tokens = token_usage.get('input_tokens') if 'input_tokens' in token_usage else token_usage.get('prompt_tokens', 0)
                    output_tokens = token_usage.get('output_tokens') if 'output_tokens' in token_usage else token_usage.get('completion_tokens', 0)
                    cached_tokens = (token_usage.get('cached_tokens') if 'cached_tokens' in token_usage else
                                   token_usage.get('cached_input_tokens') if 'cached_input_tokens' in token_usage else
                                   token_usage.get('prompt_cache_hit_tokens', 0))
                    if cached_tokens > 0:
                        token_info = f"{input_tokens:,} input, {output_tokens:,} output, {cached_tokens:,} cached"
                    else:
                        token_info = f"{input_tokens:,} input, {output_tokens:,} output"
                
                # Format cost
                cost_str = f"{cost * 100:.4f} cents" if cost > 0 else "N/A"
                
                # Format time
                time_str = f"{elapsed_time:.2f}s"
                
                if total is not None:
                    all_totals = get_all_total_scores()
                    percentile = calculate_percentile_rank(total, all_totals) if all_totals and len(all_totals) > 1 else None
                    total_str = format_total_score(total, percentile)
                    print(f"  ✓ {ticker} upgraded successfully - {total_str} (Model: {model_name})")
                else:
                    print(f"  ✓ {ticker} upgraded successfully (Model: {model_name})")
                print(f"    Time: {time_str} | Tokens: {token_info} | Cost: {cost_str}")
                successful += 1
            else:
                print(f"  ✗ Error upgrading {ticker}: {result.get('error', 'Unknown error')}")
                failed += 1
        else:
            print(f"  ✗ Error upgrading {ticker}: Invalid ticker or lookup failed")
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"Upgrade complete!")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Total: {len(tickers_to_upgrade)}")
    if successful > 0:
        print(f"  Total tokens: {total_upgrade_tokens:,}")
        print(f"  Total cost: {total_upgrade_cost * 100:.4f} cents")


def migrate_scores_to_uppercase():
    """Migrate existing scores to uppercase ticker keys and remove duplicates.
    Tickers (1-5 chars, alphabetic) are converted to uppercase.
    Company names remain lowercase."""
    scores_data = load_scores()
    uppercase_companies = {}
    ticker_lookup = load_ticker_lookup()
    
    for company, data in scores_data["companies"].items():
        # Check if it's a ticker (short, alphabetic)
        if len(company) <= 5 and company.replace(' ', '').isalpha():
            # It's a ticker - convert to uppercase
            company_upper = company.upper()
            if company_upper not in uppercase_companies:
                uppercase_companies[company_upper] = data
            else:
                # Duplicate found - keep the newer one
                existing_date = uppercase_companies[company_upper].get('date', '1900-01-01')
                new_date = data.get('date', '1900-01-01')
                
                if 'timestamp' in uppercase_companies[company_upper] and 'timestamp' in data:
                    existing_time = datetime.fromisoformat(uppercase_companies[company_upper].get('timestamp', '1900-01-01T00:00:00'))
                    new_time = datetime.fromisoformat(data.get('timestamp', '1900-01-01T00:00:00'))
                    if new_time > existing_time:
                        uppercase_companies[company_upper] = data
                elif new_date > existing_date:
                    uppercase_companies[company_upper] = data
        else:
            # It's a company name - keep as lowercase
            if company not in uppercase_companies:
                uppercase_companies[company] = data
            else:
                # Duplicate found - keep the newer one
                existing_date = uppercase_companies[company].get('date', '1900-01-01')
                new_date = data.get('date', '1900-01-01')
                
                if 'timestamp' in uppercase_companies[company] and 'timestamp' in data:
                    existing_time = datetime.fromisoformat(uppercase_companies[company].get('timestamp', '1900-01-01T00:00:00'))
                    new_time = datetime.fromisoformat(data.get('timestamp', '1900-01-01T00:00:00'))
                    if new_time > existing_time:
                        uppercase_companies[company] = data
                elif new_date > existing_date:
                    uppercase_companies[company] = data
    
    scores_data["companies"] = uppercase_companies
    save_scores(scores_data)
    return len(scores_data["companies"])


async def fill_single_company_async(grok, company_name, company_scores, ticker_lookup, company_index, total_companies):
    """Async function to fill missing scores for a single company.
    
    Returns:
        tuple: (company_name, company_scores, tokens_used, cost)
    """
    try:
        # Determine if company_name is a ticker and get actual company name
        ticker = None
        actual_company_name = company_name
        company_name_upper = company_name.upper()
        
        # Check if it's a ticker (short, alphabetic, uppercase)
        if len(company_name) <= 5 and company_name.replace(' ', '').isalpha():
            ticker = company_name_upper
            # Try to get company name from ticker lookup
            actual_company_name = ticker_lookup.get(ticker, company_name)
        else:
            # Might be a company name, try to find ticker
            ticker = get_ticker_from_company_name(company_name)
            if ticker:
                actual_company_name = ticker_lookup.get(ticker, company_name)
            else:
                actual_company_name = company_name
        
        # Display format: "TICKER (Company Name)" or just "Company Name" if no ticker
        if ticker:
            display_name = f"{ticker} ({actual_company_name})"
        else:
            display_name = actual_company_name.capitalize()
        
        print(f"[{company_index}/{total_companies}] Processing {display_name}...")
        
        # Get list of missing score keys
        missing_keys = [key for key in SCORE_DEFINITIONS if not company_scores[key]]
        
        # Preserve existing model or determine from ticker
        existing_model = company_scores.get('model')
        if not existing_model:
            existing_model = get_model_for_ticker(ticker) if ticker else "grok-4-1-fast-reasoning"
        
        tokens_used = 0
        token_usage = None
        cost = 0.0
        
        if missing_keys:
            # Query missing scores in parallel (this uses ThreadPoolExecutor internally)
            # Run in executor to make it async-compatible
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()
            
            missing_scores, tokens_used, token_usage, model_used = await loop.run_in_executor(
                None,
                lambda: query_all_scores_async(grok, actual_company_name, missing_keys,
                                              batch_mode=True, silent=True, ticker=ticker)
            )
            # Update company_scores with the new scores
            company_scores.update(missing_scores)
            # Use the model from the query (should match existing_model, but use query result)
            company_scores['model'] = model_used
            
            # Calculate cost
            if tokens_used > 0:
                cost = calculate_token_cost(tokens_used, model=model_used, token_usage=token_usage)
            
            print(f"  ✓ {display_name} - filled {len(missing_keys)} missing score(s)")
        
        return company_name, company_scores, tokens_used, token_usage, cost
    except Exception as e:
        print(f"  ✗ Error processing {company_name}: {e}")
        return company_name, company_scores, 0, None, 0.0


def fill_missing_barriers_scores():
    """Fill in missing scores for all companies using SCORE_DEFINITIONS.
    Processes companies in batches of 20 using async."""
    try:
        scores_data = load_scores()
        grok = get_api_client()
        
        companies_to_score = []
        for company_name, data in scores_data["companies"].items():
            moat_score = data.get('moat_score', data.get('score'))
            if moat_score is None:
                continue
            
            missing_scores = []
            company_scores = {}
            for score_key in SCORE_DEFINITIONS:
                company_scores[score_key] = data.get(score_key)
                if company_scores[score_key] is None:
                    missing_scores.append(SCORE_DEFINITIONS[score_key]['display_name'])
            
            if missing_scores:
                companies_to_score.append((company_name, company_scores))
        
        if not companies_to_score:
            print("\nAll companies already have all scores!")
            return
        
        print(f"\nFound {len(companies_to_score)} companies missing scores:")
        print("=" * 60)
        for company_name, company_scores in companies_to_score:
            moat = company_scores.get('moat_score', 'N/A')
            missing = [SCORE_DEFINITIONS[k]['display_name'] for k, v in company_scores.items() if v is None]
            # Display ticker in uppercase if it looks like a ticker, otherwise capitalize
            display_name = company_name.upper() if len(company_name) <= 5 and company_name.replace(' ', '').isalpha() else company_name.capitalize()
            print(f"{display_name}: Moat {moat}/10 - Missing: {', '.join(missing)}")
        
        print(f"\nQuerying missing scores in batches of 20...")
        print("=" * 60)
        
        ticker_lookup = load_ticker_lookup()
        
        # Track totals for summary
        fill_start_time = time.time()
        fill_total_tokens = 0
        fill_total_cost = 0.0
        fill_token_usage_combined = {
            'input_tokens': 0,
            'output_tokens': 0,
            'cached_tokens': 0,
            'thinking_tokens': 0
        }
        
        # Process companies in batches of 20 using async
        async def process_all_batches():
            nonlocal fill_total_tokens, fill_total_cost, fill_token_usage_combined
            batch_size = 20
            total_batches = (len(companies_to_score) + batch_size - 1) // batch_size
            
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(companies_to_score))
                batch = companies_to_score[start_idx:end_idx]
                
                print(f"\nProcessing batch {batch_num + 1}/{total_batches} ({len(batch)} companies)...")
                
                # Create async tasks for this batch
                tasks = []
                for i, (company_name, company_scores) in enumerate(batch):
                    company_index = start_idx + i + 1
                    task = fill_single_company_async(grok, company_name, company_scores.copy(), ticker_lookup, company_index, len(companies_to_score))
                    tasks.append(task)
                
                # Run all tasks in the batch concurrently
                results = await asyncio.gather(*tasks)
                
            # Update scores_data with results and save, accumulate tokens/cost
            for company_name, updated_scores, tokens_used, token_usage, cost in results:
                scores_data["companies"][company_name] = updated_scores
                fill_total_tokens += tokens_used
                fill_total_cost += cost
                if token_usage:
                    fill_token_usage_combined['input_tokens'] += token_usage.get('input_tokens', token_usage.get('prompt_tokens', 0) or 0)
                    fill_token_usage_combined['output_tokens'] += token_usage.get('output_tokens', token_usage.get('completion_tokens', 0) or 0)
                    cached = token_usage.get('cached_tokens', 0) or token_usage.get('cached_input_tokens', 0) or token_usage.get('prompt_cache_hit_tokens', 0) or 0
                    fill_token_usage_combined['cached_tokens'] += cached
                    fill_token_usage_combined['thinking_tokens'] += token_usage.get('thinking_tokens', 0) or 0
                
                # Save EACH company as it's completed
                save_scores(scores_data, ticker=company_name)
            
            print(f"  Batch {batch_num + 1} complete - saved progress")
        
        # Run the async function
        asyncio.run(process_all_batches())
        
        fill_elapsed_time = time.time() - fill_start_time
        
        print("\n" + "=" * 60)
        print("All missing scores have been filled!")
        print(f"\nFill Summary ({len(companies_to_score)} companies):")
        print(f"  Time: {fill_elapsed_time:.2f}s")
        print(f"  Total tokens: {fill_total_tokens:,}")
        if fill_token_usage_combined['thinking_tokens'] > 0:
            print(f"  Token breakdown: input={fill_token_usage_combined['input_tokens']:,}, output={fill_token_usage_combined['output_tokens']:,} (includes {fill_token_usage_combined['thinking_tokens']:,} thinking), cached={fill_token_usage_combined['cached_tokens']:,}")
        else:
            print(f"  Token breakdown: input={fill_token_usage_combined['input_tokens']:,}, output={fill_token_usage_combined['output_tokens']:,}, cached={fill_token_usage_combined['cached_tokens']:,}")
        fill_cost_cents = fill_total_cost * 100
        print(f"  Total cost: {fill_cost_cents:.4f} cents")
        
    except ValueError as e:
        print(f"Error: {e}")
        print("\nTo fix this:")
        print("1. Get an API key from https://console.x.ai/")
        print("2. Set the XAI_API_KEY environment variable:")
        print("   export XAI_API_KEY='your_api_key_here'")
        
    except Exception as e:
        print(f"Error: {e}")


def view_scores(score_type=None, show_names=None):
    """Display all stored moat scores using SCORE_DEFINITIONS.
    
    Args:
        score_type: Can be None (show totals), a score type name (show specific score), 
                    or a ticker/company name (show all scores for that company).
        show_names: If provided, overrides GLOBAL_SHOW_NAMES.
    """
    if show_names is None:
        show_names = GLOBAL_SHOW_NAMES
        
    scores_data = load_scores()
    
    if not scores_data["companies"]:
        print("No scores stored yet.")
        return
    
    ticker_lookup = load_ticker_lookup()
    
    # Helper function to get display name
    def get_display_name(key, company_name=None):
        # In this context, 'key' is the ticker used for storage
        return get_current_display_name(key, company_name)
    
    # Check if score_type is actually a ticker or company name
    if score_type:
        # Try direct match
        if score_type in scores_data["companies"]:
            data = scores_data["companies"][score_type]
        # Try uppercase (for ticker lookup)
        elif score_type.upper() in scores_data["companies"]:
            data = scores_data["companies"][score_type.upper()]
        # Try lowercase (for company name lookup)
        elif score_type.lower() in scores_data["companies"]:
            data = scores_data["companies"][score_type.lower()]
        else:
            # Try to resolve as ticker to company name
            resolved_name, ticker = resolve_to_company_name(score_type)
            if ticker and ticker in scores_data["companies"]:
                data = scores_data["companies"][ticker]
            elif resolved_name.lower() in scores_data["companies"]:
                data = scores_data["companies"][resolved_name.lower()]
            else:
                print(f"Company '{score_type}' not found in scores.")
                return
        
        display_name = get_display_name(score_type, data.get('company_name'))
        model_name = data.get('model', 'Unknown')
        print(f"\n{display_name} Scores (Model: {model_name}):")
        print("=" * 80)
        
        total = 0
        all_present = True
        scores_list = []
        
        for score_key in SCORE_DEFINITIONS:
            score_def = SCORE_DEFINITIONS[score_key]
            score_val = data.get(score_key, 'N/A')
            
            if score_val is None or score_val == 'N/A':
                score_display = 'N/A'
                all_present = False
                sort_value = -1  # Put N/A scores at the end
            else:
                try:
                    val = float(score_val)
                    weight = SCORE_WEIGHTS.get(score_key, 1.0)
                    # Use actual score value for sorting (descending order)
                    sort_value = val
                    # For reverse scores, invert to get "goodness" value for total calculation
                    if score_def['is_reverse']:
                        total += (10 - val) * weight
                    else:
                        total += val * weight
                    score_display = score_val
                except (ValueError, TypeError):
                    score_display = 'N/A'
                    all_present = False
                    sort_value = -1
            
            scores_list.append((sort_value, score_def['display_name'], score_display))
        
        # Sort by actual score value descending (highest scores first)
        scores_list.sort(reverse=True, key=lambda x: x[0])
        
        # Display sorted scores
        for sort_value, display_name, score_display in scores_list:
            print(f"{display_name:25} {score_display:>8}")
        
        if all_present:
            total_str = format_total_score(total)
            print(f"{'Total':25} {total_str:>8}")
        
        return
    
    # Helper function to calculate total score
    def get_total_score(item):
        data = item[1]
        total = 0
        for score_key, score_def in SCORE_DEFINITIONS.items():
            score_val = data.get(score_key, 'N/A')
            weight = SCORE_WEIGHTS.get(score_key, 1.0)
            if score_val is None or score_val == 'N/A':
                if score_def['is_reverse']:
                    total += 10 * weight
                continue
            
            try:
                val = float(score_val)
                if score_def['is_reverse']:
                    total += (10 - val) * weight
                else:
                    total += val * weight
            except (ValueError, TypeError):
                    pass
        return total
    
    sorted_companies = sorted(scores_data["companies"].items(), key=get_total_score, reverse=True)
    
    # If score_type not provided, show total scores for all companies
    if not score_type:
        print("\nStored Company Scores (Total only):")
        print("=" * 80)
        print(f"Number of stocks scored: {len(sorted_companies)}")
        print()
        
        # Calculate max name length for formatting
        display_names = []
        for company, data in sorted_companies:
            display_names.append(get_display_name(company, data.get('company_name')))
            
        max_name_len = max([len(name) for name in display_names]) if display_names else 30
        max_name_len = min(max_name_len, 50)  # Cap at 50 for layout
        
        # Calculate all totals for percentile calculation
        all_totals = []
        company_totals = {}
        for company, data in sorted_companies:
            total = 0
            all_present = True
            for score_key, score_def in SCORE_DEFINITIONS.items():
                score_val = data.get(score_key, 'N/A')
                weight = SCORE_WEIGHTS.get(score_key, 1.0)
                if score_val is None or score_val == 'N/A':
                    all_present = False
                    break
                try:
                    val = float(score_val)
                    if score_def['is_reverse']:
                        total += (10 - val) * weight
                    else:
                        total += val * weight
                except (ValueError, TypeError):
                    all_present = False
                    break
            
            if all_present:
                company_totals[company] = total
                all_totals.append(total)
        
        # Print column headers
        header_text = 'Company Name' if show_names else 'Company'
        print(f"{header_text:<{max_name_len}} {'Score':>8} {'Percentile':>12}")
        print("-" * (max_name_len + 8 + 12 + 2))
        
        # Display companies with percentiles (only show companies with complete scores)
        for company, data in sorted_companies:
            # Skip companies that don't have all scores
            if company not in company_totals:
                continue
                
            total = company_totals[company]
            max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS) * 10
            percentage = int((total / max_score) * 100)
            percentage_str = f"{percentage}"
            
            percentile = calculate_percentile_rank(total, all_totals) if len(all_totals) > 1 else None
            if percentile is not None:
                percentile_str = f"{percentile}"
            else:
                percentile_str = 'N/A'
            
            # Display ticker if available, otherwise company name
            display_key = get_display_name(company, data.get('company_name'))
            if len(display_key) > max_name_len:
                display_key = display_key[:max_name_len-3] + "..."
            print(f"{display_key:<{max_name_len}} {percentage_str:>8} {percentile_str:>12}")
        return
    
    # If we get here, score_type is a score type (not a company)
    score_type_lower = score_type.lower()
    
    score_map = {name.lower() or key.lower(): key for key, val in SCORE_DEFINITIONS.items() 
                for name in [val['display_name'], key] + key.split('_')}
    
    matching_key = None
    for name, key in score_map.items():
        if score_type_lower in name or name in score_type_lower:
            matching_key = key
            break
    
    if not matching_key:
        print(f"Unknown score type: {score_type}")
        print(f"Available types: {', '.join([key.split('_')[0] for key in SCORE_DEFINITIONS.keys()])}")
        return
    
    score_def = SCORE_DEFINITIONS[matching_key]
    print(f"\nStored Company Scores ({score_def['display_name']}):")
    print("=" * 80)
    
    def get_field_score(item):
        data = item[1]
        score = data.get(matching_key, 'N/A')
        try:
            return float(score) if score is not None and score != 'N/A' else 0
        except (ValueError, TypeError):
            return 0
    
    sorted_by_field = sorted(scores_data["companies"].items(), key=get_field_score, reverse=True)
    max_name_len = max([len(get_display_name(company, data.get('company_name'))) for company, data in sorted_by_field]) if sorted_by_field else 0
    
    for company, data in sorted_by_field:
        score = data.get(matching_key, 'N/A')
        if score is not None and score != 'N/A':
            try:
                score_float = float(score)
                score = f"{int(score_float)}" if score_float == int(score_float) else f"{score_float:.1f}"
            except (ValueError, TypeError):
                pass
        
        # Display ticker if available, otherwise company name
        display_key = get_display_name(company, data.get('company_name'))
        if len(display_key) > 30:
            display_key = display_key[:30]
        print(f"{display_key:<{min(max_name_len, 30)}} {score:>8}")


def delete_company(input_str):
    """Delete a company's scores from the JSON file.
    
    Args:
        input_str: Ticker symbol or company name to delete
    """
    scores_data = load_scores()
    
    if not scores_data["companies"]:
        print("No scores stored yet.")
        return
    
    # Try to find the company using the same resolution logic as view_scores
    storage_key = None
    display_name = None
    
    # Check direct match (uppercase for ticker, lowercase for company name)
    input_upper = input_str.strip().upper()
    input_lower = input_str.strip().lower()
    
    # First try as ticker (uppercase)
    if input_upper in scores_data["companies"]:
        storage_key = input_upper
        ticker_lookup = load_ticker_lookup()
        company_name = ticker_lookup.get(input_upper, input_upper)
        display_name = f"{input_upper} ({company_name})"
    # Then try as company name (lowercase)
    elif input_lower in scores_data["companies"]:
        storage_key = input_lower
        # Try to find ticker for display
        ticker = get_ticker_from_company_name(input_lower)
        if ticker:
            company_name = load_ticker_lookup().get(ticker, input_lower)
            display_name = f"{ticker.upper()} ({company_name})"
        else:
            display_name = input_lower
    else:
        # Try to resolve ticker to company name
        resolved_name, ticker = resolve_to_company_name(input_str)
        if ticker and ticker in scores_data["companies"]:
            storage_key = ticker
            company_name = load_ticker_lookup().get(ticker, resolved_name)
            display_name = f"{ticker.upper()} ({company_name})"
        elif resolved_name.lower() in scores_data["companies"]:
            storage_key = resolved_name.lower()
            display_name = resolved_name
    
    if not storage_key:
        print(f"Company '{input_str}' not found in scores.")
        print("\nAvailable companies:")
        for key in sorted(scores_data["companies"].keys()):
            # Try to format display name
            if len(key) <= 5 and key.replace(' ', '').isalpha():
                ticker_lookup = load_ticker_lookup()
                company_name = ticker_lookup.get(key.upper(), key)
                print(f"  {key.upper()} ({company_name})")
            else:
                ticker = get_ticker_from_company_name(key)
                if ticker:
                    print(f"  {ticker.upper()} ({key})")
                else:
                    print(f"  {key}")
        return
    
    # Confirm deletion
    print(f"\nFound: {display_name}")
    confirm = input("Are you sure you want to delete this company's scores? (yes/no): ").strip().lower()
    
    if confirm in ['yes', 'y']:
        # Delete from DB first
        if storage_key:
            db.delete_score(storage_key)
        
        # Then update the local cache
        if storage_key in scores_data["companies"]:
            del scores_data["companies"][storage_key]
            
        print(f"\n{display_name} has been deleted from scores.")
    else:
        print("Deletion cancelled.")


def show_metrics_menu():
    """Display a numbered menu of all available metrics."""
    print("\nAvailable Metrics:")
    print("=" * 40)
    metrics_list = list(SCORE_DEFINITIONS.items())
    for i, (score_key, score_def) in enumerate(metrics_list, 1):
        print(f"{i:2}. {score_def['display_name']}")
    print()
    return metrics_list


def rank_by_metric(metric_key):
    """Display ranking of all companies for a specific metric.
    
    Args:
        metric_key: The key of the metric to rank by
    """
    scores_data = load_scores()
    
    if not scores_data["companies"]:
        print("No scores stored yet.")
        return
    
    if metric_key not in SCORE_DEFINITIONS:
        print(f"Error: Invalid metric key '{metric_key}'")
        return
    
    score_def = SCORE_DEFINITIONS[metric_key]
    is_reverse = score_def['is_reverse']
    
    # Helper function to get display name
    def get_display_name(key, company_name=None):
        # In this context, 'key' is the ticker used for storage
        return get_current_display_name(key, company_name)
    
    # Collect all scores for this metric
    rankings = []
    for company_key, data in scores_data["companies"].items():
        score_val = data.get(metric_key, 'N/A')
        if score_val is not None and score_val != 'N/A':
            try:
                val = float(score_val)
                # For reverse scores, invert to get "goodness" value for ranking
                if is_reverse:
                    sort_value = 10 - val
                else:
                    sort_value = val
                display_name = get_display_name(company_key, data.get('company_name'))
                rankings.append((sort_value, val, display_name, company_key))
            except (ValueError, TypeError):
                pass
    
    if not rankings:
        print(f"\nNo scores found for {score_def['display_name']}.")
        return
    
    # Sort by score descending
    rankings.sort(reverse=True, key=lambda x: x[0])
    
    # Display rankings
    print(f"\nRankings by {score_def['display_name']}:")
    print("=" * 80)
    print(f"{'Rank':<6} {'Company':<40} {'Score':>8}")
    print("-" * 80)
    
    for rank, (sort_value, original_val, display_name, company_key) in enumerate(rankings, 1):
        # Format the original value for display
        try:
            score_float = float(original_val)
            if score_float == int(score_float):
                score_str = str(int(score_float))
            else:
                score_str = f"{score_float:.1f}"
        except (ValueError, TypeError):
            score_str = str(original_val)
        
        # Truncate display name if too long
        if len(display_name) > 38:
            display_name = display_name[:35] + "..."
        
        print(f"{rank:<6} {display_name:<40} {score_str:>8}")


def handle_rank_command():
    """Handle the rank command - show menu and get user selection."""
    metrics_list = show_metrics_menu()
    
    try:
        selection = input("Enter metric number (or 'cancel' to go back): ").strip()
        
        if selection.lower() in ['cancel', 'c', '']:
            return
        
        metric_num = int(selection)
        if metric_num < 1 or metric_num > len(metrics_list):
            print(f"Error: Please enter a number between 1 and {len(metrics_list)}")
            return
        
        # Get the metric key from the selection
        metric_key, _ = metrics_list[metric_num - 1]
        rank_by_metric(metric_key)
        
    except ValueError:
        print("Error: Please enter a valid number.")
    except KeyboardInterrupt:
        print("\nCancelled.")

def add_ticker_definition(ticker, company_name):
    """Add or update a custom ticker definition.
    
    Args:
        ticker: Ticker symbol (will be converted to uppercase)
        company_name: Company name to map to
        
    Returns:
        bool: True if successful, False otherwise
    """
    ticker_upper = ticker.strip().upper()
    company_name_stripped = company_name.strip()
    
    if not ticker_upper:
        print("Error: Ticker symbol cannot be empty.")
        return False
    
    if not company_name_stripped:
        print("Error: Company name cannot be empty.")
        return False
    
    # Load existing definitions
    custom_definitions = load_custom_ticker_definitions()
    
    # Check if it already exists
    if ticker_upper in custom_definitions:
        print(f"Updating existing definition: {ticker_upper} = {custom_definitions[ticker_upper]}")
    
    # Add or update
    custom_definitions[ticker_upper] = company_name_stripped
    
    # Save
    if save_custom_ticker_definitions(custom_definitions):
        print(f"✓ Added definition: {ticker_upper} = {company_name_stripped}")
        # Clear cache so it reloads with new definition
        global _ticker_cache
        _ticker_cache = None
        return True
    else:
        return False

def remove_ticker_definition(ticker):
    """Remove a custom ticker definition.
    
    Args:
        ticker: Ticker symbol to remove
        
    Returns:
        bool: True if successful, False otherwise
    """
    ticker_upper = ticker.strip().upper()
    
    # Load existing definitions
    custom_definitions = load_custom_ticker_definitions()
    
    if ticker_upper not in custom_definitions:
        print(f"Error: '{ticker_upper}' is not in custom ticker definitions.")
        return False
    
    # Remove
    company_name = custom_definitions.pop(ticker_upper)
    
    # Save
    if save_custom_ticker_definitions(custom_definitions):
        print(f"✓ Removed definition: {ticker_upper} = {company_name}")
        # Clear cache so it reloads without the removed definition
        global _ticker_cache
        _ticker_cache = None
        return True
    else:
        return False

def redefine_ticker_definition(new_ticker, old_ticker):
    """Rename a ticker definition from old_ticker to new_ticker.
    
    Args:
        new_ticker: New ticker symbol (will be converted to uppercase)
        old_ticker: Old ticker symbol to rename from
        
    Returns:
        bool: True if successful, False otherwise
    """
    new_ticker_upper = new_ticker.strip().upper()
    old_ticker_upper = old_ticker.strip().upper()
    
    if not new_ticker_upper:
        print("Error: New ticker symbol cannot be empty.")
        return False
    
    if not old_ticker_upper:
        print("Error: Old ticker symbol cannot be empty.")
        return False
    
    if new_ticker_upper == old_ticker_upper:
        print("Error: New and old ticker symbols are the same.")
        return False
    
    # Load existing definitions
    custom_definitions = load_custom_ticker_definitions()
    
    # Check if old ticker exists
    if old_ticker_upper not in custom_definitions:
        print(f"Error: '{old_ticker_upper}' is not in custom ticker definitions.")
        return False
    
    # Check if new ticker already exists
    if new_ticker_upper in custom_definitions:
        print(f"Error: '{new_ticker_upper}' already exists in custom ticker definitions.")
        print(f"  Current definition: {new_ticker_upper} = {custom_definitions[new_ticker_upper]}")
        return False
    
    # Get company name from old ticker
    company_name = custom_definitions[old_ticker_upper]
    
    # Check and update scores.json if old ticker exists there
    scores_updated = False
    if os.path.exists(SCORES_FILE):
        try:
            scores_data = load_scores()
            companies = scores_data.get("companies", {})
            
            # Check if old ticker exists in scores (case-insensitive check)
            old_ticker_lower = old_ticker_upper.lower()
            new_ticker_lower = new_ticker_upper.lower()
            
            # Find the actual key (might be lowercase in scores.json)
            old_key = None
            for key in companies.keys():
                if key.upper() == old_ticker_upper:
                    old_key = key
                    break
            
            if old_key:
                # Check if new ticker already exists in scores
                new_key_exists = False
                for key in companies.keys():
                    if key.upper() == new_ticker_upper:
                        new_key_exists = True
                        print(f"Warning: '{new_ticker_upper}' already exists in scores.json.")
                        print(f"  Existing entry: {key} = {companies[key].get('moat_score', 'N/A')}")
                        response = input(f"  Overwrite scores for '{new_ticker_upper}'? (yes/no): ").strip().lower()
                        if response not in ['yes', 'y']:
                            print("Cancelled. Scores.json not updated.")
                            return False
                        # Remove existing new ticker entry
                        del companies[key]
                        break
                
                # Move scores from old ticker to new ticker
                scores_data["companies"][new_ticker_lower] = companies[old_key]
                del companies[old_key]
                
                # Save scores
                save_scores(scores_data)
                scores_updated = True
                print(f"✓ Updated scores.json: {old_key} → {new_ticker_lower}")
        except Exception as e:
            print(f"Warning: Could not update scores.json: {e}")
    
    # Remove old ticker and add new ticker in definitions
    del custom_definitions[old_ticker_upper]
    custom_definitions[new_ticker_upper] = company_name
    
    # Save definitions
    if save_custom_ticker_definitions(custom_definitions):
        print(f"✓ Redefined: {old_ticker_upper} → {new_ticker_upper} = {company_name}")
        if not scores_updated:
            print(f"  (No scores found for '{old_ticker_upper}' in scores.json)")
        # Clear cache so it reloads with new definition
        global _ticker_cache
        _ticker_cache = None
        return True
    else:
        return False

def list_ticker_definitions():
    """List all custom ticker definitions."""
    custom_definitions = load_custom_ticker_definitions()
    
    if not custom_definitions:
        print("No custom ticker definitions found.")
        return
    
    print("\nCustom Ticker Definitions:")
    print("=" * 60)
    print(f"{'Ticker':<10} {'Company Name':<40}")
    print("-" * 60)
    
    for ticker in sorted(custom_definitions.keys()):
        company_name = custom_definitions[ticker]
        print(f"{ticker:<10} {company_name:<40}")
    
    print(f"\nTotal: {len(custom_definitions)} definition(s)")

def handle_define_command(command_input):
    """Handle the define command - add/remove/list ticker definitions.
    
    Args:
        command_input: Command input after 'define' keyword
    """
    command_input = command_input.strip()
    
    if not command_input:
        print("Usage:")
        print("  define SKH = SK Hynix          - Add/update a ticker definition")
        print("  define -r SKH                  - Remove a ticker definition")
        print("  define -l                      - List all custom ticker definitions")
        return
    
    # List command
    if command_input.lower() in ['-l', '--list', 'list']:
        list_ticker_definitions()
        return
    
    # Remove command
    if command_input.lower().startswith('-r ') or command_input.lower().startswith('--remove '):
        ticker = command_input[3:].strip() if command_input.lower().startswith('-r ') else command_input[9:].strip()
        if ticker:
            remove_ticker_definition(ticker)
        else:
            print("Error: Please provide a ticker symbol to remove.")
        return
    
    # Add/update command - look for "=" separator
    if '=' in command_input:
        parts = command_input.split('=', 1)
        if len(parts) == 2:
            ticker = parts[0].strip()
            company_name = parts[1].strip()
            
            if ticker and company_name:
                add_ticker_definition(ticker, company_name)
            else:
                print("Error: Both ticker and company name are required.")
                print("Usage: define SKH = SK Hynix")
        else:
            print("Error: Invalid format. Use: define SKH = SK Hynix")
    else:
        print("Error: Invalid command. Use:")
        print("  define SKH = SK Hynix          - Add/update a ticker definition")
        print("  define -r SKH                  - Remove a ticker definition")
        print("  define -l                      - List all custom ticker definitions")


def handle_redefine_command(command_input):
    """Handle the redefine command - rename a ticker definition.
    
    Args:
        command_input: Command input after 'redefine' keyword
    """
    command_input = command_input.strip()
    
    if not command_input:
        print("Usage:")
        print("  redefine NEW_TICKER = OLD_TICKER    - Rename a ticker definition")
        return
    
    # Look for "=" separator
    if '=' in command_input:
        parts = command_input.split('=', 1)
        if len(parts) == 2:
            new_ticker = parts[0].strip()
            old_ticker = parts[1].strip()
            
            if new_ticker and old_ticker:
                redefine_ticker_definition(new_ticker, old_ticker)
            else:
                print("Error: Both new and old ticker symbols are required.")
                print("Usage: redefine NEW_TICKER = OLD_TICKER")
        else:
            print("Error: Invalid format. Use: redefine NEW_TICKER = OLD_TICKER")
    else:
        print("Error: Invalid command. Use:")
        print("  redefine NEW_TICKER = OLD_TICKER    - Rename a ticker definition")


def load_peers():
    """Load peers data from JSON file.
    
    Returns:
        dict: Dictionary mapping ticker to list of peer tickers
    """
    if os.path.exists(PEERS_FILE):
        try:
            with open(PEERS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}


def save_peers(peers_data):
    """Save peers data to JSON file using atomic write to prevent corruption.
    
    Args:
        peers_data: Dictionary mapping ticker to list of peer tickers
    """
    # Create a temporary file in the same directory as the target file
    temp_dir = os.path.dirname(os.path.abspath(PEERS_FILE)) or '.'
    temp_fd, temp_path = tempfile.mkstemp(dir=temp_dir, suffix='.json', prefix='.peers_temp_')
    
    try:
        # Write to temporary file
        with os.fdopen(temp_fd, 'w') as f:
            json.dump(peers_data, f, indent=2)
        
        # Atomically replace the original file (on Windows, this may require removing the original first)
        if os.name == 'nt':  # Windows
            # On Windows, replace() may fail if file is open, so try remove first
            if os.path.exists(PEERS_FILE):
                os.remove(PEERS_FILE)
            shutil.move(temp_path, PEERS_FILE)
        else:  # Unix-like systems
            # On Unix, replace() is atomic
            os.replace(temp_path, PEERS_FILE)
        return True
    except Exception as e:
        # If anything goes wrong, try to clean up temp file and raise
        try:
            os.remove(temp_path)
        except:
            pass
        print(f"Error saving peers: {e}")
        return False


def load_peer_responses():
    """Load peer AI responses from JSON file.
    
    Returns:
        dict: Dictionary mapping ticker to list of response records
    """
    if os.path.exists(PEER_RESPONSES_FILE):
        try:
            with open(PEER_RESPONSES_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}


def save_peer_response(ticker, company_name, prompt, raw_response, parsed_company_names, model, elapsed_time, token_usage):
    """Save AI response for peer query to JSON file.
    
    Args:
        ticker: Ticker symbol (uppercase)
        company_name: Company name
        prompt: The prompt sent to AI
        raw_response: Raw response from AI
        parsed_company_names: List of parsed company names
        model: Model used
        elapsed_time: Time taken for query
        token_usage: Token usage dictionary
    """
    responses_data = load_peer_responses()
    
    # Create response record
    response_record = {
        'timestamp': datetime.now().isoformat(),
        'ticker': ticker,
        'company_name': company_name,
        'model': model,
        'prompt': prompt,
        'raw_response': raw_response,
        'parsed_company_names': parsed_company_names,
        'elapsed_time': elapsed_time,
        'token_usage': token_usage
    }
    
    # Add to responses data (append to list for this ticker)
    if ticker not in responses_data:
        responses_data[ticker] = []
    responses_data[ticker].append(response_record)
    
    # Save to file using atomic write
    temp_dir = os.path.dirname(os.path.abspath(PEER_RESPONSES_FILE)) or '.'
    temp_fd, temp_path = tempfile.mkstemp(dir=temp_dir, suffix='.json', prefix='.peer_responses_temp_')
    
    try:
        # Write to temporary file
        with os.fdopen(temp_fd, 'w') as f:
            json.dump(responses_data, f, indent=2)
        
        # Atomically replace the original file
        if os.name == 'nt':  # Windows
            if os.path.exists(PEER_RESPONSES_FILE):
                os.remove(PEER_RESPONSES_FILE)
            shutil.move(temp_path, PEER_RESPONSES_FILE)
        else:  # Unix-like systems
            os.replace(temp_path, PEER_RESPONSES_FILE)
        return True
    except Exception as e:
        # If anything goes wrong, try to clean up temp file
        try:
            os.remove(temp_path)
        except:
            pass
        print(f"Error saving peer response: {e}")
        return False


def load_ticker_conversions():
    """Load ticker conversions from JSON file.
    
    Returns:
        dict: Dictionary mapping company name to list of conversion records
    """
    if os.path.exists(TICKER_CONVERSIONS_FILE):
        try:
            with open(TICKER_CONVERSIONS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}


def save_ticker_conversion(company_name, ticker, is_public, method, ai_response=None, prompt=None, token_usage=None):
    """Save ticker conversion to JSON file.
    
    Args:
        company_name: Company name
        ticker: Ticker symbol
        is_public: True if public company, False if generated
        method: Method used (e.g., "exact_match", "partial_match", "ai_public", "ai_private", "generated_fallback", "exception_fallback")
        ai_response: Raw AI response (if AI was used)
        prompt: Prompt sent to AI (if AI was used)
        token_usage: Token usage dictionary (if AI was used)
    """
    conversions_data = load_ticker_conversions()
    
    # Create conversion record
    conversion_record = {
        'timestamp': datetime.now().isoformat(),
        'company_name': company_name,
        'ticker': ticker,
        'is_public': is_public,
        'method': method
    }
    
    # Add AI-related fields if available
    if ai_response is not None:
        conversion_record['ai_response'] = ai_response
    if prompt is not None:
        conversion_record['prompt'] = prompt
    if token_usage is not None:
        conversion_record['token_usage'] = token_usage
    
    # Add to conversions data (append to list for this company name)
    if company_name not in conversions_data:
        conversions_data[company_name] = []
    conversions_data[company_name].append(conversion_record)
    
    # Save to file using atomic write
    temp_dir = os.path.dirname(os.path.abspath(TICKER_CONVERSIONS_FILE)) or '.'
    temp_fd, temp_path = tempfile.mkstemp(dir=temp_dir, suffix='.json', prefix='.ticker_conversions_temp_')
    
    try:
        # Write to temporary file
        with os.fdopen(temp_fd, 'w') as f:
            json.dump(conversions_data, f, indent=2)
        
        # Atomically replace the original file
        if os.name == 'nt':  # Windows
            if os.path.exists(TICKER_CONVERSIONS_FILE):
                os.remove(TICKER_CONVERSIONS_FILE)
            shutil.move(temp_path, TICKER_CONVERSIONS_FILE)
        else:  # Unix-like systems
            os.replace(temp_path, TICKER_CONVERSIONS_FILE)
        return True
    except Exception as e:
        # If anything goes wrong, try to clean up temp file
        try:
            os.remove(temp_path)
        except:
            pass
        print(f"Error saving ticker conversion: {e}")
        return False


def query_peers_from_ai(ticker, company_name):
    """Query AI model to find the top 10 most comparable companies (not limited to scores.json).
    
    Args:
        ticker: Ticker symbol (uppercase)
        company_name: Company name
        
    Returns:
        tuple: (list of 10 company names ranked from most comparable to least, elapsed_time, token_usage) or (None, None, None) if error
    """
    # Create prompt asking for top 10 comparable companies
    prompt = f"""You are analyzing companies to find the 10 most comparable companies to {company_name}.

Your task is to find the 10 MOST comparable companies to {company_name}.

Consider factors such as:
1. Industry and market segment similarity (MUST be in same or very similar industry)
2. Business model similarity
3. Product/service similarity
4. Market overlap and customer base similarity
5. Competitive dynamics (direct competitors)
6. Company size and scale (if relevant)

Return ONLY a semicolon-separated list of exactly 10 FULL company names, starting with the most comparable company first.
CRITICAL: Use semicolons (;) to separate company names, NOT commas, because company names often contain commas (e.g., "Nike, Inc.").
Each company name must be complete (e.g., "Microsoft Corporation", "Alphabet Inc.", "Meta Platforms Inc.", "Nike, Inc.").
DO NOT return partial names, suffixes alone (like "Inc" or "Corporation"), or abbreviations.
Each name should be the full legal company name or commonly used full name.
Do not include explanations, ticker symbols, ranking numbers, or any other text - just the 10 complete company names separated by semicolons in order from most to least comparable.

Example format: "Microsoft Corporation; Alphabet Inc.; Meta Platforms Inc.; Amazon.com Inc.; NVIDIA Corporation; Intel Corporation; Advanced Micro Devices Inc.; Salesforce Inc.; Oracle Corporation; Adobe Inc."

Return exactly 10 complete company names in ranked order, separated by semicolons, nothing else."""

    try:
        # Use configured API client (Grok or OpenRouter)
        grok = get_api_client()
        model = get_model_for_ticker(ticker)
        
        # Track time
        start_time = time.time()
        response, token_usage = grok.simple_query_with_tokens(prompt, model=model)
        elapsed_time = time.time() - start_time
        
        # Log all responses
        log_ai_response(ticker, None, "peer_lookup", response, model)
        
        # Parse response to extract ranked company names
        response_clean = response.strip()
        
        # Try to extract company names from the response
        # Handle various formats: semicolon-separated (preferred), comma-separated (fallback), numbered lists, etc.
        company_names = []
        
        # First, try splitting by semicolon (preferred separator to avoid issues with commas in company names)
        if ';' in response_clean:
            for item in response_clean.split(';'):
                # Remove any leading numbers, dots, dashes, etc.
                item_clean = item.strip()
                # Remove common prefixes like "1.", "1)", "-", etc.
                while item_clean and (item_clean[0].isdigit() or item_clean[0] in '.)- '):
                    item_clean = item_clean[1:].strip()
                
                # Clean up the company name
                if item_clean:
                    # Remove trailing punctuation (but keep commas that are part of the name)
                    item_clean = item_clean.rstrip('.;:()[]{}')
                    if item_clean:
                        company_names.append(item_clean.strip())
        else:
            # Fallback: try splitting by comma (but this may break on names like "Nike, Inc.")
            # Use a smarter approach: split on ", " (comma followed by space) which is more likely to be a separator
            # than a comma within a name
            import re
            # Split on ", " but be careful - we'll try to reconstruct names that might have been split incorrectly
            parts = re.split(r',\s+', response_clean)
            current_name = ""
            for part in parts:
                part = part.strip()
                # Remove leading numbers, dots, dashes, etc.
                while part and (part[0].isdigit() or part[0] in '.)- '):
                    part = part[1:].strip()
                
                if not part:
                    continue
                
                # Check if this part looks like the start of a new company name (starts with capital, or is very short)
                # vs continuation of previous name (likely a suffix like "Inc." or "Corporation")
                if current_name:
                    # Check if this looks like a suffix
                    part_lower = part.lower().rstrip('.')
                    common_suffixes = ['inc', 'corp', 'corporation', 'llc', 'ltd', 'limited', 'co', 'company', 'plc', 'sa', 'ag', 'nv', 'bv', 'gmbh', 'se', 'usa']
                    if part_lower in common_suffixes or (len(part) <= 5 and part[0].isupper()):
                        # Likely a suffix, append to current name
                        current_name += ", " + part.rstrip('.,;:()[]{}')
                    else:
                        # Likely a new company name
                        # Save previous name
                        prev_clean = current_name.rstrip('.,;:()[]{}')
                        if prev_clean:
                            company_names.append(prev_clean.strip())
                        # Start new name
                        current_name = part
                else:
                    current_name = part
            
            # Don't forget the last name
            if current_name:
                current_name = current_name.rstrip('.,;:()[]{}')
                if current_name:
                    company_names.append(current_name.strip())
        
        # If we didn't get enough names, try parsing line by line
        if len(company_names) < 10:
            lines = response_clean.split('\n')
            for line in lines:
                line_clean = line.strip()
                # Skip empty lines
                if not line_clean:
                    continue
                # Try to extract company name from line
                # Remove leading numbers, dots, dashes
                while line_clean and (line_clean[0].isdigit() or line_clean[0] in '.)- '):
                    line_clean = line_clean[1:].strip()
                # Remove trailing punctuation
                line_clean = line_clean.rstrip('.,;:()[]{}')
                if line_clean and line_clean not in company_names:
                    company_names.append(line_clean)
                    if len(company_names) >= 10:
                        break
        
        # Filter out invalid company names
        invalid_suffixes = {'inc', 'corp', 'corporation', 'llc', 'ltd', 'limited', 'co', 'company', 'plc', 'sa', 'ag', 'nv', 'bv', 'gmbh'}
        valid_company_names = []
        for name in company_names:
            name_lower = name.lower().strip()
            # Skip if too short (less than 3 characters)
            if len(name_lower) < 3:
                continue
            # Skip if it's just a legal suffix
            if name_lower in invalid_suffixes:
                continue
            # Skip if it's just a single word that's a common suffix
            words = name_lower.split()
            if len(words) == 1 and words[0] in invalid_suffixes:
                continue
            # Skip if it's just punctuation or numbers
            if not any(c.isalpha() for c in name):
                continue
            valid_company_names.append(name)
        
        # Limit to top 10
        valid_company_names = valid_company_names[:10]
        
        # Save AI response to JSON
        if valid_company_names:
            save_peer_response(
                ticker=ticker,
                company_name=company_name,
                prompt=prompt,
                raw_response=response,
                parsed_company_names=valid_company_names,
                model=model,
                elapsed_time=elapsed_time,
                token_usage=token_usage
            )
        
        return (valid_company_names, elapsed_time, token_usage) if valid_company_names else (None, None, None)
        
    except Exception as e:
        print(f"Error querying AI for peers: {e}")
        return (None, None, None)


def convert_company_name_to_ticker(company_name, return_cost=False):
    """Convert a company name to a ticker symbol using AI.
    If the company is public, returns the actual ticker.
    If the company is private, generates a ticker and adds it to ticker definitions.
    
    Args:
        company_name: Company name
        return_cost: If True, also return cost information when AI is used
        
    Returns:
        tuple: (ticker_symbol, is_public) or (ticker_symbol, is_public, cost_info) if return_cost=True
               where is_public is True if it's a real public company ticker, False if generated
               and cost_info is a dict with 'cost', 'tokens', 'token_usage' if AI was used, None otherwise
    """
    # First check if we already have this company in our lookup
    ticker_lookup = load_ticker_lookup()
    company_lower = company_name.lower()
    
    # Try exact match (case insensitive)
    for ticker, name in ticker_lookup.items():
        if name.lower() == company_lower:
            # Record conversion from lookup
            save_ticker_conversion(company_name, ticker, True, "exact_match")
            if return_cost:
                return (ticker, True, None)
            return (ticker, True)
    
    # Try partial match - match on significant words (excluding common corporate suffixes)
    # Common corporate suffixes that should not count as significant matches
    corporate_suffixes = {
        'inc', 'incorporated', 'corp', 'corporation', 'ltd', 'limited', 'llc', 
        'company', 'co', 'plc', 'ag', 'sa', 'se', 'nv', 'spa', 'srl',
        'common', 'stock', 'shares', 'holdings', 'group', 'industries',
        'technologies', 'technology', 'systems', 'solutions', 'services',
        'international', 'global', 'worldwide', 'usa', 'us', 'america'
    }
    
    # Extract meaningful words (excluding suffixes and short words)
    company_words = set(
        word.strip('.,;:()[]{}') 
        for word in company_lower.split() 
        if len(word) > 2 and word.strip('.,;:()[]{}') not in corporate_suffixes
    )
    
    for ticker, name in ticker_lookup.items():
        name_lower = name.lower()
        name_words = set(
            word.strip('.,;:()[]{}') 
            for word in name_lower.split() 
            if len(word) > 2 and word.strip('.,;:()[]{}') not in corporate_suffixes
        )
        
        # Require at least 2 meaningful words to match (no single long word shortcut)
        common_words = company_words.intersection(name_words)
        if len(common_words) >= 2:
            # Record conversion from lookup
            save_ticker_conversion(company_name, ticker, True, "partial_match")
            if return_cost:
                return (ticker, True, None)
            return (ticker, True)
    
    # Not found in lookup, use AI to find ticker
    prompt = f"""Given the company name "{company_name}", determine if it is a publicly traded company.

If it is a publicly traded company, return ONLY the ticker symbol (1-5 uppercase letters, e.g., "AAPL", "MSFT", "GOOGL").
If it is a private company or not publicly traded, return ONLY the word "PRIVATE".

Do not include any explanations, company names, or other text - just the ticker symbol or the word "PRIVATE"."""

    try:
        grok = get_api_client()
        model = get_model_for_ticker("AAPL")  # Use default model
        
        response, token_usage = grok.simple_query_with_tokens(prompt, model=model)
        # Log all responses
        log_ai_response(None, company_name, "ticker_lookup", response, model)
        
        # response is the full raw AI response - save this, not response_clean
        response_clean = response.strip().upper()  # Only used for parsing, not saved
        
        # Check if response is "PRIVATE"
        if "PRIVATE" in response_clean:
            # Company is private - do not create fake ticker
            # Record that no ticker was found
            save_ticker_conversion(company_name, None, False, "ai_private_no_ticker", ai_response=response, prompt=prompt, token_usage=token_usage)
            
            # Calculate cost if requested
            cost_info = None
            if return_cost and token_usage:
                model_used = get_model_for_ticker("AAPL")
                cost = calculate_token_cost(token_usage.get('total_tokens', 0), model=model_used, token_usage=token_usage)
                cost_info = {
                    'cost': cost,
                    'tokens': token_usage.get('total_tokens', 0),
                    'token_usage': token_usage
                }
            
            # Return None to indicate no ticker found
            if return_cost:
                return (None, False, cost_info)
            return (None, False)
        else:
            # Extract ticker from response
            # Look for a valid ticker format (1-5 uppercase letters)
            ticker_match = re.search(r'\b([A-Z]{1,5})\b', response_clean)
            if ticker_match:
                ticker = ticker_match.group(1)
                # Verify it's a valid ticker by checking if it exists in our lookup
                is_public = ticker in ticker_lookup
                
                # Record conversion (but don't add to definitions for unknown tickers)
                save_ticker_conversion(company_name, ticker, is_public, "ai_public", ai_response=response, prompt=prompt, token_usage=token_usage)
                
                # Calculate cost if requested
                cost_info = None
                if return_cost and token_usage:
                    model_used = get_model_for_ticker("AAPL")
                    cost = calculate_token_cost(token_usage.get('total_tokens', 0), model=model_used, token_usage=token_usage)
                    cost_info = {
                        'cost': cost,
                        'tokens': token_usage.get('total_tokens', 0),
                        'token_usage': token_usage
                    }
                
                if return_cost:
                    return (ticker, is_public, cost_info)
                return (ticker, is_public)
            else:
                # Couldn't parse ticker, generate one
                words = company_name.split()
                ticker = ""
                for word in words:
                    if word and word[0].isalpha():
                        ticker += word[0].upper()
                        if len(ticker) >= 5:
                            break
                while len(ticker) < 3:
                    ticker += "X"
                ticker = ticker[:5]
                
                # Make sure it's unique
                original_ticker = ticker
                counter = 1
                while ticker in ticker_lookup:
                    ticker = (original_ticker[:4] + str(counter))[:5]
                    counter += 1
                    if counter > 9:
                        ticker = company_name.replace(" ", "").upper()[:5]
                        break
                
                add_ticker_definition(ticker, company_name)
                
                # Record conversion
                save_ticker_conversion(company_name, ticker, False, "generated_fallback", ai_response=response, prompt=prompt, token_usage=token_usage)
                
                # Calculate cost if requested
                cost_info = None
                if return_cost and token_usage:
                    model_used = get_model_for_ticker("AAPL")
                    cost = calculate_token_cost(token_usage.get('total_tokens', 0), model=model_used, token_usage=token_usage)
                    cost_info = {
                        'cost': cost,
                        'tokens': token_usage.get('total_tokens', 0),
                        'token_usage': token_usage
                    }
                
                if return_cost:
                    return (ticker, False, cost_info)
                return (ticker, False)
        
    except Exception as e:
        print(f"Error converting company name to ticker: {e}")
        # Fallback: generate a ticker
        words = company_name.split()
        ticker = ""
        for word in words:
            if word and word[0].isalpha():
                ticker += word[0].upper()
                if len(ticker) >= 5:
                    break
        while len(ticker) < 3:
            ticker += "X"
        ticker = ticker[:5]
        
        # Make sure it's unique
        original_ticker = ticker
        counter = 1
        while ticker in ticker_lookup:
            ticker = (original_ticker[:4] + str(counter))[:5]
            counter += 1
            if counter > 9:
                ticker = company_name.replace(" ", "").upper()[:5]
                break
        
        add_ticker_definition(ticker, company_name)
        
        # Record conversion
        save_ticker_conversion(company_name, ticker, False, "exception_fallback")
        
        if return_cost:
            return (ticker, False, None)
        return (ticker, False)


def display_peer_scores_comparison(target_ticker, peer_data_list):
    """Display total scores comparison between target ticker and peer companies.
    
    Args:
        target_ticker: Target ticker symbol (uppercase)
        peer_data_list: List of dicts with keys: 'ticker', 'name', 'has_score', 'total' (optional), 'percentage' (optional), 'percentile' (optional)
    """
    scores_data = load_scores()
    ticker_lookup = load_ticker_lookup()
    
    # Get target company data
    target_company_data = None
    for company_key in scores_data.get("companies", {}).keys():
        if company_key.upper() == target_ticker:
            target_company_data = scores_data["companies"][company_key]
            break
    
    target_name = ticker_lookup.get(target_ticker, target_ticker)
    target_total = None
    target_percentage = None
    target_percentile = None
    
    if target_company_data:
        target_total = calculate_total_score(target_company_data)
        max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS) * 10
        target_percentage = (target_total / max_score) * 100
        all_totals = get_all_total_scores()
        target_percentile = calculate_percentile_rank(target_total, all_totals) if all_totals and len(all_totals) > 1 else None
    
    # Build list of all items to display (target + peers)
    all_items = []
    
    # Target item
    target_display_name = get_current_display_name(target_ticker, target_company_data.get('company_name') if target_company_data else None)
    all_items.append({
        'ticker': target_ticker,
        'name': target_display_name,
        'has_score': target_company_data is not None,
        'total': target_total,
        'percentage': target_percentage,
        'percentile': target_percentile
    })
    
    # Peer items
    for peer in peer_data_list:
        peer_ticker = peer['ticker']
        # Try to find stored name for peer
        peer_db_name = None
        for company_key in scores_data.get("companies", {}).keys():
            if company_key.upper() == peer_ticker:
                peer_db_name = scores_data["companies"][company_key].get('company_name')
                break
        
        peer_display_name = get_current_display_name(peer_ticker, peer_db_name or peer.get('name'))
        peer_copy = peer.copy()
        peer_copy['name'] = peer_display_name
        all_items.append(peer_copy)
    
    # Calculate median score of peers that have scores (excluding target ticker)
    peer_scores = [item['total'] for item in all_items if item['ticker'] != target_ticker and item.get('has_score') and item.get('total') is not None]
    median_score = None
    median_percentage = None
    if peer_scores:
        import statistics
        sorted_peer_scores = sorted(peer_scores)
        median_score = statistics.median(sorted_peer_scores)
        max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS) * 10
        median_percentage = (median_score / max_score) * 100
    
    # Sort by total score (descending), with items without scores at the end
    all_items.sort(key=lambda x: (x.get('total') is not None, x.get('total') or 0), reverse=True)
    
    # Display comparison table
    # Column widths: Rank=6, Ticker=8, Company Name=40, Total Score=15, Percentile=12
    # Plus 4 spaces between columns = 85 total
    table_width = 85
    print("\n" + "=" * table_width)
    print(f"Total Score Comparison: {target_ticker} vs Top 10 Peers")
    print("=" * table_width)
    # Headers: right-align Total Score and Percentile to match right-aligned numeric data
    print(f"{'Rank':<6} {'Ticker':<8} {'Company Name':<40} {'Total Score':>15} {'Percentile':>12}")
    print("-" * table_width)
    
    for rank, item in enumerate(all_items, 1):
        ticker = item['ticker']
        name = item['name']
        has_score = item.get('has_score', False)
        percentage = item.get('percentage')
        percentile = item.get('percentile')
        
        # Highlight target ticker
        if ticker == target_ticker:
            ticker_display = f"*{ticker}*"
        else:
            ticker_display = ticker
        
        # Truncate company name if too long
        if len(name) > 40:
            name_display = (name[:37] + "...")[:40]
        else:
            name_display = name
        
        if has_score and percentage is not None:
            percentage_str = f"{int(percentage)}%"
            percentile_str = f"{percentile}th" if percentile is not None else "N/A"
        else:
            percentage_str = "Not scored"
            percentile_str = "N/A"
        
        print(f"{rank:<6} {ticker_display:<8} {name_display:<40} {percentage_str:>15} {percentile_str:>12}")
    
    print("-" * table_width)
    # Display median of peers
    if median_percentage is not None:
        print(f"{'Median (Peers)':<54} {int(median_percentage):>15}%")
    print("=" * table_width)
    print("* Target ticker")


def get_peers_for_ticker(ticker, force_redo=False):
    """Get the top 10 most comparable peers for a ticker using AI.
    Displays scores comparison between target and top 10 peers.
    For peers without scores, asks user if they want to score them.
    
    Args:
        ticker: Ticker symbol (uppercase)
        force_redo: If True, bypass cache and force a new AI query
        
    Returns:
        list: List of 10 ticker symbols ranked from most comparable to least, or None if error
    """
    ticker_upper = ticker.strip().upper()
    
    # Validate ticker
    ticker_lookup = load_ticker_lookup()
    if ticker_upper not in ticker_lookup:
        print(f"Error: '{ticker_upper}' is not a valid ticker symbol.")
        return None
    
    # Check if ticker exists in scores.json
    scores_data = load_scores()
    companies = scores_data.get("companies", {})
    ticker_found = False
    for company_key in companies.keys():
        if company_key.upper() == ticker_upper:
            ticker_found = True
            break
    
    if not ticker_found:
        print(f"Error: '{ticker_upper}' not found in scores.json. Please score it first.")
        return None
    
    company_name = ticker_lookup[ticker_upper]
    
    # Check if peers are already cached (unless force_redo is True)
    if not force_redo:
        peers_data = load_peers()
        if ticker_upper in peers_data:
            cached_peer_tickers = peers_data[ticker_upper]
            # Limit to 10 for consistency
            cached_peer_tickers = cached_peer_tickers[:10]
            if cached_peer_tickers:
                display_name = get_current_display_name(ticker_upper, company_name)
                print(f"\n{display_name} - Found cached peers:")
                print(f"  {len(cached_peer_tickers)} peer(s): {', '.join(cached_peer_tickers)}")
                
                # Convert cached tickers to peer_data_list format for display
                peer_data_list = []
                scores_data = load_scores()
                ticker_lookup = load_ticker_lookup()
                
                for peer_ticker in cached_peer_tickers:
                    # Check if this peer has scores
                    has_score = False
                    total = None
                    percentage = None
                    percentile = None
                    
                    for company_key in scores_data.get("companies", {}).keys():
                        if company_key.upper() == peer_ticker:
                            has_score = True
                            company_data = scores_data["companies"][company_key]
                            total = calculate_total_score(company_data)
                            max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS) * 10
                            percentage = (total / max_score) * 100
                            all_totals = get_all_total_scores()
                            percentile = calculate_percentile_rank(total, all_totals) if all_totals and len(all_totals) > 1 else None
                            break
                    
                    peer_display_name = ticker_lookup.get(peer_ticker, peer_ticker)
                    
                    peer_data_list.append({
                        'ticker': peer_ticker,
                        'name': peer_display_name,
                        'has_score': has_score,
                        'total': total,
                        'percentage': percentage,
                        'percentile': percentile
                    })
                
                # Display scores comparison
                display_peer_scores_comparison(ticker_upper, peer_data_list)
                
                return cached_peer_tickers
    
    # Not cached or force_redo is True, query AI for peers (returns company names)
    display_name = get_current_display_name(ticker_upper, company_name)
    if force_redo:
        print(f"\nForcing new peer calculation for {display_name} (bypassing cache)...")
    else:
        print(f"\nQuerying AI to find the top 10 most comparable companies to {display_name}...")
    print("This may take a moment...")
    ranked_peer_names, elapsed_time, token_usage = query_peers_from_ai(ticker_upper, company_name)
    
    if not ranked_peer_names:
        print(f"Error: Could not find peers for {ticker_upper}")
        return None
    
    # Limit to top 10
    ranked_peer_names = ranked_peer_names[:10]
    print(f"Found {len(ranked_peer_names)} peer(s)")
    
    # Calculate cost for peer query
    model = get_model_for_ticker(ticker_upper)
    peer_total_tokens = token_usage.get('total_tokens', 0) if token_usage else 0
    peer_cost = calculate_token_cost(peer_total_tokens, model=model, token_usage=token_usage) if token_usage else 0.0
    peer_cost_cents = peer_cost * 100
    
    # Track ticker conversion costs
    ticker_conversion_total_tokens = 0
    ticker_conversion_cost = 0.0
    ticker_conversion_token_usage_combined = {
        'input_tokens': 0,
        'output_tokens': 0,
        'cached_tokens': 0,
        'thinking_tokens': 0,
        'total_tokens': 0
    }
    
    # Convert company names to tickers and check which have scores
    # Limit to top 10 peers
    ranked_peer_names = ranked_peer_names[:10]
    
    peer_data_list = []
    peer_tickers = []
    seen_tickers = set()  # Track seen tickers to avoid duplicates
    scores_data = load_scores()  # Reload to get latest scores
    
    # Additional validation for invalid company names
    invalid_suffixes = {'inc', 'corp', 'corporation', 'llc', 'ltd', 'limited', 'co', 'company', 'plc', 'sa', 'ag', 'nv', 'bv', 'gmbh'}
    
    for peer_name in ranked_peer_names:
        # Skip if empty
        if not peer_name or not peer_name.strip():
            continue
        
        # Additional validation: skip invalid names
        peer_name_clean = peer_name.strip()
        peer_name_lower = peer_name_clean.lower()
        
        # Skip if too short
        if len(peer_name_lower) < 3:
            continue
        
        # Skip if it's just a legal suffix
        if peer_name_lower in invalid_suffixes:
            continue
        
        # Skip if it's just a single word that's a common suffix
        words = peer_name_lower.split()
        if len(words) == 1 and words[0] in invalid_suffixes:
            continue
        
        # Skip if it's just punctuation or numbers
        if not any(c.isalpha() for c in peer_name_clean):
            continue
            
        # Convert company name to ticker (with cost tracking)
        result = convert_company_name_to_ticker(peer_name_clean, return_cost=True)
        if len(result) == 3:
            peer_ticker, is_public, cost_info = result
            # Accumulate ticker conversion costs
            if cost_info:
                ticker_conversion_cost += cost_info['cost']
                ticker_conversion_total_tokens += cost_info['tokens']
                # Accumulate token usage details
                tu = cost_info.get('token_usage', {})
                ticker_conversion_token_usage_combined['input_tokens'] += tu.get('input_tokens', tu.get('prompt_tokens', 0) or 0)
                ticker_conversion_token_usage_combined['output_tokens'] += tu.get('output_tokens', tu.get('completion_tokens', 0) or 0)
                cached = tu.get('cached_tokens', 0) or tu.get('cached_input_tokens', 0) or tu.get('cached_cache_hit_tokens', 0) or 0
                ticker_conversion_token_usage_combined['cached_tokens'] += cached
                ticker_conversion_token_usage_combined['thinking_tokens'] += tu.get('thinking_tokens', 0) or 0
                ticker_conversion_token_usage_combined['total_tokens'] += tu.get('total_tokens', 0) or 0
        else:
            peer_ticker, is_public = result
        
        # Skip if no ticker was found (company is private or not publicly traded)
        if peer_ticker is None:
            print(f"Skipping peer '{peer_name_clean}' - no public ticker found")
            continue

        # Skip if we've already seen this ticker (duplicate)
        if peer_ticker in seen_tickers:
            continue
        
        # Skip if it's the same as the target ticker
        if peer_ticker == ticker_upper:
            continue
        
        seen_tickers.add(peer_ticker)
        peer_tickers.append(peer_ticker)
        
        # Check if this peer has scores
        has_score = False
        total = None
        percentage = None
        percentile = None
        
        for company_key in scores_data.get("companies", {}).keys():
            if company_key.upper() == peer_ticker:
                has_score = True
                company_data = scores_data["companies"][company_key]
                total = calculate_total_score(company_data)
                max_score = sum(SCORE_WEIGHTS.get(key, 1.0) for key in SCORE_DEFINITIONS) * 10
                percentage = (total / max_score) * 100
                all_totals = get_all_total_scores()
                percentile = calculate_percentile_rank(total, all_totals) if all_totals and len(all_totals) > 1 else None
                break
        
        # Get company name from lookup (may have been updated)
        ticker_lookup = load_ticker_lookup()  # Reload to get latest definitions
        peer_display_name = ticker_lookup.get(peer_ticker, peer_name)
        
        peer_data_list.append({
            'ticker': peer_ticker,
            'name': peer_display_name,
            'has_score': has_score,
            'total': total,
            'percentage': percentage,
            'percentile': percentile
        })
    
    # Check if we have fewer than 10 peers due to filtering
    if len(peer_data_list) < 10:
        print(f"\nNote: Found {len(peer_data_list)} valid peer(s) after filtering (some may have been invalid or duplicates).")
    
    # If no valid peers found, still save empty list to cache
    if not peer_tickers:
        print(f"\nWarning: No valid peers found for {ticker_upper} after processing.")
    
    # Save to cache immediately after calculating peers (before user interaction)
    # This ensures peers are cached even if user interaction fails or is interrupted
    peers_data = load_peers()
    peers_data[ticker_upper] = peer_tickers
    if save_peers(peers_data):
        if force_redo:
            print(f"\n✓ Peers recalculated and saved to {PEERS_FILE}")
        else:
            print(f"\n✓ Peers saved to {PEERS_FILE}")
    else:
        print(f"\n✗ Error: Failed to save peers to {PEERS_FILE}")
    
    # Display timing and cost information (peer query + ticker conversions)
    print(f"\nTime taken: {elapsed_time:.2f}s")
    
    # Display peer query tokens and cost
    if token_usage:
        peer_input_tokens = token_usage.get('input_tokens') if 'input_tokens' in token_usage else token_usage.get('prompt_tokens', 0)
        peer_output_tokens = token_usage.get('output_tokens') if 'output_tokens' in token_usage else token_usage.get('completion_tokens', 0)
        peer_cached_tokens = (token_usage.get('cached_tokens') if 'cached_tokens' in token_usage else
                           token_usage.get('cached_input_tokens') if 'cached_input_tokens' in token_usage else
                           token_usage.get('prompt_cache_hit_tokens', 0))
        peer_thinking_tokens = token_usage.get('thinking_tokens', 0)
        
        if peer_thinking_tokens > 0:
            print(f"Peer Query - Tokens: {peer_total_tokens:,} (input={peer_input_tokens:,}, output={peer_output_tokens:,} includes {peer_thinking_tokens:,} thinking, cached={peer_cached_tokens:,})")
        else:
            print(f"Peer Query - Tokens: {peer_total_tokens:,} (input={peer_input_tokens:,}, output={peer_output_tokens:,}, cached={peer_cached_tokens:,})")
    else:
        print(f"Peer Query - Tokens: {peer_total_tokens:,}")
    print(f"Peer Query - Cost: {peer_cost_cents:.4f} cents")
    
    # Display ticker conversion tokens and cost (if any)
    if ticker_conversion_total_tokens > 0:
        ticker_conversion_cost_cents = ticker_conversion_cost * 100
        tu_combined = ticker_conversion_token_usage_combined
        if tu_combined.get('thinking_tokens', 0) > 0:
            print(f"Ticker Conversions - Tokens: {ticker_conversion_total_tokens:,} (input={tu_combined['input_tokens']:,}, output={tu_combined['output_tokens']:,} includes {tu_combined['thinking_tokens']:,} thinking, cached={tu_combined['cached_tokens']:,})")
        else:
            print(f"Ticker Conversions - Tokens: {ticker_conversion_total_tokens:,} (input={tu_combined['input_tokens']:,}, output={tu_combined['output_tokens']:,}, cached={tu_combined['cached_tokens']:,})")
        print(f"Ticker Conversions - Cost: {ticker_conversion_cost_cents:.4f} cents")
        
        # Display total
        total_cost_cents = peer_cost_cents + ticker_conversion_cost_cents
        total_tokens = peer_total_tokens + ticker_conversion_total_tokens
        print(f"\nTotal - Tokens: {total_tokens:,}")
        print(f"Total - Cost: {total_cost_cents:.4f} cents")
    
    # Display scores comparison (shows all peers, with scores for those that have them)
    if peer_data_list:
        display_peer_scores_comparison(ticker_upper, peer_data_list)
    else:
        print(f"\nNo peers to display for {ticker_upper}.")
    
    return peer_tickers


def handle_peer_command(command_input):
    """Handle the peer command - find peers for a ticker.
    
    Args:
        command_input: Command input after 'peer' keyword (ticker symbol)
    """
    command_input = command_input.strip()
    
    if not command_input:
        print("Usage: peer TICKER")
        print("Example: peer AAPL")
        return
    
    ticker = command_input.upper()
    get_peers_for_ticker(ticker)


def handle_redopeer_command(command_input):
    """Handle the redopeer command - force a new peer calculation, bypassing cache.
    
    Args:
        command_input: Command input after 'redopeer' keyword (ticker symbol)
    """
    command_input = command_input.strip()
    
    if not command_input:
        print("Usage: redopeer TICKER")
        print("Example: redopeer AAPL")
        print("This will force a new AI query for peers, bypassing any cached results.")
        return
    
    ticker = command_input.upper()
    get_peers_for_ticker(ticker, force_redo=True)


def handle_fillpeer_command(command_input):
    """Handle the fillpeer command - score all unscored peers for a ticker.
    
    Args:
        command_input: Command input after 'fillpeer' keyword (ticker symbol)
    """
    command_input = command_input.strip()
    
    if not command_input:
        print("Usage: fillpeer TICKER")
        print("Example: fillpeer GOOGL")
        print("This will score all peers of GOOGL that don't already have scores.")
        return
    
    ticker = command_input.upper()
    
    # Load peers and scores
    peers_data = load_peers()
    scores_data = load_scores()
    scored_tickers = set(scores_data.get("companies", {}).keys())
    
    # Check if ticker has peers
    if ticker not in peers_data:
        print(f"No peers found for {ticker}. Run 'peer {ticker}' first to find peers.")
        return
    
    peer_tickers = peers_data[ticker]
    
    # Find unscored peers
    unscored_peers = [p for p in peer_tickers if p not in scored_tickers]
    
    if not unscored_peers:
        print(f"All {len(peer_tickers)} peers of {ticker} already have scores.")
        return
    
    print(f"\n{ticker} has {len(peer_tickers)} peers, {len(unscored_peers)} need scoring:")
    for p in unscored_peers:
        ticker_lookup = load_ticker_lookup()
        name = ticker_lookup.get(p, p)
        print(f"  - {p}: {name}")
    print()
    
    # Score the unscored peers
    score_multiple_tickers(' '.join(unscored_peers))


def handle_database_command():
    """Handle the 'database' command - list and switch between available SQLite databases."""
    global SCORES_DB, db
    data_dir = os.path.join(PROJECT_ROOT, "data")
    web_app_dir = os.path.join(PROJECT_ROOT, "web_app")
    
    db_paths = []
    
    # Scan data directory
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            if f.endswith('.db'):
                db_paths.append(os.path.join(data_dir, f))
                
    # Scan web_app directory
    if os.path.exists(web_app_dir):
        for f in os.listdir(web_app_dir):
            if f.endswith('.db'):
                db_paths.append(os.path.join(web_app_dir, f))
    
    if not db_paths:
        print(f"No database files found.")
        return

    db_paths.sort()
    print("\nAvailable Databases:")
    print("-" * 60)
    for i, path in enumerate(db_paths, 1):
        db_file = os.path.basename(path)
        location = " (web_app/)" if "web_app" in path else " (data/)"
        current_marker = " [current]" if path == SCORES_DB else ""
        print(f"  {i}. {db_file:<20} {location:<10}{current_marker}")
    print("-" * 60)
    
    try:
        choice = input("Enter the number of the database to use (or 'c' to cancel): ").strip()
        if choice.lower() == 'c':
            return
            
        idx = int(choice) - 1
        if 0 <= idx < len(db_paths):
            new_path = db_paths[idx]
            new_db_file = os.path.basename(new_path)
            
            SCORES_DB = new_path
            db = DBManager(SCORES_DB)
            save_db_path(new_path)
            print(f"Switched to database: {new_db_file} (this setting is now persistent)")
        else:
            print("Invalid selection.")
    except ValueError:
        print("Invalid input. Please enter a number.")
    except Exception as e:
        print(f"Error switching database: {e}")


def main():
    """Main function to run the moat scorer."""
    global GLOBAL_SHOW_NAMES
    print("Company Competitive Moat Scorer")
    print("=" * 40)
    print("Commands:")
    print("  Enter ticker symbol (e.g., AAPL) or multiple tickers (e.g., AAPL MSFT GOOGL) to score")
    print("  Type 'view' to see total scores")
    print("  Type 'viewname' to toggle showing company names instead of tickers")
    print("  Type 'rank' to see rankings by metric")
    print("  Type 'all TICKER' to see all historical scores for a company")
    print("  Type 'equal X' to see all ticker-metric pairs with score = X (e.g., equal 0 or equal NULL)")
    print("  Type 'compare TICKER' to compare the last 2 entries from different models")
    print("  Type 'delete' to remove a company's scores")
    print("  Type 'fill' to score companies with missing scores")
    print("  Type 'migrate' to fix duplicate entries")
    print("  Type 'redo TICKER1 TICKER2 ...' to rescore ticker(s) (forces new scoring even if scores exist)")
    print("  Type 'upgrade' to rescore all tickers not using the current model")
    print("  Type 'define TICKER = Company Name' to add custom ticker definition")
    print("  Type 'define -r TICKER' to remove a custom ticker definition")
    print("  Type 'define -l' to list all custom ticker definitions")
    print("  Type 'redefine NEW_TICKER = OLD_TICKER' to rename a ticker definition")
    print("  Type 'correl TICKER1 TICKER2' to show correlation between two companies' scores")
    print("  Type 'peer TICKER' to find peers and competitors for a ticker")
    print("  Type 'redopeer TICKER' to force a new peer calculation (bypasses cache)")
    print("  Type 'fillpeer TICKER' to score all unscored peers of a ticker")
    print("  Type 'database' to list and switch between available databases")
    print("  Type 'clear' to clear the terminal")
    print("  Type 'exit' to stop")
    print()
    
    while True:
        try:
            user_input = input("Enter ticker or company name (or 'view'/'viewname'/'rank'/'all'/'delete'/'fill'/'redo'/'upgrade'/'define'/'redefine'/'correl'/'peer'/'redopeer'/'fillpeer'/'database'/'clear'/'exit'): ").strip()
            
            if user_input.lower() in ['exit', 'q']:
                print("Goodbye!")
                break
            elif user_input.lower() == 'clear':
                # Clear terminal - cross-platform
                os.system('cls' if os.name == 'nt' else 'clear')
                print()
            elif user_input.lower() == 'view':
                view_scores(show_names=GLOBAL_SHOW_NAMES)
                print()
            elif user_input.lower() == 'viewname':
                GLOBAL_SHOW_NAMES = not GLOBAL_SHOW_NAMES
                save_show_names(GLOBAL_SHOW_NAMES)
                status = "ON (showing names)" if GLOBAL_SHOW_NAMES else "OFF (showing tickers)"
                print(f"Company names toggle is now {status} (this setting is now persistent)")
                print()
            elif user_input.lower() == 'rank':
                handle_rank_command()
                print()
            elif user_input.lower() == 'all':
                print("Please provide a ticker symbol. Example: all GOOGL")
                print()
            elif user_input.lower().startswith('all '):
                ticker = user_input[4:].strip()
                handle_all_command(ticker)
                print()
            elif user_input.lower() == 'equal':
                print("Usage: equal <score_value>")
                print("Example: equal 0  or  equal NULL")
                print()
            elif user_input.lower().startswith('equal '):
                score_val = user_input[6:].strip()
                handle_equal_command(score_val)
                print()
            elif user_input.lower() == 'compare':
                print("Please provide a ticker symbol. Example: compare GOOGL")
                print()
            elif user_input.lower().startswith('compare '):
                ticker = user_input[8:].strip()
                handle_compare_command(ticker)
                print()
            elif user_input.lower() == 'delete':
                delete_input = input("Enter ticker or company name to delete: ").strip()
                if delete_input:
                    delete_company(delete_input)
                else:
                    print("Please enter a ticker symbol or company name to delete.")
                print()
            elif user_input.lower() == 'fill':
                fill_missing_barriers_scores()
                print()
            elif user_input.lower() == 'migrate':
                count = migrate_scores_to_uppercase()
                print(f"\nMigration complete! Now storing {count} unique companies.")
                print("All tickers have been converted to uppercase.")
                print()
            elif user_input.lower() == 'redo':
                print("Please provide ticker symbol(s). Example: redo AAPL or redo AAPL MSFT GOOGL")
                print()
            elif user_input.lower().startswith('redo '):
                tickers = user_input[5:].strip()  # Remove 'redo ' prefix
                handle_redo_command(tickers)
                print()
            elif user_input.lower() == 'upgrade':
                handle_upgrade_command()
                print()
            elif user_input.lower() == 'define':
                print("Usage:")
                print("  define SKH = SK Hynix          - Add/update a ticker definition")
                print("  define -r SKH                  - Remove a ticker definition")
                print("  define -l                      - List all custom ticker definitions")
                print()
            elif user_input.lower().startswith('define '):
                command_input = user_input[7:].strip()  # Remove 'define ' prefix
                handle_define_command(command_input)
                print()
            elif user_input.lower() == 'redefine':
                print("Usage:")
                print("  redefine NEW_TICKER = OLD_TICKER    - Rename a ticker definition")
                print()
            elif user_input.lower().startswith('redefine '):
                command_input = user_input[9:].strip()  # Remove 'redefine ' prefix
                handle_redefine_command(command_input)
                print()
            elif user_input.lower() == 'correl':
                print("Usage: correl TICKER1 TICKER2")
                print("Example: correl AAPL MSFT")
                print()
            elif user_input.lower().startswith('correl '):
                command_input = user_input[7:].strip()  # Remove 'correl ' prefix
                tickers = command_input.split()
                if len(tickers) == 2:
                    show_correlation(tickers[0], tickers[1])
                else:
                    print("Error: Please provide exactly 2 ticker symbols.")
                    print("Usage: correl TICKER1 TICKER2")
                    print("Example: correl AAPL MSFT")
                print()
            elif user_input.lower() == 'peer':
                print("Usage: peer TICKER")
                print("Example: peer AAPL")
                print()
            elif user_input.lower().startswith('peer '):
                command_input = user_input[5:].strip()  # Remove 'peer ' prefix
                handle_peer_command(command_input)
                print()
            elif user_input.lower().startswith('redopeer '):
                command_input = user_input[9:].strip()  # Remove 'redopeer ' prefix
                handle_redopeer_command(command_input)
                print()
            elif user_input.lower() == 'fillpeer':
                print("Usage: fillpeer TICKER")
                print("Example: fillpeer GOOGL")
                print("This will score all peers of GOOGL that don't already have scores.")
                print()
            elif user_input.lower().startswith('fillpeer '):
                command_input = user_input[9:].strip()  # Remove 'fillpeer ' prefix
                handle_fillpeer_command(command_input)
                print()
            elif user_input.lower() == 'database':
                handle_database_command()
                print()
            elif user_input:
                # Check if input contains multiple space-separated tickers
                tickers_raw = user_input.strip().split()
                # Deduplicate tickers while preserving order (case-insensitive)
                seen = set()
                tickers = []
                for ticker in tickers_raw:
                    ticker_upper = ticker.upper()
                    if ticker_upper not in seen:
                        seen.add(ticker_upper)
                        tickers.append(ticker)
                
                if len(tickers) < len(tickers_raw):
                    print(f"Note: Removed {len(tickers_raw) - len(tickers)} duplicate ticker(s).")
                
                if len(tickers) > 1:
                    # Multiple tickers - use the batch scoring function
                    # Reconstruct input string with deduplicated tickers
                    score_multiple_tickers(' '.join(tickers))
                    print()
                else:
                    # Single ticker - use the original function
                    get_company_moat_score(user_input)
                    print()
            else:
                print("Please enter a ticker symbol or company name.")
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()

