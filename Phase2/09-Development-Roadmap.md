# Development Roadmap

## Overview

This roadmap breaks Phase 2 implementation into 5 milestones, each representing approximately 2-3 hours of focused development.

**Total Estimated Time**: 10-15 hours

**Recommended Approach**: Complete milestones sequentially, testing thoroughly after each.

---

## Milestone 1: Project Setup and Data Layer

**Goal**: Establish project structure, implement data models and database repositories

**Duration**: 2-3 hours

### Tasks

#### 1.1 Create Project Structure

- [ ] Create `media_generator/` directory
- [ ] Create `__init__.py` in media_generator/
- [ ] Create placeholder files:
  - `main.py`
  - `app.py`
  - `models.py`
  - `repositories.py`
  - `executors.py`
  - `config.py`
- [ ] Create `media_generator_config.json` with initial configuration

**Files to Create**:
```bash
mkdir -p media_generator
touch media_generator/__init__.py
touch media_generator/{main.py,app.py,models.py,repositories.py,executors.py,config.py}
touch media_generator/media_generator_config.json
```

#### 1.2 Implement Data Models

**File**: `media_generator/models.py`

- [ ] Import required libraries (dataclasses, typing, json, datetime)
- [ ] Implement `PromptRecord` dataclass
  - All fields from database schema
  - `is_pending` property
  - `get_json_prompt()` method
- [ ] Implement `ImagePromptData` dataclass
  - All image prompt fields
  - `from_json()` classmethod
- [ ] Implement `LyricsPromptData` dataclass
  - All lyrics prompt fields
  - `from_json()` classmethod
  - `get_full_lyrics()` method
- [ ] Implement `ArtifactRecord` dataclass

**Reference**: [03-Data-Models.md](03-Data-Models.md)

#### 1.3 Implement Database Repositories

**File**: `media_generator/repositories.py`

- [ ] Import required libraries (sqlite3, typing, datetime)
- [ ] Import data models
- [ ] Implement `PromptRepository` class
  - `__init__(db_path)` constructor
  - `get_connection()` method
  - `get_pending_image_prompts(limit)` method
  - `get_pending_lyrics_prompts(limit)` method
  - `update_artifact_status(prompt_id, status, error)` method
- [ ] Implement `ArtifactRepository` class
  - `__init__(db_path)` constructor
  - `get_connection()` method
  - `save_artifact(artifact)` method
  - `get_artifacts_for_prompt(prompt_id)` method

**Reference**: [02-Database-Interface.md](02-Database-Interface.md)

#### 1.4 Implement Configuration Loader

**File**: `media_generator/config.py`

- [ ] Implement `load_config(path)` function
- [ ] Implement `validate_config(config)` function
- [ ] Add error handling for missing files
- [ ] Add validation for required fields

**File**: `media_generator/media_generator_config.json`

- [ ] Add database section with path
- [ ] Add comfyui section with all settings
- [ ] Add media section with workflow script paths
- [ ] Add ui section with window settings

**Reference**: [06-Configuration.md](06-Configuration.md)

#### 1.5 Write Unit Tests

**File**: `media_generator/test_models.py` (optional but recommended)

- [ ] Test PromptRecord JSON parsing
- [ ] Test ImagePromptData.from_json()
- [ ] Test LyricsPromptData.from_json()
- [ ] Test LyricsPromptData.get_full_lyrics()

**File**: `media_generator/test_repositories.py` (optional)

- [ ] Test database connection
- [ ] Test get_pending_image_prompts() with test database
- [ ] Test update_artifact_status()

### Testing Milestone 1

```bash
# Test configuration loading
cd media_generator
python3 -c "from config import load_config; print(load_config('media_generator_config.json'))"

# Test database connection
python3 -c "from repositories import PromptRepository; repo = PromptRepository('/Volumes/Tikbalang2TB/Users/tikbalang/Desktop/anthonys_musings.db'); print(repo.get_pending_image_prompts(limit=5))"
```

**Expected Result**: No errors, prints list of pending prompts

---

