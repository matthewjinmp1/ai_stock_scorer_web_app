#!/usr/bin/env python3
"""
Convenience script to run scorer.py from the root directory.
This allows running the scorer without navigating to src/scoring/scorer.py
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and run the main function from scorer
from scoring.scorer import main

if __name__ == "__main__":
    main()

