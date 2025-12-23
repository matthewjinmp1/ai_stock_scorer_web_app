import sys
import os
import pytest
import re

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from scoring.scorer import calculate_total_score, calculate_percentile_rank, SCORE_DEFINITIONS, SCORE_WEIGHTS

def test_calculate_total_score_all_zeros():
    scores = {key: 0 for key in SCORE_DEFINITIONS}
    # For reverse scores, 0 becomes 10.
    # Total = sum(weight * (10 if reverse else 0))
    expected = 0
    for key, defn in SCORE_DEFINITIONS.items():
        weight = SCORE_WEIGHTS.get(key, 1.0)
        if defn['is_reverse']:
            expected += 10 * weight
        else:
            expected += 0 * weight
    
    assert calculate_total_score(scores) == pytest.approx(expected)

def test_calculate_total_score_all_tens():
    scores = {key: 10 for key in SCORE_DEFINITIONS}
    # For reverse scores, 10 becomes 0.
    expected = 0
    for key, defn in SCORE_DEFINITIONS.items():
        weight = SCORE_WEIGHTS.get(key, 1.0)
        if defn['is_reverse']:
            expected += 0 * weight
        else:
            expected += 10 * weight
            
    assert calculate_total_score(scores) == pytest.approx(expected)

def test_calculate_percentile_rank():
    all_scores = [10, 20, 30, 40, 50]
    assert calculate_percentile_rank(30, all_scores) == 60 # 3/5 * 100
    assert calculate_percentile_rank(10, all_scores) == 20 # 1/5 * 100
    assert calculate_percentile_rank(50, all_scores) == 100 # 5/5 * 100
    assert calculate_percentile_rank(5, all_scores) == 0 # 0/5 * 100
    assert calculate_percentile_rank(55, all_scores) == 100 # 5/5 * 100

def test_calculate_percentile_rank_empty():
    assert calculate_percentile_rank(10, []) is None

def test_calculate_total_score_with_strings():
    # Only set one score to test cleaning
    first_key = list(SCORE_DEFINITIONS.keys())[0]
    is_reverse = SCORE_DEFINITIONS[first_key]['is_reverse']
    
    # Test cleaning "Score: 7.5" -> 7.5
    scores = {key: 0 for key in SCORE_DEFINITIONS}
    scores[first_key] = "Score: 7.5"
    
    expected = 0
    for key, defn in SCORE_DEFINITIONS.items():
        weight = SCORE_WEIGHTS.get(key, 1.0)
        if key == first_key:
            val = 7.5
        else:
            val = 0.0
        
        if defn['is_reverse']:
            expected += (10 - val) * weight
        else:
            expected += val * weight
            
    assert calculate_total_score(scores) == pytest.approx(expected)

def test_calculate_total_score_none_values():
    # None should be treated as 0
    scores = {key: None for key in SCORE_DEFINITIONS}
    
    expected = 0
    for key, defn in SCORE_DEFINITIONS.items():
        weight = SCORE_WEIGHTS.get(key, 1.0)
        val = 0.0 # None treated as 0
        if defn['is_reverse']:
            expected += (10 - val) * weight
        else:
            expected += val * weight
            
    assert calculate_total_score(scores) == pytest.approx(expected)

