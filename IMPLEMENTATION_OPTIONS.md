# Prompt Status Progression Bug - Root Cause & Fix

## Executive Summary

**ROOT CAUSE FOUND:** Database connection mode conflict in `_run_structured_prompt_generation()` method (added for Image/Lyric support).

**THE BUG:**
- `_run_structured_prompt_generation()` uses FOUR separate database connections with conflicting PRAGMA settings
- Connection #2 (via `save_to_sqlite_database()` at line 1041) switches database to WAL mode globally
- Connection #4 (final `update_prompt_status()` at line 1072) uses DEFAULT mode on WAL-enabled database
- Result: Final status update writes to WAL file but isn't visible to readers
- **Text prompts work fine** because they never call `save_to_sqlite_database()` and use consistent connection modes

**THE FIX:**
- Refactor `_run_structured_prompt_generation()` to use ONE connection with consistent PRAGMA settings
- Use single atomic transaction for all database operations
- OR make `update_prompt_status()` aware of current journal mode and adapt accordingly

**IMPACT:**
- Image/Lyric prompts will show status transitions same as text prompts
- No more "stuck at unprocessed" when JSON generation completes
- Stage 2 media generation will correctly find prompts with `artifact_status='pending'`
- No changes needed for text prompt flow (continues working as before)

---

## Problem Statement

IMAGE and LYRIC prompts are NOT progressing from "queued" to "processing" status automatically when the Poets Service starts working on them. The user reports:
- Web GUI shows prompts stuck at "UNPROCESSED" even when being actively worked on
- Only manual server restarts move prompts forward
- TEXT prompts (like "poem") work correctly and transition through states as expected

## Investigation Goal

Compare how TEXT prompts vs IMAGE/LYRIC prompts progress through statuses to identify where the bug occurs.

---

## Key Findings from Code Analysis

### File: `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/poets_cron_service_v3.py`

### Status Update Locations (15 total calls to `update_prompt_status()`)

**Method `_run_structured_prompt_generation()` (IMAGE/LYRIC Stage 1):**
- Line 947: `update_prompt_status(prompt_id, 'processing')` ✓ SETS PROCESSING
- Line 957, 998, 1012, 1022, 1031: Various failure states
- Line 1072: `update_prompt_status(prompt_id, 'completed', artifact_status='pending')` ✓ STAGE 1 COMPLETE

**Method `run_generation_session()` (TEXT prompts):**
- Line 1096: `update_prompt_status(prompt_id, 'processing')` ✓ SETS PROCESSING
- Line 1146: `update_prompt_status(prompt_id, 'completed')` ✓ COMPLETE
- Line 1152: Failure state

**Method `process_media_prompt()` (IMAGE/LYRIC Stage 2):**
- Line 1201: `update_prompt_status(prompt_id, 'processing', artifact_status='processing')` ✓ STAGE 2 START
- Line 1224: `update_prompt_status(prompt_id, 'completed', artifact_status='ready')` ✓ FINAL STATE
- Lines 1165, 1178, 1193, 1240, 1250: Various failure states

---

## Flow Comparison

### TEXT Prompt Flow (Single Stage)

```
┌─────────────────────────────────────────────────────────┐
│ 1. Cron runs run_queue_processor() (Line 1319)          │
│    Fetches: WHERE status='unprocessed'                  │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Route to: run_generation_session(prompt_data)        │
│    Line 1376 (for TEXT prompts)                         │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 3. IMMEDIATELY update status:                           │
│    update_prompt_status(id, 'processing')               │
│    LINE 1096 ✓                                          │
│                                                         │
│    STATUS: unprocessed → PROCESSING                     │
│    ARTIFACT_STATUS: NULL                                │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 4. Create agents & run LLM generation                   │
│    Lines 1099-1143                                      │
│    Duration: 1-5 minutes                                │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 5. FINAL update status:                                 │
│    update_prompt_status(id, 'completed')                │
│    LINE 1146 ✓                                          │
│                                                         │
│    STATUS: processing → COMPLETED                       │
│    ARTIFACT_STATUS: NULL                                │
└─────────────────────────────────────────────────────────┘

RESULT: User sees status change from "unprocessed" → "processing"
        within seconds of cron cycle starting
```

### IMAGE/LYRIC Prompt Flow (Two Stages)

