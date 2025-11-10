#!/bin/bash

# Run Celery with multiple worker processes using gevent pool
# Multiple workers can expose race conditions and SSL context issues

WORKERS=${1:-3}
CONCURRENCY=${2:-10}

echo "Starting Celery with $WORKERS worker processes, $CONCURRENCY greenlets each"
echo "Total concurrency: $((WORKERS * CONCURRENCY))"
echo ""

uv run celery -A bugrepro worker \
    --pool=gevent \
    --concurrency=$CONCURRENCY \
    --autoscale=$((CONCURRENCY+5)),$((CONCURRENCY-3)) \
    --max-tasks-per-child=50 \
    --loglevel=info \
    --logfile=logs/celery-%n%I.log \
    -n worker@%h \
    --prefetch-multiplier=1

# Note: To truly run multiple processes, you'd need to use:
# uv run celery multi start 3 -A bugrepro --pool=gevent --concurrency=10 --loglevel=info
# uv run celery multi stop 3 -A bugrepro
