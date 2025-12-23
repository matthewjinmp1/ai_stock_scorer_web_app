import sqlite3
import os
import math
import statistics

# Define the project root relative to this script
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
SCORES_DB = os.path.join(PROJECT_ROOT, "data", "scores.db")
TOP_500_DB = os.path.join(PROJECT_ROOT, "web_app", "top_500_scores.db")

METRICS = [
    'moat_score', 'barriers_score', 'disruption_risk', 'switching_cost',
    'brand_strength', 'competition_intensity', 'network_effect',
    'product_differentiation', 'innovativeness_score', 'growth_opportunity',
    'riskiness_score', 'pricing_power', 'ambition_score',
    'bargaining_power_of_customers', 'bargaining_power_of_suppliers',
    'product_quality_score', 'culture_employee_satisfaction_score',
    'trailblazer_score', 'management_quality_score', 'ai_knowledge_score',
    'size_well_known_score', 'ethical_healthy_environmental_score',
    'long_term_orientation_score'
]

def calculate_pearson(x, y):
    if len(x) != len(y) or len(x) == 0:
        return 0
    
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    
    num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    den_x = sum((x[i] - mean_x)**2 for i in range(n))
    den_y = sum((y[i] - mean_y)**2 for i in range(n))
    
    if den_x == 0 or den_y == 0:
        return 0
        
    return num / math.sqrt(den_x * den_y)

