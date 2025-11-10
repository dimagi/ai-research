#!/bin/bash

set -e

echo "================================"
echo "Bug Reproduction Setup"
echo "================================"
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "uv not found. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Create virtual environment and install dependencies with uv
echo "Setting up virtual environment and installing dependencies with uv..."
uv sync

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo ""
    echo "⚠️  Please edit .env file with your configuration before proceeding!"
    echo ""
fi

# Start Docker services
echo "Starting PostgreSQL and Redis with Docker Compose..."
docker-compose up -d

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
sleep 5

# Run migrations
echo "Running Django migrations..."
uv run python manage.py migrate

echo ""
echo "================================"
echo "Setup Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your langfuse credentials (if needed)"
echo "2. Start Celery worker: ./run_celery_gevent.sh"
echo "3. In another terminal, run: uv run python trigger_tasks.py"
echo "   OR run the standalone test: uv run python reproduce_bug.py"
echo ""
echo "To stop services: docker-compose down"
echo ""
