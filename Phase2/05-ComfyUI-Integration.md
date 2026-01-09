# ComfyUI Integration Layer

## Workflow Execution Architecture

### Base Executor Class

```python
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

class ComfyUIWorkflowExecutor:
    """Base class for executing ComfyUI workflows"""

    def __init__(self, config: Dict[str, Any]):
        self.python_executable = config['comfyui']['python']
        self.comfyui_directory = Path(config['comfyui']['comfyui_directory'])
        self.output_root = Path(config['comfyui']['output_directory'])
        self.timeout_seconds = config['comfyui']['timeout_seconds']

    def _create_output_directory(self, prompt_id: int, artifact_type: str) -> Path:
        """Create timestamped output directory"""
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        output_dir = self.output_root / artifact_type / f"{prompt_id}_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _get_relative_path(self, full_path: Path) -> str:
        """Convert absolute path to relative path from output_root"""
        return str(full_path.relative_to(self.output_root.parent))
```

## Image Workflow Executor

```python
class ImageWorkflowExecutor(ComfyUIWorkflowExecutor):
    """Execute image generation workflows"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.workflow_script = Path(config['media']['scripts']['image'])

    def generate(
        self,
        prompt: PromptRecord,
        json_data: ImagePromptData,
        progress_callback=None
    ) -> List[ArtifactRecord]:
        """Execute image workflow and return artifact records"""

        # Create output directory
        output_dir = self._create_output_directory(prompt.id, 'image')

        # Build command arguments
        cmd = [
            self.python_executable,
            str(self.workflow_script),
            '--prompt', json_data.prompt,
            '--negative-prompt', json_data.negative_prompt,
            '--output', str(output_dir),
            '--queue-size', '1'
        ]

        if progress_callback:
            progress_callback(f"Starting image generation for prompt #{prompt.id}")

        # Execute workflow
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.comfyui_directory),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds
            )

            if result.returncode != 0:
                raise RuntimeError(f"Workflow failed: {result.stderr}")

            # Find generated files
            artifacts = []
            for img_file in output_dir.glob('*.png'):
                relative_path = self._get_relative_path(img_file)

                artifact = ArtifactRecord(
                    id=None,
                    prompt_id=prompt.id,
                    artifact_type='image',
                    file_path=relative_path,
                    preview_path=relative_path,  # Same as file for images
                    metadata={
                        'prompt': json_data.prompt,
                        'negative_prompt': json_data.negative_prompt,
                        'aspect_ratio': json_data.aspect_ratio,
                        'quality': json_data.quality,
                        'style_tags': json_data.style_tags,
                        'generated_at': datetime.now().isoformat()
                    }
                )
                artifacts.append(artifact)

            if progress_callback:
                progress_callback(f"Generated {len(artifacts)} image(s)")

            return artifacts

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Workflow timed out after {self.timeout_seconds}s")
        except Exception as e:
            raise RuntimeError(f"Generation failed: {str(e)}")
```

## Audio Workflow Executor

```python
class AudioWorkflowExecutor(ComfyUIWorkflowExecutor):
    """Execute audio generation workflows"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.workflow_script = Path(config['media']['scripts']['music'])

    def generate(
        self,
        prompt: PromptRecord,
        json_data: LyricsPromptData,
        progress_callback=None
    ) -> List[ArtifactRecord]:
        """Execute audio workflow and return artifact records"""

        # Create output directory
        output_dir = self._create_output_directory(prompt.id, 'audio')

        # Get full lyrics text
        lyrics_text = json_data.get_full_lyrics()

        # Build command arguments
        cmd = [
            self.python_executable,
            str(self.workflow_script),
            '--lyrics', lyrics_text,
            '--tags', f"{json_data.genre}, {json_data.mood}",
            '--output', str(output_dir),
            '--queue-size', '1'
        ]

        if progress_callback:
            progress_callback(f"Starting audio generation for prompt #{prompt.id}")

        # Execute workflow
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.comfyui_directory),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds
            )

            if result.returncode != 0:
                raise RuntimeError(f"Workflow failed: {result.stderr}")

            # Find generated files
            artifacts = []
            for audio_file in output_dir.glob('*.mp3'):
                relative_path = self._get_relative_path(audio_file)

                artifact = ArtifactRecord(
                    id=None,
                    prompt_id=prompt.id,
                    artifact_type='audio',
                    file_path=relative_path,
                    preview_path=None,  # No preview for audio
                    metadata={
                        'title': json_data.title,
                        'genre': json_data.genre,
                        'mood': json_data.mood,
                        'tempo': json_data.tempo,
                        'key': json_data.key,
                        'time_signature': json_data.time_signature,
                        'generated_at': datetime.now().isoformat()
                    }
                )
                artifacts.append(artifact)

            if progress_callback:
                progress_callback(f"Generated {len(artifacts)} audio file(s)")

            return artifacts

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Workflow timed out after {self.timeout_seconds}s")
        except Exception as e:
            raise RuntimeError(f"Generation failed: {str(e)}")
```

## Integration with UI

### Generation Method

```python
def generate_image_prompt(self, prompt: PromptRecord):
    """Generate image from prompt"""
    try:
        # Update status
        self.prompt_repo.update_artifact_status(prompt.id, 'processing')
        self.status_bar.config(text=f"Generating image for prompt #{prompt.id}...")

        # Parse JSON
        json_data = ImagePromptData.from_json(prompt.get_json_prompt())

        # Execute workflow
        executor = ImageWorkflowExecutor(self.config)
        artifacts = executor.generate(
            prompt,
            json_data,
            progress_callback=self.update_status
        )

        # Save artifacts to database
        for artifact in artifacts:
            self.artifact_repo.save_artifact(artifact)

        # Update status
        self.prompt_repo.update_artifact_status(prompt.id, 'ready')
        self.status_bar.config(text=f"Successfully generated {len(artifacts)} image(s)")

        # Refresh list
        self.refresh_image_list()

        messagebox.showinfo("Success", f"Generated {len(artifacts)} image(s) for prompt #{prompt.id}")

    except Exception as e:
        self.prompt_repo.update_artifact_status(prompt.id, 'error', str(e))
        self.status_bar.config(text=f"Error: {str(e)}")
        messagebox.showerror("Generation Failed", str(e))
```

## Error Handling

### Common Errors

1. **ComfyUI server not running**: Check if server is accessible at http://127.0.0.1:8188
2. **Workflow script not found**: Verify paths in configuration
3. **Timeout expired**: Increase timeout_seconds in config
4. **Permission denied**: Check file permissions for output directory
5. **Invalid JSON**: Validate JSON structure before parsing

### Recovery Strategies

```python
def generate_with_retry(self, prompt, max_retries=3):
    """Generate with automatic retry on transient failures"""
    for attempt in range(max_retries):
        try:
            return self.generate(prompt)
        except subprocess.TimeoutExpired:
            if attempt < max_retries - 1:
                time.sleep(5)  # Wait before retry
                continue
            raise
        except Exception as e:
            if "connection" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(10)
                continue
            raise
```

## Next Steps

See [06-Configuration.md](06-Configuration.md) for configuration file structure.
