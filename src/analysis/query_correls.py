#!/usr/bin/env python3
"""
Correlation Query Tool
Query correlations from correls.json
Usage: python query_correls.py
"""

import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from src.scoring.scorer import load_ticker_lookup

CORRELS_FILE = "data/correls.json"


def load_correlations():
    """Load correlations from JSON file.
    
    Returns:
        dict: Correlation data or None if error
    """
    if not os.path.exists(CORRELS_FILE):
        print(f"Error: {CORRELS_FILE} not found.")
        print("Please run batch_correlate.py first to generate correlations.")
        return None
    
    try:
        with open(CORRELS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {CORRELS_FILE}: {e}")
        return None


def get_all_correlations_for_ticker(ticker, correlations_data):
    """Get all correlations for a given ticker.
    
    Since correlations are stored unidirectionally (only for pairs where ticker1 < ticker2),
    we need to check both directions.
    
    Args:
        ticker: Ticker symbol (uppercase)
        correlations_data: Dictionary with correlation data
        
    Returns:
        list: List of tuples (other_ticker, correlation, num_metrics) sorted by correlation
    """
    ticker_upper = ticker.strip().upper()
    correlations = correlations_data.get("correlations", {})
    
    results = []
    
    # Check if this ticker has correlations stored (ticker comes first alphabetically)
    if ticker_upper in correlations:
        for other_ticker, data in correlations[ticker_upper].items():
            results.append((
                other_ticker,
                data.get('correlation', 0),
                data.get('num_metrics', 0)
            ))
    
    # Check if other tickers have correlations with this ticker (this ticker comes second)
    for other_ticker, ticker_correls in correlations.items():
        if ticker_upper in ticker_correls:
            data = ticker_correls[ticker_upper]
            results.append((
                other_ticker,
                data.get('correlation', 0),
                data.get('num_metrics', 0)
            ))
    
    # Sort by correlation strength (absolute value, descending)
    # This puts strongest correlations first, whether positive or negative
    results.sort(key=lambda x: abs(x[1]), reverse=True)
    
    return results


def show_ticker_correlations(ticker, correlations_data):
    """Display all correlations for a ticker, ranked by strength.
    
    Args:
        ticker: Ticker symbol
        correlations_data: Dictionary with correlation data
    """
    ticker_upper = ticker.strip().upper()
    ticker_lookup = load_ticker_lookup()
    company_name = ticker_lookup.get(ticker_upper, ticker_upper)
    
    print(f"\nCorrelations for {ticker_upper} ({company_name})")
    print("=" * 80)
    
    correlations = get_all_correlations_for_ticker(ticker_upper, correlations_data)
    
    if not correlations:
        print(f"No correlations found for {ticker_upper}.")
        print("Make sure the ticker exists in the correlations data.")
        return
    
    print(f"\nFound {len(correlations)} correlations")
    print()
    print(f"{'Rank':<6} {'Ticker':<10} {'Company Name':<40} {'Correlation':>12} {'Metrics':>10}")
    print("-" * 80)
    
    for rank, (other_ticker, correlation, num_metrics) in enumerate(correlations, 1):
        other_company_name = ticker_lookup.get(other_ticker, other_ticker)
        
        # Truncate company name if too long
        if len(other_company_name) > 38:
            other_company_name = other_company_name[:35] + "..."
        
        # Format correlation with sign
        if correlation >= 0:
            corr_str = f"+{correlation:.4f}"
        else:
            corr_str = f"{correlation:.4f}"
        
        print(f"{rank:<6} {other_ticker:<10} {other_company_name:<40} {corr_str:>12} {num_metrics:>10}")
    
    print()
    print("Note: Correlations are ranked by absolute strength (strongest first).")
    print("      Positive correlations indicate similar scoring patterns.")
    print("      Negative correlations indicate opposite scoring patterns.")


def get_top_correlations(correlations_data, top_n=100):
    """Get the top N strongest correlations across all ticker pairs.
    
    Args:
        correlations_data: Dictionary with correlation data
        top_n: Number of top correlations to return (default 100)
        
    Returns:
        list: List of tuples (ticker1, ticker2, correlation, num_metrics) sorted by absolute correlation
    """
    correlations = correlations_data.get("correlations", {})
    all_pairs = []
    
    # Collect all correlation pairs
    for ticker1, ticker_correls in correlations.items():
        for ticker2, data in ticker_correls.items():
            correlation = data.get('correlation', 0)
            num_metrics = data.get('num_metrics', 0)
            all_pairs.append((ticker1, ticker2, correlation, num_metrics))
    
    # Sort by absolute correlation strength (descending), then by actual correlation (descending)
    # This ensures consistent ordering: strongest first, with positive before negative for ties
    all_pairs.sort(key=lambda x: (abs(x[2]), x[2]), reverse=True)
    
    # Return top N
    return all_pairs[:top_n]


def show_top_correlations(correlations_data, top_n=100):
    """Display the top N strongest correlations.
    
    Args:
        correlations_data: Dictionary with correlation data
        top_n: Number of top correlations to show (default 100)
    """
    print(f"\nTop {top_n} Strongest Correlations")
    print("=" * 100)
    
    top_pairs = get_top_correlations(correlations_data, top_n)
    
    if not top_pairs:
        print("No correlations found.")
        return
    
    ticker_lookup = load_ticker_lookup()
    
    print()
    print(f"{'Rank':<6} {'Ticker 1':<10} {'Company 1':<35} {'Ticker 2':<10} {'Company 2':<35} {'Correlation':>12}")
    print("-" * 100)
    
    for rank, (ticker1, ticker2, correlation, num_metrics) in enumerate(top_pairs, 1):
        company1 = ticker_lookup.get(ticker1, ticker1)
        company2 = ticker_lookup.get(ticker2, ticker2)
        
        # Truncate company names if too long
        if len(company1) > 33:
            company1 = company1[:30] + "..."
        if len(company2) > 33:
            company2 = company2[:30] + "..."
        
        # Format correlation with sign
        if correlation >= 0:
            corr_str = f"+{correlation:.4f}"
        else:
            corr_str = f"{correlation:.4f}"
        
        print(f"{rank:<6} {ticker1:<10} {company1:<35} {ticker2:<10} {company2:<35} {corr_str:>12}")
    
    print()
    print("Note: Correlations are ranked by absolute strength (strongest first).")
    print("      Positive correlations indicate similar scoring patterns.")
    print("      Negative correlations indicate opposite scoring patterns.")


def get_bottom_correlations(correlations_data, bottom_n=100):
    """Get the bottom N most negative correlations across all ticker pairs.
    
    Args:
        correlations_data: Dictionary with correlation data
        bottom_n: Number of bottom correlations to return (default 100)
        
    Returns:
        list: List of tuples (ticker1, ticker2, correlation, num_metrics) sorted by correlation (most negative first)
    """
    correlations = correlations_data.get("correlations", {})
    all_pairs = []
    
    # Collect all correlation pairs
    for ticker1, ticker_correls in correlations.items():
        for ticker2, data in ticker_correls.items():
            correlation = data.get('correlation', 0)
            num_metrics = data.get('num_metrics', 0)
            all_pairs.append((ticker1, ticker2, correlation, num_metrics))
    
    # Sort by correlation value (ascending - most negative first)
    all_pairs.sort(key=lambda x: x[2])
    
    # Return bottom N (most negative)
    return all_pairs[:bottom_n]


def show_bottom_correlations(correlations_data, bottom_n=100):
    """Display the bottom N most negative correlations.
    
    Args:
        correlations_data: Dictionary with correlation data
        bottom_n: Number of bottom correlations to show (default 100)
    """
    print(f"\nBottom {bottom_n} Most Negative Correlations")
    print("=" * 100)
    
    bottom_pairs = get_bottom_correlations(correlations_data, bottom_n)
    
    if not bottom_pairs:
        print("No correlations found.")
        return
    
    ticker_lookup = load_ticker_lookup()
    
    print()
    print(f"{'Rank':<6} {'Ticker 1':<10} {'Company 1':<35} {'Ticker 2':<10} {'Company 2':<35} {'Correlation':>12}")
    print("-" * 100)
    
    for rank, (ticker1, ticker2, correlation, num_metrics) in enumerate(bottom_pairs, 1):
        company1 = ticker_lookup.get(ticker1, ticker1)
        company2 = ticker_lookup.get(ticker2, ticker2)
        
        # Truncate company names if too long
        if len(company1) > 33:
            company1 = company1[:30] + "..."
        if len(company2) > 33:
            company2 = company2[:30] + "..."
        
        # Format correlation with sign
        if correlation >= 0:
            corr_str = f"+{correlation:.4f}"
        else:
            corr_str = f"{correlation:.4f}"
        
        print(f"{rank:<6} {ticker1:<10} {company1:<35} {ticker2:<10} {company2:<35} {corr_str:>12}")
    
    print()
    print("Note: Correlations are ranked by value (most negative first).")
    print("      These are the pairs with the strongest negative correlations.")
    print("      They indicate companies with opposite scoring patterns.")


def list_all_tickers(correlations_data):
    """List all tickers available in the correlations data.
    
    Args:
        correlations_data: Dictionary with correlation data
    """
    correlations = correlations_data.get("correlations", {})
    
    all_tickers = set()
    
    # Get all tickers from the keys
    all_tickers.update(correlations.keys())
    
    # Get all tickers from the nested dictionaries
    for ticker_correls in correlations.values():
        all_tickers.update(ticker_correls.keys())
    
    sorted_tickers = sorted(all_tickers)
    
    print(f"\nAvailable Tickers ({len(sorted_tickers)} total):")
    print("=" * 80)
    
    # Print in columns
    cols = 5
    for i in range(0, len(sorted_tickers), cols):
        row_tickers = sorted_tickers[i:i+cols]
        print("  ".join(f"{ticker:<8}" for ticker in row_tickers))
    
    print()


def main():
    """Main function for correlation query tool."""
    print("Correlation Query Tool")
    print("=" * 80)
    
    correlations_data = load_correlations()
    if not correlations_data:
        return
    
    metadata = correlations_data.get("metadata", {})
    print(f"Loaded correlations from {CORRELS_FILE}")
    print(f"Total companies: {metadata.get('total_companies', 'N/A')}")
    print(f"Total correlations: {metadata.get('total_correlations', 'N/A')}")
    print(f"Calculated at: {metadata.get('calculated_at', 'N/A')}")
    print()
    print("Commands:")
    print("  Enter a ticker symbol to see its correlations (ranked by strength)")
    print("  Type 'top' to see the top 100 strongest correlations")
    print("  Type 'bottom' to see the bottom 100 most negative correlations")
    print("  Type 'list' to see all available tickers")
    print("  Type 'quit' or 'exit' to stop")
    print()
    
    while True:
        try:
            user_input = input("Enter ticker (or 'top'/'bottom'/'list'/'quit'): ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            elif user_input.lower() == 'top':
                show_top_correlations(correlations_data, top_n=100)
                print()
            elif user_input.lower() == 'bottom':
                show_bottom_correlations(correlations_data, bottom_n=100)
                print()
            elif user_input.lower() == 'list':
                list_all_tickers(correlations_data)
            elif user_input:
                show_ticker_correlations(user_input, correlations_data)
                print()
            else:
                print("Please enter a ticker symbol or command.")
                
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except EOFError:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")
            print()


if __name__ == "__main__":
    main()

