"""
hydraforge/discovery/discovery_models.py
Data models, enums, and structures for dynamic repository inspection,
manifest identification, command classification, and inference mapping.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DiscoveryStatus(str, Enum):
    """Overall status of repository discovery."""
    DISCOVERY_PENDING = "DISCOVERY_PENDING"
    DISCOVERY_SUCCESS = "DISCOVERY_SUCCESS"
    DISCOVERY_PARTIAL = "DISCOVERY_PARTIAL"
    DISCOVERY_FAILED = "DISCOVERY_FAILED"
    NEEDS_ORGANIZER_REVIEW = "NEEDS_ORGANIZER_REVIEW"


class InterfaceStatus(str, Enum):
    """Status of inference interface determination."""
    INTERFACE_IDENTIFIED = "INTERFACE_IDENTIFIED"
    INTERFACE_AMBIGUOUS = "INTERFACE_AMBIGUOUS"
    INTERFACE_NOT_FOUND = "INTERFACE_NOT_FOUND"


class ConfidenceLevel(str, Enum):
    """Confidence tier for classifications."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class FileType(str, Enum):
    """Categorized file types."""
    PYTHON_SOURCE = "PYTHON_SOURCE"
    CONFIG_MANIFEST = "CONFIG_MANIFEST"
    DOCUMENTATION = "DOCUMENTATION"
    DOCKERFILE = "DOCKERFILE"
    BUILD_SCRIPT = "BUILD_SCRIPT"
    DATA_FILE = "DATA_FILE"
    OTHER = "OTHER"


class CommandType(str, Enum):
    """Classified command purposes."""
    INFERENCE = "INFERENCE"
    TRAINING = "TRAINING"
    EVALUATION = "EVALUATION"
    TEST = "TEST"
    APPLICATION_STARTUP = "APPLICATION_STARTUP"
    BUILD_OR_INSTALL = "BUILD_OR_INSTALL"
    UNKNOWN = "UNKNOWN"


@dataclass
class FileClassificationRecord:
    """Record of classified file within inspected repository."""
    path: str
    file_type: FileType
    purpose: str
    language: Optional[str] = None
    size_bytes: int = 0
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    details: str = ""


@dataclass
class ManifestRecord:
    """Record of detected project manifest or dependency specification."""
    path: str
    manifest_type: str
    declared_dependencies: List[str] = field(default_factory=list)
    python_version: Optional[str] = None
    entrypoints: Dict[str, str] = field(default_factory=dict)
    raw_config_summary: Dict[str, Any] = field(default_factory=dict)
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH


@dataclass
class DiscoveredCommand:
    """A command detected in documentation, scripts, or manifests."""
    raw_command: str
    command_type: CommandType
    source_file: str
    executable_script: Optional[str] = None
    input_flags: List[str] = field(default_factory=list)
    output_flags: List[str] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    notes: str = ""
    is_malicious: bool = False
    security_warning: Optional[str] = None


@dataclass
class CandidateEntrypoint:
    """A candidate execution entrypoint for inference or model execution."""
    file_path: str
    entrypoint_type: str  # e.g., "cli_script", "package_script", "documented_command", "ast_inferred"
    callable_name: Optional[str] = None
    args_parser: Optional[str] = None  # e.g., "argparse", "click", "sys.argv", "none"
    detected_purpose: CommandType = CommandType.UNKNOWN
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    execution_signature: Optional[str] = None
    input_arguments: List[str] = field(default_factory=list)
    output_arguments: List[str] = field(default_factory=list)


@dataclass
class ProposedInterfaceMapping:
    """Proposed standard execution mapping for the identified interface."""
    interface_type: str  # e.g., "CLI_FILE_IN_OUT", "CLI_INFERRED", "PYTHON_ADAPTER", "MANUAL_REVIEW"
    executable_target: Optional[str] = None
    input_mechanism: str = "--input <file>"
    output_mechanism: str = "--output <file>"
    command_template: Optional[str] = None
    requires_adapter: bool = False
    adapter_notes: str = ""


@dataclass
class RepositoryStructureSummary:
    """Aggregate summary of repository layout."""
    total_files: int = 0
    total_size_bytes: int = 0
    source_file_count: int = 0
    manifest_count: int = 0
    doc_file_count: int = 0
    max_depth_reached: int = 0
    languages_detected: List[str] = field(default_factory=list)
    tree_preview: List[str] = field(default_factory=list)


@dataclass
class DiscoveryReport:
    """Comprehensive, immutable discovery audit report for a participant submission."""
    discovery_id: str
    submission_id: str
    repository_url: str
    commit_sha: str
    created_at: str
    status: DiscoveryStatus
    interface_status: InterfaceStatus
    confidence: ConfidenceLevel
    structure: RepositoryStructureSummary
    detected_languages: List[str] = field(default_factory=list)
    detected_manifests: List[ManifestRecord] = field(default_factory=list)
    detected_dependencies: List[str] = field(default_factory=list)
    documentation_findings: Dict[str, Any] = field(default_factory=dict)
    candidate_training_commands: List[DiscoveredCommand] = field(default_factory=list)
    candidate_inference_commands: List[DiscoveredCommand] = field(default_factory=list)
    candidate_entrypoints: List[CandidateEntrypoint] = field(default_factory=list)
    proposed_interface_mapping: Optional[ProposedInterfaceMapping] = None
    warnings: List[str] = field(default_factory=list)
    failure_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to JSON-serializable dictionary."""
        def _serialize_helper(obj):
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _serialize_helper(v) for k, v in asdict(obj).items()}
            if isinstance(obj, dict):
                return {k: _serialize_helper(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize_helper(i) for i in obj]
            return obj

        return _serialize_helper(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize report to indented JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

