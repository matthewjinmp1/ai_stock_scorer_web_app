from typing import List, Dict, Any, Optional
from src.core.repository import CompanyRepository
from src.core.metrics import calculate_total_weighted_score, get_max_possible_score, METRIC_DEFINITIONS
import bisect
import hashlib
import threading

class ScoringService:
    # Cache for custom rankings (keyed by metrics hash + search query)
    _custom_rankings_cache = {}
    _cache_lock = threading.Lock()
    # Cache for baseline rankings (all-metric score, global ranks, percentiles)
    _baseline_companies = None
    _baseline_by_ticker = None
    _baseline_lock = threading.Lock()
    
    @classmethod
    def _get_cache_key(cls, selected_metrics: List[str], search_query: Optional[str]) -> str:
        """Generate cache key from metrics and search query."""
        metrics_str = ','.join(sorted(selected_metrics))
        search_str = search_query or ''
        cache_input = f"{metrics_str}|{search_str}"
        return hashlib.md5(cache_input.encode()).hexdigest()
    
    @classmethod
    def _clear_custom_cache(cls):
        """Clear custom rankings cache. Useful for testing."""
        with cls._cache_lock:
            cls._custom_rankings_cache.clear()
    """Service for handling scoring logic and rankings."""
    
    @staticmethod
    def calculate_percentile(score: float, sorted_scores: List[float]) -> int:
        """Calculate percentile efficiently using binary search."""
        if not sorted_scores:
            return 0
        # Cache length to avoid repeated len() calls
        scores_len = len(sorted_scores)
        count_less_or_equal = bisect.bisect_right(sorted_scores, score)
        return int((count_less_or_equal / scores_len) * 100)

    @classmethod
    def get_baseline_rankings(cls) -> List[Dict[str, Any]]:
        """
        Return baseline rankings (all-metric total_score + score_percentage, percentile, global_rank).
        Uses precomputed baseline_rankings table when available; otherwise computes and caches in memory.
        """
        if CompanyRepository._has_baseline_rankings():
            return CompanyRepository.get_baseline_ranked_companies(None, limit=None, offset=None)
        if cls._baseline_companies is not None and cls._baseline_by_ticker is not None:
            return cls._baseline_companies
        with cls._baseline_lock:
            if cls._baseline_companies is not None and cls._baseline_by_ticker is not None:
                return cls._baseline_companies
            all_scores = CompanyRepository.get_all_latest_scores_only()
            max_possible = get_max_possible_score()
            all_companies = CompanyRepository.get_latest_scores()
            results: List[Dict[str, Any]] = []
            baseline_by_ticker: Dict[str, Dict[str, Any]] = {}
            for i, company in enumerate(all_companies, 1):
                total_score = float(company.get('total_score', 0))
                company['score_percentage'] = min(int((total_score / max_possible) * 100), 100) if max_possible > 0 else 0
                company['percentile'] = cls.calculate_percentile(total_score, all_scores)
                company['global_rank'] = i
                results.append(company)
                baseline_by_ticker[company['ticker'].upper()] = company
            cls._baseline_companies = results
            cls._baseline_by_ticker = baseline_by_ticker
            return results

    @classmethod
    def get_baseline_for_tickers(cls, tickers: List[str]) -> List[Dict[str, Any]]:
        """Get baseline data for a list of tickers. Uses DB when baseline_rankings exists."""
        if not tickers:
            return []
        if CompanyRepository._has_baseline_rankings():
            return CompanyRepository.get_baseline_for_tickers(tickers)
        cls.get_baseline_rankings()
        results: List[Dict[str, Any]] = []
        for t in tickers:
            entry = cls._baseline_by_ticker.get(t.upper()) if cls._baseline_by_ticker else None
            if entry:
                results.append(entry)
        results.sort(key=lambda x: x.get('global_rank', 0))
        return results

    @classmethod
    def get_ranked_companies(cls, search_query: Optional[str] = None, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get ranked companies with optional pagination.
        Uses precomputed baseline_rankings when available; otherwise computes on the fly.
        """
        if CompanyRepository._has_baseline_rankings():
            return CompanyRepository.get_baseline_ranked_companies(search_query, limit=limit, offset=offset)
        # Fallback: compute from scores
        all_scores = CompanyRepository.get_all_latest_scores_only()
        max_possible = get_max_possible_score()
        companies = CompanyRepository.get_latest_scores(search_query, limit=limit, offset=offset)
        if search_query:
            if len(companies) < 1000:
                all_companies_for_rank = CompanyRepository.get_latest_scores(search_query)
                global_ranks = {c['ticker']: i for i, c in enumerate(all_companies_for_rank, 1)}
            else:
                global_ranks = {}
        else:
            if offset is not None:
                global_ranks = {c['ticker']: offset + i + 1 for i, c in enumerate(companies)}
            else:
                all_companies_for_rank = CompanyRepository.get_latest_scores()
                global_ranks = {c['ticker']: i for i, c in enumerate(all_companies_for_rank, 1)}
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
        # Check cache first (only for non-search queries to keep cache simple)
        cache_key = cls._get_cache_key(selected_metrics, search_query)
        if not search_query:  # Only cache non-search results
            with cls._cache_lock:
                if cache_key in cls._custom_rankings_cache:
                    # Return cached copy (don't modify original)
                    import copy
                    return copy.deepcopy(cls._custom_rankings_cache[cache_key])
        
        # For custom, we need to calculate for ALL companies to get correct ranks/percentiles
        # But we can optimize by doing database-level filtering if search is provided
        if search_query:
            # Use database search to reduce the dataset before processing
            all_companies = CompanyRepository.get_latest_scores(search_query)
        else:
            # No search - need all companies for accurate ranking
            all_companies = CompanyRepository.get_latest_scores()
        
        max_possible = get_max_possible_score(selected_metrics)
        
        # Optimize: Pre-compute metric definitions and weights to avoid repeated dict access
        metric_configs = []
        for key in selected_metrics:
            if key in METRIC_DEFINITIONS:
                m_def = METRIC_DEFINITIONS[key]
                metric_configs.append((key, m_def['weight'], m_def['max_val'], m_def['is_reverse']))
        
        # Calculate custom scores - optimized loop with pre-computed configs
        # Use list comprehension for faster processing
        scored_companies = []
        max_possible_inv = 1.0 / max_possible if max_possible > 0 else 0.0
        
        for company in all_companies:
            # Fast path: direct calculation with pre-computed configs
            custom_total = 0.0
            for key, weight, max_val, is_reverse in metric_configs:
                val = company.get(key)
                if val is None or val == 'N/A':
                    continue
                # Try to convert to float - use isinstance check for speed
                if isinstance(val, (int, float)):
                    score_value = float(val)
                else:
                    try:
                        score_value = float(val)
                    except (ValueError, TypeError):
                        continue
                # Direct calculation - avoid dict lookups
                if is_reverse:
                    custom_total += (max_val - score_value) * weight
                else:
                    custom_total += score_value * weight
            
            company['custom_total_score'] = custom_total
            # Optimize percentage calculation
            company['score_percentage'] = min(int(custom_total * max_possible_inv * 100), 100)
            scored_companies.append(company)
            
        # Sort by custom score (use key function for efficiency)
        scored_companies.sort(key=lambda x: x['custom_total_score'], reverse=True)
        
        # Add ranks and percentiles - optimize by computing sorted scores once and reusing
        all_custom_scores_sorted = sorted([c['custom_total_score'] for c in scored_companies])
        # Batch process percentiles
        for i, company in enumerate(scored_companies, 1):
            company['global_rank'] = i
            company['percentile'] = cls.calculate_percentile(company['custom_total_score'], all_custom_scores_sorted)
        
        # If search was provided, prioritize exact ticker matches
        if search_query:
            search_upper = search_query.strip().upper()
            scored_companies.sort(key=lambda x: 0 if x['ticker'].upper() == search_upper else 1)
        
        # Cache result (only for non-search to keep cache manageable)
        if not search_query:
            with cls._cache_lock:
                # Limit cache size to prevent memory issues
                if len(cls._custom_rankings_cache) > 10:
                    # Remove oldest entry (simple FIFO)
                    oldest_key = next(iter(cls._custom_rankings_cache))
                    del cls._custom_rankings_cache[oldest_key]
                cls._custom_rankings_cache[cache_key] = scored_companies
            
        return scored_companies

class CompanyService:
    """Service for company-specific data and details."""
    
    @classmethod
    def get_detail(cls, ticker: str, selected_metrics: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        is_custom = selected_metrics is not None and len(selected_metrics) > 0
        if is_custom:
            company = CompanyRepository.get_company_detail(ticker)
            if not company:
                return None
            total_score = calculate_total_weighted_score(company, selected_metrics)
            max_possible = get_max_possible_score(selected_metrics)
            company['total_score'] = total_score
            company['score_percentage'] = min(int((total_score / max_possible) * 100), 100) if max_possible > 0 else 0
            all_latest = CompanyRepository.get_latest_scores()
            all_custom_scores = sorted([calculate_total_weighted_score(dict(r), selected_metrics) for r in all_latest])
            company['percentile'] = ScoringService.calculate_percentile(total_score, all_custom_scores)
        else:
            company = CompanyRepository.get_baseline_company_detail(ticker) or CompanyRepository.get_company_detail(ticker)
            if not company:
                return None
            # Baseline rows already have score_percentage, percentile, global_rank
            if 'global_rank' not in company:
                total_score = float(company.get('total_score', 0))
                max_possible = get_max_possible_score()
                company['score_percentage'] = min(int((total_score / max_possible) * 100), 100) if max_possible > 0 else 0
                all_scores = CompanyRepository.get_all_latest_scores_only()
                company['percentile'] = ScoringService.calculate_percentile(total_score, all_scores)
        company['history'] = CompanyRepository.get_company_history(ticker)
        company['peers'] = CompanyRepository.get_peers(ticker)
        return company
