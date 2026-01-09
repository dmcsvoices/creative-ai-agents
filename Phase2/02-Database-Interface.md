# Database Interface Layer

## Database Schema

### prompts table

```sql
CREATE TABLE prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_text TEXT NOT NULL,              -- Original user request
    prompt_type VARCHAR(50) DEFAULT 'text', -- 'image_prompt', 'lyrics_prompt', etc.
    status VARCHAR(20) DEFAULT 'unprocessed', -- 'completed', 'failed', etc.
    priority INTEGER DEFAULT 5,
    config_name VARCHAR(100),
    metadata TEXT,                          -- JSON field

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Results tracking
    output_reference INTEGER,               -- FK to writings.id (JSON prompt)
    error_message TEXT,
    processing_duration INTEGER,

    -- Media generation tracking
    artifact_status TEXT DEFAULT 'pending', -- 'pending', 'processing', 'ready', 'error'
    artifact_metadata TEXT,                 -- JSON field

    FOREIGN KEY (output_reference) REFERENCES writings(id)
);
```

**Key Fields for Media Generator:**
- `artifact_status`: Tracks media generation progress
  - `'pending'` - JSON prompt ready, media not generated yet
  - `'processing'` - Media Generator currently working on it
  - `'ready'` - Media generated and saved
  - `'error'` - Generation failed
- `output_reference`: Links to writings.id where JSON prompt is stored

### writings table

```sql
CREATE TABLE writings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content_type TEXT NOT NULL,             -- 'image_prompt', 'lyrics_prompt'
    content TEXT NOT NULL,                  -- JSON-structured prompt
    original_filename TEXT UNIQUE,
    created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_timestamp DATETIME,
    word_count INTEGER,
    character_count INTEGER,
    publication_status TEXT DEFAULT 'draft',
    mood TEXT,
    explicit_content BOOLEAN DEFAULT FALSE,
    notes TEXT,
    content_hash TEXT,
    source_prompt_id INTEGER,               -- FK to prompts.id
    generation_method VARCHAR(50) DEFAULT 'manual'
);
```

**Key Fields for Media Generator:**
- `content`: Contains the JSON-structured prompt (main data source)
- `content_type`: Identifies type ('image_prompt' or 'lyrics_prompt')
- `source_prompt_id`: Links back to the original prompt

### prompt_artifacts table

```sql
CREATE TABLE prompt_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL,             -- FK to prompts.id
    artifact_type TEXT NOT NULL,            -- 'image', 'audio'
    file_path TEXT NOT NULL,                -- Relative: 'image/123_20260106/file.png'
    preview_path TEXT,                      -- For thumbnails (images only)
    metadata TEXT,                          -- JSON: generation params, dimensions, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
);
```

**Key Fields for Media Generator:**
- `file_path`: Relative path from output root (what we write here)
- `preview_path`: For images, same as file_path; for audio, NULL
- `metadata`: JSON object with generation parameters and stats

## Repository Classes

### PromptRepository

```python
import sqlite3
from typing import List, Optional
from datetime import datetime

class PromptRepository:
    """Database access layer for prompts"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_connection(self) -> sqlite3.Connection:
        """Create database connection with row factory"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def get_pending_image_prompts(self, limit: int = 100) -> List[PromptRecord]:
        """Query all pending image prompts with their JSON content"""
        query = """
        SELECT
            p.id,
            p.prompt_text,
            p.prompt_type,
            p.status,
            p.artifact_status,
            p.output_reference,
            p.created_at,
            p.completed_at,
            p.error_message,
            w.id as writing_id,
            w.content as json_content
        FROM prompts p
        INNER JOIN writings w ON p.output_reference = w.id
        WHERE p.status = 'completed'
          AND p.artifact_status = 'pending'
          AND p.prompt_type = 'image_prompt'
          AND w.content_type = 'image_prompt'
        ORDER BY p.created_at ASC
        LIMIT ?
        """

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

            return [
                PromptRecord(
                    id=row['id'],
                    prompt_text=row['prompt_text'],
                    prompt_type=row['prompt_type'],
                    status=row['status'],
                    artifact_status=row['artifact_status'],
                    output_reference=row['output_reference'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                    error_message=row['error_message'],
                    writing_id=row['writing_id'],
                    json_content=row['json_content']
                )
                for row in rows
            ]

    def get_pending_lyrics_prompts(self, limit: int = 100) -> List[PromptRecord]:
        """Query all pending lyrics prompts with their JSON content"""
        query = """
        SELECT
            p.id,
            p.prompt_text,
            p.prompt_type,
            p.status,
            p.artifact_status,
            p.output_reference,
            p.created_at,
            p.completed_at,
            p.error_message,
            w.id as writing_id,
            w.content as json_content
        FROM prompts p
        INNER JOIN writings w ON p.output_reference = w.id
        WHERE p.status = 'completed'
          AND p.artifact_status = 'pending'
          AND p.prompt_type = 'lyrics_prompt'
          AND w.content_type = 'lyrics_prompt'
        ORDER BY p.created_at ASC
        LIMIT ?
        """

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

            return [
                PromptRecord(
                    id=row['id'],
                    prompt_text=row['prompt_text'],
                    prompt_type=row['prompt_type'],
                    status=row['status'],
                    artifact_status=row['artifact_status'],
                    output_reference=row['output_reference'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                    error_message=row['error_message'],
                    writing_id=row['writing_id'],
                    json_content=row['json_content']
                )
                for row in rows
            ]

    def update_artifact_status(
        self,
        prompt_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> None:
        """Update prompt artifact_status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if error_message:
                cursor.execute("""
                    UPDATE prompts
                    SET artifact_status = ?, error_message = ?
                    WHERE id = ?
                """, (status, error_message, prompt_id))
            else:
                cursor.execute("""
                    UPDATE prompts
                    SET artifact_status = ?
                    WHERE id = ?
                """, (status, prompt_id))
            conn.commit()
```

