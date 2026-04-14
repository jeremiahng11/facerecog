#!/bin/sh
# Celery Worker entrypoint — deploy as a separate Railway service.
# Railway service → Settings → Start Command: /app/celery-worker.sh
set -e
exec celery -A faceid worker -l info --concurrency 2
