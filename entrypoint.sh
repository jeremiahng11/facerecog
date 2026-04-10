#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py create_admin

exec gunicorn faceid.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120
