"""
tests/test_scoring_end_to_end.py
End-to-End Workflow Demonstration for Phase 5C:
From Participant Submission & Dynamic Discovery through Secure Worker Execution,
Hidden-Label Validation, Six-Axis Scoring, and Leaderboard Update.

NOTICE:
Synthetic data and developer-simulated participant model are used exclusively
for software integration and regression testing. These results represent
software verification outcomes, NOT genuine hydrological model performance.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

from hydraforge.benchmark.case_manager import BenchmarkCaseManager
from hydraforge.benchmark.config import BenchmarkConfig
from hydraforge.benchmark.synthetic import generate_synthetic_benchmark, SYNTHETIC_BANNER
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
from hydraforge.evaluation.pipeline import BenchmarkEvaluationPipeline, ComprehensiveEvaluationReport
from hydraforge.schema import PredictionRecord
from hydraforge.worker.container_executor import ContainerExecutor
from hydraforge.worker.worker_manager import WorkerManager
from hydraforge.worker.worker_models import (
    ExecutionTelemetry,
    WorkerContext,
    WorkerExecutionResult,
    WorkerResourceLimits,
    WorkerState,
)


def test_complete_end_to_end_synthetic_scoring_workflow(tmp_path: Path):
    """
    Demonstrates complete lifecycle:
    Submission -> Immutable Commit -> Discovery -> Organizer Approval ->
    Isolated Worker -> Input Prep -> Model Execution -> Prediction Validation ->
    Hidden-Label Six-Axis Scoring -> Final Report -> DB Persistence -> Leaderboard Update.
    """
    # 1. Setup Synthetic Benchmark Environment
    benchmark_dir = tmp_path / "synthetic_benchmark"
    generate_synthetic_benchmark(benchmark_dir)

    # 2. Construct Developer Participant Model with Nonstandard Repository Structure
    # models/hydro_ensemble/run_stream_inference.py
    repo_dir = tmp_path / "participant_repo"
    code_dir = repo_dir / "models" / "hydro_ensemble"
    code_dir.mkdir(parents=True, exist_ok=True)

    script_path = code_dir / "run_stream_inference.py"
    script_path.write_text(
        """
import json
import sys
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-inputs", required=True)
    parser.add_argument("--forecasts-output", required=True)
    args = parser.parse_args()

    with open(args.data_inputs, "r") as f:
        data = json.load(f)

    cases = data.get("cases", data)
    predictions = []

    for c in cases:
        case_id = c["case_id"]
        cid = c["catchment_id"]
        origin = c["forecast_origin"]
        horizons = c["horizons"]
        history = c.get("discharge_history", [15.0])
        base_val = history[-1] if history else 15.0

        area = c.get("attributes", {}).get("area_km2", 100.0)
        q_base = area * 0.05
        precip = c.get("forcing_history", {}).get("precipitation_mm", [0.0])
        recent_rain = precip[-1] if precip else 0.0

        for h in horizons:
            # Physical storage recession with rain runoff
            receded = (0.89 ** h) * base_val + (1.0 - (0.89 ** h)) * q_base
            runoff = (area * 0.008) * (recent_rain / (h + 1))
            q_pred = round(max(0.1, receded + runoff), 2)
            predictions.append({
                "case_id": case_id,
                "catchment_id": cid,
                "forecast_origin": origin,
                "horizon": int(h),
                "predicted_discharge": q_pred,
                "high_flow_probability": 0.08,
                "extreme_flow_probability": 0.01,
                "prediction_interval_lower": round(q_pred * 0.7, 2),
                "prediction_interval_upper": round(q_pred * 1.3, 2),
                "nominal_interval_coverage": 0.90
            })

    with open(args.forecasts_output, "w") as f:
        json.dump(predictions, f, indent=2)

if __name__ == "__main__":
    main()
