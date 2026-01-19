import unittest
import os
import sys
import sqlite3
import json
from unittest.mock import patch, MagicMock

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from web_app.app import app, find_company_in_top_companies, get_peers_for_ticker, get_db_connection

class ExtraCoverageTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()

    def test_find_company_fuzzy_complex(self):
        """Test the complex fuzzy matching logic in find_company_in_top_companies."""
        # This targets lines 388-415 in app.py (partial matches with base name)
        # We need to simulate a DB where a partial base name matches
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            # Simulate: 1. No exact match, 2. No suffix match, 3. No standard partial match
            # 4. Partial match with base name (e.g. "Apple" matches "Apple Inc")
            mock_cursor.fetchone.side_effect = [
                None, # Exact match fail
                None, # Suffix match fail
                None, # standard partial match fail
                {'ticker': 'AAPL', 'name': 'Apple Inc', 'rank': 1} # base name partial match success
            ]
            
            # Use a name with a suffix to trigger the base_name logic
            result = find_company_in_top_companies("Apple Communications")
            self.assertIsNotNone(result)
            self.assertEqual(result['ticker'], 'AAPL')

    def test_peers_no_results_error(self):
        """Test the 'No peers found' error handling in the peers route."""
        # Targets lines 521-522
        with patch('web_app.app.get_peers_for_ticker', return_value=[]):
            response = self.app.get('/peers?search=AAPL')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'No peers found', response.data)

    def test_peers_metadata_but_no_score(self):
        """Test peers route where peer exists in metadata but has no score yet."""
        # Targets lines 606-617
        with patch('web_app.app.get_peers_for_ticker', return_value=['PeerWithoutScore']):
            with patch('web_app.app.find_company_in_top_companies', return_value={'ticker': 'PWS', 'name': 'Peer Without Score', 'rank': 100}):
                with patch('web_app.app.get_db_connection') as mock_db:
                    mock_conn = MagicMock()
                    mock_db.return_value = mock_conn
                    
                    # 1. Fetch search company info (company_row) - line 505
                    # 2. Fetch search company score (company_score_row) - line 561
                    # 3. Fetch peer score (score_row) - line 590
                    mock_conn.execute().fetchone.side_effect = [
                        {'ticker': 'AAPL', 'company_name': 'Apple'}, # 1. company_row
                        {'ticker': 'AAPL', 'company_name': 'Apple', 'total_score': 2000}, # 2. company_score_row
                        None # 3. Peer score (doesn't exist)
                    ]
                    
                    # 1. Fetch all scores (all_scores_rows) - line 534
                    # 2. Fetch global ranks (global_rank_rows) - line 548
                    mock_conn.execute().fetchall.side_effect = [
                        [{'total_score': 2000}], # all_scores_rows
                        [{'ticker': 'AAPL', 'total_score': 2000}] # global_rank_rows
                    ]
                    
                    response = self.app.get('/peers?search=AAPL')
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(b'Peer Without Score', response.data)
                    self.assertIn(b'N/A', response.data)

    def test_ai_relevance_partial_match(self):
        """Test AI Relevance page search with a partial match."""
        # Targets lines 697-700
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            # Mock relevance_scores and metadata
            mock_conn.execute().fetchall.side_effect = [
                [{'ticker': 'AAPL', 'score': 90}, {'ticker': 'MSFT', 'score': 85}], # relevance_scores
                [{'ticker': 'AAPL', 'name': 'Apple', 'rank': 1}, {'ticker': 'MSFT', 'name': 'Microsoft', 'rank': 2}] # metadata
            ]
            
            # Searching for 'SOFT' should match Microsoft but not Apple
            response = self.app.get('/ai-relevance?search=SOFT')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Microsoft', response.data)
            self.assertNotIn(b'Apple', response.data)

    def test_ai_relevance_empty_ranking(self):
        """Test AI Relevance page with empty tickers."""
        # Targets line 660
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            mock_conn.execute().fetchall.return_value = [] # Empty rows
            
            response = self.app.get('/ai-relevance')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Ranking is empty', response.data)

    def test_ai_relevance_metadata_missing(self):
        """Test AI Relevance page when top_companies.db is missing."""
        # Targets lines 664
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            # relevance_scores success
            mock_conn.execute().fetchall.return_value = [{'ticker': 'AAPL', 'score': 90}]
            
            # Mock os.path.exists to fail for TOP_COMPANIES_DB
            with patch('os.path.exists', side_effect=lambda p: False if 'top_companies.db' in p else True):
                response = self.app.get('/ai-relevance')
                self.assertEqual(response.status_code, 200)
                # Should fallback to basic info
                self.assertIn(b'AAPL', response.data)

    def test_ai_relevance_company_not_in_metadata(self):
        """Test AI Relevance page when a company is in scores but not in metadata."""
        # Targets line 684
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            # relevance_scores has AAPL
            mock_conn.execute().fetchall.side_effect = [
                [{'ticker': 'AAPL', 'score': 90}], # relevance_scores
                [] # metadata empty
            ]
            
            response = self.app.get('/ai-relevance')
            self.assertEqual(response.status_code, 200)
            # Should show ticker as fallback
            self.assertIn(b'AAPL', response.data)

    def test_get_peers_for_ticker_missing_db(self):
        """Test get_peers_for_ticker when peers.db is missing."""
        # Targets line 276
        with patch('os.path.exists', return_value=False):
            result = get_peers_for_ticker('AAPL')
            self.assertEqual(result, [])

    def test_get_db_connection_error(self):
        """Test get_db_connection when sqlite3.connect fails."""
        # Targets lines 35-37
        with patch('sqlite3.connect', side_effect=sqlite3.Error("Mock Connection Error")):
            with self.assertRaises(sqlite3.Error):
                get_db_connection()

    def test_find_company_no_metadata_db(self):
        """Test find_company_in_top_companies when metadata DB is missing."""
        # Targets line 297
        with patch('os.path.exists', return_value=False):
            result = find_company_in_top_companies('AAPL')
            self.assertIsNone(result)

    def test_ai_relevance_search_partial_match_branch(self):
        """Test the partial match branch in AI relevance search."""
        # This targets the loop starting at line 697
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            # Mock data
            mock_conn.execute().fetchall.side_effect = [
                [{'ticker': 'AAPL', 'score': 90}], # relevance_scores
                [{'ticker': 'AAPL', 'name': 'Apple', 'rank': 1}] # metadata
            ]
            
            # Search for something that IS NOT an exact ticker match but IS a name match
            # Wait, 'APPLE' is not 'AAPL'.
            response = self.app.get('/ai-relevance?search=APPLE')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Apple', response.data)

    def test_ai_relevance_exact_ticker_match(self):
        """Test the exact ticker match optimization in AI relevance search."""
        # Targets line 796
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            # Mock data with multiple companies
            mock_conn.execute().fetchall.side_effect = [
                [{'ticker': 'AAPL', 'score': 90}, {'ticker': 'MSFT', 'score': 85}],
                [{'ticker': 'AAPL', 'name': 'Apple', 'rank': 1}, {'ticker': 'MSFT', 'name': 'Microsoft', 'rank': 2}]
            ]
            
            # Searching for exact ticker 'AAPL'
            response = self.app.get('/ai-relevance?search=AAPL')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Apple', response.data)
            self.assertNotIn(b'Microsoft', response.data)

    def test_ai_relevance_pagination_boundaries(self):
        """Test AI relevance pagination boundary handling."""
        # Targets lines 812 and 814
        with patch('sqlite3.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn
            # 150 companies to have 2 pages (100 per page)
            companies = [{'ticker': f'T{i}', 'score': 100-i} for i in range(150)]
            metadata = [{'ticker': f'T{i}', 'name': f'Name {i}', 'rank': i} for i in range(150)]
            mock_conn.execute().fetchall.side_effect = [companies, metadata]
            
            # Test page < 1 (line 812)
            response = self.app.get('/ai-relevance?page=0')
            self.assertEqual(response.status_code, 200)
            
            # Reset mock for next call
            mock_conn.execute().fetchall.side_effect = [companies, metadata]
            # Test page > total_pages (line 814)
            response = self.app.get('/ai-relevance?page=999')
            self.assertEqual(response.status_code, 200)

    def test_ai_relevance_cache_missing(self):
        """Test AI relevance route when DB file is missing."""
        # Targets line 729
        with patch('os.path.exists', side_effect=lambda p: False if 'ai_relevance_scores.db' in p else True):
            response = self.app.get('/ai-relevance')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'No AI relevance cache found', response.data)

    def test_ai_relevance_cache_exception(self):
        """Test AI relevance route when DB connection fails."""
        # Targets lines 744-745
        with patch('sqlite3.connect', side_effect=Exception("Database error")):
            response = self.app.get('/ai-relevance')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Error loading scored ranking', response.data)

if __name__ == '__main__':
    unittest.main()
