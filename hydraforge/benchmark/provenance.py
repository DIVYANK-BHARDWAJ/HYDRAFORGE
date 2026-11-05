"""Provenance, Threshold Metadata, and Cryptographic Fingerprinting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ThresholdMetadata:
    """Provenance for an organizer-defined flood event threshold."""
    catchment_id: str
    percentile: float
    threshold_value: float
    units: str
    source_split: str  # Must be an approved reference split (e.g., 'train')
    source_start_date: str
    source_end_date: str
    sample_count: int
    calculation_method: str = "empirical_quantile_weibull"
    is_provisional: bool = True
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SplitManifest:
    """Immutable record of split partition counts, catchment sets, and hashes."""
    split_name: str
    case_count: int
    catchment_count: int
    catchment_ids: List[str]
    input_records_hash: str
    label_records_hash: Optional[str] = None  # None for participant-facing manifests
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 hexadecimal digest of a physical file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_object_sha256(data: Any) -> str:
    """Compute deterministic SHA-256 hash of a JSON-serializable Python structure."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

