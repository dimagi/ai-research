"""
Celery tasks demonstrating threading with async code approach.

Key Pattern:
1. Use @shared_task for standard synchronous Celery tasks
2. Use ThreadPoolExecutor to run async code in separate threads
3. Each thread runs asyncio.run() with its own event loop
4. Close database connections before asyncio.run() in each thread
5. Can run multiple async operations in parallel threads

This approach provides maximum isolation between async operations.
"""
import asyncio
import concurrent.futures
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
    Fetch URLs using async code running in a dedicated thread.

    This demonstrates running async code in a separate thread
    with ThreadPoolExecutor.
    """
    logger.info("Starting fetch_and_log_api task")

    # Run async code in a thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_async_in_thread)
        result = future.result(timeout=60)

    logger.info(f"Task completed with {len(result)} results")
    return result


def _run_async_in_thread():
    """
    This function runs in a separate thread.

    It has its own event loop and can run async code safely.
    """
    # Close connections before creating event loop in this thread
    connections.close_all()

    # Create and run event loop in this thread
    return asyncio.run(async_fetch_and_log())


async def async_fetch_and_log():
    """Async function that performs HTTP requests and database operations."""
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/2",
        "https://httpbin.org/uuid",
        "https://httpbin.org/json",
    ]

    results = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in urls:
            start_time = timezone.now()

            try:
                logger.info(f"Fetching {url}")
                response = await client.get(url)
                response_time = (timezone.now() - start_time).total_seconds()

                logger.info(f"Got response from {url}: {response.status_code}")

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
def parallel_async_threads():
    """
    Run multiple async operations in parallel threads.

    This demonstrates the power of the threading approach:
    multiple separate event loops running concurrently in different threads.
    """
    logger.info("Starting parallel async threads task")

    # Run 3 async operations in parallel threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Submit multiple async operations
        futures = [
            executor.submit(_run_async_operation, i)
            for i in range(3)
        ]

        # Gather results as they complete
        results = []
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result(timeout=30)
                results.append(result)
            except Exception as e:
                logger.error(f"Thread failed: {e}")
                results.append({'error': str(e)})

    logger.info(f"Completed {len(results)} parallel operations")
    return results


def _run_async_operation(operation_id):
    """Run an async operation in its own thread with its own event loop."""
    connections.close_all()
    return asyncio.run(async_operation(operation_id))


async def async_operation(operation_id):
    """Sample async operation."""
    logger.info(f"Running async operation {operation_id}")

    # Sleep for different durations
    await asyncio.sleep(operation_id + 1)

    # Fetch some data
    async with httpx.AsyncClient() as client:
        url = f"https://httpbin.org/delay/{operation_id + 1}"
        response = await client.get(url)

        # Create log entry
        log = await APILog.objects.acreate(
            url=url,
            status_code=response.status_code,
            response_time=float(operation_id + 1),
        )

        return {
            'operation_id': operation_id,
            'status': response.status_code,
            'log_id': log.id,
        }


@shared_task
def complex_parallel_workflow():
    """
    Demonstrates a complex workflow with parallel async operations.

    This shows how threading allows you to run completely independent
    async workflows in parallel.
    """
    logger.info("Starting complex parallel workflow")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # Submit different types of async operations
        futures = {
            'fetch': executor.submit(_fetch_multiple_urls),
            'process': executor.submit(_process_data),
            'aggregate': executor.submit(_aggregate_logs),
        }

        # Wait for all to complete
        results = {}
        for name, future in futures.items():
            try:
                results[name] = future.result(timeout=60)
            except Exception as e:
                logger.error(f"Operation {name} failed: {e}")
                results[name] = {'error': str(e)}

    return results


def _fetch_multiple_urls():
    """Fetch multiple URLs in one async context."""
    connections.close_all()
    return asyncio.run(_async_fetch_multiple())


async def _async_fetch_multiple():
    """Fetch 3 URLs concurrently."""
    urls = [
        "https://httpbin.org/uuid",
        "https://httpbin.org/json",
        "https://httpbin.org/headers",
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)

        results = []
        for response, url in zip(responses, urls):
            log = await APILog.objects.acreate(
                url=url,
                status_code=response.status_code,
                response_time=0.5,
            )
            results.append({'url': url, 'log_id': log.id})

        return results


def _process_data():
    """Process some data in async context."""
    connections.close_all()
    return asyncio.run(_async_process_data())


async def _async_process_data():
    """Create several task records."""
    tasks = []
    for i in range(3):
        task = await Task.objects.acreate(
            name=f"Processed Task {i}",
            status="completed",
            result={'index': i},
            completed_at=timezone.now(),
        )
        tasks.append(task.id)

    return {'created_tasks': tasks}


def _aggregate_logs():
    """Aggregate log data in async context."""
    connections.close_all()
    return asyncio.run(_async_aggregate_logs())


async def _async_aggregate_logs():
    """Query and aggregate log data."""
    # Count logs using async ORM
    total = await APILog.objects.acount()

    # Create summary record
    task = await Task.objects.acreate(
        name="Log Aggregation",
        status="completed",
        result={'total_logs': total},
        completed_at=timezone.now(),
    )

    return {
        'total_logs': total,
        'task_id': task.id,
    }


@shared_task
def mixed_sync_async_threading():
    """
    Demonstrates mixing sync Django ORM with threaded async operations.

    Shows how to:
    1. Use sync ORM in main task
    2. Run async code in thread
    3. Use sync ORM again
    """
    logger.info("Starting mixed sync/async threading task")

    # Sync: Initial state
    initial_count = Task.objects.count()
    logger.info(f"Initial task count: {initial_count}")

    # Async in thread: Create some records
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_create_records_async)
        created = future.result(timeout=30)

    # Sync: Check final state
    final_count = Task.objects.count()
    logger.info(f"Final task count: {final_count}")

    return {
        'initial_count': initial_count,
        'final_count': final_count,
        'created': created,
    }


def _create_records_async():
    """Create records in async context in separate thread."""
    connections.close_all()
    return asyncio.run(_async_create_records())


async def _async_create_records():
    """Create several records asynchronously."""
    # Fetch some data
    async with httpx.AsyncClient() as client:
        response = await client.get("https://httpbin.org/uuid")
        uuid = response.json().get('uuid')

    # Create log
    log = await APILog.objects.acreate(
        url="https://httpbin.org/uuid",
        status_code=response.status_code,
        response_time=0.5,
    )

    # Create task
    task = await Task.objects.acreate(
        name="Created in Thread",
        status="completed",
        result={'uuid': uuid, 'log_id': log.id},
        completed_at=timezone.now(),
    )

    return {
        'task_id': task.id,
        'log_id': log.id,
    }


@shared_task
def sequential_async_operations():
    """
    Run async operations sequentially in separate threads.

    Each operation gets its own thread and event loop.
    Useful when operations need to be isolated.
    """
    logger.info("Starting sequential async operations")

    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        # Operation 1: Fetch data
        future1 = executor.submit(_run_async_in_thread_simple, "https://httpbin.org/uuid")
        result1 = future1.result(timeout=30)
        results.append(result1)

        # Operation 2: Fetch more data
        future2 = executor.submit(_run_async_in_thread_simple, "https://httpbin.org/json")
        result2 = future2.result(timeout=30)
        results.append(result2)

    return results


def _run_async_in_thread_simple(url):
    """Simple async operation in thread."""
    connections.close_all()
    return asyncio.run(_async_fetch_single(url))


async def _async_fetch_single(url):
    """Fetch a single URL."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)

        log = await APILog.objects.acreate(
            url=url,
            status_code=response.status_code,
            response_time=0.5,
        )

        return {
            'url': url,
            'status': response.status_code,
            'log_id': log.id,
        }


