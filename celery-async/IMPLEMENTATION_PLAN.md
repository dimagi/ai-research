# Implementation Plan: Celery Async Projects

## Common Components (All Approaches)

Each project will include:

### 1. Django Project Structure
```
approach-X/
├── manage.py
├── pyproject.toml          # uv configuration
├── README.md               # Approach-specific documentation
├── myproject/
│   ├── __init__.py
│   ├── settings.py         # Django settings
│   ├── celery.py          # Celery app configuration
│   └── urls.py
└── example_app/
    ├── __init__.py
    ├── models.py           # Django models (APILog, Task)
    ├── tasks.py            # Celery tasks
    ├── management/
    │   └── commands/
    │       └── run_demo.py # Demo command
    └── migrations/
```

### 2. Shared Django Models
```python
# models.py
class APILog(models.Model):
    url = models.URLField()
    status_code = models.IntegerField()
    response_time = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

class Task(models.Model):
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=50)
    result = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)
```

### 3. Common Dependencies
- Django >= 5.0
- Celery >= 5.4
- Redis (for broker and result backend)
- httpx (async HTTP client)
- psycopg2-binary or psycopg[binary] (PostgreSQL)

---

## Approach 1: asyncio.run() in Sync Tasks

### Directory: `approach-1-asyncio-run`

### Key Implementation Details

**Dependencies:**
```toml
[project]
dependencies = [
    "django>=5.0",
    "celery>=5.4",
    "redis>=5.0",
    "httpx>=0.27",
    "psycopg[binary]>=3.1",
]
```

**Celery Configuration (`myproject/celery.py`):**
```python
from celery import Celery
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Standard prefork pool (default)
```

**Task Implementation (`example_app/tasks.py`):**
```python
import asyncio
from celery import shared_task
from django.db import connections
from django.utils import timezone
import httpx
from .models import APILog, Task

@shared_task
def fetch_and_log_api():
    """
    Demonstrates asyncio.run() approach.

    Critical: Close DB connections before asyncio.run()
    """
    # CRITICAL: Close connections before using asyncio
    connections.close_all()

    # Run async code
    result = asyncio.run(async_fetch_and_log())
    return result

async def async_fetch_and_log():
    """Async function that makes HTTP requests and uses Django async ORM."""
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/2",
        "https://httpbin.org/uuid",
    ]

    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in urls:
            start_time = timezone.now()

            try:
                response = await client.get(url)
                response_time = (timezone.now() - start_time).total_seconds()

                # Use Django async ORM
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
                results.append({
                    'url': url,
                    'error': str(e),
                })

    return results
```

**Django Settings Adjustments:**
```python
# Important for asyncio.run() approach
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'CONN_MAX_AGE': 0,  # Don't persist connections
    }
}

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
```

**Demo Command:**
```python
from django.core.management.base import BaseCommand
from example_app.tasks import fetch_and_log_api

class Command(BaseCommand):
    help = 'Run demo of asyncio.run() approach'

    def handle(self, *args, **options):
        self.stdout.write('Starting async task with asyncio.run()...')
        result = fetch_and_log_api.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')
        output = result.get(timeout=30)
        self.stdout.write(self.style.SUCCESS(f'Result: {output}'))
```

**README sections:**
- How asyncio.run() works
- Why connections.close_all() is required
- Worker command: `celery -A myproject worker --loglevel=info`
- Pros/cons of this approach
- Common pitfalls

---

## Approach 2: Django's async_to_sync

### Directory: `approach-2-async-to-sync`

### Key Implementation Details

**Dependencies:**
```toml
[project]
dependencies = [
    "django>=5.0",
    "celery>=5.4",
    "redis>=5.0",
    "httpx>=0.27",
    "psycopg[binary]>=3.1",
    # asgiref comes with Django
]
```

