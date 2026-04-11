"""
Plex client discovery and playback dispatcher.
Phase 3 Stub implementation.
"""

def get_clients():
    return [
        {"name": "Web Client", "identifier": "web-1", "product": "Plex Web", "address": "127.0.0.1"},
        {"name": "Shield TV", "identifier": "shield-1", "product": "Plex for Android", "address": "192.168.1.10"}
    ]

def dispatch_playback(tracks, client_name):
    return {"status": "playing", "client": client_name}
