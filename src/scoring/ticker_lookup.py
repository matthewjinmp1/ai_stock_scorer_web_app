#!/usr/bin/env python3
"""
Ticker Lookup Tool
Allows users to input a company name and find the corresponding ticker symbol.
Searches both the main ticker database and custom ticker definitions.
"""

import os
import sys
import json

# Add parent directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Get project root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

# File paths
TICKER_FILE = os.path.join(PROJECT_ROOT, "data", "stock_tickers_clean.json")
TICKER_DEFINITIONS_FILE = os.path.join(PROJECT_ROOT, "data", "ticker_definitions.json")


def is_bond(ticker, name):
    """Check if a ticker/name represents a bond rather than a stock.
    
    Args:
        ticker: Ticker symbol
        name: Company name
        
    Returns:
        bool: True if this appears to be a bond
    """
    ticker_upper = ticker.upper()
    name_lower = name.lower()
    
    # Bonds typically have tickers with hyphens (e.g., "F-B", "F-C", "F-D")
    if '-' in ticker_upper:
        return True
    
    # Bonds have names containing "Notes due", "Bond", or percentage with dates
    bond_indicators = [
        'notes due',
        'bond',
        '% notes',
        '% note',
        'due ',
        ' maturing',
        ' maturity',
        ' preferred',
        ' preferred stock',
        ' series ',
        ' class ',
    ]
    
    for indicator in bond_indicators:
        if indicator in name_lower:
            return True
    
    return False


