"""
Management command to run demo tasks.

Usage:
    python manage.py run_demo
"""
from django.core.management.base import BaseCommand
from example_app.tasks import (
    fetch_and_log_api,
    fetch_parallel,
    high_concurrency_demo,
    mixed_io_cpu_task,
    database_operations,
    error_handling_demo,
)
from example_app.models import APILog, Task


class Command(BaseCommand):
    help = 'Run demo tasks to demonstrate gevent worker pool approach'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('Approach 3: Gevent Worker Pool Demo'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.WARNING(
            'NOTE: Worker must be started with: '
            'celery -A myproject worker --pool=gevent --concurrency=100'
        ))
        self.stdout.write()

        # Show initial state
        api_log_count = APILog.objects.count()
        task_count = Task.objects.count()

        self.stdout.write(f'Initial APILog count: {api_log_count}')
        self.stdout.write(f'Initial Task count: {task_count}')
        self.stdout.write()

        # Run Task 1: Sequential fetching (but concurrent due to gevent)
        self.stdout.write(self.style.WARNING('Task 1: Sequential Fetch (Concurrent via Gevent)'))
        self.stdout.write('Uses standard blocking code - gevent makes it concurrent automatically')
        self.stdout.write()

        result = fetch_and_log_api.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            for item in output:
                if 'error' in item:
                    self.stdout.write(f"  - {item['url']}: ERROR - {item['error']}")
                else:
                    self.stdout.write(
                        f"  - {item['url']}: {item['status']} "
                        f"({item['time']:.2f}s) [log_id={item['log_id']}]"
                    )
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 2: Parallel with explicit greenlets
        self.stdout.write(self.style.WARNING('Task 2: Explicit Parallel Fetch with Greenlets'))
        self.stdout.write('Uses gevent.spawn() for explicit concurrent execution')
        self.stdout.write()

        result = fetch_parallel.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            for item in output:
                if 'error' in item:
                    self.stdout.write(f"  - {item['url']}: ERROR - {item['error']}")
                else:
                    self.stdout.write(
                        f"  - {item['url']}: {item['status']} "
                        f"({item['time']:.2f}s) [log_id={item['log_id']}]"
                    )
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 3: High concurrency
        self.stdout.write(self.style.WARNING('Task 3: High Concurrency Demo'))
        self.stdout.write('Spawns 20 greenlets to demonstrate high concurrency')
        self.stdout.write()

        result = high_concurrency_demo.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Total requests: {output['total']}")
            self.stdout.write(f"Successful: {output['successful']}")
            self.stdout.write(f"Failed: {output['failed']}")
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 4: Mixed I/O and CPU
        self.stdout.write(self.style.WARNING('Task 4: Mixed I/O and CPU Operations'))
        self.stdout.write('Demonstrates that gevent is good for I/O, not CPU-bound work')
        self.stdout.write()

        result = mixed_io_cpu_task.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Results: {output}")
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 5: Database operations
        self.stdout.write(self.style.WARNING('Task 5: Database Operations'))
        self.stdout.write('Demonstrates proper database connection handling')
        self.stdout.write()

        result = database_operations.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Created tasks: {output['created_tasks']}")
            self.stdout.write(f"Total tasks: {output['total_tasks']}")
            self.stdout.write(f"Total logs: {output['total_logs']}")
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 6: Error handling
        self.stdout.write(self.style.WARNING('Task 6: Error Handling Demo'))
        self.stdout.write('Tests fetching URLs with various HTTP status codes')
        self.stdout.write()

        result = error_handling_demo.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Total: {output['total']}")
            self.stdout.write(f"Successful: {output['successful']}")
            self.stdout.write(f"Failed: {output['failed']}")
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Show final state
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('Final Database State'))
        self.stdout.write(self.style.SUCCESS('=' * 70))

        final_api_log_count = APILog.objects.count()
        final_task_count = Task.objects.count()

        self.stdout.write(f'Final APILog count: {final_api_log_count} '
                         f'(+{final_api_log_count - api_log_count})')
        self.stdout.write(f'Final Task count: {final_task_count} '
                         f'(+{final_task_count - task_count})')
        self.stdout.write()

        self.stdout.write('Recent API Logs:')
        for log in APILog.objects.all()[:5]:
            self.stdout.write(f'  - {log}')
        self.stdout.write()

        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('Demo completed successfully!'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
