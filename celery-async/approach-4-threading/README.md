# Approach 4: Threading with Async Code

This project demonstrates running async Python code within Celery tasks using Python's `ThreadPoolExecutor` for maximum isolation and parallel execution of async operations.

## Overview

This approach uses:
- **Standard Celery tasks** (synchronous `@shared_task`)
- **ThreadPoolExecutor** to run async code in separate threads
- **asyncio.run()** in each thread with its own event loop
- **Default prefork worker pool** (no special configuration)
- **Django async ORM** within each async context
- **Parallel async operations** in multiple threads

## How It Works

```python
import asyncio
import concurrent.futures
from celery import shared_task
from django.db import connections

@shared_task
def my_task():
    # Run async code in a thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_async_in_thread)
        result = future.result(timeout=60)
    return result

def _run_async_in_thread():
    # This runs in a separate thread
    connections.close_all()  # Close connections before event loop
    return asyncio.run(do_async_work())

async def do_async_work():
    # Use async HTTP and Django ORM
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")

    await MyModel.objects.acreate(data=response.json())
```

## Key Concepts

### 🧵 Why Threading?

Threading provides:
1. **Isolation**: Each thread has its own event loop
2. **Parallelism**: Run multiple async operations truly in parallel
3. **Flexibility**: Mix sync and async code naturally
4. **Safety**: Errors in one thread don't affect others

### ✅ Advantages

1. **Maximum isolation** - Each async operation in its own thread/event loop
2. **Truly parallel async** - Run multiple async workflows simultaneously
3. **No event loop conflicts** - Each thread manages its own loop
4. **Flexible architecture** - Easy to mix sync and async code
5. **Error isolation** - Exceptions don't leak between threads
6. **Django async ORM** - Works with proper setup

### ⚙️ How It's Different from asyncio.run()

| Feature | Threading | asyncio.run() |
|---------|-----------|---------------|
| Event Loops | Multiple (one per thread) | Single per task |
| Parallelism | True parallel async ops | Sequential async ops |
| Isolation | Maximum | Moderate |
| Complexity | Higher | Lower |
| Use Case | Complex workflows | Simple async tasks |

### 📊 Parallel Execution Example

```python
@shared_task
def parallel_workflow():
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Run 4 different async operations in parallel
        futures = {
            'fetch': executor.submit(async_fetch_data),
            'process': executor.submit(async_process),
            'aggregate': executor.submit(async_aggregate),
            'notify': executor.submit(async_notify),
        }

        # All 4 run concurrently in separate threads!
        results = {
            name: future.result()
            for name, future in futures.items()
        }

    return results
```

### ⚠️ Critical Requirements

1. **connections.close_all()** before asyncio.run() in each thread
2. **Thread pool management** - Don't create too many threads
3. **Proper timeout handling** - Use timeouts on future.result()
4. **Database settings** - Set `CONN_MAX_AGE = 0`

### ❌ Limitations

1. **Higher complexity** - More moving parts than other approaches
2. **Thread overhead** - Threads consume memory and resources
3. **Harder to debug** - Multiple threads + event loops = complex stack traces
4. **Resource management** - Need to carefully manage thread pool size
5. **Not for simple tasks** - Overkill for basic async operations

## Setup Instructions

### 1. Install Dependencies

```bash
cd approach-4-threading
uv sync
```

Dependencies:
- `django>=5.0`
- `celery>=5.4`
- `redis>=5.0`
- `httpx>=0.27`

### 2. Run Migrations

```bash
python manage.py migrate
```

### 3. Start Redis

```bash
docker run -d -p 6379:6379 redis:latest
```

### 4. Start Celery Worker

```bash
celery -A myproject worker --loglevel=info
```

Uses default prefork pool - no special configuration!

### 5. Run Demo Tasks

```bash
python manage.py run_demo
```

Demonstrates:
1. Basic async code in thread
2. Parallel async operations (3 concurrent threads)
3. Complex parallel workflow (4 independent workflows)
4. Mixed sync/async with threading
5. Sequential async operations in separate threads
6. Error handling across threads

## Project Structure

```
approach-4-threading/
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
    ├── tasks.py           # Celery tasks with threading
    ├── management/
    │   └── commands/
    │       └── run_demo.py # Demo command
    └── migrations/        # Database migrations
```

## Example Tasks

### Task 1: Basic Threading

```python
@shared_task
def fetch_data():
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_async)
        return future.result(timeout=30)

def _run_async():
    connections.close_all()
    return asyncio.run(async_fetch())

async def async_fetch():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")
        await APILog.objects.acreate(
            url=response.url,
            status_code=response.status_code,
        )
```

### Task 2: Parallel Async Operations

```python
@shared_task
def parallel_operations():
    with ThreadPoolExecutor(max_workers=3) as executor:
        # Submit 3 async operations
        futures = [
            executor.submit(_run_operation, i)
            for i in range(3)
        ]

        # Collect results as they complete
        results = []
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    return results

def _run_operation(op_id):
    connections.close_all()
    return asyncio.run(async_operation(op_id))
```

### Task 3: Complex Workflow

