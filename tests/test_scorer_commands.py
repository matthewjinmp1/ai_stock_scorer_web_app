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

def test_handle_all_command_no_entries(mock_db):
    ticker = "NONE"
    mock_db.get_all_versions.return_value = []
    
    with patch('builtins.print') as mock_print:
        scorer.handle_all_command(ticker)
        # Should print that no entries were found
        mock_print.assert_any_call(f"No entries found for {ticker} in the database.")

def test_handle_all_command_with_entries(mock_db):
    ticker = "AAPL"
    mock_db.get_all_versions.return_value = [
        {"id": 1, "model": "m1", "timestamp": "2023-01-01T12:00:00", "total_score": 80, "company_name": "Apple"}
    ]
    
    with patch('builtins.print'):
        # Just verify it doesn't crash
        scorer.handle_all_command(ticker)
        mock_db.get_all_versions.assert_called_with(ticker)

def test_handle_compare_command_missing_models(mock_db):
    ticker = "AAPL"
    # Only one version
    mock_db.get_all_versions.return_value = [{"model": "m1"}]
    
    with patch('builtins.print') as mock_print:
        scorer.handle_compare_command(ticker)
        # Check for the actual error message
        mock_print.assert_any_call(f"Error: Found only 1 entry for {ticker}. Need at least 2 entries with different models to compare.")

def test_handle_database_command_cancel():
    # Provide 'c' to cancel
    with patch('builtins.input', return_value='c'):
        with patch('builtins.print') as mock_print:
            scorer.handle_database_command()
            # Verify the menu header was printed
            mock_print.assert_any_call("\nAvailable Databases:")



@patch('scoring.scorer.load_scores')
def test_rank_by_metric_empty(mock_load_scores):
    mock_load_scores.return_value = {"companies": {}}
    with patch('builtins.print') as mock_print:
        scorer.rank_by_metric("moat_score")
        mock_print.assert_any_call("No scores stored yet.")

