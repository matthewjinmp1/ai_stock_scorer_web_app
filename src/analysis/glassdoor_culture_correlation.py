#!/usr/bin/env python3
"""
Glassdoor Rating vs Culture Score Correlation Analysis
Calculates correlation between Glassdoor ratings and culture_employee_satisfaction_score from scores_copy.json
"""

import json
import sys
from scipy.stats import pearsonr, spearmanr
import numpy as np


def load_data(glassdoor_file="data/glassdoor.json", scores_file="data/scores_copy.json"):
    """
    Load data from both JSON files.
    
    Args:
        glassdoor_file: Path to glassdoor.json
        scores_file: Path to scores_copy.json
        
    Returns:
        tuple: (glassdoor_data, scores_data)
    """
    try:
        with open(glassdoor_file, 'r') as f:
            glassdoor_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {glassdoor_file} not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse {glassdoor_file}: {e}")
        sys.exit(1)
    
    try:
        with open(scores_file, 'r') as f:
            scores_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {scores_file} not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse {scores_file}: {e}")
        sys.exit(1)
    
    return glassdoor_data, scores_data


def extract_matching_data(glassdoor_data, scores_data):
    """
    Extract matching tickers and their ratings/scores.
    
    Args:
        glassdoor_data: Dictionary from glassdoor.json
        scores_data: Dictionary from scores.json
        
    Returns:
        list: List of tuples (ticker, glassdoor_rating, culture_score)
    """
    glassdoor_companies = glassdoor_data.get("companies", {})
    scores_companies = scores_data.get("companies", {})
    
    matching_data = []
    
    for ticker in glassdoor_companies.keys():
        if ticker in scores_companies:
            glassdoor_info = glassdoor_companies[ticker]
            scores_info = scores_companies[ticker]
            
            # Get Glassdoor rating
            glassdoor_rating = glassdoor_info.get("rating")
            
            # Get culture score (convert string to float)
            culture_score_str = scores_info.get("culture_employee_satisfaction_score")
            
            # Only include if both values exist and are valid
            if glassdoor_rating is not None and culture_score_str is not None:
                try:
                    culture_score = float(culture_score_str)
                    matching_data.append((ticker, glassdoor_rating, culture_score))
                except (ValueError, TypeError):
                    continue
    
    return matching_data


def calculate_correlation(glassdoor_ratings, culture_scores):
    """
    Calculate correlation coefficients.
    
    Args:
        glassdoor_ratings: List of Glassdoor ratings
        culture_scores: List of culture scores
        
    Returns:
        dict: Dictionary with correlation statistics
    """
    glassdoor_array = np.array(glassdoor_ratings)
    culture_array = np.array(culture_scores)
    
    # Pearson correlation (linear relationship)
    pearson_corr, pearson_p = pearsonr(glassdoor_array, culture_array)
    
    # Spearman correlation (monotonic relationship)
    spearman_corr, spearman_p = spearmanr(glassdoor_array, culture_array)
    
    # Basic statistics
    stats = {
        "n": len(glassdoor_ratings),
        "pearson_correlation": pearson_corr,
        "pearson_p_value": pearson_p,
        "spearman_correlation": spearman_corr,
        "spearman_p_value": spearman_p,
        "glassdoor_mean": float(np.mean(glassdoor_array)),
        "glassdoor_std": float(np.std(glassdoor_array)),
        "glassdoor_min": float(np.min(glassdoor_array)),
        "glassdoor_max": float(np.max(glassdoor_array)),
        "culture_mean": float(np.mean(culture_array)),
        "culture_std": float(np.std(culture_array)),
        "culture_min": float(np.min(culture_array)),
        "culture_max": float(np.max(culture_array)),
    }
    
    return stats


