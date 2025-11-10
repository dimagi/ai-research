# Guide to Reproducing the SSL Verification Bug

This document provides strategies and tools for reproducing the intermittent SSL verification bug that occurs with the combination of:
- Celery with gevent pool
- Langfuse (OpenTelemetry) instrumentation
- psycopg3 with SSL connections

## Understanding the Bug

The bug is likely related to **interference between gevent's monkey patching and OpenTelemetry's context propagation**, affecting how SSL contexts are managed in thread-local storage when using greenlets.

### Key Factors

1. **Monkey Patching Order**: The order in which gevent patches modules vs. when Django/OTEL initializes
2. **Thread-Local Storage**: gevent greenlets vs real threads and how SSL contexts are stored
3. **Connection Pooling**: Race conditions when multiple greenlets access the connection pool
4. **Timing**: Specific timing patterns that expose race conditions
5. **Context Propagation**: How OTEL propagates context across greenlets

## Reproduction Tools

### 1. Monkey Patching Experiments

Test different monkey patching strategies to identify which module interactions cause the bug.

**Each strategy runs in a separate Python process** to avoid interference from previous monkey patches.

```bash
# Test all strategies automatically (each in separate process)
uv run python test_monkey_patching.py

# Or test specific strategy only
uv run python test_monkey_patching.py --strategy early_aggressive
uv run python test_monkey_patching.py --strategy late_aggressive

# Test with more attempts per strategy
uv run python test_monkey_patching.py --strategy early_aggressive --attempts 100
uv run python test_monkey_patching.py --attempts 50  # All strategies, 50 attempts each
```

**Strategies**:
- `early_aggressive`: Patch everything before Django/OTEL imports
- `early_minimal`: Patch only socket/SSL early
- `late_aggressive`: Import Django/OTEL first, then patch everything
- `late_minimal`: Import Django/OTEL first, then patch socket/SSL only
- `ssl_only`: Patch only the SSL module
- `no_ssl`: Patch everything except SSL

When running with `--strategy all` (default), the script spawns a subprocess for each strategy to ensure complete isolation.

### 2. Connection Pool Stress Testing

Aggressively stress the connection pool to expose race conditions:

```bash
# Run all connection pool tests
uv run python test_connection_pool.py

# Test specific scenarios
uv run python test_connection_pool.py --test cycling --cycles 500
uv run python test_connection_pool.py --test concurrent --greenlets 50
uv run python test_connection_pool.py --test rapid --duration 30
```

**Tests**:
- `cycling`: Rapidly open/close connections to stress the pool
- `concurrent`: Many simultaneous connections from different greenlets
- `mixed`: Mixed operations with varying timing
- `rapid`: Continuous operations with rapid context switches

### 3. SSL Context Inspection

Diagnose SSL context behavior:

```bash
# Run full diagnostic
uv run python inspect_ssl_context.py
```

This shows:
- SSL module state and patching status
- Thread-local storage behavior in greenlets
- psycopg3 internals
- Database connection SSL parameters
- Behavior with langfuse tracing

### 4. Multi-Worker Setup

Test with multiple worker processes (exposes more race conditions):

```bash
# Single worker with early patching
uv run python celery_worker_early_patch.py --pool=gevent --concurrency=10

# Multiple workers (manual for now)
# Terminal 1:
uv run python celery_worker_early_patch.py --pool=gevent --concurrency=10 -n worker1@%h

# Terminal 2:
uv run python celery_worker_early_patch.py --pool=gevent --concurrency=10 -n worker2@%h

# Terminal 3:
uv run python celery_worker_early_patch.py --pool=gevent --concurrency=10 -n worker3@%h
```

### 5. Long-Running Stress Test

Run continuous operations to catch intermittent issues:

```bash
# Run for extended period
uv run python trigger_tasks.py --mode long --concurrency 20 --duration 300

# Very aggressive
uv run python trigger_tasks.py --mode long --concurrency 50 --duration 600
```

### 6. LangGraph Threading + Gevent Test ⚠️ CRITICAL

**This test is specifically designed to reproduce thread interference issues**, as langgraph uses real threads internally which can conflict with gevent's monkey patching:

```bash
# Run all tests
uv run python test_langgraph_gevent.py

# Test with more greenlets and rounds
uv run python test_langgraph_gevent.py --greenlets 50 --rounds 5

# Test only concurrent workflows (most aggressive)
uv run python test_langgraph_gevent.py --test concurrent --greenlets 30
```

**Why this is critical:**
- Langgraph uses **real OS threads** internally for workflow execution
- Gevent's monkey patching modifies thread-related modules
- **SSL context is stored in thread-local storage**
- When greenlets switch during thread execution, SSL context can be accessed from wrong thread
- This creates the exact race condition that causes SSL verification failures

