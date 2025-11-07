# Research: Async Code in Celery with Django

## Overview

This document summarizes research findings on different approaches to running Python async code within Celery tasks that also use Django models for database queries.

## The Challenge

The fundamental challenge is bridging two different concurrency models:

1. **Celery Tasks**: Traditionally synchronous functions that run in worker processes
2. **Django Async ORM**: Requires an async context (event loop) to function
3. **Async HTTP Clients**: Libraries like `httpx` and `aiohttp` require async/await syntax

### Common Errors

- `SynchronousOnlyOperation: You cannot call this from an async context - use a thread or sync_to_async`
- Database connection exhaustion when mixing async/sync contexts
- Event loop conflicts when running asyncio in Celery workers

---

## Approach 1: asyncio.run() in Standard Celery Tasks

### Description
Use `asyncio.run()` to execute async code within a regular synchronous Celery task with the default prefork worker pool.

### How It Works
```python
from celery import Celery
import asyncio

@app.task
def my_task():
    result = asyncio.run(do_async_work())
    return result

async def do_async_work():
    # Async HTTP requests
    # Django async ORM calls
    pass
```

### Key Considerations

**Pros:**
- Simple and straightforward approach
- No special worker pool configuration needed
- Each task gets its own isolated event loop
- Works with standard prefork workers

**Cons:**
- Creates a new event loop for each task execution
- May have database connection issues with Django
- Requires calling `connections.close_all()` before using asyncio to avoid connection problems
- Not as efficient for I/O-bound workloads as alternative approaches

**Critical Fix:**
According to Stack Overflow discussions, you need to close database connections at the start of any Celery task using asyncio:

```python
from django.db import connections

@app.task
def my_task():
    connections.close_all()  # Critical for avoiding database errors
    result = asyncio.run(do_async_work())
    return result
```

### Best Use Cases
- Tasks that need to run both async HTTP requests and Django ORM queries
- When you want to keep standard Celery worker configuration
- When tasks are relatively isolated and don't need long-lived connections

---

## Approach 2: Django's async_to_sync/sync_to_async

### Description
Use Django's `asgiref` library utilities to convert between sync and async contexts.

### How It Works
```python
from asgiref.sync import async_to_sync, sync_to_async
from celery import Celery

@app.task
def my_task():
    result = async_to_sync(do_async_work)()
    return result

async def do_async_work():
    # Use sync_to_async for Django ORM if needed
    await sync_to_async(MyModel.objects.create)(name="test")
    # Or use async ORM directly
    await MyModel.objects.acreate(name="test")
```

### Key Considerations

**Pros:**
- Official Django solution for sync/async interop
- Handles thread-local state correctly
- Good integration with Django's async ORM
- Works with ThreadSensitiveContext for proper connection management

**Cons:**
- Can exhaust connection pools in Django 5.1+ if not careful
- More complex to reason about with multiple layers of wrapping
- Potential performance overhead from thread synchronization
- Need to be careful about which functions need wrapping

**Connection Pooling Issue (Django 5.1+):**
With Django's new connection pooling, connections may not be released properly. Use `ThreadSensitiveContext` to ensure cleanup:

```python
from asgiref.sync import async_to_sync

@app.task
def my_task():
    # ThreadSensitiveContext helps manage connections
    result = async_to_sync(do_async_work, thread_sensitive=True)()
    return result
```

### Best Use Cases
- When you need fine-grained control over sync/async boundaries
- Projects already using Django's async views
- When you want to reuse async utility functions
- Need proper handling of Django's thread-local state

---

## Approach 3: Gevent/Eventlet Worker Pools

### Description
Use Celery with gevent or eventlet worker pools for green thread-based concurrency.

### How It Works
```python
# Start worker with gevent pool
# celery -A myapp worker --pool=gevent --concurrency=1000

# In code - monkey patching required
import gevent.monkey
gevent.monkey.patch_all()

@app.task
def my_task():
    # Use standard blocking I/O - gevent makes it async
    response = requests.get("https://api.example.com")
    # Django ORM works normally
    obj = MyModel.objects.create(data=response.json())
```

### Key Considerations

**Pros:**
- Excellent for I/O-bound tasks (HTTP calls, database queries)
- Can handle hundreds/thousands of concurrent tasks
- No need to rewrite code with async/await
- Mature and battle-tested in production

**Cons:**
- Requires monkey-patching at startup (can break some libraries)
- Not compatible with all Python libraries
- Still get `SynchronousOnlyOperation` errors with Django async ORM
- Need careful database connection management
- Mixing gevent and asyncio is complex and error-prone

**Critical Database Issue:**
Django only checks for long-lived connections when finishing a request. With gevent, connections won't get cleaned up automatically:

```python
from django.db import close_old_connections
from django.core.signals import request_finished

@app.task
def my_task():
    try:
        # Do work
        pass
    finally:
        # Must clean up connections manually
        close_old_connections()
        # Or send signal
        request_finished.send(sender=my_task)
```

**Better Solution:**
Use `django-db-geventpool` for proper connection pooling with gevent.

