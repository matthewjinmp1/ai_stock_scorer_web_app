import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import scoring.scorer as scorer

@pytest.fixture
def mock_db():
    with patch('scoring.scorer.db') as m:
        yield m

@pytest.fixture
def mock_api_client():
    with patch('scoring.scorer.get_api_client') as m:
        client = MagicMock()
        m.return_value = client
        yield client

def test_score_single_ticker_already_scored(mock_db):
    # Setup mock to return existing scores
    ticker = "AAPL"
    existing_scores = {
        "companies": {
            ticker: {
                "moat_score": 8,
                "model": "test-model"
            }
        }
    }
    
    with patch('scoring.scorer.load_scores', return_value=existing_scores):
        # We need to make sure all SCORE_DEFINITIONS keys are in the mock data
        for key in scorer.SCORE_DEFINITIONS:
            existing_scores["companies"][ticker][key] = 8
            
        result = scorer.score_single_ticker(ticker, silent=True)
        
        assert result['success'] is True
        assert result['already_scored'] is True
        assert result['ticker'] == ticker

def test_score_single_ticker_invalid_ticker():
    with patch('scoring.scorer.load_ticker_lookup', return_value={}):
        # This will make resolve_to_company_name return (None, "INVALID")
        result = scorer.score_single_ticker("INVALID", silent=True)
        assert result is None

def test_score_single_ticker_no_company_name():
    # Test case where ticker is found but name resolution fails (returns None)
    with patch('scoring.scorer.resolve_to_company_name', return_value=(None, "AAPL")):
        result = scorer.score_single_ticker("AAPL", silent=True)
        assert result is None

def test_get_company_moat_score_no_resolution():
    # Test get_company_moat_score exits when resolution fails
    with patch('scoring.scorer.resolve_to_company_name', return_value=(None, None)):
        with patch('builtins.print') as mock_print:
            scorer.get_company_moat_score("INVALID")
            # Should print error about invalid ticker
            any_invalid = any("not a valid ticker symbol" in str(call) for call in mock_print.call_args_list)
            assert any_invalid

def test_get_company_moat_score_no_company_name():
    # Test get_company_moat_score exits when name is missing
    with patch('scoring.scorer.resolve_to_company_name', return_value=(None, "AAPL")):
        with patch('builtins.print') as mock_print:
            scorer.get_company_moat_score("AAPL")
            # Should print error about missing company name
            any_missing = any("Could not resolve company name" in str(call) for call in mock_print.call_args_list)
            assert any_missing

@patch('scoring.scorer.query_all_scores_async')
def test_score_single_ticker_new_scoring(mock_query_async, mock_db, mock_api_client):
    ticker = "NEW"
    company_name = "New Company"
    
    # Mock lookup
    with patch('scoring.scorer.load_ticker_lookup', return_value={ticker: company_name}):
        # Mock empty scores
        with patch('scoring.scorer.load_scores', return_value={"companies": {}}):
            # Mock async query result
            mock_query_async.return_value = ({key: 7 for key in scorer.SCORE_DEFINITIONS}, 100, {}, "test-model")
            
            # Mock save_scores
            with patch('scoring.scorer.save_scores') as mock_save:
                result = scorer.score_single_ticker(ticker, silent=True)
                
                assert result['success'] is True
                assert result['already_scored'] is False
                assert result['total'] > 0
                mock_save.assert_called_once()

