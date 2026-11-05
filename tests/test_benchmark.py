"""Unit tests for HYDRAFORGE Benchmark Infrastructure and Adapters."""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from hydraforge.benchmark.config import BenchmarkConfig
from hydraforge.benchmark.loader import (
    CaravanDatasetAdapter,
    OrganizerBenchmarkLoader,
    ParticipantBenchmarkLoader,
    TabularDatasetAdapter,
)
from hydraforge.benchmark.provenance import compute_object_sha256
from hydraforge.benchmark.split_manager import SplitManager
from hydraforge.benchmark.synthetic import generate_synthetic_benchmark
from hydraforge.benchmark.validation import (
    DataValidationError,
    LeakageAuditReport,
    LeakageError,
    audit_splits_for_leakage,
    validate_units,
)


def test_unit_validation():
    # Valid units
    validate_units("discharge", "m3/s")
    validate_units("streamflow", "mm/d")
    validate_units("precipitation", "mm")
    validate_units("temperature", "degC")

    # Invalid / ambiguous units
    with pytest.raises(DataValidationError, match="Unsupported discharge units"):
        validate_units("discharge", "gallons_per_minute")

    with pytest.raises(DataValidationError, match="Unsupported precipitation units"):
        validate_units("precipitation", "inches_per_hour")

    with pytest.raises(DataValidationError, match="Missing or ambiguous units"):
        validate_units("discharge", "")


def test_tabular_dataset_adapter_csv_and_duplicates(tmp_path: Path):
    # Valid CSV
    valid_csv = tmp_path / "valid.csv"
    df_valid = pd.DataFrame({
        "catchment_id": ["B1", "B1", "B2", "B2"],
        "date": ["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-02"],
        "discharge": [10.0, 12.0, 5.0, 6.0],
        "precipitation": [0.0, 5.0, 1.0, 2.0],
        "temperature": [15.0, 14.0, 10.0, 11.0]
    })
    df_valid.to_csv(valid_csv, index=False)

    adapter = TabularDatasetAdapter(file_format="csv")
    loaded = adapter.load_timeseries(valid_csv)
    assert len(loaded) == 4
    assert "date" in loaded.columns

    # Duplicate records detection
    dup_csv = tmp_path / "dup.csv"
    df_dup = pd.DataFrame({
        "catchment_id": ["B1", "B1"],  # duplicate key
        "date": ["2026-01-01", "2026-01-01"],
        "discharge": [10.0, 10.5],
        "precipitation": [0.0, 0.0],
        "temperature": [15.0, 15.0]
    })
    df_dup.to_csv(dup_csv, index=False)
    with pytest.raises(DataValidationError, match="Detected 1 duplicate"):
        adapter.load_timeseries(dup_csv)

    # Negative discharge detection
    neg_csv = tmp_path / "neg.csv"
    df_neg = pd.DataFrame({
        "catchment_id": ["B1"],
        "date": ["2026-01-01"],
        "discharge": [-5.0],
        "precipitation": [0.0],
        "temperature": [15.0]
    })
    df_neg.to_csv(neg_csv, index=False)
    with pytest.raises(DataValidationError, match="Detected negative discharge"):
        adapter.load_timeseries(neg_csv)


def test_caravan_adapter_handles_absent_files(tmp_path: Path):
    empty_dir = tmp_path / "caravan_empty"
    adapter = CaravanDatasetAdapter(caravan_root_dir=empty_dir)
    assert not adapter.genuine_files_present

    with pytest.raises(FileNotFoundError, match="Caravan dataset files are not installed"):
        adapter.load_timeseries(empty_dir / "timeseries")


