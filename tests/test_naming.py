import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Import the module we want to test
import scoring.scorer as scorer

@pytest.fixture
def mock_db():
    with patch('scoring.scorer.db') as m:
        yield m

@pytest.fixture
def mock_load_ticker_lookup():
    with patch('scoring.scorer.load_ticker_lookup') as m:
        m.return_value = {"AAPL": "Apple Inc.", "MSFT": "Microsoft Corp"}
        yield m

def test_get_current_display_name_ticker_mode():
    # Set global to False (show tickers)
    with patch('scoring.scorer.GLOBAL_SHOW_NAMES', False):
        name = scorer.get_current_display_name("AAPL")
        assert name == "AAPL"

def test_get_current_display_name_name_mode_from_db(mock_db):
    # Set global to True (show names)
    with patch('scoring.scorer.GLOBAL_SHOW_NAMES', True):
        # Mock database response
        mock_db.get_score.return_value = {"company_name": "Apple from DB"}
        
        name = scorer.get_current_display_name("AAPL")
        assert name == "Apple from DB"
        mock_db.get_score.assert_called_with("AAPL")

def test_get_current_display_name_name_mode_fallback_to_json(mock_db, mock_load_ticker_lookup):
    with patch('scoring.scorer.GLOBAL_SHOW_NAMES', True):
        # Mock database returns nothing
        mock_db.get_score.return_value = None
        
        name = scorer.get_current_display_name("AAPL")
        assert name == "Apple Inc."

def test_get_current_display_name_cleaning():
    with patch('scoring.scorer.GLOBAL_SHOW_NAMES', True):
        # Test cleaning of newlines and extra spaces
        name = scorer.get_current_display_name("MSTR", company_name="Strategy \n (MicroStrategy)")
        assert name == "Strategy (MicroStrategy)"

def test_resolve_to_company_name(mock_load_ticker_lookup):
    # Mock sqlite3.connect to avoid hitting real databases during tests
    with patch('sqlite3.connect') as mock_connect:
        mock_conn = mock_connect.return_value.__enter__.return_value
        mock_cursor = mock_conn.cursor.return_value
        mock_cursor.fetchone.return_value = None # No DB match
        
        # Mock db.get_score as well
        with patch('scoring.scorer.db.get_score', return_value=None):
            # Resolve valid ticker
            name, ticker = scorer.resolve_to_company_name("AAPL")
            assert name == "Apple Inc."
            assert ticker == "AAPL"
            
            # Resolve unknown ticker (looks like ticker, so returns None name)
            name, ticker = scorer.resolve_to_company_name("XYZ")
            assert name == None
            assert ticker == "XYZ"
            
            # Resolve company name (contains space, so not a ticker)
            name, ticker = scorer.resolve_to_company_name("Some Company")
            assert name == "Some Company"
            assert ticker == None
