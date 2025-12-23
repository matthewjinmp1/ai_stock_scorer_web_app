#!/usr/bin/env python3
"""
Compare Methods Script
Compares keyword-based matching vs AI peer matching for a given company.
Shows top 10 matches from each method side by side.
"""

import os
import sys
import json

# Add parent directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.scoring.scorer import load_ticker_lookup, load_peers

# Import from generate_company_keywords
from generate_company_keywords import (
    load_cached_keywords,
    calculate_weighted_match,
    COMPOUNDING_WEIGHT
)


def get_keyword_matches(ticker, top_n=10):
    """Get top N keyword matches for a ticker."""
    cached_data = load_cached_keywords()
    companies = cached_data.get("companies", {})
    
    ticker_upper = ticker.strip().upper()
    
    if ticker_upper not in companies:
        return None, f"'{ticker_upper}' not found in keywords cache"
    
    keywords1 = companies[ticker_upper].get("keywords", [])
    company_name = companies[ticker_upper].get("company_name", ticker_upper)
    
    # Compare against all other tickers
    comparisons = []
    for other_ticker, other_data in companies.items():
        if other_ticker == ticker_upper:
            continue
        
        keywords2 = other_data.get("keywords", [])
        other_name = other_data.get("company_name", other_ticker)
        
        weighted_score, max_score, matching_keywords = calculate_weighted_match(keywords1, keywords2)
        
        if max_score == 0:
            percent = 0.0
        else:
            percent = (weighted_score / max_score) * 100
        
        comparisons.append({
            'ticker': other_ticker,
            'name': other_name,
            'percent': percent,
            'matches': len(matching_keywords)
        })
    
    # Sort by percent descending and take top N
    comparisons.sort(key=lambda x: x['percent'], reverse=True)
    return comparisons[:top_n], company_name


def get_peer_matches(ticker):
    """Get AI peer matches for a ticker from peers.json."""
    peers_data = load_peers()
    ticker_lookup = load_ticker_lookup()
    
    # Load keywords cache to check which peers have keyword data
    cached_keywords = load_cached_keywords()
    keywords_tickers = set(cached_keywords.get("companies", {}).keys())
    
    ticker_upper = ticker.strip().upper()
    
    if ticker_upper not in peers_data:
        return None, f"'{ticker_upper}' not found in peers.json"
    
    peer_tickers = peers_data[ticker_upper][:10]  # Top 10
    company_name = ticker_lookup.get(ticker_upper, ticker_upper)
    
    # Build peer list with names and keyword availability
    peers = []
    for peer_ticker in peer_tickers:
        peer_name = ticker_lookup.get(peer_ticker, peer_ticker)
        has_keywords = peer_ticker in keywords_tickers
        peers.append({
            'ticker': peer_ticker,
            'name': peer_name,
            'has_keywords': has_keywords
        })
    
    return peers, company_name


def display_comparison(ticker):
    """Display side-by-side comparison of keyword matches vs AI peers."""
    ticker_upper = ticker.strip().upper()
    ticker_lookup = load_ticker_lookup()
    
    # Get keyword matches
    keyword_matches, kw_result = get_keyword_matches(ticker_upper)
    
    # Get peer matches
    peer_matches, peer_result = get_peer_matches(ticker_upper)
    
    # Get company name
    company_name = ticker_lookup.get(ticker_upper, ticker_upper)
    
    print()
    print("=" * 100)
    print(f"COMPARISON: {ticker_upper} ({company_name})")
    print("=" * 100)
    print()
    
    # Check for errors
    if keyword_matches is None:
        print(f"Keyword Error: {kw_result}")
        keyword_matches = []
    
    if peer_matches is None:
        print(f"Peer Error: {peer_result}")
        peer_matches = []
    
    # Display side by side
    print(f"{'KEYWORD MATCHES':<50} {'AI PEER MATCHES':<50}")
    print(f"{'(Compounding weight: ' + str(COMPOUNDING_WEIGHT) + ')':<50} {'(From peers.json)':<50}")
    print("-" * 100)
    
    max_rows = max(len(keyword_matches), len(peer_matches), 10)
    
    for i in range(max_rows):
        # Keyword match column
        if i < len(keyword_matches):
            kw = keyword_matches[i]
            kw_str = f"{i+1:2}. {kw['ticker']:<6} {kw['name'][:35]}"
        else:
            kw_str = ""
        
        # Peer match column
        if i < len(peer_matches):
            peer = peer_matches[i]
            peer_str = f"{i+1:2}. {peer['ticker']:<6} {peer['name'][:35]}"
        else:
            peer_str = ""
        
        print(f"{kw_str:<50} {peer_str:<50}")
    
    print("-" * 100)
    
    # Find overlap - only consider peers that have keywords data
    if keyword_matches and peer_matches:
        kw_tickers = set(m['ticker'] for m in keyword_matches)
        # Only include peers that have keyword data for fair comparison
        peer_tickers_with_kw = set(p['ticker'] for p in peer_matches if p.get('has_keywords', False))
        peer_tickers_without_kw = set(p['ticker'] for p in peer_matches if not p.get('has_keywords', False))
        
        overlap = kw_tickers & peer_tickers_with_kw
        
        print()
        print(f"OVERLAP: {len(overlap)}/{len(peer_tickers_with_kw)} peers with keywords appear in keyword top 10")
        if overlap:
            print(f"  Matching: {', '.join(sorted(overlap))}")
        if peer_tickers_without_kw:
            print(f"  Missing keywords: {', '.join(sorted(peer_tickers_without_kw))}")
    
    print()


def main():
    """Main function."""
    print("=" * 100)
    print("Keyword vs AI Peer Comparison Tool")
    print("=" * 100)
    
    # Load data and find tickers in both files
    ticker_lookup = load_ticker_lookup()
    peers_data = load_peers()
    keywords_data = load_cached_keywords()
    
    peers_tickers = set(peers_data.keys())
    keywords_tickers = set(keywords_data.get("companies", {}).keys())
    common_tickers = sorted(peers_tickers & keywords_tickers)
    
    print(f"\nTickers in peers.json: {len(peers_tickers)}")
    print(f"Tickers in keywords.json: {len(keywords_tickers)}")
    print(f"Tickers in BOTH: {len(common_tickers)}")
    if common_tickers:
        print(f"  {', '.join(common_tickers)}")
    print()
    print("Enter a ticker to compare keyword-based matches vs AI peer matches.")
    print("Type 'exit' to quit.")
    print()
    
    while True:
        try:
            input_str = input("Enter ticker: ").strip()
            
            if not input_str:
                continue
            
            if input_str.lower() == 'exit':
                print("Goodbye!")
                break
            
            ticker_upper = input_str.upper()
            
            if ticker_upper not in ticker_lookup:
                print(f"Error: '{ticker_upper}' is not a valid ticker symbol.")
                continue
            
            display_comparison(ticker_upper)
            
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