def test_leakage_audit_detects_catchment_leakage():
    train_cases = [{"catchment_id": "B1", "forecast_origin": "2026-01-01T00:00:00Z"}]
    val_cases = [{"catchment_id": "B2", "forecast_origin": "2026-01-02T00:00:00Z"}]
    test_a_cases = [{"case_id": "ca1", "catchment_id": "B1", "forecast_origin": "2026-02-01T00:00:00Z"}]
    # Test B contains B1 which is also in training!
    test_b_cases = [{"catchment_id": "B1", "forecast_origin": "2026-02-01T00:00:00Z"}]
    test_c_cases = []

    audit = audit_splits_for_leakage(train_cases, val_cases, test_a_cases, test_b_cases, test_c_cases)
    assert not audit.is_leakage_free
    assert audit.catchment_overlap_count == 1
    assert any("CRITICAL CATCHMENT LEAKAGE" in w for w in audit.warnings)


def test_leakage_audit_detects_temporal_leakage():
    # Training origin is 2026-03-01
    train_cases = [{"catchment_id": "B1", "forecast_origin": "2026-03-01T00:00:00Z"}]
    val_cases = []
    # Test A origin is 2026-02-01 (preceding or overlapping training!)
    test_a_cases = [{"case_id": "ca1", "catchment_id": "B1", "forecast_origin": "2026-02-01T00:00:00Z"}]
    test_b_cases = [{"catchment_id": "B_UNSEEN", "forecast_origin": "2026-03-02T00:00:00Z"}]
    test_c_cases = []

    audit = audit_splits_for_leakage(train_cases, val_cases, test_a_cases, test_b_cases, test_c_cases)
    assert not audit.is_leakage_free
    assert audit.temporal_leakage_detected
    assert any("CRITICAL TEMPORAL LEAKAGE" in w for w in audit.warnings)


def test_leakage_audit_detects_unpaired_corruptions():
    train_cases = [{"catchment_id": "B1", "forecast_origin": "2026-01-01T00:00:00Z"}]
    test_a_cases = [{"case_id": "clean_1", "catchment_id": "B1", "forecast_origin": "2026-02-01T00:00:00Z"}]
    test_b_cases = [{"catchment_id": "B_UNSEEN", "forecast_origin": "2026-02-01T00:00:00Z"}]
    # Test C references non-existent clean case
    test_c_cases = [{"case_id": "corr_1", "clean_case_id": "clean_NONEXISTENT", "catchment_id": "B1"}]

    audit = audit_splits_for_leakage(train_cases, [], test_a_cases, test_b_cases, test_c_cases)
    assert not audit.is_leakage_free
    assert not audit.corrupted_cases_paired_correctly
    assert audit.unpaired_corrupted_cases == 1


def test_synthetic_benchmark_deterministic_generation(tmp_path: Path):
    path_run1 = tmp_path / "bench1"
    path_run2 = tmp_path / "bench2"

    cfg = BenchmarkConfig(random_seed=123)
    sum1, audit1 = generate_synthetic_benchmark(path_run1, cfg)
    sum2, audit2 = generate_synthetic_benchmark(path_run2, cfg)

    assert audit1.is_leakage_free
    assert audit2.is_leakage_free
    assert sum1["manifests"]["test_a"]["input_records_hash"] == sum2["manifests"]["test_a"]["input_records_hash"]
    assert sum1["manifests"]["test_b"]["input_records_hash"] == sum2["manifests"]["test_b"]["input_records_hash"]


def test_synthetic_benchmark_corruption_preserves_ground_truth(tmp_path: Path):
    bench_dir = tmp_path / "bench"
    generate_synthetic_benchmark(bench_dir, BenchmarkConfig(random_seed=42))

    loader = OrganizerBenchmarkLoader(bench_dir)
    test_a_lbls = loader.load_ground_truth("test_a")
    test_c_lbls = loader.load_ground_truth("test_c")

    clean_map = {(l.case_id, l.horizon): l.true_discharge for l in test_a_lbls}

    for c_lbl in test_c_lbls:
        clean_target = clean_map.get((c_lbl.clean_case_id, c_lbl.horizon))
        assert clean_target is not None
        # Ground truth label discharge MUST NOT be modified under corruption!
        assert c_lbl.true_discharge == clean_target

