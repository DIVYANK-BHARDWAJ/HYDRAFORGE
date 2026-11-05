"""
tests/test_worker_integration.py
End-to-End Integration Tests for Phase 5B:
Connects Participant Submission -> Immutable Commit -> Discovery -> Inference Contract ->
Worker Execution -> Output Collection -> Prediction Validation.
Proves that nonstandard filenames and custom directory structures execute seamlessly.
"""

import json
from pathlib import Path
import pytest

from hydraforge.discovery import RepositoryInspector
from hydraforge.schema import PredictionRecord
from hydraforge.worker import (
    WorkerContext,
    WorkerManager,
    WorkerResourceLimits,
    WorkerState,
    set_mock_container_executor,
)


@pytest.fixture(autouse=True)
def clean_mock_executor():
    set_mock_container_executor(None)
    yield
    set_mock_container_executor(None)


def test_end_to_end_nonstandard_repository_execution(tmp_path):
    """
    End-to-end integration proof:
    Participant uses custom directory 'algorithms/neural_flow' and script 'stream_predictor_v4.py'.
    No standard filenames used.
    Discovered automatically by Phase 5A engine and executed through Phase 5B Worker Engine.
    """
    repo_dir = tmp_path / "participant_repo"
    nested_code_dir = repo_dir / "algorithms" / "neural_flow"
    nested_code_dir.mkdir(parents=True)

    # 1. Nonstandard participant script
    script_file = nested_code_dir / "stream_predictor_v4.py"
    script_file.write_text(
        "import argparse\n"
        "import json\n"
        "import sys\n"
        "\n"
        "def main():\n"
        "    parser = argparse.ArgumentParser()\n"
        "    parser.add_argument('--input', required=True)\n"
        "    parser.add_argument('--output', required=True)\n"
        "    args = parser.parse_args()\n"
        "    with open(args.input, 'r') as f:\n"
        "        data = json.load(f)\n"
        "    cases = data.get('cases', [])\n"
        "    predictions = []\n"
        "    for case in cases:\n"
        "        predictions.append({\n"
        "            'case_id': case['case_id'],\n"
        "            'catchment_id': case['catchment_id'],\n"
        "            'forecast_origin': case['forecast_origin'],\n"
        "            'horizon': 1,\n"
        "            'predicted_discharge': 18.5,\n"
        "            'high_flow_probability': 0.15,\n"
        "            'extreme_flow_probability': 0.02,\n"
        "            'prediction_interval_lower': 12.0,\n"
        "            'prediction_interval_upper': 25.0,\n"
        "            'nominal_interval_coverage': 0.90\n"
        "        })\n"
        "    with open(args.output, 'w') as f:\n"
        "        json.dump({'predictions': predictions}, f)\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )

    (repo_dir / "requirements.txt").write_text("numpy>=1.24\nscipy>=1.10\n")
    (repo_dir / "README.md").write_text(
        "# NeuralFlow Forecaster\n"
        "Run inference:\n"
        "```bash\n"
        "python algorithms/neural_flow/stream_predictor_v4.py --input /data/cases.json --output /out/predictions.json\n"
        "```\n"
    )

    # 2. Step 1: Run Phase 5A Dynamic Discovery on exact commit
    commit_sha = "f" * 40
    inspector = RepositoryInspector()
    report = inspector.inspect_repository(
        repo_dir=repo_dir,
        submission_id="sub_team_stream",
        repository_url="https://github.com/team-stream/neuralflow.git",
        commit_sha=commit_sha
    )

    assert report.status.value == "DISCOVERY_SUCCESS"
    assert report.interface_status.value == "INTERFACE_IDENTIFIED"
    assert "stream_predictor_v4.py" in report.proposed_interface_mapping.executable_target

    # 3. Step 2: Prepare Authorized Benchmark Cases
    benchmark_cases = [
        {
            "case_id": "case_basin_2026_01",
            "catchment_id": "catchment_rhone_42",
            "forecast_origin": "2020-06-01T00:00:00Z",
            "horizons": [1, 3, 7],
            "discharge_history": [10.5, 11.2, 12.0],
            "forcing_history": {"precip": [0.0, 5.0, 2.0]}
        }
    ]

    worker_scratch = tmp_path / "worker_scratch"
    context = WorkerContext(
        submission_id="sub_team_stream",
        job_id="job_stream_001",
        commit_sha=commit_sha,
        discovery_report_id=report.discovery_id,
        benchmark_cases=benchmark_cases,
        scratch_dir=worker_scratch
    )

    # 4. Step 3: Simulate in-container execution of the nonstandard script
    def mock_container_run(cmd, repo_p, in_p, out_p, limits):
        # Read the real delivered input file
        in_file = in_p / "cases.json"
        with open(in_file, "r") as f:
            cases_data = json.load(f)

        cases = cases_data.get("cases", [])
        preds = []
        for c in cases:
            preds.append({
                "case_id": c["case_id"],
                "catchment_id": c["catchment_id"],
                "forecast_origin": c["forecast_origin"],
                "horizon": 1,
                "predicted_discharge": 18.5,
                "high_flow_probability": 0.15,
                "extreme_flow_probability": 0.02,
                "prediction_interval_lower": 12.0,
                "prediction_interval_upper": 25.0,
                "nominal_interval_coverage": 0.90
            })

        out_file = out_p / "predictions.json"
        with open(out_file, "w") as f:
            json.dump({"predictions": preds}, f)

        return WorkerState.EXECUTION_SUCCESS, 0, "Execution completed", "", False

    set_mock_container_executor(mock_container_run)

    # 5. Step 4: Execute through WorkerManager
    manager = WorkerManager()
    result = manager.run_worker_job(
        context=context,
        discovery_report=report,
        repo_dir=repo_dir
    )

    # 6. Step 5: Verify execution success & predictions collection
    assert result.final_state == WorkerState.EXECUTION_SUCCESS
    assert len(result.prediction_records) == 1
    pred = result.prediction_records[0]
    assert isinstance(pred, PredictionRecord)
    assert pred.case_id == "case_basin_2026_01"
    assert pred.predicted_discharge == 18.5
    assert pred.high_flow_probability == 0.15
    assert result.telemetry.output_hash is not None
    assert result.cleanup_success is True


def test_in_memory_python_adapter_shim_integration(tmp_path):
    """
    Test runtime adapter generation for in-memory model class without CLI parser.
    Ensures hydraforge_shim.py is synthesized in scratch and executes seamlessly.
    """
    repo_dir = tmp_path / "callable_repo"
    repo_dir.mkdir()

    # Participant exposes a class Predictor with predict(case_dict)
    (repo_dir / "my_model.py").write_text(
        "class HydrologyPredictor:\n"
        "    def predict(self, case):\n"
        "        return {\n"
        "            'case_id': case['case_id'],\n"
        "            'catchment_id': case['catchment_id'],\n"
        "            'forecast_origin': case['forecast_origin'],\n"
        "            'horizon': 1,\n"
        "            'predicted_discharge': 22.0,\n"
        "            'high_flow_probability': 0.10,\n"
        "            'extreme_flow_probability': 0.01,\n"
        "            'prediction_interval_lower': 15.0,\n"
        "            'prediction_interval_upper': 30.0,\n"
        "            'nominal_interval_coverage': 0.90\n"
        "        }\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(
        repo_dir=repo_dir,
        submission_id="sub_callable",
        repository_url="https://github.com/team/callable.git",
        commit_sha="b" * 40
    )

    assert report.interface_status.value == "INTERFACE_IDENTIFIED"
    assert report.proposed_interface_mapping.interface_type == "PYTHON_ADAPTER"

    benchmark_cases = [{
        "case_id": "c1",
        "catchment_id": "basin_01",
        "forecast_origin": "2020-01-01T00:00:00Z",
        "horizons": [1],
        "discharge_history": [10.0]
    }]

    context = WorkerContext(
        submission_id="sub_callable",
        job_id="job_callable_01",
        commit_sha="b" * 40,
        discovery_report_id=report.discovery_id,
        benchmark_cases=benchmark_cases,
        scratch_dir=tmp_path / "scratch_callable"
    )

    def mock_shim_run(cmd, repo_p, in_p, out_p, limits):
        # Assert that command targets /tmp/hydraforge_shim.py
        assert "/tmp/hydraforge_shim.py" in cmd
        out_file = out_p / "predictions.json"
        with open(out_file, "w") as f:
            json.dump({"predictions": [{
                "case_id": "c1",
                "catchment_id": "basin_01",
                "forecast_origin": "2020-01-01T00:00:00Z",
                "horizon": 1,
                "predicted_discharge": 22.0,
                "high_flow_probability": 0.10,
                "extreme_flow_probability": 0.01,
                "prediction_interval_lower": 15.0,
                "prediction_interval_upper": 30.0,
                "nominal_interval_coverage": 0.90
            }]}, f)
        return WorkerState.EXECUTION_SUCCESS, 0, "", "", False

    set_mock_container_executor(mock_shim_run)
    manager = WorkerManager()
    result = manager.run_worker_job(context, report, repo_dir)

    assert result.final_state == WorkerState.EXECUTION_SUCCESS
    assert len(result.prediction_records) == 1
    assert result.prediction_records[0].predicted_discharge == 22.0

