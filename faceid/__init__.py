# Import the Celery app so shared_task decorators register correctly.
# Wrapped in try/except so the project still runs if Celery is not installed
# (e.g. during initial deploy before the Redis + Celery services are added).
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    pass
