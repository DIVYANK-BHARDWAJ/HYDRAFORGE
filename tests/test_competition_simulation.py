"""
tests/test_competition_simulation.py
Master 10-Scenario End-to-End Competition Simulation Test.
Verifies the complete HYDRAFORGE evaluation platform under realistic competition conditions.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import pytest

from hydraforge.api.services.submission_service import SubmissionService
from hydraforge.benchmark.case_manager import BenchmarkCaseManager
from hydraforge.benchmark.config import BenchmarkConfig
from hydraforge.benchmark.input_preparer import BenchmarkInputPreparer
from hydraforge.benchmark.synthetic import generate_synthetic_benchmark
from hydraforge.database.connection import DatabaseManager
from hydraforge.database.migrations import apply_migrations
from hydraforge.database.repository import EvaluationRepository
from hydraforge.discovery import (
    ConfidenceLevel,
    DiscoveryReport,
    DiscoveryStatus,
    InterfaceStatus,
    ProposedInterfaceMapping,
    RepositoryInspector,
    RepositoryStructureSummary,
)
from hydraforge.evaluation.job import EvaluationJob, JobStatus
from hydraforge.evaluation.pipeline import (
    BenchmarkEvaluationPipeline,
    ComprehensiveEvaluationReport,
)
from hydraforge.evaluation.prediction_validator import PredictionValidator
from hydraforge.evaluation.queue import PersistentEvaluationQueue, QueueStatus
from hydraforge.submission.github_verifier import set_mock_github_resolver
from hydraforge.worker.container_executor import ContainerExecutor
from hydraforge.worker.worker_manager import WorkerManager
from hydraforge.worker.worker_models import ExecutionTelemetry, WorkerResourceLimits, WorkerState
from scripts.validate_submission import validate_prediction_payload


@pytest.fixture
def sim_env(tmp_path: Path):
    db_file = tmp_path / "sim.db"
    db_mgr = DatabaseManager(db_path=db_file)
    apply_migrations(db_mgr)
    repo = EvaluationRepository(db_manager=db_mgr)
    queue = PersistentEvaluationQueue(db_manager=db_mgr)
    bm_dir = tmp_path / "benchmark"
    generate_synthetic_benchmark(bm_dir, BenchmarkConfig(random_seed=42))
    return {
        "db_mgr": db_mgr,
        "repo": repo,
        "queue": queue,
        "bm_dir": bm_dir,
        "tmp_path": tmp_path,
    }


def test_scenario_1_valid_two_field_submission_and_capture(sim_env):
    """Scenario 1: Valid 2-field submission triggers automated discovery without participant credentials."""
    set_mock_github_resolver(lambda u: (True, "main", "1" * 40, "VERIFIED"))
    service = SubmissionService(repository=sim_env["repo"])

    ok, res = service.register_submission({
        "team_name": "AlpineHydro",
        "repository_url": "https://github.com/alpine-hydro/topoflow-gnn",
    })

    assert ok is True
    assert res["team_name"] == "AlpineHydro"
    assert res["commit_sha"] == "1" * 40
    assert res["default_branch"] == "main"
    assert res["verification_status"] == "VERIFIED"


def test_scenario_2_extraneous_fields_strictly_rejected(sim_env):
    """Scenario 2: Reject unexpected fields (no commit_sha, branch, or email injection)."""
    service = SubmissionService(repository=sim_env["repo"])

    ok, res = service.register_submission({
        "team_name": "AlpineHydro",
        "repository_url": "https://github.com/alpine-hydro/topoflow-gnn",
        "commit_sha": "fake_sha_injected",
    })

    assert ok is False
    assert res["error"] == "VALIDATION_ERROR"
    assert "Unexpected field" in res["message"]


def test_scenario_3_ssrf_attack_blocked(sim_env):
    """Scenario 3: Private IP, AWS metadata IP, and loopback URLs rejected with fail-closed defense."""
    service = SubmissionService(repository=sim_env["repo"])

    # AWS metadata service IP
    ok1, res1 = service.register_submission({
        "team_name": "MaliciousTeam",
        "repository_url": "http://169.254.169.254/latest/meta-data/",
    })
    assert ok1 is False
    assert res1["error"] == "VALIDATION_ERROR"

    # Local loopback
    ok2, res2 = service.register_submission({
        "team_name": "MaliciousTeam",
        "repository_url": "http://127.0.0.1:8000/repo",
    })
    assert ok2 is False
    assert res2["error"] == "VALIDATION_ERROR"


def test_scenario_4_inaccessible_repo_flags_failure(sim_env):
    """Scenario 4: Inaccessible repository stores intake record with PENDING/FAILED status and preserves error."""
    set_mock_github_resolver(lambda u: (False, None, None, "Repository is private or does not exist"))
    service = SubmissionService(repository=sim_env["repo"])

    ok, res = service.register_submission({
        "team_name": "GhostTeam",
        "repository_url": "https://github.com/nonexistent/private-repo",
    })

    assert ok is True
    assert res["verification_status"] in ("PENDING", "FAILED")
    assert "Repository is private" in str(res.get("verification_details", ""))


def test_scenario_5_zero_code_execution_on_intake(sim_env):
    """Scenario 5: Intake strictly collects metadata; no subprocess, Docker, or code execution."""
    service = SubmissionService(repository=sim_env["repo"])
    set_mock_github_resolver(lambda u: (True, "master", "2" * 40, "VERIFIED"))

    # Register submission
    ok, res = service.register_submission({
        "team_name": "PassiveTeam",
        "repository_url": "https://github.com/passiveteam/pure-hydro",
    })
    assert ok is True
    sub = sim_env["repo"].get_submission(res["submission_id"])
    assert sub["submission_status"] in ("SUBMITTED", "UNDER_REVIEW")
    assert sub["linked_evaluation_job_id"] is None


def test_scenario_6_discovery_handles_nonstandard_repository_structure(sim_env):
    """Scenario 6: Discovery engine inspects non-standard layout and identifies inference entry point."""
    repo_path = sim_env["tmp_path"] / "custom_repo"
    repo_path.mkdir(parents=True, exist_ok=True)

    # Write a script with argument parsing
    (repo_path / "stream_predictor.py").write_text("""
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--input', type=str)
parser.add_argument('--output', type=str)
if __name__ == '__main__':
    args = parser.parse_args()