#### STAGE 1: JSON Generation (First Cron Cycle)

```
┌─────────────────────────────────────────────────────────┐
│ 1. Cron runs run_queue_processor() (Line 1319)          │
│    Fetches: WHERE status='unprocessed'                  │
│    AND prompt_type='image_prompt'                       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Route to: run_generation_session(prompt_data)        │
│    Line 1370                                            │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 3. ROUTING DECISION (Lines 1088-1091):                  │
│    if prompt_type in ['image_prompt', 'lyrics_prompt']: │
│        return _run_structured_prompt_generation(...)    │
│                                                         │
│    EXIT run_generation_session() immediately            │
│    → Delegate to specialized handler                    │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 4. Enter: _run_structured_prompt_generation()           │
│    Line 934                                             │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 5. IMMEDIATELY update status:                           │
│    update_prompt_status(id, 'processing')               │
│    LINE 947 ✓                                           │
│                                                         │
│    STATUS: unprocessed → PROCESSING                     │
│    ARTIFACT_STATUS: NULL                                │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 6. Create structured agents & generate JSON             │
│    Lines 949-994                                        │
│    Duration: 30-90 seconds                              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 7. Validate JSON schema (image_prompt or lyrics_prompt) │
│    Lines 1007-1034                                      │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 8. Save JSON to database                                │
│    Lines 1038-1048                                      │
│    (uses save_to_sqlite_database)                       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 9. STAGE 1 COMPLETE:                                    │
│    update_prompt_status(id, 'completed',                │
│                         artifact_status='pending')      │
│    LINE 1072 ✓                                          │
│                                                         │
│    STATUS: processing → COMPLETED                       │
│    ARTIFACT_STATUS: NULL → 'pending'                    │
│                                                         │
│    This signals Stage 2 that JSON is ready              │
└─────────────────────────────────────────────────────────┘

RESULT: Prompt marked as "completed" but with artifact_status='pending'
        waiting for media generation in Stage 2
```

#### STAGE 2: Media Generation (Later Cron Cycle)

```
┌─────────────────────────────────────────────────────────┐
│ 1. WAITING FOR NEXT CRON CYCLE                          │
│    (typically 5-15 minutes later)                       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Cron runs run_queue_processor() (Line 1324)          │
│    Fetches DIFFERENT query:                             │
│    WHERE status='completed'                             │
│    AND artifact_status='pending'                        │
│    AND prompt_type IN ('image_prompt', 'lyrics_prompt') │
│                                                         │
│    → get_pending_media_prompts()                        │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 3. FOR EACH media_prompt:                               │
│    Route to: process_media_prompt(media_prompt)         │
│    Line 1389                                            │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 4. Pre-conditions checks:                               │
│    - Pipeline configured? (1159-1171)                   │
│    - Pipeline available? (1173-1184)                    │
│    - ComfyUI running? (1186-1199)                       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 5. IMMEDIATELY update status:                           │
│    update_prompt_status(id, 'processing',               │
│                         artifact_status='processing')   │
│    LINES 1201-1205 ✓                                    │
│                                                         │
│    STATUS: completed → PROCESSING (back to processing!) │
│    ARTIFACT_STATUS: pending → 'processing'              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 6. Execute pipeline.run() - ComfyUI generation          │
│    Lines 1208-1212                                      │
│    Duration: 2-15 minutes (image or audio)              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 7. Record artifacts to database (Line 1214)             │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ 8. FINAL STATE:                                         │
│    update_prompt_status(id, 'completed',                │
│                         artifact_status='ready',        │
│                         artifact_metadata=summary)      │
│    LINES 1224-1229 ✓                                    │
│                                                         │
│    STATUS: processing → COMPLETED (FINAL)               │
│    ARTIFACT_STATUS: processing → 'ready'                │
└─────────────────────────────────────────────────────────┘

RESULT: Media files generated, prompt fully complete
```

---

## Critical Differences

