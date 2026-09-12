# Lab 10 — container image for the bank transaction-triage agent
# Multi-stage-free, small, and production-sane (non-root, healthcheck, pinned base).

FROM python:3.12-slim

# Don't write .pyc, unbuffered logs (so Container Apps captures them live)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install deps first (better layer caching)
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app/ /app/

# Run as a non-root user (bank security baseline)
RUN useradd -m -u 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Container-level healthcheck (Container Apps also has its own probes)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

# Start the API. Container Apps sets/knows the target port; we bind 0.0.0.0.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
