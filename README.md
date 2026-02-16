# Birds of Vinca

A Python monorepo for importing and curating media capture from Bird Buddy.

### Curating
- remove periods of inactivity from videos
- remove poor pictures 
- remove highly similar pictures

### Data Capture
- weather conditions
    - temperature
    - cloud cover
    - precipitating
- feed type
- species

After enough collection I can data mine:
- Which feeds attract which species?
- What time of day or year attract which species?

### Frontend
Expose imported media in a simpler gallery style viewer with search by species / timestamp.


## Tech Stack

- Python 3.12+
- pytest for testing
- black for formatting
- ruff for linting
- mypy for type checking


## Project Structure

This repository contains two Python subprojects:

- **[poll_sightings/](poll_sightings/)** - Poll sightings service
- **[curator/](curator/)** - Curator service

## Development

This project uses a shared dev container with isolated virtual environments for each subproject.

### Getting Started

Open `birds-of-vinca.code-workspace` in VS Code for the best multi-project development experience.

### Project Structure

curator and poll_sightings have their own Pythong virtual environments.
- `curator/.venv/` - Curator service environment
- `poll_sightings/.venv/` - Poll Sightings service environment

#### Running Tests

```bash
# Test curator
cd curator
./check.sh  # Runs black, ruff, mypy, and pytest

# Test poll_sightings
cd poll_sightings
./check.sh  # Runs black, ruff, mypy, and pytest
```

#### Manual Virtual Environment Activation

If you need to manually activate a virtual environment:

```bash
# Activate curator environment
cd curator
source .venv/bin/activate

# Activate poll_sightings environment
cd poll_sightings
source .venv/bin/activate

# Deactivate any environment
deactivate
```

### Manual Setup

If you need to manually recreate the virtual environments:

```bash
bash .devcontainer/setup-venvs.sh
```

Or individually:

```bash
cd curator
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
deactivate

cd ../poll_sightings
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
deactivate
```

