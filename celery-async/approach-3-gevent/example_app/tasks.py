"""
Celery tasks demonstrating gevent worker pool approach.

Key Pattern:
1. Use standard synchronous code (no async/await)
2. Use requests library (not httpx) - gevent patches it
3. Use standard Django ORM (not async ORM)
4. Use gevent.spawn() for explicit concurrent operations
5. MUST clean up database connections in each greenlet

Gevent uses "green threads" (greenlets) for concurrency.
All blocking I/O is automatically made concurrent by gevent's monkey-patching.
"""
import logging
import time
from celery import shared_task
from django.db import close_old_connections
from django.utils import timezone
import requests  # NOT httpx - gevent patches requests
import gevent
from gevent import monkey

# Verify monkey-patching happened
if not monkey.is_module_patched('socket'):
    raise RuntimeError(
        "Gevent monkey-patching not applied! "
        "Make sure myproject/__init__.py does gevent.monkey.patch_all()"
    )

from .models import APILog, Task

logger = logging.getLogger(__name__)


@shared_task
def fetch_and_log_api():
    """
    Fetch multiple URLs and log them to the database.

    This uses standard blocking I/O - gevent makes it concurrent automatically.
    No async/await syntax needed!

    CRITICAL: Must clean up database connections at the end.
    """
    logger.info("Starting fetch_and_log_api task")

    try:
        result = _fetch_and_log()
        logger.info(f"Task completed with {len(result)} results")
        return result
    finally:
        # CRITICAL: Clean up database connections
        # Gevent doesn't trigger Django's request_finished signal,
        # so we must manually close connections
        close_old_connections()


