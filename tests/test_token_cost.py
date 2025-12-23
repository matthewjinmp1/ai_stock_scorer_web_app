import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from scoring.scorer import calculate_token_cost, MODEL_PRICING

def test_calculate_token_cost_basic():
    # Test fallback cost (average of input/output)
    model = "grok-4-1-fast-reasoning"
    pricing = MODEL_PRICING[model]
    avg_price = (pricing[0] + pricing[1]) / 2
    
    # 1M tokens should cost avg_price
    assert calculate_token_cost(1_000_000, model=model) == pytest.approx(avg_price)
    
    # 100k tokens
    assert calculate_token_cost(100_000, model=model) == pytest.approx(avg_price * 0.1)

def test_calculate_token_cost_breakdown():
    model = "grok-4-1-fast-reasoning"
    pricing = MODEL_PRICING[model]
    input_price = pricing[0]
    output_price = pricing[1]
    cached_price = pricing[2]
    
    token_usage = {
        'input_tokens': 1_000_000,
        'output_tokens': 1_000_000,
        'cached_tokens': 500_000
    }
    
    # Regular input = 1M - 500k = 500k
    # Cost = (500k * input_price) + (500k * cached_price) + (1M * output_price)
    expected = (0.5 * input_price) + (0.5 * cached_price) + (1.0 * output_price)
    
    assert calculate_token_cost(0, model=model, token_usage=token_usage) == pytest.approx(expected)

def test_calculate_token_cost_alternative_keys():
    # Test with prompt_tokens and completion_tokens
    model = "grok-4-1-fast-reasoning"
    pricing = MODEL_PRICING[model]
    
    token_usage = {
        'prompt_tokens': 1_000_000,
        'completion_tokens': 1_000_000,
        'prompt_cache_hit_tokens': 0
    }
    
    expected = (1.0 * pricing[0]) + (1.0 * pricing[1])
    assert calculate_token_cost(0, model=model, token_usage=token_usage) == pytest.approx(expected)

def test_calculate_token_cost_unknown_model():
    assert calculate_token_cost(1000, model="non-existent") == 0.0

def test_calculate_token_cost_zero():
    assert calculate_token_cost(0, model="grok-4-1-fast-reasoning") == 0.0

