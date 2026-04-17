#!/bin/sh
# Wait for the app to be reachable before starting tailscaled
# This prevents Serve race conditions where Tailscale tries to proxy
# to a service that isn't ready yet.

set -e

# Configuration
APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-80}"
MAX_ATTEMPTS=60
WAIT_INTERVAL=2

echo "[$(date)] Waiting for app at $APP_HOST:$APP_PORT to be reachable..."

ATTEMPTS=0
while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    if nc -z "$APP_HOST" "$APP_PORT" 2>/dev/null; then
        echo "[$(date)] ✓ App is reachable at $APP_HOST:$APP_PORT"
        # Wait additional time for FastAPI to be fully ready after port opens
        sleep 3
        break
    fi
    ATTEMPTS=$((ATTEMPTS + 1))
    echo "[$(date)] Attempt $ATTEMPTS/$MAX_ATTEMPTS: Waiting for $APP_HOST:$APP_PORT..."
    sleep $WAIT_INTERVAL
done

if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
    echo "[$(date)] ✗ Timeout waiting for app to be reachable"
    exit 1
fi

# Start Tailscale using the official containerboot entrypoint which properly handles TS_SERVE_CONFIG
echo "[$(date)] Launching Tailscale containerboot..."
exec /usr/local/bin/containerboot

