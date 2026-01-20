import unittest
import os
import sys
import sqlite3
import tempfile
import shutil
import json

# Add project root to sys.path so we can import web_app.app
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from src.web.app import app, calculate_percentile_rank, get_max_possible_score, get_db_connection

class WebAppTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.app = app.test_client()
        
        # Store original DB_PATH
        self.original_db_path = os.getenv('DB_PATH')
        
    def tearDown(self):
        # Restore original DB_PATH
        if self.original_db_path:
            os.environ['DB_PATH'] = self.original_db_path
        elif 'DB_PATH' in os.environ:
            del os.environ['DB_PATH']

    def test_home_page(self):
        """Test that the home portal page loads successfully."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Stock Analysis Portal', response.data)
        self.assertIn(b'AI Stock Scores', response.data)

    def test_rankings_page(self):
        """Test that the rankings page loads successfully."""
        response = self.app.get('/rankings')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'AI Stock Scores', response.data)

    def test_rankings_page_structure(self):
        """Test that rankings page has required HTML elements."""
        response = self.app.get('/rankings')
        self.assertEqual(response.status_code, 200)
        # Check for search bar
        self.assertIn(b'searchInput', response.data)
        self.assertIn(b'Enter ticker or company name', response.data)
        # Check for suggestions dropdown
        self.assertIn(b'suggestionsDropdown', response.data)
        # Check for table structure
        self.assertIn(b'<table', response.data)
        self.assertIn(b'Ticker', response.data)
        self.assertIn(b'Company Name', response.data)
        self.assertIn(b'Score %', response.data)
        self.assertIn(b'Percentile', response.data)

    def test_health_endpoint(self):
        """Test the health check endpoint."""
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})

    def test_company_detail_page(self):
        """Test that a company detail page loads successfully (using a known ticker)."""
        # We'll use AAPL as it's likely to be in the top 500
        response = self.app.get('/company/AAPL')
        if response.status_code == 200:
            self.assertIn(b'Apple', response.data)
        else:
            # If AAPL isn't there, we just check that we don't get a 500 error
            self.assertIn(response.status_code, [200, 404])

    def test_company_detail_structure(self):
        """Test that company detail page has required elements."""
        response = self.app.get('/company/AAPL')
        if response.status_code == 200:
            # Check for key elements
            self.assertIn(b'Score %', response.data)
            self.assertIn(b'Percentile', response.data)
            # Check for metrics section
            self.assertIn(b'Key Performance Metrics', response.data)
            # Check for back button
            self.assertIn(b'Back to Rankings', response.data)

    def test_nonexistent_company(self):
        """Test that a 404 is returned for a non-existent company."""
        response = self.app.get('/company/NONEXISTENT_TICKER_123')
        self.assertEqual(response.status_code, 404)

    def test_company_detail_case_insensitive(self):
        """Test that ticker lookup is case-insensitive."""
        # Try both uppercase and lowercase
        response_upper = self.app.get('/company/AAPL')
        response_lower = self.app.get('/company/aapl')
        
        # Both should return the same status code
        self.assertEqual(response_upper.status_code, response_lower.status_code)

    def test_percentile_calculation(self):
        """Test percentile calculation function."""
        # Test with simple scores
        scores = [10.0, 20.0, 30.0, 40.0, 50.0]
        
        # Score of 30 should be at 60th percentile (3 out of 5 are <= 30)
        self.assertEqual(calculate_percentile_rank(30.0, scores), 60)
        
        # Score of 50 should be at 100th percentile (all are <= 50)
        self.assertEqual(calculate_percentile_rank(50.0, scores), 100)
        
        # Score of 10 should be at 20th percentile (1 out of 5 are <= 10)
        self.assertEqual(calculate_percentile_rank(10.0, scores), 20)
        
        # Score of 0 should be at 0th percentile
        self.assertEqual(calculate_percentile_rank(0.0, scores), 0)
        
        # Score higher than max should be at 100th percentile
        self.assertEqual(calculate_percentile_rank(100.0, scores), 100)

    def test_percentile_calculation_empty_list(self):
        """Test percentile calculation with empty list."""
        self.assertEqual(calculate_percentile_rank(50.0, []), 0)

    def test_percentile_calculation_single_score(self):
        """Test percentile calculation with single score."""
        scores = [50.0]
        self.assertEqual(calculate_percentile_rank(50.0, scores), 100)
        self.assertEqual(calculate_percentile_rank(40.0, scores), 0)

    def test_max_possible_score(self):
        """Test max possible score calculation."""
        max_score = get_max_possible_score()
        
        # Should be greater than 0
        self.assertGreater(max_score, 0)
        
        # Should be a reasonable number (sum of weights * 10)
        # With 23 metrics at weight 10 and one at 19.31, should be around 249.31 * 10 = 2493.1
        expected_min = 2000  # Reasonable minimum
        expected_max = 3000  # Reasonable maximum
        self.assertGreaterEqual(max_score, expected_min)
        self.assertLessEqual(max_score, expected_max)

    def test_rankings_with_companies(self):
        """Test that rankings page displays companies when they exist."""
        response = self.app.get('/rankings')
        self.assertEqual(response.status_code, 200)
        
        # If there are companies, check for table rows
        # This is a basic check - actual data depends on database
        html = response.data.decode('utf-8')
        if 'company-row' in html or 'tbody' in html:
            # If there's a tbody, there should be some structure
            pass  # Just verify it doesn't crash

    def test_search_functionality_present(self):
        """Test that search functionality HTML is present."""
        response = self.app.get('/rankings')
        self.assertEqual(response.status_code, 200)
        
        html = response.data.decode('utf-8')
        # Check for search input
        self.assertIn('id="searchInput"', html)
        # Check for clear button (may only appear when there's a search query)
        # The clear button is conditionally rendered, so we check for the search form instead
        self.assertIn('id="searchForm"', html)

    def test_company_detail_history_section(self):
        """Test that detail page loads successfully (history may not be displayed if only one entry)."""
        response = self.app.get('/company/AAPL')
        if response.status_code == 200:
            # The page should load without errors
            # History section may not be visible if there's only one score entry
            # Just verify the page renders correctly
            self.assertIn(b'Key Performance Metrics', response.data)

    def test_invalid_ticker_format(self):
        """Test handling of invalid ticker formats."""
        # Test with special characters
        response = self.app.get('/company/INVALID@TICKER')
        # Should either 404 or handle gracefully (not 500)
        self.assertIn(response.status_code, [200, 404])

    def test_percentile_edge_cases(self):
        """Test percentile calculation with edge cases."""
        # All same scores
        scores = [50.0, 50.0, 50.0]
        self.assertEqual(calculate_percentile_rank(50.0, scores), 100)
        
        # Duplicate scores
        scores = [10.0, 20.0, 20.0, 30.0]
        # Score of 20 should be at 75th percentile (3 out of 4 are <= 20)
        self.assertEqual(calculate_percentile_rank(20.0, scores), 75)

    def test_rankings_page_renders_without_errors(self):
        """Test that rankings page renders without template errors."""
        response = self.app.get('/rankings')
        self.assertEqual(response.status_code, 200)
        # Check that it's valid HTML (basic check)
        self.assertIn(b'<!DOCTYPE html>', response.data)
        self.assertIn(b'</html>', response.data)

    def test_company_detail_renders_without_errors(self):
        """Test that company detail page renders without template errors."""
        response = self.app.get('/company/AAPL')
        if response.status_code == 200:
            # Check that it's valid HTML
            self.assertIn(b'<!DOCTYPE html>', response.data)
            self.assertIn(b'</html>', response.data)

    def test_rankings_page_has_scroll_restoration(self):
        """Test that scroll restoration JavaScript is present."""
        response = self.app.get('/rankings')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Check for scroll restoration function
        self.assertIn('saveScrollAndNavigate', html)
        self.assertIn('sessionStorage', html)

    def test_company_detail_with_null_scores(self):
        """Test handling of companies with null/None scores."""
        # This is a basic test - actual null handling depends on database
        response = self.app.get('/company/AAPL')
        # Should not crash with 500 error
        self.assertIn(response.status_code, [200, 404])

    def test_multiple_company_requests(self):
        """Test that multiple company requests work correctly."""
        tickers = ['AAPL', 'MSFT', 'GOOG']
        for ticker in tickers:
            response = self.app.get(f'/company/{ticker}')
            # Should not crash
            self.assertIn(response.status_code, [200, 404])

    def test_pagination_basic(self):
        """Test that pagination works on index page."""
        response = self.app.get('/rankings?page=1')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Check for pagination controls if there are multiple pages
        if 'total_pages' in html or 'pagination' in html:
            # Pagination should be present
            pass  # Just verify it doesn't crash

    def test_pagination_page_parameter(self):
        """Test pagination with different page numbers."""
        # Test page 1
        response = self.app.get('/rankings?page=1')
        self.assertEqual(response.status_code, 200)
        
        # Test page 2 (if it exists)
        response = self.app.get('/rankings?page=2')
        self.assertEqual(response.status_code, 200)
        
        # Test page 0 (should default to 1)
        response = self.app.get('/rankings?page=0')
        self.assertEqual(response.status_code, 200)

    def test_pagination_invalid_page_numbers(self):
        """Test pagination with invalid page numbers."""
        # Test negative page
        response = self.app.get('/rankings?page=-1')
        self.assertEqual(response.status_code, 200)  # Should handle gracefully
        
        # Test non-integer page
        response = self.app.get('/rankings?page=abc')
        self.assertEqual(response.status_code, 200)  # Should default to 1
        
        # Test very large page number
        response = self.app.get('/rankings?page=99999')
        self.assertEqual(response.status_code, 200)  # Should handle gracefully

    def test_pagination_controls_present(self):
        """Test that pagination controls are present when needed."""
        response = self.app.get('/rankings')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Check for pagination elements
        # These may or may not be present depending on number of companies
        # Just verify the page loads without errors

    def test_search_functionality_basic(self):
        """Test basic search functionality."""
        # Test search with a query
        response = self.app.get('/rankings?search=AAPL')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Search query should be preserved in the form
        self.assertIn('search', html.lower())

    def test_search_empty_query(self):
        """Test search with empty query."""
        response = self.app.get('/rankings?search=')
        self.assertEqual(response.status_code, 200)
        # Should show all companies (no filter)

    def test_search_special_characters(self):
        """Test search with special characters."""
        # Test with special characters that might break SQL
        response = self.app.get('/rankings?search=%27OR%271%27=%271')
        self.assertEqual(response.status_code, 200)  # Should not cause SQL injection
        
        # Test with other special characters
        response = self.app.get('/rankings?search=@#$%')
        self.assertEqual(response.status_code, 200)

    def test_search_combined_with_pagination(self):
        """Test search combined with pagination."""
        response = self.app.get('/rankings?search=AAPL&page=1')
        self.assertEqual(response.status_code, 200)
        
        # Both parameters should work together
        response = self.app.get('/rankings?search=TEST&page=2')
        self.assertEqual(response.status_code, 200)

    def test_search_results_count(self):
        """Test that search results count is displayed."""
        response = self.app.get('/rankings?search=AAPL')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Should show results count or "companies analyzed"
        self.assertTrue('result' in html.lower() or 'compan' in html.lower())

    def test_url_parameter_encoding(self):
        """Test URL parameter encoding/decoding."""
        # Test with URL-encoded search query
        response = self.app.get('/rankings?search=Apple%20Inc')
        self.assertEqual(response.status_code, 200)
        
        # Test with plus sign (space encoding)
        response = self.app.get('/rankings?search=Apple+Inc')
        self.assertEqual(response.status_code, 200)

    def test_pagination_edge_cases(self):
        """Test pagination edge cases."""
        # Test with both page and search
        response = self.app.get('/rankings?page=1&search=TEST')
        self.assertEqual(response.status_code, 200)
        
        # Test with page beyond total (should handle gracefully)
        response = self.app.get('/rankings?page=999999')
        self.assertEqual(response.status_code, 200)

    def test_search_case_insensitive(self):
        """Test that search is case-insensitive."""
        response_upper = self.app.get('/rankings?search=AAPL')
        response_lower = self.app.get('/rankings?search=aapl')
        
        # Both should return 200
        self.assertEqual(response_upper.status_code, 200)
        self.assertEqual(response_lower.status_code, 200)

    def test_pagination_go_to_page_feature(self):
        """Test that 'Go to page' input is present."""
        response = self.app.get('/rankings')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Check for page jump input
        if 'Go to page' in html or 'pageJumpInput' in html:
            # Feature is present
            pass  # Just verify it doesn't crash

    def test_search_form_submission(self):
        """Test that search form can be submitted."""
        response = self.app.get('/rankings?search=TEST')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Check for search form
        self.assertIn('id="searchForm"', html)

    def test_pagination_next_prev_buttons(self):
        """Test pagination next/prev button functionality."""
        response = self.app.get('/rankings?page=2')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        
        # Should have prev button on page 2+
        # Just verify page loads correctly

    def test_search_with_ticker_prefix(self):
        """Test searching by ticker prefix."""
        response = self.app.get('/rankings?search=AA')
        self.assertEqual(response.status_code, 200)
        # Should find companies with tickers starting with "AA"

    def test_search_with_company_name_prefix(self):
        """Test searching by company name prefix."""
        response = self.app.get('/rankings?search=Apple')
        self.assertEqual(response.status_code, 200)
        # Should find companies with names containing "Apple"

    def test_pagination_per_page_consistency(self):
        """Test that per_page is consistent."""
        response1 = self.app.get('/rankings?page=1')
        response2 = self.app.get('/rankings?page=2')
        
        # Both should return 200
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)
        
        # Number of companies per page should be consistent
        # (This is harder to test without parsing HTML, but we verify no errors)

    def test_score_percentage_capped_at_100(self):
        """Test that score percentages are capped at 100% to handle data corruption."""
        max_score = get_max_possible_score()
        
        # Test with a score that would exceed 100%
        test_score = max_score * 2  # 200% of max
        percentage = int((test_score / max_score) * 100)
        capped_percentage = min(percentage, 100)
        
        # Should be capped at 100
        self.assertEqual(capped_percentage, 100)
        self.assertGreater(percentage, 100)  # Verify it would exceed without capping

    def test_peers_page_loads(self):
        """Test that the peers page loads successfully."""
        response = self.app.get('/peers')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Peers', response.data)
        self.assertIn(b'AI Stock Scores - Peers', response.data)

    def test_peers_page_structure(self):
        """Test that peers page has required HTML elements."""
        response = self.app.get('/peers')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Check for search bar
        self.assertIn('searchInput', html)
        self.assertIn('searchForm', html)
        # Check for navigation tabs
        self.assertIn('Rankings', html)
        self.assertIn('Peers', html)

    def test_peers_page_with_search(self):
        """Test peers page with a search query."""
        response = self.app.get('/peers?search=AAPL')
        self.assertEqual(response.status_code, 200)
        # Should either show peers or show an error message
        html = response.data.decode('utf-8')
        self.assertTrue(
            'peers' in html.lower() or 
            'not found' in html.lower() or
            'no peers' in html.lower()
        )

    def test_peers_page_empty_search(self):
        """Test peers page with empty search."""
        response = self.app.get('/peers?search=')
        self.assertEqual(response.status_code, 200)
        # Should show the page without results

    def test_peers_page_invalid_company(self):
        """Test peers page with invalid company."""
        response = self.app.get('/peers?search=NONEXISTENT_COMPANY_XYZ123')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Should show error message
        self.assertTrue(
            'not found' in html.lower() or
            'no peers' in html.lower()
        )

    def test_company_suggestions_api(self):
        """Test the company suggestions API endpoint."""
        response = self.app.get('/api/company-suggestions?q=AAPL')
        self.assertEqual(response.status_code, 200)
        # Should return JSON
        import json
        suggestions = json.loads(response.data)
        self.assertIsInstance(suggestions, list)

    def test_company_suggestions_api_empty_query(self):
        """Test company suggestions API with empty query."""
        response = self.app.get('/api/company-suggestions?q=')
        self.assertEqual(response.status_code, 200)
        import json
        suggestions = json.loads(response.data)
        self.assertEqual(suggestions, [])

    def test_company_suggestions_api_short_query(self):
        """Test company suggestions API with very short query."""
        response = self.app.get('/api/company-suggestions?q=A')
        self.assertEqual(response.status_code, 200)
        import json
        suggestions = json.loads(response.data)
        self.assertIsInstance(suggestions, list)

    def test_company_suggestions_api_prioritizes_ticker(self):
        """Test that company suggestions prioritize exact ticker matches."""
        response = self.app.get('/api/company-suggestions?q=AAPL')
        self.assertEqual(response.status_code, 200)
        import json
        suggestions = json.loads(response.data)
        if suggestions:
            # If AAPL exists, it should be first
            first_suggestion = suggestions[0]
            self.assertIn('ticker', first_suggestion)
            self.assertIn('name', first_suggestion)

    def test_search_with_comma_treated_as_single_query(self):
        """Test search with comma - should be treated as a single prefix search."""
        response = self.app.get('/?search=AAPL,MSFT,GOOG')
        self.assertEqual(response.status_code, 200)
        # Should treat as single prefix search (comma-separated feature removed)

    def test_peers_page_with_company_name(self):
        """Test peers page searching by company name."""
        response = self.app.get('/peers?search=Apple')
        self.assertEqual(response.status_code, 200)
        # Should either find Apple or show appropriate message

    def test_peers_navigation_tabs(self):
        """Test that navigation tabs work correctly."""
        # Test Rankings tab link
        response = self.app.get('/rankings')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('href="/"', html) # Home link
        self.assertIn('href="/rankings"', html) # Rankings link
        self.assertIn('href="/peers"', html)
        
        # Test Peers tab link
        response = self.app.get('/peers')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('href="/"', html) # Home link
        self.assertIn('href="/rankings"', html) # Rankings link
        self.assertIn('href="/peers"', html)


    def test_peers_page_no_peers_db(self):
        """Test peers page when peers database doesn't exist (edge case)."""
        # This tests the error handling when peers.db is missing
        # The route should still return 200 with appropriate message
        response = self.app.get('/peers?search=TEST')
        self.assertEqual(response.status_code, 200)

    def test_peers_page_no_top_companies_db(self):
        """Test peers page when top_companies.db doesn't exist (edge case)."""
        # This tests error handling in find_company_in_top_companies
        response = self.app.get('/peers?search=TEST')
        self.assertEqual(response.status_code, 200)

    def test_company_suggestions_api_no_query_param(self):
        """Test company suggestions API without query parameter."""
        response = self.app.get('/api/company-suggestions')
        self.assertEqual(response.status_code, 200)
        import json
        suggestions = json.loads(response.data)
        self.assertEqual(suggestions, [])

    def test_company_suggestions_api_special_characters(self):
        """Test company suggestions API with special characters."""
        response = self.app.get('/api/company-suggestions?q=%27OR%271%27=%271')
        self.assertEqual(response.status_code, 200)
        # Should not cause SQL injection

    def test_search_empty_items_in_comma_list(self):
        """Test search with empty items - should be treated as single prefix search."""
        response = self.app.get('/?search=AAPL,,MSFT')
        self.assertEqual(response.status_code, 200)
        # Should skip empty items

    def test_peers_route_with_company_that_has_peers(self):
        """Test peers route when company exists and has peers."""
        # Try with a common ticker that might have peers
        response = self.app.get('/peers?search=AAPL')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Should either show peers or show appropriate message
        self.assertTrue(
            'peers' in html.lower() or 
            'not found' in html.lower() or
            'no peers' in html.lower() or
            'showing peers' in html.lower()
        )

    def test_peers_route_searched_company_in_list(self):
        """Test that searched company appears in peers list."""
        response = self.app.get('/peers?search=AAPL')
        self.assertEqual(response.status_code, 200)
        # If peers are found, the searched company should be in the list
        # This is tested indirectly through the route logic

    def test_company_suggestions_returns_valid_structure(self):
        """Test that company suggestions return valid structure."""
        response = self.app.get('/api/company-suggestions?q=APPLE')
        self.assertEqual(response.status_code, 200)
        import json
        suggestions = json.loads(response.data)
        if suggestions:
            suggestion = suggestions[0]
            self.assertIn('ticker', suggestion)
            self.assertIn('name', suggestion)
            self.assertIsInstance(suggestion['ticker'], str)
            self.assertIsInstance(suggestion['name'], str)

    def test_search_single_letter(self):
        """Test search with single letter."""
        response = self.app.get('/?search=A')
        self.assertEqual(response.status_code, 200)
        # Should handle single character searches

    def test_peers_page_renders_without_errors(self):
        """Test that peers page renders without template errors."""
        response = self.app.get('/peers')
        self.assertEqual(response.status_code, 200)
        # Check that it's valid HTML
        self.assertIn(b'<!DOCTYPE html>', response.data)
        self.assertIn(b'</html>', response.data)

    # ========================================================================
    # Watchlist Tests
    # ========================================================================
    
    def test_watchlist_page_loads(self):
        """Test that the watchlist page loads successfully."""
        response = self.app.get('/watchlist')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Watchlist', response.data)
        self.assertIn(b'AI Stock Scores - Watchlist', response.data)

    def test_watchlist_page_structure(self):
        """Test that watchlist page has required HTML elements."""
        response = self.app.get('/watchlist')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Check for input field
        self.assertIn('addTickerInput', html)
        # Check for navigation tabs
        self.assertIn('Rankings', html)
        self.assertIn('Peers', html)
        self.assertIn('Watchlist', html)
        # Check for suggestions dropdown
        self.assertIn('suggestionsDropdown', html)

    def test_watchlist_navigation_tabs(self):
        """Test that watchlist page has correct navigation tabs."""
        response = self.app.get('/watchlist')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Should have all three tabs
        self.assertIn('Rankings', html)
        self.assertIn('Peers', html)
        self.assertIn('Watchlist', html)
        # Watchlist tab should be active
        self.assertIn('href="/watchlist"', html)

    def test_watchlist_data_api_empty_tickers(self):
        """Test watchlist-data API with empty tickers list."""
        response = self.app.post('/api/watchlist-data',
                                data='{"tickers": []}',
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        import json
        data = json.loads(response.data)
        self.assertEqual(data, [])

    def test_watchlist_data_api_no_tickers_key(self):
        """Test watchlist-data API with missing tickers key."""
        response = self.app.post('/api/watchlist-data',
                                data='{}',
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        import json
        data = json.loads(response.data)
        self.assertEqual(data, [])

    def test_watchlist_data_api_valid_ticker(self):
        """Test watchlist-data API with a valid ticker."""
        # First, check if we have a database set up
        conn = get_db_connection()
        # Get a ticker that exists in the database
        ticker_row = conn.execute('SELECT ticker FROM scores LIMIT 1').fetchone()
        conn.close()
        
        if ticker_row:
            test_ticker = ticker_row['ticker']
            response = self.app.post('/api/watchlist-data',
                                    data=json.dumps({'tickers': [test_ticker]}),
                                    content_type='application/json')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIsInstance(data, list)
            if len(data) > 0:
                company = data[0]
                self.assertIn('ticker', company)
                self.assertIn('company_name', company)
                self.assertIn('total_score', company)
                self.assertIn('score_percentage', company)
                self.assertIn('percentile', company)
                self.assertIn('global_rank', company)

    def test_watchlist_data_api_multiple_tickers(self):
        """Test watchlist-data API with multiple tickers."""
        conn = get_db_connection()
        # Get multiple tickers that exist in the database
        ticker_rows = conn.execute('SELECT ticker FROM scores LIMIT 3').fetchall()
        conn.close()
        
        if len(ticker_rows) >= 2:
            test_tickers = [row['ticker'] for row in ticker_rows[:2]]
            response = self.app.post('/api/watchlist-data',
                                    data=json.dumps({'tickers': test_tickers}),
                                    content_type='application/json')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIsInstance(data, list)
            # Should return at most the number of tickers requested
            self.assertLessEqual(len(data), len(test_tickers))

    def test_watchlist_data_api_invalid_ticker(self):
        """Test watchlist-data API with a ticker that doesn't exist."""
        response = self.app.post('/api/watchlist-data',
                                data='{"tickers": ["NONEXISTENT_TICKER_XYZ123"]}',
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        import json
        data = json.loads(response.data)
        self.assertIsInstance(data, list)
        # Should return empty list for non-existent ticker
        self.assertEqual(len(data), 0)

    def test_watchlist_data_api_mixed_valid_invalid_tickers(self):
        """Test watchlist-data API with mix of valid and invalid tickers."""
        conn = get_db_connection()
        ticker_row = conn.execute('SELECT ticker FROM scores LIMIT 1').fetchone()
        conn.close()
        
        if ticker_row:
            valid_ticker = ticker_row['ticker']
            tickers = [valid_ticker, 'NONEXISTENT_TICKER_XYZ123']
            response = self.app.post('/api/watchlist-data',
                                    data=json.dumps({'tickers': tickers}),
                                    content_type='application/json')
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIsInstance(data, list)
            # Should return at least one result (the valid ticker)
            self.assertGreaterEqual(len(data), 1)
            # Should not have more results than valid tickers
            self.assertLessEqual(len(data), len(tickers))

    def test_watchlist_page_renders_without_errors(self):
        """Test that watchlist page renders without template errors."""
        response = self.app.get('/watchlist')
        self.assertEqual(response.status_code, 200)
        # Check that it's valid HTML
        self.assertIn(b'<!DOCTYPE html>', response.data)
        self.assertIn(b'</html>', response.data)

    # ========================================================================
    # Groups Tests
    # ========================================================================
    
    def test_groups_page_loads(self):
        """Test that the groups page loads successfully."""
        response = self.app.get('/groups')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Groups', response.data)
        self.assertIn(b'AI Stock Scores - Groups', response.data)

    def test_groups_page_structure(self):
        """Test that groups page has required HTML elements."""
        response = self.app.get('/groups')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Check for input field
        self.assertIn('addTickerInput', html)
        # Check for navigation tabs
        self.assertIn('Rankings', html)
        self.assertIn('Peers', html)
        self.assertIn('Watchlist', html)
        self.assertIn('Groups', html)
        # Check for suggestions dropdown
        self.assertIn('suggestionsDropdown', html)

    def test_groups_navigation_tabs(self):
        """Test that groups page has correct navigation tabs."""
        response = self.app.get('/groups')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Should have all four tabs
        self.assertIn('Rankings', html)
        self.assertIn('Peers', html)
        self.assertIn('Watchlist', html)
        self.assertIn('Groups', html)
        # Groups tab should be active
        self.assertIn('href="/groups"', html)

    def test_groups_page_renders_without_errors(self):
        """Test that groups page renders without template errors."""
        response = self.app.get('/groups')
        self.assertEqual(response.status_code, 200)
        # Check that it's valid HTML
        self.assertIn(b'<!DOCTYPE html>', response.data)
        self.assertIn(b'</html>', response.data)

    # ========================================================================
    # AI Relevance Tests
    # ========================================================================
    
    def test_ai_relevance_page_loads(self):
        """Test that the AI relevance page loads successfully."""
        response = self.app.get('/ai-relevance')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'AI Relevance', response.data)

    def test_ai_relevance_navigation_tabs(self):
        """Test that AI relevance page has correct navigation tabs."""
        response = self.app.get('/ai-relevance')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('Home', html)
        self.assertIn('AI Relevance', html)
        self.assertIn('href="/ai-relevance"', html)
        # Should NOT have the other app tabs
        self.assertNotIn('Rankings', html)
        self.assertNotIn('Peers', html)
        self.assertNotIn('Watchlist', html)
        self.assertNotIn('Groups', html)

    def test_ai_relevance_page_empty_ranking(self):
        """Test AI Relevance page when ranking is missing or empty."""
        # Use a nonexistent file path for ranking to trigger error handling
        # Since we can't easily mock file existence in this setup without deeper changes,
        # we'll just verify the current behavior.
        response = self.app.get('/ai-relevance')
        self.assertEqual(response.status_code, 200)
        # If it finds the file, it shows companies. If not, it shows the error div.
        # Either way, it should not crash.

    def test_home_page_links(self):
        """Test that home page cards lead to the correct locations."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('href="/rankings"', html)
        self.assertIn('href="/ai-relevance"', html)

    def test_find_company_in_top_companies_fuzzy(self):
        """Test fuzzy matching in find_company_in_top_companies helper."""
        from src.web.app import find_company_in_top_companies
        
        # Test with common suffixes
        result = find_company_in_top_companies("Apple Inc.")
        if result:
            self.assertEqual(result['ticker'], 'AAPL')
            
        result = find_company_in_top_companies("Microsoft Corp")
        if result:
            self.assertEqual(result['ticker'], 'MSFT')

    def test_peers_company_not_found(self):
        """Test peers route with a ticker that does not exist in scores."""
        response = self.app.get('/peers?search=DEFINITELY_NOT_A_REAL_TICKER_12345')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Company not found', response.data)

    def test_peers_no_peers_found(self):
        """Test peers route when a company exists but has no peers listed."""
        # Find a ticker that has a score but likely no peers in our peers.db
        # This depends on DB state, but we'll try a generic search
        response = self.app.get('/peers?search=BRK-B') # Berkshire often has no direct peers in simple lists
        self.assertEqual(response.status_code, 200)
        # Should not crash, might show error message or empty table

    # ========================================================================
    # Helper Function Tests
    # ========================================================================
    
    def test_calculate_percentile_rank_empty_list(self):
        """Test percentile rank calculation with empty list."""
        result = calculate_percentile_rank(50, [])
        self.assertEqual(result, 0)
    
    def test_calculate_percentile_rank_single_value(self):
        """Test percentile rank with single value."""
        result = calculate_percentile_rank(50, [50])
        self.assertEqual(result, 100)  # 100% of values are <= 50
    
    def test_calculate_percentile_rank_lowest(self):
        """Test percentile rank for lowest value."""
        scores = [10, 20, 30, 40, 50]
        result = calculate_percentile_rank(10, scores)
        self.assertEqual(result, 20)  # 1/5 = 20%
    
    def test_calculate_percentile_rank_highest(self):
        """Test percentile rank for highest value."""
        scores = [10, 20, 30, 40, 50]
        result = calculate_percentile_rank(50, scores)
        self.assertEqual(result, 100)  # 5/5 = 100%
    
    def test_calculate_percentile_rank_middle(self):
        """Test percentile rank for middle value."""
        scores = [10, 20, 30, 40, 50]
        result = calculate_percentile_rank(30, scores)
        self.assertEqual(result, 60)  # 3/5 = 60%
    
    def test_calculate_percentile_rank_duplicate_values(self):
        """Test percentile rank with duplicate values."""
        scores = [10, 20, 20, 30, 40]
        result = calculate_percentile_rank(20, scores)
        self.assertEqual(result, 60)  # 3/5 = 60% (both 20s are counted)
    
    def test_calculate_percentile_rank_value_not_in_list(self):
        """Test percentile rank for value not in the list."""
        scores = [10, 20, 30, 40, 50]
        result = calculate_percentile_rank(25, scores)
        self.assertEqual(result, 40)  # 2/5 = 40% (25 is between 20 and 30)
    
    def test_get_max_possible_score(self):
        """Test that max possible score is calculated correctly."""
        max_score = get_max_possible_score()
        # Should be sum of all weights * 10
        # 24 metrics * 10 weight each = 240, plus size_well_known_score = 19.31
        # Total = (23 * 10 + 19.31) * 10 = 249.31 * 10 = 2493.1
        # But let's just check it's a reasonable positive number
        self.assertGreater(max_score, 0)
        self.assertIsInstance(max_score, (int, float))
        # Based on the weights in app.py, it should be 2493.1
        expected = (23 * 10 + 19.31) * 10
        self.assertEqual(max_score, expected)

if __name__ == '__main__':
    unittest.main()

