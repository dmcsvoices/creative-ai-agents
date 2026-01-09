# Testing Guide

## Overview

This guide provides SQL queries, test procedures, and validation steps for testing the Media Generator application.

---

## Database Testing Queries

### 1. Check Pending Prompts

**Find all pending image prompts**:
```sql
SELECT
    p.id,
    p.prompt_text,
    p.prompt_type,
    p.status,
    p.artifact_status,
    p.created_at,
    w.content_type,
    LENGTH(w.content) as json_length
FROM prompts p
INNER JOIN writings w ON p.output_reference = w.id
WHERE p.status = 'completed'
  AND p.artifact_status = 'pending'
  AND p.prompt_type = 'image_prompt'
ORDER BY p.created_at ASC;
```

**Find all pending lyrics prompts**:
```sql
SELECT
    p.id,
    p.prompt_text,
    p.prompt_type,
    p.status,
    p.artifact_status,
    p.created_at,
    w.content_type,
    LENGTH(w.content) as json_length
FROM prompts p
INNER JOIN writings w ON p.output_reference = w.id
WHERE p.status = 'completed'
  AND p.artifact_status = 'pending'
  AND p.prompt_type = 'lyrics_prompt'
ORDER BY p.created_at ASC;
```

**Current test data** (as of 2026-01-06):
```sql
-- Expected results:
-- Image prompts: IDs 197, 199, 200
-- Lyrics prompts: ID 198
```

### 2. View Prompt JSON Content

**Get full JSON for a specific prompt**:
```sql
SELECT
    p.id,
    p.prompt_text,
    p.prompt_type,
    w.content
FROM prompts p
INNER JOIN writings w ON p.output_reference = w.id
WHERE p.id = 200;  -- Replace with actual prompt_id
```

**Validate JSON structure**:
```sql
-- Check if JSON is valid (SQLite 3.38+)
SELECT
    p.id,
    json_valid(w.content) as is_valid_json
FROM prompts p
INNER JOIN writings w ON p.output_reference = w.id
WHERE p.prompt_type IN ('image_prompt', 'lyrics_prompt');
```

### 3. Check Artifact Status Distribution

**Count prompts by status**:
```sql
SELECT
    prompt_type,
    artifact_status,
    COUNT(*) as count
FROM prompts
WHERE prompt_type IN ('image_prompt', 'lyrics_prompt')
GROUP BY prompt_type, artifact_status
ORDER BY prompt_type, artifact_status;
```

**Expected output**:
```
prompt_type    | artifact_status | count
---------------|-----------------|------
image_prompt   | pending         | 3
image_prompt   | ready           | 0
lyrics_prompt  | pending         | 1
lyrics_prompt  | ready           | 0
```

### 4. View Generated Artifacts

**Get all artifacts for a specific prompt**:
```sql
SELECT
    pa.id,
    pa.prompt_id,
    pa.artifact_type,
    pa.file_path,
    pa.preview_path,
    pa.metadata,
    pa.created_at
FROM prompt_artifacts pa
WHERE pa.prompt_id = 200;  -- Replace with actual prompt_id
```

**Get all artifacts with prompt details**:
```sql
SELECT
    p.id as prompt_id,
    p.prompt_text,
    p.prompt_type,
    p.artifact_status,
    pa.id as artifact_id,
    pa.artifact_type,
    pa.file_path,
    pa.created_at as artifact_created_at
FROM prompts p
LEFT JOIN prompt_artifacts pa ON p.id = pa.prompt_id
WHERE p.prompt_type IN ('image_prompt', 'lyrics_prompt')
ORDER BY p.created_at DESC;
```

### 5. Check for Errors

**Find prompts with errors**:
```sql
SELECT
    id,
    prompt_text,
    prompt_type,
    artifact_status,
    error_message,
    created_at,
    completed_at
FROM prompts
WHERE artifact_status = 'error'
  AND prompt_type IN ('image_prompt', 'lyrics_prompt')
ORDER BY created_at DESC;
```

### 6. Verify File Paths

**Check artifact file paths are relative**:
```sql
SELECT
    prompt_id,
    file_path,
    CASE
        WHEN file_path LIKE '/%' THEN 'ABSOLUTE (WRONG!)'
        WHEN file_path LIKE 'image/%' OR file_path LIKE 'audio/%' THEN 'RELATIVE (CORRECT)'
        ELSE 'UNKNOWN FORMAT'
    END as path_format
FROM prompt_artifacts;
```

**Expected**: All paths should be RELATIVE

### 7. Database Statistics