## Milestone 2: Tkinter UI Implementation

**Goal**: Build complete user interface with all panels and controls

**Duration**: 3-4 hours

### Tasks

#### 2.1 Create Main Application Window

**File**: `media_generator/app.py`

- [ ] Import tkinter libraries (tk, ttk, scrolledtext, messagebox)
- [ ] Import models, repositories, config
- [ ] Implement `MediaGeneratorApp` class
  - `__init__(config)` constructor
  - Initialize repositories
  - Initialize state variables (selected_image_prompt, selected_lyrics_prompt)
  - Set window title and geometry
  - Call `create_widgets()`
  - Call `setup_menu_bar()`
- [ ] Implement `run()` method to start mainloop

#### 2.2 Implement Top Panel (Lists)

- [ ] Create PanedWindow for vertical split
- [ ] Create top frame for horizontal split
- [ ] Implement left panel: Image Prompts
  - Create LabelFrame
  - Create Treeview with columns (id, created, preview)
  - Configure column widths
  - Add scrollbar
  - Bind selection event to `on_image_select()`
- [ ] Implement right panel: Lyrics Prompts
  - Create LabelFrame
  - Create Treeview with columns (id, created, title)
  - Configure column widths
  - Add scrollbar
  - Bind selection event to `on_lyrics_select()`

#### 2.3 Implement Details Panel

- [ ] Create LabelFrame for details
- [ ] Create ScrolledText widget
- [ ] Configure font (Courier, 10)
- [ ] Set wrap mode (tk.WORD)

#### 2.4 Implement Control Panel

- [ ] Create frame for control buttons
- [ ] Add "Generate Selected" button → `generate_selected()`
- [ ] Add "Generate All Pending" button → `generate_all_pending()`
- [ ] Add "Refresh Lists" button → `refresh_all_lists()`
- [ ] Add "View Output Folder" button → `open_output_folder()`

#### 2.5 Implement Status Bar

- [ ] Create status label at bottom
- [ ] Configure relief (SUNKEN) and anchor (W)

#### 2.6 Implement Menu Bar

- [ ] Create menubar
- [ ] Add File menu
  - Refresh
  - View Output Folder
  - Separator
  - Exit
- [ ] Add Tools menu
  - Generate All Pending
  - Clear Error Messages
- [ ] Add Help menu
  - About

#### 2.7 Implement Event Handlers

- [ ] `refresh_all_lists()` - Reload both lists
- [ ] `refresh_image_list()` - Query and populate image treeview
- [ ] `refresh_lyrics_list()` - Query and populate lyrics treeview
- [ ] `on_image_select(event)` - Handle image selection
- [ ] `on_lyrics_select(event)` - Handle lyrics selection
- [ ] `display_prompt_details(prompt)` - Show JSON in details panel
- [ ] `update_status_bar()` - Update status text with counts
- [ ] `open_output_folder()` - Open file explorer

**Reference**: [04-Tkinter-UI-Design.md](04-Tkinter-UI-Design.md)

#### 2.8 Implement Main Entry Point

**File**: `media_generator/main.py`

- [ ] Import sys, config, app modules
- [ ] Implement `main()` function
  - Load configuration
  - Validate configuration
  - Create MediaGeneratorApp instance
  - Run app
- [ ] Add `if __name__ == '__main__':` block

### Testing Milestone 2

```bash
cd media_generator
python3 main.py
```

**Expected Behavior**:
- Window opens with title "Media Generator - Pending Prompts"
- Two list panels show pending prompts
- Details panel is empty until selection
- All buttons are visible and clickable
- Status bar shows prompt counts
- Selecting a prompt shows JSON details

**Test Cases**:
- [ ] Window opens without errors
- [ ] Image prompts list populated (should show IDs 197, 199, 200)
- [ ] Lyrics prompts list populated (should show ID 198)
- [ ] Clicking on image prompt shows JSON details
- [ ] Clicking on lyrics prompt shows JSON details
- [ ] Status bar updates with correct counts
- [ ] Refresh button reloads lists

---

## Milestone 3: ComfyUI Workflow Integration

