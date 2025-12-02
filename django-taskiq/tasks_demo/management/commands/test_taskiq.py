"""
Management command to test taskiq integration with Django.
"""
import asyncio
from django.core.management.base import BaseCommand
from tasks_demo.tasks import (
    simple_task,
    create_task_record,
    process_task_record,
    bulk_create_tasks,
    get_task_statistics,
)


class Command(BaseCommand):
    help = 'Test taskiq tasks with Django'

    def add_arguments(self, parser):
        parser.add_argument(
            '--demo',
            type=str,
            choices=['simple', 'create', 'process', 'bulk', 'stats', 'all'],
            default='all',
            help='Which demo to run'
        )

    def handle(self, *args, **options):
        demo = options['demo']

        if demo in ['simple', 'all']:
            self.stdout.write(self.style.SUCCESS('\n=== Testing Simple Task ==='))
            asyncio.run(self.test_simple_task())

        if demo in ['create', 'all']:
            self.stdout.write(self.style.SUCCESS('\n=== Testing Create Task ==='))
            asyncio.run(self.test_create_task())

        if demo in ['bulk', 'all']:
            self.stdout.write(self.style.SUCCESS('\n=== Testing Bulk Create ==='))
            asyncio.run(self.test_bulk_create())

        if demo in ['stats', 'all']:
            self.stdout.write(self.style.SUCCESS('\n=== Testing Statistics ==='))
            asyncio.run(self.test_statistics())

        if demo in ['process', 'all']:
            self.stdout.write(self.style.SUCCESS('\n=== Testing Process Task ==='))
            asyncio.run(self.test_process_task())

    async def test_simple_task(self):
        """Test simple task without database operations."""
        self.stdout.write("Kicking off simple task...")
        result = await simple_task.kiq("Hello from Django!")
        self.stdout.write(f"Task kicked: {result.task_id}")

        # Wait for result (in-memory broker returns immediately)
        task_result = await result.wait_result(timeout=5)
        self.stdout.write(self.style.SUCCESS(f"Result: {task_result.return_value}"))

    async def test_create_task(self):
        """Test creating a task record in the database."""
        self.stdout.write("Creating task record...")
        result = await create_task_record.kiq(
            title="Test Task from Management Command",
            description="This task was created to test taskiq integration"
        )

        task_result = await result.wait_result(timeout=5)
        if task_result.is_err:
            self.stdout.write(self.style.ERROR(f"Error: {task_result.error}"))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Created task: {task_result.return_value}"
            ))

    async def test_bulk_create(self):
        """Test bulk creating task records."""
        self.stdout.write("Bulk creating 5 tasks...")
        result = await bulk_create_tasks.kiq(count=5)

        task_result = await result.wait_result(timeout=5)
        if task_result.is_err:
            self.stdout.write(self.style.ERROR(f"Error: {task_result.error}"))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Bulk created: {task_result.return_value}"
            ))

    async def test_statistics(self):
        """Test getting task statistics."""
        self.stdout.write("Getting task statistics...")
        result = await get_task_statistics.kiq()

        task_result = await result.wait_result(timeout=5)
        if task_result.is_err:
            self.stdout.write(self.style.ERROR(f"Error: {task_result.error}"))
        else:
            stats = task_result.return_value
            self.stdout.write(self.style.SUCCESS(f"Statistics: {stats}"))

    async def test_process_task(self):
        """Test processing a task record."""
        # First create a task to process
        self.stdout.write("Creating a task to process...")
        create_result = await create_task_record.kiq(
            title="Task to be processed",
            description="This task will be processed by the worker"
        )

        task_result = await create_result.wait_result(timeout=5)
        if task_result.is_err:
            self.stdout.write(self.style.ERROR(f"Error creating task: {task_result.error}"))
            return

        task_id = task_result.return_value['id']
        self.stdout.write(f"Created task with ID: {task_id}")

        # Now process it
        self.stdout.write("Processing task...")
        process_result = await process_task_record.kiq(task_id=task_id)

        final_result = await process_result.wait_result(timeout=10)
        if final_result.is_err:
            self.stdout.write(self.style.ERROR(f"Error: {final_result.error}"))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Processed task: {final_result.return_value}"
            ))
