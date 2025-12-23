#!/usr/bin/env python3
"""
Evaluate Methods Script
Uses Grok AI to judge whether keyword-based matching or AI peer matching
produces better peer recommendations for each company.

For each ticker in both keywords.json and peers.json:
- Gets top 10 keyword matches
- Gets all AI peers
- Asks Grok which method produced better peers
- Aggregates stats
"""

import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional

# Add parent directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from openai import OpenAI
    from config import XAI_API_KEY
except ImportError:
    print("Error: Could not import OpenAI client or XAI_API_KEY.")
    sys.exit(1)

from src.scoring.scorer import load_ticker_lookup, load_peers

# Import from generate_company_keywords
from generate_company_keywords import (
    load_cached_keywords,
    calculate_weighted_match,
    GROK_PRICING,
    calculate_grok_cost
)

# Settings
NUM_THREADS = 20
MODEL = "grok-4-1-fast-reasoning"

# Initialize Grok client
grok_client = OpenAI(
    api_key=XAI_API_KEY,
    base_url="https://api.x.ai/v1"
)


def get_keyword_matches(ticker: str, companies: dict, ticker_lookup: dict, top_n: int = 10) -> List[Dict]:
    """Get top N keyword matches for a ticker."""
    ticker_upper = ticker.strip().upper()
    
    if ticker_upper not in companies:
        return []
    
    keywords1 = companies[ticker_upper].get("keywords", [])
    
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
            'percent': percent
        })
    
    # Sort by percent descending and take top N
    comparisons.sort(key=lambda x: x['percent'], reverse=True)
    return comparisons[:top_n]


def get_peer_list(ticker: str, peers_data: dict, ticker_lookup: dict) -> List[Dict]:
    """Get AI peers for a ticker from peers.json."""
    ticker_upper = ticker.strip().upper()
    
    if ticker_upper not in peers_data:
        return []
    
    peer_tickers = peers_data[ticker_upper]
    
    peers = []
    for peer_ticker in peer_tickers:
        peer_name = ticker_lookup.get(peer_ticker, peer_ticker)
        peers.append({
            'ticker': peer_ticker,
            'name': peer_name
        })
    
    return peers


def evaluate_with_grok(ticker: str, company_name: str, 
                       keyword_matches: List[Dict], 
                       ai_peers: List[Dict]) -> Tuple[str, dict, float]:
    """
    Ask Grok to evaluate which method produced better peer recommendations.
    
    Returns:
        Tuple of (winner: 'keywords' | 'peers' | 'tie', token_usage, cost)
    """
    # Format the lists for the prompt - USE COMPANY NAMES ONLY, not tickers
    # Some tickers are made up for private/non-US companies
    kw_list = "\n".join([f"  {i+1}. {m['name']}" for i, m in enumerate(keyword_matches)])
    peer_list = "\n".join([f"  {i+1}. {p['name']}" for i, p in enumerate(ai_peers)])
    
    prompt = f"""You are evaluating two methods for finding peer companies (competitors/similar businesses) for a given company.

COMPANY: {company_name}

METHOD A - KEYWORD MATCHING (based on industry/sector keyword overlap):
{kw_list}

METHOD B - AI PEER SELECTION (directly suggested by AI):
{peer_list}

TASK: Which method produced a better list of peer companies for {company_name}?

Consider:
- Are the suggested companies actually in the same industry/sector?
- Are they genuine competitors or comparable businesses?
- Are there any obvious mistakes (companies from completely different industries)?

RESPOND WITH EXACTLY ONE WORD:
- "KEYWORDS" if Method A is better
- "PEERS" if Method B is better
- "TIE" if they are roughly equal"""

    try:
        response = grok_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are an expert financial analyst who evaluates peer company recommendations. Answer with exactly one word: KEYWORDS, PEERS, or TIE."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50,
            temperature=0.1
        )
        
        answer = response.choices[0].message.content.strip().upper()
        
        # Parse token usage
        token_usage = {
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens': response.usage.completion_tokens,
            'reasoning_tokens': 0
        }
        
        # Try to get reasoning tokens
        if hasattr(response.usage, 'completion_tokens_details') and response.usage.completion_tokens_details:
            details = response.usage.completion_tokens_details
            if hasattr(details, 'reasoning_tokens'):
                token_usage['reasoning_tokens'] = details.reasoning_tokens or 0
        
        cost = calculate_grok_cost(token_usage, MODEL)
        
        # Normalize answer
        if "KEYWORD" in answer:
            return "keywords", token_usage, cost
        elif "PEER" in answer:
            return "peers", token_usage, cost
        else:
            return "tie", token_usage, cost
            
    except Exception as e:
        print(f"  Error evaluating {ticker}: {e}")
        return "error", {}, 0.0


