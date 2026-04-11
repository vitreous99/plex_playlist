# Phase 3 — Verification Checklist

This document provides step-by-step verification that all Phase 3 deliverables are functional.

---

## Step-by-Step Verification

| Step | Description | Status | Notes |
|------|-------------|--------|-------|
| 3.1 | Track Matcher | ⬜ | `track_matcher.py` — fuzzy matching LLM suggestions to real Plex tracks |
| 3.2 | Sonic Similarity expansion | ⬜ | `sonic_engine.py` — expanding seeds to related tracks |
| 3.3 | Sonic Adventure | ⬜ | `sonic_engine.py` — acoustic path generation |
| 3.4 | Playlist Assembly pipeline | ⬜ | `playlist_builder.py` — full orchestration |
| 3.5 | Client Discovery | ⬜ | `client_dispatcher.py` — `GET /api/clients` |
| 3.6 | PlayQueue dispatch | ⬜ | `client_dispatcher.py` — push to target device |
| 3.7 | `POST /api/playlist/play` | ⬜ | End-to-end play endpoint |
| 3.8 | `POST /api/playlist/save` | ⬜ | Save permanent playlist in Plex |
| 3.9 | Error handling & diagnostics | ⬜ | Resilient errors & `GET /api/diagnostics` |

---

## Unit Tests to Verify Scope

- `tests/test_track_matcher.py`: Validates fuzzy matching logic, successful matches, and unmatched logs.
- `tests/test_sonic_engine.py`: Validates `sonicallySimilar` and `sonicAdventure` calls, deduplication, and limits.
- `tests/test_playlist_builder.py`: Validates orchestration of prompt -> suggestions -> matcher -> sonic expansion.
- `tests/test_client_dispatcher.py`: Validates client discovery and PlayQueue creation/dispatch.
- `tests/test_api_playlist.py`: Validates endpoints `/api/clients`, `/api/playlist/play`, `/api/playlist/save`, and `/api/diagnostics`.