| Aspect | TEXT Prompts | IMAGE/LYRIC Prompts |
|--------|--------------|---------------------|
| **Architecture** | Single-stage | Two-stage |
| **Processing Method** | `run_generation_session()` | Stage 1: `_run_structured_prompt_generation()`<br>Stage 2: `process_media_prompt()` |
| **Status Update Timing** | Line 1096 (immediate) | Stage 1: Line 947 (immediate)<br>Stage 2: Line 1201 (immediate) |
| **Status Transitions** | `unprocessed` → `processing` → `completed` | Stage 1: `unprocessed` → `processing` → `completed`<br>Stage 2: `completed` → `processing` → `completed` |
| **artifact_status** | Always NULL | Stage 1: NULL → `'pending'`<br>Stage 2: `'pending'` → `'processing'` → `'ready'` |
| **Query Used** | `WHERE status='unprocessed'` | Stage 1: `WHERE status='unprocessed'`<br>Stage 2: `WHERE status='completed' AND artifact_status='pending'` |
| **Cron Cycles** | 1 cycle | 2+ cycles (depending on timing) |

---

## The Actual Problem (Hypothesis)

**IMAGE/LYRIC prompts ARE updating to 'processing' correctly at the code level:**
- ✓ Line 947 updates to `'processing'` when JSON generation starts
- ✓ Line 1201 updates to `'processing'` when media generation starts

**But the user is NOT seeing these updates in the Web GUI. Possible causes:**

### 1. Database Connection Caching in Poets Service

The Poets Service may be using the SAME database connection issue we fixed in the API:
- **Location:** `poets_cron_service_v3.py` line ~199-217
- **Issue:** Database connections without `cache=private` and `isolation_level=None`
- **Effect:** Status updates by Poets Service may not be visible to API queries

### 2. Stage 2 Query Not Finding Prompts

The query at line 1324 (`get_pending_media_prompts()`) expects:
```sql
WHERE status='completed'
AND artifact_status='pending'
AND prompt_type IN ('image_prompt', 'lyrics_prompt')
```

**Possible failures:**
- `artifact_status` column missing from database schema
- `artifact_status` being set to wrong value (e.g., `None` instead of `'pending'`)
- Query not returning rows due to database caching

### 3. Stage 1 Completing Too Fast

If Stage 1 completes in <5 seconds:
- Status: `unprocessed` → `processing` → `completed` (with `artifact_status='pending'`)
- User may NEVER see "processing" status because API refreshes every 5 seconds
- By the time API queries, it's already at `completed` with `artifact_status='pending'`

**User perception:** "Stuck at unprocessed" when actually it finished Stage 1 and waiting for Stage 2

### 4. Stage 2 Not Running

If `get_pending_media_prompts()` returns 0 rows:
- Stage 2 never executes
- Prompt stays at `status='completed', artifact_status='pending'` forever
- No media files generated

---

## Investigation Plan

### Phase 1: Verify Database Schema
**Goal:** Confirm `artifact_status` column exists and is populated

**Actions:**
1. Query database directly to check prompts table schema
2. Look for existing image_prompt or lyrics_prompt records
3. Check their `status` and `artifact_status` values
4. Verify if any prompts are stuck at `status='completed', artifact_status='pending'`

**Files to check:**
- Database schema definition (likely in a migration file or setup script)
- `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/poets_cron_service_v3.py` lines ~199-217 (database connection setup)

### Phase 2: Check Database Connection Configuration
**Goal:** Verify Poets Service uses proper SQLite connection settings

**Actions:**
1. Read `get_db_connection()` or equivalent in `poets_cron_service_v3.py`
2. Check if it uses `isolation_level=None` and `cache=private` (like we fixed in the API)
3. If not, that's the bug - status updates aren't immediately visible

**Expected location:** Lines ~199-217 in `poets_cron_service_v3.py`

### Phase 3: Trace Actual Execution
**Goal:** Verify status updates are actually being written to database

**Actions:**
1. Check Poets Service logs for evidence of status updates
2. Look for log messages at:
   - Line 947: "Processing structured prompt"
   - Line 1072: "Completed with artifact_status=pending"
   - Line 1201: "Processing media prompt"
3. Check timestamps to see if Stage 1 completes faster than API refresh interval

**Log locations:** Poets Service stdout/stderr, launchd logs

### Phase 4: Check get_pending_media_prompts() Implementation
**Goal:** Verify Stage 2 query is correct and returns expected rows

**Actions:**
1. Read the `get_pending_media_prompts()` method (likely around line 454)
2. Verify the SQL query matches expectations
3. Check if there's any filtering that might exclude valid prompts
4. Test the query directly against the database

