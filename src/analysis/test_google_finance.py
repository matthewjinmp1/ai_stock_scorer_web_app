import requests
from bs4 import BeautifulSoup

def get_google_finance_pe(ticker, exchange):
    url = f"https://www.google.com/finance/quote/{ticker}:{exchange}"
    print(f"Fetching {url}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        # Google Finance layout changes, but P/E is usually in a div with specific text
        # Let's look for "P/E ratio" text and then the next sibling or parent's child
        pe_label = soup.find(text="P/E ratio")
        if pe_label:
            pe_val = pe_label.parent.parent.find_next_sibling().text
            print(f"Found P/E: {pe_val}")
            return pe_val
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    # Test Samsung (005930:KRX)
    get_google_finance_pe("005930", "KRX")
    # Test Apple (AAPL:NASDAQ)
    get_google_finance_pe("AAPL", "NASDAQ")

