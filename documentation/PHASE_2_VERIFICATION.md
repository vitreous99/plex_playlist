# Phase 2 — Verification Checklist

**Status:** ✅ Complete  
**Date Completed:** 2026-04-10

---

## Step-by-Step Verification

| Step | Description | Status | Notes |
|------|-------------|--------|-------|
| 2.1 | Plex server connection utility | ✅ | `plex_client.py` — singleton with try/except |
| 2.2 | Metadata sync module | ✅ | `sync.py` — upserts via ON CONFLICT, batched commits |
| 2.3 | Sync FastAPI endpoints | ✅ | `POST /api/sync` (202), `GET /api/sync/status` |
| 2.4 | SQLite query helpers | ✅ | `library_search.py` — 4 parameterised query functions |
| 2.5 | Pydantic LLM I/O models | ✅ | `schemas.py` — SuggestedTrack, PlaylistResponse, PromptRequest, SyncStatus |
| 2.6 | Prompt processor | ✅ | `prompt_processor.py` — NLP, context pool, system prompt builder |
| 2.7 | Ollama API integration | ✅ | `ollama_client.py` — AsyncClient with structured JSON format |
| 2.8 | Retry & over-request logic | ✅ | Max 3 attempts; JSON parse retry; under-count re-prompt |
| 2.9 | `POST /api/suggest` endpoint | ✅ | 503 on Ollama down; 404 on empty; 422 on validation error |
| 2.10 | Integration tests | ✅ | **99 tests, 99 passed** |

---

## Test Results

```
$ cd backend && pytest tests/ -v
 collected 99 items
 99 passed in 1.16s
```

---

## Files Created

### Service Layer
- `backend/app/services/plex_client.py` — Plex singleton, get_server(), get_music_section()
- `backend/app/services/sync.py` — run_sync(), get_sync_status(), upsert loop
- `backend/app/services/library_search.py` — search_tracks_by_keywords(), get_distinct_artists(), get_distinct_genres(), get_tracks_by_artist()
- `backend/app/services/prompt_processor.py` — extract_keywords(), build_context_pool(), build_system_prompt(), build_prompt()
- `backend/app/services/ollama_client.py` — generate_playlist(), _deduplicate_tracks(), OllamaError, retry logic

### Schemas
- `backend/app/models/schemas.py` — SuggestedTrack, PlaylistResponse, PromptRequest, SyncStatus

### API Routers
- `backend/app/api/__init__.py`
- `backend/app/api/sync.py` — POST /api/sync, GET /api/sync/status
- `backend/app/api/suggest.py` — POST /api/suggest

### Tests (76 new, 23 pre-existing)
- `tests/test_plex_client.py` (7), `test_sync.py` (9), `test_library_search.py` (14)
- `tests/test_prompt_processor.py` (14), `test_ollama_client.py` (10)
- `tests/test_schemas.py` (10), `test_api_sync.py` (5), `test_api_suggest.py` (7)

---

## Architecture Decisions

- **Singleton pattern** for Plex server — avoids re-auth on each request; reset_server() for testing.
- **grandparentTitle/parentTitle** — avoids N+1 HTTP calls during sync vs calling track.artist().
- **Raw SQL upsert** (INSERT OR REPLACE ON CONFLICT) — most efficient SQLite upsert strategy.
- **Batch commits every 100 rows** — balances memory and throughput.
- **Module-level _sync_state** — shared across requests; safe for single-process Docker deployment.
- **ORM expressions** for library search — all parameterised, no raw string SQL.
- **Stopword list with music-domain words** — avoids LLM prompt noise ("songs", "playlist", etc.).
- **Context cap of 40 items** — prevents context window overflow for small models.
- **ollama.AsyncClient** — non-blocking Ollama calls in FastAPI async context.
- **format=schema** — Ollama structured output guarantees valid PlaylistResponse JSON.
- **Deduplication** — case-insensitive (title, artist) keying across retry accumulation.

---

## API Endpoints

| Method | Path | Response |
|--------|------|----------|
| `POST` | `/api/sync` | 202 + status JSON |
| `GET` | `/api/sync/status` | SyncStatus JSON |
| `POST` | `/api/suggest` | PlaylistResponse JSON |

---

## How to Run Tests

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=. .venv/bin/pytest tests/ -v
```