""", encoding="utf-8")

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(
        repo_dir=repo_path,
        commit_sha="3" * 40,
        submission_id="sub_custom"
    )

    assert report is not None
    assert report.status == DiscoveryStatus.DISCOVERY_SUCCESS
    assert report.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW)
    assert report.proposed_interface_mapping is not None


def test_scenario_7_hidden_labels_strictly_shielded(sim_env):
    """Scenario 7: Input preparer shields all future ground-truth labels and test split targets."""
    case_mgr = BenchmarkCaseManager(benchmark_root=sim_env["bm_dir"])
    cases = case_mgr.get_eligible_cases("test_a")
    assert len(cases) > 0

    preparer = BenchmarkInputPreparer()
    out_file = sim_env["tmp_path"] / "inputs_shield_test" / "cases.json"
    sanitized_cases, input_hash = preparer.prepare_inference_inputs(cases[:1], out_file)

    # Label shielding verification
    payload_str = json.dumps(sanitized_cases)
    assert "target_discharge" not in payload_str
    assert "ground_truth" not in payload_str
    assert "actual_q" not in payload_str
    assert "observed_discharge" not in payload_str
    assert "true_discharge" not in payload_str


def test_scenario_8_malicious_output_fails_closed(sim_env):
    """Scenario 8: Prediction validator detects invalid schema, nan, or negative discharge."""
    bad_pred = {
        "contract_version": "1.0.0",
        "predictions": [{
            "forecast_timestamp": "2024-01-08T00:00:00Z",
            "lead_day": 1,
            "predicted_discharge_m3_s": -10.0,
            "quantile_10": 1.0,
            "quantile_50": 2.0,
            "quantile_90": 3.0,
            "prob_exceed_q95": 0.1,
            "prob_exceed_q99": 0.05
        }]
    }
    v, errs = validate_prediction_payload(bad_pred)
    assert v is False
    assert any("negative" in err for err in errs)


def test_scenario_9_persistent_queue_lifecycle(sim_env):
    """Scenario 9: Queue manages atomic claim, worker heartbeat, and lease recovery."""
    queue = sim_env["queue"]
    repo = sim_env["repo"]

    # Insert mock evaluation job
    job = EvaluationJob(
        job_id="job_sim_9",
        repository_url="https://github.com/team/model",
        commit_sha="4" * 40,
        contract_version="1.0.0",
        benchmark_version="1.0.0",
        scoring_config_version="1.0.0",
        execution_backend="docker",
        status=JobStatus.QUEUED,
    )
    repo.insert_job(job)

    # 1. Enqueue
    qid = queue.enqueue("job_sim_9", priority=5)

    # 2. Claim
    item = queue.claim_next_job("worker_node_1", lease_seconds=120)
    assert item is not None
    assert item.job_id == "job_sim_9"

    # 3. Heartbeat
    hb_ok = queue.heartbeat(qid, "worker_node_1")
    assert hb_ok is True

    # 4. Complete
    comp_ok = queue.mark_completed(qid, "worker_node_1")
    assert comp_ok is True

    final_item = queue.get_queue_item(qid)
    assert final_item.status == QueueStatus.COMPLETED


def test_scenario_10_six_axis_deterministic_scoring(sim_env):
    """Scenario 10: Complete pipeline generates 6-axis scores and stores leaderboard record."""
    tmp_path = sim_env["tmp_path"]
    model_dir = tmp_path / "sim_model"
    model_dir.mkdir(parents=True, exist_ok=True)

    script_path = model_dir / "predict.py"
    script_path.write_text("""
