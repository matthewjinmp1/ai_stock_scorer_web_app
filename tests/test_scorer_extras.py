import sys
import os
import pytest
import json
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import scoring.scorer as scorer

def test_calculate_correlation_perfect():
    # Setup two identical companies
    ticker1_data = {key: 10 for key in scorer.SCORE_DEFINITIONS}
    ticker2_data = {key: 10 for key in scorer.SCORE_DEFINITIONS}
    
    # We need to mock load_ticker_lookup to return names for the tickers
    mock_lookup = {"T1": "Company 1", "T2": "Company 2"}
    
    with patch('scoring.scorer.load_ticker_lookup', return_value=mock_lookup):
        with patch('scoring.scorer.load_scores', return_value={"companies": {"T1": ticker1_data, "T2": ticker2_data}}):
            # Reset with variation to ensure non-zero denominator
            for i, key in enumerate(scorer.SCORE_DEFINITIONS):
                ticker1_data[key] = float(i)
                ticker2_data[key] = float(i)
                
            corr, count = scorer.calculate_correlation("T1", "T2")
            assert corr == pytest.approx(1.0)
            assert count == len(scorer.SCORE_DEFINITIONS)

def test_calculate_correlation_inverse():
    ticker1_data = {}
    ticker2_data = {}
    for i, key in enumerate(scorer.SCORE_DEFINITIONS):
        ticker1_data[key] = float(i)
        ticker2_data[key] = float(10 - i)
        
    mock_lookup = {"T1": "Company 1", "T2": "Company 2"}
    
    with patch('scoring.scorer.load_ticker_lookup', return_value=mock_lookup):
        with patch('scoring.scorer.load_scores', return_value={"companies": {"T1": ticker1_data, "T2": ticker2_data}}):
            corr, count = scorer.calculate_correlation("T1", "T2")
            assert corr == pytest.approx(-1.0)

def test_get_ticker_from_company_name_exact():
    mock_lookup = {"AAPL": "Apple Inc.", "MSFT": "Microsoft"}
    with patch('scoring.scorer.load_ticker_lookup', return_value=mock_lookup):
        # Exact match
        assert scorer.get_ticker_from_company_name("Apple Inc.") == "AAPL"
        # Case insensitive
        assert scorer.get_ticker_from_company_name("apple inc.") == "AAPL"
        # Unknown
        assert scorer.get_ticker_from_company_name("Non-Existent") is None

@patch('os.path.exists')
@patch('builtins.open', new_callable=MagicMock)
def test_save_ticker_conversion(mock_open, mock_exists):
    mock_exists.return_value = False
    with patch('json.dump') as mock_json_dump:
        # Mock load_ticker_conversions to avoid recursion or complex setup
        with patch('scoring.scorer.load_ticker_conversions', return_value={}):
            # Patch the file path constant
            with patch('scoring.scorer.TICKER_CONVERSIONS_FILE', 'tests/temp_conversions.json'):
                scorer.save_ticker_conversion("Apple", "AAPL", True, "exact_match")
                mock_json_dump.assert_called_once()
                # Verify the record structure
                data_written = mock_json_dump.call_args[0][0]
                assert "Apple" in data_written
                assert data_written["Apple"][0]["ticker"] == "AAPL"
                assert data_written["Apple"][0]["method"] == "exact_match"

@patch('scoring.scorer.db')
def test_load_scores_db(mock_db):
    mock_db.get_all_scores.return_value = {"AAPL": {"moat_score": 10}}
    scores = scorer.load_scores()
    assert scores == {"companies": {"AAPL": {"moat_score": 10}}}

@patch('scoring.scorer.db')
def test_get_all_total_scores(mock_db):
    # Mock get_all_scores to return some data
    mock_db.get_all_scores.return_value = {
        "AAPL": {"moat_score": 10, "total_score": 100},
        "MSFT": {"moat_score": 8, "total_score": 80}
    }
    totals = scorer.get_all_total_scores()
    assert len(totals) == 2
    assert all(isinstance(t, float) for t in totals)
