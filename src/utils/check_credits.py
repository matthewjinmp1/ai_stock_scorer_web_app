#!/usr/bin/env python3
"""
Credit Status Checker for Grok API
This script will periodically check if your credits are available.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from src.clients.grok_client import GrokClient
from config import XAI_API_KEY
import time

def check_credits():
    """Check if credits are available by making a simple API call."""
    try:
        grok = GrokClient(api_key=XAI_API_KEY)
        
        # Try a very simple request
        response = grok.simple_query("Hi", model="grok-2-latest")
        return True, response
        
    except Exception as e:
        return False, str(e)

def main():
    """Monitor credit availability."""
    print("Checking Grok API Credits...")
    print("=" * 40)
    
    max_attempts = 10
    attempt = 0
    
    while attempt < max_attempts:
        attempt += 1
        print(f"\nAttempt {attempt}/{max_attempts}")
        
        success, result = check_credits()
        
        if success:
            print("SUCCESS! Credits are now available!")
            print(f"Response: {result}")
            break
        else:
            print(f"Still waiting... Error: {result}")
            
            if attempt < max_attempts:
                print("Waiting 30 seconds before next check...")
                time.sleep(30)
    
    if attempt >= max_attempts:
        print("\nMaximum attempts reached.")
        print("Please check your xAI console manually:")
        print("https://console.x.ai/")

if __name__ == "__main__":
    main()
