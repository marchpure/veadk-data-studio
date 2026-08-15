#!/bin/bash

# Script to run tests for the Project X server
# 
# This script automatically sets up the correct PYTHONPATH regardless of where
# the project is located on the developer's machine. It works by:
# 1. Finding the directory where this script is located (server/)
# 2. Setting PYTHONPATH to the parent directory (byaan/)
# 3. This allows imports like "from server.main import app" to work correctly

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Set Python path dynamically
# Get the current script directory (server)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# The tests import from "server.xxx", so PYTHONPATH needs the parent directory
export PYTHONPATH="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}Running Project X Server Tests${NC}"
echo "=================================="
echo -e "Using PYTHONPATH: $PYTHONPATH"
echo ""

# Parse command line arguments
TEST_TYPE=${1:-all}
VERBOSE=${2:--v}

case $TEST_TYPE in
    all)
        echo -e "${YELLOW}Running all tests...${NC}"
        uv run pytest tests/ $VERBOSE
        ;;
    integration)
        echo -e "${YELLOW}Running integration tests...${NC}"
        uv run pytest tests/integration/ $VERBOSE
        ;;
    unit)
        echo -e "${YELLOW}Running unit tests...${NC}"
        uv run pytest tests/unit/ $VERBOSE
        ;;
    notebooks)
        echo -e "${YELLOW}Running notebook tests...${NC}"
        uv run pytest tests/integration/test_notebooks_workflows.py $VERBOSE
        ;;
    coverage)
        echo -e "${YELLOW}Running tests with coverage...${NC}"
        uv run pytest tests/ --cov=server --cov-report=term-missing --cov-report=html
        echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    *)
        echo "Usage: $0 [all|integration|unit|notebooks|coverage] [-v|-vv|--tb=short]"
        echo ""
        echo "Options:"
        echo "  all         - Run all tests (default)"
        echo "  integration - Run only integration tests"
        echo "  unit        - Run only unit tests"
        echo "  notebooks   - Run only notebook workflow tests"
        echo "  coverage    - Run with coverage report"
        echo ""
        echo "Verbosity options (second argument):"
        echo "  -v          - Verbose output (default)"
        echo "  -vv         - Very verbose output"
        echo "  --tb=short  - Short traceback format"
        echo "  -q          - Quiet mode"
        exit 1
        ;;
esac