**Goal**: Implement workflow executors to generate actual media

**Duration**: 2-3 hours

### Tasks

#### 3.1 Implement Base Executor

**File**: `media_generator/executors.py`

- [ ] Import subprocess, json, pathlib, typing, datetime
- [ ] Import data models
- [ ] Implement `ComfyUIWorkflowExecutor` base class
  - `__init__(config)` constructor
  - Store python_executable, comfyui_directory, output_root, timeout
  - `_create_output_directory(prompt_id, artifact_type)` method
  - `_get_relative_path(full_path)` method

#### 3.2 Implement Image Workflow Executor

- [ ] Implement `ImageWorkflowExecutor` class (extends base)
  - `__init__(config)` constructor
  - Store workflow_script path
  - `generate(prompt, json_data, progress_callback)` method
    1. Create output directory
    2. Build command arguments
    3. Call progress_callback with status
    4. Execute subprocess
    5. Check returncode
    6. Find generated PNG files
    7. Create ArtifactRecord for each file
    8. Return list of artifacts

**Reference**: [05-ComfyUI-Integration.md](05-ComfyUI-Integration.md)

#### 3.3 Implement Audio Workflow Executor

- [ ] Implement `AudioWorkflowExecutor` class (extends base)
  - `__init__(config)` constructor
  - Store workflow_script path
  - `generate(prompt, json_data, progress_callback)` method
    1. Create output directory
    2. Get full lyrics text
    3. Build command arguments
    4. Call progress_callback with status
    5. Execute subprocess
    6. Check returncode
    7. Find generated MP3 files
    8. Create ArtifactRecord for each file
    9. Return list of artifacts

#### 3.4 Add Error Handling

- [ ] Handle subprocess.TimeoutExpired
- [ ] Handle workflow script not found
- [ ] Handle ComfyUI errors from stderr
- [ ] Handle no output files generated

#### 3.5 Integrate with UI

**File**: `media_generator/app.py`

- [ ] Import executors
- [ ] Implement `generate_selected()` method
  - Check which prompt is selected
  - Call appropriate generation method
- [ ] Implement `generate_image_prompt(prompt)` method
  1. Update artifact_status to 'processing'
  2. Update status bar
  3. Parse JSON data using ImagePromptData.from_json()
  4. Create ImageWorkflowExecutor
  5. Call executor.generate() with progress callback
  6. Save artifacts to database
  7. Update artifact_status to 'ready'
  8. Update status bar
  9. Refresh image list
  10. Show success messagebox
  11. On error: Update artifact_status to 'error', show error messagebox
- [ ] Implement `generate_lyrics_prompt(prompt)` method (similar pattern)
- [ ] Implement `update_status(message)` method for progress callback

### Testing Milestone 3

**Prerequisites**:
- ComfyUI server must be running
- Workflow scripts must exist
- Pending prompts in database

**Test Case 1: Image Generation**
```bash
python3 main.py
# 1. Select an image prompt from the list
# 2. Click "Generate Selected"
# 3. Wait for generation (may take 1-2 minutes)
# 4. Check status messages in status bar
# 5. Verify success dialog appears
```

**Expected Results**:
- [ ] Status bar shows "Generating image for prompt #..."
- [ ] No errors or exceptions
- [ ] Success dialog appears
- [ ] Prompt disappears from pending list (artifact_status='ready')
- [ ] Files created in output/poets/image/{prompt_id}_{timestamp}/
- [ ] Database has artifact record with correct file_path

**Test Case 2: Audio Generation**
```bash
python3 main.py
# 1. Select a lyrics prompt from the list
# 2. Click "Generate Selected"
# 3. Wait for generation (may take 2-4 minutes)
# 4. Verify success dialog appears
```

**Expected Results**:
- [ ] Status bar shows "Generating audio for prompt #..."
- [ ] No errors or exceptions
- [ ] Success dialog appears
- [ ] Prompt disappears from pending list
- [ ] Files created in output/poets/audio/{prompt_id}_{timestamp}/
- [ ] Database has artifact record

