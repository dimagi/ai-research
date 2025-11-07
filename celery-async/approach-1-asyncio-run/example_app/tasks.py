"""
Celery tasks demonstrating asyncio.run() approach.

Key Pattern:
1. Use @shared_task decorator for standard synchronous Celery tasks
2. Call connections.close_all() BEFORE using asyncio.run()
3. Use asyncio.run() to execute async functions
4. Inside async functions, use Django's async ORM (acreate, aget, etc.)
"""
import asyncio
import logging
from celery import shared_task
from django.db import connections
from django.utils import timezone
import httpx

from .models import APILog, Task

logger = logging.getLogger(__name__)


@shared_task
def fetch_and_log_api():
    """
    Fetch multiple URLs asynchronously and log them to the database.

    This demonstrates the asyncio.run() approach with Django ORM.

    CRITICAL: We must call connections.close_all() before asyncio.run()
    to avoid database connection errors when mixing sync/async contexts.
    """
    logger.info("Starting fetch_and_log_api task")

    # CRITICAL: Close all database connections before entering async context
    # This prevents "SynchronousOnlyOperation" and connection errors
    connections.close_all()

    # Run the async function using asyncio.run()
    # This creates a new event loop, runs the coroutine, and closes the loop
    result = asyncio.run(async_fetch_and_log())

    logger.info(f"Task completed with {len(result)} results")
    return result


async def async_fetch_and_log():
    """
    Async function that performs HTTP requests and database operations.

    This function runs inside an event loop created by asyncio.run().
    It can use:
    - async HTTP clients (httpx)
    - Django async ORM (acreate, aget, aupdate, etc.)
    - asyncio features (gather, sleep, etc.)
    """
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/2",
        "https://httpbin.org/uuid",
        "https://httpbin.org/json",
    ]

    results = []

    # Create an async HTTP client
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Process each URL sequentially (you could also use asyncio.gather for parallel)
        for url in urls:
            start_time = timezone.now()

            try:
                logger.info(f"Fetching {url}")
                response = await client.get(url)
                response_time = (timezone.now() - start_time).total_seconds()

                logger.info(f"Got response from {url}: {response.status_code}")

                # Use Django async ORM to create database record
                # Note: acreate() is Django's async version of create()
                log = await APILog.objects.acreate(
                    url=url,
                    status_code=response.status_code,
                    response_time=response_time,
                )

                results.append({
                    'url': url,
                    'status': response.status_code,
                    'time': response_time,
                    'log_id': log.id,
                })

            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                results.append({
                    'url': url,
                    'error': str(e),
                })

    return results


@shared_task
def fetch_parallel():
    """
    Fetch multiple URLs in parallel using asyncio.gather().

    This demonstrates concurrent async operations.
    """
    logger.info("Starting parallel fetch task")

    # Close connections before async
    connections.close_all()

    result = asyncio.run(async_fetch_parallel())
    return result


async def async_fetch_parallel():
    """Fetch multiple URLs concurrently."""
    urls = [
        "https://httpbin.org/uuid",
        "https://httpbin.org/json",
        "https://httpbin.org/headers",
    ]

    # Create task record
    task_record = await Task.objects.acreate(
        name="Parallel Fetch",
        status="running",
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create tasks for all URLs
        fetch_tasks = [fetch_single_url(client, url) for url in urls]

        # Run all tasks concurrently
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    # Update task record
    task_record.status = "completed"
    task_record.result = [r for r in results if not isinstance(r, Exception)]
    task_record.completed_at = timezone.now()
    await task_record.asave()

    return task_record.result


async def fetch_single_url(client: httpx.AsyncClient, url: str):
    """Fetch a single URL and create a log entry."""
    start_time = timezone.now()

    try:
        response = await client.get(url)
        response_time = (timezone.now() - start_time).total_seconds()

        log = await APILog.objects.acreate(
            url=url,
            status_code=response.status_code,
            response_time=response_time,
        )

        return {
            'url': url,
            'status': response.status_code,
            'time': response_time,
            'log_id': log.id,
        }

    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return {
            'url': url,
            'error': str(e),
        }


@shared_task
def create_task_and_fetch():
    """
    Demonstrates mixing sync and async Django ORM operations.

    Shows how to:
    1. Use sync ORM before async context
    2. Use async ORM inside async context
    3. Handle the transition properly
    """
    logger.info("Creating task record (sync)")

    # We can use sync ORM here
    task_count_before = Task.objects.count()

    logger.info(f"Task count before: {task_count_before}")

    # Now switch to async context
    connections.close_all()

    result = asyncio.run(async_create_and_fetch())

    # After async context, we could use sync ORM again if needed
    # (though we'd need to be careful about connections)

    return {
        'task_count_before': task_count_before,
        'fetch_result': result,
    }


async def async_create_and_fetch():
    """Create a task record and fetch some data."""
    # Create task using async ORM
    task = await Task.objects.acreate(
        name="Fetch with Task Record",
        status="running",
    )

    # Fetch some data
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get("https://httpbin.org/uuid")

        log = await APILog.objects.acreate(
            url="https://httpbin.org/uuid",
            status_code=response.status_code,
            response_time=0.5,
        )

    # Update task
    task.status = "completed"
    task.result = {'log_id': log.id}
    task.completed_at = timezone.now()
    await task.asave()

    return {
        'task_id': task.id,
        'log_id': log.id,
    }
