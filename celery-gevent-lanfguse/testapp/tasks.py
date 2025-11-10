import time
import requests
from celery import shared_task
from django.db import connection
from langfuse import observe
from .models import RequestLog
from .langfuse import get_random_langfuse_account

@shared_task
def test_db_query():
    """
    A simple task that executes a database query.
    This task uses langfuse's @observe decorator which uses OpenTelemetry.
    When run with gevent pool, this may cause SSL verification issues with psycopg3.
    """
    tracer = get_random_langfuse_account()
    with tracer.trace("test_db_query") as span:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            span.set_outputs({"result": str(result)})
    return f"Query result: {result}"


@shared_task
def test_db_query_with_model():
    """
    A task that uses Django ORM.
    This also triggers database connection which may fail with SSL verification
    when using gevent + langfuse.
    """
    from django.contrib.auth.models import User
    tracer = get_random_langfuse_account()
    with tracer.trace("test_db_query_with_model") as span:
        count = User.objects.count()
        span.set_outputs({"count": str(count)})
    return f"User count: {count}"


@shared_task(bind=True)
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
        tracer = get_random_langfuse_account()
        with tracer.trace("test_http_with_db_logging") as span:
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
            span.set_outputs({
                "status_code": response.status_code,
                "response_time": response_time
            })
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

    tracer = get_random_langfuse_account()
    with tracer.trace(f"test_multiple_http_requests") as trace:

        for i in range(num_requests):
            def make_request(index):
                url = f"https://httpbin.org/uuid"
                start_time = time.time()

                try:
                    with tracer.span(f"test_multiple_http_requests-{i}") as span:
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
                        span.set_outputs({
                            "status_code": response.status_code,
                            "response_time": response_time
                        })

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
        trace.set_outputs({"results": num_requests})

    return f"Completed {num_requests} requests: {results}"


@shared_task(bind=True)
def test_mixed_operations(self):
    """
    Task that combines database queries, HTTP requests, and model operations.
    This is the most comprehensive test for the bug.
    """
    results = []

    # 1. Database query
    tracer = get_random_langfuse_account()
    with tracer.trace("test_mixed_operations-db") as span:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM testapp_requestlog")
            log_count = cursor.fetchone()[0]
        span.set_outputs({"log_count": log_count})
    results.append(f"Logs in DB: {log_count}")

    # 2. HTTP request
    with tracer.trace("test_mixed_operations-request") as span:
        response = requests.get("https://httpbin.org/get", timeout=10)
        results.append(f"HTTP: {response.status_code}")
        span.set_outputs({
            "status_code": response.status_code,
        })

    # 3. Model query
    tracer = get_random_langfuse_account()
    with tracer.trace("test_mixed_operations-model") as trace:
        recent_logs = RequestLog.objects.count()
        results.append(f"Model count: {recent_logs}")

        # 4. Model creation
        with tracer.span("test_mixed_operations-model-nested") as span:
            RequestLog.objects.create(
                task_id=self.request.id,
                url="https://httpbin.org/get",
                method='GET',
                status_code=response.status_code,
                response_time=0.1,
                success=True
            )
            results.append("Log created")
            span.set_outputs({"status": "log created"})

        trace.set_outputs({"status": "success"})

    return " | ".join(results)
