# Data Models

## Python Data Classes

### PromptRecord

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
import json

@dataclass
class PromptRecord:
    """Represents a prompt record from the database"""
    id: int
    prompt_text: str
    prompt_type: str
    status: str
    artifact_status: str
    output_reference: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]

    # Joined data from writings table
    json_content: Optional[str] = None
    writing_id: Optional[int] = None

    @property
    def is_pending(self) -> bool:
        """Check if prompt is pending media generation"""
        return (self.status == 'completed' and
                self.artifact_status == 'pending' and
                self.json_content is not None)

    def get_json_prompt(self) -> Dict[str, Any]:
        """Parse JSON content"""
        if not self.json_content:
            return {}
        try:
            return json.loads(self.json_content)
        except json.JSONDecodeError:
            return {}
```

### ImagePromptData

```python
@dataclass
class ImagePromptData:
    """Parsed image prompt JSON structure"""
    prompt: str
    negative_prompt: str
    style_tags: list[str]
    aspect_ratio: str
    quality: str
    mood: str
    subject: str
    background: str
    lighting: str

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'ImagePromptData':
        tech = data.get('technical_params', {})
        comp = data.get('composition', {})
        return cls(
            prompt=data.get('prompt', ''),
            negative_prompt=data.get('negative_prompt', ''),
            style_tags=data.get('style_tags', []),
            aspect_ratio=tech.get('aspect_ratio', '16:9'),
            quality=tech.get('quality', 'high'),
            mood=tech.get('mood', ''),
            subject=comp.get('subject', ''),
            background=comp.get('background', ''),
            lighting=comp.get('lighting', '')
        )
```

**Example JSON:**
```json
{
  "prompt": "A serene mountain lake at dawn, with soft golden light...",
  "negative_prompt": "Crowds, bright sunlight, harsh shadows",
  "style_tags": ["realism", "impressionism", "serenity"],
  "technical_params": {
    "aspect_ratio": "16:9",
    "quality": "high",
    "mood": "tranquil and awe-inspiring"
  },
  "composition": {
    "subject": "Mirror-like lake surface reflecting dawn sky",
    "background": "Misty mountain range with silhouetted pines",
    "lighting": "Soft golden-hour light with directional mist highlights"
  }
}
```

### LyricsPromptData

```python
@dataclass
class LyricsPromptData:
    """Parsed lyrics prompt JSON structure"""
    title: str
    genre: str
    mood: str
    tempo: str
    structure: list[Dict[str, Any]]
    key: str
    time_signature: str
    vocal_style: str
    instrumentation: list[str]

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'LyricsPromptData':
        meta = data.get('metadata', {})
        return cls(
            title=data.get('title', ''),
            genre=data.get('genre', ''),
            mood=data.get('mood', ''),
            tempo=data.get('tempo', ''),
            structure=data.get('structure', []),
            key=meta.get('key', ''),
            time_signature=meta.get('time_signature', '4/4'),
            vocal_style=meta.get('vocal_style', ''),
            instrumentation=meta.get('instrumentation', [])
        )

    def get_full_lyrics(self) -> str:
        """Combine all lyrics sections into single text"""
        lyrics_parts = []
        for section in self.structure:
            section_type = section.get('type', '').upper()
            lyrics = section.get('lyrics', '')
            lyrics_parts.append(f"[{section_type}]\n{lyrics}\n")
        return "\n".join(lyrics_parts)
```

**Example JSON:**
```json
{
  "title": "Steam and Soliloquy",
  "genre": "indie folk",
  "mood": "reflective melancholy",
  "tempo": "slow",
  "structure": [
    {
      "type": "verse",
      "number": 1,
      "lyrics": "Steam ascends from the porcelain cup,\nSunlight stitches through the blinds' thin skin..."
    },
    {
      "type": "chorus",
      "lyrics": "Coffee brews the questions I can't quite name..."
    }
  ],
  "metadata": {
    "key": "D major",
    "time_signature": "4/4",
    "vocal_style": "whispered confessions with dynamic crescendos",
    "instrumentation": ["acoustic guitar", "harmonica", "soft percussion"]
  }
}
```

### ArtifactRecord

```python
@dataclass
class ArtifactRecord:
    """Represents generated artifact metadata"""
    id: Optional[int]
    prompt_id: int
    artifact_type: str
    file_path: str
    preview_path: Optional[str]
    metadata: Dict[str, Any]
    created_at: Optional[datetime] = None
```

**Usage Example:**
```python
# Create artifact record for saving
artifact = ArtifactRecord(
    id=None,  # Will be set by database
    prompt_id=200,
    artifact_type='image',
    file_path='image/200_20260106T120000/generated_image_001.png',
    preview_path='image/200_20260106T120000/generated_image_001.png',
    metadata={
        'prompt': 'A serene mountain lake...',
        'width': 768,
        'height': 1024,
        'steps': 20,
        'generated_at': '2026-01-06T12:00:00'
    }
)

# Save to database
artifact_id = artifact_repo.save_artifact(artifact)
```

## Type Hints and Validation

### JSON Schema Validation (Optional Enhancement)

```python
from typing import TypedDict, List

class TechnicalParams(TypedDict):
    aspect_ratio: str
    quality: str
    mood: str

class Composition(TypedDict):
    subject: str
    background: str
    lighting: str

class ImagePromptJSON(TypedDict):
    prompt: str
    negative_prompt: str
    style_tags: List[str]
    technical_params: TechnicalParams
    composition: Composition
```

## Next Steps

Proceed to [04-Tkinter-UI-Design.md](04-Tkinter-UI-Design.md) for the UI architecture.