---

## Milestone 4: End-to-End Integration Testing

**Goal**: Verify complete workflow from database to frontend

**Duration**: 2-3 hours

### Tasks

#### 4.1 Test Image Generation Workflow

- [ ] Use Poets Service to create new image_prompt
  ```sql
  INSERT INTO prompts (prompt_text, prompt_type, status, artifact_status)
  VALUES ('Create a cyberpunk cityscape at night', 'image_prompt', 'unprocessed', 'pending');
  ```
- [ ] Run Media Generator app
- [ ] Verify prompt appears in list
- [ ] Generate media
- [ ] Verify files created
- [ ] Check database artifact record
- [ ] Open frontend and verify image displays

#### 4.2 Test Lyrics Generation Workflow

- [ ] Use Poets Service to create new lyrics_prompt
  ```sql
  INSERT INTO prompts (prompt_text, prompt_type, status, artifact_status)
  VALUES ('Write a melancholic indie folk song about lost time', 'lyrics_prompt', 'unprocessed', 'pending');
  ```
- [ ] Run Media Generator app
- [ ] Verify prompt appears in list
- [ ] Generate media
- [ ] Verify files created
- [ ] Check database artifact record
- [ ] Open frontend and verify audio player works

#### 4.3 Test Error Scenarios

**Test Case: ComfyUI Not Running**
- [ ] Stop ComfyUI server
- [ ] Try to generate image
- [ ] Verify error message appears
- [ ] Verify artifact_status='error' in database
- [ ] Verify error_message populated

**Test Case: Invalid JSON**
- [ ] Manually insert malformed JSON in writings table
- [ ] Try to generate
- [ ] Verify graceful error handling

**Test Case: Timeout**
- [ ] Set very short timeout in config (e.g., 5 seconds)
- [ ] Try to generate
- [ ] Verify timeout error message

#### 4.4 Test Batch Processing

- [ ] Create multiple pending prompts (3-5)
- [ ] Implement batch processing logic
- [ ] Test "Generate All Pending" button
- [ ] Verify all prompts processed
- [ ] Verify progress updates

#### 4.5 Performance Testing

- [ ] Measure generation time for images (typical: 30-90 seconds)
- [ ] Measure generation time for audio (typical: 90-240 seconds)
- [ ] Test with larger prompts
- [ ] Monitor memory usage

### Testing Checklist

**Database Integration**:
- [ ] Can connect to database
- [ ] Can query pending prompts
- [ ] Can update artifact_status
- [ ] Can insert artifact records
- [ ] No database locks or timeouts

**ComfyUI Integration**:
- [ ] Workflow scripts execute successfully
- [ ] Output files created in correct location
- [ ] File paths stored correctly in database
- [ ] Errors handled gracefully

**Frontend Integration**:
- [ ] Frontend displays generated images
- [ ] Frontend audio player works
- [ ] Can view full-screen images
- [ ] Artifact metadata visible

**UI Functionality**:
- [ ] Lists refresh correctly
- [ ] Selection works properly
- [ ] Progress updates visible
- [ ] Error messages clear
- [ ] Status bar accurate

---

## Milestone 5: Polish and Documentation

**Goal**: Improve user experience, add logging, create user guide

**Duration**: 2-3 hours

### Tasks

#### 5.1 Add Logging

**File**: `media_generator/logger.py` (new)

- [ ] Implement logging configuration
- [ ] Log to file: `media_generator/logs/app.log`
- [ ] Log levels: DEBUG, INFO, WARNING, ERROR
- [ ] Add logging to all major operations

**Update Files**:
- [ ] Add logging to `app.py` (UI events, generation start/end)
- [ ] Add logging to `repositories.py` (database queries, updates)
- [ ] Add logging to `executors.py` (workflow execution, errors)

#### 5.2 Improve Error Messages

- [ ] Make error dialogs more user-friendly
- [ ] Add troubleshooting hints
- [ ] Include relevant details (prompt_id, error type)

#### 5.3 Add Keyboard Shortcuts