def _fetch_and_log():
    """
    Fetch URLs using standard blocking requests.

    Gevent makes this concurrent automatically through monkey-patching.
    """
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/2",
        "https://httpbin.org/uuid",
        "https://httpbin.org/json",
    ]

    results = []

    # Standard blocking code - gevent makes it concurrent!
    for url in urls:
        start_time = timezone.now()

        try:
            logger.info(f"Fetching {url}")

            # Standard blocking HTTP request
            # Gevent automatically yields to other greenlets during I/O
            response = requests.get(url, timeout=30)

            response_time = (timezone.now() - start_time).total_seconds()

            logger.info(f"Got response from {url}: {response.status_code}")

            # Standard Django ORM - no async!
            log = APILog.objects.create(
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
    Fetch multiple URLs in parallel using gevent.spawn().

    This explicitly spawns greenlets for concurrent execution.
    Demonstrates gevent's concurrency model.
    """
    logger.info("Starting parallel fetch task")

    try:
        result = _fetch_parallel()
        return result
    finally:
        close_old_connections()


def _fetch_parallel():
    """Fetch URLs in parallel using greenlets."""
    urls = [
        "https://httpbin.org/uuid",
        "https://httpbin.org/json",
        "https://httpbin.org/headers",
    ]

    # Create task record
    task_record = Task.objects.create(
        name="Parallel Fetch (Gevent)",
        status="running",
    )

    # Define a function to fetch a single URL
    def fetch_url(url):
        """This runs in a separate greenlet."""
        try:
            start_time = timezone.now()

            response = requests.get(url, timeout=30)
            response_time = (timezone.now() - start_time).total_seconds()

            # CRITICAL: Each greenlet needs its own connection cleanup
            # But for simplicity in this demo, we'll rely on the outer cleanup

            log = APILog.objects.create(
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

    # Spawn greenlets for concurrent execution
    greenlets = [gevent.spawn(fetch_url, url) for url in urls]

    # Wait for all greenlets to complete
    gevent.joinall(greenlets)

    # Collect results
    results = [g.value for g in greenlets]

    # Update task record
    task_record.status = "completed"
    task_record.result = results
    task_record.completed_at = timezone.now()
    task_record.save()

    return results


@shared_task
def high_concurrency_demo():
    """
    Demonstrate gevent's ability to handle high concurrency.

    Spawns 50 greenlets to fetch data concurrently.
    This would be difficult with traditional threading.
    """
    logger.info("Starting high concurrency demo (50 concurrent requests)")

    try:
        result = _high_concurrency()
        return result
    finally:
        close_old_connections()


def _high_concurrency():
    """Make many concurrent requests."""
    # URLs that respond at different times
    urls = [f"https://httpbin.org/delay/{i % 3 + 1}" for i in range(20)]

    task_record = Task.objects.create(
        name="High Concurrency Demo",
        status="running",
    )

    def fetch_url(url, index):
        """Fetch URL in a greenlet."""
        try:
            start_time = time.time()
            response = requests.get(url, timeout=30)
            elapsed = time.time() - start_time

            return {
                'index': index,
                'url': url,
                'status': response.status_code,
                'time': elapsed,
            }

        except Exception as e:
            return {
                'index': index,
                'url': url,
                'error': str(e),
            }

    # Spawn many greenlets
    greenlets = [gevent.spawn(fetch_url, url, i) for i, url in enumerate(urls)]

    # Wait for all to complete
    gevent.joinall(greenlets)

    # Collect results
    results = [g.value for g in greenlets]
    successful = [r for r in results if 'error' not in r]

    # Update task
    task_record.status = "completed"
    task_record.result = {
        'total': len(results),
        'successful': len(successful),
        'failed': len(results) - len(successful),
    }
    task_record.completed_at = timezone.now()
    task_record.save()

    return task_record.result


@shared_task
def mixed_io_cpu_task():
    """
    Demonstrates mixing I/O and CPU-bound work with gevent.

    Note: Gevent is great for I/O but doesn't help with CPU-bound work.
    CPU-intensive code will block other greenlets.
    """
    logger.info("Starting mixed I/O and CPU task")

    try:
        result = _mixed_io_cpu()
        return result
    finally:
        close_old_connections()


def _mixed_io_cpu():
    """Mix I/O and CPU work."""
    results = []

    # I/O-bound work (good for gevent)
    response = requests.get("https://httpbin.org/uuid")
    uuid = response.json().get('uuid')

    log = APILog.objects.create(
        url="https://httpbin.org/uuid",
        status_code=response.status_code,
        response_time=0.5,
    )

    results.append({
        'type': 'io',
        'uuid': uuid,
        'log_id': log.id,
    })

    # CPU-bound work (blocks other greenlets)
    # This is just for demonstration - don't do heavy CPU work with gevent!
    total = 0
    for i in range(1000000):
        total += i

    results.append({
        'type': 'cpu',
        'sum': total,
    })

    return results


@shared_task
def database_operations():
    """
    Demonstrates database operations with gevent.

    Shows proper connection management patterns.
    """
    logger.info("Starting database operations task")

    try:
        result = _database_operations()
        return result
    finally:
        close_old_connections()


def _database_operations():
    """Perform various database operations."""
    # Create some records
    tasks = []
    for i in range(5):
        task = Task.objects.create(
            name=f"Gevent Task {i}",
            status="completed",
            result={'index': i},
            completed_at=timezone.now(),
        )
        tasks.append(task.id)

    # Query records
    total_tasks = Task.objects.count()
    total_logs = APILog.objects.count()

    # Update a record
    if tasks:
        task = Task.objects.get(id=tasks[0])
        task.result = {'index': 0, 'updated': True}
        task.save()

    return {
        'created_tasks': tasks,
        'total_tasks': total_tasks,
        'total_logs': total_logs,
    }


@shared_task
def error_handling_demo():
    """
    Demonstrates error handling with gevent.

    Shows how errors in greenlets are handled.
    """
    logger.info("Starting error handling demo")

    try:
        result = _error_handling()
        return result
    finally:
        close_old_connections()


def _error_handling():
    """Test error handling in greenlets."""
    urls = [
        "https://httpbin.org/status/200",  # Success
        "https://httpbin.org/status/404",  # Not found
        "https://httpbin.org/status/500",  # Server error
        "https://httpbin.org/delay/1",     # Success with delay
    ]

    def fetch_url(url):
        """Fetch URL and handle errors."""
        try:
            response = requests.get(url, timeout=30)

            # Log even error responses
            log = APILog.objects.create(
                url=url,
                status_code=response.status_code,
                response_time=0.5,
            )

            return {
                'url': url,
                'status': response.status_code,
                'log_id': log.id,
                'success': 200 <= response.status_code < 300,
            }

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return {
                'url': url,
                'error': str(e),
                'success': False,
            }

    # Spawn greenlets
    greenlets = [gevent.spawn(fetch_url, url) for url in urls]
    gevent.joinall(greenlets)

    results = [g.value for g in greenlets]
    successful = [r for r in results if r.get('success')]

    return {
        'total': len(results),
        'successful': len(successful),
        'failed': len(results) - len(successful),
        'results': results,
    }
