"""
Celery tasks demonstrating Django's async_to_sync/sync_to_async approach.

Key Pattern:
1. Use @shared_task decorator for standard synchronous Celery tasks
2. Use async_to_sync() to wrap and execute async functions
3. Use sync_to_async() if you need to call sync Django ORM from async code
4. thread_sensitive=True ensures proper thread-local state handling

This is Django's official approach for bridging sync and async code.
"""
import logging
from celery import shared_task
from asgiref.sync import async_to_sync, sync_to_async
from django.utils import timezone
import httpx

from .models import APILog, Task

logger = logging.getLogger(__name__)


@shared_task
def fetch_and_log_api():
    """
    Fetch multiple URLs asynchronously and log them to the database.

    This demonstrates the async_to_sync approach with Django ORM.

    Note: No need to call connections.close_all() with async_to_sync!
    Django's asgiref handles thread management automatically.
    """
    logger.info("Starting fetch_and_log_api task")

    # Use async_to_sync to run the async function
    # thread_sensitive=True ensures proper handling of Django's thread-local state
    result = async_to_sync(async_fetch_and_log, thread_sensitive=True)()

    logger.info(f"Task completed with {len(result)} results")
    return result


async def async_fetch_and_log():
    """
    Async function that performs HTTP requests and database operations.

    This function is wrapped by async_to_sync() and runs with proper
    thread-local state management thanks to asgiref.
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
        # Process each URL
        for url in urls:
            start_time = timezone.now()

            try:
                logger.info(f"Fetching {url}")
                response = await client.get(url)
                response_time = (timezone.now() - start_time).total_seconds()

                logger.info(f"Got response from {url}: {response.status_code}")

                # Use Django async ORM
                # async_to_sync handles the event loop and thread state
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

    Demonstrates concurrent async operations with async_to_sync.
    """
    logger.info("Starting parallel fetch task")

    result = async_to_sync(async_fetch_parallel, thread_sensitive=True)()
    return result


async def async_fetch_parallel():
    """Fetch multiple URLs concurrently."""
    import asyncio

    urls = [
        "https://httpbin.org/uuid",
        "https://httpbin.org/json",
        "https://httpbin.org/headers",
    ]

    # Create task record using async ORM
    task_record = await Task.objects.acreate(
        name="Parallel Fetch (async_to_sync)",
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
def mixed_sync_async_task():
    """
    Demonstrates mixing sync and async code elegantly.

    Shows how to:
    1. Use sync Django ORM in the task
    2. Call async code with async_to_sync
    3. Go back to sync code
    4. Call async code again

    This is more natural than the asyncio.run() approach.
    """
    logger.info("Starting mixed sync/async task")

    # Sync Django ORM - works normally
    task_count_before = Task.objects.count()
    api_log_count_before = APILog.objects.count()

    logger.info(f"Task count before: {task_count_before}")
    logger.info(f"API log count before: {api_log_count_before}")

    # Call async code
    fetch_result = async_to_sync(fetch_data_async, thread_sensitive=True)()

    # Back to sync code - can use ORM again
    task_count_after = Task.objects.count()

    return {
        'task_count_before': task_count_before,
        'task_count_after': task_count_after,
        'api_log_count_before': api_log_count_before,
        'fetch_result': fetch_result,
    }


async def fetch_data_async():
    """Pure async function that fetches data and creates records."""
    async with httpx.AsyncClient() as client:
        response = await client.get("https://httpbin.org/uuid")
        data = response.json()

        # Create records
        log = await APILog.objects.acreate(
            url="https://httpbin.org/uuid",
            status_code=response.status_code,
            response_time=0.5,
        )

        task = await Task.objects.acreate(
            name="Mixed Sync/Async Task",
            status="completed",
            result={'uuid': data.get('uuid')},
            completed_at=timezone.now(),
        )

        return {
            'log_id': log.id,
            'task_id': task.id,
            'uuid': data.get('uuid'),
        }


@shared_task
def using_sync_to_async():
    """
    Demonstrates using sync_to_async to call sync functions from async code.

    This is useful when you have:
    - Legacy sync functions that need to be called from async code
    - Third-party libraries that are sync-only
    - Mix of sync Django ORM and async operations
    """
    logger.info("Starting sync_to_async demo")

    result = async_to_sync(demo_sync_to_async, thread_sensitive=True)()
    return result


async def demo_sync_to_async():
    """
    Demonstrates calling sync functions from async context.
    """
    import asyncio

    # You can call sync Django ORM using sync_to_async
    # This is useful if you have a complex sync ORM query
    # that you don't want to rewrite with async ORM

    @sync_to_async
    def get_task_count():
        """Sync function that uses Django ORM."""
        return Task.objects.count()

    @sync_to_async
    def get_latest_log():
        """Sync function that uses Django ORM."""
        return APILog.objects.first()

    # Call sync functions from async context
    task_count = await get_task_count()

    # You can also mix with async HTTP
    async with httpx.AsyncClient() as client:
        response = await client.get("https://httpbin.org/json")

    # Create record with async ORM
    task = await Task.objects.acreate(
        name="sync_to_async Demo",
        status="completed",
        result={
            'task_count': task_count,
            'status_code': response.status_code,
        },
        completed_at=timezone.now(),
    )

    # Call another sync function
    latest_log = await get_latest_log()

    return {
        'task_id': task.id,
        'task_count': task_count,
        'latest_log_id': latest_log.id if latest_log else None,
    }


@shared_task
def complex_workflow():
    """
    Demonstrates a complex workflow mixing sync and async operations.

    This shows the power of async_to_sync/sync_to_async for
    real-world scenarios.
    """
    logger.info("Starting complex workflow")

    # Sync: Check preconditions
    initial_state = {
        'tasks': Task.objects.count(),
        'logs': APILog.objects.count(),
    }

    # Async: Fetch multiple APIs in parallel
    fetch_results = async_to_sync(
        parallel_api_calls,
        thread_sensitive=True
    )()

    # Sync: Process results
    successful = [r for r in fetch_results if 'error' not in r]
    failed = [r for r in fetch_results if 'error' in r]

    # Async: Create summary record
    summary = async_to_sync(
        create_summary_record,
        thread_sensitive=True
    )(successful, failed)

    # Sync: Final state
    final_state = {
        'tasks': Task.objects.count(),
        'logs': APILog.objects.count(),
    }

    return {
        'initial_state': initial_state,
        'final_state': final_state,
        'successful': len(successful),
        'failed': len(failed),
        'summary': summary,
    }


async def parallel_api_calls():
    """Make multiple API calls in parallel."""
    import asyncio

    urls = [
        "https://httpbin.org/uuid",
        "https://httpbin.org/json",
        "https://httpbin.org/headers",
        "https://httpbin.org/user-agent",
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [fetch_single_url(client, url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return [r for r in results if not isinstance(r, Exception)]


async def create_summary_record(successful, failed):
    """Create a summary task record."""
    task = await Task.objects.acreate(
        name="Complex Workflow Summary",
        status="completed",
        result={
            'successful_count': len(successful),
            'failed_count': len(failed),
            'successful_urls': [r['url'] for r in successful],
        },
        completed_at=timezone.now(),
    )

    return {
        'task_id': task.id,
        'successful': len(successful),
        'failed': len(failed),
    }
