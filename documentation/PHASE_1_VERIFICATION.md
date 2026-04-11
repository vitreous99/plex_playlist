# Phase 1 — Verification Checklist

This document provides step-by-step verification that all Phase 1 deliverables are functional.

---

## Prerequisites

1. Docker and Docker Compose installed
2. NVIDIA Container Toolkit installed (for GPU passthrough)
3. A valid `.env` file created from `.env.example`

---

## Verification Steps

### 1. Environment Setup

```bash
# Copy and configure environment variables
cp .env.example .env
# Edit .env with your Plex URL, token, etc.
```

### 2. Docker Compose Validation

```bash
# Validate the compose file syntax
docker compose config
```

**Expected:** YAML output of the resolved configuration with no errors.

### 3. Build and Start the Stack

```bash
# Build and start all services
docker compose up --build -d
```

**Expected:** All three containers start: `plex-playlist-app`, `plex-playlist-ollama`, `plex-playlist-frontend`.

### 4. Verify Backend Health

```bash
# Check the FastAPI health endpoint
curl http://localhost:8000/health
```

**Expected:** `{"status":"ok","timestamp":"...","version":"0.1.0"}`

### 5. Verify Ollama Connectivity (from app container)

```bash
# Test that the app container can reach Ollama
docker exec plex-playlist-app python -c "
import urllib.request, json
resp = urllib.request.urlopen('http://ollama:11434/api/tags')
print(json.loads(resp.read()))
"
```

**Expected:** JSON response with a `models` key (list may be empty if no models pulled yet).

### 6. Verify GPU Passthrough

```bash
# Check nvidia-smi inside the Ollama container
docker exec plex-playlist-ollama nvidia-smi
```

**Expected:** GPU information table showing the NVIDIA GPU.

### 7. Verify Frontend

```bash
# Check that the frontend is served
curl -s http://localhost:3000 | head -5
```

**Expected:** HTML content of the placeholder page.

### 8. Verify Database Creation

```bash
# Check that the SQLite database was created
docker exec plex-playlist-app python -c "
import sqlite3
conn = sqlite3.connect('db/library_cache.db')
cursor = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
print([row[0] for row in cursor.fetchall()])
conn.close()
"
```

**Expected:** `['tracks']`

### 9. Run Unit Tests

```bash
# From the backend directory (or inside the container)
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

**Expected:** All tests pass.

### 10. Cleanup

```bash
docker compose down
```

---

## Summary

| Check | Service | Expected Result |
|-------|---------|-----------------|
| Health endpoint | app | 200 OK, `{"status": "ok"}` |
| Ollama reachable | ollama (from app) | JSON response from `/api/tags` |
| GPU visible | ollama | `nvidia-smi` shows GPU |
| Frontend serves | frontend | HTML page on port 3000 |
| Database created | app | `tracks` table exists |
| Unit tests | local/CI | All tests green |
