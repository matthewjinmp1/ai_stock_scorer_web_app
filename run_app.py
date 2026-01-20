import os
import sys

# Ensure the project root is in the path so internal 'src' imports work correctly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

try:
    from src.web.app import app
except ImportError as e:
    print(f"Error: Could not import the web application. {e}")
    print("Make sure you are running this from the project root.")
    sys.exit(1)

if __name__ == "__main__":
    print("\n" + "="*40)
    print("   AI STOCK SCORER - WEB DASHBOARD")
    print("="*40)
    print("Starting development server...")
    print("Access the dashboard at: http://127.0.0.1:5001")
    print("="*40 + "\n")
    
    # Run the app on port 5001 (as used in previous sessions)
    app.run(debug=True, port=5001)
