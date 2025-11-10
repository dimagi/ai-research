#!/usr/bin/env python
"""
Celery worker entry point with early gevent monkey patching.

This ensures gevent patches are applied before ANY other imports,
which may affect SSL context initialization differently.

Usage:
    uv run python celery_worker_early_patch.py --pool=gevent --concurrency=10
"""

# CRITICAL: Patch BEFORE any other imports
from gevent import monkey
print("Applying gevent monkey patches BEFORE any imports...")
monkey.patch_all(aggressive=True)
print("Monkey patching complete")

# Print what's patched
print("\nPatched modules:")
for mod in ['socket', 'ssl', 'thread', 'time', 'select', 'subprocess', 'os']:
    patched = monkey.is_module_patched(mod)
    status = "✓" if patched else "✗"
    print(f"  {status} {mod}")
print()

# Now import celery and start worker
from celery.bin import worker
from bugrepro.celery import app

if __name__ == '__main__':
    worker.worker(app=app).execute_from_commandline()
