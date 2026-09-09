#!/bin/bash
# Setup script cho AI20K project (uv-based)

set -e

echo "=== AI20K Project Setup ==="

# Check uv
if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found. Install it first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "uv OK: $(uv --version)"

# Create venv + install deps (runtime + dev) from uv.lock
uv sync

# Create .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env — please edit with your API keys"
fi

# Create data directories
mkdir -p data/chroma

echo "Setup complete! Run: uv run uvicorn src.main:app --reload"
