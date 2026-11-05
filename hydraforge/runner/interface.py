"""Runner interface and execution outcome dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RunnerExecutionResult:
    """Outcome of running a submission in an execution sandbox."""
    exit_code: int
    stdout: str
    stderr: str
    runtime_seconds: Optional[float]
    peak_memory_mb: Optional[float]
    output_dir: Path
    is_success: bool
    failure_reason: Optional[str] = None


class BaseRunner(ABC):
    """Abstract submission execution runner."""

    @abstractmethod
    def run_submission(
        self,
        repo_dir: Path,
        input_dir: Path,
        output_dir: Path,
        entrypoint: str,
        timeout_seconds: int = 300,
        max_memory_mb: float = 4096.0,
        is_trusted: bool = False
    ) -> RunnerExecutionResult:
        """Execute submission code against input_dir and collect predictions in output_dir."""
        pass

