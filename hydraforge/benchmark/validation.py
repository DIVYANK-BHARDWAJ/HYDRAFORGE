"""Dataset Validation, Unit Checking, and Machine-Readable Leakage Audits."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from hydraforge.benchmark.config import (
    SUPPORTED_DISCHARGE_UNITS,
    SUPPORTED_PRECIPITATION_UNITS,
    SUPPORTED_TEMPERATURE_UNITS,
)


class DataValidationError(Exception):
    """Raised when dataset ingestion or split construction violates integrity constraints."""
    pass


class LeakageError(Exception):
    """Raised when data leakage across benchmark splits is detected."""
    pass


@dataclass
class LeakageAuditReport:
    """Comprehensive, machine-readable audit report on benchmark integrity."""
    timestamp: str
    is_leakage_free: bool
    train_catchments: List[str]
    test_b_catchments: List[str]
    catchment_overlap_count: int
    temporal_leakage_detected: bool
    overlapping_target_windows: int
    corrupted_cases_paired_correctly: bool
    unpaired_corrupted_cases: int
    details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def validate_units(
    variable_name: str,
    units: str
) -> None:
    """Ensure units match canonical hydrological standards; reject ambiguous units."""
    if not units or not str(units).strip():
        raise DataValidationError(f"Missing or ambiguous units for variable '{variable_name}'")

    clean_units = str(units).strip()
    if variable_name in ("discharge", "streamflow", "target_discharge"):
        if clean_units not in SUPPORTED_DISCHARGE_UNITS:
            raise DataValidationError(
                f"Unsupported discharge units '{clean_units}'. Permitted: {sorted(SUPPORTED_DISCHARGE_UNITS)}"
            )
    elif variable_name in ("precipitation", "precip", "rain"):
        if clean_units not in SUPPORTED_PRECIPITATION_UNITS:
            raise DataValidationError(
                f"Unsupported precipitation units '{clean_units}'. Permitted: {sorted(SUPPORTED_PRECIPITATION_UNITS)}"
            )
    elif variable_name in ("temperature", "temp"):
        if clean_units not in SUPPORTED_TEMPERATURE_UNITS:
            raise DataValidationError(
                f"Unsupported temperature units '{clean_units}'. Permitted: {sorted(SUPPORTED_TEMPERATURE_UNITS)}"
            )


def audit_splits_for_leakage(
    train_cases: Sequence[Dict[str, Any]],
    val_cases: Sequence[Dict[str, Any]],
    test_a_cases: Sequence[Dict[str, Any]],
    test_b_cases: Sequence[Dict[str, Any]],
    test_c_cases: Sequence[Dict[str, Any]],
) -> LeakageAuditReport:
    """Perform a rigorous, multi-point leakage audit across all benchmark partitions."""
    warnings: List[str] = []
    is_free = True

    # 1. Catchment Leakage in Test B
    train_catchments: Set[str] = {c["catchment_id"] for c in train_cases}
    val_catchments: Set[str] = {c["catchment_id"] for c in val_cases}
    test_b_catchments: Set[str] = {c["catchment_id"] for c in test_b_cases}

    train_and_val = train_catchments.union(val_catchments)
    b_overlap = train_and_val.intersection(test_b_catchments)

    if b_overlap:
        is_free = False
        warnings.append(
            f"CRITICAL CATCHMENT LEAKAGE: {len(b_overlap)} Test B catchments present in training/validation: {sorted(b_overlap)}"
        )

    # 2. Temporal Leakage in Test A
    # Max training origin per catchment must strictly precede min Test A origin
    temporal_leakage = False
    train_max_dates: Dict[str, str] = {}
    for c in train_cases:
        cid = c["catchment_id"]
        origin = c["forecast_origin"]
        if cid not in train_max_dates or origin > train_max_dates[cid]:
            train_max_dates[cid] = origin

    overlapping_targets = 0
    for c in test_a_cases:
        cid = c["catchment_id"]
        origin = c["forecast_origin"]
        if cid in train_max_dates:
            if origin <= train_max_dates[cid]:
                temporal_leakage = True
                overlapping_targets += 1
                warnings.append(
                    f"CRITICAL TEMPORAL LEAKAGE: Test A case '{c.get('case_id')}' origin {origin} "
                    f"<= Training max origin {train_max_dates[cid]} for catchment {cid}"
                )

    if temporal_leakage:
        is_free = False

    # 3. Test C paired corruption check
    clean_case_ids: Set[str] = {c["case_id"] for c in test_a_cases}
    unpaired_c = 0
    for c in test_c_cases:
        clean_ref = c.get("clean_case_id")
        if not clean_ref or clean_ref not in clean_case_ids:
            unpaired_c += 1
            warnings.append(
                f"CORRUPTION INTEGRITY FLAW: Test C case '{c.get('case_id')}' references missing clean case '{clean_ref}'"
            )

    if unpaired_c > 0:
        is_free = False

    return LeakageAuditReport(
        timestamp=datetime.utcnow().isoformat(),
        is_leakage_free=is_free,
        train_catchments=sorted(train_catchments),
        test_b_catchments=sorted(test_b_catchments),
        catchment_overlap_count=len(b_overlap),
        temporal_leakage_detected=temporal_leakage,
        overlapping_target_windows=overlapping_targets,
        corrupted_cases_paired_correctly=(unpaired_c == 0),
        unpaired_corrupted_cases=unpaired_c,
        details={
            "train_case_count": len(train_cases),
            "val_case_count": len(val_cases),
            "test_a_case_count": len(test_a_cases),
            "test_b_case_count": len(test_b_cases),
            "test_c_case_count": len(test_c_cases),
        },
        warnings=warnings
    )

