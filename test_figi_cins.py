import os
import requests
import json

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
API_KEY = "ea07b908-24ca-4544-ad14-fd465674e555"

def test_cins_mapping(identifiers):
    headers = {
        'Content-Type': 'application/json',
        'X-OPENFIGI-APIKEY': API_KEY
    }
    # Try mapping as ID_CUSIP and ID_CINS
    jobs = []
    for id_val in identifiers:
        jobs.append({"idType": "ID_CUSIP", "idValue": id_val})
        jobs.append({"idType": "ID_CINS", "idValue": id_val})
    
    response = requests.post(OPENFIGI_URL, headers=headers, json=jobs)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        results = response.json()
        for i, res in enumerate(results):
            job = jobs[i]
            print(f"Type: {job['idType']}, Value: {job['idValue']}")
            if 'data' in res:
                print(f"  SUCCESS: Found {len(res['data'])} matches")
                for d in res['data'][:1]:
                    print(f"    - Ticker: {d.get('ticker')}, Name: {d.get('name')}")
            else:
                print(f"  FAILED: {res.get('error')}")

if __name__ == "__main__":
    # Spotify (L...), Flutter (G...), Grab (G...)
    test_cins_mapping(["L8681T102", "G3643J108", "G4113P101"])

