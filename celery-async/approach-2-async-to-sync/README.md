# Approach 2: Django's async_to_sync / sync_to_async

This project demonstrates running async Python code within Celery tasks using Django's official `asgiref` utilities: `async_to_sync` and `sync_to_async`.

## Overview

This approach uses:
- **Standard Celery tasks** (synchronous `@shared_task`)
- **async_to_sync()** from `asgiref` to execute async functions
- **sync_to_async()** from `asgiref` to call sync code from async context
- **Default prefork worker pool** (no special worker configuration)
- **Django async ORM** with automatic thread-local state management

## How It Works

```python
from celery import shared_task
from asgiref.sync import async_to_sync, sync_to_async

@shared_task
def my_task():
    # Wrap async function with async_to_sync
    # thread_sensitive=True ensures proper Django thread-local state handling
    result = async_to_sync(do_async_work, thread_sensitive=True)()
    return result

async def do_async_work():
    # Use async HTTP clients
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")

    # Use Django async ORM - works automatically!
    await MyModel.objects.acreate(data=response.json())

    # Can even call sync functions if needed
    @sync_to_async
    def get_count():
        return MyModel.objects.count()  # Sync ORM

    count = await get_count()
```

## Key Points

### ✅ Advantages

1. **Django's official solution** - Maintained by Django core team
2. **No manual connection management** - `asgiref` handles thread-local state automatically
3. **Clean sync/async mixing** - Natural transitions between sync and async code
4. **Thread-safe** - Proper handling of Django's thread-local storage
5. **No connections.close_all() needed** - Unlike asyncio.run() approach
6. **Flexible** - Use sync_to_async to call sync code from async context

### ⚙️ Thread-Sensitive Mode

Always use `thread_sensitive=True` for Django operations:

```python
# GOOD - Preserves thread-local state (database connections, etc.)
result = async_to_sync(async_function, thread_sensitive=True)()

# BAD - May cause issues with Django's thread-local storage
result = async_to_sync(async_function)()
```

The `thread_sensitive=True` parameter ensures that:
- Database connections are handled correctly
- Request context is preserved
- Thread-local storage works as expected

### 📝 Using sync_to_async

When you need to call sync Django ORM from async code:

```python
async def my_async_function():
    # Option 1: Decorator
    @sync_to_async
    def get_users():
        return list(User.objects.all())

    users = await get_users()

    # Option 2: Direct wrap
    count = await sync_to_async(MyModel.objects.count)()
```

### ⚠️ Connection Pooling Considerations

With Django 5.1+, connection pooling is enabled by default. If you encounter connection pool exhaustion:

```python
# In settings.py
DATABASES = {
    'default': {
        # ...
        'CONN_MAX_AGE': 0,  # Disable connection pooling if needed
    }
}
```

### ❌ Limitations

1. **Performance overhead** - Thread synchronization has some cost
2. **Complexity** - Need to understand sync/async boundaries
3. **Pool exhaustion** - Possible with Django 5.1+ if not careful
4. **Still creates event loops** - Similar overhead to asyncio.run()

## Setup Instructions

### 1. Install Dependencies

```bash
cd approach-2-async-to-sync
uv sync
```

Dependencies include:
- `django>=5.0` (includes `asgiref`)
- `celery>=5.4`
- `redis>=5.0`
- `httpx>=0.27`

### 2. Run Migrations

```bash
python manage.py migrate
```

### 3. Start Redis

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

Uses default prefork pool - no special configuration needed!

### 5. Run Demo Tasks

```bash
python manage.py run_demo
```

This demonstrates:
1. Sequential async fetching with `async_to_sync`
2. Parallel fetching with `asyncio.gather()`
3. Elegant mixing of sync and async operations
4. Using `sync_to_async` to call sync code from async
5. Complex workflow with multiple transitions

## Project Structure

```
approach-2-async-to-sync/
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
    ├── tasks.py           # Celery tasks with async_to_sync
    ├── management/
    │   └── commands/
    │       └── run_demo.py # Demo command
    └── migrations/        # Database migrations
```

## Example Tasks

### Task 1: Basic async_to_sync

```python
@shared_task
def fetch_and_log_api():
    # No connections.close_all() needed!
    result = async_to_sync(async_fetch_and_log, thread_sensitive=True)()
    return result

async def async_fetch_and_log():
    async with httpx.AsyncClient() as client:
        response = await client.get(url)

    # Django async ORM works automatically
    await APILog.objects.acreate(
        url=url,
        status_code=response.status_code,
    )
```

