import os
import requests
import json

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
API_KEY = "ea07b908-24ca-4544-ad14-fd465674e555"

def test_ticker_mapping(tickers):
    headers = {
        'Content-Type': 'application/json',
        'X-OPENFIGI-APIKEY': API_KEY
    }
    jobs = [{"idType": "TICKER", "idValue": t, "exchCode": "US"} for t in tickers]
    
    response = requests.post(OPENFIGI_URL, headers=headers, json=jobs)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        results = response.json()
        for i, res in enumerate(results):
            print(f"Ticker: {tickers[i]}")
            if 'data' in res:
                for d in res['data']:
                    print(f"  - Ticker: {d.get('ticker')}, Exch: {d.get('exchCode')}, Composite FIGI: {d.get('compositeFIGI')}")
                    # We can't see CUSIP directly here, but we can see other IDs
                    print(f"    - Metadata: {d}")
            else:
                print(f"  Error: {res.get('error')}")

if __name__ == "__main__":
    test_ticker_mapping(["SPOT", "FLUT"])

