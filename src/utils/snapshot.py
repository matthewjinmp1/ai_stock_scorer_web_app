#!/usr/bin/env python3
"""
Snapshot tool for scores.json
Creates dated snapshots of the scores.json file and stores them in snapshots.json
"""

import json
import os
from datetime import datetime

SCORES_FILE = "data/scores.json"
SNAPSHOTS_FILE = "data/snapshots.json"


def load_scores():
    """Load scores from scores.json."""
    if os.path.exists(SCORES_FILE):
        try:
            with open(SCORES_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error loading {SCORES_FILE}: {e}")
            return None
    else:
        print(f"Error: {SCORES_FILE} not found.")
        return None


def load_snapshots():
    """Load existing snapshots from snapshots.json."""
    if os.path.exists(SNAPSHOTS_FILE):
        try:
            with open(SNAPSHOTS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"snapshots": []}
    return {"snapshots": []}


def save_snapshots(snapshots_data):
    """Save snapshots to snapshots.json."""
    with open(SNAPSHOTS_FILE, 'w') as f:
        json.dump(snapshots_data, f, indent=2)


def create_snapshot():
    """Create a snapshot of the current scores.json file."""
    scores_data = load_scores()
    if scores_data is None:
        return False
    
    # Get current date (no time)
    snapshot_date = datetime.now().strftime("%Y-%m-%d")
    
    # Load existing snapshots
    snapshots_data = load_snapshots()
    
    # Create new snapshot entry
    new_snapshot = {
        "date": snapshot_date,
        "scores": scores_data
    }
    
    # Add to snapshots list
    snapshots_data["snapshots"].append(new_snapshot)
    
    # Save snapshots
    save_snapshots(snapshots_data)
    
    print(f"Snapshot created successfully!")
    print(f"Date: {snapshot_date}")
    print(f"Total snapshots: {len(snapshots_data['snapshots'])}")
    print(f"Saved to {SNAPSHOTS_FILE}")
    
    return True


def list_snapshots():
    """List all available snapshots."""
    snapshots_data = load_snapshots()
    snapshots = snapshots_data.get("snapshots", [])
    
    if not snapshots:
        print("No snapshots found.")
        return
    
    print(f"\nTotal snapshots: {len(snapshots)}")
    print("=" * 60)
    for i, snapshot in enumerate(snapshots, 1):
        date_str = snapshot.get("date", "Unknown date")
        
        companies_count = len(snapshot.get("scores", {}).get("companies", {}))
        print(f"{i}. {date_str} - {companies_count} companies")
    print("=" * 60)


def main():
    """Main function."""
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "list":
            list_snapshots()
        elif command == "create" or command == "snapshot":
            create_snapshot()
        else:
            print(f"Unknown command: {command}")
            print("Usage:")
            print("  python snapshot.py          - Create a new snapshot")
            print("  python snapshot.py create   - Create a new snapshot")
            print("  python snapshot.py list     - List all snapshots")
    else:
        # Default action: create snapshot
        create_snapshot()


if __name__ == "__main__":
    main()

