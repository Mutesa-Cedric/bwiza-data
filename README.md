# bwiza-data

Kinyarwanda data factory for Bwiza AI.

## Requirements

- Python 3.11+
- pip (venv recommended)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Smoke test

```bash
python scripts/smoke_test.py
```

## Run tests

```bash
pytest
```