@shared_task
def error_handling_threads():
    """
    Demonstrates error handling with threads and async code.

    Shows how to handle exceptions in both threading and async contexts.
    """
    logger.info("Starting error handling demo")

    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Submit some operations that may fail
        futures = [
            executor.submit(_run_risky_async_op, i)
            for i in range(5)
        ]

        # Collect results with error handling
        for i, future in enumerate(futures):
            try:
                result = future.result(timeout=30)
                results.append({
                    'operation': i,
                    'success': True,
                    'result': result,
                })
            except Exception as e:
                logger.error(f"Operation {i} failed: {e}")
                results.append({
                    'operation': i,
                    'success': False,
                    'error': str(e),
                })

    successful = [r for r in results if r['success']]

    return {
        'total': len(results),
        'successful': len(successful),
        'failed': len(results) - len(successful),
        'results': results,
    }


def _run_risky_async_op(op_id):
    """Run an async operation that may fail."""
    connections.close_all()
    return asyncio.run(_async_risky_op(op_id))


async def _async_risky_op(op_id):
    """Async operation that fails for certain inputs."""
    # Fail for odd numbers (just for demo)
    if op_id % 2 == 1:
        raise ValueError(f"Operation {op_id} is odd and fails!")

    async with httpx.AsyncClient() as client:
        response = await client.get("https://httpbin.org/uuid")

        log = await APILog.objects.acreate(
            url="https://httpbin.org/uuid",
            status_code=response.status_code,
            response_time=0.5,
        )

        return {
            'op_id': op_id,
            'log_id': log.id,
        }
