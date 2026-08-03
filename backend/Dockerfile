FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for fastembed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the fastembed model at build time (as root, before switching user)
ENV FASTEMBED_CACHE_PATH=/app/.cache/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding()"

COPY . .

# Create non-root user and grant access to the model cache.
#
# /data is created here on purpose, owned by appuser, even though a named volume
# is mounted over it at runtime. Docker seeds an empty named volume from the
# image path, ownership included; without this the volume would arrive owned by
# root, the daily-budget file would be unwritable, and the budget module refuses
# rather than failing open. That would take every paid call down.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser \
    && mkdir -p /data \
    && chown -R appuser:appgroup /app/.cache /data
USER appuser

# Railway uses dynamic PORT
ENV PORT=8000
EXPOSE $PORT

CMD uvicorn main:app --host 0.0.0.0 --port $PORT
