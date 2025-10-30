"""
Pipeline wrapper for the exported audio workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional

from .base import BaseMediaPipeline


class AudioPipeline(BaseMediaPipeline):
    """Execute the audio workflow with the supplied lyrics prompt."""

    def __init__(
        self,
        *,
        script_path: Path,
        python_executable: str,
        output_root: Path,
        queue_size: int,
        timeout_seconds: int,
        comfyui_directory: Optional[str] = None,
        extra_args: Optional[list[str]] = None,
    ):
        super().__init__(
            prompt_type="audio",
            script_path=Path(script_path),
            python_executable=python_executable,
            output_root=Path(output_root),
            prompt_arg="lyrics6",
            queue_size=queue_size,
            timeout_seconds=timeout_seconds,
            comfyui_directory=comfyui_directory,
            extra_args=extra_args,
        )

    def run(
        self,
        *,
        prompt_id: int,
        prompt_text: str,
        metadata: Optional[Mapping[str, object]] = None,
    ):
        metadata_dict = {"prompt_text": prompt_text}
        if metadata:
            metadata_dict.update({k: v for k, v in metadata.items() if v is not None})

        return super().run(
            prompt_id=prompt_id,
            prompt_text=prompt_text,
            metadata=metadata_dict,
        )

