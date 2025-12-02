"""
Demo tasks for taskiq + Django integration.

These tasks demonstrate:
1. Basic async task execution
2. Database operations within tasks
3. Proper connection management
4. Error handling
"""
import asyncio
from datetime import datetime
from config.tkq import broker, with_db_connection_management
from tasks_demo.models import Task


@broker.task
async def simple_task(message: str) -> str:
    """
    A simple task that doesn't interact with the database.

    Args:
        message: A message to process

    Returns:
        The processed message
    """
    await asyncio.sleep(1)  # Simulate some work
    return f"Processed: {message}"


@broker.task
@with_db_connection_management
async def create_task_record(title: str, description: str = "") -> dict:
    """
    Create a new Task record in the database.

    This demonstrates proper database operations within a taskiq task.
    The connection management (open/close) is handled by the
    with_db_connection_management decorator.

    Args:
        title: The task title
        description: Optional task description

    Returns:
        Dictionary with created task details
    """
    # Import here to ensure we're using the properly initialized Django ORM
    from tasks_demo.models import Task

    # Create the task (Django ORM operations work in async context with proper setup)
    task = await asyncio.to_thread(
        Task.objects.create,
        title=title,
        description=description,
        status='pending'
    )

    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "created_at": task.created_at.isoformat(),
    }


@broker.task
@with_db_connection_management
async def process_task_record(task_id: int) -> dict:
    """
    Process a task record by updating its status.

    This demonstrates:
    1. Reading from the database
    2. Performing work
    3. Updating the database
    4. Error handling

    Args:
        task_id: The ID of the task to process

    Returns:
        Dictionary with processing results
    """
    from tasks_demo.models import Task
    from django.utils import timezone

    try:
        # Fetch the task
        task = await asyncio.to_thread(
            Task.objects.get,
            id=task_id
        )

        # Update status to processing
        task.status = 'processing'
        await asyncio.to_thread(task.save)

        # Simulate work
        await asyncio.sleep(2)
        result_message = f"Task '{task.title}' processed at {datetime.now().isoformat()}"

        # Update status to completed
        task.status = 'completed'
        task.result = result_message
        await asyncio.to_thread(task.save)

        return {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "result": task.result,
        }

    except Task.DoesNotExist:
        # Update to failed if task not found
        return {
            "error": f"Task with id {task_id} not found",
            "status": "failed"
        }
    except Exception as e:
        # Handle other errors
        try:
            task = await asyncio.to_thread(Task.objects.get, id=task_id)
            task.status = 'failed'
            task.result = str(e)
            await asyncio.to_thread(task.save)
        except:
            pass

        return {
            "error": str(e),
            "status": "failed",
            "task_id": task_id
        }


@broker.task
@with_db_connection_management
async def bulk_create_tasks(count: int = 5) -> dict:
    """
    Create multiple task records in bulk.

    This demonstrates bulk operations with the database.

    Args:
        count: Number of tasks to create

    Returns:
        Dictionary with summary of created tasks
    """
    from tasks_demo.models import Task

    tasks_to_create = [
        Task(
            title=f"Bulk Task {i+1}",
            description=f"Auto-generated task {i+1}",
            status='pending'
        )
        for i in range(count)
    ]

    # Bulk create
    created_tasks = await asyncio.to_thread(
        Task.objects.bulk_create,
        tasks_to_create
    )

    return {
        "created_count": len(created_tasks),
        "task_ids": [task.id for task in created_tasks],
    }


@broker.task
@with_db_connection_management
async def get_task_statistics() -> dict:
    """
    Get statistics about tasks in the database.

    This demonstrates aggregation queries with the database.

    Returns:
        Dictionary with task statistics
    """
    from tasks_demo.models import Task
    from django.db.models import Count

    # Get counts by status - convert to list inside the thread
    stats = await asyncio.to_thread(
        lambda: list(Task.objects.values('status').annotate(count=Count('id')))
    )

    total = await asyncio.to_thread(Task.objects.count)

    return {
        "total_tasks": total,
        "by_status": {item['status']: item['count'] for item in stats},
    }