**Overall system statistics**:
```sql
SELECT
    'Total Prompts' as metric,
    COUNT(*) as value
FROM prompts
WHERE prompt_type IN ('image_prompt', 'lyrics_prompt')

UNION ALL

SELECT
    'Pending Prompts',
    COUNT(*)
FROM prompts
WHERE prompt_type IN ('image_prompt', 'lyrics_prompt')
  AND artifact_status = 'pending'

UNION ALL

SELECT
    'Ready Prompts',
    COUNT(*)
FROM prompts
WHERE prompt_type IN ('image_prompt', 'lyrics_prompt')
  AND artifact_status = 'ready'

UNION ALL

SELECT
    'Error Prompts',
    COUNT(*)
FROM prompts
WHERE prompt_type IN ('image_prompt', 'lyrics_prompt')
  AND artifact_status = 'error'

UNION ALL

SELECT
    'Total Artifacts',
    COUNT(*)
FROM prompt_artifacts;
```

---

## Test Data Creation

### Create Test Image Prompt

```sql
-- Step 1: Insert prompt
INSERT INTO prompts (
    prompt_text,
    prompt_type,
    status,
    artifact_status,
    created_at,
    completed_at
) VALUES (
    'Test: Create a futuristic cityscape at sunset',
    'image_prompt',
    'completed',
    'pending',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- Step 2: Get the prompt_id (will be in last_insert_rowid())
-- SQLite: SELECT last_insert_rowid();

-- Step 3: Insert JSON content to writings
INSERT INTO writings (
    title,
    content_type,
    content,
    source_prompt_id,
    created_date
) VALUES (
    'Test Image Prompt',
    'image_prompt',
    '{
      "prompt": "A futuristic cityscape at sunset with flying vehicles and neon lights, cyberpunk aesthetic, ultra-detailed, cinematic composition",
      "negative_prompt": "low quality, blurry, distorted, amateur",
      "style_tags": ["cyberpunk", "futuristic", "cinematic"],
      "technical_params": {
        "aspect_ratio": "16:9",
        "quality": "high",
        "mood": "atmospheric and dramatic"
      },
      "composition": {
        "subject": "Futuristic city skyline with flying cars",
        "background": "Orange and purple sunset sky",
        "lighting": "Neon lights and warm sunset glow"
      }
    }',
    (SELECT last_insert_rowid()),
    CURRENT_TIMESTAMP
);

-- Step 4: Link prompt to writing
UPDATE prompts
SET output_reference = (SELECT last_insert_rowid())
WHERE id = (SELECT last_insert_rowid() - 1);
```

### Create Test Lyrics Prompt

```sql
-- Step 1: Insert prompt
INSERT INTO prompts (
    prompt_text,
    prompt_type,
    status,
    artifact_status,
    created_at,
    completed_at
) VALUES (
    'Test: Write a melancholic indie song about memories',
    'lyrics_prompt',
    'completed',
    'pending',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- Step 2: Insert JSON content to writings
INSERT INTO writings (
    title,
    content_type,
    content,
    source_prompt_id,
    created_date
) VALUES (
    'Test Lyrics Prompt',
    'lyrics_prompt',
    '{
      "title": "Faded Polaroids",
      "genre": "indie",
      "mood": "melancholic",
      "tempo": "slow",
      "structure": [
        {
          "type": "verse",
          "number": 1,
          "lyrics": "Dust collects on wooden frames\nFaces blur but feelings stay\nYour laugh echoes in empty rooms\nA ghost of brighter days"
        },
        {
          "type": "chorus",
          "lyrics": "Faded polaroids on the shelf\nMemories I can barely help\nTime moves on but I stand still\nLost in moments I never will"
        }
      ],
      "metadata": {
        "key": "E minor",
        "time_signature": "4/4",
        "vocal_style": "soft and introspective",
        "instrumentation": ["acoustic guitar", "piano", "soft drums"]
      }
    }',
    (SELECT last_insert_rowid()),
    CURRENT_TIMESTAMP
);

-- Step 3: Link prompt to writing
UPDATE prompts
SET output_reference = (SELECT last_insert_rowid())
WHERE id = (SELECT last_insert_rowid() - 1);
```

---

## Manual Testing Procedures

### Test Procedure 1: Application Startup

**Steps**:
1. Open terminal
2. Navigate to project directory
   ```bash
   cd /Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean
   ```
3. Activate Python environment (if needed)
   ```bash
   source poets_env_fresh/bin/activate
   ```
