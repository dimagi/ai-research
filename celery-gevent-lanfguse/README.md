# Celery + Gevent + Langfuse (OpenTelemetry) Bug Reproduction

This project reproduces a bug that occurs when using:
- Django with PostgreSQL (SSL connection)
- Celery with gevent pool
- Langfuse (>3.0) which uses OpenTelemetry

The bug affects SSL verification in psycopg3 connections when all three components are used together.

## Issue Description

When using Celery with the gevent pool and langfuse's OpenTelemetry instrumentation, SSL certificate verification for PostgreSQL connections may fail or behave incorrectly. This is likely due to the interaction between:

1. **gevent's monkey patching** of the SSL module
2. **OpenTelemetry's instrumentation** which modifies threading and context propagation
3. **psycopg3's SSL verification** which depends on the SSL context being properly configured

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL with SSL enabled
- Redis (for Celery broker)
- [uv](https://docs.astral.sh/uv/) - Fast Python package installer (optional but recommended)

### Installation

#### Quick Setup (Automated)

```bash
./setup.sh
```

This will:
- Install uv if not present
- Create virtual environment and install dependencies
- Start PostgreSQL and Redis with Docker
- Run Django migrations

#### Manual Setup

1. Install uv (if not already installed):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Install dependencies:
```bash
uv sync
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your database and langfuse credentials
```

4. Start services:
```bash
docker-compose up -d
```

5. Run migrations:
```bash
uv run python manage.py migrate
```

#### Alternative: Traditional pip Setup

If you prefer not to use uv:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
```

## Running the Reproduction

### Terminal 1: Start Celery Worker with Gevent Pool

```bash
./run_celery_gevent.sh
```

Or manually with uv:
```bash
uv run celery -A bugrepro worker --pool=gevent --concurrency=10 --loglevel=info
```

Or with traditional activation:
```bash
source .venv/bin/activate  # uv creates .venv by default
celery -A bugrepro worker --pool=gevent --concurrency=10 --loglevel=info
```

### Terminal 2: Trigger the Tasks

The `trigger_tasks.py` script supports multiple test modes:

```bash
# Run all tests (simple, http, multiple, mixed, stress)
uv run python trigger_tasks.py

# Run only specific test mode
uv run python trigger_tasks.py --mode simple
uv run python trigger_tasks.py --mode http
uv run python trigger_tasks.py --mode stress

# Customize stress test parameters
uv run python trigger_tasks.py --mode stress --concurrency 50 --http-tasks 20
```

Available modes:
- **simple**: Basic database tasks (3 tasks)
- **http**: HTTP requests with database logging (5 tasks)
- **multiple**: Multiple HTTP requests per task (3 tasks, 3 requests each)
- **mixed**: Combined DB + HTTP + model operations (5 tasks)
- **stress**: High concurrency test (default: 20 concurrent + 10 HTTP tasks)
- **all**: Run all test modes (default)

Or run the standalone test script:
```bash
uv run python reproduce_bug.py
```

## Expected Behavior vs. Actual Behavior

### Expected Behavior
The Celery tasks should:
1. Connect to PostgreSQL using SSL
2. Execute database queries successfully
3. Report telemetry to Langfuse via OpenTelemetry

### Actual Behavior (Bug)
One or more of the following may occur:
- SSL certificate verification failures
- Connection errors to PostgreSQL
- Hangs or timeouts during database operations
- Incorrect SSL context being used for connections

## Components

### Key Files

- `bugrepro/settings.py` - Django settings with PostgreSQL SSL configuration
- `bugrepro/celery.py` - Celery app configuration
- `testapp/tasks.py` - Celery tasks with langfuse decorators
- `run_celery_gevent.sh` - Script to run Celery with gevent pool
- `trigger_tasks.py` - Script to trigger the tasks

### Tasks

The project includes several tasks designed to reproduce the bug under different conditions:

1. **test_db_query**: Executes a raw SQL query using Django's connection cursor. Decorated with `@observe()` from langfuse.

2. **test_db_query_with_model**: Uses Django ORM to query the database. Decorated with `@observe()`.

3. **test_internal_observe**: Uses `@observe()` decorator internally within the task instead of on the task function. Tests whether decorator placement affects the bug.

4. **test_http_with_db_logging**: Makes HTTP requests to httpbin.org and logs each request to the database. Combines HTTP I/O, database writes, and OpenTelemetry tracing. This task is most likely to trigger the bug.

5. **test_multiple_http_requests**: Makes multiple HTTP requests per task, with each request wrapped in an internal `@observe()` decorator. Logs all requests to the database.

6. **test_mixed_operations**: Combines database queries (raw SQL), HTTP requests, and ORM operations in a single task. The most comprehensive test case.

All tasks that interact with the database will potentially trigger SSL verification issues when run with gevent pool and langfuse instrumentation.

## Debugging

To help debug the issue, you can:

1. Enable verbose logging in Celery:
```bash
uv run celery -A bugrepro worker --pool=gevent --loglevel=debug
```

2. Check PostgreSQL logs for SSL-related errors

3. Add debug logging to tasks:
```python
import logging
logger = logging.getLogger(__name__)
logger.debug("Connection info: %s", connection.settings_dict)
```

4. Test without gevent pool (for comparison):
```bash
uv run celery -A bugrepro worker --pool=solo --loglevel=info
```

5. Test without langfuse decorators (remove `@observe()`)

6. Use Django management command for isolated testing:
```bash
uv run python manage.py test_bug --with-gevent --with-langfuse
```

## Advanced Reproduction Tools

For intermittent bugs, we provide specialized tools to increase reproduction likelihood. See **[REPRODUCING_THE_BUG.md](REPRODUCING_THE_BUG.md)** for detailed strategies.

### Quick Reference

**Test monkey patching order** (affects SSL context initialization):
```bash
uv run python test_monkey_patching.py --strategy early_aggressive
uv run python test_monkey_patching.py --strategy late_aggressive
```

**Stress test connection pool** (expose race conditions):
```bash
uv run python test_connection_pool.py --cycles 200 --greenlets 30
```

**Inspect SSL context** (diagnostic tool):
```bash
uv run python inspect_ssl_context.py
```

**Run with early patching** (patch before all imports):
```bash
uv run python celery_worker_early_patch.py --pool=gevent --concurrency=20
```

**Long-running stress test**:
```bash
uv run python trigger_tasks.py --mode long --concurrency 30 --duration 300
```

## Workarounds

Potential workarounds to try:

1. Use a different Celery pool (prefork, solo) instead of gevent
2. Disable OpenTelemetry instrumentation for database connections
3. Use psycopg2 instead of psycopg3
4. Adjust gevent monkey patching order
5. Configure SSL context manually before gevent patches

## Dependencies

- Django 4.2.x
- Celery 5.3+
- gevent 23.0+
- psycopg 3.1+ (with binary)
- langfuse 3.0+
- PostgreSQL with SSL support

Dependencies are managed via `pyproject.toml` and can be installed with:
- **uv** (recommended) - ~10-100x faster than pip
- **pip** - traditional package manager (requirements.txt included for compatibility)

## Related Issues

This bug may be related to:
- gevent's monkey patching of SSL module
- OpenTelemetry's context propagation in async environments
- psycopg3's SSL context handling
- Thread-local storage in gevent greenlets

## Contributing

To help debug or fix this issue:
1. Try different versions of the dependencies
2. Add detailed logging at each layer
3. Profile the SSL handshake process
4. Compare behavior with/without each component