def calculate_stats(values):
    """Calculate mean, median, and stdev for a list of values."""
    if not values:
        return 0, 0, 0
    
    mean = sum(values) / len(values)
    median = statistics.median(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0
    return mean, median, stdev

def get_latest_data(db_path, model_condition):
    if not os.path.exists(db_path):
        return {}
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Select ticker, total_score, and all individual metrics
        metrics_cols = ", ".join(METRICS)
        query = f"""
            SELECT ticker, total_score, {metrics_cols}, timestamp 
            FROM scores s1
            WHERE {model_condition}
            AND timestamp = (
                SELECT MAX(timestamp) 
                FROM scores s2 
                WHERE s2.ticker = s1.ticker 
                AND {model_condition}
            )
        """
        cursor.execute(query)
        data = {row['ticker']: dict(row) for row in cursor.fetchall()}
        conn.close()
        return data
    except Exception as e:
        print(f"Error reading {db_path}: {e}")
        return {}

def calculate_percentile_ranks(data_dict):
    if not data_dict:
        return {}
    
    all_totals = [row['total_score'] for row in data_dict.values() if row['total_score'] is not None]
    if not all_totals:
        return {}

    sorted_scores = sorted(all_totals)
    n = len(sorted_scores)
    
    percentiles = {}
    for ticker, row in data_dict.items():
        score = row['total_score']
        if score is None:
            continue
        # Count scores <= current score
        count = sum(1 for s in sorted_scores if s <= score)
        percentiles[ticker] = (count / n) * 100
        
    return percentiles

def analyze_cross_db_correlation():
    print("Cross-Database Correlation Analysis")
    print("=" * 60)
    
    # Get all Grok data from scores.db
    grok_condition = "model = 'grok-4-1-fast-reasoning'"
    grok_all_data = get_latest_data(SCORES_DB, grok_condition)
    print(f"Loaded {len(grok_all_data)} Grok records from {os.path.basename(SCORES_DB)}")
    
    # Get all Mimo data from top_500_scores.db
    mimo_condition = "model IN ('xiaomi/mimo-v2-flash', 'xiaomimimo/mimo-v2-flash', 'xiaomi/mimo-v2-flash:free')"
    mimo_all_data = get_latest_data(TOP_500_DB, mimo_condition)
    print(f"Loaded {len(mimo_all_data)} Mimo records from {os.path.basename(TOP_500_DB)}")
    
    # Calculate Percentiles for ALL companies in each DB (based on total_score)
    grok_percentiles = calculate_percentile_ranks(grok_all_data)
    mimo_percentiles = calculate_percentile_ranks(mimo_all_data)
    
    # Find common tickers
    common_tickers = sorted(list(set(grok_all_data.keys()) & set(mimo_all_data.keys())))
    
    if not common_tickers:
        print("\nNo common tickers found between the two databases.")
        return

    print(f"\nFound {len(common_tickers)} common companies for correlation analysis.")
    print("-" * 60)

    # 1. Calculate Percentile Correlation (of total scores)
    x_perc = [grok_percentiles.get(t, 0) for t in common_tickers if t in grok_percentiles and t in mimo_percentiles]
    y_perc = [mimo_percentiles.get(t, 0) for t in common_tickers if t in grok_percentiles and t in mimo_percentiles]
    perc_correlation = calculate_pearson(x_perc, y_perc)
    
    # 2. Calculate Total Score Correlation
    x_total = [grok_all_data[t]['total_score'] for t in common_tickers if grok_all_data[t]['total_score'] is not None and mimo_all_data[t]['total_score'] is not None]
    y_total = [mimo_all_data[t]['total_score'] for t in common_tickers if grok_all_data[t]['total_score'] is not None and mimo_all_data[t]['total_score'] is not None]
    total_correlation = calculate_pearson(x_total, y_total)

    print(f"Percentile Rank Correlation: {perc_correlation:.4f}")
    print(f"Total Score Correlation:     {total_correlation:.4f}")
    
    # 3. Calculate Global Metric Pair Correlation
    # This correlates every single (stock, metric) pair as a single dataset
    all_x_metrics = []
    all_y_metrics = []
    for metric in METRICS:
        for t in common_tickers:
            val_g = grok_all_data[t].get(metric)
            val_m = mimo_all_data[t].get(metric)
            if val_g is not None and val_m is not None:
                all_x_metrics.append(float(val_g))
                all_y_metrics.append(float(val_m))
    
    global_metric_correlation = calculate_pearson(all_x_metrics, all_y_metrics)
    print(f"Global Metric Correlation:   {global_metric_correlation:.4f} (Across all {len(all_x_metrics)} stock-metric pairs)")
    
    # 4. Show Stats per Metric
    print("\nMetric Statistics (Grok vs Mimo):")
    print(f"{'Metric':<35} | {'Grok (Mean/Med/SD)':<25} | {'Mimo (Mean/Med/SD)':<25}")
    print("-" * 90)
    
    for metric in METRICS:
        vals_g = []
        vals_m = []
        for t in common_tickers:
            vg = grok_all_data[t].get(metric)
            vm = mimo_all_data[t].get(metric)
            if vg is not None: vals_g.append(float(vg))
            if vm is not None: vals_m.append(float(vm))
            
        mean_g, med_g, sd_g = calculate_stats(vals_g)
        mean_m, med_m, sd_m = calculate_stats(vals_m)
        
        g_str = f"{mean_g:>4.1f} / {med_g:>4.1f} / {sd_g:>4.1f}"
        m_str = f"{mean_m:>4.1f} / {med_m:>4.1f} / {sd_m:>4.1f}"
        print(f"{metric:<35} | {g_str:<25} | {m_str:<25}")

    # Global Stats across ALL common stock-metric pairs
    global_mean_g, global_med_g, global_sd_g = calculate_stats(all_x_metrics)
    global_mean_m, global_med_m, global_sd_m = calculate_stats(all_y_metrics)
    
    print("-" * 90)
    g_global_str = f"{global_mean_g:>4.1f} / {global_med_g:>4.1f} / {global_sd_g:>4.1f}"
    m_global_str = f"{global_mean_m:>4.1f} / {global_med_m:>4.1f} / {global_sd_m:>4.1f}"
    print(f"{'ALL METRICS COMBINED':<35} | {g_global_str:<25} | {m_global_str:<25}")
    print("=" * 90)

    # 5. Calculate Individual Metric Correlations
    print("\nIndividual Metric Correlations:")
    print(f"{'Metric':<35} | {'Correlation':>12}")
    print("-" * 50)
    
    metric_correlations = []
    for metric in METRICS:
        x_metric = []
        y_metric = []
        for t in common_tickers:
            val_g = grok_all_data[t].get(metric)
            val_m = mimo_all_data[t].get(metric)
            if val_g is not None and val_m is not None:
                x_metric.append(float(val_g))
                y_metric.append(float(val_m))
        
        if len(x_metric) > 1:
            corr = calculate_pearson(x_metric, y_metric)
            metric_correlations.append((metric, corr))
            print(f"{metric:<35} | {corr:>12.4f}")
    
    print("=" * 60)
    
    # Interpretation of Total Score Correlation
    correlation = total_correlation
    if correlation >= 0.7:
        interp = "Strong Positive"
    elif correlation >= 0.4:
        interp = "Moderate Positive"
    elif correlation >= 0.1:
        interp = "Weak Positive"
    elif correlation > -0.1:
        interp = "Near Zero (No Correlation)"
    elif correlation > -0.4:
        interp = "Weak Negative"
    elif correlation > -0.7:
        interp = "Moderate Negative"
    else:
        interp = "Strong Negative"
        
    print(f"Overall Score Interpretation: {interp}")
    print("=" * 60)
    
    # Show top/bottom percentile differences
    differences = []
    for t in common_tickers:
        if t in grok_percentiles and t in mimo_percentiles:
            g_perc = grok_percentiles[t]
            m_perc = mimo_percentiles[t]
            diff = abs(g_perc - m_perc)
            differences.append((t, g_perc, m_perc, diff))
    
    if differences:
        # Sort by difference
        differences.sort(key=lambda x: x[3], reverse=True)
        
        print("\nBiggest Percentile Discrepancies (Top 10):")
        print(f"{'Ticker':<10} {'Grok %':>10} {'Mimo %':>10} {'Diff':>10}")
        print("-" * 45)
        for t, g, m, d in differences[:10]:
            print(f"{t:<10} {g:>9.1f}% {m:>9.1f}% {d:>9.1f}%")

        print("\nClosest Percentile Matches (Top 10):")
        print(f"{'Ticker':<10} {'Grok %':>10} {'Mimo %':>10} {'Diff':>10}")
        print("-" * 45)
        for t, g, m, d in differences[-10:]:
            print(f"{t:<10} {g:>9.1f}% {m:>9.1f}% {d:>9.1f}%")

if __name__ == "__main__":
    analyze_cross_db_correlation()

