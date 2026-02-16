#!/bin/bash
# Creates virtual environments for each subproject in the monorepo

set -e  # Exit on error

PROJECT_ROOT="/workspaces/birds_of_vinca"
PROJECTS=("curator" "poll_sightings" "libs/bov_data")

for project in "${PROJECTS[@]}"; do
    echo "Setting up virtual environment for $project..."
    cd "$PROJECT_ROOT/$project"

    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi

    # Activate and install dependencies
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -e .[dev]
    deactivate

    echo "✓ $project virtual environment ready"
done

echo "All virtual environments set up successfully!"
