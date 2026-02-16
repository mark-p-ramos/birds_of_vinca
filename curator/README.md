# Curator

Curator service for Birds of Vinca project.

## Development

This project is part of a monorepo with separate virtual environments per project.

### Quick Start

1. Open the repository in VSCode with the dev container
2. The virtual environment is created automatically at `curator/.venv/`
3. VSCode will automatically use the correct Python interpreter when editing curator files

### Running Quality Checks

```bash
cd curator
./check.sh  # Runs black, ruff, mypy, and pytest
```

### Manual Virtual Environment

If you need to manually activate the virtual environment:

```bash
cd curator
source .venv/bin/activate
```

## Testing

```bash
cd curator
pytest
```

## Installation

The project uses a local virtual environment. In the dev container, it's set up automatically.

For manual setup:

```bash
cd curator
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```
