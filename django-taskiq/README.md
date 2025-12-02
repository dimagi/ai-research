# Django + Taskiq Integration Demo

This project demonstrates how to integrate **taskiq** (a distributed task queue) with **Django**, with special attention to proper database connection management.

## Overview

Taskiq is an asynchronous task queue library for Python that supports various brokers (Redis, RabbitMQ, etc.). This demo shows how to:

1. Set up taskiq with Django
2. Handle database connections properly in async workers
3. Create tasks that interact with Django models
4. Test the integration

## Project Structure

```
django-taskiq/
├── config/                 # Django project settings
│   ├── settings.py
│   ├── tkq.py             # Taskiq broker configuration ⭐
│   └── ...
├── tasks_demo/            # Demo Django app
│   ├── models.py          # Task model
│   ├── tasks.py           # Taskiq tasks ⭐
│   └── management/
│       └── commands/
│           └── test_taskiq.py  # Test command
├── manage.py
└── requirements.txt
```

## Key Components

### 1. Broker Configuration (`config/tkq.py`)

This is the heart of the taskiq integration. Key features:

- **Django Initialization**: Properly sets up Django before defining tasks
- **Connection Management**: Critical hooks for database connection handling
  - `worker_startup`: Initializes worker and closes stale connections
  - `worker_shutdown`: Cleans up connections on shutdown
  - `task_preprocessor`: Closes connections before each task
  - `task_postprocessor`: Closes connections after each task

#### Why Connection Management Matters

Django's database connections are **thread-local** and don't work well with async workers. Without proper management:
- Connections can become stale
- Thread-safety issues can occur
- Connection pool exhaustion is possible
- Tasks may fail with "connection already closed" errors

Our solution: **Close connections before and after each task execution** using taskiq's lifecycle hooks.

### 2. Task Definitions (`tasks_demo/tasks.py`)

Example tasks demonstrating:

- **Simple tasks**: No database interaction
- **CRUD operations**: Create, read, update task records
- **Bulk operations**: Efficient batch processing
- **Error handling**: Proper exception handling in async context

#### Important Pattern: `asyncio.to_thread()`

Since Django's ORM is synchronous, we use `asyncio.to_thread()` to run ORM operations in a thread pool:

```python
task = await asyncio.to_thread(
    Task.objects.create,
    title=title,
    description=description
)
```

This allows async tasks to safely interact with Django's synchronous ORM.

### 3. Model (`tasks_demo/models.py`)

A simple `Task` model with:
- Title and description
- Status tracking (pending, processing, completed, failed)
- Timestamps
- Result field for storing task outcomes

## Setup

### 1. Create Virtual Environment

```bash
cd django-taskiq
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install django taskiq taskiq-redis taskiq-dependencies redis
```

### 3. Run Migrations

```bash
python manage.py migrate
```

## Usage

### Testing with InMemoryBroker

The project is configured with `InMemoryBroker` for development (no Redis required):

```bash
# Run all tests
python manage.py test_taskiq --demo=all

# Run specific demos
python manage.py test_taskiq --demo=simple
python manage.py test_taskiq --demo=create
python manage.py test_taskiq --demo=bulk
python manage.py test_taskiq --demo=stats
python manage.py test_taskiq --demo=process
```

### Using with Redis (Production)

For production, update `config/tkq.py` to use the Redis broker:

```python
# Uncomment in config/tkq.py:
broker = ListQueueBroker(
    url="redis://localhost:6379",
).with_result_backend(
    RedisAsyncResultBackend(
        redis_url="redis://localhost:6379",
    )
)
```

Then start a worker:

```bash
# Start the taskiq worker
taskiq worker config.tkq:broker tasks_demo.tasks

# In another terminal, run your tasks
python manage.py test_taskiq
```

## Database Connection Management Deep Dive

### The Challenge

When using taskiq with Django, several connection-related issues can occur:

1. **Stale Connections**: Connections opened in one task may be reused incorrectly
2. **Thread Safety**: Django connections are thread-local, async workers use different threads
3. **Connection Leaks**: Workers may not properly close connections
4. **Transaction Issues**: Failed tasks may leave transactions open

### The Solution

We implement a comprehensive connection management strategy:

```python
@broker.task_preprocessor
async def close_old_connections(task_info):
    """Close connections before each task."""
    connections.close_all()

@broker.task_postprocessor
async def close_connections_after_task(task_info):
    """Close connections after each task."""
    connections.close_all()
```

This ensures:
- ✅ Each task starts with fresh connections
- ✅ No stale or invalid connections are reused
- ✅ Connections are properly released back to the pool
- ✅ No connection leaks over time

### Alternative Approaches

Other patterns you might see:

1. **Persistent Connections**: Keep connections open (not recommended for async)
2. **Connection Per Task**: Create new connection for each task (overhead)
3. **Connection Pooling**: External pool like pgbouncer (adds complexity)

Our approach (**close before/after**) is the simplest and most reliable for Django + taskiq.

## Example Tasks

### Create a Task

```python
from tasks_demo.tasks import create_task_record

# Kick off the task
result = await create_task_record.kiq(
    title="My Task",
    description="Task description"
)

# Wait for result
task_result = await result.wait_result(timeout=5)
print(task_result.return_value)
```

### Process a Task

```python
from tasks_demo.tasks import process_task_record

result = await process_task_record.kiq(task_id=1)
task_result = await result.wait_result(timeout=10)
print(task_result.return_value)
```

### Get Statistics

```python
from tasks_demo.tasks import get_task_statistics

result = await get_task_statistics.kiq()
stats = await result.wait_result(timeout=5)
print(stats.return_value)
```

## Common Patterns

### 1. Error Handling in Tasks

```python
@broker.task
async def my_task(param: str) -> dict:
    try:
        # Task logic here
        result = await do_something(param)
        return {"status": "success", "result": result}
    except Exception as e:
        # Log error, update database, etc.
        return {"status": "error", "error": str(e)}
```

### 2. Database Operations

```python
# Always use asyncio.to_thread for Django ORM
task = await asyncio.to_thread(
    Task.objects.get,
    id=task_id
)

# For updates
task.status = 'completed'
await asyncio.to_thread(task.save)
```

### 3. Bulk Operations

```python
# More efficient than individual creates
tasks = [Task(title=f"Task {i}") for i in range(100)]
await asyncio.to_thread(Task.objects.bulk_create, tasks)
```

## Troubleshooting

### Issue: "Database connection isn't set to UTC"

**Solution**: Ensure `USE_TZ = True` in Django settings and close connections properly.

### Issue: "Connection already closed"

**Solution**: Verify task preprocessor/postprocessor are configured in `tkq.py`.

### Issue: Tasks not executing

**Solution**:
- Check worker is running: `taskiq worker config.tkq:broker tasks_demo.tasks`
- Verify broker configuration
- Check for exceptions in worker logs

### Issue: "No such table" errors

**Solution**: Run migrations: `python manage.py migrate`

## Production Considerations

1. **Use Redis or RabbitMQ**: InMemoryBroker is for development only
2. **Monitor Connections**: Track database connection pool usage
3. **Set Timeouts**: Configure appropriate task timeouts
4. **Error Tracking**: Integrate Sentry or similar for error monitoring
5. **Scaling Workers**: Run multiple workers for high throughput
6. **Health Checks**: Implement worker health monitoring

## Resources

- [Taskiq Documentation](https://taskiq-python.github.io/)
- [Django Database Management](https://docs.djangoproject.com/en/stable/ref/databases/)
- [Django + Celery Patterns](https://docs.celeryproject.org/en/stable/django/) (similar concepts)

## License

MIT License - Feel free to use this as a template for your projects!