### Best Use Cases
- High-concurrency I/O-bound workloads
- Many simultaneous HTTP requests or database queries
- When you want to avoid rewriting code with async/await
- Production systems that need to handle thousands of concurrent tasks

---

## Approach 4: Threading with Async Code

### Description
Run async code in separate threads from within Celery tasks.

### How It Works
```python
import asyncio
import concurrent.futures

@app.task
def my_task():
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, do_async_work())
        result = future.result()
    return result

async def do_async_work():
    # Async operations
    pass
```

### Key Considerations

**Pros:**
- Isolates async code completely in separate threads
- Can run multiple async operations concurrently
- Avoids event loop conflicts
- Good for mixing sync and async code

**Cons:**
- More complex architecture
- Thread overhead
- Need to manage thread pool size
- Database connection issues similar to asyncio.run() approach
- More difficult to debug

### Best Use Cases
- When you need to run multiple async operations in parallel
- Complex tasks mixing sync and async code
- When you need better isolation between components

---

## Comparison Matrix

| Approach | Complexity | Performance | Django ORM | Connection Management | Worker Pool |
|----------|-----------|-------------|------------|----------------------|-------------|
| asyncio.run() | Low | Medium | ⚠️ Requires fixes | Needs `close_all()` | Prefork (default) |
| async_to_sync | Medium | Medium | ✅ Good | ⚠️ Watch pool limits | Prefork (default) |
| Gevent/Eventlet | Medium | High (I/O) | ⚠️ No async ORM | Requires cleanup | Gevent/Eventlet |
| Threading | High | Medium | ⚠️ Requires fixes | Complex | Prefork (default) |

---

## Key Insights from Research

### 1. Database Connection Management is Critical
Almost every approach requires special attention to database connections:
- Close connections before starting asyncio
- Use connection pooling libraries
- Send Django signals to trigger cleanup
- Set `CONN_MAX_AGE = 0` for some approaches

### 2. Django Async ORM Limitations
Django's async ORM (`acreate`, `aget`, etc.) requires:
- A running event loop
- Proper async context
- Cannot be called from sync code without wrapping

### 3. Event Loop Considerations
- Each approach to asyncio has different event loop implications
- `asyncio.run()` creates a new loop each time
- `async_to_sync` manages loops internally
- Gevent uses green threads, not asyncio event loops

### 4. Worker Pool Choice Matters
- **Prefork**: Best for CPU-bound tasks, default choice
- **Gevent/Eventlet**: Best for I/O-bound tasks with high concurrency
- **Solo**: Single worker, good for debugging
- Can mix different pools for different task queues

### 5. Production Considerations
- Start with benchmarking your actual workload
- Consider using separate worker pools for different task types
- Monitor connection pool usage
- Use task routing to send tasks to appropriate workers

---

## Recommendations by Use Case

### Use asyncio.run() if:
- You have simple tasks that need async HTTP + Django ORM
- You want minimal configuration changes
- Tasks are relatively independent
- You're okay with per-task event loop overhead

### Use async_to_sync if:
- You're already using Django async features
- You need fine-grained control over sync/async boundaries
- You want the most "Django-native" approach
- You can monitor connection pool usage

### Use Gevent/Eventlet if:
- You have high I/O concurrency needs (hundreds of simultaneous tasks)
- Your tasks mostly do HTTP requests and database queries
- You don't need Django's async ORM specifically
- You can handle monkey-patching requirements

### Use Threading if:
- You need maximum isolation between sync and async code
- You're running complex tasks with multiple async operations
- You have specific threading requirements
- Other approaches aren't working for your use case

---

## References

1. [Real Python: Asynchronous Tasks With Django and Celery (2024)](https://realpython.com/asynchronous-tasks-with-django-and-celery/)
2. [Stack Overflow: How to combine Celery with asyncio](https://stackoverflow.com/questions/39815771/how-to-combine-celery-with-asyncio)
3. [Stack Overflow: Querying Django ORM inside celery task](https://stackoverflow.com/questions/69915159/querying-django-orm-inside-celery-task-synchronousonlyoperation-you-cannot-cal)
4. [Medium: Mastering Celery Workers in Django](https://medium.com/@gupta.rishabh2912/mastering-celery-workers-in-django-when-to-use-prefork-eventlet-or-gevent-2679cffae2bd)
5. [Django Forum: Best Practice for Celery with async](https://forum.djangoproject.com/t/is-there-best-practice-for-used-celery-in-django-with-async/23038)
6. [Blog: Using Async Functions in Celery with Django Connection Pooling](https://mrdonbrown.blogspot.com/2025/10/using-async-functions-in-celery-with.html)

---

## Implementation Plan

Based on this research, we will create four working example projects:

1. **approach-1-asyncio-run**: Standard Celery tasks using `asyncio.run()`
2. **approach-2-async-to-sync**: Using Django's `asgiref` utilities
3. **approach-3-gevent**: Using Celery with gevent worker pool
4. **approach-4-threading**: Using threading with async code

Each will demonstrate:
- Async HTTP requests using `httpx`
- Django model creation/queries
- Proper connection management
- Error handling
- Complete working setup with documentation