**Task Implementation:**
```python
from asgiref.sync import async_to_sync, sync_to_async
from celery import shared_task
from django.utils import timezone
import httpx
from .models import APILog, Task

@shared_task
def fetch_and_log_api():
    """
    Demonstrates async_to_sync approach.

    Uses Django's official sync/async utilities.
    """
    result = async_to_sync(async_fetch_and_log, thread_sensitive=True)()
    return result

async def async_fetch_and_log():
    """Async function using Django's async ORM and httpx."""
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/uuid",
        "https://httpbin.org/headers",
    ]

    # Create a Task record
    task_record = await Task.objects.acreate(
        name="API Fetch",
        status="running",
    )

    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in urls:
            start_time = timezone.now()

            try:
                response = await client.get(url)
                response_time = (timezone.now() - start_time).total_seconds()

                # Django async ORM works naturally
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
                results.append({
                    'url': url,
                    'error': str(e),
                })

    # Update task record
    task_record.status = "completed"
    task_record.result = results
    task_record.completed_at = timezone.now()
    await task_record.asave()

    return results

@shared_task
def mixed_sync_async_task():
    """Demonstrates mixing sync and async code."""
    # Sync Django ORM
    task_count = Task.objects.count()

    # Call async code
    result = async_to_sync(fetch_data_async)()

    # More sync code
    return {
        'previous_tasks': task_count,
        'fetch_result': result,
    }

async def fetch_data_async():
    """Pure async function."""
    async with httpx.AsyncClient() as client:
        response = await client.get("https://httpbin.org/json")
        return response.json()
```

**Django Settings:**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        # For Django 5.1+, be careful with connection pooling
        # 'CONN_MAX_AGE': 0,  # Uncomment if you have issues
    }
}
```

**README sections:**
- How async_to_sync works
- thread_sensitive parameter explained
- Connection pooling considerations
- When to use sync_to_async
- Worker command: `celery -A myproject worker --loglevel=info`

---

## Approach 3: Gevent Worker Pool

### Directory: `approach-3-gevent`

### Key Implementation Details

**Dependencies:**
```toml
[project]
dependencies = [
    "django>=5.0",
    "celery>=5.4",
    "redis>=5.0",
    "requests>=2.31",  # Not httpx - gevent works with requests
    "psycopg[binary]>=3.1",
    "gevent>=24.2",
    "django-db-geventpool>=4.0",  # For connection pooling
]
```

**Celery Configuration with Gevent:**
```python
from celery import Celery
import os

# IMPORTANT: Monkey patch before any other imports
import gevent.monkey
gevent.monkey.patch_all()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

**Task Implementation:**
```python
import gevent
from gevent import monkey
monkey.patch_all()

from celery import shared_task
from django.db import close_old_connections
from django.utils import timezone
import requests  # NOT httpx - gevent patches requests
from .models import APILog, Task

@shared_task
def fetch_and_log_api():
    """
    Demonstrates gevent approach.

    Uses standard blocking I/O - gevent makes it concurrent.
    """
    try:
        return _fetch_and_log()
    finally:
        # CRITICAL: Clean up database connections
        close_old_connections()

def _fetch_and_log():
    """Standard blocking code - gevent handles concurrency."""
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/2",
        "https://httpbin.org/uuid",
    ]

    # Create task record (standard sync ORM)
    task_record = Task.objects.create(
        name="API Fetch (Gevent)",
        status="running",
    )

    results = []

    # Use gevent to fetch URLs concurrently
    def fetch_url(url):
        start_time = timezone.now()
        try:
            response = requests.get(url, timeout=30)
            response_time = (timezone.now() - start_time).total_seconds()

            # Standard Django ORM - works fine with gevent
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
            return {
                'url': url,
                'error': str(e),
            }

    # Spawn greenlets for concurrent fetching
    jobs = [gevent.spawn(fetch_url, url) for url in urls]
    gevent.joinall(jobs)

    results = [job.value for job in jobs]

    # Update task
    task_record.status = "completed"
    task_record.result = results
    task_record.completed_at = timezone.now()
    task_record.save()

    return results
```

**Django Settings with Gevent:**
```python
# Use gevent-compatible database backend
DATABASES = {
    'default': {
        'ENGINE': 'django_db_geventpool.backends.postgresql_psycopg2',
        'NAME': 'celery_gevent_db',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': 'localhost',
        'PORT': '5432',
        'ATOMIC_REQUESTS': False,
        'CONN_MAX_AGE': 0,
        'OPTIONS': {
            'MAX_CONNS': 20,
        }
    }
}

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
```

**Worker Command:**
```bash
celery -A myproject worker --pool=gevent --concurrency=100 --loglevel=info
```

