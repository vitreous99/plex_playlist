# =============================================================================
# ADB Bridge — FastAPI service for Android Debug Bridge (ADB) orchestration
# =============================================================================
# This container exposes HTTP endpoints to wake devices and launch apps
# via ADB over TCP.

FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies: Google platform-tools ADB + network diagnostics
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    unzip \
    iputils-ping \
    iproute2 \
    && wget -q https://dl.google.com/android/repository/platform-tools-latest-linux.zip -O /tmp/pt.zip \
    && unzip -q /tmp/pt.zip -d /opt \
    && rm /tmp/pt.zip \
    && apt-get purge -y wget unzip \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/platform-tools:${PATH}"

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
