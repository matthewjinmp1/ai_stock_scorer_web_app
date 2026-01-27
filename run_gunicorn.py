#!/usr/bin/env python
"""Launcher script for gunicorn that ensures Python path is set correctly."""
import sys
import os

# Get the directory where this script is located (project root)
script_dir = os.path.dirname(os.path.abspath(__file__))
cwd = os.getcwd()

# Determine the actual project root
# The script should be in the project root, so script_dir is the project root
project_root = script_dir

# Add project root to Python path - this MUST be done before any imports
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Also ensure current working directory is in path
if cwd not in sys.path and cwd != project_root:
    sys.path.insert(0, cwd)

# Change to project root directory to ensure relative paths work
os.chdir(project_root)

# Update PYTHONPATH environment variable
os.environ['PYTHONPATH'] = project_root + (os.pathsep + os.environ.get('PYTHONPATH', '') if os.environ.get('PYTHONPATH') else '')

# Debug output (will show in Render logs)
print(f"Script directory (project root): {project_root}", file=sys.stderr)
print(f"Current working directory: {os.getcwd()}", file=sys.stderr)
print(f"Python path (first 3): {sys.path[:3]}", file=sys.stderr)
config_path = os.path.join(project_root, 'src', 'core', 'config.py')
print(f"Config file exists: {os.path.exists(config_path)} at {config_path}", file=sys.stderr)

# Verify we can import the config before starting gunicorn
try:
    # Test import
    import importlib.util
    spec = importlib.util.spec_from_file_location("src.core.config", config_path)
    if spec and spec.loader:
        print("Config module can be loaded", file=sys.stderr)
except Exception as e:
    print(f"Warning: Could not verify config import: {e}", file=sys.stderr)

# Import and run gunicorn
from gunicorn.app.wsgiapp import WSGIApplication

if __name__ == '__main__':
    port = os.environ.get('PORT', '8000')
    # Calculate optimal workers: (2 x CPU cores) + 1
    # For Render free tier (512MB RAM), use 2-4 workers max
    # For paid tiers, can use more
    workers = int(os.environ.get('GUNICORN_WORKERS', '2'))
    threads = int(os.environ.get('GUNICORN_THREADS', '4'))
    timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))
    keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', '5'))
    
    sys.argv = [
        'gunicorn',
        '--bind', f'0.0.0.0:{port}',
        '--workers', str(workers),
        '--threads', str(threads),
        '--worker-class', 'gthread',
        '--timeout', str(timeout),
        '--keep-alive', str(keepalive),
        '--max-requests', '1000',  # Restart workers after 1000 requests to prevent memory leaks
        '--max-requests-jitter', '50',
        '--log-level', 'info',
        '--access-logfile', '-',
        '--error-logfile', '-',
        'src.web.app:app'
    ]
    WSGIApplication().run()

