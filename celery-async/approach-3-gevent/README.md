# Approach 3: Gevent Worker Pool

This project demonstrates running high-concurrency I/O tasks with Celery using the gevent worker pool and green threads (greenlets).

## Overview

This approach uses:
- **Standard synchronous code** (NO async/await syntax)
- **Gevent worker pool** for green thread concurrency
- **Monkey-patching** to make blocking I/O non-blocking
- **requests library** (NOT httpx) - gevent patches it
- **Standard Django ORM** (NOT async ORM)
- **Manual connection cleanup** with `close_old_connections()`

## How It Works

```python
# In myproject/__init__.py - MUST be first!
import gevent.monkey
gevent.monkey.patch_all()

# In tasks.py - standard synchronous code
from celery import shared_task
from django.db import close_old_connections
import requests  # Gevent patches this
import gevent

@shared_task
def my_task():
    try:
        # Standard blocking code - gevent makes it concurrent!
        response = requests.get("https://api.example.com")

        # Standard Django ORM - no async needed
        MyModel.objects.create(data=response.json())

        return response.json()
    finally:
        # CRITICAL: Clean up connections
        close_old_connections()

# For explicit parallelism
def parallel_fetch():
    def fetch_url(url):
        return requests.get(url).json()

    # Spawn greenlets for concurrent execution
    jobs = [gevent.spawn(fetch_url, url) for url in urls]
    gevent.joinall(jobs)
    return [job.value for job in jobs]
```

## Key Concepts

### 🧵 What is Gevent?

Gevent is a coroutine-based Python networking library that uses:
- **Greenlets**: Lightweight pseudo-threads
- **Monkey-patching**: Makes standard blocking I/O non-blocking
- **Event loop**: libev-based event loop for concurrency

Unlike asyncio:
- No async/await syntax needed
- Works with standard libraries (requests, etc.)
- Automatic concurrency for blocking I/O

### 🐒 Monkey-Patching

Gevent "patches" Python's standard library to make blocking operations non-blocking:

```python
import gevent.monkey
gevent.monkey.patch_all()

# Now ALL of these are non-blocking:
# - socket operations
# - threading
# - time.sleep
# - subprocess
# - ssl
# - and more!
```

**Critical**: Monkey-patching MUST happen before importing anything else!

### ✅ Advantages

1. **Extremely high concurrency** - Can handle thousands of concurrent operations
2. **No code rewriting** - Use standard synchronous libraries
3. **Simple syntax** - No async/await complexity
4. **Mature and battle-tested** - Used in production by many companies
5. **Great for I/O-bound tasks** - HTTP requests, database queries, file I/O

### ⚠️ Critical Requirements

1. **Monkey-patch first**: Must call `gevent.monkey.patch_all()` before any other imports
2. **Use gevent worker pool**: `celery -A myproject worker --pool=gevent --concurrency=1000`
3. **Clean up connections**: Call `close_old_connections()` in finally blocks
4. **Use requests, not httpx**: Gevent patches requests, not httpx
5. **No Django async ORM**: Use standard ORM only

### ❌ Limitations

1. **Incompatible libraries** - Some libraries don't work with monkey-patching
2. **No async ORM** - Can't use Django's `acreate`, `aget`, etc.
3. **CPU-bound tasks** - Greenlets don't help with CPU-intensive work
4. **Debugging complexity** - Stack traces can be confusing
5. **Connection management** - Requires manual cleanup
6. **Global state** - Monkey-patching affects entire process

## Setup Instructions

### 1. Install Dependencies

```bash
cd approach-3-gevent
uv sync
```

Dependencies:
- `django>=5.0`
- `celery>=5.4`
- `redis>=5.0`
- `requests>=2.31` (NOT httpx!)
- `gevent>=24.2`

### 2. Run Migrations

```bash
python manage.py migrate
```

### 3. Start Redis

```bash
docker run -d -p 6379:6379 redis:latest
```

### 4. Start Celery Worker with Gevent Pool

**CRITICAL**: Must use `--pool=gevent`!

```bash
celery -A myproject worker --pool=gevent --concurrency=100 --loglevel=info
```

