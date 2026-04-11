# Plex Playlist

> **Intelligent Semantic Music Orchestrator** — A Dockerized middleware that
> enables natural-language playlist generation for a local Plex Music library,
> using Ollama for LLM inference and Plex's "Super Sonic" neural analysis.

## Project Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Infrastructure & Scaffolding | ✅ Complete |
| 2 | Core Backend (Data & LLM) | ✅ Complete |
| 3 | Sonic Fulfillment & Playback | 🔲 Planned |
| 4 | Frontend & Polish | 🔲 Planned |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) (for Ollama GPU inference)
- A Plex Media Server with a Music library
- A [Plex authentication token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/vitreous99/plex_playlist.git
cd plex_playlist

# 2. Configure environment
cp .env.example .env
# Edit .env with your Plex URL, token, and preferences

# 3. Start the stack
docker compose up --build -d

# 4. Verify
curl http://localhost:8000/health
# → {"status":"ok","timestamp":"...","version":"0.1.0"}
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| `app` | 8000 | FastAPI backend |
| `ollama` | 11434 | LLM inference engine (GPU) |
| `frontend` | 3000 | Web UI (nginx) |

### Phase 2 API Endpoints

```bash
# Sync library metadata from Plex to local SQLite cache
curl -X POST http://localhost:8000/api/sync

# Check sync progress
curl http://localhost:8000/api/sync/status
# → {"synced_tracks": 1234, "total_tracks": 1234, "last_synced_at": "...", "in_progress": false}

# Generate a playlist from natural language
curl -X POST http://localhost:8000/api/suggest \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "upbeat 90s rock for a morning run", "track_count": 20}'
# → {"name": "...", "description": "...", "tracks": [...]}
```

## Project Structure

```
plex_playlist/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI application entry point
│   │   ├── config.py            # Environment-based configuration
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── database.py      # SQLAlchemy engine & session
│   │   │   └── tables.py        # ORM table definitions
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── sync.py          # POST /api/sync, GET /api/sync/status
│   │   │   └── suggest.py       # POST /api/suggest
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── plex_client.py   # Plex server connection utility
│   │       ├── sync.py          # Library metadata sync
│   │       ├── library_search.py# SQLite query helpers
│   │       ├── prompt_processor.py # NLP + LLM prompt builder
│   │       └── ollama_client.py # Ollama API integration + retry
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py          # Shared fixtures (in-memory DB, test client)
│   │   ├── test_config.py
│   │   ├── test_database.py
│   │   ├── test_health.py
│   │   ├── test_plex_client.py
│   │   ├── test_sync.py
│   │   ├── test_library_search.py
│   │   ├── test_schemas.py
│   │   ├── test_prompt_processor.py
│   │   ├── test_ollama_client.py
│   │   ├── test_api_sync.py
│   │   └── test_api_suggest.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/
│   └── index.html               # Placeholder (Phase 4)
├── db/                           # SQLite volume mount point
├── documentation/
│   ├── ROADMAP.md
│   ├── PHASE_1_INFRASTRUCTURE.md
│   ├── PHASE_1_VERIFICATION.md
│   ├── PHASE_2_CORE_BACKEND.md
│   ├── PHASE_2_VERIFICATION.md
│   ├── PHASE_3_SONIC_PLAYBACK.md
│   └── PHASE_4_FRONTEND_POLISH.md
├── docker-compose.yml
├── .env.example
└── .gitignore
```

## Development

### Running Tests

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

### API Documentation

Once running, interactive API docs are available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11+ / FastAPI |
| Media Interface | python-plexapi |
| LLM Inference | Ollama (Docker, GPU) |
| Structured Output | Pydantic v2 |
| Data Layer | SQLite + SQLAlchemy (async) |
| Orchestration | Docker Compose |
| Frontend | HTML/JS via nginx |

## License

Private — see repository settings.
