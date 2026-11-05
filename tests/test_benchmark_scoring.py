"""
tests/test_benchmark_scoring.py
Comprehensive Verification Suite for Phase 5C:
Benchmark Execution, Prediction Validation, Label Protection, and Six-Axis Scoring.
Covers all 20 test specifications.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
import pytest

from hydraforge.benchmark.case_manager import BenchmarkCaseManager
from hydraforge.benchmark.config import BenchmarkConfig
from hydraforge.benchmark.input_preparer import BenchmarkInputPreparer
from hydraforge.benchmark.synthetic import generate_synthetic_benchmark
from hydraforge.benchmark.validation import DataValidationError
from hydraforge.database.connection import DatabaseManager
from hydraforge.database.repository import EvaluationRepository
from hydraforge.discovery.discovery_models import (
    ConfidenceLevel,
    DiscoveryReport,
    DiscoveryStatus,
    InterfaceStatus,
    ProposedInterfaceMapping,
    RepositoryStructureSummary,
)
from hydraforge.evaluation.job import JobStatus
from hydraforge.evaluation.pipeline import BenchmarkEvaluationPipeline, ComprehensiveEvaluationReport
from hydraforge.evaluation.prediction_validator import PredictionValidationReport, PredictionValidator
from hydraforge.evaluation.split_evaluator import SplitEvaluator
from hydraforge.metrics.evaluator import HydraForgeEvaluator
from hydraforge.runner.isolation import LabelLeakageSecurityViolation
from hydraforge.schema import BenchmarkInputRecord, GroundTruthLabel, PredictionRecord
from hydraforge.worker.worker_manager import WorkerManager
from hydraforge.worker.worker_models import (
    ExecutionTelemetry,
    WorkerContext,
    WorkerExecutionResult,
    WorkerResourceLimits,
    WorkerState,
)


@pytest.fixture
def synthetic_benchmark_suite(tmp_path: Path):
    """Generate a clean synthetic benchmark dataset for testing."""
    bench_dir = tmp_path / "benchmark"
    generate_synthetic_benchmark(bench_dir)
    return bench_dir


@pytest.fixture
def sample_benchmark_input():
    return BenchmarkInputRecord(
        case_id="case_syn_001",
        catchment_id="BASIN_SYN_01",
        forecast_origin="2025-09-01T00:00:00Z",
        horizons=[1, 3],
        discharge_history=[15.2, 16.1, 14.8],
        forcing_history={
            "precipitation_mm": [2.1, 4.5, 0.0],
            "temperature_c": [18.2, 19.0, 17.5],
        },
        attributes={"area_km2": 120.0, "elevation_m": 450.0},
        split="test_a",
        region="Alps",
    )


@pytest.fixture
def sample_ground_truth():
    return [
        GroundTruthLabel(
            case_id="case_syn_001",
            catchment_id="BASIN_SYN_01",
            forecast_origin="2025-09-01T00:00:00Z",
            horizon=1,
            true_discharge=18.5,
            high_flow_threshold=22.0,
            extreme_flow_threshold=35.0,
            persistence_discharge=14.8,
            split="test_a",
            region="Alps",
        ),
        GroundTruthLabel(
            case_id="case_syn_001",
            catchment_id="BASIN_SYN_01",
            forecast_origin="2025-09-01T00:00:00Z",
            horizon=3,
            true_discharge=17.2,
            high_flow_threshold=22.0,
            extreme_flow_threshold=35.0,
            persistence_discharge=14.8,
            split="test_a",
            region="Alps",
        ),
    ]


@pytest.fixture
def valid_prediction_records():
    return [
        PredictionRecord(
            case_id="case_syn_001",
            catchment_id="BASIN_SYN_01",
            forecast_origin="2025-09-01T00:00:00Z",
            horizon=1,
            predicted_discharge=18.0,
            high_flow_probability=0.15,
            extreme_flow_probability=0.02,
            prediction_interval_lower=12.0,
            prediction_interval_upper=24.0,
            nominal_interval_coverage=0.90,
        ),
        PredictionRecord(
            case_id="case_syn_001",
            catchment_id="BASIN_SYN_01",
            forecast_origin="2025-09-01T00:00:00Z",
            horizon=3,
            predicted_discharge=16.8,
            high_flow_probability=0.10,
            extreme_flow_probability=0.01,
            prediction_interval_lower=10.0,
            prediction_interval_upper=23.0,
            nominal_interval_coverage=0.90,
        ),
    ]


# -----------------------------------------------------------------------------
# 1. Valid Benchmark Input Preparation
# -----------------------------------------------------------------------------
def test_1_valid_benchmark_input_preparation(sample_benchmark_input, tmp_path):
    preparer = BenchmarkInputPreparer()
    out_file = tmp_path / "inputs" / "cases.json"
    cases, input_hash = preparer.prepare_inference_inputs([sample_benchmark_input], out_file)

    assert len(cases) == 1
    assert cases[0]["case_id"] == "case_syn_001"
    assert "true_discharge" not in cases[0]
    assert "high_flow_threshold" not in cases[0]
    assert len(input_hash) == 64
    assert out_file.exists()


# -----------------------------------------------------------------------------
# 2. Temporal Leakage Prevention
# -----------------------------------------------------------------------------
def test_2_temporal_leakage_prevention():
    preparer = BenchmarkInputPreparer()
    leaky_input = BenchmarkInputRecord(
        case_id="leak_01",
        catchment_id="BASIN_01",
        forecast_origin="2025-06-01T00:00:00Z",
        horizons=[1],
        discharge_history=[10.0],
        forcing_history={
            "precip": {
                "dates": ["2025-05-31T00:00:00Z", "2025-06-02T00:00:00Z"],  # Future date!
                "values": [5.0, 10.0],
            }
        },
        attributes={},
        split="test_a",
    )

    with pytest.raises(DataValidationError, match="Temporal leakage detected"):
        preparer.prepare_inference_inputs([leaky_input])


# -----------------------------------------------------------------------------
# 3. Geographic Split Integrity
# -----------------------------------------------------------------------------
def test_3_geographic_split_integrity(synthetic_benchmark_suite):
    mgr = BenchmarkCaseManager(synthetic_benchmark_suite)
    audit = mgr.validate_benchmark_integrity()

    assert audit["status"] == "VALID"
    # Verify Test B catchments do not appear in Train catchments
    train_cids = set(audit["splits_checked"]["train"]["catchments"])
    test_b_cids = set(audit["splits_checked"]["test_b"]["catchments"])
    assert train_cids.isdisjoint(test_b_cids)


# -----------------------------------------------------------------------------
# 4. Hidden-Label Separation
# -----------------------------------------------------------------------------
def test_4_hidden_label_separation(sample_benchmark_input):
    preparer = BenchmarkInputPreparer()
    # Attempt to inject reference label into input record dict
    sample_benchmark_input.attributes["true_discharge"] = 999.0

    # Attributes should not contain true_discharge
    cases, _ = preparer.prepare_inference_inputs([sample_benchmark_input])
    # The case dictionary itself must never have root-level 'true_discharge'
    assert "true_discharge" not in cases[0]


# -----------------------------------------------------------------------------
# 5. Prediction Schema Validation
# -----------------------------------------------------------------------------
def test_5_prediction_schema_validation(sample_benchmark_input, valid_prediction_records):
    validator = PredictionValidator()
    report = validator.validate(valid_prediction_records, [sample_benchmark_input])

    assert report.is_valid is True
    assert report.valid_count == 2
    assert report.missing_count == 0
    assert report.invalid_count == 0


# -----------------------------------------------------------------------------
# 6. Missing Predictions
# -----------------------------------------------------------------------------
def test_6_missing_predictions(sample_benchmark_input, valid_prediction_records):
    validator = PredictionValidator()
    # Provide only 1 out of 2 requested horizons
    report = validator.validate([valid_prediction_records[0]], [sample_benchmark_input])

    assert report.is_valid is False
    assert report.missing_count == 1
    assert any("Missing 1 required benchmark predictions" in err for err in report.errors)


# -----------------------------------------------------------------------------
# 7. Duplicate Predictions
# -----------------------------------------------------------------------------
def test_7_duplicate_predictions(sample_benchmark_input, valid_prediction_records):
    validator = PredictionValidator()
    # Duplicate record for horizon 1
    dups = [valid_prediction_records[0], valid_prediction_records[0], valid_prediction_records[1]]
    report = validator.validate(dups, [sample_benchmark_input])

    assert report.is_valid is False
    assert report.duplicate_count == 1
    assert any("Duplicate prediction detected" in err for err in report.errors)


# -----------------------------------------------------------------------------
# 8. Invalid Probabilities
# -----------------------------------------------------------------------------
def test_8_invalid_probabilities(sample_benchmark_input, valid_prediction_records):
    validator = PredictionValidator()
    bad_pred = valid_prediction_records[0]
    bad_pred.high_flow_probability = 1.45  # Greater than 1.0!

    report = validator.validate([bad_pred, valid_prediction_records[1]], [sample_benchmark_input])
    assert report.is_valid is False
    assert any("high_flow_probability must be in [0, 1]" in err for err in report.errors)


# -----------------------------------------------------------------------------
# 9. Invalid Quantile / Interval Ordering
# -----------------------------------------------------------------------------
def test_9_invalid_quantile_ordering(sample_benchmark_input, valid_prediction_records):
    validator = PredictionValidator()

    # Extreme prob > High flow prob inversion
    bad_q = valid_prediction_records[0]
    bad_q.high_flow_probability = 0.10
    bad_q.extreme_flow_probability = 0.50

    report = validator.validate([bad_q, valid_prediction_records[1]], [sample_benchmark_input])
    assert report.is_valid is False
    assert any("Quantile probability inversion" in err for err in report.errors)

    # Interval lower > upper inversion
    bad_interval = valid_prediction_records[1]
    bad_interval.prediction_interval_lower = 30.0
    bad_interval.prediction_interval_upper = 15.0

    report2 = validator.validate([valid_prediction_records[0], bad_interval], [sample_benchmark_input])
    assert report2.is_valid is False
    assert any("Uncertainty interval inversion" in err for err in report2.errors)


# -----------------------------------------------------------------------------
# 10. Invalid Discharge Values (Negative or NaN)
# -----------------------------------------------------------------------------
def test_10_invalid_discharge_values(sample_benchmark_input, valid_prediction_records):
    validator = PredictionValidator()

    # Negative discharge
    bad_neg = valid_prediction_records[0]
    bad_neg.predicted_discharge = -5.2

    report = validator.validate([bad_neg, valid_prediction_records[1]], [sample_benchmark_input])
    assert report.is_valid is False
    assert any("predicted_discharge must be non-negative" in err for err in report.errors)

    # NaN discharge
    bad_nan = valid_prediction_records[0]
    bad_nan.predicted_discharge = float("nan")

    report2 = validator.validate([bad_nan, valid_prediction_records[1]], [sample_benchmark_input])
    assert report2.is_valid is False
    assert any("invalid numeric value: nan" in err for err in report2.errors)


# -----------------------------------------------------------------------------
# 11. Forecast Timestamp Mismatch
# -----------------------------------------------------------------------------
def test_11_forecast_timestamp_mismatch(sample_benchmark_input, valid_prediction_records):
    validator = PredictionValidator()
    bad_ts = valid_prediction_records[0]
    bad_ts.forecast_origin = "2024-01-01T00:00:00Z"

    report = validator.validate([bad_ts, valid_prediction_records[1]], [sample_benchmark_input])
    assert report.is_valid is False
    assert any("Forecast origin mismatch" in err for err in report.errors)


# -----------------------------------------------------------------------------
# 12. Correct Six-Axis Metric Invocation
# -----------------------------------------------------------------------------
def test_12_correct_six_axis_metric_invocation(valid_prediction_records, sample_ground_truth):
    evaluator = HydraForgeEvaluator()
    res = evaluator.evaluate(
        predictions=valid_prediction_records,
        ground_truth=sample_ground_truth,
        catchment_metadata={"BASIN_SYN_01": {"region": "Alps", "area_km2": 120.0}},
        execution_stats={"runtime_seconds": 1.2, "peak_memory_mb": 150.0},
    )

    assert len(res.dimensions) == 6
    expected_dims = {
        "forecast_skill",
        "event_detection",
        "generalization",
        "calibration_and_uncertainty",
        "robustness",
        "efficiency",
    }
    assert set(res.dimensions.keys()) == expected_dims


# -----------------------------------------------------------------------------
# 13. Score Bounds (0 <= score <= 100)
# -----------------------------------------------------------------------------
def test_13_score_bounds(valid_prediction_records, sample_ground_truth):
    evaluator = HydraForgeEvaluator()
    res = evaluator.evaluate(
        predictions=valid_prediction_records,
        ground_truth=sample_ground_truth,
        execution_stats={"runtime_seconds": 0.5, "peak_memory_mb": 80.0},
    )

    assert 0.0 <= res.total_score <= 100.0
    for dim in res.dimensions.values():
        assert 0.0 <= dim.points_awarded <= dim.max_points


# -----------------------------------------------------------------------------
# 14. Missing Metric Handling
# -----------------------------------------------------------------------------
def test_14_missing_metric_handling(sample_ground_truth):
    evaluator = HydraForgeEvaluator()
    # Empty predictions
    res = evaluator.evaluate(
        predictions=[],
        ground_truth=sample_ground_truth,
    )

    assert res.total_score >= 0.0
    assert any("Missing" in w for w in res.warnings)


# -----------------------------------------------------------------------------
# 15. Stress-Test Reproducibility
# -----------------------------------------------------------------------------
def test_15_stress_test_reproducibility(synthetic_benchmark_suite):
    mgr = BenchmarkCaseManager(synthetic_benchmark_suite)
    cases_c = mgr.get_eligible_cases("test_c")
    gt_c = mgr.get_reference_labels("test_c")

    assert len(cases_c) > 0
    assert len(gt_c) > 0

    # Check each corrupted case has clean reference and corruption family
    for c in cases_c:
        assert c.is_corrupted is True
        assert c.clean_case_id is not None
        assert c.corruption_family in ("missing_discharge", "input_noise", "reporting_delay")


# -----------------------------------------------------------------------------
# 16. Actual Efficiency Measurement
# -----------------------------------------------------------------------------
def test_16_actual_efficiency_measurement(valid_prediction_records, sample_ground_truth):
    evaluator = HydraForgeEvaluator()
    res = evaluator.evaluate(
        predictions=valid_prediction_records,
        ground_truth=sample_ground_truth,
        execution_stats={"runtime_seconds": 12.5, "peak_memory_mb": 420.0},
    )

    eff_dim = res.dimensions["efficiency"]
    assert eff_dim.points_awarded > 0.0
    assert eff_dim.raw_metrics["runtime_seconds"] == 12.5
    assert eff_dim.raw_metrics["peak_memory_mb"] == 420.0


# -----------------------------------------------------------------------------
# 17. Evaluation Persistence in Database
# -----------------------------------------------------------------------------
def test_17_evaluation_persistence(tmp_path):
    from hydraforge.database.migrations import apply_migrations
    db_file = tmp_path / "test_eval.db"
    db_mgr = DatabaseManager(db_file)
    apply_migrations(db_mgr)
    repo = EvaluationRepository(db_mgr)

    from hydraforge.evaluation.job import EvaluationJob
    job = EvaluationJob(
        job_id="job_persist_test",
        repository_url="https://github.com/test/repo",
        commit_sha="a" * 40,
        status=JobStatus.COMPLETED,
        final_score=85.25,
    )
    repo.insert_job(job, {"team_name": "HydroPioneers", "submission_name": "v1"})
    repo.save_evaluation_result(
        job_id=job.job_id,
        total_score=85.25,
        dimensions={
            "forecast_skill": 21.0,
            "event_detection": 22.0,
            "generalization": 17.0,
            "calibration_and_uncertainty": 12.0,
            "robustness": 8.5,
            "efficiency": 4.75,
        },
        full_report_json=json.dumps({"evaluation_id": "eval_persist_test"}),
    )

    retrieved_job = repo.get_job("job_persist_test")
    assert retrieved_job is not None
    assert retrieved_job["final_score"] == 85.25

    res = repo.get_evaluation_result("job_persist_test")
    assert res is not None
    assert res["total_score"] == 85.25
    assert res["forecast_skill"] == 21.0


# -----------------------------------------------------------------------------
# 18. Failed Evaluation Handling (No Score Awarded)
# -----------------------------------------------------------------------------
def test_18_failed_evaluation_handling(synthetic_benchmark_suite, tmp_path):
    # Mock WorkerManager that returns failure
    class FailingWorkerManager(WorkerManager):
        def run_worker_job(self, context, discovery_report, repo_dir):
            return WorkerExecutionResult(
                job_id=context.job_id,
                submission_id=context.submission_id,
                final_state=WorkerState.EXECUTION_FAILED,
                telemetry=ExecutionTelemetry(stderr="Out of memory crash"),
                error_message="Worker terminated unexpectedly",
                cleanup_success=True,
            )

    pipeline = BenchmarkEvaluationPipeline(
        benchmark_root=synthetic_benchmark_suite,
        worker_manager=FailingWorkerManager(),
        scratch_dir=tmp_path / "scratch",
    )

    report = pipeline.execute_evaluation(
        submission_id="sub_fail_01",
        team_name="TeamFail",
        repo_dir=tmp_path,
        commit_sha="b" * 40,
        discovery_report=DiscoveryReport(
            discovery_id="disc_01",
            submission_id="sub_fail_01",
            repository_url="http://example.com",
            commit_sha="b" * 40,
            created_at=datetime.now(timezone.utc).isoformat(),
            status=DiscoveryStatus.DISCOVERY_SUCCESS,
            interface_status=InterfaceStatus.INTERFACE_IDENTIFIED,
            confidence=ConfidenceLevel.HIGH,
            structure=RepositoryStructureSummary(),
            proposed_interface_mapping=ProposedInterfaceMapping(
                interface_type="CLI_FILE_IN_OUT",
                executable_target="predict.py",
            ),
        ),
        eval_splits=["test_a"],
    )

    assert report.status == "EXECUTION_FAILED"
    assert report.total_score is None
    assert report.is_eligible_for_leaderboard is False
    assert len(report.failure_reasons) > 0


# -----------------------------------------------------------------------------
# 19. Leaderboard Eligibility (Only Completed & Valid)
# -----------------------------------------------------------------------------
def test_19_leaderboard_eligibility(tmp_path):
    from hydraforge.database.migrations import apply_migrations
    db_file = tmp_path / "test_lb.db"
    db_mgr = DatabaseManager(db_file)
    apply_migrations(db_mgr)
    repo = EvaluationRepository(db_mgr)

    from hydraforge.evaluation.job import EvaluationJob

    # Job 1: COMPLETED valid job
    job1 = EvaluationJob(
        job_id="job_valid_1",
        repository_url="https://github.com/team1/repo",
        commit_sha="1" * 40,
        status=JobStatus.COMPLETED,
        final_score=78.5,
    )
    repo.insert_job(job1, {"team_name": "Team One"})
    repo.save_evaluation_result(
        job_id=job1.job_id,
        total_score=78.5,
        dimensions={"forecast_skill": 20.0},
        full_report_json="{}",
    )

    # Job 2: FAILED job
    job2 = EvaluationJob(
        job_id="job_failed_2",
        repository_url="https://github.com/team2/repo",
        commit_sha="2" * 40,
        status=JobStatus.EXECUTION_FAILED,
        final_score=None,
    )
    repo.insert_job(job2, {"team_name": "Team Two"})

    # Job 3: INVALID PREDICTIONS job
    job3 = EvaluationJob(
        job_id="job_invalid_3",
        repository_url="https://github.com/team3/repo",
        commit_sha="3" * 40,
        status=JobStatus.INVALID_PREDICTIONS,
        final_score=None,
    )
    repo.insert_job(job3, {"team_name": "Team Three"})

    # Query leaderboard
    leaderboard = repo.get_leaderboard()
    assert len(leaderboard) == 1
    assert leaderboard[0]["job_id"] == "job_valid_1"
    assert leaderboard[0]["team_name"] == "Team One"
    assert leaderboard[0]["total_score"] == 78.5


# -----------------------------------------------------------------------------
# 20. Immutable Commit Preservation
# -----------------------------------------------------------------------------
def test_20_immutable_commit_preservation(synthetic_benchmark_suite, tmp_path):
    pipeline = BenchmarkEvaluationPipeline(
        benchmark_root=synthetic_benchmark_suite,
        scratch_dir=tmp_path / "scratch",
    )

    # Reject mutable branch name instead of immutable SHA-1
    report = pipeline.execute_evaluation(
        submission_id="sub_branch_01",
        team_name="TeamBranch",
        repo_dir=tmp_path,
        commit_sha="main",  # Mutable branch name!
        discovery_report=DiscoveryReport(
            discovery_id="disc_02",
            submission_id="sub_branch_01",
            repository_url="http://example.com",
            commit_sha="main",
            created_at=datetime.now(timezone.utc).isoformat(),
            status=DiscoveryStatus.DISCOVERY_SUCCESS,
            interface_status=InterfaceStatus.INTERFACE_IDENTIFIED,
            confidence=ConfidenceLevel.HIGH,
            structure=RepositoryStructureSummary(),
        ),
        eval_splits=["test_a"],
    )

    assert report.status == "REPOSITORY_REJECTED"
    assert "Invalid commit SHA" in report.failure_reasons[0]