Parameters:
- `--pool=gevent`: Use gevent worker pool (required!)
- `--concurrency=100`: Number of greenlets (can be very high, e.g., 1000)
- `--loglevel=info`: Logging level

### 5. Run Demo Tasks

```bash
python manage.py run_demo
```

Demonstrates:
1. Sequential fetch (concurrent via gevent)
2. Explicit parallel fetch with `gevent.spawn()`
3. High concurrency (20+ concurrent requests)
4. Mixed I/O and CPU operations
5. Database operations with proper cleanup
6. Error handling in greenlets

## Project Structure

```
approach-3-gevent/
├── pyproject.toml          # Dependencies
├── manage.py               # Django management script
├── README.md              # This file
├── myproject/
│   ├── __init__.py        # CRITICAL: Monkey-patch here!
│   ├── settings.py        # Django settings
│   ├── celery.py          # Celery configuration
│   └── urls.py            # URL configuration (minimal)
└── example_app/
    ├── models.py          # APILog and Task models
    ├── tasks.py           # Celery tasks using gevent
    ├── management/
    │   └── commands/
    │       └── run_demo.py # Demo command
    └── migrations/        # Database migrations
```

## Example Tasks

### Task 1: Basic Gevent Task

```python
@shared_task
def fetch_and_log_api():
    try:
        # Standard blocking code - gevent makes it concurrent!
        for url in urls:
            response = requests.get(url)
            APILog.objects.create(
                url=url,
                status_code=response.status_code,
            )
    finally:
        close_old_connections()
```

### Task 2: Explicit Parallel Execution

```python
@shared_task
def fetch_parallel():
    try:
        def fetch_url(url):
            response = requests.get(url)
            return APILog.objects.create(
                url=url,
                status_code=response.status_code,
            )

        # Spawn greenlets
        jobs = [gevent.spawn(fetch_url, url) for url in urls]

        # Wait for all to complete
        gevent.joinall(jobs)

        # Get results
        return [job.value for job in jobs]
    finally:
        close_old_connections()
```

### Task 3: High Concurrency

```python
@shared_task
def high_concurrency_demo():
    try:
        urls = [f"https://httpbin.org/delay/{i%3+1}" for i in range(50)]

        def fetch(url):
            return requests.get(url, timeout=30)

        # Spawn 50 greenlets!
        jobs = [gevent.spawn(fetch, url) for url in urls]
        gevent.joinall(jobs)

        results = [job.value for job in jobs]
        return len(results)
    finally:
        close_old_connections()
```

## Database Configuration

### For SQLite (Demo)

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'CONN_MAX_AGE': 0,  # Don't persist connections
    }
}
```

### For PostgreSQL (Production)

Use `django-db-geventpool` for proper connection pooling:

```bash
pip install django-db-geventpool psycopg2-binary
```

```python
DATABASES = {
    'default': {
        'ENGINE': 'django_db_geventpool.backends.postgresql_psycopg2',
        'NAME': 'dbname',
        'USER': 'user',
        'PASSWORD': 'password',
        'HOST': 'localhost',
        'PORT': '5432',
        'ATOMIC_REQUESTS': False,
        'CONN_MAX_AGE': 0,
        'OPTIONS': {
            'MAX_CONNS': 20,  # Connection pool size
        }
    }
}
```

## Testing the Implementation

### Manual Testing

```python
# In Django shell
from example_app.tasks import fetch_parallel

# Queue the task
result = fetch_parallel.delay()

# Get result
output = result.get(timeout=30)
print(output)
```

### Performance Testing

Test high concurrency:

```python
from example_app.tasks import high_concurrency_demo

# This will make 50 concurrent HTTP requests
result = high_concurrency_demo.delay()
output = result.get(timeout=60)
```

## Common Issues and Solutions

### Issue 1: ImportError: No module named 'gevent'

**Solution**: Install gevent:
```bash
pip install gevent
```

### Issue 2: "Monkey-patching not applied" Error

**Error**:
```
RuntimeError: Gevent monkey-patching not applied!
```

**Solution**: Ensure `myproject/__init__.py` does monkey-patching:

```python
# myproject/__init__.py
import gevent.monkey
gevent.monkey.patch_all()  # Must be FIRST!

