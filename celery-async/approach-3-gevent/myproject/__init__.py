# CRITICAL: Import gevent and monkey-patch FIRST, before anything else
# This must happen before any other imports to ensure proper patching
import gevent.monkey
gevent.monkey.patch_all()

# Now import the Celery app
from .celery import app as celery_app

__all__ = ('celery_app',)