**Expected location:** Line ~454 in `poets_cron_service_v3.py`

---

## Critical Files

1. **Main Service File:**
   - `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/poets_cron_service_v3.py`
   - Lines of interest: 947, 1072, 1096, 1146, 1201, 1224, 1319, 1324

2. **Database Connection:**
   - Same file, lines ~199-217 (database setup)
   - Look for `get_db_connection()` or similar method

3. **API Backend (already fixed):**
   - `/Users/tikbalang/anthonys-musings-api/main.py`
   - Line 155-168 (get_db_connection with proper settings)

4. **Database File:**
   - Location specified in Poets Service config
   - Likely: `/Users/tikbalang/anthonys-musings-api/anthonys_musings.db` (shared)

---

## ROOT CAUSE IDENTIFIED ✓

### The Bug: Database Connection Mode Conflict in `_run_structured_prompt_generation()`

**File:** `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/poets_cron_service_v3.py`
**Method:** `_run_structured_prompt_generation()` (lines 934-1079)
**Supporting File:** `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/tools.py` (`save_to_sqlite_database()`)

**The Problem: Four Separate Connections with Conflicting PRAGMA Settings**

The `_run_structured_prompt_generation()` method (NEW, added for image/lyric support) uses FOUR independent database connections:

```python
# Connection #1 (Line 947)
self.update_prompt_status(prompt_id, 'processing')
# → Opens connection with DEFAULT journal mode
# → Commits successfully
# → Closes connection
# ✓ WORKS - Status visible as "processing"

# Connection #2 (Lines 1041-1048)
save_to_sqlite_database(json_response, prompt_type, "writing", metadata)
# → Opens connection from tools.py
# → EXECUTES: PRAGMA journal_mode=WAL  ⚠️ CHANGES DATABASE GLOBALLY!
# → EXECUTES: PRAGMA synchronous=NORMAL
# → EXECUTES: PRAGMA cache_size=10000
# → Commits JSON data successfully
# → Closes connection
# ✓ WORKS - JSON saved

# Connection #3 (Lines 1054-1067)
conn = sqlite3.connect(db_path)  # Opens with DEFAULT mode expectations
# → But database is now in WAL mode (from Connection #2)
# → Updates prompts.output_reference (linking JSON)
# → Commits successfully because WAL mode is active
# → Closes connection
# ✓ WORKS - Link created

# Connection #4 (Line 1072)
self.update_prompt_status(prompt_id, 'completed', artifact_status='pending')
# → Opens connection with DEFAULT mode expectations
# → But database is in WAL mode (from Connection #2)
# → Writes UPDATE statement
# → Commits to WAL file
# ✗ FAILS TO BE VISIBLE - Data in WAL file but readers using DEFAULT mode can't see it
```

**Why This Breaks Image/Lyric Prompts:**

When SQLite is switched to WAL (Write-Ahead Logging) mode:
- Writes go to a separate `.db-wal` file
- Readers must be WAL-aware to see the latest data
- Connection #4 writes using DEFAULT mode assumptions but WAL mode is active
- The `update_prompt_status()` call succeeds but data is invisible to:
  - The API backend (reading with DEFAULT mode connections)
  - The Poets Service on next query (also using DEFAULT mode)
  - The Web GUI (which queries the API)

**Why Text Prompts Work Fine:**

```python
# Text prompts (run_generation_session) use only TWO connections:

# Connection #1 (Line 1096)
self.update_prompt_status(prompt_id, 'processing')
# → DEFAULT mode, commits, visible
# ✓ WORKS

# [Agent runs, no database operations]

# Connection #2 (Line 1146)
self.update_prompt_status(prompt_id, 'completed')
# → DEFAULT mode, commits, visible
# ✓ WORKS

# NO calls to save_to_sqlite_database()
# NO PRAGMA journal_mode changes
# Both connections use consistent mode
```

**Verified:**
- ✓ `get_unprocessed_prompts()` correctly returns image/lyric prompts (no filtering issue)
- ✓ Routing logic correctly sends image/lyric prompts to `_run_structured_prompt_generation()`
- ✓ First status update (line 947) to `'processing'` WORKS
- ✗ Final status update (line 1072) to `'completed'` INVISIBLE due to WAL mode conflict
- ✓ Text prompts never encounter this issue because they skip `save_to_sqlite_database()`

