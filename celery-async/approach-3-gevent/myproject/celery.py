"""
Celery configuration for approach 3: Gevent worker pool

CRITICAL: This must be imported AFTER gevent.monkey.patch_all()
The __init__.py handles the monkey-patching before importing this module.

Gevent uses green threads (greenlets) for concurrency instead of
traditional threads or asyncio.
"""
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
