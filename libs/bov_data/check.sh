#!/bin/bash
# Run all code quality checks for bov_data

set -e

echo "Running Black..."
black --check src/ tests/

echo "Running Ruff..."
ruff check src/ tests/

echo "Running Mypy..."
mypy src/

echo "Running tests..."
pytest

echo "All checks passed!"