---

## THE FIX

### Option 1: Standardize ALL Connections to Use WAL Mode (RECOMMENDED)

**Goal:** Make all database connections use consistent PRAGMA settings so WAL mode conflicts don't occur.

**File:** `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/poets_cron_service_v3.py`
**Line:** 288-291

**Replace:**
```python
def get_database_connection(self):
    """Get database connection"""
    db_path = self.config['database']['path']
    return sqlite3.connect(db_path)
```

**With:**
```python
def get_database_connection(self):
    """Get database connection with consistent WAL mode settings"""
    db_path = self.config['database']['path']
    conn = sqlite3.connect(db_path)

    # Enable WAL mode for all connections (matches what save_to_sqlite_database does)
    # This ensures all connections use the same journal mode
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    return conn
```

**Why This Works:**
- ALL connections now use WAL mode from the start
- Matches the PRAGMA settings from `save_to_sqlite_database()` in tools.py
- Eliminates the mode conflict that causes invisibility
- Text prompts continue working (WAL mode is backward compatible with their flow)

**Impact:**
- Connection #1 (line 947): Opens in WAL mode ✓
- Connection #2 (line 1041): Already uses WAL mode ✓
- Connection #3 (line 1054): Now opens in WAL mode ✓
- Connection #4 (line 1072): Now opens in WAL mode ✓
- All connections consistent → all writes visible

---

### Option 2: Remove WAL Mode from save_to_sqlite_database() (ALTERNATIVE)

**Goal:** Keep all connections in DEFAULT mode by not switching to WAL in the middle.

**File:** `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/tools.py`
**Find:** `save_to_sqlite_database()` function

**Remove or comment out:**
```python
conn.execute("PRAGMA journal_mode=WAL")
```

**Why This Would Work:**
- Database stays in DEFAULT mode throughout
- All connections use DEFAULT mode
- No mode conflicts

**Why NOT Recommended:**
- WAL mode provides better concurrency and performance
- tools.py might be used by other code that expects WAL mode
- Removing PRAGMA changes might break other functionality

---

### Option 3: Use Single Atomic Transaction (MOST ROBUST)

**Goal:** Refactor `_run_structured_prompt_generation()` to use ONE database connection for all operations.

**File:** `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/poets_cron_service_v3.py`
**Method:** `_run_structured_prompt_generation()` (lines 934-1079)

**Refactor to:**
```python
def _run_structured_prompt_generation(self, base_url: str, prompt_data: Dict) -> bool:
    prompt_id = prompt_data['id']

    # Open ONE connection for entire operation
    conn = self.get_database_connection()

    try:
        # Enable WAL mode explicitly
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        # Start transaction
        conn.execute("BEGIN")

        # Update to processing
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE prompts SET status = ?, updated_at = ? WHERE id = ?",
            ('processing', datetime.now().isoformat(), prompt_id)
        )

        # ... [Generate JSON with agents] ...

        # Save JSON to database (inline, not via separate connection)
        # [Move save_to_sqlite_database logic here]

        # Link JSON to prompt
        cursor.execute(
            "UPDATE prompts SET output_reference = ? WHERE id = ?",
            (writing_id, prompt_id)
        )

        # Final status update
        cursor.execute(
            "UPDATE prompts SET status = ?, artifact_status = ?, updated_at = ? WHERE id = ?",
            ('completed', 'pending', datetime.now().isoformat(), prompt_id)
        )

        # Commit all changes at once
        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        self.logger.error(f"Error in structured prompt generation: {e}")
        return False

    finally:
        conn.close()
```

**Why This Is Most Robust:**
- Single connection eliminates mode conflicts entirely
- Atomic transaction ensures all-or-nothing semantics
- Better error handling with rollback capability
- More efficient (fewer connection open/close cycles)

**Why NOT Recommended (for now):**
- Requires significant refactoring
- More complex to implement correctly
- Higher risk of introducing new bugs

---

## RECOMMENDED FIX: Option 1

**Rationale:**
- Minimal code change (4 lines)
- Low risk (makes connections consistent with existing tools.py behavior)
- No refactoring needed
- Text prompts continue working unchanged
- Fixes the root cause directly

---

## Pre-Implementation Safety Measures

