import sys
import os
import pytest
import json
import threading
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import scoring.scorer as scorer

@patch('os.path.exists')
@patch('builtins.open', new_callable=MagicMock)
def test_log_ai_response(mock_open, mock_exists):
    mock_exists.return_value = False
    
    # We need to capture the data passed to json.dump
    with patch('json.dump') as mock_json_dump:
        scorer.log_ai_response("AAPL", "Apple", "metric", "7", "model")
        
        mock_json_dump.assert_called_once()
        log_list = mock_json_dump.call_args[0][0]
        
        assert len(log_list) == 1
        assert log_list[0]["ticker"] == "AAPL"
        assert log_list[0]["response"] == "7"

@patch('os.path.exists')
@patch('builtins.open', new_callable=MagicMock)
def test_log_strange_response_not_strange(mock_open, mock_exists):
    # A simple number like "7" is NOT strange
    with patch('json.dump') as mock_json_dump:
        scorer.log_strange_response("AAPL", "Apple", "metric", "7", "model")
        # Should NOT be called
        mock_json_dump.assert_not_called()

@patch('os.path.exists')
@patch('builtins.open', new_callable=MagicMock)
def test_log_strange_response_is_strange(mock_open, mock_exists):
    mock_exists.return_value = False
    
    # A text response is strange
    with patch('json.dump') as mock_json_dump:
        # Mock print to avoid console output during test
        with patch('builtins.print'):
            scorer.log_strange_response("AAPL", "Apple", "metric", "The score is 7", "model")
            
            mock_json_dump.assert_called_once()
            log_list = mock_json_dump.call_args[0][0]
            
            assert len(log_list) == 1
            assert log_list[0]["response"] == "The score is 7"

def test_log_ai_response_threading():
    # Verify the lock is used
    # Instead of patching __enter__, we patch the lock object itself
    mock_lock = MagicMock()
    with patch('scoring.scorer.ALL_RESPONSES_LOG_LOCK', mock_lock):
        with patch('os.path.exists', return_value=False):
            with patch('builtins.open', MagicMock()):
                with patch('json.dump', MagicMock()):
                    scorer.log_ai_response("AAPL", "Apple", "metric", "7", "model")
                    # Check if __enter__ was called on the lock
                    mock_lock.__enter__.assert_called_once()


