"""
Management command to run demo tasks.

Usage:
    python manage.py run_demo
"""
from django.core.management.base import BaseCommand
from django.db import connection
from example_app.tasks import (
    fetch_and_log_api,
    fetch_parallel,
    create_task_and_fetch,
)
from example_app.models import APILog, Task


class Command(BaseCommand):
    help = 'Run demo tasks to demonstrate asyncio.run() approach'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('Approach 1: asyncio.run() Demo'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write()

        # Show initial state
        api_log_count = APILog.objects.count()
        task_count = Task.objects.count()

        self.stdout.write(f'Initial APILog count: {api_log_count}')
        self.stdout.write(f'Initial Task count: {task_count}')
        self.stdout.write()

        # Run Task 1: Sequential fetching
        self.stdout.write(self.style.WARNING('Running Task 1: Sequential Fetch'))
        self.stdout.write('This will fetch 4 URLs sequentially using async/await')
        self.stdout.write()

        result = fetch_and_log_api.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f'Results: {len(output)} URLs fetched')
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
        self.stdout.write(self.style.WARNING('Running Task 2: Parallel Fetch'))
        self.stdout.write('This will fetch 3 URLs in parallel using asyncio.gather()')
        self.stdout.write()

        result = fetch_parallel.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f'Results: {len(output)} URLs fetched')
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
        self.stdout.write(self.style.WARNING('Running Task 3: Mixed Sync/Async'))
        self.stdout.write('This demonstrates mixing sync ORM before async context')
        self.stdout.write()

        result = create_task_and_fetch.delay()
        self.stdout.write(f'Task ID: {result.id}')
        self.stdout.write('Waiting for result...')

        try:
            output = result.get(timeout=60)
            self.stdout.write(self.style.SUCCESS('✓ Task completed!'))
            self.stdout.write(f'Task count before: {output["task_count_before"]}')
            self.stdout.write(f'Fetch result: {output["fetch_result"]}')
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

        # Show recent logs
        self.stdout.write('Recent API Logs:')
        for log in APILog.objects.all()[:5]:
            self.stdout.write(f'  - {log}')
        self.stdout.write()

        self.stdout.write(self.style.SUCCESS('=' * 70))
        self.stdout.write(self.style.SUCCESS('Demo completed successfully!'))
        self.stdout.write(self.style.SUCCESS('=' * 70))