### ArtifactRepository

```python
import json

class ArtifactRepository:
    """Database access layer for prompt_artifacts"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def save_artifact(self, artifact: ArtifactRecord) -> int:
        """Save generated artifact to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO prompt_artifacts (
                    prompt_id,
                    artifact_type,
                    file_path,
                    preview_path,
                    metadata,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                artifact.prompt_id,
                artifact.artifact_type,
                artifact.file_path,
                artifact.preview_path,
                json.dumps(artifact.metadata)
            ))
            conn.commit()
            return cursor.lastrowid

    def get_artifacts_for_prompt(self, prompt_id: int) -> List[ArtifactRecord]:
        """Get all artifacts for a prompt"""
        query = """
        SELECT id, prompt_id, artifact_type, file_path, preview_path, metadata, created_at
        FROM prompt_artifacts
        WHERE prompt_id = ?
        ORDER BY created_at DESC
        """

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (prompt_id,))
            rows = cursor.fetchall()

            return [
                ArtifactRecord(
                    id=row['id'],
                    prompt_id=row['prompt_id'],
                    artifact_type=row['artifact_type'],
                    file_path=row['file_path'],
                    preview_path=row['preview_path'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {},
                    created_at=datetime.fromisoformat(row['created_at'])
                )
                for row in rows
            ]
```

## Sample Queries

### Find all pending image prompts:
```sql
SELECT
    p.id,
    p.prompt_text,
    p.created_at,
    w.content
FROM prompts p
INNER JOIN writings w ON p.output_reference = w.id
WHERE p.artifact_status = 'pending'
  AND p.prompt_type = 'image_prompt'
ORDER BY p.created_at ASC;
```

### Find all pending lyrics prompts:
```sql
SELECT
    p.id,
    p.prompt_text,
    p.created_at,
    w.content
FROM prompts p
INNER JOIN writings w ON p.output_reference = w.id
WHERE p.artifact_status = 'pending'
  AND p.prompt_type = 'lyrics_prompt'
ORDER BY p.created_at ASC;
```

### Check status distribution:
```sql
SELECT
    prompt_type,
    artifact_status,
    COUNT(*) as count
FROM prompts
WHERE prompt_type IN ('image_prompt', 'lyrics_prompt')
GROUP BY prompt_type, artifact_status;
```

### View generated artifacts for a prompt:
```sql
SELECT
    pa.id,
    pa.artifact_type,
    pa.file_path,
    pa.created_at,
    p.prompt_text
FROM prompt_artifacts pa
INNER JOIN prompts p ON pa.prompt_id = p.id
WHERE pa.prompt_id = ?;
```

## Database Connection Best Practices

1. **Use timeout**: Always set `timeout=30.0` to handle concurrent access
2. **Use row_factory**: Set `conn.row_factory = sqlite3.Row` for dict-like access
3. **Use context managers**: `with conn:` for automatic commit/rollback
4. **Close connections**: Explicitly close in finally blocks or use context managers
5. **Handle errors**: Wrap queries in try/except blocks

## Next Steps

Proceed to [03-Data-Models.md](03-Data-Models.md) to see the Python data classes.
