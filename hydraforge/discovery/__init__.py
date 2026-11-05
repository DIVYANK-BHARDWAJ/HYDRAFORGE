"""
hydraforge/discovery
Dynamic Repository Discovery & Standardized Inference Contract Package.
"""

from hydraforge.discovery.contract import (
    InferenceContractSpecification,
    get_sample_input_contract_json,
    get_sample_output_contract_json,
)
from hydraforge.discovery.discovery_models import (
    CandidateEntrypoint,
    CommandType,
    ConfidenceLevel,
    DiscoveredCommand,
    DiscoveryReport,
    DiscoveryStatus,
    FileClassificationRecord,
    FileType,
    InterfaceStatus,
    ManifestRecord,
    ProposedInterfaceMapping,
    RepositoryStructureSummary,
)
from hydraforge.discovery.discovery_report import DiscoveryReportFormatter
from hydraforge.discovery.documentation_parser import DocumentationParser
from hydraforge.discovery.entrypoint_discovery import EntrypointDiscovery
from hydraforge.discovery.file_classifier import (
    FileClassifier,
    InsecureSymlinkError,
    RepositoryLimitsExceededError,
)
from hydraforge.discovery.manifest_detector import ManifestDetector
from hydraforge.discovery.repository_inspector import RepositoryInspector

__all__ = [
    "CandidateEntrypoint",
    "CommandType",
    "ConfidenceLevel",
    "DiscoveredCommand",
    "DiscoveryReport",
    "DiscoveryReportFormatter",
    "DiscoveryStatus",
    "DocumentationParser",
    "EntrypointDiscovery",
    "FileClassificationRecord",
    "FileClassifier",
    "FileType",
    "InferenceContractSpecification",
    "InsecureSymlinkError",
    "InterfaceStatus",
    "ManifestDetector",
    "ManifestRecord",
    "ProposedInterfaceMapping",
    "RepositoryInspector",
    "RepositoryLimitsExceededError",
    "RepositoryStructureSummary",
    "get_sample_input_contract_json",
    "get_sample_output_contract_json",
]

