import yfinance as yf
import requests

def test_yf():
    ticker = "005930.KS" # Samsung
    print(f"Testing {ticker}...")
    try:
        # Create session with headers
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        stock = yf.Ticker(ticker, session=session)
        info = stock.info
        pe = info.get('trailingPE') or info.get('forwardPE')
        print(f"P/E: {pe}")
        print(f"Name: {info.get('longName')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_yf()

