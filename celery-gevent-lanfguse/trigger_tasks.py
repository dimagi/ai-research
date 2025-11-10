#!/usr/bin/env python
"""
Script to trigger Celery tasks that demonstrate the bug.

This script sends tasks to the Celery worker running with gevent pool.
The tasks use langfuse (OpenTelemetry) decorators and make database queries.
This combination can cause SSL verification issues with psycopg3.

Run with higher concurrency to stress test:
    python trigger_tasks.py --concurrency 20 --http-tasks 10
"""

import argparse
import random

import django
import os
import sys
import time

from requests import ReadTimeout

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bugrepro.settings')
django.setup()

from testapp.tasks import (
    test_db_query,
    test_db_query_with_model,
    test_http_with_db_logging,
    test_multiple_http_requests,
    test_mixed_operations,
)


def run_simple_tests():
    """Run simple tests with basic tasks"""
    print("=== Running Simple Tests ===\n")

    tasks = []

    # Test 1: Basic DB query
    result1 = test_db_query.delay()
    tasks.append(('test_db_query', result1))
    print(f"✓ Task submitted: test_db_query ({result1.id})")

    # Test 2: DB query with model
    result2 = test_db_query_with_model.delay()
    tasks.append(('test_db_query_with_model', result2))
    print(f"✓ Task submitted: test_db_query_with_model ({result2.id})")

    print("\n--- Waiting for results ---\n")

    for name, result in tasks:
        try:
            res = result.get(timeout=30)
            print(f"✓ {name}: {res}")
        except Exception as e:
            print(f"✗ {name} failed: {e}")


def run_http_tests(num_tasks=5, delay=1):
    """Run HTTP tests with httpbin"""
    print(f"\n=== Running HTTP Tests (num_tasks={num_tasks}, delay={delay}s) ===\n")

    tasks = []

    for i in range(num_tasks):
        result = test_http_with_db_logging.delay(delay=delay)
        tasks.append((f'test_http_with_db_logging-{i}', result))
        print(f"✓ Task {i+1}/{num_tasks} submitted: test_http_with_db_logging ({result.id})")

    print("\n--- Waiting for HTTP task results ---\n")

    success_count = 0
    error_count = 0

    for name, result in tasks:
        try:
            res = result.get(timeout=60)
            print(f"✓ {name}: {res}")
            success_count += 1
        except Exception as e:
            print(f"✗ {name} failed: {e}")
            error_count += 1

    print(f"\n--- HTTP Tests Summary: {success_count} succeeded, {error_count} failed ---")


def run_multiple_request_tests(num_tasks=3, requests_per_task=3):
    """Run tests that make multiple HTTP requests per task"""
    print(f"\n=== Running Multiple Request Tests (tasks={num_tasks}, requests/task={requests_per_task}) ===\n")

    tasks = []

    for i in range(num_tasks):
        result = test_multiple_http_requests.delay(num_requests=requests_per_task)
        tasks.append((f'test_multiple_http_requests-{i}', result))
        print(f"✓ Task {i+1}/{num_tasks} submitted: test_multiple_http_requests ({result.id})")

    print("\n--- Waiting for multiple request task results ---\n")

    success_count = 0
    error_count = 0

    for name, result in tasks:
        try:
            res = result.get(timeout=120)
            print(f"✓ {name}: {res}")
            success_count += 1
        except Exception as e:
            print(f"✗ {name} failed: {e}")
            error_count += 1

    print(f"\n--- Multiple Request Tests Summary: {success_count} succeeded, {error_count} failed ---")


