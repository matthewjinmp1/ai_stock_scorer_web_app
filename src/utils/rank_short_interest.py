#!/usr/bin/env python3
"""
Rank Short Interest
Ranks tickers from short_interest.json by short_float in ascending order (lowest first)
Saves results to short_interest_ranked.json
"""

import json
import os
from datetime import datetime

SHORT_INTEREST_FILE = "data/short_interest.json"
RANKED_OUTPUT_FILE = "data/short_interest_ranked.json"


def parse_short_float(short_float_str):
    """
    Parse short float string (e.g., "1.46%") to float value.
    
    Args:
        short_float_str: String like "1.46%" or None
        
    Returns:
        float: Numeric value, or 999.0 if None/invalid (to sort to end)
    """
    if short_float_str is None:
        return 999.0
    
    try:
        # Remove % sign and convert to float
        value = float(short_float_str.replace('%', '').strip())
        return value
    except (ValueError, AttributeError):
        return 999.0


def rank_short_interest():
    """Rank tickers by short float in ascending order."""
    
    if not os.path.exists(SHORT_INTEREST_FILE):
        print(f"Error: {SHORT_INTEREST_FILE} not found.")
        return False
    
    # Load data
    print(f"Loading {SHORT_INTEREST_FILE}...")
    try:
        with open(SHORT_INTEREST_FILE, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {SHORT_INTEREST_FILE}: {e}")
        return False
    
    tickers_data = data.get('tickers', {})
    print(f"Found {len(tickers_data)} tickers")
    
    # Create list of tickers with their short float values
    ticker_list = []
    for ticker, ticker_data in tickers_data.items():
        short_float_str = ticker_data.get('short_float')
        short_float_value = parse_short_float(short_float_str)
        
        ticker_list.append({
            'ticker': ticker,
            'company_name': ticker_data.get('company_name', ''),
            'exchange': ticker_data.get('exchange', ''),
            'short_float': short_float_str,
            'short_float_value': short_float_value,
            'scraped_at': ticker_data.get('scraped_at', '')
        })
    
    # Sort by short_float_value ascending (lowest first)
    ticker_list.sort(key=lambda x: x['short_float_value'])
    
    # Create ranked output structure
    ranked_data = {
        'ranked_tickers': [],
        'total_tickers': len(ticker_list),
        'ranked_at': datetime.now().isoformat(),
        'sort_order': 'ascending (lowest short float first)'
    }
    
    # Add ranked entries
    for rank, ticker_info in enumerate(ticker_list, 1):
        ranked_entry = {
            'rank': rank,
            'ticker': ticker_info['ticker'],
            'company_name': ticker_info['company_name'],
            'exchange': ticker_info['exchange'],
            'short_float': ticker_info['short_float'],
            'scraped_at': ticker_info['scraped_at']
        }
        ranked_data['ranked_tickers'].append(ranked_entry)
    
    # Save ranked data
    print(f"\nSaving ranked data to {RANKED_OUTPUT_FILE}...")
    try:
        with open(RANKED_OUTPUT_FILE, 'w') as f:
            json.dump(ranked_data, f, indent=2)
        print(f"Successfully saved {len(ticker_list)} ranked tickers to {RANKED_OUTPUT_FILE}")
        return True
    except Exception as e:
        print(f"Error saving {RANKED_OUTPUT_FILE}: {e}")
        return False


def display_top_bottom(limit=20):
    """Display top and bottom ranked tickers."""
    
    if not os.path.exists(RANKED_OUTPUT_FILE):
        print(f"Error: {RANKED_OUTPUT_FILE} not found. Run ranking first.")
        return
    
    try:
        with open(RANKED_OUTPUT_FILE, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading {RANKED_OUTPUT_FILE}: {e}")
        return
    
    ranked_tickers = data.get('ranked_tickers', [])
    
    if not ranked_tickers:
        print("No ranked tickers found.")
        return
    
    print("\n" + "=" * 80)
    print(f"Top {limit} Tickers with LOWEST Short Float (Best)")
    print("=" * 80)
    print(f"{'Rank':<6} {'Ticker':<8} {'Short Float':<12} {'Company Name':<40}")
    print("-" * 80)
    
    for entry in ranked_tickers[:limit]:
        short_float = entry.get('short_float', 'N/A')
        if short_float is None:
            short_float = 'N/A'
        print(f"{entry['rank']:<6} {entry['ticker']:<8} {short_float:<12} {entry['company_name'][:38]}")
    
    print("\n" + "=" * 80)
    print(f"Top {limit} Tickers with HIGHEST Short Float (Worst)")
    print("=" * 80)
    print(f"{'Rank':<6} {'Ticker':<8} {'Short Float':<12} {'Company Name':<40}")
    print("-" * 80)
    
    for entry in ranked_tickers[-limit:][::-1]:  # Reverse to show highest first
        short_float = entry.get('short_float', 'N/A')
        if short_float is None:
            short_float = 'N/A'
        print(f"{entry['rank']:<6} {entry['ticker']:<8} {short_float:<12} {entry['company_name'][:38]}")
    
    print("=" * 80)


def main():
    """Main function."""
    print("=" * 80)
    print("Short Interest Ranker")
    print("=" * 80)
    print("Ranking tickers by short float (ascending - lowest first)")
    print("=" * 80)
    print()
    
    # Rank the tickers
    if rank_short_interest():
        # Display summary
        display_top_bottom()
    else:
        print("Failed to rank tickers.")


if __name__ == "__main__":
    main()

