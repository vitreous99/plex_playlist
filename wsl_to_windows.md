Architecture & Networking Guide
The Core Problem: WSL Mirrored Networking vs. Docker
This project runs inside Docker on WSL2 using Mirrored Networking.
Under mirrored networking, WSL shares the exact same IP address and localhost as the Windows host machine. However, standard Docker Bridge networks (the 172.x.x.x IPs) cannot route traffic back out to the Windows host IP.

If a Docker container tries to reach the Windows machine via its physical LAN IP (e.g., 192.168.1.2), Windows will immediately drop the packet, resulting in a Connection refused error.

The Solution: Host Mode & The Magic Bridge
To allow the Dockerized app to talk to native Windows services (like Plex Media Server) and other host-bound tools (like Ollama), we use two specific bypasses:

Host Mode (network_mode: "host"): The backend app drops its isolated Docker bridge and runs directly on the WSL network stack. Because WSL mirrors Windows, Container Localhost = WSL Localhost = Windows Localhost.

The Magic Bridge (host.docker.internal): Containers that must stay on a bridge network (like Nginx) use Docker's built-in DNS gateway to reach the host-mode app.

⚙️ Critical Configurations
1. docker-compose.yml
The architecture relies on specific network assignments to prevent port clashing and routing black holes.

Backend App: Must use network_mode: "host". It does not use port mappings (ports:) because it is bound directly to the host.

ADB Bridge: Mapped to "9001:9000" to prevent port collisions with other host services (e.g., Portainer, which natively uses 9000).

Nginx Frontend: Runs on the default internal bridge, but is granted access to the host network via extra_hosts.

YAML
# Snippet of critical compose settings
services:
  app:
    # Binds app directly to host loopback to reach Plex/Ollama
    network_mode: "host" 
    
  frontend:
    networks:
      - internal
    extra_hosts:
      # Allows Nginx to bridge out and talk to the host-mode app
      - "host.docker.internal:host-gateway"

  adb-bridge:
    ports:
      # Maps to 9001 on the host to avoid clashing with Portainer on 9000
      - "9001:9000"
2. Nginx Routing (nginx.conf)
Because the backend app is running on the host network, Nginx cannot route to it using its Docker container name. Nginx must route traffic across the magic gateway to the host.

Nginx
location /api/ {
    # CRITICAL: Routes traffic across the bridge to the app running on the host network
    proxy_pass http://host.docker.internal:8000/api/; 
}
3. Environment Variables (.env)
The backend app expects all host-level services to live on 127.0.0.1. Do not use physical LAN IPs (like 192.168.1.x).

Ini, TOML
# Look for Plex on the shared loopback
PLEX_URL=http://127.0.0.1:32400

# Look for Ollama on the shared loopback
OLLAMA_URL=http://127.0.0.1:11434

# Look for the ADB Bridge on the shifted host port
ADB_BRIDGE_URL=http://127.0.0.1:9001
4. Zero-Dependency Docker Healthchecks
To prevent containers from being marked as unhealthy due to missing external libraries (like httpx), healthchecks use Python's built-in urllib.

Dockerfile
# Example from adb-bridge Dockerfile
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health', timeout=5)" || exit 1
🛠️ Troubleshooting & Diagnostics
If the connection breaks in the future, follow these steps in order to isolate the network failure.

1. Is the service listening on Windows?
Run this in Windows PowerShell to ensure the service (e.g., Plex) is awake and listening on all adapters (0.0.0.0):

PowerShell
netstat -aon | Select-String ":32400"
2. Can Windows reach the service?
Run this in Windows PowerShell. If this fails, the server is down or the IP is wrong.

PowerShell
curl.exe -m 5 -v http://127.0.0.1:32400
3. Is the WSL Mirror active?
Run this in a standard WSL terminal. If this fails but step 2 works, WSL Mirrored Networking has crashed (restart WSL).

Bash
curl -m 5 -v http://127.0.0.1:32400
4. Is Docker properly dropping its bridge?
Run this inside WSL. It spins up a temporary container on the host network. If this connects, your compose file is misconfigured. If this gets Connection refused, Docker desktop networking is hung.

Bash
docker run --rm --network host --entrypoint "" alpine curl -m 5 -v http://127.0.0.1: