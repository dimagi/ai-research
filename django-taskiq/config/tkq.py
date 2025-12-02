"""
Taskiq configuration for Django integration.

This module sets up the taskiq broker and handles Django database connection management.
"""
import os
import django
from functools import wraps
from taskiq import InMemoryBroker
from taskiq_redis import RedisAsyncResultBackend, ListQueueBroker

# Initialize Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Import Django-specific modules after django.setup()
from django.db import connection, connections
from django.core.management import call_command


# For development, we'll use InMemoryBroker (no Redis required)
# For production, uncomment the Redis broker configuration below
broker = InMemoryBroker()

# Production configuration with Redis (uncomment when Redis is available):
# broker = ListQueueBroker(
#     url="redis://localhost:6379",
# ).with_result_backend(
#     RedisAsyncResultBackend(
#         redis_url="redis://localhost:6379",
#     )
# )


# Critical: Database connection management for Django + Taskiq
# Django connections are thread-local and don't work well with async workers
# We need to properly close connections before and after task execution

@broker.on_event("worker_startup")
async def worker_startup(state):
    """
    Called when a worker starts up.
    Ensures Django is properly initialized.
    """
    print("Worker starting up...")
    # Close any existing connections
    connections.close_all()
    print("Worker startup complete")


@broker.on_event("worker_shutdown")
async def worker_shutdown(state):
    """
    Called when a worker shuts down.
    Ensures all database connections are closed.
    """
    print("Worker shutting down...")
    connections.close_all()
    print("Worker shutdown complete")


# Note: task_preprocessor and task_postprocessor are not available on InMemoryBroker
# For production with Redis/RabbitMQ, these hooks are available and should be used.
# For now, we'll handle connection management within the tasks themselves using a decorator.

# Uncomment these when using a production broker:
# @broker.task_preprocessor
# async def close_old_connections(context):
#     """
#     Close database connections before each task execution.
#     This prevents stale connections and thread-safety issues.
#     """
#     connections.close_all()
#
#
# @broker.task_postprocessor
# async def close_connections_after_task(context):
#     """
#     Close database connections after each task execution.
#     This is critical for proper connection management in async environments.
#     """
#     connections.close_all()


# Decorator for proper database connection management
def with_db_connection_management(func):
    """
    Decorator to ensure proper database connection management.

    This wraps task functions to:
    1. Close stale connections before execution
    2. Close connections after execution
    3. Handle errors gracefully

    Use this on tasks that interact with the database.
    """
    import asyncio

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            # Close any existing connections before starting (in thread to avoid async context issues)
            await asyncio.to_thread(connections.close_all)

            # Execute the task
            result = await func(*args, **kwargs)

            return result
        finally:
            # Always close connections after task execution (in thread to avoid async context issues)
            try:
                await asyncio.to_thread(connections.close_all)
            except Exception:
                pass  # Ignore errors during cleanup

    return wrapper


# Helper function to ensure database is migrated
def ensure_migrations():
    """Run migrations if needed."""
    try:
        call_command('migrate', '--check')
        print("Database migrations are up to date")
    except Exception as e:
        print(f"Running migrations: {e}")
        call_command('migrate')
