#!/bin/bash

set -e

echo "================================"
echo "Bug Reproduction Setup"
echo "================================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

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
python manage.py migrate

echo ""
echo "================================"
echo "Setup Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your langfuse credentials (if needed)"
echo "2. Start Celery worker: ./run_celery_gevent.sh"
echo "3. In another terminal, run: python trigger_tasks.py"
echo "   OR run the standalone test: python reproduce_bug.py"
echo ""
echo "To stop services: docker-compose down"
echo ""
