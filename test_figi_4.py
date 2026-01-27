import os
import requests
import json

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
API_KEY = "ea07b908-24ca-4544-ad14-fd465674e555"

def test_name_mapping(names):
    headers = {
        'Content-Type': 'application/json',
        'X-OPENFIGI-APIKEY': API_KEY
    }
    # Name mapping requires a slightly different structure or using a different idType if supported
    # Actually, for name lookup, OpenFIGI uses a different approach.
    # But we can try "idType": "TICKER" if we had it.
    
    # Wait, OpenFIGI's main mapping API doesn't do "fuzzy name search".
    # But it does have a Search API or we can try other identifiers.
    
    # Let's try to see if we can use ID_CUSIP with the first 8 characters
    # as some systems use 8-char CUSIPs.
    
    jobs = [{"idType": "ID_CUSIP", "idValue": n} for n in names]
    
    response = requests.post(OPENFIGI_URL, headers=headers, json=jobs)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        results = response.json()
        for i, res in enumerate(results):
            print(f"Query: {names[i]}")
            if 'data' in res:
                print(f"  Found {len(res['data'])} matches")
            else:
                print(f"  Error: {res.get('error')}")

if __name__ == "__main__":
    # Test Amazon 8-char and others
    test_name_mapping(["02313510", "L8681T10", "G3643J10"])

