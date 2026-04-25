# NVIDIA Shield Keep-Alive Setup

## Overview
Your Plex Playlist backend now includes an automatic keep-alive mechanism that prevents your NVIDIA Shield from sleeping during music playback. When you send a playlist to play on your Shield, the system will automatically send keep-alive pings every 10 minutes for 90 minutes to keep it awake.

## How It Works
1. User initiates playback via `/api/playlist/play`
2. Playlist is generated and dispatched to the Shield client
3. A background task automatically starts on the backend
4. The task sends ADB commands to the Shield every 10 minutes
5. Shield receives HOME key events (non-intrusive, doesn't interrupt music)
6. Device stays awake for the entire 90-minute session

## Configuration

Add these environment variables to your `.env` file or Docker environment:

```env
# Enable/disable keep-alive (default: true)
KEEP_ALIVE_ENABLED=true

# Total time to keep device awake (default: 90 minutes)
KEEP_ALIVE_DURATION_MINUTES=90

# Interval between keep-alive pings (default: 10 minutes)
KEEP_ALIVE_INTERVAL_MINUTES=10

# Optional: Shield IP address (if not using default ADB bridge setup)
SHIELD_IP=192.168.1.100
```

## Quick Start

### For Docker Compose Users
Update your `.env` file:
```env
KEEP_ALIVE_ENABLED=true
KEEP_ALIVE_DURATION_MINUTES=90
KEEP_ALIVE_INTERVAL_MINUTES=10
SHIELD_IP=
```

Then rebuild and restart:
```bash
docker compose down
docker compose build
docker compose up -d
```

### Customization Examples

**Keep device awake for 2 hours instead of 90 minutes:**
```env
KEEP_ALIVE_DURATION_MINUTES=120
```

**Ping more frequently (every 5 minutes):**
```env
KEEP_ALIVE_INTERVAL_MINUTES=5
```

**Disable keep-alive completely:**
```env
KEEP_ALIVE_ENABLED=false
```

**Different Shield IP:**
```env
SHIELD_IP=192.168.1.50
```

## Implementation Details

### New Components
- **Backend Service**: `/backend/app/services/keep_alive.py` - Handles periodic pings
- **ADB Bridge Endpoint**: POST `/ping` on ADB bridge - Sends keep-alive commands via ADB
- **Configuration**: New settings in `app/config.py` for keep-alive tuning
- **Async Playback**: `dispatch_playback_async()` starts keep-alive task automatically

### API Changes
- `/api/playlist/play` now triggers keep-alive automatically
- Backward compatible with existing code
- Error-tolerant (playback succeeds even if keep-alive fails to start)

## Monitoring

Check the backend logs to see keep-alive activity:
```
docker logs plex-playlist-app | grep "keep-alive"
```

Example log output:
```
2026-04-21 12:00:00 | INFO | [abc123de] | app.services.keep_alive | Keep-alive task started
2026-04-21 12:00:00 | DEBUG | [abc123de] | app.services.keep_alive | Keep-alive: next ping in 10 minutes
2026-04-21 12:10:00 | DEBUG | [abc123de] | app.services.keep_alive | Keep-alive ping sent successfully
```

## Troubleshooting

### Keep-alive not working?
1. Ensure `KEEP_ALIVE_ENABLED=true` in your `.env`
2. Check that ADB bridge is running: `docker logs plex-playlist-adb-bridge`
3. Verify Shield IP is correct or in default config
4. Check backend logs: `docker logs plex-playlist-app`

### ADB bridge endpoint errors?
- Check Shield is on the same network
- Verify Shield IP with `adb devices` on your host
- Ensure ADB port 5555 is open on Shield

### Music stops after playback starts?
- If keep-alive fails, playback continues normally
- Check that your music tracks are fully cached in Plex
- Verify Plex client (Plexamp) is properly configured

## Optional: Manual Keep-Alive Testing

To manually test the keep-alive mechanism:
```bash
# Send a manual ping to Shield
curl -X POST http://127.0.0.1:9001/ping

# Expected response:
# {"status":"pong","message":"Keep-alive ping sent successfully","timestamp":"2026-04-21T12:00:00..."}
```

## Notes
- Keep-alive runs as a background task and doesn't block playback dispatch
- Multiple playlists in succession will restart the keep-alive timer
- Pings are sent at intervals regardless of user activity
- The HOME key event is non-intrusive and won't interrupt audio playback
