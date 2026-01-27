import json
import os
import sys

# Add parent directory to path to import db_manager and scorer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.db_manager import DBManager
import scoring.scorer as scorer

def migrate():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
    json_path = os.path.join(project_root, "data", "scores.json")
    db_path = os.path.join(project_root, "data", "scores.db")

    if not os.path.exists(json_path):
        print(f"JSON file not found at {json_path}")
        return

    print(f"Migrating data from {json_path} to {db_path}...")
    
    with open(json_path, 'r') as f:
        data = json.load(f)

    db = DBManager(db_path)
    companies = data.get("companies", {})
    
    print(f"Found {len(companies)} companies.")
    
    count = 0
    for ticker, scores in companies.items():
        # Calculate total score using scorer's logic
        scores['total_score'] = scorer.calculate_total_score(scores)
            
        db.save_score(ticker, scores)
        count += 1
        if count % 50 == 0:
            print(f"Migrated {count} companies...")

    print(f"Successfully migrated {count} companies to SQLite database.")

if __name__ == "__main__":
    migrate()

