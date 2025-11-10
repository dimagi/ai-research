#!/bin/bash

# Run Celery worker with gevent pool using uv
# This is where the bug manifests - gevent + langfuse + psycopg3 SSL
uv run celery -A bugrepro worker --pool=gevent --concurrency=10 --loglevel=info
