import time
import requests
from celery import shared_task
from django.db import connection
from langfuse import observe
from .models import RequestLog


@shared_task
@observe()
def test_db_query():
    """
    A simple task that executes a database query.
    This task uses langfuse's @observe decorator which uses OpenTelemetry.
    When run with gevent pool, this may cause SSL verification issues with psycopg3.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
    return f"Query result: {result}"


@shared_task
@observe()
def test_db_query_with_model():
    """
    A task that uses Django ORM.
    This also triggers database connection which may fail with SSL verification
    when using gevent + langfuse.
    """
    from django.contrib.auth.models import User
    count = User.objects.count()
    return f"User count: {count}"


@shared_task
def test_internal_observe():
    """
    Task that uses @observe decorator internally instead of on the function.
    This tests whether the bug is related to the decorator placement.
    """
    @observe()
    def internal_db_operation():
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            return cursor.fetchone()

    result = internal_db_operation()
    return f"Internal observe result: {result[0][:50]}..."


@shared_task(bind=True)
@observe()
def test_http_with_db_logging(self, delay=1):
    """
    Task that makes HTTP requests to httpbin and logs them to the database.
    This combines HTTP I/O, database writes, and OpenTelemetry tracing,
    which may trigger the gevent + langfuse + psycopg3 SSL bug.
    """
    task_id = self.request.id
    url = f"https://httpbin.org/delay/{delay}"

    start_time = time.time()
    try:
        response = requests.get(url, timeout=30)
        response_time = time.time() - start_time

        # Log to database (this will use SSL connection)
        RequestLog.objects.create(
            task_id=task_id,
            url=url,
            method='GET',
            status_code=response.status_code,
            response_time=response_time,
            success=True
        )

        return f"HTTP request successful: {url} ({response.status_code}) in {response_time:.2f}s"
    except Exception as e:
        response_time = time.time() - start_time

        # Log error to database
        RequestLog.objects.create(
            task_id=task_id,
            url=url,
            method='GET',
            status_code=None,
            response_time=response_time,
            success=False,
            error_message=str(e)
        )

        raise


@shared_task(bind=True)
def test_multiple_http_requests(self, num_requests=3):
    """
    Task that makes multiple HTTP requests and logs each to database.
    Uses @observe internally for each request to increase complexity.
    """
    task_id = self.request.id
    results = []

    for i in range(num_requests):
        @observe()
        def make_request(index):
            url = f"https://httpbin.org/uuid"
            start_time = time.time()

            try:
                response = requests.get(url, timeout=10)
                response_time = time.time() - start_time

                # Log to database
                RequestLog.objects.create(
                    task_id=f"{task_id}-{index}",
                    url=url,
                    method='GET',
                    status_code=response.status_code,
                    response_time=response_time,
                    success=True
                )

                return f"Request {index}: {response.status_code}"
            except Exception as e:
                response_time = time.time() - start_time

                RequestLog.objects.create(
                    task_id=f"{task_id}-{index}",
                    url=url,
                    method='GET',
                    status_code=None,
                    response_time=response_time,
                    success=False,
                    error_message=str(e)
                )
                raise

        result = make_request(i)
        results.append(result)

    return f"Completed {num_requests} requests: {results}"


@shared_task(bind=True)
@observe()
def test_mixed_operations(self):
    """
    Task that combines database queries, HTTP requests, and model operations.
    This is the most comprehensive test for the bug.
    """
    results = []

    # 1. Database query
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM testapp_requestlog")
        log_count = cursor.fetchone()[0]
    results.append(f"Logs in DB: {log_count}")

    # 2. HTTP request
    response = requests.get("https://httpbin.org/get", timeout=10)
    results.append(f"HTTP: {response.status_code}")

    # 3. Model query
    recent_logs = RequestLog.objects.count()
    results.append(f"Model count: {recent_logs}")

    # 4. Model creation
    RequestLog.objects.create(
        task_id=self.request.id,
        url="https://httpbin.org/get",
        method='GET',
        status_code=response.status_code,
        response_time=0.1,
        success=True
    )
    results.append("Log created")

    return " | ".join(results)
