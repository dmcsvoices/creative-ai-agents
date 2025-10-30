"""
Base classes shared by media pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from .utils import (
    MediaPipelineError,
    WorkflowResult,
    detect_new_files,
    ensure_directory,
    relative_to_root,
    run_workflow,
    snapshot_files,
)


@dataclass
class MediaArtifact:
    """Structured representation of a generated artifact."""

    artifact_type: str
    file_path: str
    preview_path: Optional[str]
    metadata: Dict[str, object]


class BaseMediaPipeline:
    """Shared logic for invoking SaveAsScript workflows."""

    def __init__(
        self,
        *,
        prompt_type: str,
        script_path: Path,
        python_executable: str,
        output_root: Path,
        prompt_arg: str,
        queue_size: int,
        timeout_seconds: int,
        comfyui_directory: Optional[str] = None,
        extra_args: Optional[Sequence[str]] = None,
    ):
        self.prompt_type = prompt_type
        self.script_path = script_path
        self.python_executable = python_executable
        self.output_root = output_root
        self.prompt_arg = prompt_arg
        self.queue_size = queue_size
        self.timeout_seconds = timeout_seconds
        self.comfyui_directory = comfyui_directory
        self.extra_args = list(extra_args or [])

    def _create_run_directory(self, prompt_id: int) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        run_dir = self.output_root / self.prompt_type / f"{prompt_id}_{timestamp}"
        ensure_directory(run_dir)
        return run_dir

    def _build_command_args(
        self,
        *,
        prompt_text: str,
        run_dir: Path,
    ) -> List[str]:
        args: List[str] = [
            f"--{self.prompt_arg}",
            prompt_text,
            "--queue-size",
            str(self.queue_size),
            "--output",
            str(run_dir),
        ]

        if self.comfyui_directory:
            args.extend(["--comfyui-directory", self.comfyui_directory])

        args.extend(self.extra_args)
        return args

    def run(
        self,
        *,
        prompt_id: int,
        prompt_text: str,
        metadata: Optional[Mapping[str, object]] = None,
    ) -> Dict[str, object]:
        """
        Execute the workflow and return artifacts + execution details.

        Returns a dictionary containing:
            - ``artifacts``: List[MediaArtifact]
            - ``stdout`` and ``stderr`` from the workflow execution
            - ``duration_seconds``
        """
        run_dir = self._create_run_directory(prompt_id)
        pre_snapshot = snapshot_files(run_dir)

        workflow_args = self._build_command_args(
            prompt_text=prompt_text,
            run_dir=run_dir,
        )

        result: WorkflowResult = run_workflow(
            self.python_executable,
            self.script_path,
            workflow_args,
            timeout_seconds=self.timeout_seconds,
            cwd=self.script_path.parent,
        )

        new_files, _ = detect_new_files(run_dir, pre_snapshot)

        if not new_files:
            raise MediaPipelineError(
                f"No artifacts were produced for prompt {prompt_id} "
                f"using script {self.script_path.name}"
            )

        artifact_metadata: Dict[str, object] = {
            "script": self.script_path.name,
            "duration_seconds": result.duration_seconds,
        }
        if metadata:
            artifact_metadata.update(metadata)

        artifacts = [
            MediaArtifact(
                artifact_type=self.prompt_type,
                file_path=relative_to_root(path, self.output_root),
                preview_path=relative_to_root(path, self.output_root)
                if self.prompt_type == "image"
                else None,
                metadata=artifact_metadata,
            )
            for path in new_files
        ]

        return {
            "artifacts": artifacts,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_seconds": result.duration_seconds,
            "run_directory": relative_to_root(run_dir, self.output_root),
        }
