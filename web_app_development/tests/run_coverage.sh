#!/bin/bash

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Navigate to project root
cd "$PROJECT_ROOT"

# Ensure coverage is installed
python3 -m pip install coverage

# Run the tests with coverage
# Include src directory (the main code being tested)
python3 -m coverage run --source=src -m unittest discover -s web_app_development/tests -p "test_*.py"

# Generate detailed report
echo ""
echo "Coverage Report (Web App Code):"
echo "==============================="
# Show all files that were executed, excluding standard library and site-packages
python3 -m coverage report -m \
    --include="src/*" \
    --omit="*/site-packages/*,*/dist-packages/*,*/__pycache__/*"

echo ""
echo "Summary:"
echo "--------"
python3 -m coverage report --include="src/*" --omit="*/site-packages/*,*/dist-packages/*,*/__pycache__/*" | tail -3

# Optional: Generate HTML report for detailed view
# Uncomment the following lines to generate HTML report
# python3 -m coverage html --include="web_app/*" --omit="*/site-packages/*,*/dist-packages/*,*/__pycache__/*"
# echo ""
# echo "HTML report generated in htmlcov/index.html"
# echo "Open htmlcov/index.html in your browser for detailed coverage visualization"

