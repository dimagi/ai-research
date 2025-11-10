#!/usr/bin/env python
"""
Experiment with different gevent monkey patching configurations.

This script tests various patching orders and module combinations to help
identify the specific interaction that causes SSL verification issues.

Each strategy runs in a separate process to avoid interference.
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


def run_single_strategy(strategy_name, num_attempts):
    """Run a single strategy test (called from subprocess)."""
    apply_patching(strategy_name)
    success = test_db_connection(num_attempts)
    return 0 if success else 1


def run_all_strategies(num_attempts):
    """Run all strategies in separate processes."""
    import subprocess

    print("\n" + "="*70)
    print("RUNNING ALL PATCHING STRATEGIES IN SEPARATE PROCESSES")
    print("="*70)
    print("\nThis ensures each strategy runs in a clean Python environment")
    print("without interference from previous monkey patching.\n")

    results = {}

    for strategy_name in PATCHING_STRATEGIES.keys():
        print(f"\n{'='*70}")
        print(f"Starting subprocess for strategy: {strategy_name}")
        print(f"{'='*70}\n")

        # Run this script in a subprocess with --internal-run flag
        cmd = [
            sys.executable,
            __file__,
            '--internal-run',
            '--strategy', strategy_name,
            '--attempts', str(num_attempts)
        ]

        result = subprocess.run(cmd, capture_output=False, text=True)
        results[strategy_name] = (result.returncode == 0)

        print(f"\n{'='*70}")
        if result.returncode == 0:
            print(f"✓ Strategy '{strategy_name}' PASSED")
        else:
            print(f"✗ Strategy '{strategy_name}' FAILED (exit code: {result.returncode})")
        print(f"{'='*70}\n")

    # Final summary
    print("\n" + "="*70)
    print("FINAL SUMMARY - ALL STRATEGIES")
    print("="*70)
    for strategy, success in results.items():
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"{strategy:20} {status}")
    print("="*70 + "\n")

    if all(results.values()):
        print("✓ All strategies passed!")
        return 0
    else:
        failed = [s for s, success in results.items() if not success]
        print(f"⚠️  {len(failed)} strateg{'y' if len(failed) == 1 else 'ies'} failed: {', '.join(failed)}")
        return 1


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Test different gevent monkey patching strategies in isolated processes'
    )
    parser.add_argument(
        '--strategy',
        choices=list(PATCHING_STRATEGIES.keys()) + ['all'],
        default='all',
        help='Patching strategy to test (default: all, runs each in separate process)'
    )
    parser.add_argument(
        '--attempts',
        type=int,
        default=10,
        help='Number of connection attempts per strategy (default: 10)'
    )
    parser.add_argument(
        '--internal-run',
        action='store_true',
        help='Internal flag: run single strategy (called from subprocess)'
    )

    args = parser.parse_args()

    # Internal run mode: execute single strategy and exit
    if args.internal_run:
        if args.strategy == 'all':
            print("Error: --internal-run requires specific strategy", file=sys.stderr)
            return 1
        return run_single_strategy(args.strategy, args.attempts)

    # Normal mode: either run all strategies in subprocesses or single strategy
    if args.strategy == 'all':
        return run_all_strategies(args.attempts)
    else:
        # Single strategy requested - run directly (no subprocess needed)
        return run_single_strategy(args.strategy, args.attempts)


if __name__ == '__main__':
    sys.exit(main())
