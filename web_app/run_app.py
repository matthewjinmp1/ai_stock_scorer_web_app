#!/usr/bin/env python3
import sys
import os
import subprocess

def run_app():
    # Get the directory of this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    # Ensure dependencies are installed
    try:
        import flask
    except ImportError:
        print("Flask not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])

    # Run the app
    # Set PYTHONPATH to include project root so app.py can find data etc
    env = os.environ.copy()
    env['FLASK_APP'] = 'app.py'
    env['PYTHONPATH'] = project_root + os.pathsep + env.get('PYTHONPATH', '')
    
    print("\n" + "="*50)
    print("Starting AI Stock Scorer Web App")
    print("Dashboard will be available at: http://127.0.0.1:5001")
    print("="*50 + "\n")
    
    # Run from within the web_app directory
    subprocess.call([sys.executable, "app.py"], cwd=current_dir, env=env)

if __name__ == "__main__":
    run_app()

