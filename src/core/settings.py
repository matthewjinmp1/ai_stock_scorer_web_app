import os

# Project root directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Data directories
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_DIR = os.path.join(DATA_DIR, 'db')
RAW_DIR = os.path.join(DATA_DIR, 'raw')

# Database paths
TOP_COMPANIES_DB = os.path.join(DB_DIR, 'top_companies.db')
TOP_SCORES_DB = os.path.join(DB_DIR, 'top_scores.db')
AI_RELEVANCE_DB = os.path.join(DB_DIR, 'ai_relevance_scores.db')
ROBOTICS_RELEVANCE_DB = os.path.join(DB_DIR, 'robotics_relevance_scores.db')
PEERS_DB = os.path.join(DB_DIR, 'peers.db')

# Trait (ambition/innovation) score ranking (JSON from rate_top_100_traits.py)
TRAIT_SCORES_JSON = os.path.join(DATA_DIR, 'trait_scores_confidence5_billion.json')

# Glassdoor JSON path (external from reorganization but linked for scripts)
GLASSDOOR_JSON = os.path.join(BASE_DIR, 'web_app_development/glassdoor/data/returns/jsons/glassdoor_2025_stock_returns.json')
