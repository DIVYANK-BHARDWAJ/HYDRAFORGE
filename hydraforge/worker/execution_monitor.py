"""
hydraforge/worker/execution_monitor.py
Monitors isolated worker execution telemetry, resource consumption,
process lifetime, exit codes, and timeout enforcement.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from hydraforge.worker.worker_models import ExecutionTelemetry


class ExecutionMonitor:
    """Monitors running execution and collects audit telemetry."""

    def __init__(self) -> None:
        self._start_mono: float = 0.0
        self.telemetry = ExecutionTelemetry()

    def start(self, input_hash: str) -> None:
        """Mark start of execution."""
        self._start_mono = time.monotonic()
        self.telemetry.start_time = datetime.now(timezone.utc).isoformat()
        self.telemetry.input_hash = input_hash

    def finish(
        self,
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
        peak_memory_mb: float = 0.0,
        cpu_usage_percent: float = 0.0,
        disk_consumed_mb: float = 0.0,
        timed_out: bool = False,
        termination_reason: Optional[str] = None,
        output_hash: Optional[str] = None
    ) -> ExecutionTelemetry:
        """Record completion of execution and compute final metrics."""
        duration = time.monotonic() - self._start_mono if self._start_mono > 0 else 0.0
        self.telemetry.end_time = datetime.now(timezone.utc).isoformat()
        self.telemetry.wall_clock_seconds = round(duration, 3)
        self.telemetry.exit_code = exit_code
        self.telemetry.stdout = stdout
        self.telemetry.stderr = stderr
        self.telemetry.peak_memory_mb = round(peak_memory_mb, 2)
        self.telemetry.cpu_usage_percent = round(cpu_usage_percent, 2)
        self.telemetry.disk_consumed_mb = round(disk_consumed_mb, 2)
        self.telemetry.timed_out = timed_out
        self.telemetry.termination_reason = termination_reason
        self.telemetry.output_hash = output_hash
        return self.telemetry