**Tests:**
- `basic`: Multiple rounds of concurrent greenlets running langgraph workflows
- `concurrent`: Maximum stress with rapid context switches during workflow execution
- `all`: Both tests (default)

This test is the most likely to reproduce the bug if thread interaction is the root cause.

## Recommended Reproduction Strategy

### Phase 1: Identify Trigger Conditions

1. **⚠️ PRIORITY: Test LangGraph + Gevent thread interference** (most likely to reproduce):
   ```bash
   uv run python test_langgraph_gevent.py --greenlets 50 --rounds 5
   ```

2. **Test monkey patching order** (all strategies with concurrent greenlets):
   ```bash
   uv run python test_monkey_patching.py --attempts 50
   ```

   Or test specific strategies:
   ```bash
   uv run python test_monkey_patching.py --strategy early_aggressive --attempts 50
   uv run python test_monkey_patching.py --strategy late_aggressive --attempts 50
   ```

3. **Stress connection pool**:
   ```bash
   uv run python test_connection_pool.py --cycles 200 --greenlets 30
   ```

4. **Run diagnostic**:
   ```bash
   uv run python inspect_ssl_context.py
   ```

### Phase 2: Aggressive Stress Testing

1. **Start Celery with early patching**:
   ```bash
   uv run python celery_worker_early_patch.py --pool=gevent --concurrency=20 --loglevel=debug
   ```

2. **Run long stress test**:
   ```bash
   uv run python trigger_tasks.py --mode long --concurrency 30 --duration 300
   ```

3. **Monitor for errors**:
   - SSL verification failures
   - Connection timeouts
   - "certificate verify failed" errors
   - Greenlet context errors

### Phase 3: Vary Conditions

Try different combinations:

```bash
# High concurrency
uv run python celery_worker_early_patch.py --pool=gevent --concurrency=50

# With multiple workers (3 workers × 15 greenlets = 45 total)
# (Run in separate terminals or use celery multi)

# Maximum database connections
uv run python trigger_tasks.py --mode stress --concurrency 100 --http-tasks 50
```

## What to Look For

### Error Patterns

1. **SSL Verification Errors**:
   ```
   ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
   psycopg.OperationalError: SSL error
   ```

2. **Connection Errors**:
   ```
   connection refused
   connection reset by peer
   connection timeout
   ```

3. **Context Errors**:
   ```
   AttributeError: 'greenlet' object has no attribute
   RuntimeError: cannot access local object in different thread
   ```

4. **Greenlet Errors**:
   ```
   GreenletExit
   Timeout
   ```

### Success Indicators

- All tests pass consistently
- No SSL errors even under high load
- Connections establish reliably
- No timeouts or hangs

## Environment Variables to Try

Test with different configurations in `.env`:

```bash
# Strict SSL
DB_SSLMODE=verify-full

# Require SSL but don't verify
DB_SSLMODE=require

# Disable SSL (for comparison)
DB_SSLMODE=prefer
```

## Additional Debugging

### Enable Django Debug Logging

Add to `bugrepro/settings.py`:

```python
LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

### Monitor PostgreSQL Logs

```bash
docker-compose logs -f postgres | grep SSL
```

### Track Connection Count

```sql
SELECT count(*) FROM pg_stat_activity WHERE datname = 'bugrepro';
```

## Theory: Why It's Hard to Reproduce

The bug likely requires a specific sequence of events:

1. Greenlet context switch during SSL handshake
2. OTEL context propagation at wrong moment
3. SSL context accessed from wrong greenlet/thread
4. Connection pool exhaustion or specific pool state
5. Race condition in thread-local storage access

These conditions may only align occasionally, making the bug intermittent.

## Next Steps If Bug Is Not Reproduced

1. **Try production-like load**: Run for hours/days with continuous traffic
2. **Vary database settings**: Different SSL modes, connection limits
3. **Test with older/newer versions**: Try different versions of gevent, psycopg3, langfuse
4. **Add instrumentation**: Patch SSL/connection code to log internal state
5. **Use debugger**: Attach debugger and break on SSL context creation
6. **Profile**: Use profiler to see where time is spent during failures

## Reporting Results

When you observe the bug, capture:

1. Full error message and traceback
2. Monkey patching configuration used
3. Number of workers/greenlets/concurrency
4. Database connection count
5. Output from `inspect_ssl_context.py`
6. Celery worker logs
7. PostgreSQL logs
8. Timing (how long until failure)

This information will help identify the root cause.