def run_mixed_operations_tests(num_tasks=5):
    """Run tests with mixed operations (DB + HTTP + models)"""
    print(f"\n=== Running Mixed Operations Tests (num_tasks={num_tasks}) ===\n")

    tasks = []

    for i in range(num_tasks):
        result = test_mixed_operations.delay()
        tasks.append((f'test_mixed_operations-{i}', result))
        print(f"✓ Task {i+1}/{num_tasks} submitted: test_mixed_operations ({result.id})")

    print("\n--- Waiting for mixed operations task results ---\n")

    success_count = 0
    error_count = 0

    for name, result in tasks:
        try:
            res = result.get(timeout=60)
            print(f"✓ {name}: {res}")
            success_count += 1
        except Exception as e:
            print(f"✗ {name} failed: {e}")
            error_count += 1

    print(f"\n--- Mixed Operations Summary: {success_count} succeeded, {error_count} failed ---")


def run_stress_test(concurrency=20, http_tasks=10):
    """
    Run a stress test with high concurrency to increase likelihood of bug.

    This spawns many tasks simultaneously to stress the gevent pool
    and increase the chance of triggering SSL verification issues.
    """
    print(f"\n{'='*60}")
    print(f"=== STRESS TEST (concurrency={concurrency}, http_tasks={http_tasks}) ===")
    print(f"{'='*60}\n")

    tasks = []
    start_time = time.time()

    # Spawn many tasks quickly to stress the system
    print("Spawning tasks...")
    for i in range(concurrency):
        # Mix different task types
        if i % 4 == 0:
            result = test_db_query.delay()
            task_name = f"db_query-{i}"
        elif i % 4 == 1:
            result = test_multiple_http_requests.delay()
            task_name = f"test_multiple_http_requests-{i}"
        elif i % 4 == 2:
            result = test_db_query_with_model.delay()
            task_name = f"db_model-{i}"
        else:
            result = test_mixed_operations.delay()
            task_name = f"mixed_ops-{i}"

        tasks.append((task_name, result))

    # Add HTTP tasks
    for i in range(http_tasks):
        result = test_http_with_db_logging.delay(delay=1)
        tasks.append((f"http-{i}", result))

    print(f"✓ Spawned {len(tasks)} tasks in {time.time() - start_time:.2f}s")

    # Wait for all results
    print("\nWaiting for all tasks to complete...")

    success_count = 0
    error_count = 0
    timeout_count = 0
    request_timeout_count = 0

    for name, result in tasks:
        try:
            result.get(timeout=120)
            success_count += 1
            print(".", end="", flush=True)
        except TimeoutError:
            timeout_count += 1
            print("t", end="", flush=True)
        except ReadTimeout:
            request_timeout_count += 1
            print("T", end="", flush=True)
        except Exception:
            error_count += 1
            print("X", end="", flush=True)

    elapsed = time.time() - start_time

    print(f"\n\n{'='*60}")
    print("STRESS TEST RESULTS")
    print(f"{'='*60}")
    print(f"Total tasks:         {len(tasks)}")
    print(f"✓ Succeeded:         {success_count}")
    print(f"✗ Failed:            {error_count}")
    print(f"t Timeout:           {timeout_count}")
    print(f"T Requests Timeout:  {request_timeout_count}")
    print(f"Time elapsed:        {elapsed:.2f}s")
    print(f"Success rate:        {success_count/len(tasks)*100:.1f}%")
    print(f"{'='*60}\n")

    if error_count > 0 or timeout_count > 0:
        print("⚠️  Some tasks failed or timed out - bug may be present!")
        return 1
    else:
        print("✓ All tasks completed successfully")
        return 0


