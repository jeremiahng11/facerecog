#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py create_admin

# Use Daphne (ASGI) when Channels is installed so WebSockets work.
# Falls back to Gunicorn (WSGI) for pure-HTTP deployments.
if python -c "import daphne, channels" 2>/dev/null; then
  echo "Starting Daphne ASGI server (HTTP + WebSocket support)"
  exec daphne -b 0.0.0.0 -p ${PORT:-8000} faceid.asgi:application
else
  echo "Starting Gunicorn WSGI server (HTTP only)"
  exec gunicorn faceid.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120
fi