```python
@shared_task
def complex_workflow():
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            'step1': executor.submit(_async_step1),
            'step2': executor.submit(_async_step2),
            'step3': executor.submit(_async_step3),
        }

        # All steps run in parallel!
        results = {
            name: future.result(timeout=60)
            for name, future in futures.items()
        }

    return results
```

## When to Use This Approach

✅ **Perfect for:**
- Complex workflows with multiple independent async operations
- Need truly parallel async execution
- Maximum isolation between async operations
- Advanced error handling requirements
- Mixing different async libraries/patterns
- When you need fine-grained control over concurrency

❌ **Not good for:**
- Simple async tasks (use asyncio.run() instead)
- High-volume simple operations (use gevent instead)
- When thread overhead is a concern
- Beginners to async programming
- Resource-constrained environments

## Thread Pool Sizing

Choose `max_workers` based on your needs:

```python
# Sequential execution (1 thread)
with ThreadPoolExecutor(max_workers=1) as executor:
    # Good for simple isolation

# Moderate parallelism (2-4 threads)
with ThreadPoolExecutor(max_workers=4) as executor:
    # Good for balanced workflows

# High parallelism (10+ threads)
with ThreadPoolExecutor(max_workers=10) as executor:
    # Good for I/O-heavy parallel operations
    # Watch resource usage!

# CPU-based sizing
import os
with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
    # Scales with available CPUs
```

## Error Handling

Threading requires careful error handling:

```python
@shared_task
def safe_parallel_task():
    results = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_risky_op, i) for i in range(5)]

        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result(timeout=30)
                results.append({'success': True, 'data': result})
            except TimeoutError:
                results.append({'success': False, 'error': 'timeout'})
            except Exception as e:
                results.append({'success': False, 'error': str(e)})

    return results
```

## Testing the Implementation

### Manual Testing

```python
from example_app.tasks import parallel_async_threads

# Queue the task
result = parallel_async_threads.delay()

# Get result
output = result.get(timeout=60)
print(output)
```

### Performance Comparison

Compare with asyncio.run():

```python
# Threading: 3 operations in parallel (truly concurrent)
parallel_async_threads()  # ~1 second total

# asyncio.run(): 3 operations sequential
# Would take ~3 seconds total
```

## Common Issues and Solutions

### Issue 1: Too Many Threads

**Symptom**: System slowdown, memory issues

**Solution**: Reduce `max_workers`:
```python
# Instead of
with ThreadPoolExecutor(max_workers=100) as executor:

# Use
with ThreadPoolExecutor(max_workers=10) as executor:
```

### Issue 2: Database Connection Errors

**Error**: Connection already closed, too many connections

**Solution**:
1. Call `connections.close_all()` before asyncio.run()
2. Set `CONN_MAX_AGE = 0`
3. Limit thread pool size

### Issue 3: Deadlocks

**Symptom**: Task hangs indefinitely

**Solution**: Always use timeouts:
```python
result = future.result(timeout=30)  # Don't wait forever!
```

### Issue 4: Memory Leaks

**Symptom**: Memory usage grows over time

**Solution**:
- Use context managers (`with` statements)
- Clean up resources in each thread
- Don't keep references to completed futures

## Comparison with Other Approaches

| Feature | Threading | asyncio.run() | async_to_sync | Gevent |
|---------|-----------|---------------|---------------|--------|
| Complexity | High | Low | Medium | Medium |
| Parallelism | True | False | False | High |
| Isolation | Maximum | Moderate | Moderate | Low |
| Overhead | High | Medium | Medium | Low |
| Max Concurrent | 10-50 | 1 | 1 | 1000+ |
| Best For | Complex workflows | Simple tasks | Django integration | High I/O |

## Advanced Patterns

### Pattern 1: Pipeline

```python
def pipeline_task():
    with ThreadPoolExecutor(max_workers=1) as executor:
        # Step 1
        future1 = executor.submit(_fetch_data)
        data = future1.result()

        # Step 2 (depends on step 1)
        future2 = executor.submit(_process_data, data)
        processed = future2.result()

        # Step 3 (depends on step 2)
        future3 = executor.submit(_save_data, processed)
        return future3.result()
```

### Pattern 2: Fan-out/Fan-in

```python
def fan_out_in_task():
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Fan out: Start many parallel operations
        futures = [
            executor.submit(_process_item, item)
            for item in items
        ]

        # Fan in: Collect all results
        results = [f.result() for f in futures]

        # Aggregate
        return aggregate(results)
```

### Pattern 3: Timeout with Fallback

```python
def timeout_fallback_task():
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_slow_operation)

        try:
            return future.result(timeout=5)
        except TimeoutError:
            # Fall back to cached data
            return get_cached_data()
```

## Further Reading

- [Python ThreadPoolExecutor](https://docs.python.org/3/library/concurrent.futures.html)
- [Threading Best Practices](https://docs.python.org/3/library/threading.html)
- [asyncio and Threading](https://docs.python.org/3/library/asyncio-dev.html#concurrency-and-multithreading)

## Next Steps

After understanding this approach, compare with:
- **Approach 1**: Simple asyncio.run() for basic async
- **Approach 2**: Django's async_to_sync for official integration
- **Approach 3**: Gevent for ultra-high concurrency