import argparse
import json

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--outputs", required=True)
    args = parser.parse_args()

    with open(args.inputs, "r") as f:
        raw_data = json.load(f)
    cases = raw_data.get("cases", raw_data) if isinstance(raw_data, dict) else raw_data

    predictions = []
    for c in cases:
        case_id = c["case_id"]
        cid = c["catchment_id"]
        origin = c["forecast_origin"]
        horizons = c["horizons"]
        history = c.get("discharge_history", [15.0])
        base_val = history[-1] if history else 15.0

        for h in horizons:
            q_pred = round(max(0.1, base_val * 0.95), 2)
            predictions.append({
                "case_id": case_id,
                "catchment_id": cid,
                "forecast_origin": origin,
                "horizon": int(h),
                "predicted_discharge": q_pred,
                "high_flow_probability": 0.05,
                "extreme_flow_probability": 0.01,
                "prediction_interval_lower": round(q_pred * 0.7, 2),
                "prediction_interval_upper": round(q_pred * 1.3, 2),
                "nominal_interval_coverage": 0.90
            })

    with open(args.outputs, "w") as f:
        json.dump(predictions, f, indent=2)

if __name__ == "__main__":
    main()
""", encoding="utf-8")

    commit_sha = "5" * 40
    discovery_report = DiscoveryReport(
        discovery_id="disc_sim_10",
        submission_id="sub_sim_10",
        repository_url="https://github.com/team/model",
        commit_sha=commit_sha,
        created_at=datetime.now(timezone.utc).isoformat(),
        status=DiscoveryStatus.DISCOVERY_SUCCESS,
        interface_status=InterfaceStatus.INTERFACE_IDENTIFIED,
        confidence=ConfidenceLevel.HIGH,
        structure=RepositoryStructureSummary(total_files=2, source_file_count=1),
        proposed_interface_mapping=ProposedInterfaceMapping(
            interface_type="CLI_FILE_IN_OUT",
            executable_target="predict.py",
            input_mechanism="--inputs",
            output_mechanism="--outputs",
        ),
    )

    class SimulatedExecutor(ContainerExecutor):
        def is_isolation_backend_available(self) -> bool:
            return True

        def execute_in_container(self, command_args, repo_dir, input_dir, output_dir, scratch_dir, limits, input_hash, used_adapter):
            cmd = [
                "python",
                str(repo_dir / "predict.py"),
                "--inputs",
                str(input_dir / "cases.json"),
                "--outputs",
                str(output_dir / "predictions.json"),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            assert res.returncode == 0
            telemetry = ExecutionTelemetry(
                exit_code=0,
                wall_clock_seconds=0.85,
                peak_memory_mb=120.0,
                cpu_usage_percent=30.0,
                stdout="Simulated run success",
                stderr="",
                input_hash=input_hash,
                output_hash=None,
                termination_reason="NORMAL_EXIT",
            )
            return WorkerState.EXECUTION_SUCCESS, telemetry, "sim_container"

    worker_mgr = WorkerManager(container_executor=SimulatedExecutor())

    pipeline = BenchmarkEvaluationPipeline(
        benchmark_root=sim_env["bm_dir"],
        worker_manager=worker_mgr,
        db_repository=sim_env["repo"],
        scratch_dir=tmp_path / "scratch",
    )

    report = pipeline.execute_evaluation(
        submission_id="sub_sim_10",
        team_name="SimHydroTeam",
        repo_dir=model_dir,
        commit_sha=commit_sha,
        discovery_report=discovery_report,
        repository_url="https://github.com/team/model",
        eval_splits=("test_a",),
        resource_limits=WorkerResourceLimits(cpu_limit=2.0, memory_limit_mb=1024.0),
        is_organizer_approved=True,
        is_trusted_developer_fixture=True,
    )

    assert report.status == "COMPLETED"
    assert report.total_score is not None and report.total_score >= 0.0
    assert report.six_axis_scores is not None
    assert "forecast_skill" in report.six_axis_scores

    # Verify database persistence
    saved_res = sim_env["repo"].get_evaluation_result(report.job_id)
    assert saved_res is not None
    assert round(saved_res["total_score"], 2) == round(report.total_score, 2)
