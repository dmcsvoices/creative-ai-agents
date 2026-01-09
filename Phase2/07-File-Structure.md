# File Structure

## Project Directory Organization

```
/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/
│
├── Phase2/                             # Architecture documentation (current folder)
│   ├── README.md
│   ├── 01-System-Architecture.md
│   ├── 02-Database-Interface.md
│   ├── 03-Data-Models.md
│   ├── 04-Tkinter-UI-Design.md
│   ├── 05-ComfyUI-Integration.md
│   ├── 06-Configuration.md
│   ├── 07-File-Structure.md (this file)
│   ├── 08-Integration-Points.md
│   ├── 09-Development-Roadmap.md
│   └── 10-Testing-Guide.md
│
├── media_generator/                    # NEW - Phase 2 application
│   ├── __init__.py
│   ├── main.py                         # Application entry point
│   ├── app.py                          # MediaGeneratorApp class
│   ├── models.py                       # Data models
│   ├── repositories.py                 # Database repositories
│   ├── executors.py                    # ComfyUI workflow executors
│   ├── ui_components.py                # Reusable UI widgets
│   ├── config.py                       # Configuration loader
│   └── media_generator_config.json     # Configuration file
│
├── poets_cron_service_v3.py           # Phase 1 - Poets Service (complete)
├── tools.py                            # Phase 1 - Tools (complete)
├── poets_cron_config.json              # Phase 1 - Config (complete)
│
├── media/                              # Existing media pipeline (Phase 1)
│   ├── __init__.py
│   ├── base.py
│   ├── image.py
│   └── music.py
│
└── output/poets/                       # Media output directory
    ├── image/
    │   └── {prompt_id}_{timestamp}/
    │       ├── generated_image_001.png
    │       ├── generated_image_002.png
    │       └── ...
    └── audio/
        └── {prompt_id}_{timestamp}/
            ├── generated_song.mp3
            └── ...
```

## Module Descriptions

### `media_generator/main.py`

**Purpose**: Application entry point

**Responsibilities**:
- Load configuration from `media_generator_config.json`
- Validate configuration paths
- Initialize and launch MediaGeneratorApp
- Handle command-line arguments (if any)

**Pseudocode**:
```python
#!/usr/bin/env python3
"""
Media Generator Application Entry Point
"""
import sys
from pathlib import Path
from config import load_config, validate_config
from app import MediaGeneratorApp

def main():
    # Load configuration
    config_path = "media_generator/media_generator_config.json"
    config = load_config(config_path)

    # Validate configuration
    issues = validate_config(config)
    if issues:
        print("Configuration issues found:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    # Launch application
    app = MediaGeneratorApp(config)
    app.run()

    return 0

if __name__ == '__main__':
    sys.exit(main())
```

---

### `media_generator/app.py`

**Purpose**: Main application window and UI logic

**Responsibilities**:
- Create tkinter window and all UI components
- Manage application state (selected prompts, generation status)
- Handle user interactions (button clicks, list selections)
- Coordinate between repositories and executors
- Update UI with generation progress

**Key Classes**:
- `MediaGeneratorApp` - Main application controller

**Methods**:
- `__init__(config)` - Initialize window and repositories
- `create_widgets()` - Build UI components
- `setup_menu_bar()` - Create File/Tools/Help menus
- `refresh_image_list()` - Load pending image prompts
- `refresh_lyrics_list()` - Load pending lyrics prompts
- `on_image_select(event)` - Handle image prompt selection
- `on_lyrics_select(event)` - Handle lyrics prompt selection
- `display_prompt_details(prompt)` - Show JSON in details panel
- `generate_selected()` - Generate media for selected prompt
- `generate_all_pending()` - Batch process all prompts
- `generate_image_prompt(prompt)` - Execute image workflow
- `generate_lyrics_prompt(prompt)` - Execute audio workflow
- `open_output_folder()` - Open file explorer
- `update_status_bar()` - Update status text
- `run()` - Start main loop

---

### `media_generator/models.py`

**Purpose**: Data models and type definitions

**Responsibilities**:
- Define dataclasses for database records
- Provide JSON parsing methods
- Type safety for application data

**Key Classes**:
- `PromptRecord` - Database prompt row
- `ImagePromptData` - Parsed image prompt JSON
- `LyricsPromptData` - Parsed lyrics prompt JSON
- `ArtifactRecord` - Generated artifact metadata

**See**: [03-Data-Models.md](03-Data-Models.md) for complete implementations

---

### `media_generator/repositories.py`

**Purpose**: Database access layer

**Responsibilities**:
- Execute SQL queries
- Map database rows to data models
- Update prompt and artifact status
- Handle database connection lifecycle

**Key Classes**:
- `PromptRepository` - Access prompts and writings tables
- `ArtifactRepository` - Access prompt_artifacts table

**Methods**:
- `get_pending_image_prompts(limit)` - Query pending images
- `get_pending_lyrics_prompts(limit)` - Query pending lyrics
- `update_artifact_status(prompt_id, status, error)` - Update status
- `save_artifact(artifact)` - Insert artifact record
- `get_artifacts_for_prompt(prompt_id)` - Query existing artifacts

