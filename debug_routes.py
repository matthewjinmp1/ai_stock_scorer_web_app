import sys
import os
# repo root
sys.path.insert(0, os.getcwd())

from src.web.app import app

print("Listing all registered routes:")
for rule in app.url_map.iter_rules():
    print(f"{rule.endpoint}: {rule.rule}")

with app.test_client() as client:
    response = client.get('/peers')
    print(f"\n/peers status: {response.status_code}")
    
    response = client.get('/watchlist')
    print(f"/watchlist status: {response.status_code}")
    
    response = client.get('/groups')
    print(f"/groups status: {response.status_code}")
    
    response = client.get('/ai-relevance')
    print(f"/ai-relevance status: {response.status_code}")