def run_long_test(concurrency=10, duration=60):
    """
    Run a stress test with high concurrency to increase likelihood of bug.

    This spawns many tasks simultaneously to stress the gevent pool
    and increase the chance of triggering SSL verification issues.
    """
    print(f"\n{'='*60}")
    print(f"=== LONG TEST (concurrency={concurrency}, duration={duration}) ===")
    print(f"{'='*60}\n")

    tasks = []
    start_time = time.time()

    # Spawn many tasks quickly to stress the system
    print("Spawning tasks...")
    for i in range(concurrency):
        result, task_name = _span_task(i)
        tasks.append((task_name, result))

    print(f"✓ Spawned {len(tasks)} tasks in {time.time() - start_time:.2f}s")

    # Wait for all results
    print("\nWaiting for all tasks to complete...")

    total_count = 0
    success_count = 0
    error_count = 0
    timeout_count = 0
    request_timeout_count = 0

    while tasks:
        name, result = tasks.pop(0)
        try:
            result.get(timeout=120)
            success_count += 1
            print(".", end="", flush=True)
        except TimeoutError:
            timeout_count += 1
            print("t", end="", flush=True)
        except ReadTimeout:
            request_timeout_count += 1
            print("T", end="", flush=True)
        except Exception:
            error_count += 1
            print("X", end="", flush=True)
        finally:
            total_count += 1

        elapsed = time.time() - start_time
        if elapsed < duration:
            new = concurrency - len(tasks)
            for i in range(new):
                result, task_name = _span_task(random.randint(i, 100))
                print("+", end="", flush=True)
                tasks.append((task_name, result))

    elapsed = time.time() - start_time

    print(f"\n\n{'='*60}")
    print("STRESS TEST RESULTS")
    print(f"{'='*60}")
    print(f"Total tasks:         {total_count}")
    print(f"✓ Succeeded:         {success_count}")
    print(f"✗ Failed:            {error_count}")
    print(f"t Timeout:           {timeout_count}")
    print(f"T Requests Timeout:  {request_timeout_count}")
    print(f"Time elapsed:        {elapsed:.2f}s")
    print(f"Success rate:        {success_count/total_count*100:.1f}%")
    print(f"{'='*60}\n")

    if error_count > 0 or timeout_count > 0:
        print("⚠️  Some tasks failed or timed out - bug may be present!")
        return 1
    else:
        print("✓ All tasks completed successfully")
        return 0


def _span_task(i):
    if i % 4 == 0:
        result = test_db_query.delay()
        task_name = f"db_query-{i}"
    elif i % 4 == 1:
        result = test_multiple_http_requests.delay()
        task_name = f"test_multiple_http_requests-{i}"
    elif i % 4 == 2:
        result = test_db_query_with_model.delay()
        task_name = f"db_model-{i}"
    else:
        result = test_mixed_operations.delay()
        task_name = f"mixed_ops-{i}"
    return result, task_name


def main():
    parser = argparse.ArgumentParser(
        description='Trigger Celery tasks to reproduce the gevent + langfuse + psycopg3 bug'
    )
    parser.add_argument(
        '--mode',
        choices=['simple', 'http', 'multiple', 'mixed', 'stress', 'long', 'all'],
        default='all',
        help='Test mode to run (default: all)'
    )
    parser.add_argument(
        '--concurrency',
        type=int,
        default=20,
        help='Number of concurrent tasks for stress test (default: 20)'
    )
    parser.add_argument(
        '--http-tasks',
        type=int,
        default=10,
        help='Number of HTTP tasks for stress test (default: 10)'
    )
    parser.add_argument(
        '--http-delay',
        type=int,
        default=1,
        help='Delay in seconds for HTTP requests (default: 1)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=60,
        help='Duration to run the "long" test for (seconds)'
    )

    args = parser.parse_args()

    try:
        if args.mode == 'simple' or args.mode == 'all':
            run_simple_tests()

        if args.mode == 'http' or args.mode == 'all':
            run_http_tests(num_tasks=5, delay=args.http_delay)

        if args.mode == 'multiple' or args.mode == 'all':
            run_multiple_request_tests(num_tasks=3, requests_per_task=3)

        if args.mode == 'mixed' or args.mode == 'all':
            run_mixed_operations_tests(num_tasks=5)

        if args.mode == 'stress' or args.mode == 'all':
            return run_stress_test(
                concurrency=args.concurrency,
                http_tasks=args.http_tasks
            )

        if args.mode == 'long':
            return run_long_test(
                concurrency=args.concurrency,
                duration=60
            )

        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130


if __name__ == '__main__':
    sys.exit(main())
