FROM python:3.11-slim

# Install system dependencies required by dlib/face_recognition and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake \
    gcc \
    g++ \
    make \
    libopenblas-dev \
    liblapack-dev \
    libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create and activate a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Run Django build-time management commands
RUN python manage.py collectstatic --noinput \
 && python manage.py migrate --noinput \
 && python manage.py create_admin

EXPOSE 8000

CMD ["sh", "-c", "gunicorn faceid.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120"]
