import sys
import os
import requests
import yfinance as yf
from datetime import datetime

def fetch_yahoo_direct(ticker, start_date):
    """Fallback method using direct requests to Yahoo Finance API if yfinance fails."""
    try:
        start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
        end_ts = int(datetime.now().timestamp())
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start_ts}&period2={end_ts}&interval=1d"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        chart = data.get('chart', {}).get('result', [{}])[0]
        indicators = chart.get('indicators', {}).get('quote', [{}])[0]
        closes = indicators.get('close', [])
        
        valid_closes = [c for c in closes if c is not None]
        if not valid_closes:
            return None, None, None
            
        return valid_closes[0], valid_closes[-1], ((valid_closes[-1] / valid_closes[0]) - 1) * 100
    except Exception:
        return None, None, None

def get_live_return(stock_or_ticker, start_date="2025-01-01"):
    """Fetch price at start_date and current price."""
    if isinstance(stock_or_ticker, dict):
        ticker = stock_or_ticker['ticker']
    else:
        ticker = stock_or_ticker

    try:
        yf_ticker = ticker
        if ticker == 'GOOG': yf_ticker = 'GOOGL'
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        with open(os.devnull, 'w') as fnull:
            old_stderr = sys.stderr
            sys.stderr = fnull
            try:
                data = yf.download(yf_ticker, start=start_date, session=session, progress=False)
            finally:
                sys.stderr = old_stderr
        
        if not data.empty:
            start_price = float(data.iloc[0]['Close'])
            end_price = float(data.iloc[-1]['Close'])
            total_return = ((end_price / start_price) - 1) * 100
            if isinstance(stock_or_ticker, dict):
                stock_or_ticker.update({'start_price': start_price, 'current_price': end_price, 'return': total_return})
                return stock_or_ticker
            return start_price, end_price, total_return
    except Exception:
        pass
        
    start_p, end_p, ret = fetch_yahoo_direct(ticker, start_date)
    if ret is not None:
        if isinstance(stock_or_ticker, dict):
            stock_or_ticker.update({'start_price': start_p, 'current_price': end_p, 'return': ret})
            return stock_or_ticker
        return start_p, end_p, ret
    
    return None
