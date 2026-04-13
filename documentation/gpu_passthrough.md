# GPU Passthrough

The application must be configured to pass the host GPU to the Ollama container. For NVIDIA hardware, install and configure the `nvidia-container-toolkit` on the host and ensure drivers are current.

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