**README sections:**
- What is gevent and how it works
- Monkey patching explained
- Why use requests instead of httpx
- Database connection pooling with django-db-geventpool
- High concurrency benefits
- Compatibility considerations

---

## Approach 4: Threading with Async Code

### Directory: `approach-4-threading`

### Key Implementation Details

**Dependencies:**
```toml
[project]
dependencies = [
    "django>=5.0",
    "celery>=5.4",
    "redis>=5.0",
    "httpx>=0.27",
    "psycopg[binary]>=3.1",
]
```

**Task Implementation:**
```python
import asyncio
import concurrent.futures
from celery import shared_task
from django.db import connections
from django.utils import timezone
import httpx
from .models import APILog, Task

@shared_task
def fetch_and_log_api():
    """
    Demonstrates threading approach.

    Runs async code in a separate thread.
    """
    # Run async code in thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_async_in_thread)
        result = future.result(timeout=60)

    return result

def _run_async_in_thread():
    """This runs in a separate thread."""
    # Close connections before creating event loop
    connections.close_all()

    # Create and run event loop in this thread
    return asyncio.run(async_fetch_and_log())

async def async_fetch_and_log():
    """Async function that runs in separate thread."""
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/uuid",
    ]

    results = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch URLs concurrently
        tasks = [fetch_single_url(client, url) for url in urls]
        results = await asyncio.gather(*tasks)

    return results

async def fetch_single_url(client, url):
    """Fetch a single URL and log it."""
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
        return {
            'url': url,
            'error': str(e),
        }

@shared_task
def parallel_async_tasks():
    """
    Run multiple async operations in parallel threads.

    Demonstrates advanced threading usage.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Submit multiple async operations
        futures = [
            executor.submit(asyncio.run, async_operation(i))
            for i in range(3)
        ]

        # Gather results
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    return results

async def async_operation(task_id):
    """Sample async operation."""
    await asyncio.sleep(1)
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://httpbin.org/delay/{task_id}")
        return {
            'task_id': task_id,
            'status': response.status_code,
        }
```

**README sections:**
- How threading isolates async code
- ThreadPoolExecutor usage
- When to use multiple workers
- Trade-offs vs other approaches
- Worker command: `celery -A myproject worker --loglevel=info`

---

## Testing Strategy

Each implementation will include:

### 1. Management Command (`run_demo.py`)
```python
from django.core.management.base import BaseCommand
from example_app.tasks import fetch_and_log_api
import time

class Command(BaseCommand):
    help = 'Run demo tasks'

    def handle(self, *args, **options):
        self.stdout.write('Starting demo task...')

        # Send task to Celery
        result = fetch_and_log_api.delay()

        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        # Wait for completion
        output = result.get(timeout=60)

        self.stdout.write(self.style.SUCCESS('Task completed!'))
        self.stdout.write(str(output))

        # Show database records
        from example_app.models import APILog
        count = APILog.objects.count()
        self.stdout.write(f'Total API logs in database: {count}')
```

### 2. Test Script
Each project includes a shell script `test.sh`:
```bash
#!/bin/bash
set -e

echo "Running migrations..."
python manage.py migrate

echo "Starting Celery worker in background..."
celery -A myproject worker --loglevel=info &
CELERY_PID=$!

sleep 3

echo "Running demo tasks..."
python manage.py run_demo

echo "Stopping Celery worker..."
kill $CELERY_PID

echo "Demo completed successfully!"
```

---

## Implementation Order

1. **Approach 1 (asyncio.run)** - Simplest, good baseline
2. **Approach 2 (async_to_sync)** - Similar to #1, but uses Django's utilities
3. **Approach 3 (gevent)** - More complex, different worker pool
4. **Approach 4 (threading)** - Most complex, builds on #1

---

## Success Criteria Checklist

For each implementation:

- [ ] `uv sync` successfully installs dependencies
- [ ] `python manage.py migrate` creates database tables
- [ ] Celery worker starts without errors
- [ ] Demo command successfully runs tasks
- [ ] Async HTTP requests complete successfully
- [ ] Django models are created in database
- [ ] No connection errors or warnings
- [ ] README has clear setup instructions
- [ ] Code includes helpful comments
- [ ] Error handling is implemented
- [ ] Logs show clear task progress