4. Run application
   ```bash
   python3 media_generator/main.py
   ```

**Expected Results**:
- [ ] Application window opens without errors
- [ ] Window title is "Media Generator - Pending Prompts"
- [ ] Window size is approximately 1200x800
- [ ] No error messages in terminal
- [ ] Status bar shows "Ready | Pending: X prompts"

**Failure Cases**:
- **Config file not found**: Check file exists at `media_generator/media_generator_config.json`
- **Database not found**: Check database path in config
- **Import errors**: Check all required files exist in media_generator/

---

### Test Procedure 2: List Population

**Steps**:
1. Launch application
2. Observe left panel (Image Prompts)
3. Observe right panel (Song Prompts)

**Expected Results**:
- [ ] Image prompts list shows 3-4 items (IDs 197, 199, 200, plus any test data)
- [ ] Each row shows: ID, Created date, Preview text (truncated prompt)
- [ ] Lyrics prompts list shows 1-2 items (ID 198, plus any test data)
- [ ] Each row shows: ID, Created date, Title
- [ ] Lists are sorted by creation date (oldest first)
- [ ] Scrollbars appear if needed

**Failure Cases**:
- **Empty lists**: Check database has pending prompts (use SQL queries above)
- **SQL error**: Check repository SQL syntax
- **Encoding error**: Check JSON content is valid UTF-8

---

### Test Procedure 3: Prompt Selection and Details

**Steps**:
1. Click on an image prompt in the left list
2. Observe details panel
3. Click on a lyrics prompt in the right list
4. Observe details panel

**Expected Results**:
- [ ] Clicking image prompt highlights the row
- [ ] Details panel shows:
  - Prompt ID
  - Type (image_prompt)
  - Created timestamp
  - Original request text
  - Formatted JSON content
- [ ] Clicking lyrics prompt clears image selection
- [ ] Details panel updates with lyrics prompt information
- [ ] JSON is properly formatted with indentation

**Failure Cases**:
- **No details shown**: Check `display_prompt_details()` method
- **Malformed JSON**: Check JSON.loads() error handling
- **Selection not clearing**: Check event handler logic

---

### Test Procedure 4: Image Generation

**Prerequisites**:
- ComfyUI server running
- Image workflow script exists
- At least one pending image prompt

**Steps**:
1. Launch application
2. Select an image prompt from the list
3. Click "Generate Selected" button
4. Monitor status bar for progress messages
5. Wait for completion (30-120 seconds typically)
6. Observe success/error dialog

**Expected Results**:
- [ ] Status bar shows "Generating image for prompt #..."
- [ ] Button becomes disabled during generation
- [ ] After completion, success dialog appears
- [ ] Dialog shows "Generated N image(s) for prompt #X"
- [ ] Prompt disappears from pending list
- [ ] Status bar updates with new count

**Verification**:
```bash
# Check output directory
ls -la /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets/image/

# Check database
sqlite3 /Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db
sqlite> SELECT * FROM prompt_artifacts WHERE prompt_id = 200;
sqlite> SELECT artifact_status FROM prompts WHERE id = 200;
```

**Expected Database State**:
- `prompts.artifact_status` = 'ready'
- `prompt_artifacts` has new row with:
  - `artifact_type` = 'image'
  - `file_path` like 'image/200_YYYYMMDDTHHMMSS/generated_image_001.png'
  - `metadata` JSON with prompt details

**Failure Cases**:
- **Timeout error**: Increase timeout in config, or check ComfyUI performance
- **Script not found**: Verify workflow_script path in config
- **No output files**: Check ComfyUI stderr output, verify workflow runs
- **Import error**: Check ComfyUI working directory

---

### Test Procedure 5: Audio Generation

**Prerequisites**:
- ComfyUI server running
- Audio workflow script exists
- At least one pending lyrics prompt

**Steps**:
1. Launch application
2. Select a lyrics prompt from the list
3. Click "Generate Selected" button
4. Monitor status bar for progress messages
5. Wait for completion (90-240 seconds typically)
6. Observe success/error dialog

**Expected Results**:
- [ ] Status bar shows "Generating audio for prompt #..."
- [ ] Button becomes disabled during generation
- [ ] After completion, success dialog appears
- [ ] Dialog shows "Generated N audio file(s) for prompt #X"
- [ ] Prompt disappears from pending list
- [ ] Status bar updates with new count

**Verification**:
```bash
# Check output directory
ls -la /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets/audio/

# Play audio file
afplay /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets/audio/198_*/generated_song.mp3
```

