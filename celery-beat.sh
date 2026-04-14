#!/bin/sh
# Celery Beat scheduler entrypoint — deploy as a separate Railway service.
# Railway service → Settings → Start Command: /app/celery-beat.sh
# Optional: use GitHub Actions cron instead (see .github/workflows/).
set -e
exec celery -A faceid beat -l info