from .celery import app as celery_app
__all__ = ('celery_app',)
```

### Issue 3: Worker Not Starting with Gevent Pool

**Error**:
```
ValueError: Invalid pool implementation: gevent
```

**Solution**: Make sure gevent is installed in the same environment as Celery.

### Issue 4: Database Connection Errors

**Error**:
```
django.db.utils.DatabaseError: database is locked
```

**Solution**:
1. Set `CONN_MAX_AGE = 0`
2. Call `close_old_connections()` in task finally blocks
3. For PostgreSQL, use `django-db-geventpool`

### Issue 5: Tasks Not Concurrent

**Symptom**: Tasks run sequentially instead of concurrently

**Solution**: Make sure you started worker with `--pool=gevent`:

```bash
celery -A myproject worker --pool=gevent --concurrency=100
```

### Issue 6: httpx Doesn't Work

**Error**:
```
Various errors with httpx
```

**Solution**: Use `requests` library instead. Gevent monkey-patches `requests`, not `httpx`.

### Issue 7: CPU-Bound Code Blocks Everything

**Symptom**: When one task does CPU-intensive work, all other greenlets block

**Solution**: Gevent is for I/O-bound tasks only. For CPU-bound work:
- Use default prefork pool
- Or use a separate worker pool for CPU tasks

## When to Use This Approach

✅ **Perfect for:**
- High-concurrency I/O workloads (hundreds/thousands of simultaneous operations)
- HTTP APIs that make many external requests
- Web scraping tasks
- Database-heavy tasks with many queries
- Real-time data processing
- Webhook handlers

❌ **Not good for:**
- CPU-intensive tasks (use prefork instead)
- When you need Django async ORM
- Libraries incompatible with monkey-patching
- Complex async workflows requiring asyncio
- When you can't use monkey-patching (conflicts with other code)

## Comparison with Other Approaches

| Feature | Gevent | asyncio.run() | async_to_sync | Threading |
|---------|--------|---------------|---------------|-----------|
| Concurrency Level | Very High | Medium | Medium | Medium |
| Code Complexity | Low | Low | Medium | High |
| async/await Syntax | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| Django Async ORM | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| HTTP Library | requests | httpx | httpx | httpx |
| Setup Complexity | Medium | Low | Low | Low |
| Production Ready | ✅ Yes | ⚠️ Maybe | ✅ Yes | ⚠️ Maybe |
| Max Concurrency | 1000+ | 10-50 | 10-50 | 10-50 |

## Advantages Over asyncio Approaches

1. **Much higher concurrency** - Can handle 1000+ concurrent operations
2. **No syntax changes** - Use standard synchronous code
3. **Library compatibility** - Works with most Python libraries
4. **Mature** - Battle-tested in production for years
5. **No event loop management** - Gevent handles it automatically

## Gevent vs Eventlet

Celery supports both gevent and eventlet. They're similar but:

**Gevent:**
- Uses libev event loop (faster)
- Better C extension support
- More active development
- Recommended choice

**Eventlet:**
- Pure Python event loop
- Better stdlib compatibility
- Used by some older projects

For new projects, use gevent.

## Production Considerations

1. **Connection pooling**: Use `django-db-geventpool` with PostgreSQL
2. **Concurrency limit**: Start with 100-500, tune based on your workload
3. **Monitoring**: Greenlet count, connection pool usage
4. **Library compatibility**: Test all third-party libraries with gevent
5. **Separate worker pools**: Use different pools for gevent and prefork tasks

## Further Reading

- [Gevent Documentation](http://www.gevent.org/)
- [Celery Gevent Pool](https://docs.celeryq.dev/en/stable/userguide/concurrency/gevent.html)
- [django-db-geventpool](https://github.com/jneight/django-db-geventpool)
- [Understanding Greenlets](http://www.gevent.org/api/gevent.greenlet.html)

## Next Steps

After understanding this approach, check out:
- **Approach 1**: `asyncio.run()` for async/await syntax
- **Approach 2**: Django's `async_to_sync` for Django-native async
- **Approach 4**: Threading for complex async isolation