**Expected Database State**:
- `prompts.artifact_status` = 'ready'
- `prompt_artifacts` has new row with:
  - `artifact_type` = 'audio'
  - `file_path` like 'audio/198_YYYYMMDDTHHMMSS/generated_song.mp3'
  - `metadata` JSON with title, genre, mood, etc.

---

### Test Procedure 6: Frontend Verification

**Prerequisites**:
- Media Generator has created artifacts
- Frontend server running
- Browser open to http://localhost:5000

**Steps**:
1. Navigate to Browse tab
2. Filter by content type: "image_prompt"
3. Find the generated prompt
4. Click on the card
5. Observe image modal
6. Repeat for "lyrics_prompt"

**Expected Results**:
- [ ] Prompt card shows in Browse tab
- [ ] Card displays thumbnail (for images)
- [ ] Clicking card opens modal viewer
- [ ] Image displays at full resolution
- [ ] Can zoom and pan image
- [ ] Audio player shows controls
- [ ] Can play/pause audio

**Failure Cases**:
- **No artifacts shown**: Check API endpoint `/api/prompts/{id}/artifacts`
- **404 on media file**: Check file_path in database matches actual file
- **Image not loading**: Check file permissions, MIME type

---

### Test Procedure 7: Error Handling

**Test Case A: ComfyUI Not Running**

**Steps**:
1. Stop ComfyUI server
2. Launch Media Generator
3. Select a prompt
4. Click "Generate Selected"

**Expected Results**:
- [ ] Error dialog appears
- [ ] Error message mentions connection or subprocess failure
- [ ] Prompt status updated to 'error'
- [ ] error_message field populated in database
- [ ] Prompt still shows in pending list with error indicator

**Test Case B: Invalid JSON**

**Steps**:
1. Manually corrupt JSON in database:
   ```sql
   UPDATE writings
   SET content = 'NOT VALID JSON'
   WHERE id = (SELECT output_reference FROM prompts WHERE id = 200);
   ```
2. Try to generate
3. Observe error handling

**Expected Results**:
- [ ] Error dialog shows JSON parsing error
- [ ] Status updated to 'error'
- [ ] Application does not crash

**Test Case C: Timeout**

**Steps**:
1. Set very short timeout in config (5 seconds)
2. Try to generate
3. Wait for timeout

**Expected Results**:
- [ ] Subprocess times out after 5 seconds
- [ ] Error dialog shows timeout message
- [ ] Status updated to 'error'

---

## Automated Testing (Optional)

### Unit Tests

**File**: `media_generator/test_models.py`

```python
import unittest
import json
from models import PromptRecord, ImagePromptData, LyricsPromptData
from datetime import datetime

class TestDataModels(unittest.TestCase):

    def test_image_prompt_parsing(self):
        """Test ImagePromptData.from_json() parses correctly"""
        json_str = '''{
            "prompt": "Test prompt",
            "negative_prompt": "Test negative",
            "style_tags": ["tag1", "tag2"],
            "technical_params": {
                "aspect_ratio": "16:9",
                "quality": "high",
                "mood": "peaceful"
            },
            "composition": {
                "subject": "Test subject",
                "background": "Test background",
                "lighting": "Test lighting"
            }
        }'''

        data = ImagePromptData.from_json(json.loads(json_str))

        self.assertEqual(data.prompt, "Test prompt")
        self.assertEqual(data.negative_prompt, "Test negative")
        self.assertEqual(data.aspect_ratio, "16:9")
        self.assertEqual(data.quality, "high")
        self.assertIn("tag1", data.style_tags)

    def test_lyrics_prompt_parsing(self):
        """Test LyricsPromptData.from_json() parses correctly"""
        json_str = '''{
            "title": "Test Song",
            "genre": "indie",
            "mood": "melancholic",
            "tempo": "slow",
            "structure": [
                {"type": "verse", "lyrics": "Test verse"},
                {"type": "chorus", "lyrics": "Test chorus"}
            ],
            "metadata": {
                "key": "E minor",
                "time_signature": "4/4",
                "vocal_style": "soft",
                "instrumentation": ["guitar", "piano"]
            }
        }'''

        data = LyricsPromptData.from_json(json.loads(json_str))

        self.assertEqual(data.title, "Test Song")
        self.assertEqual(data.genre, "indie")
        self.assertEqual(len(data.structure), 2)
        self.assertEqual(data.key, "E minor")

    def test_get_full_lyrics(self):
        """Test LyricsPromptData.get_full_lyrics() combines sections"""
        data = LyricsPromptData(
            title="Test",
            genre="test",
            mood="test",
            tempo="test",
            structure=[
                {"type": "verse", "lyrics": "Line 1"},
                {"type": "chorus", "lyrics": "Line 2"}
            ],
            key="C",
            time_signature="4/4",
            vocal_style="test",
            instrumentation=[]
        )

        lyrics = data.get_full_lyrics()

        self.assertIn("[VERSE]", lyrics)
        self.assertIn("Line 1", lyrics)
        self.assertIn("[CHORUS]", lyrics)
        self.assertIn("Line 2", lyrics)

if __name__ == '__main__':
    unittest.main()
```

