#!/bin/bash

# Simple script to start the AI Stock Scorer Web App
# Usage: ./start.sh

# Get the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Check if python3 is installed
if ! command -v python3 &> /dev/null
then
    echo "Error: python3 could not be found. Please install it."
    exit 1
fi

# Run the app
python3 run_app.py
