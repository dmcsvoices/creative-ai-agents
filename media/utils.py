"""
Utility helpers for executing SaveAsScript workflows and collecting artifacts.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


class MediaPipelineError(RuntimeError):
    """Raised when a media pipeline execution fails."""


def ensure_directory(path: Path) -> Path:
    """Create the directory (and parents) if it does not already exist."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_files(root: Path) -> Dict[Path, Tuple[int, int]]:
    """
    Build a snapshot map of files under ``root`` keyed by relative path.

    The tuple captures ``(mtime_ns, size_bytes)`` to make it easy to detect new
    or modified files after a workflow completes.
    """
    snapshot: Dict[Path, Tuple[int, int]] = {}

    if not root.exists():
        return snapshot

    for path in root.rglob("*"):
        if path.is_file():
            snapshot[path.relative_to(root)] = (path.stat().st_mtime_ns, path.stat().st_size)
    return snapshot


def detect_new_files(
    root: Path, before: Mapping[Path, Tuple[int, int]]
) -> Tuple[List[Path], Dict[Path, Tuple[int, int]]]:
    """
    Return files that were added or modified relative to ``before`` snapshot.
    """
    after = snapshot_files(root)
    new_files: List[Path] = []

    for rel_path, meta in after.items():
        if rel_path not in before or before[rel_path] != meta:
            new_files.append(root / rel_path)

    return new_files, after


@dataclass
class WorkflowResult:
    """Result information from executing a workflow script."""

    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


def run_workflow(
    python_executable: str,
    script_path: Path,
    workflow_args: Sequence[str],
    *,
    timeout_seconds: int,
    cwd: Optional[Path] = None,
    env_overrides: Optional[Mapping[str, str]] = None,
) -> WorkflowResult:
    """
    Execute the exported SaveAsScript workflow using subprocess.

    Raises:
        MediaPipelineError: if the process exits with a non-zero return code.
    """
    logger = logging.getLogger("media.workflow")

    if not script_path.exists():
        raise MediaPipelineError(f"Workflow script not found: {script_path}")

    command: List[str] = [python_executable, str(script_path), *workflow_args]
    logger.debug(
        "Executing workflow: %s",
        " ".join(shlex.quote(part) for part in command),
    )

    env = os.environ.copy()
    if env_overrides:
        env.update({k: v for k, v in env_overrides.items() if v is not None})

    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error(
            "Workflow %s timed out after %ss", script_path.name, timeout_seconds
        )
        raise MediaPipelineError(
            f"Workflow timed out after {timeout_seconds}s: {script_path}"
        ) from exc

    duration = time.monotonic() - start
    result = WorkflowResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_seconds=duration,
    )

    if completed.returncode != 0:
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        logger.error(
            "Workflow %s failed with code %s\nstdout:\n%s\nstderr:\n%s",
            script_path.name,
            completed.returncode,
            stdout or "<empty>",
            stderr or "<empty>",
        )
        raise MediaPipelineError(
            f"Workflow {script_path.name} failed with code {completed.returncode}. "
            f"See media.workflow logs for stdout/stderr details.",
        )

    return result


def relative_to_root(path: Path, root: Path) -> str:
    """Return a POSIX string path relative to the root directory."""
    return path.relative_to(root).as_posix()
