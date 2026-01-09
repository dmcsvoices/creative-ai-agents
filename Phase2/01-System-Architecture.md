# System Architecture

## High-Level Overview

The Media Generator App is the second phase of a two-app separation of concerns architecture for media generation.

### Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────┐
│          TKINTER GUI APPLICATION                        │
│                                                         │
│  ┌──────────────┐         ┌──────────────┐            │
│  │ Image Prompts│         │ Song Prompts │            │
│  │   List View  │         │  List View   │            │
│  └──────┬───────┘         └──────┬───────┘            │
│         │                        │                     │
│         └────────────┬───────────┘                     │
│                      │                                 │
│              ┌───────▼────────┐                        │
│              │ Generation     │                        │
│              │ Control Panel  │                        │
│              └───────┬────────┘                        │
└──────────────────────┼─────────────────────────────────┘
                       │
         ┌─────────────▼──────────────┐
         │  DATABASE INTERFACE LAYER  │
         │  • PromptRepository        │
         │  • ArtifactRepository      │
         │  • JSON Parser             │
         └─────────────┬──────────────┘
                       │
         ┌─────────────▼──────────────┐
         │  COMFYUI INTEGRATION LAYER │
         │  • ImageWorkflowExecutor   │
         │  • AudioWorkflowExecutor   │
         │  • File Management         │
         └─────────────┬──────────────┘
                       │
         ┌─────────────▼──────────────┐
         │   SQLite DATABASE          │
         │   anthonys_musings.db      │
         │   • prompts                │
         │   • writings               │
         │   • prompt_artifacts       │
         └────────────────────────────┘
```

## Full System Data Flow

```
USER REQUEST (via API or direct DB insert)
    ↓
POETS SERVICE (Phase 1 - Online AutoGen Agents)
    ↓ Generates JSON structured prompt
    ↓ Saves to writings table as TEXT
    ↓ Sets artifact_status = 'pending'
    ↓ Links via output_reference
    ↓
DATABASE (Centralized SQLite)
    ↓ prompts table: status='completed', artifact_status='pending'
    ↓ writings table: content=JSON, content_type='image_prompt'/'lyrics_prompt'
    ↓
MEDIA GENERATOR APP (Phase 2 - Tkinter Standalone)
    ↓ Queries pending prompts (JOIN prompts + writings)
    ↓ Displays in dual-list UI
    ↓ User selects prompt to generate
    ↓ Parses JSON structure
    ↓ Invokes ComfyUI workflow (subprocess)
    ↓ Saves generated files to output/poets/
    ↓ Writes artifact records to prompt_artifacts table
    ↓ Updates artifact_status = 'ready'
    ↓
FRONTEND (Already Built - Docker Container)
    ↓ Fetches /api/prompts/{id}/artifacts
    ↓ Displays in Browse tab
    ↓ Image modal viewer with zoom/pan
    ↓ Audio player with HTML5 controls
    ↓
