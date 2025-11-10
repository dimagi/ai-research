#!/usr/bin/env python
"""
Test connection pool behavior under stress with gevent + langfuse.

This script aggressively creates/closes connections and uses greenlets
to try to trigger race conditions in SSL context management.
"""

import os
import sys

# Apply gevent monkey patching early
from gevent import monkey
monkey.patch_all(aggressive=True)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bugrepro.settings')
django.setup()

import gevent
from django.db import connection, connections
from django.db.utils import OperationalError
from testapp.langfuse import get_random_langfuse_account
import time


def test_connection_cycling(iterations=100):
    """Rapidly open and close connections to stress the connection pool."""
    print(f"\n{'='*60}")
    print(f"TEST 1: Connection Cycling ({iterations} iterations)")
    print(f"{'='*60}\n")

    errors = []

    for i in range(iterations):
        try:
            tracer = get_random_langfuse_account()
            with tracer.trace(f"cycle_{i}") as span:
                # Close existing connection
                connection.close()

                # Open new connection
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT pg_backend_pid() as pid,
                               (SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()) as ssl_used
                    """)
                    pid, ssl_used = cursor.fetchone()
                    span.set_outputs({"pid": pid, "ssl": ssl_used})

                print(f"  {i+1}. ✓ PID={pid}, SSL={ssl_used}")

        except Exception as e:
            print(f"  {i+1}. ✗ Error: {e}")
            errors.append((i, str(e)))

    print(f"\n{'='*60}")
    print(f"Connection Cycling: {iterations - len(errors)}/{iterations} successful")
    if errors:
        print(f"Errors: {len(errors)}")
        for idx, err in errors[:5]:  # Show first 5 errors
            print(f"  Iteration {idx}: {err}")
    print(f"{'='*60}\n")

    return len(errors) == 0


def test_concurrent_connections(num_greenlets=20):
    """Test many concurrent database connections from different greenlets."""
    print(f"\n{'='*60}")
    print(f"TEST 2: Concurrent Connections ({num_greenlets} greenlets)")
    print(f"{'='*60}\n")

    errors = []
    success_count = [0]  # Use list for mutability in nested function

    def make_connection(greenlet_id):
        try:
            tracer = get_random_langfuse_account()
            with tracer.trace(f"greenlet_{greenlet_id}") as span:
                # Each greenlet gets its own connection
                with connections['default'].cursor() as cursor:
                    cursor.execute("""
                        SELECT
                            pg_backend_pid() as pid,
                            (SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()) as ssl_used,
                            current_database() as db,
                            version() as version
                    """)
                    pid, ssl_used, db, version = cursor.fetchone()
                    span.set_outputs({
                        "pid": pid,
                        "ssl": ssl_used,
                        "greenlet": greenlet_id
                    })

                print(f"  Greenlet {greenlet_id}: ✓ PID={pid}, SSL={ssl_used}")
                success_count[0] += 1

        except Exception as e:
            print(f"  Greenlet {greenlet_id}: ✗ Error: {e}")
            errors.append((greenlet_id, str(e)))

    # Spawn greenlets
    greenlets = [gevent.spawn(make_connection, i) for i in range(num_greenlets)]

    # Wait for all to complete
    gevent.joinall(greenlets, timeout=30)

    print(f"\n{'='*60}")
    print(f"Concurrent Connections: {success_count[0]}/{num_greenlets} successful")
    if errors:
        print(f"Errors: {len(errors)}")
        for gid, err in errors[:5]:
            print(f"  Greenlet {gid}: {err}")
    print(f"{'='*60}\n")

    return len(errors) == 0


def test_mixed_operations(iterations=50):
    """Mix connection operations with langfuse tracing in greenlets."""
    print(f"\n{'='*60}")
    print(f"TEST 3: Mixed Operations ({iterations} iterations)")
    print(f"{'='*60}\n")

    errors = []
    success_count = [0]

    def mixed_operation(op_id):
        try:
            tracer = get_random_langfuse_account()

            # Random delay to increase timing variations
            gevent.sleep(0.001 * (op_id % 10))

            with tracer.trace(f"mixed_{op_id}") as span:
                # Alternate between different connection operations
                if op_id % 3 == 0:
                    # Force new connection
                    connection.close()

                with connection.cursor() as cursor:
                    if op_id % 2 == 0:
                        # Complex query with SSL info from pg_stat_ssl
                        cursor.execute("""
                            SELECT
                                pg_backend_pid() as pid,
                                (SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()) as ssl_used,
                                (SELECT version FROM pg_stat_ssl WHERE pid = pg_backend_pid()) as ssl_version,
                                (SELECT cipher FROM pg_stat_ssl WHERE pid = pg_backend_pid()) as ssl_cipher
                        """)
                    else:
                        # Simple query
                        cursor.execute("SELECT 1")

                    result = cursor.fetchone()
                    span.set_outputs({"result": str(result)[:100]})

                print(f"  {op_id}. ✓")
                success_count[0] += 1

        except Exception as e:
            print(f"  {op_id}. ✗ Error: {e}")
            errors.append((op_id, str(e)))

    # Spawn all greenlets at once
    greenlets = [gevent.spawn(mixed_operation, i) for i in range(iterations)]
    gevent.joinall(greenlets, timeout=60)

    print(f"\n{'='*60}")
    print(f"Mixed Operations: {success_count[0]}/{iterations} successful")
    if errors:
        print(f"Errors: {len(errors)}")
        for idx, err in errors[:5]:
            print(f"  Operation {idx}: {err}")
    print(f"{'='*60}\n")

    return len(errors) == 0


def test_rapid_context_switches(duration=10):
    """Rapidly switch between greenlets while doing DB operations."""
    print(f"\n{'='*60}")
    print(f"TEST 4: Rapid Context Switches ({duration}s)")
    print(f"{'='*60}\n")

    errors = []
    operation_count = [0]
    start_time = time.time()

    def rapid_operation(worker_id):
        while time.time() - start_time < duration:
            try:
                tracer = get_random_langfuse_account()
                with tracer.trace(f"rapid_{worker_id}_{operation_count[0]}") as span:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_backend_pid()")
                        pid = cursor.fetchone()[0]
                        span.set_outputs({"pid": pid})

                    operation_count[0] += 1

                    # Force context switch
                    gevent.sleep(0)

            except Exception as e:
                errors.append((worker_id, str(e)))
                print(f"  Worker {worker_id}: ✗ Error: {e}")

    # Spawn 10 workers that continuously do operations
    num_workers = 10
    greenlets = [gevent.spawn(rapid_operation, i) for i in range(num_workers)]
    gevent.joinall(greenlets, timeout=duration + 2)

    print(f"\n{'='*60}")
    print(f"Rapid Context Switches: {operation_count[0]} operations completed")
    print(f"Errors: {len(errors)}")
    if errors:
        for wid, err in errors[:5]:
            print(f"  Worker {wid}: {err}")
    print(f"{'='*60}\n")

    return len(errors) == 0


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Test connection pool behavior with gevent + langfuse'
    )
    parser.add_argument(
        '--test',
        choices=['cycling', 'concurrent', 'mixed', 'rapid', 'all'],
        default='all',
        help='Test to run (default: all)'
    )
    parser.add_argument(
        '--cycles',
        type=int,
        default=100,
        help='Number of connection cycles (default: 100)'
    )
    parser.add_argument(
        '--greenlets',
        type=int,
        default=20,
        help='Number of concurrent greenlets (default: 20)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=10,
        help='Duration for rapid context switch test (default: 10s)'
    )

    args = parser.parse_args()

    print("\n" + "="*60)
    print("CONNECTION POOL STRESS TEST")
    print("="*60)
    print("\nMonkey patching status:")
    from gevent import monkey
    for mod in ['socket', 'ssl', 'thread']:
        status = "✓" if monkey.is_module_patched(mod) else "✗"
        print(f"  {status} {mod}")
    print()

    results = {}

    if args.test in ['cycling', 'all']:
        results['cycling'] = test_connection_cycling(args.cycles)

    if args.test in ['concurrent', 'all']:
        results['concurrent'] = test_concurrent_connections(args.greenlets)

    if args.test in ['mixed', 'all']:
        results['mixed'] = test_mixed_operations(args.cycles // 2)

    if args.test in ['rapid', 'all']:
        results['rapid'] = test_rapid_context_switches(args.duration)

    # Summary
    print("\n" + "="*60)
    print("OVERALL SUMMARY")
    print("="*60)
    for test_name, success in results.items():
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"{test_name:20} {status}")
    print("="*60 + "\n")

    if not all(results.values()):
        print("⚠️  Some tests FAILED - bug may be present!")
        return 1
    else:
        print("✓ All tests PASSED")
        return 0


if __name__ == '__main__':
    sys.exit(main())
