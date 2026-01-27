import unittest
import os
import sys
import sqlite3
import json
from unittest.mock import patch, MagicMock

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from src.web.app import app, find_company_in_top_companies
from src.core.repository import CompanyRepository
from src.core.config import TOP_SCORES_DB

class ExtraCoverageTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()

    def test_find_company_fuzzy_complex(self):
        """Test the complex fuzzy matching logic in find_company_in_top_companies."""
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Simulate the sequence of queries in find_company_in_top_companies
            mock_cursor.fetchone.side_effect = [
                None, # 1. Exact match fail
                None, # 2. Base name match fail (after suffix strip)
                {'ticker': 'AAPL', 'name': 'Apple Inc', 'rank': 1} # 3. Partial match success
            ]
            
            result = find_company_in_top_companies("Apple Communications")
            self.assertIsNotNone(result)
            self.assertEqual(result['ticker'], 'AAPL')

    def test_peers_no_results_error(self):
        """Test the 'No peers found' error handling in the peers route."""
        with patch('src.core.repository.CompanyRepository.get_company_detail', return_value={'ticker': 'AAPL', 'company_name': 'Apple'}):
            with patch('src.core.repository.CompanyRepository.get_peers', return_value=[]):
                response = self.app.get('/peers?search=AAPL')
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'No peers found', response.data)

    def test_ai_relevance_partial_match(self):
        """Test AI Relevance page search with a partial match."""
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.execute.return_value.fetchall.side_effect = [
                [{'ticker': 'AAPL', 'score': 90}, {'ticker': 'MSFT', 'score': 85}], # relevance_scores
                {'AAPL': {'ticker': 'AAPL', 'name': 'Apple', 'rank': 1}, 'MSFT': {'ticker': 'MSFT', 'name': 'Microsoft', 'rank': 2}} # company_metadata (simplified)
            ]
            
            # We need to patch the metadata call specifically because it's a class method
            with patch('src.core.repository.CompanyRepository.get_company_metadata', return_value={
                'AAPL': {'ticker': 'AAPL', 'name': 'Apple', 'rank': 1},
                'MSFT': {'ticker': 'MSFT', 'name': 'Microsoft', 'rank': 2}
            }):
                # Searching for 'SOFT' should match Microsoft but not Apple
                response = self.app.get('/ai-relevance?search=SOFT')
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'Microsoft', response.data)
                self.assertNotIn(b'Apple', response.data)

    def test_ai_relevance_empty_ranking(self):
        """Test AI Relevance page with empty tickers."""
        with patch('os.path.exists', return_value=True):
            with patch('sqlite3.connect') as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn
                mock_conn.execute.return_value.fetchall.return_value = [] # Empty rows
                
                response = self.app.get('/ai-relevance')
                self.assertEqual(response.status_code, 200)
                # It should show "0 companies ranked" in the header
                self.assertIn(b'0 companies ranked', response.data)

    def test_find_company_no_metadata_db(self):
        """Test find_company_in_top_companies when metadata DB is missing."""
        with patch('os.path.exists', side_effect=lambda p: False if 'top_companies.db' in p else True):
            result = find_company_in_top_companies('AAPL')
            self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
