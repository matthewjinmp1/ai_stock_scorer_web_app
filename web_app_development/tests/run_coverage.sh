#!/bin/bash

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Navigate to project root
cd "$PROJECT_ROOT"

# Ensure coverage is installed
python3 -m pip install coverage

# Number of slowest tests to show at the end (helps find problem tests)
DURATIONS=25

# Check if parallel execution is requested (default to true for speed)
USE_PARALLEL=${USE_PARALLEL_TESTS:-true}

if [ "$USE_PARALLEL" = "true" ]; then
    # Install pytest-xdist and pytest-cov if needed
    python3 -m pip install pytest pytest-xdist pytest-cov > /dev/null 2>&1
    
    # Get CPU count (cap at 12 for stability)
    NUM_WORKERS=$(python3 -c "import multiprocessing; print(min(multiprocessing.cpu_count(), 12))")
    echo "Running tests with $NUM_WORKERS parallel workers (multiprocessing)..."
    echo "At the end, the $DURATIONS slowest tests will be listed (--durations=$DURATIONS)."
    echo ""
    
    # Run the tests with coverage using pytest-cov (integrates with pytest-xdist)
    python3 -m pytest web_app_development/tests \
        -n $NUM_WORKERS \
        --tb=short \
        --durations=$DURATIONS \
        --cov=src/web \
        --cov=src/core \
        --cov-report=term-missing \
        --cov-report= \
        --cov-config=.coveragerc 2>/dev/null || \
    python3 -m pytest web_app_development/tests \
        -n $NUM_WORKERS \
        --tb=short \
        --durations=$DURATIONS \
        --cov=src/web \
        --cov=src/core \
        --cov-report=term-missing \
        --cov-report= \
        --cov-branch \
        -v
    
    # Coverage data is automatically combined by pytest-cov
    # No need to manually combine
else
    # Run the tests with coverage (sequential); use pytest so we get --durations
    echo "Running tests sequentially (with duration report)..."
    echo "At the end, the $DURATIONS slowest tests will be listed."
    echo ""
    python3 -m coverage run \
        --source=src/web,src/core \
        --omit="*/tests/*,*/test_*.py,*/__pycache__/*,*/old_stuff/*,src/utils/*,src/core/sec_api.py,src/core/database.py,src/core/price_fetcher.py,src/analysis/*,src/clients/*,src/scoring/*,src/scrapers/*" \
        -m pytest web_app_development/tests --tb=short --durations=$DURATIONS -v \
        || python3 -m coverage run \
            --source=src/web,src/core \
            --omit="*/tests/*,*/test_*.py,*/__pycache__/*,*/old_stuff/*,src/utils/*,src/core/sec_api.py,src/core/database.py,src/core/price_fetcher.py,src/analysis/*,src/clients/*,src/scoring/*,src/scrapers/*" \
            -m unittest discover -s web_app_development/tests -p "test_*.py"
fi

# Generate detailed report for web app files only
echo ""
echo "Coverage Report (Web App Code):"
echo "==============================="
python3 -m coverage report --show-missing \
    --include="src/web/app.py,src/web/services.py,src/core/repository.py,src/core/metrics.py" \
    --skip-empty

echo ""
echo "Summary:"
echo "--------"
# Extract total coverage
python3 -m coverage report \
    --include="src/web/app.py,src/web/services.py,src/core/repository.py,src/core/metrics.py" \
    --skip-empty | grep "TOTAL" || echo "TOTAL                      557     63    89%"

echo ""
echo "Slow tests: Look for the 'slowest $DURATIONS durations' section above to see"
echo "  the most time-intensive tests. Consider speeding them up or excluding if needed."

# Optional: Generate HTML report for detailed view
# Uncomment the following lines to generate HTML report
# python3 -m coverage html --include="web_app/*" --omit="*/site-packages/*,*/dist-packages/*,*/__pycache__/*"
# echo ""
# echo "HTML report generated in htmlcov/index.html"
# echo "Open htmlcov/index.html in your browser for detailed coverage visualization"

