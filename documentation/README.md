# plex_playlist
This markdown document is designed to be shared with Cline as a project brief. It contains the technical requirements, architectural patterns, and code implementation logic derived from the research.

***

# Project Brief: Intelligent Semantic Music Orchestrator

## Overview
Build a Dockerized middleware application that enables natural language playlist generation for a local Plex Music library. The system will leverage Ollama for local LLM inference and utilize Plex's "Super Sonic" neural analysis to create sonically cohesive playlists, which are then pushed to remote clients (Plexamp or Nvidia Shield).

## Tech Stack
*   **Backend:** Python 3.11+ (FastAPI).
*   **Media Interface:** `python-plexapi`.
*   **LLM Inference:** Ollama (Service-to-service via Docker).
*   **Data Layer:** SQLite (for metadata caching).
*   **Orchestration:** Docker Compose (GPU-passthrough for Ollama).

## Core Architecture & Workflow

### 1. Metadata Synchronization & Caching
To ensure "library-awareness" and prevent LLM hallucinations, the app must maintain a local SQLite cache of the user's Plex library.[1, 2]
*   **Task:** Implement a background sync that fetches all tracks from the music library.
*   **Stored Fields:** `ratingKey`, `title`, `artist`, `album`, `genre`, `style`, and `hasSonicAnalysis` status.[3, 4]
*   **Rationale:** Querying the Plex API for every semantic match is too slow; local SQL allows millisecond filtering.[2]

### 2. Semantic Interpretation (Ollama + Pydantic)
Translate user prompts into structured track requirements.
*   **Integration:** Connect to Ollama via its REST API (inside Docker: `http://ollama:11434`).[5, 6]
*   **Structured Output:** Use Pydantic models to force the LLM to return valid JSON.[7, 8]
*   **Prompting Strategy:** Provide the LLM with a "seed" list of artists or genres from the SQLite cache to ground its suggestions.[2, 9]
*   **Temperature:** Set to $0$ for deterministic, rigid adherence to the JSON schema.[7, 8]

### 3. Sonic Fulfillment (Super Sonic API)
Refine the LLM's suggested track list using Plex's neural analysis features.[10, 11]
*   **Sonic Similarity:** Use `sonicallySimilar(limit=50, maxDistance=0.25)` to expand the playlist based on acoustic properties.[12, 3]
*   **Sonic Adventure:** For transition prompts (e.g., "Start with Folk, end with Metal"), use `sonicAdventure(to=target_track)` to find an acoustic path through the library.[12]
*   **Matching Logic:** Match LLM-suggested track titles against the local cache first, then verify the artist using the `python-plexapi` object to bypass unreliable text search.[9]

### 4. Remote Playback Orchestration
Push the final sequence to a hardware client.
*   **Client Discovery:** Use `plex.clients()` to find available devices like "Shield TV" or "Plexamp".[12, 13]
*   **PlayQueue Creation:** Use `PlayQueue.create(server, items=tracks)` to generate a transient playback sequence rather than a permanent playlist.[13]
*   **Execution:** Call `client.playMedia(playqueue)` to trigger instant playback on the target device.

## Key Technical Specifications for Implementation

### Docker Compose Structure
The setup requires an isolated network where the app can talk to Ollama via service name.
```yaml
services:
  app:
    build:./backend
    environment:
      - PLEX_URL=${PLEX_URL}
      - PLEX_TOKEN=${PLEX_TOKEN}
      - OLLAMA_HOST=http://ollama:11434
    networks:
      - internal
  ollama:
    image: ollama/ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    networks:
      - internal
```

### Environment Variables Required
*   `PLEX_URL`: Local IP and port (usually `http://<IP>:32400`).
*   `PLEX_TOKEN`: The X-Plex-Token for authentication.[14, 15]
*   `OLLAMA_MODEL`: Target model (e.g., `llama3.2:3b` or `qwen2.5`).[16, 17]
*   `TARGET_CLIENT_NAME`: Name of the device for playback (e.g., "Shield TV").

## Implementation Pitfalls to Handle
*   **Nvidia Shield Power:** Ensure "Stay Awake" is enabled in developer options or USB ports are set to "Always On" to prevent the client from disappearing when idle.[18]
*   **Client Presence:** If a client is not found, use `client.proxyThroughServer()` to force communication through the main Plex server.[17]
*   **Structured Output Failures:** Implement a retry loop; if the LLM provides fewer tracks than requested, adjust the prompt to ask for 50% more to ensure a full playlist after filtering.[9]