**See**: [02-Database-Interface.md](02-Database-Interface.md) for complete implementations

---

### `media_generator/executors.py`

**Purpose**: ComfyUI workflow execution

**Responsibilities**:
- Execute ComfyUI workflows via subprocess
- Create output directories with timestamps
- Parse workflow results
- Build artifact records
- Handle errors and timeouts

**Key Classes**:
- `ComfyUIWorkflowExecutor` - Base executor class
- `ImageWorkflowExecutor` - Image generation
- `AudioWorkflowExecutor` - Audio generation

**Methods**:
- `generate(prompt, json_data, progress_callback)` - Execute workflow
- `_create_output_directory(prompt_id, type)` - Create timestamped dir
- `_get_relative_path(full_path)` - Convert to relative path

**See**: [05-ComfyUI-Integration.md](05-ComfyUI-Integration.md) for complete implementations

---

### `media_generator/ui_components.py`

**Purpose**: Reusable UI widgets (optional enhancement)

**Responsibilities**:
- Custom treeview widgets with formatting
- Progress dialogs
- Error dialogs
- Status indicators

**Potential Classes**:
- `PromptTreeview` - Enhanced treeview with custom rendering
- `ProgressDialog` - Modal progress window
- `DetailPanel` - JSON formatter with syntax highlighting

---

### `media_generator/config.py`

**Purpose**: Configuration management

**Responsibilities**:
- Load JSON configuration file
- Validate required fields
- Check paths exist
- Provide environment variable overrides

**Functions**:
- `load_config(path)` - Load and parse JSON
- `validate_config(config)` - Check all required fields
- `get_config_value(key, default)` - Get with fallback

**See**: [06-Configuration.md](06-Configuration.md) for complete implementation

---

### `media_generator/media_generator_config.json`

**Purpose**: Application configuration

**Content**:
- Database path
- ComfyUI paths and settings
- Media workflow scripts
- UI preferences

**See**: [06-Configuration.md](06-Configuration.md) for complete structure

---

## Output Directory Structure

### Path Format

**Absolute path**: `/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets/`

**Relative path (stored in database)**: `image/123_20260106T120000/file.png`

**Structure**:
```
output/poets/
├── image/
│   ├── 197_20260106T210000/
│   │   └── generated_image_001.png
│   ├── 199_20260106T211500/
│   │   └── generated_image_001.png
│   └── 200_20260106T213000/
│       ├── generated_image_001.png
│       └── generated_image_002.png
│
└── audio/
    └── 198_20260106T212000/
        └── generated_song.mp3
```

### Naming Convention

**Directory**: `{prompt_id}_{timestamp}`
- `prompt_id`: Database prompt.id
- `timestamp`: ISO8601 compact format (YYYYMMDDTHHmmss)

**Files**: Generated by ComfyUI workflows
- Images: `generated_image_NNN.png` (where NNN is zero-padded sequence)
- Audio: `generated_song.mp3`

---

## Import Dependencies

### Standard Library
```python
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import sqlite3
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
```

### Third-Party (None Required)
All dependencies are from Python standard library. No pip packages needed.

---

## Database File

**Location**: `/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db`

**Access**: Read/Write via repositories

**Backup**: Recommended to backup before batch operations

---

## ComfyUI Workflow Scripts

**Image Workflow**: `/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/poets_service/image_workflow.py`

**Audio Workflow**: `/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/poets_service/audio_workflow.py`

**Python Interpreter**: `/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/bin/python`

**Working Directory**: `/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI`

---

## Logs and Temporary Files

### Logs (Future Enhancement)

```
media_generator/logs/
├── app.log                    # Application logs
├── generation.log             # Generation activity
└── errors.log                 # Error logs
```

### Temporary Files

ComfyUI creates temporary files in its own temp directory. No cleanup needed by application.

---

## Example File Creation Workflow

1. **User selects image prompt #200**
2. **App creates output directory**:
   ```
   output/poets/image/200_20260106T213045/
   ```
3. **App executes ComfyUI workflow**:
   ```bash
   /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/bin/python \
     /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/poets_service/image_workflow.py \
     --prompt "A serene mountain lake at dawn..." \
     --negative-prompt "crowds, bright sunlight" \
     --output /path/to/output/poets/image/200_20260106T213045 \
     --queue-size 1
   ```
4. **ComfyUI generates files**:
   ```
   output/poets/image/200_20260106T213045/generated_image_001.png
   ```
5. **App saves to database**:
   ```sql
   INSERT INTO prompt_artifacts (
       prompt_id,
       artifact_type,
       file_path,
       preview_path,
       metadata
   ) VALUES (
       200,
       'image',
       'image/200_20260106T213045/generated_image_001.png',
       'image/200_20260106T213045/generated_image_001.png',
       '{"prompt": "...", "width": 768, "height": 1024}'
   );
   ```
6. **App updates prompt status**:
   ```sql
   UPDATE prompts
   SET artifact_status = 'ready'
   WHERE id = 200;
   ```

---

## Next Steps

See [08-Integration-Points.md](08-Integration-Points.md) for connections to existing systems.
