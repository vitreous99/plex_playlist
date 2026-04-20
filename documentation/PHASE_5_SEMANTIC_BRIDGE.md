# Phase 5 — The Semantic Bridge: LLM Seed Selector + Local Vector Index

## Overview

The current pipeline is **semantic → string-match → sonic**:

1. Gemma extracts smart search terms from the user prompt.
2. Those terms query the SQLite cache (string/LIKE matching).
3. Matched tracks are passed to Plex's `sonicallySimilar` / `sonicAdventure` for expansion.

The weakness is Step 2: string matching hallucinates or misses tracks whose metadata words don't literally appear in the user prompt ("Sunday afternoon vibe" won't hit any genre column). The Semantic Bridge replaces Step 2 with a **local vector index** so that meaning, not text overlap, drives the context fetch.

### Why Seed Selector over LLM as Judge

An "LLM as Judge" workflow retrieves 100 candidate tracks then asks Gemma to discard 80. On an RTX 3060 / 12 GB VRAM running Gemma via Ollama this hits two walls:

| Problem | Impact |
|---|---|
| Context window latency | 100 tracks of metadata → 15–30 s extra per request |
| Small-LLM context bias | Gemma favours items at the start/end of long prompts → repetitive playlists |

The Seed Selector keeps Gemma's workload tiny (output 2–3 IDs) and delegates compute-heavy similarity to Plex and the local vector index.

---

## Proposed Pipeline (4 Steps)

