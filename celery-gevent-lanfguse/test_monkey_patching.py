#!/usr/bin/env python
"""
Experiment with different gevent monkey patching configurations.

This script tests various patching orders and module combinations to help
identify the specific interaction that causes SSL verification issues.
"""

import sys
import os

# Configuration for different patching strategies
PATCHING_STRATEGIES = {
    'early_aggressive': {
        'description': 'Patch everything as early as possible',
        'patch_before_imports': True,
        'modules': ['socket', 'ssl', 'thread', 'time', 'select', 'subprocess'],
        'aggressive': True,
    },
    'early_minimal': {
        'description': 'Patch only socket/ssl early',
        'patch_before_imports': True,
        'modules': ['socket', 'ssl'],
        'aggressive': False,
    },
    'late_aggressive': {
        'description': 'Import Django/OTEL first, then patch everything',
        'patch_before_imports': False,
        'modules': ['socket', 'ssl', 'thread', 'time', 'select', 'subprocess'],
        'aggressive': True,
    },
    'late_minimal': {
        'description': 'Import Django/OTEL first, then patch only socket/ssl',
        'patch_before_imports': False,
        'modules': ['socket', 'ssl'],
        'aggressive': False,
    },
    'ssl_only': {
        'description': 'Patch only SSL module',
        'patch_before_imports': True,
        'modules': ['ssl'],
        'aggressive': False,
    },
    'no_ssl': {
        'description': 'Patch everything except SSL',
        'patch_before_imports': True,
        'modules': ['socket', 'thread', 'time', 'select', 'subprocess'],
        'aggressive': False,
    },
}


def apply_patching(strategy_name):
    """Apply monkey patching according to the specified strategy."""
    from gevent import monkey

    strategy = PATCHING_STRATEGIES[strategy_name]

    print(f"\n{'='*60}")
    print(f"PATCHING STRATEGY: {strategy_name}")
    print(f"Description: {strategy['description']}")
    print(f"{'='*60}\n")

    if strategy['patch_before_imports']:
        print("Applying patches BEFORE Django/OTEL imports...")
        if strategy['aggressive']:
            print("Using patch_all(aggressive=True)...")
            monkey.patch_all(aggressive=True)
        else:
            print(f"Patching modules: {strategy['modules']}")
            for module in strategy['modules']:
                if module == 'socket':
                    monkey.patch_socket()
                elif module == 'ssl':
                    monkey.patch_ssl()
                elif module == 'thread':
                    monkey.patch_thread()
                elif module == 'time':
                    monkey.patch_time()
                elif module == 'select':
                    monkey.patch_select()
                elif module == 'subprocess':
                    monkey.patch_subprocess()

    # Now import Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bugrepro.settings')
    import django
    django.setup()

    if not strategy['patch_before_imports']:
        print("Applying patches AFTER Django/OTEL imports...")
        if strategy['aggressive']:
            print("Using patch_all(aggressive=True)...")
            monkey.patch_all(aggressive=True)
        else:
            print(f"Patching modules: {strategy['modules']}")
            for module in strategy['modules']:
                if module == 'socket' and not monkey.is_module_patched('socket'):
                    monkey.patch_socket()
                elif module == 'ssl' and not monkey.is_module_patched('ssl'):
                    monkey.patch_ssl()
                elif module == 'thread' and not monkey.is_module_patched('thread'):
                    monkey.patch_thread()
                elif module == 'time' and not monkey.is_module_patched('time'):
                    monkey.patch_time()
                elif module == 'select' and not monkey.is_module_patched('select'):
                    monkey.patch_select()
                elif module == 'subprocess' and not monkey.is_module_patched('subprocess'):
                    monkey.patch_subprocess()

    # Show what's patched
    print("\nPatched modules:")
    for mod in ['socket', 'ssl', 'thread', 'time', 'select', 'subprocess', 'os']:
        patched = monkey.is_module_patched(mod)
        status = "✓" if patched else "✗"
        print(f"  {status} {mod}")
    print()


def test_db_connection(num_attempts=10):
    """Test database connections with the current patching strategy."""
    from django.db import connection
    from testapp.langfuse import get_random_langfuse_account
    import time

    print(f"Testing {num_attempts} database connections with langfuse tracing...\n")

    success_count = 0
    error_count = 0

    for i in range(num_attempts):
        try:
            tracer = get_random_langfuse_account()
            with tracer.trace(f"test_connection_{i}") as span:
                # Force new connection
                connection.close()

                with connection.cursor() as cursor:
                    cursor.execute("SELECT version(), pg_backend_pid()")
                    version, pid = cursor.fetchone()
                    span.set_outputs({"backend_pid": pid})

                print(f"  {i+1}. ✓ Connection successful (PID: {pid})")
                success_count += 1

            # Small delay to allow context switching
            time.sleep(0.01)

        except Exception as e:
            print(f"  {i+1}. ✗ Connection failed: {e}")
            error_count += 1
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Results: {success_count}/{num_attempts} successful, {error_count} failed")
    print(f"{'='*60}\n")

    return error_count == 0


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Test different gevent monkey patching strategies'
    )
    parser.add_argument(
        '--strategy',
        choices=list(PATCHING_STRATEGIES.keys()) + ['all'],
        default='all',
        help='Patching strategy to test (default: all)'
    )
    parser.add_argument(
        '--attempts',
        type=int,
        default=10,
        help='Number of connection attempts per strategy (default: 10)'
    )

    args = parser.parse_args()

    strategies = [args.strategy] if args.strategy != 'all' else list(PATCHING_STRATEGIES.keys())

    results = {}

    for strategy in strategies:
        # Each strategy needs a fresh process, so we document this
        if len(strategies) > 1 and strategy != strategies[0]:
            print("\n" + "!"*60)
            print("NOTE: Testing multiple strategies requires separate runs")
            print("      due to the persistent nature of monkey patching.")
            print("      Please run this script multiple times with --strategy")
            print("!"*60 + "\n")
            print(f"To test '{strategy}', run:")
            print(f"  uv run python test_monkey_patching.py --strategy {strategy}")
            print()
            continue

        apply_patching(strategy)
        success = test_db_connection(args.attempts)
        results[strategy] = success

        # Can only test one strategy per process
        break

    # Summary
    if results:
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for strategy, success in results.items():
            status = "✓ SUCCESS" if success else "✗ FAILED"
            print(f"{strategy:20} {status}")
        print("="*60 + "\n")

    return 0 if all(results.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
