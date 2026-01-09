# Integration Points

## Overview

The Media Generator App integrates with three existing systems:

1. **SQLite Database** - Shared data store with Poets Service
2. **ComfyUI Workflows** - Media generation engine
3. **Frontend Web App** - User interface for browsing artifacts

---

## 1. Database Integration

### Connection Details

**Path**: `/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db`

**Type**: SQLite3

**Access Pattern**: Direct file access (no server)

**Concurrency**: Both Poets Service and Media Generator can access simultaneously
- SQLite handles locking automatically
- Use `timeout=30.0` parameter to handle lock contention

### Connection Code

```python
import sqlite3

def get_connection() -> sqlite3.Connection:
    """Create database connection with proper configuration"""
    conn = sqlite3.connect(
        '/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db',
        timeout=30.0  # Wait up to 30 seconds for locks
    )
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    return conn
```

### Tables Used

#### **prompts** (Read/Write)
- **Read**: Query for pending prompts (`artifact_status = 'pending'`)
- **Write**: Update `artifact_status` field ('processing' → 'ready' or 'error')
- **Write**: Update `error_message` on failure

#### **writings** (Read Only)
- **Read**: Get JSON content via JOIN with prompts table
- **Never Write**: This table is managed by Poets Service

#### **prompt_artifacts** (Write Only)
- **Write**: Insert artifact records after successful generation
- **Fields**: prompt_id, artifact_type, file_path, preview_path, metadata

### Data Flow

```
┌─────────────────────┐
│  POETS SERVICE      │
│  (Phase 1)          │
└──────────┬──────────┘
           │ Writes prompts with artifact_status='pending'
           │ Writes JSON to writings table
           ▼
┌─────────────────────┐
│  DATABASE           │
│  anthonys_musings.db│
│                     │
│  prompts ◄──┐       │
│  writings   │       │
│  prompt_    │       │
│   artifacts │       │
└─────────────┼───────┘
           ▲  │
           │  │ Reads pending prompts
           │  │ Writes artifacts
           │  │ Updates status
           │  │
┌──────────┴──▼───────┐
│  MEDIA GENERATOR    │
│  (Phase 2)          │
└──────────┬──────────┘
           │
           ▼
    Generated Media Files
```

### Critical Queries

**Query pending image prompts**:
```sql
SELECT
    p.id,
    p.prompt_text,
    p.prompt_type,
    p.status,
    p.artifact_status,
    p.output_reference,
    p.created_at,
    w.content as json_content
FROM prompts p
INNER JOIN writings w ON p.output_reference = w.id
WHERE p.status = 'completed'
  AND p.artifact_status = 'pending'
  AND p.prompt_type = 'image_prompt'
ORDER BY p.created_at ASC;
```

**Update status to processing**:
```sql
UPDATE prompts
SET artifact_status = 'processing'
WHERE id = ?;
```

**Update status to ready**:
```sql
UPDATE prompts
SET artifact_status = 'ready'
WHERE id = ?;
```

**Update status to error**:
```sql
UPDATE prompts
SET artifact_status = 'error',
    error_message = ?
WHERE id = ?;
```

**Insert artifact**:
```sql
INSERT INTO prompt_artifacts (
    prompt_id,
    artifact_type,
    file_path,
    preview_path,
    metadata,
    created_at,
    updated_at
) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
```

---

## 2. ComfyUI Integration

### ComfyUI Environment

**Python Interpreter**: `/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/bin/python`

**ComfyUI Root**: `/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI`

**Output Root**: `/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets`

### Workflow Scripts

**Image Workflow**:
```
/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/poets_service/image_workflow.py
```

**Audio Workflow**:
```
/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/poets_service/audio_workflow.py
```

### Execution Pattern

**Image Generation Command**:
```bash
/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/bin/python \
  /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/poets_service/image_workflow.py \
  --prompt "A serene mountain lake at dawn, soft golden light..." \
  --negative-prompt "crowds, bright sunlight, harsh shadows" \
  --output /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets/image/200_20260106T213045 \
  --queue-size 1
```

**Audio Generation Command**:
```bash
/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/bin/python \
  /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/poets_service/audio_workflow.py \
  --lyrics "[VERSE]\nSteam ascends from the porcelain cup...\n[CHORUS]\nCoffee brews the questions..." \
  --tags "indie folk, reflective melancholy" \
  --output /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets/audio/198_20260106T212000 \
  --queue-size 1
```

### Working Directory

**IMPORTANT**: Must execute subprocess with `cwd` parameter set to ComfyUI directory:

```python
result = subprocess.run(
    cmd,
    cwd='/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI',  # Critical!
    capture_output=True,
    text=True,
    timeout=900  # 15 minutes
)
```

**Why**: ComfyUI workflows need to resolve relative imports and find models/nodes.

### Expected Output

**Image Workflow** generates:
- `generated_image_001.png`
- `generated_image_002.png` (if multiple variations requested)
- PNG format, dimensions vary (typically 768x1024 or 1024x768)

**Audio Workflow** generates:
- `generated_song.mp3`
- MP3 format, variable bitrate
- Duration depends on lyrics length (typically 2-4 minutes)

