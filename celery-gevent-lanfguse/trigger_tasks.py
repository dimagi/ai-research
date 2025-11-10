#!/usr/bin/env python
"""
Script to trigger Celery tasks that demonstrate the bug.

This script sends tasks to the Celery worker running with gevent pool.
The tasks use langfuse (OpenTelemetry) decorators and make database queries.
This combination can cause SSL verification issues with psycopg3.
"""

import django
import os

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bugrepro.settings')
django.setup()

from testapp.tasks import test_db_query, test_db_query_with_model


def main():
    print("Triggering tasks...")

    # Trigger the first task
    result1 = test_db_query.delay()
    print(f"Task 1 (test_db_query) submitted: {result1.id}")

    # Trigger the second task
    result2 = test_db_query_with_model.delay()
    print(f"Task 2 (test_db_query_with_model) submitted: {result2.id}")

    print("\nWaiting for results...")

    try:
        res1 = result1.get(timeout=10)
        print(f"Task 1 result: {res1}")
    except Exception as e:
        print(f"Task 1 failed with error: {e}")

    try:
        res2 = result2.get(timeout=10)
        print(f"Task 2 result: {res2}")
    except Exception as e:
        print(f"Task 2 failed with error: {e}")


if __name__ == '__main__':
    main()
