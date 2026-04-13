# =============================================================================
# ADB Bridge — FastAPI service for Android Debug Bridge (ADB) orchestration
# =============================================================================
# This container exposes HTTP endpoints to wake devices and launch apps
# via ADB over TCP.

FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies: ADB tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    android-tools-adb \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:9000/health', timeout=5.0)"

# Expose port for HTTP API
EXPOSE 9000

# Run the application
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
