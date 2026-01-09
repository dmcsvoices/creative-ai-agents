# Configuration

## Configuration File: `media_generator_config.json`

```json
{
  "database": {
    "path": "/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db"
  },

  "comfyui": {
    "python": "/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/bin/python",
    "comfyui_directory": "/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI",
    "output_directory": "output/poets",
    "host": "http://127.0.0.1:8188",
    "timeout_seconds": 900,
    "queue_size": 1
  },

  "media": {
    "scripts": {
      "image": "/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/poets_service/image_workflow.py",
      "music": "/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/poets_service/audio_workflow.py"
    }
  },

  "ui": {
    "window_width": 1200,
    "window_height": 800,
    "refresh_interval_seconds": 30,
    "max_prompts_display": 100
  }
}
```

## Configuration Loader

```python
import json
from pathlib import Path

def load_config(config_path: str = "media_generator_config.json") -> dict:
    """Load configuration from JSON file"""
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, 'r') as f:
        config = json.load(f)

    # Validate required fields
    required_fields = [
        ('database', 'path'),
        ('comfyui', 'python'),
        ('comfyui', 'comfyui_directory'),
        ('media', 'scripts', 'image'),
        ('media', 'scripts', 'music')
    ]

    for fields in required_fields:
        obj = config
        for field in fields:
            if field not in obj:
                raise KeyError(f"Missing required config field: {'.'.join(fields)}")
            obj = obj[field]

    return config
```

## Configuration Parameters

### Database Section
- **path**: Full path to SQLite database file
  - Must be accessible for read/write
  - Should be backed up regularly

### ComfyUI Section
- **python**: Path to Python interpreter in ComfyUI environment
  - Must have ComfyUI dependencies installed
- **comfyui_directory**: Root directory of ComfyUI installation
  - Used as working directory for subprocess
- **output_directory**: Where to save generated media
  - Relative to ComfyUI directory or absolute path
- **host**: ComfyUI server URL (for future API integration)
- **timeout_seconds**: Maximum time for generation
  - Default: 900 (15 minutes)
  - Adjust based on prompt complexity
- **queue_size**: Batch size for workflow execution
  - Default: 1 (process one at a time)

### Media Section
- **scripts.image**: Path to image generation workflow script
- **scripts.music**: Path to audio generation workflow script

### UI Section
- **window_width**: Initial window width in pixels
- **window_height**: Initial window height in pixels
- **refresh_interval_seconds**: Auto-refresh interval (optional feature)
- **max_prompts_display**: Maximum prompts to show in lists

## Environment Variables (Optional)

```bash
# Override config file location
export MEDIA_GENERATOR_CONFIG="/path/to/config.json"

# Override database path
export MUSINGS_DB_PATH="/path/to/database.db"

# Override ComfyUI directory
export COMFYUI_DIR="/path/to/ComfyUI"
```

## Validation

```python
def validate_config(config: dict) -> list[str]:
    """Validate configuration and return list of warnings/errors"""
    issues = []

    # Check database exists
    db_path = Path(config['database']['path'])
    if not db_path.exists():
        issues.append(f"Database not found: {db_path}")

    # Check Python executable
    python_path = Path(config['comfyui']['python'])
    if not python_path.exists():
        issues.append(f"Python executable not found: {python_path}")

    # Check ComfyUI directory
    comfyui_dir = Path(config['comfyui']['comfyui_directory'])
    if not comfyui_dir.exists():
        issues.append(f"ComfyUI directory not found: {comfyui_dir}")

    # Check workflow scripts
    for script_type, script_path in config['media']['scripts'].items():
        path = Path(script_path)
        if not path.exists():
            issues.append(f"{script_type} workflow script not found: {path}")

    return issues
```