\`\`\`
User Prompt
    │
    ▼
[Step 1] Intent Parsing (Gemma – fast, structured)
    │  Output: { mood, tempo, genre_hint, exclude[] }
    ▼
[Step 2] Vector Fetch (FAISS local index – sub-millisecond)
    │  Output: top-40 candidate tracks (real rating_keys from your library)
    ▼
[Step 3] Seed Selection (Gemma – tiny context, fast)
    │  Output: 2–3 rating_keys chosen as sonic seeds
    ▼
[Step 4] Plex Sonic Handoff (sonicallySimilar / sonicAdventure)
         Output: full playlist expanded by Plex neural analysis
\`\`\`

---

## Step-by-Step Implementation Plan

### Phase 5.0 — Preprocessing: Build the Vector Index (one-time, re-runs after sync)

**Goal:** embed every track in the SQLite cache into a FAISS flat index so semantic search is possible without an LLM call.

**What to build:** `backend/app/services/vector_index.py`

- Load all `Track` rows from SQLite (synchronous SQLAlchemy session, called from the background sync task).
- For each track build a plain-English description string, e.g.:
  `"Artist: Pink Floyd | Album: The Wall | Genre: Progressive Rock | Mood: melancholic, atmospheric"`
- Embed using `sentence-transformers` model `all-MiniLM-L6-v2` (22 MB, runs on CPU or 3060 GPU).
- Store float32 vectors in a FAISS `IndexFlatIP` (inner-product / cosine similarity).
- Persist index and rating_key lookup to disk:
  - `db/vector_index.faiss`
  - `db/vector_index_keys.json`
- Expose two public functions:
  - `build_vector_index(db_url: str) -> None`
  - `search_vector_index(query: str, top_k: int = 40) -> list[int]` — returns rating_keys

**When to run:** call `build_vector_index()` at the end of `run_sync()` in `backend/app/services/sync.py` after the final `session.commit()`.

**New dependencies** (add to `backend/requirements.txt`):
\`\`\`
sentence-transformers>=3.0,<4.0
faiss-cpu>=1.8,<2.0          # swap to faiss-gpu if CUDA runtime is confirmed
\`\`\`

**Relevant existing files:**
- `backend/app/services/sync.py` — wire `build_vector_index()` after final commit
- `backend/app/models/tables.py` — `Track` already has `title`, `artist`, `album`, `genre`, `style`, `rating_key`

---

### Phase 5.1 — Step 1: Intent Parsing (replace `build_term_extraction_prompt`)

**Goal:** replace comma-separated keyword extraction with a structured JSON intent object.

**What to change:** `backend/app/services/prompt_processor.py`

- Replace `_TERM_EXTRACTOR_PROMPT` with a template instructing Gemma to return:
  \`\`\`json
  { "mood": "relaxed", "tempo": "slow", "genre_hint": "jazz", "exclude": ["christmas"] }
  \`\`\`
- Add `parse_intent(user_prompt: str) -> PlaylistIntent` (async, calls Ollama with `format=PlaylistIntent.model_json_schema()`).
- Assemble the vector query string from intent fields: `f"{mood} {tempo} {genre_hint}"`.

**New Pydantic model** to add to `backend/app/models/schemas.py`:
\`\`\`python
class PlaylistIntent(BaseModel):
    mood: str
    tempo: str
    genre_hint: str = ""
    exclude: list[str] = []
\`\`\`

---

### Phase 5.2 — Step 2: Vector Fetch (replace `build_context_pool` string matching)

**Goal:** use FAISS semantic search instead of SQL LIKE-query keyword matching.

**What to change:** `backend/app/services/prompt_processor.py` — `build_context_pool()`

- Replace `search_tracks_by_keywords` + LIKE filtering with `search_vector_index(intent_query, top_k=40)`.
- Load full `Track` rows from SQLite using returned rating_keys (`SELECT ... WHERE rating_key IN (...)`).
- Derive artist/genre/sample_tracks lists from those rows — same output shape as existing `context_pool` dict; `build_system_prompt()` requires no changes.
- Keep the broad artist/genre fallback logic unchanged.

---

### Phase 5.3 — Step 3: Seed Selection (new Gemma micro-call)

**Goal:** ask Gemma to pick the 2–3 best sonic seeds from the real candidate tracks.

**What to build:** `select_seeds(intent: PlaylistIntent, candidates: list[Track]) -> list[Track]` in `backend/app/services/prompt_processor.py`

- Build a minimal prompt: list candidates as `{idx}. {title} — {artist} ({genre})` and ask *"Pick the 2 best seeds for this vibe. Return their list numbers as a JSON array."*
- Use `format=SeedSelection.model_json_schema()` for structured output.
- Map returned indices back to `Track` objects.

**New Pydantic model** to add to `backend/app/models/schemas.py`:
\`\`\`python
class SeedSelection(BaseModel):
    indices: list[int]   # 1-based positions in the candidate list
\`\`\`

**Caller:** `build_playlist_streamed()` in `backend/app/api/stream.py` — call `select_seeds()` after vector fetch; pass selected `DbTrack` objects directly to the sonic engine as seeds.

---

### Phase 5.4 — Step 4: Plex Sonic Handoff (no changes required)

`backend/app/services/sonic_engine.py` already accepts `DbTrack` seeds and calls `sonicallySimilar` / `sonicAdventure`. No modifications needed.

---

### Phase 5.5 — Wire Everything in `stream.py`

Update `build_playlist_streamed()` in `backend/app/api/stream.py`:

\`\`\`
[existing] prompt_start event
    │
[NEW]  parse_intent(prompt)              → PlaylistIntent    (emit: intent_parsed)
[NEW]  search_vector_index(intent_query) → rating_keys       (emit: vector_fetch)
[NEW]  load Track rows for rating_keys
[NEW]  select_seeds(intent, candidates)  → 2–3 DbTrack seeds (emit: seed_selected)
    │
[existing] build_system_prompt(context_pool, track_count)
[existing] generate_playlist(system_prompt, prompt, track_count)
[existing] match_tracks(...)
[existing] expand_with_sonic_similarity / build_sonic_adventure
\`\`\`

New SSE step names to emit (all `phase: "prompt"`):
- `intent_parsed` — include mood, tempo, genre_hint in detail
- `vector_fetch` — include candidate count and top-3 track titles in detail
- `seed_selected` — include selected track titles in detail

---

## Files to Create / Modify

| File | Action | Notes |
|---|---|---|
| `backend/app/services/vector_index.py` | **Create** | FAISS index build + search |
| `backend/app/services/prompt_processor.py` | **Modify** | Add `parse_intent`, `select_seeds`; swap `build_context_pool` to vector search |
| `backend/app/models/schemas.py` | **Modify** | Add `PlaylistIntent`, `SeedSelection` models |
| `backend/app/services/sync.py` | **Modify** | Call `build_vector_index()` after sync completes |
| `backend/app/api/stream.py` | **Modify** | Wire new steps, emit new SSE events |
| `backend/requirements.txt` | **Modify** | Add `sentence-transformers`, `faiss-cpu` |
| `backend/tests/test_vector_index.py` | **Create** | Unit tests for build and search |
| `backend/tests/test_prompt_processor.py` | **Modify** | Update tests for `parse_intent` / `select_seeds` |

---

## Verification

| # | Test | Pass Condition |
|---|---|---|
| 5.1 | `build_vector_index()` runs on a synced DB | `db/vector_index.faiss` + `db/vector_index_keys.json` exist with > 0 entries |
| 5.2 | `search_vector_index("relaxed jazz", top_k=5)` | Returns 5 rating_keys that all exist in the tracks table |
| 5.3 | `parse_intent("chill Sunday morning")` | Returns valid `PlaylistIntent`; `mood` and `tempo` populated; no holiday terms |
| 5.4 | `select_seeds(intent, candidates)` | Returns 2–3 `Track` objects drawn from the candidate list |
| 5.5 | Full end-to-end SSE generation | Activity feed shows `intent_parsed`, `vector_fetch`, `seed_selected` steps |
| 5.6 | Sonic expansion completes for selected seeds | Final playlist ≥ requested track count (or best-effort) |
| 5.7 | `pytest backend/tests/` | All existing tests remain green |

---

## Hardware Notes (RTX 3060 / 12 GB VRAM)

- `all-MiniLM-L6-v2` is 22 MB. Embedding speed: ~14,000 sentences/s on CPU, faster on 3060. A 50,000-track library re-indexes in under 5 seconds.
- FAISS `IndexFlatIP` for 50,000 × 384-dim vectors = ~75 MB RAM. No GPU required for search at this library scale.
- Swap `faiss-cpu` for `faiss-gpu` in `requirements.txt` to use 3060 VRAM for ANN search (minimal real-world benefit at < 100k tracks, but essentially free to enable).
- The two new Gemma micro-calls (intent parse + seed select) operate on < 200 tokens each — combined latency ~1–2 s, a net win vs. the current longer `generate_playlist` context.

---

## Deliberate Scope Exclusions

- No change to the Plex sync schedule or sync API endpoints.
- `sonicallySimilar` and `sonicAdventure` remain the expansion engine — not replaced.
- No persistent vector store (ChromaDB, Qdrant) — FAISS flat file is sufficient and avoids a new long-running service dependency.
- The existing `generate_playlist` LLM call is kept and now receives a better-anchored context pool. It also serves as a fallback if seed selection returns no results.

---

*Follows the naming and structure conventions established in Phase 1–4 documentation.*
