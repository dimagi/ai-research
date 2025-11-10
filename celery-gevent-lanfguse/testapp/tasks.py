from celery import shared_task
from django.db import connection
from langfuse.decorators import observe


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
