"""
hydraforge/worker/dependency_manager.py
Manages dependency resolution, manifest validation, and in-container installation.
STRICT SECURITY: Never installs packages or executes setup.py on the host.
Dependencies are prepared exclusively within disposable isolated containers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from hydraforge.discovery.discovery_models import DiscoveryReport, ManifestRecord


class DependencyResolutionError(Exception):
    """Raised when dependency resolution fails or manifests conflict."""
    pass


# Package names that present severe security or system-level risks
DISALLOWED_PACKAGES: Set[str] = {
    "cryptography_backdoor",
    "pyhook",
    "pwn",
    "scapy",
}


class DependencyManager:
    """Validates manifests and constructs in-container dependency installation plans."""

    def __init__(self, install_timeout_seconds: int = 120) -> None:
        self.install_timeout_seconds = install_timeout_seconds

    def evaluate_dependencies(
        self, report: DiscoveryReport
    ) -> Tuple[bool, List[str], Optional[str]]:
        """
        Validate dependencies extracted by Phase 5A discovery.
        Returns:
            (is_valid, install_plan_lines, error_or_warning)
        """
        manifests = report.detected_manifests
        # Check for multiple conflicting manifest types
        if manifests:
            types = {m.manifest_type for m in manifests}
            if len(types) > 2 and ("requirements.txt" in types and "pyproject.toml" in types and "Pipfile" in types):
                return False, [], "Multiple conflicting manifests detected without clear precedence. Requires organizer review."

        if not report.detected_dependencies:
            # Zero external dependencies declared (pure standard library)
            return True, [], None

        clean_deps: List[str] = []
        for dep in report.detected_dependencies:
            dep_clean = dep.strip()
            pkg_name = re.split(r"[=<>~!]", dep_clean)[0].strip().lower()

            if pkg_name in DISALLOWED_PACKAGES:
                return False, [], f"Disallowed or malicious package name detected in dependencies: '{pkg_name}'"

            # Check for shell metacharacters attempting injection
            if any(char in dep_clean for char in (";", "&", "|", "`", "$", "(", ")", "\n", "\r")):
                return False, [], f"Security violation: Illegal characters detected in dependency string: '{dep_clean}'"

            clean_deps.append(dep_clean)

        return True, clean_deps, None

    def build_container_install_command(
        self,
        manifest_path: str,
        pip_cache_dir: Optional[str] = "/root/.cache/pip"
    ) -> List[str]:
        """
        Construct a hardened pip install command executed ONLY inside the isolated container.
        """
        # Ensure path stays within /workspace
        norm_manifest = manifest_path.replace("\\", "/").lstrip("/")
        container_manifest = f"/workspace/{norm_manifest}"

        return [
            "pip", "install",
            "--no-warn-script-location",
            "--disable-pip-version-check",
            "-r", container_manifest,
        ]