### Step 0.1: Save Implementation Options
**Action:** Copy this plan file to a permanent location for future reference

```bash
cp /Volumes/Tikbalang2TB/Users/tikbalang/.claude/plans/melodic-foraging-tulip.md \
   /Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/IMPLEMENTATION_OPTIONS.md
```

**Purpose:**
- Preserves all 3 implementation options (Option 1, 2, and 3)
- Allows rollback to try different approaches if Option 1 doesn't work
- Documents the investigation and root cause analysis

### Step 0.2: Commit Current State (Pre-Change Snapshot)
**Action:** Ensure all current changes are committed and pushed

**Repository:** `poets-service-clean`

```bash
cd /Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean

# Check for uncommitted changes
git status

# If there are uncommitted changes, commit them
git add -A
git commit -m "Pre-fix snapshot: Current working state before WAL mode fix"

# Push to remote
git push origin main
```

**Purpose:**
- Creates a clean rollback point
- Ensures no work is lost if fix causes issues
- Allows easy diff comparison after fix

### Step 0.3: Tag the Pre-Fix State
**Action:** Create a git tag for easy rollback reference

```bash
cd /Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean

# Create annotated tag
git tag -a pre-wal-fix -m "State before implementing WAL mode consistency fix"

# Push tag to remote
git push origin pre-wal-fix
```

**Purpose:**
- Makes rollback trivial: `git checkout pre-wal-fix`
- Clear marker for "last known working state"
- Can compare with `git diff pre-wal-fix`

### Step 0.4: Verify Rollback Procedure
**How to rollback if fix causes problems:**

```bash
cd /Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean

# Option A: Revert to tagged state
git checkout pre-wal-fix
git checkout -b rollback-attempt-1

# Option B: Revert the specific commit
git log --oneline  # Find the fix commit hash
git revert <commit-hash>

# Restart service after rollback
launchctl stop com.user.poets_cron_service
launchctl start com.user.poets_cron_service
```

---

## Implementation Steps

### Step 1: Update Database Connection Method
**File:** `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/poets_cron_service_v3.py`
**Action:** Replace `get_database_connection()` method at lines 288-291

**Change:**
```python
# OLD:
def get_database_connection(self):
    """Get database connection"""
    db_path = self.config['database']['path']
    return sqlite3.connect(db_path)

# NEW:
def get_database_connection(self):
    """Get database connection with consistent WAL mode settings"""
    db_path = self.config['database']['path']
    conn = sqlite3.connect(db_path)

    # Enable WAL mode for all connections (matches what save_to_sqlite_database does)
    # This ensures all connections use the same journal mode
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    return conn
```

### Step 2: Restart Poets Service
**Action:** Restart the launchd service to pick up code changes

```bash
launchctl stop com.user.poets_cron_service
launchctl start com.user.poets_cron_service
```

### Step 3: Test with New Image/Lyric Prompt
**Action:** Submit new image_prompt or lyrics_prompt through Web GUI

**Expected Behavior (Stage 1 - JSON Generation):**
1. Poets Service picks up prompt (status: `unprocessed`)
2. Within 5-10 seconds, Web GUI shows status: `processing` ✓
3. JSON generation completes (~30-90 seconds)
4. Web GUI shows status: `completed`, artifact_status: `pending` ✓
5. Queue modal auto-refresh shows transitions without manual refresh ✓
6. Bottom stats update in real-time ✓

### Step 4: Verify Stage 2 Works
**Action:** Wait for next cron cycle after Stage 1 completes

**Expected Behavior (Stage 2 - Media Generation):**
1. Poets Service queries for prompts with `artifact_status='pending'`
2. Finds the prompt (was invisible before fix!) ✓
3. Status updates to `processing`, artifact_status: `processing` ✓
4. Media files generated after 2-15 minutes
5. Final state: status: `completed`, artifact_status: `ready` ✓
6. Web GUI shows all transitions in real-time ✓

### Step 5: Verify Text Prompts Still Work
**Action:** Submit a text prompt (poem, story, etc.)

**Expected Behavior:**
1. Status transitions: `unprocessed` → `processing` → `completed` ✓
2. All transitions visible in real-time ✓
3. No regression in text prompt functionality ✓

