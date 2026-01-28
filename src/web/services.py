from typing import List, Dict, Any, Optional
from src.core.repository import CompanyRepository
from src.core.metrics import calculate_total_weighted_score, get_max_possible_score, METRIC_DEFINITIONS
import bisect

class ScoringService:
    """Service for handling scoring logic and rankings."""
    
    @staticmethod
    def calculate_percentile(score: float, sorted_scores: List[float]) -> int:
        if not sorted_scores:
            return 0
        count_less_or_equal = bisect.bisect_right(sorted_scores, score)
        return int((count_less_or_equal / len(sorted_scores)) * 100)

    @classmethod
    def get_ranked_companies(cls, search_query: Optional[str] = None, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get ranked companies with optional pagination.
        
        Args:
            search_query: Optional search filter
            limit: Optional limit for pagination
            offset: Optional offset for pagination
        """
        # Fetch all scores for percentile calculation first (cached, so fast)
        all_scores = CompanyRepository.get_all_latest_scores_only()
        max_possible = get_max_possible_score()
        
        # Fetch companies (filtered if search query provided, paginated if limit/offset provided)
        companies = CompanyRepository.get_latest_scores(search_query, limit=limit, offset=offset)
        
        # Calculate global ranks efficiently
        if search_query:
            # For search, we need all companies to calculate accurate global ranks
            # But only if we have a reasonable number of results
            if len(companies) < 1000:  # Only fetch all if search returned few results
                all_companies_for_rank = CompanyRepository.get_latest_scores(search_query)
                global_ranks = {c['ticker']: i for i, c in enumerate(all_companies_for_rank, 1)}
            else:
                # For large result sets, use offset-based rank estimation
                global_ranks = {}
        else:
            # For no search with pagination, calculate rank from offset
            if offset is not None:
                global_ranks = {c['ticker']: offset + i + 1 for i, c in enumerate(companies)}
            else:
                # No pagination, need all for accurate ranks
                all_companies_for_rank = CompanyRepository.get_latest_scores()
                global_ranks = {c['ticker']: i for i, c in enumerate(all_companies_for_rank, 1)}
        
        # Process results in a single pass
        results = []
        for i, company in enumerate(companies):
            total_score = float(company.get('total_score', 0))
            company['score_percentage'] = min(int((total_score / max_possible) * 100), 100) if max_possible > 0 else 0
            company['percentile'] = cls.calculate_percentile(total_score, all_scores)
            company['global_rank'] = global_ranks.get(company['ticker'], (offset or 0) + i + 1)
            results.append(company)
            
        return results

    @classmethod
    def get_custom_rankings(cls, selected_metrics: List[str], search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        # For custom, we need to calculate for ALL companies to get correct ranks/percentiles
        # But we can optimize by doing database-level filtering if search is provided
        if search_query:
            # Use database search to reduce the dataset before processing
            all_companies = CompanyRepository.get_latest_scores(search_query)
        else:
            # No search - need all companies for accurate ranking
            all_companies = CompanyRepository.get_latest_scores()
        
        max_possible = get_max_possible_score(selected_metrics)
        
        # Calculate custom scores - this is the expensive part, but necessary
        scored_companies = []
        for company in all_companies:
            custom_total = calculate_total_weighted_score(company, selected_metrics)
            company['custom_total_score'] = custom_total
            company['score_percentage'] = min(int((custom_total / max_possible) * 100), 100) if max_possible > 0 else 0
            scored_companies.append(company)
            
        # Sort by custom score
        scored_companies.sort(key=lambda x: x['custom_total_score'], reverse=True)
        
        # Add ranks and percentiles
        all_custom_scores_sorted = sorted([c['custom_total_score'] for c in scored_companies])
        for i, company in enumerate(scored_companies, 1):
            company['global_rank'] = i
            company['percentile'] = cls.calculate_percentile(company['custom_total_score'], all_custom_scores_sorted)
        
        # If search was provided, prioritize exact ticker matches
        if search_query:
            search_upper = search_query.strip().upper()
            scored_companies.sort(key=lambda x: 0 if x['ticker'].upper() == search_upper else 1)
            
        return scored_companies

class CompanyService:
    """Service for company-specific data and details."""
    
    @classmethod
    def get_detail(cls, ticker: str, selected_metrics: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        company = CompanyRepository.get_company_detail(ticker)
        if not company:
            return None
            
        is_custom = selected_metrics is not None and len(selected_metrics) > 0
        
        if is_custom:
            total_score = calculate_total_weighted_score(company, selected_metrics)
            max_possible = get_max_possible_score(selected_metrics)
            company['total_score'] = total_score
            company['score_percentage'] = min(int((total_score / max_possible) * 100), 100) if max_possible > 0 else 0
            
            # Calculate custom percentile
            all_latest = CompanyRepository.get_latest_scores()
            all_custom_scores = sorted([calculate_total_weighted_score(dict(r), selected_metrics) for r in all_latest])
            company['percentile'] = ScoringService.calculate_percentile(total_score, all_custom_scores)
        else:
            total_score = float(company.get('total_score', 0))
            max_possible = get_max_possible_score()
            company['score_percentage'] = min(int((total_score / max_possible) * 100), 100) if max_possible > 0 else 0
            
            all_scores = CompanyRepository.get_all_latest_scores_only()
            company['percentile'] = ScoringService.calculate_percentile(total_score, all_scores)
            
        company['history'] = CompanyRepository.get_company_history(ticker)
        company['peers'] = CompanyRepository.get_peers(ticker)
        
        return company
