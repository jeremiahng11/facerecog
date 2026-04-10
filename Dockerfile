FROM python:3.11-slim

# Install system dependencies required by dlib/face_recognition and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libboost-all-dev \
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

# Run build-time management commands (no env vars needed)
RUN python manage.py collectstatic --noinput

# Copy and register the runtime entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
