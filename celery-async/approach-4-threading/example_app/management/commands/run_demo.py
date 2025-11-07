"""
Management command to run demo tasks.

Usage:
    python manage.py run_demo
"""
from django.core.management.base import BaseCommand
from example_app.tasks import (
    fetch_and_log_api,
    parallel_async_threads,
    complex_parallel_workflow,
    mixed_sync_async_threading,
    sequential_async_operations,
    error_handling_threads,
)
from example_app.models import APILog, Task


class Command(BaseCommand):
    help = 'Run demo tasks to demonstrate threading with async code approach'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('Approach 4: Threading with Async Code Demo'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write()

        # Show initial state
        api_log_count = APILog.objects.count()
        task_count = Task.objects.count()

        self.stdout.write(f'Initial APILog count: {api_log_count}')
        self.stdout.write(f'Initial Task count: {task_count}')
        self.stdout.write()

        # Run Task 1: Basic threading with async
        self.stdout.write(self.style.WARNING('Task 1: Async Code in Thread'))
        self.stdout.write('Runs async code in a dedicated thread with its own event loop')
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

        # Run Task 2: Parallel async threads
        self.stdout.write(self.style.WARNING('Task 2: Parallel Async Threads'))
        self.stdout.write('Runs multiple async operations in parallel threads (3 concurrent)')
        self.stdout.write()

        result = parallel_async_threads.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Completed {len(output)} parallel operations")
            for item in output:
                if 'error' in item:
                    self.stdout.write(f"  - ERROR: {item['error']}")
                else:
                    self.stdout.write(
                        f"  - Operation {item['operation_id']}: "
                        f"status={item['status']} [log_id={item['log_id']}]"
                    )
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 3: Complex parallel workflow
        self.stdout.write(self.style.WARNING('Task 3: Complex Parallel Workflow'))
        self.stdout.write('Demonstrates multiple independent async workflows in parallel')
        self.stdout.write()

        result = complex_parallel_workflow.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Fetch result: {output.get('fetch')}")
            self.stdout.write(f"Process result: {output.get('process')}")
            self.stdout.write(f"Aggregate result: {output.get('aggregate')}")
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 4: Mixed sync/async
        self.stdout.write(self.style.WARNING('Task 4: Mixed Sync/Async with Threading'))
        self.stdout.write('Demonstrates elegant mixing of sync ORM and threaded async code')
        self.stdout.write()

        result = mixed_sync_async_threading.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Initial count: {output['initial_count']}")
            self.stdout.write(f"Final count: {output['final_count']}")
            self.stdout.write(f"Created: {output['created']}")
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 5: Sequential async operations
        self.stdout.write(self.style.WARNING('Task 5: Sequential Async Operations'))
        self.stdout.write('Runs async operations sequentially, each in its own thread')
        self.stdout.write()

        result = sequential_async_operations.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            for item in output:
                self.stdout.write(
                    f"  - {item['url']}: {item['status']} [log_id={item['log_id']}]"
                )
            self.stdout.write()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Task failed: {e}'))
            self.stdout.write()

        # Run Task 6: Error handling
        self.stdout.write(self.style.WARNING('Task 6: Error Handling in Threads'))
        self.stdout.write('Demonstrates error handling with threading and async code')
        self.stdout.write()

        result = error_handling_threads.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f"Total operations: {output['total']}")
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