def process_ticker(ticker: str, companies: dict, peers_data: dict, 
                   ticker_lookup: dict) -> Dict:
    """Process a single ticker and return evaluation results."""
    start_time = time.time()
    
    company_name = companies.get(ticker, {}).get("company_name", ticker)
    
    # Get matches from both methods
    keyword_matches = get_keyword_matches(ticker, companies, ticker_lookup)
    ai_peers = get_peer_list(ticker, peers_data, ticker_lookup)
    
    if not keyword_matches or not ai_peers:
        return {
            'ticker': ticker,
            'company_name': company_name,
            'winner': 'skip',
            'reason': 'Missing data',
            'time': 0
        }
    
    # Evaluate with Grok
    winner, token_usage, cost = evaluate_with_grok(ticker, company_name, keyword_matches, ai_peers)
    
    elapsed = time.time() - start_time
    
    return {
        'ticker': ticker,
        'company_name': company_name,
        'winner': winner,
        'keyword_matches': [m['ticker'] for m in keyword_matches],
        'ai_peers': [p['ticker'] for p in ai_peers],
        'token_usage': token_usage,
        'cost': cost,
        'time': elapsed
    }


def main():
    print("=" * 80)
    print("Method Evaluation Tool - Grok AI Judge")
    print("=" * 80)
    print()
    
    # Load data
    print("Loading data...")
    ticker_lookup = load_ticker_lookup()
    peers_data = load_peers()
    keywords_data = load_cached_keywords()
    companies = keywords_data.get("companies", {})
    
    # Find common tickers
    peers_tickers = set(peers_data.keys())
    keywords_tickers = set(companies.keys())
    common_tickers = sorted(peers_tickers & keywords_tickers)
    
    print(f"Tickers in peers.json: {len(peers_tickers)}")
    print(f"Tickers in keywords.json: {len(keywords_tickers)}")
    print(f"Tickers in BOTH: {len(common_tickers)}")
    print()
    
    if not common_tickers:
        print("No common tickers found. Nothing to evaluate.")
        return
    
    print(f"Common tickers: {', '.join(common_tickers)}")
    print()
    print(f"Evaluating {len(common_tickers)} tickers with {NUM_THREADS} threads...")
    print("-" * 80)
    
    # Process all tickers with multithreading
    results = []
    total_cost = 0.0
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = {
            executor.submit(process_ticker, ticker, companies, peers_data, ticker_lookup): ticker
            for ticker in common_tickers
        }
        
        completed = 0
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                results.append(result)
                
                completed += 1
                winner = result['winner']
                elapsed = result.get('time', 0)
                cost = result.get('cost', 0)
                total_cost += cost
                
                symbol = {'keywords': 'K', 'peers': 'P', 'tie': '=', 'error': '!', 'skip': '-'}
                print(f"[{completed}/{len(common_tickers)}] {result['ticker']:<6} -> {symbol.get(winner, '?')} {winner:<8} ({elapsed:.1f}s, {cost*100:.2f}¢)")
                
            except Exception as e:
                print(f"[{completed}/{len(common_tickers)}] {ticker:<6} -> ERROR: {e}")
    
    total_time = time.time() - start_time
    
    # Calculate stats
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    
    keywords_wins = sum(1 for r in results if r['winner'] == 'keywords')
    peers_wins = sum(1 for r in results if r['winner'] == 'peers')
    ties = sum(1 for r in results if r['winner'] == 'tie')
    errors = sum(1 for r in results if r['winner'] == 'error')
    skipped = sum(1 for r in results if r['winner'] == 'skip')
    
    valid_total = keywords_wins + peers_wins + ties
    
    print(f"Total tickers evaluated: {len(results)}")
    print(f"Valid evaluations: {valid_total}")
    print(f"Errors: {errors}")
    print(f"Skipped: {skipped}")
    print()
    print(f"{'METHOD':<20} {'WINS':<10} {'PERCENTAGE':<15}")
    print("-" * 45)
    
    if valid_total > 0:
        print(f"{'KEYWORDS':<20} {keywords_wins:<10} {keywords_wins/valid_total*100:5.1f}%")
        print(f"{'PEERS':<20} {peers_wins:<10} {peers_wins/valid_total*100:5.1f}%")
        print(f"{'TIE':<20} {ties:<10} {ties/valid_total*100:5.1f}%")
    else:
        print("No valid evaluations to display.")
    
    print()
    print(f"Total time: {total_time:.1f} seconds")
    print(f"Total cost: {total_cost*100:.2f} cents")
    print()
    
    # Show detailed results
    print("-" * 80)
    print("DETAILED RESULTS:")
    print("-" * 80)
    
    # Group by winner
    for winner_type in ['keywords', 'peers', 'tie']:
        winner_results = [r for r in results if r['winner'] == winner_type]
        if winner_results:
            label = {'keywords': 'KEYWORDS WON', 'peers': 'PEERS WON', 'tie': 'TIE'}
            print(f"\n{label[winner_type]} ({len(winner_results)}):")
            for r in winner_results:
                print(f"  {r['ticker']:<6} - {r['company_name']}")
    
    # Save results to JSON
    output_file = os.path.join(os.path.dirname(__file__), "evaluation_results.json")
    output_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_evaluated": len(results),
        "stats": {
            "keywords_wins": keywords_wins,
            "peers_wins": peers_wins,
            "ties": ties,
            "errors": errors,
            "skipped": skipped
        },
        "total_cost_cents": total_cost * 100,
        "total_time_seconds": total_time,
        "results": results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)
    
    print()
    print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    main()
