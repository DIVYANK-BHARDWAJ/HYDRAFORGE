"""
hydraforge/worker/worker_config.py
Configuration profiles, container engine options, and hardened security settings
for isolated model execution environments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass(frozen=True)
class WorkerSecurityProfile:
    """Security settings enforcing container and namespace isolation."""
    # User isolation: Non-root UID/GID inside container
    container_user: str = "10001:10001"

    # Filesystem immutability
    read_only_rootfs: bool = True
    no_new_privileges: bool = True
    drop_all_capabilities: bool = True

    # Network airgap: disabled by default
    network_mode: str = "none"

    # Isolation backend (docker, gvisor, firecracker)
    isolation_backend: str = "docker"
    gvisor_runtime: str = "runsc"

    # Volume Mountpoints inside container
    container_input_dir: str = "/inputs"
    container_workspace_dir: str = "/workspace"
    container_output_dir: str = "/outputs"
    container_tmp_dir: str = "/tmp"

    # Base container images
    default_base_image: str = "python:3.11-slim"
    prewarmed_ml_image: str = "hydraforge/runner:1.0.0"

    # Permitted environment variables passed into container
    safe_env_whitelist: Tuple[str, ...] = (
        "PATH",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "HYDRAFORGE_ISOLATED",
        "LC_ALL",
        "LANG",
    )


DEFAULT_SECURITY_PROFILE = WorkerSecurityProfile()

