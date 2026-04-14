"""
Background tasks for the cafeteria system. Uses Celery if available,
otherwise these are just plain functions that can be called via management commands.
"""
import logging
from django.core.management import call_command

logger = logging.getLogger(__name__)

try:
    from celery import shared_task
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    # Decorator that just returns the function unchanged.
    def shared_task(*args, **kwargs):
        def wrap(fn):
            return fn
        # Allow usage with and without parentheses.
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return wrap


@shared_task
def reset_monthly_credits():
    """
    Scheduled task: reset every active staff user's credit balance on
    CREDIT_RESET_DAY at 00:01 Singapore time.
    Celery Beat schedule to add:
        'reset-monthly-credits': {
            'task': 'accounts.tasks.reset_monthly_credits',
            'schedule': crontab(hour=0, minute=1, day_of_month=CREDIT_RESET_DAY),
        }
    """
    logger.info('Running monthly credit reset')
    call_command('reset_credits')
    return 'ok'


@shared_task
def send_order_email_async(order_id: int, email: str):
    """Send an order receipt email asynchronously."""
    from .models import Order
    from .emails import send_order_receipt
    try:
        order = Order.objects.get(pk=order_id)
        send_order_receipt(order, email)
    except Order.DoesNotExist:
        logger.warning(f'Order {order_id} not found for email receipt')