def display_results(matching_data, stats):
    """
    Display correlation analysis results.
    
    Args:
        matching_data: List of tuples (ticker, glassdoor_rating, culture_score)
        stats: Dictionary with correlation statistics
    """
    print("=" * 80)
    print("Glassdoor Rating vs Culture Score Correlation Analysis")
    print("=" * 80)
    print()
    
    print(f"Sample Size: {stats['n']} companies")
    print()
    
    print("Glassdoor Ratings Statistics:")
    print(f"  Mean: {stats['glassdoor_mean']:.2f}")
    print(f"  Std Dev: {stats['glassdoor_std']:.2f}")
    print(f"  Range: {stats['glassdoor_min']:.2f} - {stats['glassdoor_max']:.2f}")
    print()
    
    print("Culture Employee Satisfaction Scores Statistics:")
    print(f"  Mean: {stats['culture_mean']:.2f}")
    print(f"  Std Dev: {stats['culture_std']:.2f}")
    print(f"  Range: {stats['culture_min']:.1f} - {stats['culture_max']:.1f}")
    print()
    
    print("Correlation Results:")
    print("-" * 80)
    print(f"Pearson Correlation (linear): {stats['pearson_correlation']:.4f}")
    print(f"  p-value: {stats['pearson_p_value']:.6f}")
    
    if stats['pearson_p_value'] < 0.001:
        significance = "*** (highly significant)"
    elif stats['pearson_p_value'] < 0.01:
        significance = "** (very significant)"
    elif stats['pearson_p_value'] < 0.05:
        significance = "* (significant)"
    else:
        significance = "(not significant)"
    
    print(f"  Significance: {significance}")
    print()
    
    print(f"Spearman Correlation (monotonic): {stats['spearman_correlation']:.4f}")
    print(f"  p-value: {stats['spearman_p_value']:.6f}")
    
    if stats['spearman_p_value'] < 0.001:
        significance = "*** (highly significant)"
    elif stats['spearman_p_value'] < 0.01:
        significance = "** (very significant)"
    elif stats['spearman_p_value'] < 0.05:
        significance = "* (significant)"
    else:
        significance = "(not significant)"
    
    print(f"  Significance: {significance}")
    print()
    
    # Interpretation
    pearson_abs = abs(stats['pearson_correlation'])
    if pearson_abs >= 0.7:
        strength = "strong"
    elif pearson_abs >= 0.4:
        strength = "moderate"
    elif pearson_abs >= 0.2:
        strength = "weak"
    else:
        strength = "very weak"
    
    direction = "positive" if stats['pearson_correlation'] > 0 else "negative"
    
    print("Interpretation:")
    print(f"  There is a {strength} {direction} correlation between Glassdoor ratings")
    print(f"  and culture employee satisfaction scores.")
    print()
    
    # Show some examples
    print("Sample Data (first 10 companies):")
    print("-" * 80)
    print(f"{'Ticker':<8} {'Glassdoor':<12} {'Culture Score':<15}")
    print("-" * 80)
    for ticker, gd_rating, culture_score in matching_data[:10]:
        print(f"{ticker:<8} {gd_rating:<12.2f} {culture_score:<15.1f}")
    
    if len(matching_data) > 10:
        print(f"... and {len(matching_data) - 10} more companies")
    
    print("=" * 80)


def main():
    """Main function to run correlation analysis."""
    print("Loading data...")
    glassdoor_data, scores_data = load_data(scores_file="data/scores_copy.json")
    
    print("Extracting matching data...")
    matching_data = extract_matching_data(glassdoor_data, scores_data)
    
    if not matching_data:
        print("Error: No matching tickers found between glassdoor.json and scores.json")
        sys.exit(1)
    
    # Extract arrays for correlation calculation
    glassdoor_ratings = [item[1] for item in matching_data]
    culture_scores = [item[2] for item in matching_data]
    
    print("Calculating correlations...")
    stats = calculate_correlation(glassdoor_ratings, culture_scores)
    
    # Display results
    display_results(matching_data, stats)


if __name__ == "__main__":
    main()

