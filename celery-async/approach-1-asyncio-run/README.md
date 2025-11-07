# Approach 1: asyncio.run() in Sync Celery Tasks

This project demonstrates running async Python code within standard synchronous Celery tasks using `asyncio.run()`.

## Overview

This approach uses:
- **Standard Celery tasks** (synchronous `@shared_task`)
- **asyncio.run()** to execute async code within tasks
- **Default prefork worker pool** (no special worker configuration)
- **Django async ORM** for database operations

## How It Works

```python
from celery import shared_task
from django.db import connections
import asyncio

@shared_task
def my_task():
    # CRITICAL: Close connections before asyncio
    connections.close_all()

    # Run async code
    result = asyncio.run(do_async_work())
    return result

async def do_async_work():
    # Use async HTTP clients
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")

    # Use Django async ORM
    await MyModel.objects.acreate(data=response.json())
```

## Key Points

### ✅ Advantages

1. **Simple setup** - No special worker pool configuration needed
2. **Standard Celery** - Uses default prefork workers
3. **Isolated event loops** - Each task gets its own event loop
4. **Django async ORM** - Can use `acreate`, `aget`, `aupdate`, etc.
5. **Async HTTP** - Can use modern async HTTP clients like `httpx`

### ⚠️ Critical Requirement

**You MUST call `connections.close_all()` before `asyncio.run()`**

```python
from django.db import connections

@shared_task
def my_task():
    connections.close_all()  # <- CRITICAL!
    return asyncio.run(async_function())
```

Without this, you'll get database connection errors when using Django's async ORM.

### ⚙️ Database Settings

Set `CONN_MAX_AGE = 0` in your database configuration:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'CONN_MAX_AGE': 0,  # Don't persist connections
    }
}
```

### ❌ Limitations

1. **Event loop overhead** - Creates a new event loop for each task
2. **Not ideal for high concurrency** - Better options exist for I/O-heavy workloads
3. **Connection management** - Requires manual connection cleanup
4. **Cannot reuse event loop** - Each `asyncio.run()` call creates/destroys a loop

## Setup Instructions

### 1. Install Dependencies

```bash
cd approach-1-asyncio-run
uv sync
```

### 2. Run Migrations

```bash
python manage.py migrate
```

This creates the SQLite database and tables for `APILog` and `Task` models.

### 3. Start Redis

Celery needs Redis as a message broker:

```bash
# Using Docker
docker run -d -p 6379:6379 redis:latest

# Or using local Redis
redis-server
```

### 4. Start Celery Worker

```bash
celery -A myproject worker --loglevel=info
```

This starts a Celery worker with the default prefork pool.

### 5. Run Demo Tasks

In another terminal:

```bash
python manage.py run_demo
```

This will:
1. Fetch 4 URLs sequentially using async/await
2. Fetch 3 URLs in parallel using `asyncio.gather()`
3. Demonstrate mixing sync and async Django ORM operations
4. Display results and database state

## Project Structure

```
approach-1-asyncio-run/
├── pyproject.toml          # Dependencies
├── manage.py               # Django management script
├── README.md              # This file
├── myproject/
│   ├── __init__.py        # Celery app import
│   ├── settings.py        # Django settings
│   ├── celery.py          # Celery configuration
│   └── urls.py            # URL configuration (minimal)
└── example_app/
    ├── models.py          # APILog and Task models
    ├── tasks.py           # Celery tasks with asyncio.run()
    ├── management/
    │   └── commands/
    │       └── run_demo.py # Demo command
    └── migrations/        # Database migrations
```

## Example Tasks

### Task 1: Sequential Async Fetching

```python
@shared_task
def fetch_and_log_api():
    connections.close_all()
    return asyncio.run(async_fetch_and_log())

async def async_fetch_and_log():
    async with httpx.AsyncClient() as client:
        for url in urls:
            response = await client.get(url)
            await APILog.objects.acreate(
                url=url,
                status_code=response.status_code,
                response_time=elapsed,
            )
```

### Task 2: Parallel Async Fetching

```python
@shared_task
def fetch_parallel():
    connections.close_all()
    return asyncio.run(async_fetch_parallel())

async def async_fetch_parallel():
    async with httpx.AsyncClient() as client:
        tasks = [fetch_single_url(client, url) for url in urls]
        results = await asyncio.gather(*tasks)
    return results
```

### Task 3: Mixed Sync/Async

```python
@shared_task
def create_task_and_fetch():
    # Sync ORM before async
    count = Task.objects.count()

    # Switch to async
    connections.close_all()
    result = asyncio.run(async_create_and_fetch())

    return {'count': count, 'result': result}
```

## Testing the Implementation

### Manual Testing

```python
# In Django shell
from example_app.tasks import fetch_and_log_api

# Queue the task
result = fetch_and_log_api.delay()

# Get the result
output = result.get(timeout=30)
print(output)

# Check database
from example_app.models import APILog
print(APILog.objects.count())
```

### Check Celery Logs

The worker logs will show:
- Task execution start/completion
- HTTP requests being made
- Database operations
- Any errors or warnings

## Common Issues and Solutions

### Issue 1: `SynchronousOnlyOperation` Error

**Error:**
```
SynchronousOnlyOperation: You cannot call this from an async context
```

**Solution:**
Make sure you're calling `connections.close_all()` before `asyncio.run()`:

```python
@shared_task
def my_task():
    connections.close_all()  # Add this!
    return asyncio.run(async_function())
```

### Issue 2: Connection Already Closed

**Error:**
```
django.db.utils.InterfaceError: connection already closed
```

**Solution:**
Set `CONN_MAX_AGE = 0` in your database settings.

### Issue 3: Event Loop Already Running

**Error:**
```
RuntimeError: This event loop is already running
```

**Solution:**
Don't nest `asyncio.run()` calls. Use `await` instead inside async functions.

### Issue 4: Celery Worker Not Picking Up Tasks

**Solution:**
1. Make sure Redis is running
2. Check that `CELERY_BROKER_URL` is correct
3. Restart the Celery worker
4. Check worker logs for errors

## When to Use This Approach

✅ **Good for:**
- Simple async tasks with Django ORM
- Minimal configuration requirements
- Projects already using standard Celery setup
- Tasks that don't need ultra-high concurrency

❌ **Not ideal for:**
- Very high concurrency I/O workloads (use gevent instead)
- Tasks that need to share event loop state
- Production systems with strict performance requirements
- Complex async workflows

## Comparison with Other Approaches

| Feature | asyncio.run() | async_to_sync | Gevent | Threading |
|---------|---------------|---------------|---------|-----------|
| Complexity | Low | Medium | Medium | High |
| Setup | Minimal | Minimal | Moderate | Minimal |
| Performance | Medium | Medium | High | Medium |
| Django Async ORM | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes |
| Worker Pool | Prefork | Prefork | Gevent | Prefork |
| Connection Mgmt | Manual | Automatic | Manual | Manual |

## Further Reading

- [Django Async Documentation](https://docs.djangoproject.com/en/5.0/topics/async/)
- [Celery Documentation](https://docs.celeryq.dev/)
- [Python asyncio Documentation](https://docs.python.org/3/library/asyncio.html)
- [httpx Async Client](https://www.python-httpx.org/async/)

## Next Steps

After understanding this approach, check out:
- **Approach 2**: Using Django's `async_to_sync` for better integration
- **Approach 3**: Using Gevent for high-concurrency I/O workloads
- **Approach 4**: Using threading for advanced async isolation
