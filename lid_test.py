import time
import sys
from datetime import datetime

def main():
    print(f"--- Counter started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    print("This script will count indefinitely once per second.")
    print("Use this to test if background processes continue when the lid is closed.")
    print("Press Ctrl+C to stop.\n")
    
    count = 1
    try:
        while True:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] Count: {count}")
            sys.stdout.flush()  # Ensure it prints immediately
            count += 1
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n--- Counter stopped at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

if __name__ == "__main__":
    main()