### Error Handling

**Common Errors**:
1. **Timeout**: Workflow takes longer than 900 seconds
   - Solution: Increase timeout in config or simplify prompt
2. **Python Not Found**: Incorrect Python path
   - Solution: Verify path exists and is executable
3. **Workflow Script Not Found**: Incorrect script path
   - Solution: Verify script exists at specified path
4. **ComfyUI Import Error**: Missing dependencies
   - Solution: Ensure ComfyUI environment is activated
5. **Out of Memory**: Large images or complex audio
   - Solution: Reduce resolution or audio length

**Error Detection**:
```python
if result.returncode != 0:
    raise RuntimeError(f"Workflow failed: {result.stderr}")
```

---

## 3. Frontend Integration

### Frontend Location

**Path**: `/Users/tikbalang/anthonys-musings-web/frontend/static/index.html`

**Server**: Flask app serving static files and API endpoints

**API Base**: `http://localhost:5000/api` (or configured port)

### API Endpoints Used by Frontend

**Get prompt artifacts**:
```
GET /api/prompts/{prompt_id}/artifacts
```

**Response**:
```json
{
  "prompt_id": 200,
  "artifacts": [
    {
      "id": 15,
      "artifact_type": "image",
      "file_path": "image/200_20260106T213045/generated_image_001.png",
      "preview_path": "image/200_20260106T213045/generated_image_001.png",
      "metadata": {
        "prompt": "A serene mountain lake...",
        "width": 768,
        "height": 1024
      },
      "created_at": "2026-01-06T21:30:45"
    }
  ]
}
```

**Get media file**:
```
GET /api/media/{file_path}
```

**Example**:
```
GET /api/media/image/200_20260106T213045/generated_image_001.png
```

**Returns**: Binary file data with appropriate Content-Type header

### Frontend Features (Already Built)

✅ **Browse Tab** - Shows all writings with filtering
✅ **Content Type Filter** - Can filter by 'image_prompt' and 'lyrics_prompt'
✅ **Image Cards** - Display image thumbnails in grid
✅ **Audio Cards** - Display audio player controls
✅ **Modal Viewer** - Full-screen image viewer with zoom/pan
✅ **Artifact Loading** - Automatically fetches artifacts for each prompt

**No Frontend Changes Needed!**

### Data Flow to Frontend

```
MEDIA GENERATOR APP
    ↓ Generates media files
    ↓ Saves to output/poets/image/ or output/poets/audio/
    ↓ Writes file_path to prompt_artifacts table
    ↓ Sets artifact_status = 'ready'
    ↓
DATABASE (anthonys_musings.db)
    ↓
FLASK API SERVER
    ↓ Reads prompt_artifacts table
    ↓ Serves files from output directory
    ↓
FRONTEND (index.html)
    ↓ Fetches artifacts via API
    ↓ Displays in Browse tab
    ↓
USER BROWSER
```

### Testing Frontend Integration

