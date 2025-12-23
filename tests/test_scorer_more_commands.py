import sys
import os
import pytest
import json
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import scoring.scorer as scorer

@patch('os.path.exists')
@patch('builtins.open', new_callable=MagicMock)
def test_load_peers(mock_open, mock_exists):
    mock_exists.return_value = True
    mock_file = mock_open.return_value.__enter__.return_value
    mock_file.read.return_value = json.dumps({"AAPL": ["MSFT", "GOOGL"]})
    
    peers = scorer.load_peers()
    assert peers["AAPL"] == ["MSFT", "GOOGL"]

@patch('builtins.open', new_callable=MagicMock)
def test_save_peers(mock_open):
    peers_data = {"AAPL": ["MSFT"]}
    with patch('json.dump') as mock_json_dump:
        scorer.save_peers(peers_data)
        mock_json_dump.assert_called_once()
        assert mock_json_dump.call_args[0][0] == peers_data

@patch('scoring.scorer.load_scores')
def test_rank_by_metric_with_data(mock_load_scores):
    # Setup data
    mock_load_scores.return_value = {
        "companies": {
            "AAPL": {"moat_score": 9, "company_name": "Apple"},
            "MSFT": {"moat_score": 8, "company_name": "Microsoft"}
        }
    }
    
    with patch('builtins.print') as mock_print:
        scorer.rank_by_metric("moat_score")
        # Check that rankings were printed
        mock_print.assert_any_call(f"{'Rank':<6} {'Company':<40} {'Score':>8}")
        # Verify order (Apple 9 > Microsoft 8)
        
        found_apple = False
        found_microsoft = False
        apple_rank = 0
        microsoft_rank = 0
        
        for i, call in enumerate(mock_print.call_args_list):
            msg = str(call[0][0]) if call[0] else ""
            if "Apple" in msg:
                found_apple = True
                apple_rank = i
            if "Microsoft" in msg:
                found_microsoft = True
                microsoft_rank = i
        
        assert found_apple and found_microsoft
        assert apple_rank < microsoft_rank

@patch('scoring.scorer.db')
@patch('scoring.scorer.load_scores')
def test_delete_company(mock_load_scores, mock_db):
    mock_load_scores.return_value = {"companies": {"AAPL": {"moat_score": 8}}}
    
    # Mock user input to 'yes'
    with patch('builtins.input', return_value='yes'):
        with patch('builtins.print'):
            scorer.delete_company("AAPL")
            mock_db.delete_score.assert_called_with("AAPL")

def test_calculate_total_score_cleaning_edge_cases():
    # Test weird string score
    scores = {key: 0 for key in scorer.SCORE_DEFINITIONS}
    first_key = list(scorer.SCORE_DEFINITIONS.keys())[0]
    scores[first_key] = "Highly rated (9.5/10)"
    
    total = scorer.calculate_total_score(scores)
    # The cleaner should extract 9.5
    assert total > 0 # At least some score was added