### Task 2: Mixed Sync/Async

```python
@shared_task
def mixed_sync_async_task():
    # Sync Django ORM
    task_count = Task.objects.count()

    # Call async code
    result = async_to_sync(fetch_data_async, thread_sensitive=True)()

    # Back to sync - seamless!
    new_count = Task.objects.count()

    return {'before': task_count, 'after': new_count}
```

### Task 3: Using sync_to_async

```python
async def demo_sync_to_async():
    # Call sync Django ORM from async context
    @sync_to_async
    def get_task_count():
        return Task.objects.count()

    count = await get_task_count()

    # Mix with async operations
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")

    # Use async ORM
    await Task.objects.acreate(
        name="Demo",
        result={'count': count},
    )
```

### Task 4: Complex Workflow

```python
@shared_task
def complex_workflow():
    # Sync: Check preconditions
    initial_state = {'tasks': Task.objects.count()}

    # Async: Fetch multiple APIs
    fetch_results = async_to_sync(
        parallel_api_calls,
        thread_sensitive=True
    )()

    # Sync: Process results
    successful = [r for r in fetch_results if 'error' not in r]

    # Async: Create summary
    summary = async_to_sync(
        create_summary_record,
        thread_sensitive=True
    )(successful)

    return {'summary': summary}
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

### Run All Demo Tasks

```bash
python manage.py run_demo
```

This runs 5 different tasks demonstrating various patterns.

## Common Issues and Solutions

### Issue 1: Thread-Local State Errors

**Error:**
```
django.core.exceptions.ImproperlyConfigured: Requested setting..., but settings are not configured
```

**Solution:**
Always use `thread_sensitive=True`:

```python
result = async_to_sync(async_func, thread_sensitive=True)()
```

### Issue 2: Connection Pool Exhaustion (Django 5.1+)

**Error:**
```
Too many connections / Connection pool exhausted
```

**Solution:**
Set `CONN_MAX_AGE = 0` in database settings to disable connection pooling.

### Issue 3: Nested async_to_sync

**Error:**
```
RuntimeError: Cannot enter into task <Task pending ...> while another task is already running
```

**Solution:**
Don't nest `async_to_sync` calls. Structure your code to avoid this:

```python
# BAD
async def outer():
    result = async_to_sync(inner)()  # Don't do this!

# GOOD
async def outer():
    result = await inner()  # Use await in async context
```

### Issue 4: sync_to_async Not Working

**Solution:**
Make sure you're calling it correctly:

```python
# Decorator style
@sync_to_async
def my_sync_func():
    return Model.objects.count()

result = await my_sync_func()

# Direct wrap style
result = await sync_to_async(Model.objects.count)()
```

## When to Use This Approach

✅ **Good for:**
- Projects already using Django's async features
- Need for fine-grained sync/async control
- Mixing legacy sync code with new async code
- Want Django's official solution
- Need proper thread-local state handling

❌ **Not ideal for:**
- Extremely high concurrency (use gevent instead)
- Simple tasks (asyncio.run() is simpler)
- Need to avoid any performance overhead
- Very complex async workflows

## Comparison with Other Approaches

| Feature | async_to_sync | asyncio.run() | Gevent | Threading |
|---------|---------------|---------------|---------|-----------|
| Complexity | Medium | Low | Medium | High |
| Django Official | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Thread-Local Safe | ✅ Yes | ⚠️ Manual | ⚠️ Manual | ⚠️ Manual |
| Connection Mgmt | ✅ Auto | ❌ Manual | ❌ Manual | ❌ Manual |
| Performance | Medium | Medium | High | Medium |
| sync_to_async | ✅ Built-in | ❌ No | ❌ No | ❌ No |

## Advantages Over asyncio.run()

1. **No manual connection cleanup** - Don't need `connections.close_all()`
2. **Better thread-local handling** - Preserves Django's request context
3. **bi-directional** - Can go sync→async→sync→async naturally
4. **sync_to_async** - Can call sync code from async context
5. **Django official** - Better integration with Django ecosystem

## Further Reading

- [Django Async Documentation](https://docs.djangoproject.com/en/5.0/topics/async/)
- [asgiref Documentation](https://github.com/django/asgiref)
- [Celery Documentation](https://docs.celeryq.dev/)
- [Real Python: Async in Django](https://realpython.com/async-io-python/)

## Next Steps

After understanding this approach, check out:
- **Approach 1**: Simple `asyncio.run()` approach for comparison
- **Approach 3**: Gevent for high-concurrency workloads
- **Approach 4**: Threading for advanced async isolation