**Run tests**:
```bash
cd media_generator
python3 -m unittest test_models.py
```

---

## Performance Benchmarks

### Expected Generation Times

**Image Generation**:
- Simple prompts: 30-60 seconds
- Complex prompts: 60-120 seconds
- Multiple variations: +30 seconds per image

**Audio Generation**:
- Short songs (< 2 minutes): 90-150 seconds
- Long songs (> 3 minutes): 150-300 seconds

### Resource Usage

**Memory**:
- Application: ~50-100 MB
- ComfyUI: 2-8 GB (depends on models loaded)

**Disk Space**:
- Images: ~2-10 MB per image
- Audio: ~3-8 MB per song
- Estimated for 100 prompts: 1-2 GB

### Database Performance

**Query Times** (expected):
- Get pending prompts: < 100ms
- Update status: < 50ms
- Insert artifact: < 50ms

**If slower**:
- Add index on `artifact_status`:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_prompts_artifact_status
  ON prompts(artifact_status, prompt_type);
  ```

---

## Validation Checklist

### Before Deployment

**Configuration**:
- [ ] Database path exists and is writable
- [ ] ComfyUI Python path exists
- [ ] ComfyUI directory exists
- [ ] Workflow scripts exist
- [ ] Output directory exists and is writable

**Database**:
- [ ] Can connect to database
- [ ] All required tables exist (prompts, writings, prompt_artifacts)
- [ ] Has pending prompts for testing

**ComfyUI**:
- [ ] ComfyUI server runs without errors
- [ ] Workflow scripts execute successfully
- [ ] Can generate sample image
- [ ] Can generate sample audio

**Application**:
- [ ] Application launches without errors
- [ ] Lists populate correctly
- [ ] Can select prompts
- [ ] Can generate media
- [ ] Errors handled gracefully

**Integration**:
- [ ] Frontend displays generated artifacts
- [ ] File paths are relative
- [ ] Metadata is correct
- [ ] End-to-end workflow works

---

## Troubleshooting Guide

### Issue: No prompts showing in lists

**Diagnosis**:
```sql
SELECT COUNT(*) FROM prompts WHERE artifact_status = 'pending' AND prompt_type = 'image_prompt';
```

**If count is 0**: No pending prompts in database. Create test data (see above).

**If count > 0**: Check repository query, check JOIN with writings table.

---

### Issue: "Database is locked" error

**Diagnosis**: Another process has exclusive lock

**Solution**:
1. Close all connections to database
2. Increase timeout in repository:
   ```python
   conn = sqlite3.connect(db_path, timeout=30.0)
   ```
3. Use context manager to ensure connections close:
   ```python
   with self.get_connection() as conn:
       # query here
   ```

---

### Issue: ComfyUI subprocess fails

**Diagnosis**: Check stderr output

**Common causes**:
- ComfyUI not running
- Wrong Python path
- Wrong working directory
- Missing dependencies

**Solution**:
```python
result = subprocess.run(
    cmd,
    cwd='/Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI',
    capture_output=True,
    text=True
)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("Return code:", result.returncode)
```

---

### Issue: Generated files not found

**Diagnosis**: Check output directory

**Steps**:
1. Check directory exists:
   ```bash
   ls -la /Volumes/Tikbalang2TB/Users/tikbalang/comfy_env/ComfyUI/output/poets/image/
   ```
2. Check workflow actually created files
3. Check glob pattern matches file names:
   ```python
   for img_file in output_dir.glob('*.png'):
       print(img_file)
   ```

---

## Summary

This testing guide provides:

✅ **SQL queries** for database validation
✅ **Test data creation** scripts
✅ **Manual testing procedures** for each feature
✅ **Automated unit tests** (optional)
✅ **Performance benchmarks** to measure against
✅ **Validation checklist** for deployment
✅ **Troubleshooting guide** for common issues

Use this guide throughout development to ensure the Media Generator application works correctly at every stage.
