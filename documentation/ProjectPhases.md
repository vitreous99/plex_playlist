# Project Phases

## Project Structure and Dependencies

The project should follow a standard containerized Python structure.

- **backend/**: FastAPI application using python-plexapi, ollama-python, and SQLAlchemy.
- **frontend/**: A lightweight React or simple HTML/JS interface for prompt entry.
- **db/**: A persistent volume for the SQLite metadata cache.
- **docker-compose.yml**: Orchestration of the backend, frontend, and Ollama services.

## Core Implementation Logic for Cline

Cline should be instructed to implement the following core logic modules:

- **Metadata Sync Module**: A background task that iterates through the Plex library (type=track), collects ratingKey, title, artist, album, genre, and style, and stores them in SQLite.
- **Prompt Processor**: A function that takes the user's string, retrieves a relevant "pool" of tracks from SQLite based on keywords, and constructs the Ollama prompt with the injected context.
- **Sonic Refinement Engine**: A module that takes the LLM's initial suggestions, finds them in the library, and optionally calls sonicallySimilar() to fill the playlist to the requested length.
- **Client Dispatcher**: A service that lists available PlexClients, allows the user to select one, and issues the playMedia command with a newly created PlayQueue.

## Environment Configuration

The application requires a set of environment variables to be passed into the Docker containers to facilitate connection.

| Variable Name | Description | Source |
|---|---|---|
| PLEX_URL | The base URL of the Plex Media Server | `http://<your-ip>:32400` |
| PLEX_TOKEN | The X-Plex-Token for authentication | Found in Plex Web settings or via network trace |
| OLLAMA_BASE_URL | The address of the Ollama service | `http://ollama:11434` (Internal Docker) |
| DEFAULT_MODEL | The LLM model to use | e.g., llama3.2:3b or qwen2.5 |
| CLIENT_NAME | The default playback client title | e.g., Shield TV or iPhone Plexamp |