1. **Generate artifact** using Media Generator App
2. **Check database** has artifact record with correct file_path
3. **Open frontend** in browser (http://localhost:5000)
4. **Navigate to Browse tab**
5. **Filter by content type** (image_prompt or lyrics_prompt)
6. **Click on card** to view full artifact

---

## 4. Poets Service Integration

### Poets Service Role

**Location**: `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/poets_cron_service_v3.py`

**Status**: ✅ Phase 1 Complete

**Function**:
- Processes user requests for image_prompt and lyrics_prompt types
- Uses AutoGen agents to generate structured JSON prompts
- Saves JSON to writings table
- Sets artifact_status='pending' in prompts table
- Does NOT generate actual media (that's Phase 2's job)

### Integration Point

**Handoff**: Poets Service → Database → Media Generator

**Poets Service writes**:
```sql
-- Insert prompt record
INSERT INTO prompts (
    prompt_text,
    prompt_type,
    status,
    artifact_status
) VALUES (
    'Create a serene mountain landscape at dawn',
    'image_prompt',
    'completed',
    'pending'  ← Signals Media Generator
);

-- Insert JSON prompt to writings
INSERT INTO writings (
    content_type,
    content,
    source_prompt_id
) VALUES (
    'image_prompt',
    '{"prompt": "A serene mountain...", ...}',
    ?
);
```

**Media Generator reads**:
```sql
SELECT p.*, w.content
FROM prompts p
INNER JOIN writings w ON p.output_reference = w.id
WHERE p.artifact_status = 'pending'
  AND p.prompt_type = 'image_prompt';
```

### No Direct Communication

Poets Service and Media Generator App **do not communicate directly**. They only communicate through the database.

**Benefits**:
- Decoupled architecture
- Can run independently
- Can run on different machines
- Easy to scale

---

## 5. File System Integration

### Shared Output Directory

**Path**: `/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets/`

**Access**: Read/Write by Media Generator, Read by Frontend

**Structure**:
```
output/poets/
├── image/
│   └── {prompt_id}_{timestamp}/
│       └── *.png
└── audio/
    └── {prompt_id}_{timestamp}/
        └── *.mp3
```

### Path Handling

**Absolute Path** (used during generation):
```
/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets/image/200_20260106T213045/generated_image_001.png
```

**Relative Path** (stored in database):
```
image/200_20260106T213045/generated_image_001.png
```

**Conversion**:
```python
from pathlib import Path

output_root = Path('/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets')
absolute_path = Path('/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets/image/200_20260106T213045/generated_image_001.png')

relative_path = absolute_path.relative_to(output_root.parent)
# Result: 'output/poets/image/200_20260106T213045/generated_image_001.png'
```

Wait, checking the pattern from the documentation...

Actually, looking at the Phase 2 docs, the relative path should be from `output/poets/`, not include it:

```python
relative_path = str(full_path.relative_to(self.output_root.parent))
```

So if output_root is `output/poets`, then parent is `output`, and relative path includes `poets`:
- Database stores: `poets/image/200_.../file.png`

Or based on 02-Database-Interface.md example:
- Database stores: `image/200_20260106T120000/generated_image_001.png`

Let me check the artifact example again... yes, it stores just `image/123_20260106/file.png`.

So the relative path is from the output_root itself, not its parent:

```python
output_root = Path('output/poets')
full_path = Path('output/poets/image/200_20260106T213045/generated_image_001.png')
relative_path = str(full_path.relative_to(output_root))
# Result: 'image/200_20260106T213045/generated_image_001.png'
```

Let me correct this in the doc.

### File Permissions

**Requirement**: Media Generator must have write access to output directory

**Check**:
```bash
ls -ld /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets
```

**Fix if needed**:
```bash
chmod 755 /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets
```

---

## 6. Configuration Integration

### Shared Configuration Values

Some configuration values must match across systems:

| Value | Poets Service | Media Generator | Frontend |
|-------|--------------|-----------------|----------|
| Database Path | ✓ | ✓ | ✓ |
| Output Directory | ✓ | ✓ | ✓ |
| Content Types | ✓ | ✓ | ✓ |

### Poets Service Config

**File**: `poets_cron_config.json`

**Relevant Section**:
```json
{
  "processing": {
    "supported_types": ["text", "poetry", "prose", "dialogue", "song",
                        "image_prompt", "lyrics_prompt"]
  }
}
```

### Media Generator Config

**File**: `media_generator_config.json`

**Relevant Section**:
```json
{
  "database": {
    "path": "/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db"
  },
  "comfyui": {
    "output_directory": "output/poets"
  }
}
```

### Frontend Config

**File**: Backend Flask configuration (not in scope for this doc)

**Must Match**:
- Database path
- Output directory path
- API endpoint definitions

---

## Integration Testing Checklist

### End-to-End Test

- [ ] Poets Service generates image_prompt with artifact_status='pending'
- [ ] Media Generator sees prompt in pending list
- [ ] Media Generator successfully executes ComfyUI workflow
- [ ] Media files created in correct output directory
- [ ] Artifact record inserted into prompt_artifacts table
- [ ] Prompt artifact_status updated to 'ready'
- [ ] Frontend displays artifact in Browse tab
- [ ] Frontend can open/play media file

### Database Test

- [ ] Can connect to database with 30-second timeout
- [ ] Can query pending prompts
- [ ] Can update artifact_status
- [ ] Can insert artifact records
- [ ] No SQL errors or lock timeouts

### ComfyUI Test

- [ ] Python interpreter exists and is executable
- [ ] Workflow scripts exist
- [ ] Can execute workflow from correct working directory
- [ ] Workflow generates expected output files
- [ ] Can handle timeouts gracefully

### File System Test

- [ ] Output directory exists
- [ ] Have write permissions to output directory
- [ ] Can create subdirectories
- [ ] Generated files have correct permissions
- [ ] Relative paths calculated correctly

---

## Common Integration Issues

### Issue: Database Locked

**Symptom**: `sqlite3.OperationalError: database is locked`

**Cause**: Another process has exclusive lock

**Solution**:
- Increase timeout: `sqlite3.connect(db_path, timeout=30.0)`
- Ensure connections are closed properly
- Use context managers: `with conn:`

### Issue: ComfyUI Import Error

**Symptom**: `ModuleNotFoundError: No module named 'comfy'`

**Cause**: Not running from ComfyUI directory or wrong Python

**Solution**:
- Set `cwd` parameter in subprocess.run()
- Verify Python path points to ComfyUI environment

### Issue: File Not Found

**Symptom**: Generated files not found after workflow completes

**Cause**: Output directory mismatch or workflow failure

**Solution**:
- Check workflow script output path
- Verify output_directory config matches
- Check subprocess stderr for errors

### Issue: Frontend Not Showing Artifacts

**Symptom**: Frontend shows prompt but no artifacts

**Cause**: artifact_status not set to 'ready' or file_path incorrect

**Solution**:
- Verify artifact_status='ready' in prompts table
- Verify prompt_artifacts record exists
- Verify file_path is relative, not absolute
- Check frontend API is serving files correctly

---

## Next Steps

See [09-Development-Roadmap.md](09-Development-Roadmap.md) for implementation milestones.