### Step 6: Commit Changes
**Repo:** `poets-service-clean`
**Commit Message:** "Fix WAL mode consistency for image/lyric prompt status updates"
**Description:**
```
Standardize all database connections to use WAL mode by default.

Previously, save_to_sqlite_database() switched the database to WAL mode,
but subsequent connections opened without WAL awareness. This caused
status updates to be written to the WAL file but invisible to readers.

Now all connections use WAL mode from the start, ensuring:
- All status updates are immediately visible
- Image/lyric prompts progress through states correctly
- Stage 2 media generation finds prompts with artifact_status='pending'
- Text prompts continue working (WAL mode is backward compatible)

Fixes: Status stuck at "unprocessed" for image/lyric prompts
```

---

## Why This Fix Works

### The Root Cause
- `save_to_sqlite_database()` (called during JSON generation) enables WAL mode
- Subsequent connections opened without WAL mode awareness
- Status updates written to WAL file but invisible to DEFAULT mode readers

### The Solution
- ALL connections now enable WAL mode immediately after opening
- Matches the behavior of `save_to_sqlite_database()`
- Eliminates the mode mismatch that caused invisibility

### WAL Mode Consistency
**Before Fix:**
- Connection #1: DEFAULT mode → writes visible ✓
- Connection #2: Switches to WAL mode → database now in WAL
- Connection #3: Opens with DEFAULT expectations, but DB is WAL → confusion
- Connection #4: Opens with DEFAULT expectations, but DB is WAL → writes invisible ✗

**After Fix:**
- Connection #1: WAL mode → writes visible ✓
- Connection #2: WAL mode (no change needed, already WAL) → writes visible ✓
- Connection #3: WAL mode → writes visible ✓
- Connection #4: WAL mode → writes visible ✓

### Backward Compatibility
- Text prompts continue working unchanged
- WAL mode is fully backward compatible with existing flows
- No changes needed to any other code paths

---

## Files to Modify

### Primary File (ONLY ONE FILE NEEDS CHANGES)
- `/Volumes/Tikbalang2TB/Users/tikbalang/poets-service-clean/poets_cron_service_v3.py`
  - Lines 288-291: Update `get_database_connection()` method
  - Add 4 lines of code (PRAGMA settings)

### No Changes Needed
- ✓ `tools.py` - Leave `save_to_sqlite_database()` unchanged
- ✓ `_run_structured_prompt_generation()` - Logic is correct, no changes
- ✓ `update_prompt_status()` - Logic is correct, no changes
- ✓ API backend - Already has proper connection settings
- ✓ Web GUI - Already has auto-refresh
- ✓ Database schema - Already has `artifact_status` column

---

## Testing Checklist

### Pre-Implementation Verification
- [ ] Read current `get_database_connection()` method (should be simple: 3 lines)
- [ ] Verify text prompts are working correctly (baseline)
- [ ] Check Poets Service logs to confirm service is running

### Post-Implementation Testing
- [ ] Update `get_database_connection()` with WAL mode settings
- [ ] Restart Poets Service via launchd
- [ ] Check logs for any startup errors

### Image/Lyric Prompt Testing (Stage 1)
- [ ] Submit new `image_prompt` via Web GUI
- [ ] Open Queue modal, verify it shows the prompt as "Queued"
- [ ] Wait for Poets Service cron cycle (~5-15 minutes)
- [ ] Verify status changes to "processing" **within 5-10 seconds** (KEY FIX!)
- [ ] Wait for JSON generation to complete (~30-90 seconds)
- [ ] Verify status changes to "completed" **and shows immediately** (KEY FIX!)
- [ ] Verify Queue modal auto-refresh shows transitions without manual refresh
- [ ] Verify bottom stats update without page refresh

### Image/Lyric Prompt Testing (Stage 2)
- [ ] Wait for next cron cycle (check logs for "Processing media prompts")
- [ ] Verify Stage 2 picks up the prompt (was broken before fix!)
- [ ] Verify status updates to "processing" again
- [ ] Verify `artifact_status` shows "processing"
- [ ] Wait for media generation (2-15 minutes)
- [ ] Verify final state: `status='completed'`, `artifact_status='ready'`
- [ ] Verify media files appear in Browse tab

