# Docker Optimization

## Network Topology and Docker Orchestration

The deployment of these services requires careful networking consideration to ensure the application can reach both the Ollama instance and the Plex Media Server, while also being able to discover playback clients on the local network.

### Bridge Networking vs. Host Networking

In a standard Docker Compose setup, bridge networking is the default. This provides isolation but can complicate client discovery.

- **Bridge Networking:** Best for service-to-service communication (e.g., the backend talking to Ollama). Containers can reach each other using their service names (for example, `http://ollama:11434`).
- **Host Networking:** Often necessary for the Plex server itself or the playlist application if it needs to use UDP multicast for GDM (G’day Mate) discovery of Plexamp clients. Host mode bypasses Docker NAT, allowing the container to see the host network interfaces directly.

## GPU Passthrough for Local Inference

The application must be configured to pass the host GPU to the Ollama container. For NVIDIA hardware, this requires the `nvidia-container-toolkit` on the host.

```yaml
# Essential Docker Compose snippet for GPU support
services:
  ollama:
    image: ollama/ollama
    volumes:
      - ./ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## Addressing CORS and Connection Issues

When running Ollama in a containerized environment, it is common to encounter connection errors. Set `OLLAMA_HOST` to `0.0.0.0:11434` to listen on all interfaces, and configure `OLLAMA_ORIGINS` if a browser-based UI will call the API directly to avoid Cross-Origin Resource Sharing (CORS) rejections.