#!/bin/bash
# Script to run all tests

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

# Add src to PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT/src

# Move to project root to run tests consistently
cd "$PROJECT_ROOT"

# Run pytest
echo "Running unit tests..."
python3 -m pytest tests/test_scorer_logic.py tests/test_db_manager.py tests/test_naming.py tests/test_token_cost.py tests/test_scorer_utils.py tests/test_logging.py tests/test_scorer_main.py tests/test_scorer_commands.py tests/test_scorer_extras.py tests/test_scorer_more_commands.py tests/test_scorer_async.py -v
