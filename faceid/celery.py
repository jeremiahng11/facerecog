"""
Celery application setup.

Uses REDIS_URL env var (auto-injected by Railway's Redis plugin).
If Redis is not configured, tasks become no-ops — the code still runs.

To start workers on Railway:
  celery -A faceid worker -l info
  celery -A faceid beat -l info   (for scheduled tasks)
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'faceid.settings')

app = Celery('faceid')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


# ─── Periodic schedule (Celery Beat) ─────────────────────────────────────────
# Resets every active staff user's credit balance to their monthly allowance
# at 00:01 Singapore time on CREDIT_RESET_DAY (default 1st of the month).
CREDIT_RESET_DAY = int(os.environ.get('CREDIT_RESET_DAY', '1'))

app.conf.beat_schedule = {
    'reset-monthly-credits': {
        'task': 'accounts.tasks.reset_monthly_credits',
        # Note: crontab is UTC by default; align with Asia/Singapore.
        'schedule': crontab(hour=16, minute=1, day_of_month=str(CREDIT_RESET_DAY - 1 if CREDIT_RESET_DAY > 1 else 'last')),
        # At 16:01 UTC on the day before = 00:01 SGT on CREDIT_RESET_DAY.
    },
}

app.conf.timezone = 'UTC'
