#!/bin/bash
# Get the absolute path to the project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================"
echo "Starting AI Stock Scorer"
echo "========================================"

# Activate virtual environment
if [ -d "$PROJECT_ROOT/venv" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
    cd "$SCRIPT_DIR"
    python3 run_scorer.py
else
    echo "Virtual environment 'venv' not found in $PROJECT_ROOT. Please ensure it exists."
    exit 1
fi

