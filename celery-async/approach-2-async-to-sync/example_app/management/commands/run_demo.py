"""
Management command to run demo tasks.

Usage:
    python manage.py run_demo
"""
from django.core.management.base import BaseCommand
from example_app.tasks import (
    fetch_and_log_api,
    fetch_parallel,
    mixed_sync_async_task,
    using_sync_to_async,
    complex_workflow,
)
from example_app.models import APILog, Task


class Command(BaseCommand):
    help = 'Run demo tasks to demonstrate async_to_sync approach'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('Approach 2: async_to_sync Demo'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write()

        # Show initial state
        api_log_count = APILog.objects.count()
        task_count = Task.objects.count()

        self.stdout.write(f'Initial APILog count: {api_log_count}')
        self.stdout.write(f'Initial Task count: {task_count}')
        self.stdout.write()

        # Run Task 1: Sequential fetching
        self.stdout.write(self.style.WARNING('Task 1: Sequential Fetch with async_to_sync'))
        self.stdout.write('Demonstrates using async_to_sync to wrap async functions')
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

        # Run Task 2: Parallel fetching
        self.stdout.write(self.style.WARNING('Task 2: Parallel Fetch with asyncio.gather()'))
        self.stdout.write('Demonstrates concurrent async operations')
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

        # Run Task 3: Mixed sync/async
        self.stdout.write(self.style.WARNING('Task 3: Mixed Sync/Async Operations'))
        self.stdout.write('Demonstrates elegant mixing of sync and async code')
        self.stdout.write()

        result = mixed_sync_async_task.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Task count before: {output['task_count_before']}")
            self.stdout.write(f"Task count after: {output['task_count_after']}")
            self.stdout.write(f"API log count before: {output['api_log_count_before']}")
            self.stdout.write(f"Fetch result: {output['fetch_result']}")
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 4: sync_to_async demo
        self.stdout.write(self.style.WARNING('Task 4: sync_to_async Demo'))
        self.stdout.write('Demonstrates calling sync functions from async context')
        self.stdout.write()

        result = using_sync_to_async.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Result: {output}")
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 5: Complex workflow
        self.stdout.write(self.style.WARNING('Task 5: Complex Workflow'))
        self.stdout.write('Demonstrates real-world scenario with multiple sync/async transitions')
        self.stdout.write()

        result = complex_workflow.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Initial state: {output['initial_state']}")
            self.stdout.write(f"Final state: {output['final_state']}")
            self.stdout.write(f"Successful requests: {output['successful']}")
            self.stdout.write(f"Failed requests: {output['failed']}")
            self.stdout.write(f"Summary: {output['summary']}")
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
