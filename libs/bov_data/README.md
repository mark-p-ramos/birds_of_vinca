# BOV Data

Data access layer for Birds of Vinca project.

## Overview

This package provides database access and data models for the Birds of Vinca application. It handles all interactions with MongoDB and provides a clean interface for other services to work with bird sighting data.

## Installation

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package in editable mode with dev dependencies
pip install -e ".[dev]"
```

## Development

### Running Tests

```bash
# Run all tests
.venv/bin/pytest

# Run with coverage
.venv/bin/pytest --cov=bov_data
```

### Code Quality

```bash
# Format code
.venv/bin/black src/ tests/

# Lint code
.venv/bin/ruff check src/ tests/

# Type checking
.venv/bin/mypy src/
```

### Convenience Script

Use the provided check script to run all quality checks:

```bash
./check.sh
```

## Usage

```python
from bov_data import ...

# Example usage will be added as the package develops
```

## Project Structure

```
bov_data/
├── src/
│   └── bov_data/
│       └── __init__.py
├── tests/
│   └── __init__.py
├── pyproject.toml
├── README.md
└── check.sh
```
