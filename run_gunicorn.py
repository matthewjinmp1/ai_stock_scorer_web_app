#!/usr/bin/env python
"""Launcher script for gunicorn that ensures Python path is set correctly."""
import sys
import os

# Get the directory where this script is located (project root)
script_dir = os.path.dirname(os.path.abspath(__file__))

# Add project root to Python path if not already there
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Change to project root directory
os.chdir(script_dir)

# Import gunicorn and run
import subprocess
import sys

port = os.environ.get('PORT', '8000')
cmd = [sys.executable, '-m', 'gunicorn', '--bind', f'0.0.0.0:{port}', 'src.web.app:app']
sys.exit(subprocess.call(cmd))

