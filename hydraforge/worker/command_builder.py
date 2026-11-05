"""
hydraforge/worker/command_builder.py
Constructs validated container execution commands from Phase 5A Discovery Reports.
Integrates CLI file-in / file-out parameters and adapter shims.
Strictly forbids blindly executing raw shell strings extracted from documentation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from hydraforge.discovery.discovery_models import (
    DiscoveryReport,
    InterfaceStatus,
    ProposedInterfaceMapping,
)
from hydraforge.worker.adapter_builder import AdapterBuilder


class UnresolvedInterfaceError(Exception):
    """Raised when an interface is ambiguous or not safely discoverable."""
    pass


class CommandBuilder:
    """Builds safe container command argument lists from discovery reports."""

    def __init__(
        self,
        container_input_path: str = "/inputs/cases.json",
        container_output_path: str = "/outputs/predictions.json",
    ) -> None:
        self.container_input_path = container_input_path
        self.container_output_path = container_output_path

    def build_execution_command(
        self,
        report: DiscoveryReport,
        scratch_dir: Path,
    ) -> Tuple[List[str], bool]:
        """
        Construct validated container command args from discovery report.
        Returns:
            (command_argv, used_runtime_adapter)
        """
        # 1. Check interface status
        if report.interface_status != InterfaceStatus.INTERFACE_IDENTIFIED:
            raise UnresolvedInterfaceError(
                f"Cannot build execution command: interface status is '{report.interface_status.value}'. "
                "Manual organizer review is required."
            )

        mapping = report.proposed_interface_mapping
        if not mapping or not mapping.executable_target:
            raise UnresolvedInterfaceError(
                "Cannot build execution command: proposed interface mapping is missing."
            )

        target = mapping.executable_target.replace("\\", "/").lstrip("/")

        # Security check: Target must stay within workspace (no path traversal "../")
        if ".." in target or target.startswith("/"):
            raise UnresolvedInterfaceError(f"Security error: Invalid executable target '{target}'.")

        # 2. Case A: Standard CLI with file-in/file-out
        if mapping.interface_type in ("CLI_FILE_IN_OUT", "CLI_INFERRED"):
            # Cleanly invoke python with standardized input/output flags
            command_argv = [
                "python",
                f"/workspace/{target}",
                "--input", self.container_input_path,
                "--output", self.container_output_path,
            ]
            return command_argv, False

        # 3. Case B: Python In-Memory Adapter Interface
        if mapping.interface_type == "PYTHON_ADAPTER":
            # Extract target callable
            module_name = target.replace(".py", "").replace("/", ".")
            callable_spec = f"{module_name}:predict"

            # Check if an explicit callable method was found in candidate entrypoints
            for ep in report.candidate_entrypoints:
                if ep.file_path == mapping.executable_target and ep.callable_name:
                    callable_spec = f"{module_name}:{ep.callable_name}"
                    break

            # Generate shim in scratch directory
            shim_path = AdapterBuilder.write_shim_to_directory(scratch_dir, callable_spec)

            # Invoke container running the generated shim
            command_argv = [
                "python",
                "/tmp/hydraforge_shim.py",
                "--input", self.container_input_path,
                "--output", self.container_output_path,
            ]
            return command_argv, True

        raise UnresolvedInterfaceError(
            f"Unsupported interface type '{mapping.interface_type}'. Requires organizer review."
        )

