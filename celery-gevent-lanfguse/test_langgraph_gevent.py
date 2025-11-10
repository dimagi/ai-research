#!/usr/bin/env python
"""
Test the interaction between langgraph's threading and gevent's greenlets.

This is a critical test because:
1. Langgraph uses real threads internally
2. Gevent monkey patches thread-related modules
3. SSL context is stored in thread-local storage
4. OTEL context propagation also uses thread-locals

The combination could cause SSL verification failures when:
- A greenlet is switched while in a thread
- SSL context is accessed from the wrong thread-local
- Connection pool returns a connection with incorrect SSL context
"""

import os
import sys

# Apply gevent monkey patching EARLY
from gevent import monkey
monkey.patch_all(aggressive=True)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bugrepro.settings')
django.setup()

import gevent
from typing import TypedDict
from django.db import connection
from testapp.langfuse import get_random_langfuse_account

# Langgraph imports (uses threads internally)
from langgraph.graph import StateGraph, END


class GraphState(TypedDict):
    """State for our simple graph."""
    task_id: int
    db_query_result: str
    ssl_info: dict
    error: str | None


def db_query_node(state: GraphState) -> GraphState:
    """Node that performs a database query."""
    task_id = state["task_id"]

    try:
        tracer = get_random_langfuse_account()
        with tracer.trace(f"langgraph_db_{task_id}") as span:
            # Force new connection sometimes
            if task_id % 3 == 0:
                connection.close()

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        pg_backend_pid() as pid,
                        (SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()) as ssl_used,
                        (SELECT version FROM pg_stat_ssl WHERE pid = pg_backend_pid()) as ssl_version,
                        current_database() as db
                """)
                pid, ssl_used, ssl_version, db = cursor.fetchone()

                result = f"PID={pid}, DB={db}, SSL={ssl_used}"

                span.set_outputs({
                    "pid": pid,
                    "ssl_used": ssl_used,
                    "task_id": task_id
                })

                state["db_query_result"] = result
                state["ssl_info"] = {
                    "pid": pid,
                    "ssl_used": ssl_used,
                    "ssl_version": ssl_version,
                }
                state["error"] = None

    except Exception as e:
        state["db_query_result"] = f"ERROR: {e}"
        state["error"] = str(e)

    return state


def http_request_node(state: GraphState) -> GraphState:
    """Node that makes an HTTP request (adds I/O delay)."""
    import requests

    try:
        # Make a simple HTTP request to add delay
        response = requests.get("https://httpbin.org/delay/0.1", timeout=5)
        state["http_status"] = response.status_code
    except Exception as e:
        state["http_status"] = None
        if not state["error"]:
            state["error"] = f"HTTP error: {e}"

    return state


def create_workflow():
    """Create a simple langgraph workflow."""
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("db_query", db_query_node)
    workflow.add_node("http_request", http_request_node)

    # Define edges
    workflow.set_entry_point("db_query")
    workflow.add_edge("db_query", "http_request")
    workflow.add_edge("http_request", END)

    return workflow.compile()


def run_workflow_in_greenlet(greenlet_id, app):
    """Run the langgraph workflow in a greenlet."""
    try:
        initial_state = GraphState(
            task_id=greenlet_id,
            db_query_result="",
            ssl_info={},
            error=None
        )

        # Run the workflow - this may use threads internally
        result = app.invoke(initial_state)

        if result["error"]:
            print(f"  Greenlet {greenlet_id}: ✗ {result['error']}")
            return False
        else:
            print(f"  Greenlet {greenlet_id}: ✓ {result['db_query_result']}")
            return True

    except Exception as e:
        print(f"  Greenlet {greenlet_id}: ✗ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_langgraph_with_gevent(num_greenlets=20, num_rounds=3):
    """Test langgraph workflows running in concurrent greenlets."""
    print("\n" + "="*70)
    print("TESTING LANGGRAPH THREADS + GEVENT GREENLETS")
    print("="*70)

    print("\nMonkey patching status:")
    for mod in ['socket', 'ssl', 'thread', 'time']:
        status = "✓" if monkey.is_module_patched(mod) else "✗"
        print(f"  {status} {mod}")

    print(f"\nCreating langgraph workflow...")
    app = create_workflow()
    print("✓ Workflow created")

    total_success = 0
    total_failed = 0

    for round_num in range(num_rounds):
        print(f"\n{'='*70}")
        print(f"ROUND {round_num + 1}/{num_rounds} - {num_greenlets} concurrent greenlets")
        print(f"{'='*70}\n")

        results = []

        def run_and_store(gid):
            success = run_workflow_in_greenlet(gid, app)
            results.append(success)

        # Spawn all greenlets at once
        greenlets = [
            gevent.spawn(run_and_store, round_num * num_greenlets + i)
            for i in range(num_greenlets)
        ]

        # Wait for all to complete
        gevent.joinall(greenlets, timeout=60)

        success_count = sum(1 for r in results if r)
        failed_count = len(results) - success_count

        total_success += success_count
        total_failed += failed_count

        print(f"\nRound {round_num + 1} results: {success_count}/{num_greenlets} successful")

        # Small delay between rounds
        gevent.sleep(0.1)

    print(f"\n{'='*70}")
    print("FINAL RESULTS")
    print(f"{'='*70}")
    print(f"Total successful: {total_success}")
    print(f"Total failed: {total_failed}")
    print(f"Success rate: {total_success / (total_success + total_failed) * 100:.1f}%")
    print(f"{'='*70}\n")

    return total_failed == 0


def test_concurrent_workflows(num_concurrent=10):
    """
    Run multiple workflow instances concurrently with rapid context switching.

    This creates maximum stress by having many workflows active simultaneously,
    each potentially using threads while greenlets are switching contexts.
    """
    print("\n" + "="*70)
    print("TESTING CONCURRENT WORKFLOW EXECUTION")
    print("="*70)
    print(f"\nRunning {num_concurrent} workflows concurrently with rapid context switches...\n")

    app = create_workflow()
    errors = []
    success_count = [0]

    def run_workflow_with_switches(worker_id):
        """Run workflow with frequent context switches."""
        for i in range(5):  # Each worker runs 5 workflows
            try:
                task_id = worker_id * 100 + i
                initial_state = GraphState(
                    task_id=task_id,
                    db_query_result="",
                    ssl_info={},
                    error=None
                )

                # Force context switch before running
                gevent.sleep(0)

                result = app.invoke(initial_state)

                # Force context switch after running
                gevent.sleep(0)

                if result["error"]:
                    errors.append((task_id, result["error"]))
                    print(f"  Worker {worker_id}, Task {i}: ✗")
                else:
                    success_count[0] += 1
                    print(f"  Worker {worker_id}, Task {i}: ✓")

            except Exception as e:
                errors.append((worker_id, str(e)))
                print(f"  Worker {worker_id}, Task {i}: ✗ Exception: {e}")

    # Spawn concurrent workers
    greenlets = [
        gevent.spawn(run_workflow_with_switches, i)
        for i in range(num_concurrent)
    ]

    gevent.joinall(greenlets, timeout=120)

    total_attempts = num_concurrent * 5
    print(f"\n{'='*70}")
    print(f"Results: {success_count[0]}/{total_attempts} successful")
    if errors:
        print(f"\nFirst 5 errors:")
        for task_id, err in errors[:5]:
            print(f"  Task {task_id}: {err}")
    print(f"{'='*70}\n")

    return len(errors) == 0


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Test langgraph threading with gevent greenlets'
    )
    parser.add_argument(
        '--test',
        choices=['basic', 'concurrent', 'all'],
        default='all',
        help='Test to run (default: all)'
    )
    parser.add_argument(
        '--greenlets',
        type=int,
        default=20,
        help='Number of concurrent greenlets (default: 20)'
    )
    parser.add_argument(
        '--rounds',
        type=int,
        default=3,
        help='Number of rounds for basic test (default: 3)'
    )

    args = parser.parse_args()

    all_passed = True

    if args.test in ['basic', 'all']:
        passed = test_langgraph_with_gevent(args.greenlets, args.rounds)
        all_passed = all_passed and passed

    if args.test in ['concurrent', 'all']:
        passed = test_concurrent_workflows(args.greenlets)
        all_passed = all_passed and passed

    if all_passed:
        print("\n✓ All tests PASSED\n")
        return 0
    else:
        print("\n✗ Some tests FAILED - bug may be present!\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
