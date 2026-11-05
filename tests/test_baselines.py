"""Unit tests for HYDRAFORGE Reference Baselines."""

import json
from pathlib import Path
import pytest

from hydraforge.baselines.persistence import PersistenceBaseline
from hydraforge.baselines.climatology import ClimatologyBaseline
from hydraforge.baselines.gbdt import GBDTBaseline
from hydraforge.benchmark.loader import OrganizerBenchmarkLoader, ParticipantBenchmarkLoader
from hydraforge.benchmark.synthetic import generate_synthetic_benchmark
from hydraforge.schema import (
    BenchmarkInputRecord,
    ContractConfig,
    GroundTruthLabel,
    validate_predictions,
)


@pytest.fixture(scope="module")
def benchmark_data(tmp_path_factory):
    bench_dir = tmp_path_factory.mktemp("baseline_bench")
    generate_synthetic_benchmark(bench_dir)
    p_loader = ParticipantBenchmarkLoader(bench_dir / "inputs")
    o_loader = OrganizerBenchmarkLoader(bench_dir)

    with open(bench_dir / "metadata" / "catchments.json", "r") as f:
        meta = json.load(f)

    return {
        "train_in": p_loader.load_inputs("train"),
        "train_lbl": o_loader.load_ground_truth("train"),
        "test_a_in": p_loader.load_inputs("test_a"),
        "test_a_lbl": o_loader.load_ground_truth("test_a"),
        "test_c_in": p_loader.load_inputs("test_c"),
        "meta": meta
    }


def test_persistence_baseline(benchmark_data):
    model = PersistenceBaseline()
    model.fit(benchmark_data["train_in"], benchmark_data["train_lbl"])
    preds = model.predict(benchmark_data["test_a_in"], benchmark_data["meta"])

    # Output validation against Phase 1 contract schema
    validate_predictions(preds, benchmark_data["test_a_in"], ContractConfig())

    assert len(preds) == len(benchmark_data["test_a_in"]) * 3
    # Check predictions match last observation
    pred_map = {(p.case_id, p.horizon): p for p in preds}
    for inp in benchmark_data["test_a_in"]:
        p1 = pred_map[(inp.case_id, 1)]
        assert p1.predicted_discharge == round(inp.discharge_history[-1], 3)
        assert p1.prediction_interval_lower <= p1.prediction_interval_upper


def test_persistence_handles_missing_discharge():
    model = PersistenceBaseline()
    model.fallback_discharge = 15.0
    rec = BenchmarkInputRecord(
        case_id="ungauged_case",
        catchment_id="B_UNGAUGED",
        forecast_origin="2026-05-01T00:00:00Z",
        horizons=[1, 3],
        discharge_history=[]  # Empty discharge history
    )
    preds = model.predict([rec])
    assert len(preds) == 2
    assert preds[0].predicted_discharge == 15.0


def test_climatology_baseline(benchmark_data):
    model = ClimatologyBaseline()
    model.fit(benchmark_data["train_in"], benchmark_data["train_lbl"])
    preds = model.predict(benchmark_data["test_a_in"], benchmark_data["meta"])

    validate_predictions(preds, benchmark_data["test_a_in"], ContractConfig())
    for p in preds:
        assert p.predicted_discharge > 0.0
        assert 0.0 <= p.high_flow_probability <= 1.0
        assert 0.0 <= p.extreme_flow_probability <= 1.0
        assert p.prediction_interval_lower <= p.prediction_interval_upper


def test_gbdt_baseline(benchmark_data, tmp_path: Path):
    model = GBDTBaseline(random_seed=42)
    model.fit(benchmark_data["train_in"], benchmark_data["train_lbl"])
    preds = model.predict(benchmark_data["test_a_in"], benchmark_data["meta"])

    validate_predictions(preds, benchmark_data["test_a_in"], ContractConfig())
    assert len(preds) == len(benchmark_data["test_a_in"]) * 3
    for p in preds:
        assert p.predicted_discharge >= 0.0
        assert p.prediction_interval_lower <= p.prediction_interval_upper
        assert 0.0 <= p.high_flow_probability <= 1.0

    # Test serialization and artifact size
    model_save_path = tmp_path / "gbdt_model.json"
    model.save(model_save_path)
    assert model_save_path.exists()
    assert model.artifact_size_mb > 0.0


def test_baseline_train_test_separation(benchmark_data):
    # Ensure baseline models can be trained without ANY access to test_a or test_b labels
    model = GBDTBaseline()
    # Fit only on train
    model.fit(benchmark_data["train_in"], benchmark_data["train_lbl"])
    # Predict on corrupted Test C inputs
    preds_c = model.predict(benchmark_data["test_c_in"], benchmark_data["meta"])
    validate_predictions(preds_c, benchmark_data["test_c_in"], ContractConfig())