- [ ] Cmd+R / Ctrl+R: Refresh lists
- [ ] Cmd+G / Ctrl+G: Generate selected
- [ ] Cmd+O / Ctrl+O: Open output folder
- [ ] Cmd+Q / Ctrl+Q: Quit application

#### 5.4 Add Progress Indicators

- [ ] Show progress bar during generation
- [ ] Show spinner icon in status bar
- [ ] Disable buttons during generation
- [ ] Add "Cancel" option for long operations

#### 5.5 Improve UI Styling

- [ ] Apply ttk theme (clam or aqua)
- [ ] Configure treeview styling
- [ ] Add icons to buttons (optional)
- [ ] Improve spacing and padding

#### 5.6 Create User Documentation

**File**: `media_generator/README.md` (new)

- [ ] Installation instructions
- [ ] Configuration guide
- [ ] Usage instructions with screenshots
- [ ] Troubleshooting section
- [ ] FAQ

**File**: `media_generator/TROUBLESHOOTING.md` (new)

- [ ] Common errors and solutions
- [ ] Database issues
- [ ] ComfyUI integration issues
- [ ] File permission issues

#### 5.7 Add About Dialog

- [ ] Show application version
- [ ] Show configuration paths
- [ ] Show database status
- [ ] Show ComfyUI status

### Final Testing

- [ ] Test on clean environment
- [ ] Verify all features work
- [ ] Check all error scenarios
- [ ] Verify logging captures important events
- [ ] Test keyboard shortcuts
- [ ] Check UI on different screen sizes

---

## Post-Implementation Tasks

### Optional Enhancements

**Priority 2 Features**:
- [ ] Batch generation with queue management
- [ ] Retry failed generations
- [ ] Preview thumbnails in list
- [ ] Filter/search prompts
- [ ] Export generation logs
- [ ] Scheduled automatic generation

**Priority 3 Features**:
- [ ] Multi-threading for parallel generation
- [ ] Real-time progress from ComfyUI
- [ ] Custom workflow selection
- [ ] Prompt editing before generation
- [ ] Generation history view

### Deployment

- [ ] Package application (pyinstaller or similar)
- [ ] Create launcher script
- [ ] Set up as system service (optional)
- [ ] Document deployment process

### Maintenance

- [ ] Create backup script for database
- [ ] Monitor disk space for output directory
- [ ] Set up log rotation
- [ ] Document update procedure

---

## Timeline Summary

| Milestone | Duration | Cumulative | Deliverables |
|-----------|----------|------------|--------------|
| 1. Data Layer | 2-3 hours | 2-3 hours | Models, repositories, config |
| 2. Tkinter UI | 3-4 hours | 5-7 hours | Complete functional UI |
| 3. ComfyUI Integration | 2-3 hours | 7-10 hours | Working media generation |
| 4. Integration Testing | 2-3 hours | 9-13 hours | Verified end-to-end workflow |
| 5. Polish & Docs | 2-3 hours | 11-16 hours | Production-ready app |

**Total**: 11-16 hours of focused development

---

## Success Criteria

**Milestone 1 Complete When**:
- [ ] Can load configuration
- [ ] Can connect to database
- [ ] Can query pending prompts
- [ ] Data models parse JSON correctly

**Milestone 2 Complete When**:
- [ ] UI opens without errors
- [ ] Lists populate with pending prompts
- [ ] Selection shows details
- [ ] All buttons present and clickable

**Milestone 3 Complete When**:
- [ ] Can generate image from prompt
- [ ] Can generate audio from prompt
- [ ] Files saved to correct location
- [ ] Database updated correctly

**Milestone 4 Complete When**:
- [ ] End-to-end workflow verified
- [ ] Frontend displays artifacts
- [ ] Error scenarios handled
- [ ] Performance acceptable

**Milestone 5 Complete When**:
- [ ] Logging implemented
- [ ] User documentation complete
- [ ] UI polished
- [ ] Ready for production use

---

## Next Steps

See [10-Testing-Guide.md](10-Testing-Guide.md) for detailed testing procedures and SQL queries.
