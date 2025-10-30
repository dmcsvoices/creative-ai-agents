# Media Prompt Processing Integration Plan

## Overview
Integrate ComfyUI-powered media generation into the Anthony's Musings system so that `image` and `music` prompts created via the web interface are automatically processed by the LaunchAgent-driven poets service. The media outputs (images, audio) will be persisted, linked back to the originating prompt, and exposed to the web UI for user consumption.

---

## Current State Summary
- **Prompt Creation**: Web UI posts prompts to `/api/prompts` with `prompt_type` (`text`, `music`, `voice`, `image`) and metadata.
- **Data Storage**: API persists the prompt into the SQLite `prompts` table.
- **Queue Processing**: `poets_cron_service_v3.py --queue` processes `text`-style prompts by orchestrating AutoGen agents that generate textual content in the shared SQLite database.
- **Media Prompts**: Currently ingested into the queue, but skipped by the poets service (no downstream media generation).

---

## Goals
1. Detect `image`, `music`, and optionally `voice` prompts in the queue processor and hand them off to dedicated media pipelines.
2. Execute media workflows using scripts from [ComfyUI-SaveAsScript](https://github.com/atmaranto/ComfyUI-SaveAsScript).
3. Persist resulting artifact metadata (file paths, types, thumbnails, waveforms, etc.) in SQLite so the API and UI can surface them.
4. Update frontend queue views to display artifact links/previews when available.
5. Ensure LaunchAgent scheduling handles combined workloads safely with logging and failure reporting.

---

## High-Level Architecture Changes
1. **Repository Layout**
   - Add a `media/` folder under `poets-service-clean/` containing wrappers for image/audio processing.
   - Store the pre-exported SaveAsScript workflows under `poets-service-clean/media/` (manually maintained).
   - Add configuration entries in `poets_cron_config.json` for media workflows (ComfyUI host, script entry points, output directories).

2. **Database Schema Updates**
   - Create a new `prompt_artifacts` table with columns:
     - `id INTEGER PRIMARY KEY`
     - `prompt_id INTEGER REFERENCES prompts(id) ON DELETE CASCADE`
     - `artifact_type TEXT` (e.g. `image`, `audio`, `thumbnail`)
     - `file_path TEXT` (store paths relative to the configured media root)
     - `preview_path TEXT NULL`
     - `metadata TEXT NULL` (JSON: seeds, workflow names, durations, sample rate, etc.)
     - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
     - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
   - Optional prompt columns:
     - `artifact_status TEXT DEFAULT 'pending'`
     - `artifact_metadata TEXT NULL`
   - Extend API models (`PromptResponse`) to include `artifact_status` and artifact listings in serialized responses.

3. **Queue Processing Branching**
   - In `PoetsService.run_queue_processor`, filter prompts:
     ```python
     if prompt['prompt_type'] in ('image', 'music', 'voice'):
         self.logger.info("Routing prompt to media pipeline")
         self.process_media_prompt(prompt)
     else:
         self.run_generation_session(base_url, prompt)
     ```
   - Ensure `process_media_prompt` marks prompt status transitions (`processing`, `completed`, `failed`) and records errors.

4. **Media Pipeline Wrappers**
   - Create `media/image_pipeline.py`:
     - Accepts prompt data (text, metadata, prompt id).
     - Invokes the pre-exported SaveAsScript workflow (manually provided under `media/`) with the prompt text and configured output directory.
     - Calls ComfyUI server (configurable host/port) and waits for completion.
     - Captures generated file paths (images), optional thumbnails, seeds.
     - Returns structured metadata to the caller.
   - Create `media/audio_pipeline.py` for `music` prompts (if corresponding scripts are provided). Otherwise, plan a placeholder script so we can hook in later.
   - Use `subprocess.run(..., check=True, capture_output=True)` with timeout handling and detailed logging.

5. **Prompt Artifact Persistence**
   - Add helper in poets service: `record_prompt_artifacts(prompt_id, artifacts: List[dict])` to insert rows into `prompt_artifacts` and update prompt-level status metadata.
   - On success:
     - `status = 'completed'`
     - `artifact_status = 'ready'`
     - Save metadata summary (e.g. `{"count": 4, "primary": "/media/image_123.png"}`)
   - On failure:
     - `status = 'failed'`
     - `artifact_status = 'error'`
     - Populate `prompts.error_message` with stderr/log snippet.

6. **Configuration Enhancements**
   - Update `poets_cron_config.json`:
     ```json
     "media": {
       "enabled": true,
       "scripts": {
         "image": "media/image_workflow.py",
         "music": "media/music_workflow.py"
       },
       "comfyui": {
         "python": "/usr/bin/python3",
         "host": "http://127.0.0.1:8188",
         "output_directory": "GeneratedMedia"
       }
     }
     ```
   - Ensure directories exist or are created on startup.
   - Add config validation in `PoetsService.test_configuration()` to check ComfyUI connectivity when media is enabled; log a warning and disable media if the host is unreachable.

7. **Frontend Updates**
   - Modify queue modal rendering to show artifact chips or previews when `prompt.artifacts` is present.
     - For images: display thumbnail/preview using `<img>` tags pointing to served media (requires exposing media via API or static hosting route).
     - For audio: show file name and a play button (HTML5 audio player).
   - Provide error messaging if `artifact_status === 'error'`.
   - Optional: add a “refresh artifacts” button that re-fetches the prompt detail endpoint.

8. **API Adjustments**
   - Add `/api/prompts/{id}/artifacts` endpoint returning artifact metadata and signed/relative URLs.
   - Serve generated media files via FastAPI static file mount or presigned local file link (depending on deployment constraints). If not possible, store relative paths and let the frontend resolve them (e.g. by reverse proxy or direct file hosting).
   - Update `PromptResponse` schema to include `artifact_status` and `artifacts: List[ArtifactResponse]`.

9. **LaunchAgent / Control Script**
   - Retain single LaunchAgent invocation (`poets_cron_service_v3.py --queue`) but note in documentation that it now covers media prompts, which might take longer.
   - Add optional CLI flag `--media-only` to `PoetsService` to process only media prompts. Could be used if a separate schedule is desired.
   - Extend `control.sh` commands to surface new behavior (e.g. `./control.sh logs` should mention media operations in the log tail output).

10. **Logging & Monitoring**
    - Log ComfyUI command invocation, stdout, stderr, generated file paths, and durations.
    - Store subset of log data in prompt metadata for troubleshooting.
    - Consider rotating logs more aggressively due to potentially large output.

11. **Testing Strategy**
    - Add unit tests for `record_prompt_artifacts` using an in-memory SQLite DB.
    - Add integration tests (optional) for `process_media_prompt` with a mocked `subprocess.run` to avoid requiring ComfyUI during CI.
    - Provide manual testing checklist:
      1. Submit `image` prompt via web UI.
      2. Confirm prompt appears in queue with `prompt_type = 'image'`.
      3. Run `poets_cron_service_v3.py --queue`.
      4. Verify artifact records in DB and generated files in output directory.
      5. Load web UI queue modal and confirm preview/links.

---

## Implementation Steps (Detailed)

1. **Bootstrap Media Folder**
   - Create `poets-service-clean/media/__init__.py` (empty).
   - Add `image_pipeline.py` and `audio_pipeline.py` with stub classes/functions.
   - Define common utilities in `media/utils.py` (e.g., command runner, config loader, path helpers).

2. **Integrate Pre-Exported SaveAsScript Workflows**
   - Assume the "known good" scripts are dropped into `poets-service-clean/media/` manually.
   - Document expected script filenames and invocation patterns so the pipelines can call them deterministically.
   - Provide sample config values mapping prompt types to script entry points (e.g., Python module vs shell command).

3. **Config Updates**
   - Modify `poets_cron_config.json` to include the `media` block and default workflow references.
   - Update `PoetsService.__init__` to load `self.media_config = self.config.get('media', {})`.
   - Extend `test_configuration()` to validate the presence of workflow files and ability to reach ComfyUI host (HTTP GET to `/system_stats` or similar). If ComfyUI is unavailable, log a warning and disable media processing instead of failing the entire run.

4. **Database Migration Script**
   - Create `database_migration_v4.py` (or extend existing migration script) to add `prompt_artifacts` table and new columns.
   - Ensure migration handles existing prompts (default `artifact_status = 'pending'` for any non-text prompt).
   - Update documentation to run the migration before enabling media processing.

5. **API Model + Endpoint Adjustments**
   - Update `PromptResponse` pydantic model to include `artifact_status: Optional[str]` and `artifacts: List[ArtifactMeta] = []`.
   - Implement `ArtifactMeta` model with `id`, `artifact_type`, `file_path`, `preview_path`, `metadata`.
   - In `get_prompts` and `get_prompt`, join or follow-up query to fetch artifact rows.
   - Add new FastAPI endpoint `GET /api/prompts/{prompt_id}/artifacts` returning artifact list.
   - Optionally add `GET /api/artifacts/{artifact_id}` for direct download (or provide static mount).

6. **Queue Processor Changes**
   - Add method `process_media_prompt(self, prompt)` in `PoetsService`:
     - Update status to `processing` via `update_prompt_status`.
     - Determine which pipeline to use based on `prompt_type`.
     - Call pipeline wrapper, capturing artifacts list.
     - On success: call `record_prompt_artifacts`, update prompt status to `completed`, set `completed_at` + `processing_duration`.
     - On failure: update prompt status to `failed`, write `error_message`, rethrow/log.
   - Ensure we honor existing process lock and continue to next prompt even if one fails.

7. **Media Pipelines Implementation**
   - `image_pipeline.run(prompt, config)` should:
     1. Create temp working directory under configured output root.
     2. Build command (e.g. `config.python media/image_workflow.py --prompt PROMPT --output OUTPUT_DIR` or whatever entrypoint the script exposes).
     3. Execute command. On success, parse generated file list (if the script emits JSON use that; otherwise list the output directory).
     4. Create metadata dictionary containing seed, prompt text, workflow name, execution time.
     5. Return `[("image", file_path, preview_path, metadata_json), ...]`.
   - `audio_pipeline.run` mirrors the above but for audio artifacts (`artifact_type = 'audio'`), calling the corresponding script dropped into `media/`. If audio support is not yet provided, return `NotImplemented` and log a warning; keep architecture ready.

8. **Static File Serving / Storage**
   - Decide storage location (e.g. `poets-service-clean/GeneratedMedia`). Ensure path is mounted or otherwise accessible to web stack.
   - Options to expose files:
     - Serve via FastAPI `StaticFiles` (mount `/media` to `GeneratedMedia`).
     - Or integrate with existing Nginx container to serve from a bind-mounted directory.
   - Update Docker compose (if necessary) to mount `GeneratedMedia` for the API container.

9. **Frontend Enhancements**
   - Update queue modal to fetch artifact data (`fetch('/api/prompts/{id}/artifacts')`).
   - Render artifacts:
     ```javascript
     artifacts.filter(a => a.artifact_type === 'image').forEach(a => {
       const img = document.createElement('img');
       img.src = a.preview_url || a.file_url;
       // ... append to prompt item
     });
     ```
   - Add audio player for `audio` types.
   - Display artifact count badge next to prompt type (e.g., `image (4)`).

10. **Documentation & Control Script**
    - Update `poets-service-clean/README.md` with setup steps, config explanation, and troubleshooting for ComfyUI integration.
    - Update `control.sh` usage text noting that media prompts are now processed.
    - Provide instructions for installing ComfyUI, launching server, and verifying connectivity.

11. **Testing & Validation**
    - Write integration test script `tests/test_media_pipeline.py` verifying:
      - `process_media_prompt` handles success path with mocked pipeline returning artifacts.
      - Failure path updates prompt status and error message.
    - Manual QA checklist:
      - Submit prompts of each type.
      - Run queue processor.
      - Verify DB rows in `prompts` and `prompt_artifacts` via `sqlite3`.
      - Confirm generated files exist on disk.
      - Check web UI queue modal displays artifacts.
      - Ensure LaunchAgent logs show media processing steps.

---

## Rollout Strategy
1. **Local Development**: Implement pipelines with mocked ComfyUI responses. Run migrations, API/UI updates locally.
2. **Test Environment**: Enable actual ComfyUI server, execute end-to-end tests with sample prompts, fix any path/permission issues.
3. **Production Deployment**: Deploy updated code, confirm ComfyUI server is running, run migration, monitor logs for media prompt processing.
4. **Monitoring**: Initially monitor `poets_cron_service` logs and DB for errors; consider adding alerting on repeated failures or long-running prompts.

---

## Open Questions / Decisions Needed
- Where will ComfyUI run (same host vs separate machine)? Adjust config accordingly.
- How to serve generated media files securely (public vs authenticated)?
- Do we process `voice` prompts now or later? Provide placeholder pipeline if not ready.
- Do we need cleanup/retention policies for media artifacts? (Add scheduled job to prune old files.)

---

## Next Steps
1. Confirm desired ComfyUI deployment topology and workflows.
2. Approve database schema changes and API exposure for artifacts.
3. Implement migration + code changes following steps above.
4. Perform end-to-end test with sample image and music prompts.