""",
        encoding="utf-8",
    )

    # 3. Dynamic Discovery Phase (Synthesize verified report from Phase 5A)
    commit_sha = "c" * 40
    discovery_report = DiscoveryReport(
        discovery_id="disc_e2e_001",
        submission_id="sub_e2e_flow_team",
        repository_url="https://github.com/flow-team/neural-hydro",
        commit_sha=commit_sha,
        created_at=datetime.now(timezone.utc).isoformat(),
        status=DiscoveryStatus.DISCOVERY_SUCCESS,
        interface_status=InterfaceStatus.INTERFACE_IDENTIFIED,
        confidence=ConfidenceLevel.HIGH,
        structure=RepositoryStructureSummary(
            total_files=5,
            source_file_count=1,
        ),
        proposed_interface_mapping=ProposedInterfaceMapping(
            interface_type="CLI_FILE_IN_OUT",
            executable_target="models/hydro_ensemble/run_stream_inference.py",
            input_mechanism="--data-inputs",
            output_mechanism="--forecasts-output",
        ),
    )

    # 4. Mock Isolated Container Execution (Enforcing Container Boundary Simulation)
    class SimulatedContainerExecutor(ContainerExecutor):
        def is_isolation_backend_available(self) -> bool:
            return True

        def execute_in_container(
            self,
            command_args,
            repo_dir,
            input_dir,
            output_dir,
            scratch_dir,
            limits,
            input_hash,
            used_adapter,
        ):
            # Assert label shielding: hidden labels are NEVER mounted into container
            assert "labels" not in str(input_dir)
            assert "labels" not in str(scratch_dir)

            # Execute python model script inside simulated isolated worker sandbox
            import subprocess

            cmd = [
                "python",
                str(repo_dir / "models" / "hydro_ensemble" / "run_stream_inference.py"),
                "--data-inputs",
                str(input_dir / "cases.json"),
                "--forecasts-output",
                str(output_dir / "predictions.json"),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            assert res.returncode == 0

            telemetry = ExecutionTelemetry(
                exit_code=0,
                wall_clock_seconds=1.45,
                peak_memory_mb=180.5,
                cpu_usage_percent=45.0,
                stdout="Inference executed successfully.",
                stderr="",
                input_hash=input_hash,
                output_hash=None,
                termination_reason="NORMAL_EXIT",
            )
            return WorkerState.EXECUTION_SUCCESS, telemetry, "test_container_sim"

    worker_mgr = WorkerManager(container_executor=SimulatedContainerExecutor())

    # 5. Database Setup
    from hydraforge.database.migrations import apply_migrations
    db_file = tmp_path / "evaluation.db"
    db_mgr = DatabaseManager(db_file)
    apply_migrations(db_mgr)
    db_repo = EvaluationRepository(db_mgr)

    # 6. Execute Full Pipeline
    pipeline = BenchmarkEvaluationPipeline(
        benchmark_root=benchmark_dir,
        worker_manager=worker_mgr,
        db_repository=db_repo,
        scratch_dir=tmp_path / "scratch",
    )

    eval_report: ComprehensiveEvaluationReport = pipeline.execute_evaluation(
        submission_id="sub_e2e_flow_team",
        team_name="HydroDynamics Lab",
        repo_dir=repo_dir,
        commit_sha=commit_sha,
        discovery_report=discovery_report,
        repository_url="https://github.com/flow-team/neural-hydro",
        eval_splits=("test_a", "test_b", "test_c"),
        resource_limits=WorkerResourceLimits(cpu_limit=2.0, memory_limit_mb=2048.0),
        is_organizer_approved=True,
        is_trusted_developer_fixture=True,
    )

    # 7. Verification of Evaluation Outcomes
    assert eval_report.status == "COMPLETED"
    assert eval_report.total_score is not None
    assert 0.0 <= eval_report.total_score <= 100.0
    assert eval_report.is_eligible_for_leaderboard is True

    # Check that all 6 dimensions are present in report
    scores = eval_report.six_axis_scores
    assert "forecast_skill" in scores
    assert "event_detection" in scores
    assert "generalization" in scores
    assert "calibration_and_uncertainty" in scores
    assert "robustness" in scores
    assert "efficiency" in scores

    assert eval_report.total_score > 0.0
    assert scores["event_detection"]["points_awarded"] > 0
    assert scores["calibration_and_uncertainty"]["points_awarded"] > 0
    assert scores["efficiency"]["points_awarded"] > 0

    # Check split summaries
    splits = eval_report.test_split_details
    assert "test_a" in splits
    assert "test_b" in splits
    assert "test_c" in splits

    # Check validation report
    val = eval_report.validation_report
    assert val["is_valid"] is True
    assert val["invalid_count"] == 0
    assert val["missing_count"] == 0
    assert val["duplicate_count"] == 0

    # 8. Check JSON and CSV exports
    json_export = eval_report.to_json()
    assert "HydroDynamics Lab" in json_export
    assert eval_report.commit_sha in json_export

    csv_export = eval_report.to_csv()
    assert "HydroDynamics Lab" in csv_export
    assert "forecast_skill" in csv_export

    # 9. Verify Database Persistence & Leaderboard Query
    persisted_job = db_repo.get_job(eval_report.job_id)
    assert persisted_job is not None
    assert persisted_job["job_status"] == "COMPLETED"
    assert persisted_job["final_score"] == pytest.approx(eval_report.total_score, abs=0.01)

    persisted_result = db_repo.get_evaluation_result(eval_report.job_id)
    assert persisted_result is not None
    assert persisted_result["total_score"] == pytest.approx(eval_report.total_score, abs=0.01)

    # Check official leaderboard
    leaderboard = db_repo.get_leaderboard()
    assert len(leaderboard) == 1
    assert leaderboard[0]["team_name"] == "HydroDynamics Lab"
    assert leaderboard[0]["job_id"] == eval_report.job_id
    assert leaderboard[0]["total_score"] == eval_report.total_score
    assert leaderboard[0]["commit_sha"] == commit_sha
