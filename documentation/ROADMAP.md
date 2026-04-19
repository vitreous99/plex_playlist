# Plex Playlist — Project Roadmap

> **Intelligent Semantic Music Orchestrator**
> A Dockerized middleware that enables natural-language playlist generation for a local Plex Music library, using Ollama for LLM inference and Plex's "Super Sonic" neural analysis.

---

## How to Read This Document

This roadmap is divided into **4 sequential phases**. Each phase contains **numbered steps**. Every step is written so it can be directly converted into a backlog item (task/ticket) with a clear definition of done. Steps within a phase should generally be completed in order, but steps marked *(parallel-safe)* can be worked on concurrently with their neighbors.

---

## Dependency Map (Phase → Phase)

```
Phase 1 (Infrastructure)
    └──▶ Phase 2 (Core Backend: Data + LLM)
              └──▶ Phase 3 (Sonic Fulfillment + Playback)
                        └──▶ Phase 4 (Frontend + Polish)
```

Phases are strictly sequential — each phase depends on the deliverables of the previous one.

---

## Quick Reference: Tech Stack

| Component | Technology | Version / Note |
|-----------|-----------|----------------|
| Backend | Python + FastAPI | 3.11+ |
| Media Interface | python-plexapi | Latest |
| LLM Inference | Ollama (REST API) | Service in Docker |
| Structured Output | Pydantic v2 | JSON schema enforcement |
| Data Layer | SQLite + SQLAlchemy | aiosqlite for async |
| Orchestration | Docker Compose | GPU passthrough |
| Frontend | HTML/JS (lightweight) | Served via nginx or FastAPI StaticFiles |
