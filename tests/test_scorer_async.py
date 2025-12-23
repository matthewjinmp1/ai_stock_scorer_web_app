import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import scoring.scorer as scorer

def test_query_all_scores_async():
    mock_grok = MagicMock()
    # Mock simple_query_with_tokens to return a value and usage with all keys
    mock_grok.simple_query_with_tokens.return_value = ("7", {
        "total_tokens": 10,
        "input_tokens": 6,
        "output_tokens": 4
    })
    
    score_keys = ["moat_score", "barriers_score"]
    
    with patch('scoring.scorer.log_ai_response'):
        with patch('scoring.scorer.log_strange_response'):
            results, tokens, usage, model = scorer.query_all_scores_async(
                mock_grok, "Apple", score_keys, silent=True
            )
            
            assert results["moat_score"] == "7"
            assert results["barriers_score"] == "7"
            assert tokens == 20
            # usage combines input tokens: 6 + 6 = 12
            assert usage["input_tokens"] == 12 

def test_resolve_to_company_name_branches():
    mock_lookup = {"AAPL": "Apple Inc."}
    with patch('scoring.scorer.load_ticker_lookup', return_value=mock_lookup):
        # We need to mock sqlite3.connect because resolve_to_company_name now checks DB
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = mock_connect.return_value.__enter__.return_value
            mock_cursor = mock_conn.cursor.return_value
            mock_cursor.fetchone.return_value = None # No DB match
            
            # Ticker match
            name, ticker = scorer.resolve_to_company_name("AAPL")
            assert name == "Apple Inc."
            assert ticker == "AAPL"
            
            # Name match (contains spaces, so not a ticker)
            name, ticker = scorer.resolve_to_company_name("Apple Inc.")
            assert name == "Apple Inc."
            assert ticker is None
            
            # Unknown ticker match (no spaces, so looks like ticker)
            name, ticker = scorer.resolve_to_company_name("XYZ")
            assert name is None
            assert ticker == "XYZ"

@patch('scoring.scorer.get_current_display_name')
@patch('scoring.scorer.get_all_total_scores', return_value=[90.0, 80.0])
@patch('scoring.scorer.load_scores')
def test_view_scores_with_data(mock_load_scores, mock_totals, mock_display_name):
    # Setup data with ALL metrics to avoid being skipped
    apple_data = {key: 9 for key in scorer.SCORE_DEFINITIONS}
    apple_data["company_name"] = "Apple"
    msft_data = {key: 8 for key in scorer.SCORE_DEFINITIONS}
    msft_data["company_name"] = "Microsoft"
    
    mock_load_scores.return_value = {
        "companies": {
            "AAPL": apple_data,
            "MSFT": msft_data
        }
    }
    # Mock display name
    mock_display_name.side_effect = lambda t, n=None: n if n else t
    
    with patch('builtins.print') as mock_print:
        with patch('scoring.scorer.calculate_percentile_rank', return_value=100):
            scorer.view_scores()
            
            # Combine all output
            all_output = "".join(str(call) for call in mock_print.call_args_list)
            assert "Apple" in all_output or "AAPL" in all_output
            assert "Microsoft" in all_output or "MSFT" in all_output

@patch('scoring.scorer.get_all_total_scores', return_value=[80.0, 70.0])
@patch('scoring.scorer.score_single_ticker')
def test_handle_redo_command_multiple(mock_score, mock_totals):
    # Setup mock return value
    mock_score.return_value = {
        'success': True, 
        'ticker': 'AAPL', 
        'scores': {}, 
        'total': 80.0, 
        'total_tokens': 100, 
        'token_usage': {'input_tokens': 50, 'output_tokens': 50},
        'model_used': 'test-model'
    }
    
    scorer.handle_redo_command("AAPL MSFT")
    assert mock_score.call_count == 2

@patch('scoring.scorer.load_scores')
@patch('scoring.scorer.score_single_ticker')
def test_handle_upgrade_command(mock_score, mock_load_scores):
    mock_load_scores.return_value = {
        "companies": {
            "AAPL": {"model": "old-model"},
            "MSFT": {"model": scorer.DEFAULT_MODEL}
        }
    }
    
    # Setup mock return value
    mock_score.return_value = {
        'success': True,
        'total': 80.0,
        'total_tokens': 100,
        'token_usage': {'input_tokens': 50, 'output_tokens': 50},
        'model_used': scorer.DEFAULT_MODEL,
        'scores': {'model': scorer.DEFAULT_MODEL}
    }
    
    with patch('scoring.scorer.get_model_for_ticker', return_value=scorer.DEFAULT_MODEL):
        with patch('builtins.input', return_value='y'):
            with patch('builtins.print'):
                scorer.handle_upgrade_command()
                mock_score.assert_called_once_with("AAPL", silent=True, batch_mode=True, force_rescore=True)
