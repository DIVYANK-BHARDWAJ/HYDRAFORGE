"""
hydraforge/worker/worker_cleanup.py
Guaranteed post-execution cleanup for isolated workers.
Removes disposable containers, prunes scratch volumes, and records cleanup audits.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


class WorkerCleanup:
    """Manages teardown of ephemeral container containers and scratch directories."""

    @staticmethod
    def cleanup_container(container_id_or_name: str, timeout: int = 10) -> bool:
        """Forcefully remove disposable container if still running."""
        if not container_id_or_name:
            return True
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_id_or_name],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return True
        except Exception:
            return False

    @staticmethod
    def cleanup_scratch_directory(scratch_dir: Optional[Path]) -> Tuple[bool, Optional[str]]:
        """Remove temporary scratch directory and files."""
        if not scratch_dir or not Path(scratch_dir).exists():
            return True, None

        scratch_path = Path(scratch_dir).resolve()
        try:
            shutil.rmtree(scratch_path, ignore_errors=False)
            return True, None
        except Exception as e:
            return False, f"Failed to remove scratch directory '{scratch_path}': {e}"

