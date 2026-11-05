"""
hydraforge/discovery/discovery_report.py
Report formatting, terminal markdown rendering, and database serialization
helpers for dynamic repository discovery.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from hydraforge.discovery.discovery_models import DiscoveryReport, DiscoveryStatus, InterfaceStatus


class DiscoveryReportFormatter:
    """Renders DiscoveryReport objects into structured Markdown and JSON representations."""

    @staticmethod
    def to_markdown(report: DiscoveryReport) -> str:
        """Format DiscoveryReport as GitHub-style Markdown."""
        lines = [
            "# HYDRAFORGE Repository Discovery Report",
            f"**Discovery ID:** `{report.discovery_id}`  ",
            f"**Submission ID:** `{report.submission_id}`  ",
            f"**Repository:** `{report.repository_url}`  ",
            f"**Commit SHA:** `{report.commit_sha}`  ",
            f"**Created At:** {report.created_at}  ",
            "",
            "## Discovery Status Overview",
            f"- **Overall Status:** `{report.status.value}`",
            f"- **Interface Classification:** `{report.interface_status.value}`",
            f"- **Confidence Level:** `{report.confidence.value}`",
            "",
            "## Repository Structure",
            f"- **Total Files Scanned:** {report.structure.total_files}",
            f"- **Total Size:** {report.structure.total_size_bytes / 1024:.1f} KB",
            f"- **Source Files:** {report.structure.source_file_count}",
            f"- **Manifests Found:** {report.structure.manifest_count}",
            f"- **Documentation Files:** {report.structure.doc_file_count}",
            f"- **Max Depth Reached:** {report.structure.max_depth_reached}",
            f"- **Detected Languages:** {', '.join(report.detected_languages) if report.detected_languages else 'None'}",
            "",
            "## Detected Manifests & Dependencies",
        ]

        if not report.detected_manifests:
            lines.append("*No project manifests detected.*")
        else:
            for m in report.detected_manifests:
                lines.append(f"- **{m.path}** (`{m.manifest_type}`): {len(m.declared_dependencies)} dependencies")
                if m.python_version:
                    lines.append(f"  - Python Version: `{m.python_version}`")
                if m.entrypoints:
                    lines.append(f"  - Declared Entrypoints: `{m.entrypoints}`")

        lines.extend([
            "",
            "## Candidate Inference Commands",
        ])

        if not report.candidate_inference_commands:
            lines.append("*No documented inference commands found.*")
        else:
            for cmd in report.candidate_inference_commands:
                warn = f" ⚠️ **SECURITY WARNING:** {cmd.security_warning}" if cmd.is_malicious else ""
                lines.append(f"- `{cmd.raw_command}` (from `{cmd.source_file}`){warn}")

        lines.extend([
            "",
            "## Candidate Entrypoints",
        ])

        if not report.candidate_entrypoints:
            lines.append("*No entrypoints identified.*")
        else:
            for ep in report.candidate_entrypoints:
                lines.append(
                    f"- `{ep.file_path}` ({ep.entrypoint_type}) — Purpose: `{ep.detected_purpose.value}` "
                    f"[Confidence: {ep.confidence.value}]"
                )

        lines.extend([
            "",
            "## Proposed Interface Mapping",
        ])

        if report.proposed_interface_mapping:
            pim = report.proposed_interface_mapping
            lines.append(f"- **Interface Type:** `{pim.interface_type}`")
            lines.append(f"- **Executable Target:** `{pim.executable_target}`")
            lines.append(f"- **Input Mechanism:** `{pim.input_mechanism}`")
            lines.append(f"- **Output Mechanism:** `{pim.output_mechanism}`")
            if pim.command_template:
                lines.append(f"- **Command Template:** `{pim.command_template}`")
            lines.append(f"- **Requires Adapter:** `{pim.requires_adapter}`")
            if pim.adapter_notes:
                lines.append(f"- **Notes:** {pim.adapter_notes}")
        else:
            lines.append("*No automated interface mapping available.*")

        if report.warnings:
            lines.extend([
                "",
                "## Warnings & Security Notices",
            ])
            for w in report.warnings:
                lines.append(f"- ⚠️ {w}")

        if report.failure_reasons:
            lines.extend([
                "",
                "## Failure Reasons",
            ])
            for f in report.failure_reasons:
                lines.append(f"- ❌ {f}")

        return "\n".join(lines)

