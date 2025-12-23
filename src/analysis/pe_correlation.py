import sqlite3
import os
import math
import time
import json
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import statistics

# Define paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
DB_PATH = os.path.join(PROJECT_ROOT, "web_app", "top_500_scores.db")
CACHE_FILE = os.path.join(PROJECT_ROOT, "data", "pe_cache.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

EXCHANGE_MAP = {
    'SZ': 'SHE',
    'SS': 'SHA',
    'HK': 'HKG',
    'KS': 'KRX',
    'T': 'TYO',
    'DE': 'ETR',
    'PA': 'EPA',
    'AS': 'AMS',
    'LS': 'ELI',
    'MI': 'BIT',
    'MC': 'BME',
    'L': 'LON',
    'TO': 'TSE',
    'V': 'CVE',
    'AX': 'ASX',
    'SR': 'TADAWUL',
    'NS': 'NSE',
    'BS': 'BOM',
    'MX': 'BMV',
    'ST': 'STO',
    'OL': 'OSL',
    'CP': 'CPH',
    'HE': 'HEL',
    'VI': 'VIE',
    'BR': 'EBR',
    'SW': 'SWX',
    'TW': 'TPE',
    'SI': 'SGX',
}

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
    if not values:
        return 0, 0, 0
    mean = sum(values) / len(values)
    median = statistics.median(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0
    return mean, median, stdev

def get_latest_scores():
    if not os.path.exists(DB_PATH):
        return {}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = """
            SELECT ticker, total_score, company_name 
            FROM scores s1
            WHERE timestamp = (
                SELECT MAX(timestamp) 
                FROM scores s2 
                WHERE s2.ticker = s1.ticker
            )
        """
        cursor.execute(query)
        scores = {row['ticker']: {'total_score': row['total_score'], 'name': row['company_name']} for row in cursor.fetchall()}
        conn.close()
        return scores
    except Exception:
        return {}

def calculate_percentile_ranks(scores_dict):
    if not scores_dict: return {}
    all_scores = [v['total_score'] for v in scores_dict.values() if v['total_score'] is not None]
    sorted_scores = sorted(all_scores)
    n = len(sorted_scores)
    percentiles = {}
    for ticker, data in scores_dict.items():
        score = data['total_score']
        if score is None: continue
        count = sum(1 for s in sorted_scores if s <= score)
        percentiles[ticker] = (count / n) * 100
    return percentiles

def fetch_pe_google(ticker):
    """Scrape P/E from Google Finance."""
    parts = ticker.split('.')
    symbol = parts[0]
    suffix = parts[1] if len(parts) > 1 else None
    
    exchanges = []
    if suffix:
        exchange = EXCHANGE_MAP.get(suffix.upper())
        if exchange:
            exchanges.append(exchange)
    else:
        # For US stocks, try NASDAQ and NYSE
        exchanges = ['NASDAQ', 'NYSE']
    
    for exc in exchanges:
        url = f"https://www.google.com/finance/quote/{symbol}:{exc}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            if response.status_code != 200:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            # Look for "P/E ratio" in the page
            # Note: Google Finance sometimes uses "P/E ratio (TTM)"
            pe_label = soup.find(string=lambda t: t and "P/E ratio" in t)
            if pe_label:
                try:
                    # Navigation depends on the structure, but usually it's in a sibling or nearby div
                    # The structure is often: <div><div>P/E ratio</div><div>VAL</div></div>
                    pe_val_str = pe_label.parent.parent.find_next_sibling().text
                    # Clean value (e.g., "23.01" or "1,234.56")
                    pe_val_str = pe_val_str.replace(',', '')
                    if pe_val_str and pe_val_str != '-':
                        return ticker, float(pe_val_str)
                except:
                    pass
        except Exception:
            continue
            
    return ticker, None

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)

def analyze_pe_correlation(workers=5, limit=None):
    print("P/E Ratio vs. Percentile Score Correlation Analysis (via Google Finance)")
    print("=" * 70)
    
    scores_data = get_latest_scores()
    if not scores_data:
        print("No scores found.")
        return
        
    percentiles = calculate_percentile_ranks(scores_data)
    cache = load_cache()
    pe_data = {}
    
    tickers_to_fetch = []
    for ticker in scores_data.keys():
        if ticker in cache:
            pe_data[ticker] = cache[ticker]
        else:
            tickers_to_fetch.append(ticker)
            
    if limit:
        tickers_to_fetch = tickers_to_fetch[:limit]

    if tickers_to_fetch:
        print(f"Fetching {len(tickers_to_fetch)} new P/E ratios from Google Finance...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_ticker = {executor.submit(fetch_pe_google, t): t for t in tickers_to_fetch}
            count = 0
            for future in as_completed(future_to_ticker):
                ticker, pe = future.result()
                count += 1
                if pe is not None and 0 < pe < 1000:
                    pe_data[ticker] = pe
                    cache[ticker] = pe
                
                if count % 20 == 0 or count == len(tickers_to_fetch):
                    print(f"Processed {count}/{len(tickers_to_fetch)} tickers...")
                    save_cache(cache)
                    time.sleep(0.5) # Small throttle
    
    save_cache(cache) # Final save
    
    common_tickers = sorted(list(set(percentiles.keys()) & set(pe_data.keys())))
    if not common_tickers:
        print("No common data found. Check your internet or Google Finance structure.")
        return
        
    x_perc = [percentiles[t] for t in common_tickers]
    y_pe = [pe_data[t] for t in common_tickers]
    
    correlation = calculate_pearson(x_perc, y_pe)
    mean_perc, med_perc, sd_perc = calculate_stats(x_perc)
    mean_pe, med_pe, sd_pe = calculate_stats(y_pe)

    print("-" * 70)
    print(f"Sample Size:          {len(common_tickers)} companies")
    print(f"Pearson Correlation:  {correlation:.4f}")
    print(f"\nDescriptive Statistics (Mean / Median / StDev):")
    print(f"{'Percentile':<15} | {mean_perc:>4.1f} / {med_perc:>4.1f} / {sd_perc:>4.1f}")
    print(f"{'P/E Ratio':<15} | {mean_pe:>4.1f} / {med_pe:>4.1f} / {sd_pe:>4.1f}")

    if abs(correlation) >= 0.1:
        interp = "Weak" if abs(correlation) < 0.4 else "Moderate" if abs(correlation) < 0.7 else "Strong"
        direction = "Positive" if correlation > 0 else "Negative"
        print(f"Interpretation:       {interp} {direction} Correlation")
    else:
        print(f"Interpretation:       Negligible Correlation")
    print("=" * 70)
    
    # Show Top 10 by Percentile and their P/E
    print("\nTop 10 Companies by Percentile and their P/E:")
    top_10 = sorted(common_tickers, key=lambda t: percentiles[t], reverse=True)[:10]
    print(f"{'Ticker':<10} | {'Name':<35} | {'Percentile':>10} | {'P/E':>8}")
    print("-" * 75)
    for t in top_10:
        name = scores_data[t]['name'] or t
        print(f"{t:<10} | {name[:35]:<35} | {percentiles[t]:>9.1f}% | {pe_data[t]:>8.2f}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    analyze_pe_correlation(workers=args.workers, limit=args.limit)