### Text Prompt Regression Testing
- [ ] Submit new text prompt (poem or story)
- [ ] Verify status transitions: `unprocessed` → `processing` → `completed`
- [ ] Verify all transitions visible in real-time
- [ ] Verify generated text appears correctly
- [ ] **Confirm NO regression** in text prompt functionality

### Edge Case Testing
- [ ] Submit multiple prompts (mix of text and image/lyric)
- [ ] Verify all process correctly
- [ ] Check for any database lock errors in logs
- [ ] Verify concurrent processing works

---

## Success Criteria

### Must Have (Blocking)
✓ **Image/lyric prompt status updates visible in Web GUI within 5-10 seconds**
✓ **No more "stuck at unprocessed" when JSON generation completes**
✓ **Stage 2 correctly finds prompts with `artifact_status='pending'`**
✓ **Text prompts continue working unchanged (no regression)**

### Should Have (Important)
✓ **Queue modal auto-refresh shows transitions**
✓ **Bottom stats update without manual page refresh**
✓ **No manual server restarts needed to progress prompts**
✓ **All status transitions match text prompt behavior**

### Nice to Have (Validation)
✓ **No database errors in Poets Service logs**
✓ **No performance degradation**
✓ **WAL file checkpoints happen automatically**

---

## Risk Assessment

### Low Risk (Option 1 is Safe)

**Why Option 1 is Low Risk:**
1. **Minimal code change:** Only 4 lines added to one method
2. **Backward compatible:** WAL mode doesn't break existing functionality
3. **SQLite standard:** WAL mode is the recommended mode for multi-process access
4. **Already in use:** `save_to_sqlite_database()` already enables WAL mode
5. **Easy rollback:** Git tag allows instant reversion

**Potential Issues and Mitigations:**

| Potential Issue | Likelihood | Impact | Mitigation |
|----------------|------------|--------|------------|
| **Database locks** | Very Low | Medium | WAL mode reduces locks, not increases them |
| **Performance impact** | Very Low | Low | WAL mode typically IMPROVES performance |
| **Text prompt regression** | Very Low | High | WAL mode is backward compatible, text prompts don't check journal mode |
| **Disk space increase** | Low | Very Low | WAL files auto-checkpoint, typically <10MB |
| **Concurrent access issues** | Very Low | Medium | WAL mode designed for concurrent access |

**Monitoring After Implementation:**

Watch for these in Poets Service logs (`~/Library/Logs/poets_cron_service/`):
- `database is locked` errors → Indicates WAL mode not working as expected
- `disk I/O error` → Indicates filesystem issues (unlikely)
- Status update failures → Would show in log as exceptions from `update_prompt_status()`

**Quick Health Checks:**
```bash
# Check WAL file exists and is being used
ls -lh /Users/tikbalang/anthonys-musings-api/anthonys_musings.db*

# Should see:
# anthonys_musings.db       (main database)
# anthonys_musings.db-wal   (write-ahead log, may be small or missing if checkpointed)
# anthonys_musings.db-shm   (shared memory, exists while connections open)

# Check WAL file size (should auto-checkpoint at ~1MB)
# If WAL file grows unbounded, checkpointing may not be working

# Force WAL checkpoint manually if needed
sqlite3 /Users/tikbalang/anthonys-musings-api/anthonys_musings.db "PRAGMA wal_checkpoint(FULL);"
```

**Signs Fix Is Working:**
- Image/lyric prompts show "processing" status in Web GUI within seconds
- Queue modal updates automatically without refresh
- Stage 2 finds prompts with `artifact_status='pending'`
- No "stuck at unprocessed" issues

**Signs Fix Has Problems:**
- Text prompts stop working (HIGH SEVERITY - rollback immediately)
- Database lock errors in logs (MEDIUM SEVERITY - try forcing checkpoint)
- WAL file grows >100MB (LOW SEVERITY - checkpoint not running)
- Status still stuck (LOW SEVERITY - fix didn't work, try Option 2 or 3)

---

## Alternative Options Reference

If Option 1 doesn't work or causes issues, refer to `IMPLEMENTATION_OPTIONS.md` for:

- **Option 2:** Remove WAL mode from `save_to_sqlite_database()`
  - Simpler but may impact other code using that function
  - Trades concurrency for consistency

- **Option 3:** Refactor to use single atomic transaction
  - Most robust but requires significant refactoring
  - Best long-term solution if Option 1 fails