def load_ticker_database():
    """Load ticker to company name mappings from stock_tickers_clean.json.
    Filters out bonds - only includes stocks.
    
    Returns:
        dict: Mapping of ticker -> company name (stocks only)
    """
    ticker_map = {}
    
    if not os.path.exists(TICKER_FILE):
        return ticker_map
    
    try:
        with open(TICKER_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            for company in data.get('companies', []):
                ticker = company.get('ticker', '').strip().upper()
                name = company.get('name', '').strip()
                
                if ticker and name:
                    # Skip bonds
                    if not is_bond(ticker, name):
                        ticker_map[ticker] = name
    except Exception as e:
        print(f"Warning: Could not load ticker database: {e}")
    
    return ticker_map


def load_ticker_definitions():
    """Load custom ticker definitions from ticker_definitions.json.
    
    Returns:
        dict: Mapping of ticker -> company name
    """
    definitions = {}
    
    if not os.path.exists(TICKER_DEFINITIONS_FILE):
        return definitions
    
    try:
        with open(TICKER_DEFINITIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            definitions = data.get('definitions', {})
    except Exception as e:
        print(f"Warning: Could not load ticker definitions: {e}")
    
    return definitions


def create_reverse_lookup(ticker_map):
    """Create a reverse lookup mapping company name -> list of tickers.
    
    Args:
        ticker_map: dict mapping ticker -> company name
        
    Returns:
        dict: Mapping of company name (normalized) -> list of (ticker, original_name) tuples
    """
    reverse_map = {}
    
    for ticker, company_name in ticker_map.items():
        # Normalize company name for matching (lowercase, remove common suffixes)
        normalized = normalize_company_name(company_name)
        
        if normalized not in reverse_map:
            reverse_map[normalized] = []
        
        reverse_map[normalized].append((ticker, company_name))
    
    return reverse_map


def normalize_company_name(name):
    """Normalize company name for matching.
    
    Args:
        name: Company name string
        
    Returns:
        str: Normalized company name (lowercase, trimmed)
    """
    return name.lower().strip()


def extract_company_keywords(name):
    """Extract meaningful keywords from a company name, removing common suffixes.
    
    Args:
        name: Company name string
        
    Returns:
        list: List of keywords (words, excluding common suffixes)
    """
    # Common suffixes to remove
    suffixes = ['inc', 'inc.', 'corp', 'corp.', 'corporation', 'ltd', 'ltd.', 'limited', 
                'llc', 'plc', 'sa', 'ag', 'nv', 'bv', 'gmbh', 'se', 'co', 'company',
                'holdings', 'holding', 'group', 'companies', 'enterprises', 'industries']
    
    normalized = normalize_company_name(name)
    words = normalized.split()
    
    # Remove suffixes
    keywords = [w for w in words if w.rstrip('.,') not in suffixes]
    
    return keywords


def calculate_match_score(query, company_name, query_words, name_keywords):
    """Calculate a relevance score for a match.
    
    Higher score = better match.
    
    Args:
        query: Original query (normalized)
        company_name: Company name (normalized)
        query_words: Set of query words
        name_keywords: List of company name keywords
        
    Returns:
        int: Match score (higher is better)
    """
    score = 0
    name_keywords_set = set(name_keywords)
    
    # Exact match = highest score
    if query == company_name:
        return 1000
    
    # Query starts with company name or vice versa
    if company_name.startswith(query) or query.startswith(company_name):
        score += 500
    
    # All query words match as standalone words (word boundary match)
    # Check if query words appear as complete words in company name
    all_words_match = True
    word_boundary_matches = 0
    
    for qword in query_words:
        # Check if query word appears as a standalone word (with word boundaries)
        # Use word boundaries: space, start, end, or punctuation
        import re
        pattern = r'\b' + re.escape(qword) + r'\b'
        if re.search(pattern, company_name):
            word_boundary_matches += 1
        else:
            all_words_match = False
    
    if all_words_match and len(query_words) > 0:
        score += 400 + (word_boundary_matches * 50)
    elif word_boundary_matches > 0:
        score += 200 + (word_boundary_matches * 30)
    
    # First word of query matches first word of company name
    if query_words and name_keywords:
        if list(query_words)[0] == name_keywords[0]:
            score += 300
    
    # Query words are subset of company keywords
    if query_words.issubset(name_keywords_set):
        score += 100
    
    # Partial word matches (substring, but not as word boundary) - lower score
    if query in company_name or company_name in query:
        score += 50
    
    # Penalize matches where query is embedded in a longer word (e.g., "ford" in "ashford")
    # Check if query appears as substring but not as word
    if query in company_name:
        import re
        pattern = r'\b' + re.escape(query) + r'\b'
        if not re.search(pattern, company_name):
            # Query is embedded in a word, penalize
            score -= 200
    
    # Boost custom definitions slightly
    # (This will be handled by the caller)
    
    return score


def search_company_name(query, ticker_db, ticker_defs, max_results=20):
    """Search for tickers matching a company name query with smart ranking.
    
    Args:
        query: Company name to search for
        ticker_db: dict mapping ticker -> company name from main database
        ticker_defs: dict mapping ticker -> company name from definitions
        max_results: Maximum number of results to return
        
    Returns:
        list: List of (ticker, company_name, source, score) tuples, sorted by score descending
    """
    query_normalized = normalize_company_name(query)
    query_words = set(query_normalized.split())
    # Filter out very short words (1-2 chars) unless query is very short
    if len(query_normalized) > 3:
        query_words = {w for w in query_words if len(w) > 2}
    else:
        query_words = {w for w in query_words if len(w) > 0}
    
    scored_results = []
    
    # Combine both sources (definitions take precedence if same ticker)
    all_tickers = {**ticker_db, **ticker_defs}
    
    # Search through all tickers
    for ticker, company_name in all_tickers.items():
        name_normalized = normalize_company_name(company_name)
        name_keywords = extract_company_keywords(company_name)
        
        # Calculate match score
        score = calculate_match_score(query_normalized, name_normalized, query_words, name_keywords)
        
        # Only include if score > 0 (some match found)
        if score > 0:
            source = 'definitions' if ticker in ticker_defs else 'database'
            # Small boost for custom definitions
            if source == 'definitions':
                score += 10
            scored_results.append((ticker, company_name, source, score))
    
    # Remove duplicates (keep highest scoring ticker)
    ticker_scores = {}
    for ticker, company_name, source, score in scored_results:
        if ticker not in ticker_scores or score > ticker_scores[ticker][3]:
            ticker_scores[ticker] = (ticker, company_name, source, score)
    
    # Sort by score descending
    unique_results = sorted(ticker_scores.values(), key=lambda x: x[3], reverse=True)
    
    # Return top results (without score in output)
    return [(ticker, company_name, source) for ticker, company_name, source, _ in unique_results[:max_results]]


def display_results(query, results, max_display=10):
    """Display search results, showing top matches first.
    
    Args:
        query: Original search query
        results: List of (ticker, company_name, source) tuples (already sorted by relevance)
        max_display: Maximum number of results to display
    """
    if not results:
        print(f"\nNo ticker found for '{query}'")
        print("\nTips:")
        print("  - Try using a partial company name")
        print("  - Check spelling")
        print("  - The company might not be in the database")
        return
    
    # Show top results
    display_count = min(len(results), max_display)
    top_results = results[:display_count]
    
    print(f"\nFound {len(results)} match(es) for '{query}' (showing top {display_count}):")
    print("-" * 80)
    print(f"{'Ticker':<10} {'Company Name':<50} {'Source':<15}")
    print("-" * 80)
    
    for ticker, company_name, source in top_results:
        source_label = 'Custom Def' if source == 'definitions' else 'Database'
        print(f"{ticker:<10} {company_name:<50} {source_label:<15}")
    
    print("-" * 80)
    
    if len(results) > max_display:
        print(f"\n... and {len(results) - max_display} more result(s) (showing top {max_display} by relevance)")
    
    if len(results) == 1:
        ticker, company_name, _ = results[0]
        print(f"\n✓ Ticker: {ticker}")
        print(f"  Company: {company_name}")
    elif len(top_results) > 0:
        # Show the top match
        ticker, company_name, _ = top_results[0]
        print(f"\nTop match: {ticker} - {company_name}")


def main():
    """Main function."""
    print("=" * 80)
    print("Ticker Lookup Tool")
    print("=" * 80)
    print("\nEnter a company name to find its ticker symbol.")
    print("Searches both the main ticker database and custom definitions.")
    print("Type 'exit' to quit.")
    print()
    
    # Load data once at startup
    print("Loading ticker data...")
    ticker_db = load_ticker_database()
    ticker_defs = load_ticker_definitions()
    
    db_count = len(ticker_db)
    def_count = len(ticker_defs)
    print(f"Loaded {db_count:,} tickers from database")
    print(f"Loaded {def_count:,} tickers from custom definitions")
    print()
    
    while True:
        try:
            query = input("Enter company name: ").strip()
            
            if not query:
                continue
            
            if query.lower() in ['exit', 'quit', 'q']:
                print("Goodbye!")
                break
            
            # Search for matches
            results = search_company_name(query, ticker_db, ticker_defs)
            
            # Display results
            display_results(query, results)
            print()
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
