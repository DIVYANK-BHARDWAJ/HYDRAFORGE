"""
hydraforge/discovery/repository_inspector.py
Master coordinator for dynamic repository discovery and inference contract mapping.
Inspects arbitrary repository structures without executing code or assuming fixed filenames.
Operates strictly on the immutable captured commit SHA.
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from hydraforge.discovery.discovery_models import (
    CommandType,
    ConfidenceLevel,
    DiscoveryReport,
    DiscoveryStatus,
    FileType,
    InterfaceStatus,
    RepositoryStructureSummary,
)
from hydraforge.discovery.documentation_parser import DocumentationParser
from hydraforge.discovery.entrypoint_discovery import EntrypointDiscovery
from hydraforge.discovery.file_classifier import (
    FileClassifier,
    InsecureSymlinkError,
    RepositoryLimitsExceededError,
)
from hydraforge.discovery.manifest_detector import ManifestDetector
from hydraforge.submission.repository import (
    RepositoryIntake,
    RepositorySecurityError,
    validate_commit_sha,
    validate_repository_url,
)


class RepositoryInspector:
    """Master engine for static repository inspection and contract discovery."""

    def __init__(
        self,
        file_classifier: Optional[FileClassifier] = None,
        manifest_detector: Optional[ManifestDetector] = None,
        doc_parser: Optional[DocumentationParser] = None,
        entrypoint_discovery: Optional[EntrypointDiscovery] = None,
        intake: Optional[RepositoryIntake] = None,
        db_repo: Optional[Any] = None,
    ) -> None:
        self.file_classifier = file_classifier or FileClassifier()
        self.manifest_detector = manifest_detector or ManifestDetector()
        self.doc_parser = doc_parser or DocumentationParser()
        self.entrypoint_discovery = entrypoint_discovery or EntrypointDiscovery()
        self.intake = intake or RepositoryIntake()
        self.db_repo = db_repo

    def inspect_repository(
        self,
        repo_dir: Path,
        submission_id: str = "sub_local_test",
        repository_url: str = "https://github.com/participant/project.git",
        commit_sha: str = "0" * 40,
    ) -> DiscoveryReport:
        """
        Inspect an already checked-out local repository directory.
        STRICT SECURITY: Never executes or imports participant code.
        """
        repo_dir = Path(repo_dir).resolve()
        discovery_id = f"disc_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        warnings: List[str] = []
        failure_reasons: List[str] = []

        # 1. Scan and classify filesystem tree
        try:
            classified_files, structure, scan_warnings = self.file_classifier.scan_and_classify(repo_dir)
            warnings.extend(scan_warnings)
        except RepositoryLimitsExceededError as e:
            return DiscoveryReport(
                discovery_id=discovery_id,
                submission_id=submission_id,
                repository_url=repository_url,
                commit_sha=commit_sha,
                created_at=now_iso,
                status=DiscoveryStatus.DISCOVERY_FAILED,
                interface_status=InterfaceStatus.INTERFACE_NOT_FOUND,
                confidence=ConfidenceLevel.NONE,
                structure=RepositoryStructureSummary(),
                warnings=warnings,
                failure_reasons=[f"Resource limits exceeded: {str(e)}"]
            )
        except Exception as e:
            return DiscoveryReport(
                discovery_id=discovery_id,
                submission_id=submission_id,
                repository_url=repository_url,
                commit_sha=commit_sha,
                created_at=now_iso,
                status=DiscoveryStatus.DISCOVERY_FAILED,
                interface_status=InterfaceStatus.INTERFACE_NOT_FOUND,
                confidence=ConfidenceLevel.NONE,
                structure=RepositoryStructureSummary(),
                warnings=warnings,
                failure_reasons=[f"Filesystem scan failed: {str(e)}"]
            )

        # 2. Detect and parse manifests & dependencies
        manifests, all_deps, manifest_warnings = self.manifest_detector.detect_manifests(repo_dir)
        warnings.extend(manifest_warnings)

        # 3. Parse documentation for commands and instructions
        doc_findings, doc_commands, doc_warnings = self.doc_parser.parse_repository_docs(repo_dir)
        warnings.extend(doc_warnings)

        # Separate training and inference commands
        training_cmds = [c for c in doc_commands if c.command_type == CommandType.TRAINING]
        inference_cmds = [c for c in doc_commands if c.command_type in (CommandType.INFERENCE, CommandType.EVALUATION)]

        # Check for malicious commands in documentation
        has_malicious = any(c.is_malicious for c in doc_commands)
        if has_malicious:
            warnings.append("Malicious command patterns detected in documentation. Marked for organizer review.")

        # 4. Discover inference entrypoints
        py_files = [f.path for f in classified_files if f.file_type == FileType.PYTHON_SOURCE]
        candidates, iface_status, proposed_mapping, ep_warnings = self.entrypoint_discovery.discover_entrypoints(
            repo_root=repo_dir,
            manifest_records=manifests,
            doc_commands=doc_commands,
            python_files=py_files
        )
        warnings.extend(ep_warnings)

        # 5. Synthesize final status and confidence
        if has_malicious:
            final_status = DiscoveryStatus.NEEDS_ORGANIZER_REVIEW
            final_confidence = ConfidenceLevel.LOW
        elif iface_status == InterfaceStatus.INTERFACE_IDENTIFIED:
            final_status = DiscoveryStatus.DISCOVERY_SUCCESS
            final_confidence = ConfidenceLevel.HIGH if (proposed_mapping and not proposed_mapping.requires_adapter) else ConfidenceLevel.MEDIUM
        elif iface_status == InterfaceStatus.INTERFACE_AMBIGUOUS:
            final_status = DiscoveryStatus.NEEDS_ORGANIZER_REVIEW
            final_confidence = ConfidenceLevel.LOW
        else:
            # INTERFACE_NOT_FOUND
            final_status = DiscoveryStatus.DISCOVERY_PARTIAL if py_files else DiscoveryStatus.DISCOVERY_FAILED
            final_confidence = ConfidenceLevel.NONE
            failure_reasons.append("No valid inference entrypoint or prediction interface could be discovered.")

        report = DiscoveryReport(
            discovery_id=discovery_id,
            submission_id=submission_id,
            repository_url=repository_url,
            commit_sha=commit_sha,
            created_at=now_iso,
            status=final_status,
            interface_status=iface_status,
            confidence=final_confidence,
            structure=structure,
            detected_languages=structure.languages_detected,
            detected_manifests=manifests,
            detected_dependencies=all_deps,
            documentation_findings=doc_findings,
            candidate_training_commands=training_cmds,
            candidate_inference_commands=inference_cmds,
            candidate_entrypoints=candidates,
            proposed_interface_mapping=proposed_mapping,
            warnings=warnings,
            failure_reasons=failure_reasons
        )

        if self.db_repo and hasattr(self.db_repo, "insert_discovery_report"):
            try:
                self.db_repo.insert_discovery_report(
                    discovery_id=report.discovery_id,
                    submission_id=report.submission_id,
                    commit_sha=report.commit_sha,
                    status=report.status.value,
                    interface_status=report.interface_status.value,
                    confidence=report.confidence.value,
                    report_json=report.to_json(),
                    created_at=report.created_at,
                )
            except Exception as e:
                report.warnings.append(f"Failed to persist discovery report to database: {e}")

        return report

    def inspect_remote_submission(
        self,
        submission_id: str,
        repository_url: str,
        commit_sha: str,
        scratch_base: Optional[Path] = None
    ) -> DiscoveryReport:
        """
        Clone exact immutable commit SHA into scratch dir and run discovery.
        """
        clean_url = validate_repository_url(repository_url)
        clean_sha = validate_commit_sha(commit_sha)

        with tempfile.TemporaryDirectory() as tmp_dir:
            checkout_dest = Path(tmp_dir) / "repo"
            try:
                self.intake.checkout(
                    repo_url=clean_url,
                    commit_sha=clean_sha,
                    destination_dir=checkout_dest
                )
            except RepositorySecurityError as e:
                now_iso = datetime.now(timezone.utc).isoformat()
                return DiscoveryReport(
                    discovery_id=f"disc_{uuid.uuid4().hex[:12]}",
                    submission_id=submission_id,
                    repository_url=clean_url,
                    commit_sha=clean_sha,
                    created_at=now_iso,
                    status=DiscoveryStatus.DISCOVERY_FAILED,
                    interface_status=InterfaceStatus.INTERFACE_NOT_FOUND,
                    confidence=ConfidenceLevel.NONE,
                    structure=RepositoryStructureSummary(),
                    warnings=[],
                    failure_reasons=[f"Secure repository checkout failed: {str(e)}"]
                )

            return self.inspect_repository(
                repo_dir=checkout_dest,
                submission_id=submission_id,
                repository_url=clean_url,
                commit_sha=clean_sha
            )
