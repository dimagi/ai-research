#!/bin/bash

# Activate virtual environment
source venv/bin/activate

# Run Celery worker with gevent pool
# This is where the bug manifests - gevent + langfuse + psycopg3 SSL
celery -A bugrepro worker --pool=gevent --concurrency=10 --loglevel=info
