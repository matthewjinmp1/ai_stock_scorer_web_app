import sys
import os
import pytest
import json
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import scoring.scorer as scorer

def test_format_total_score():
    # Calculate max possible score to know what to expect
    max_score = sum(scorer.SCORE_WEIGHTS.get(key, 1.0) for key in scorer.SCORE_DEFINITIONS) * 10
    
    # Test with 50% of max score
    total = max_score * 0.5
    
    # With percentile
    assert scorer.format_total_score(total, 80) == "50 (80th percentile)"
    assert scorer.format_total_score(total, 1) == "50 (1st percentile)"
    
    # Test with raw percentage if no percentile provided and only one score exists
    with patch('scoring.scorer.get_all_total_scores', return_value=[total]):
        assert scorer.format_total_score(total) == "50"


@patch('os.path.exists')
@patch('builtins.open', new_callable=MagicMock)
def test_load_custom_ticker_definitions(mock_open, mock_exists):
    # Setup
    mock_exists.return_value = True
    mock_file = mock_open.return_value.__enter__.return_value
    mock_file.read.return_value = json.dumps({
        "definitions": {
            "T1": "Company 1",
            "t2": "  Company 2  "
        }
    })
    
    defs = scorer.load_custom_ticker_definitions()
    
    assert defs["T1"] == "Company 1"
    assert defs["T2"] == "Company 2" # Uppercased and stripped

@patch('builtins.open', new_callable=MagicMock)
def test_save_custom_ticker_definitions(mock_open):
    defs = {"AAPL": "Apple Inc."}
    success = scorer.save_custom_ticker_definitions(defs)
    
    assert success is True
    mock_open.assert_called()
    
    # Verify what was written
    args, kwargs = mock_open.call_args
    assert "ticker_definitions.json" in args[0]
    
    handle = mock_open.return_value.__enter__.return_value
    # Get the data passed to json.dump
    # In reality json.dump(data, f) is called, so we check handle.write if we can,
    # but since json.dump takes the file handle, it's easier to check the data.
    # But wait, json.dump doesn't call write directly in a way that's easy to mock without patching json.dump.
    
    with patch('json.dump') as mock_json_dump:
        scorer.save_custom_ticker_definitions(defs)
        mock_json_dump.assert_called_once()
        data_written = mock_json_dump.call_args[0][0]
        assert data_written["definitions"] == defs

def test_get_model_for_ticker():
    # Currently it always returns DEFAULT_MODEL
    assert scorer.get_model_for_ticker("AAPL") == scorer.DEFAULT_MODEL
    assert scorer.get_model_for_ticker("GOOGL") == scorer.DEFAULT_MODEL

@patch('scoring.scorer.load_db_path')
@patch('os.path.exists')
@patch('builtins.open', new_callable=MagicMock)
def test_load_show_names(mock_open, mock_exists, mock_load_db):
    mock_exists.return_value = True
    mock_file = mock_open.return_value.__enter__.return_value
    mock_file.read.return_value = json.dumps({"show_names": True})
    
    assert scorer.load_show_names() is True
    
    mock_file.read.return_value = json.dumps({"show_names": False})
    assert scorer.load_show_names() is False
    
    # Default fallback
    mock_exists.return_value = False
    assert scorer.load_show_names() is False

