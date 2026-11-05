"""
hydraforge/worker/resource_enforcer.py
Enforces hardware resource ceilings (CPU, memory, disk, process limits)
and translates configuration into container isolation arguments.
"""

from __future__ import annotations

from typing import List

from hydraforge.worker.worker_models import WorkerResourceLimits


class ResourceLimitConfigError(Exception):
    """Raised when configured limits exceed system boundaries or safety policies."""
    pass


class ResourceEnforcer:
    """Translates WorkerResourceLimits into container runtime flags."""

    @staticmethod
    def validate_limits(limits: WorkerResourceLimits) -> None:
        """Sanity check resource limits against safety thresholds."""
        if limits.cpu_limit <= 0.0 or limits.cpu_limit > 16.0:
            raise ResourceLimitConfigError(f"Invalid CPU limit: {limits.cpu_limit}. Must be between 0.1 and 16.0.")
        if limits.memory_limit_mb < 256.0 or limits.memory_limit_mb > 32768.0:
            raise ResourceLimitConfigError(f"Invalid memory limit: {limits.memory_limit_mb} MB.")
        if limits.pids_limit < 10 or limits.pids_limit > 1024:
            raise ResourceLimitConfigError(f"Invalid pids limit: {limits.pids_limit}.")
        if limits.timeout_seconds <= 0 or limits.timeout_seconds > 3600:
            raise ResourceLimitConfigError(f"Invalid timeout: {limits.timeout_seconds}s.")

    @staticmethod
    def build_docker_resource_args(limits: WorkerResourceLimits) -> List[str]:
        """Generate command arguments for docker run enforcing limits."""
        ResourceEnforcer.validate_limits(limits)
        mem_mb = int(limits.memory_limit_mb)
        return [
            "--cpus", str(limits.cpu_limit),
            "--memory", f"{mem_mb}m",
            "--memory-swap", f"{mem_mb}m",  # Disables swap beyond RAM allocation
            "--pids-limit", str(limits.pids_limit),
        ]

