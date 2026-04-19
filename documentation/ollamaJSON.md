Reliable automation depends on the LLM returning data in a format the code can parse without error. Ollama supports structured outputs through JSON schemas or Pydantic models. By specifying a schema in the request, the model is constrained to return a valid JSON object.

## Pydantic schema example

The recommended Pydantic schema for a playlist suggestion is shown below.

```python
from pydantic import BaseModel
from typing import List, Optional

class SuggestedTrack(BaseModel):
    title: str
    artist: str
    album: Optional[str] = None
    reasoning: str  # Explains why the track fits the prompt

class PlaylistResponse(BaseModel):
    name: str
    description: str
    tracks: List[SuggestedTrack]
```

When calling the Ollama API, set the `format` parameter to `PlaylistResponse.model_json_schema()` and set `temperature` to `0` to encourage deterministic adherence to the schema.

## Model selection and performance

Research indicates that different models excel at information extraction and structured output. While larger models are generally more capable, smaller models are often sufficient for library matching if given clear instructions.

- **Llama 3.2 (3B) / 3.1 (8B):** Strong adherence to JSON schemas and good general reasoning.
- **Qwen 2.5 (Coder or Instruct):** Exceptional performance in structured data extraction tasks.
- **Phi 4:** Fast inference on limited hardware; good for simple classifications.
- **Gemma 2 (9B):** Reliable but occasionally less consistent with rigid JSON formatting.

For a self-hosted environment, a 3B to 8B parameter model is often the sweet spot for balancing accuracy with the VRAM limits of consumer hardware.