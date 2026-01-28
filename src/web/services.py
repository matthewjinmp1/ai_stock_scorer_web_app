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
    def get_ranked_companies(cls, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        # Fetch companies (filtered if search query provided)
        companies = CompanyRepository.get_latest_scores(search_query)
        
        # Fetch all scores for percentile calculation (needed regardless of search)
        all_scores = CompanyRepository.get_all_latest_scores_only()
        max_possible = get_max_possible_score()
        
        # Calculate global ranks efficiently
        if search_query:
            # For search, we need all companies to calculate accurate global ranks
            # But we can optimize: only fetch once and reuse
            all_companies_for_rank = CompanyRepository.get_latest_scores()
            global_ranks = {c['ticker']: i for i, c in enumerate(all_companies_for_rank, 1)}
        else:
            # For no search, companies are already sorted by score, so rank = index + 1
            global_ranks = {c['ticker']: i for i, c in enumerate(companies, 1)}
        
        # Process results in a single pass
        results = []
        for i, company in enumerate(companies):
            total_score = float(company.get('total_score', 0))
            company['score_percentage'] = min(int((total_score / max_possible) * 100), 100) if max_possible > 0 else 0
            company['percentile'] = cls.calculate_percentile(total_score, all_scores)
            company['global_rank'] = global_ranks.get(company['ticker'], i + 1)
            results.append(company)
            
        return results

    @classmethod
    def get_custom_rankings(cls, selected_metrics: List[str], search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        # For custom, we calculate for ALL companies to get correct ranks/percentiles
        all_companies = CompanyRepository.get_latest_scores()
        max_possible = get_max_possible_score(selected_metrics)
        
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
            
        # Filter if search query present
        if search_query:
            search_upper = search_query.strip().upper()
            filtered = [
                c for c in scored_companies 
                if search_upper == c['ticker'].upper() or search_upper in c['ticker'].upper() or search_upper in (c['company_name'] or '').upper()
            ]
            # Prioritize exact ticker matches
            filtered.sort(key=lambda x: 0 if x['ticker'].upper() == search_upper else 1)
            return filtered
            
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
