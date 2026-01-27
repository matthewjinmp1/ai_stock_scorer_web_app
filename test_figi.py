import os
import requests
import json

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
API_KEY = "ea07b908-24ca-4544-ad14-fd465674e555"

def test_mapping(cusips):
    headers = {
        'Content-Type': 'application/json',
        'X-OPENFIGI-APIKEY': API_KEY
    }
    jobs = [{"idType": "ID_CUSIP", "idValue": c} for c in cusips]
    
    response = requests.post(OPENFIGI_URL, headers=headers, json=jobs)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        results = response.json()
        for i, res in enumerate(results):
            print(f"CUSIP: {cusips[i]}")
            if 'data' in res:
                print(f"  Found {len(res['data'])} matches")
                for d in res['data'][:2]:
                    print(f"    - Ticker: {d.get('ticker')}, Exch: {d.get('exchCode')}, Type: {d.get('securityType2')}")
            else:
                print(f"  No data found: {res.get('error')}")

if __name__ == "__main__":
    # Test some of the missing ones
    test_mapping(["00105510", "00003602", "01055102", "1055102", "001055102"])