USER VIEWS MEDIA
```

## Component Responsibilities

### 1. Poets Service (Phase 1 ✅ Complete)

**Responsibilities:**
- Accept user requests for image_prompt or lyrics_prompt
- Use AutoGen agents (Anthony, Cindy) to generate structured JSON
- Save JSON as TEXT to writings table
- Set prompt status to 'completed', artifact_status to 'pending'
- Link prompt to writing via output_reference

**Location:** `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/`

**Key Files:**
- `poets_cron_service_v3.py` - Main service with JSON generation methods
- `tools.py` - Database save utilities
- `poets_cron_config.json` - Configuration

**No changes needed** - Phase 1 complete and working.

### 2. Media Generator App (Phase 2 - This Project)

**Responsibilities:**
- Query database for pending prompts
- Display pending prompts in dual-list UI
- Parse JSON prompt structures
- Execute ComfyUI workflows via subprocess
- Save generated media files to disk
- Record artifact metadata in database
- Update prompt artifact_status

**Location:** `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/media_generator/`

**Key Components:**
- `app.py` - Main tkinter application
- `models.py` - Data classes
- `repositories.py` - Database access
- `executors.py` - ComfyUI workflow execution
- `media_generator_config.json` - Configuration

**To be built** - This is Phase 2.

### 3. Frontend (Already Built ✅)

**Responsibilities:**
- Browse tab with media filtering
- Fetch artifacts via API
- Display images in modal viewer
- Play audio with HTML5 controls
- Provide full-screen viewing experience

**Location:** `/Users/tikbalang/anthonys-musings-web/frontend/static/`

**Key Features:**
- Browse tab (lines 2020-2088)
- Artifact grid display
- Image modal (lines 2114-2193)
- Audio player
- Responsive design

**No changes needed** - Already fully implemented.

### 4. Database (Shared Resource)

**Responsibilities:**
- Store prompts and their status
- Store JSON prompt content (writings table)
- Track artifact metadata (prompt_artifacts table)
- Maintain referential integrity

**Location:** `/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db`

**Schema:** See [02-Database-Interface.md](02-Database-Interface.md)

**No changes needed** - Schema already perfect for this architecture.

## Architectural Principles

### Separation of Concerns

1. **Text Generation** (Poets Service) - Handles AI-powered creative writing
2. **Media Generation** (This App) - Handles compute-intensive media creation
3. **Display** (Frontend) - Handles user interface and browsing

### Decoupling Benefits

- **Reliability**: Poets Service doesn't crash if ComfyUI fails
- **Scalability**: Can run multiple media generator instances
- **Maintainability**: Each component has single responsibility
- **Flexibility**: Run media generation manually or on schedule
- **Simplicity**: Database-driven workflow, no complex orchestration

### Communication Pattern

**Database as Message Queue:**
- Poets Service writes prompts with `artifact_status='pending'`
- Media Generator reads prompts with `artifact_status='pending'`
- Media Generator updates to `artifact_status='processing'` during work
- Media Generator sets `artifact_status='ready'` on completion
- Frontend queries for prompts with `artifact_status='ready'`

## File Organization

### Output Directory Structure

```
output/poets/
├── image/
│   ├── 197_20260106T120000/
│   │   └── generated_image_001.png
│   ├── 199_20260106T120500/
│   │   └── generated_image_001.png
│   └── 200_20260106T121000/
│       └── generated_image_001.png
└── audio/
    └── 198_20260106T121500/
        └── generated_song.mp3
```

### Path Storage Convention

- **Database stores RELATIVE paths**: `image/197_20260106T120000/generated_image_001.png`
- **Full path calculation**: `{output_root}/{file_path}`
- **Preview paths**:
  - Images: Same as `file_path` (thumbnail = full image)
  - Audio: NULL (no preview for audio)

## Integration Points

### With Poets Service

- **Integration Type**: Database-driven (async, decoupled)
- **Shared Resource**: SQLite database
- **Contract**: Poets Service sets `artifact_status='pending'`, Media Generator processes it

### With Frontend

- **Integration Type**: Database-driven (async, via API)
- **API Endpoint**: `/api/prompts/{id}/artifacts`
- **Media Serving**: `/api/media/{file_path}`
- **Contract**: Media Generator writes to `prompt_artifacts`, Frontend reads from it

### With ComfyUI

- **Integration Type**: Subprocess execution
- **Method**: Python subprocess calling workflow scripts
- **Working Directory**: ComfyUI directory for proper environment context
- **Timeout**: 900 seconds (15 minutes) per generation

## Operational Model

### Running the System

**Prerequisites:**
1. ComfyUI server running (manual or systemd service)
2. Poets Service running (LaunchAgent)
3. Frontend API server running (Docker)

**Media Generation Workflow:**
1. Launch Media Generator App (manual or scheduled)
2. App queries database for pending prompts
3. User selects prompt(s) to generate
4. App invokes ComfyUI workflows
5. Generated files saved to output directory
6. Database updated with artifact paths
7. Frontend automatically shows new media on next refresh

### Monitoring

**Check queue status:**
```sql
SELECT prompt_type, artifact_status, COUNT(*)
FROM prompts
WHERE prompt_type IN ('image_prompt', 'lyrics_prompt')
GROUP BY prompt_type, artifact_status;
```

**View errors:**
```sql
SELECT id, prompt_text, error_message, created_at
FROM prompts
WHERE artifact_status = 'error'
ORDER BY created_at DESC;
```

## Next Steps

Proceed to [02-Database-Interface.md](02-Database-Interface.md) to understand the database schema and queries.
