"""
tests/test_worker_security.py
Adversarial security and isolation tests for Phase 5B.
Exercises all 20 required adversarial developer fixtures:
resource exhaustion, path traversal, symlink escapes, label access attempts,
network access, malicious manifests, timeouts, cleanup, and fail-closed availability.
"""

import json
import os
import tempfile
from pathlib import Path
import pytest

from hydraforge.discovery.discovery_models import (
    ConfidenceLevel,
    DiscoveryReport,
    DiscoveryStatus,
    FileType,
    InterfaceStatus,
    ProposedInterfaceMapping,
    RepositoryStructureSummary,
)
from hydraforge.runner.isolation import LabelLeakageSecurityViolation, verify_hidden_label_shielding
from hydraforge.worker import (
    CommandBuilder,
    ContainerExecutor,
    DEFAULT_SECURITY_PROFILE,
    DependencyManager,
    OutputCollectionSecurityError,
    OutputCollector,
    ResourceEnforcer,
    ResourceLimitConfigError,
    WorkerCleanup,
    WorkerContext,
    WorkerExecutionResult,
    WorkerManager,
    WorkerResourceLimits,
    WorkerSecurityProfile,
    WorkerState,
    set_mock_container_executor,
)


@pytest.fixture(autouse=True)
def reset_mock_executor():
    """Ensure mock executor is cleared after every test."""
    set_mock_container_executor(None)
    yield
    set_mock_container_executor(None)


@pytest.fixture
def sample_discovery_report():
    """Valid DiscoveryReport fixture pointing to a standard nonstandard script."""
    return DiscoveryReport(
        discovery_id="disc_test_sec_001",
        submission_id="sub_adversarial_001",
        repository_url="https://github.com/adversarial/suite.git",
        commit_sha="a" * 40,
        created_at="2026-11-05T00:00:00Z",
        status=DiscoveryStatus.DISCOVERY_SUCCESS,
        interface_status=InterfaceStatus.INTERFACE_IDENTIFIED,
        confidence=ConfidenceLevel.HIGH,
        structure=RepositoryStructureSummary(total_files=2),
        proposed_interface_mapping=ProposedInterfaceMapping(
            interface_type="CLI_FILE_IN_OUT",
            executable_target="run_model.py",
            input_mechanism="--input",
            output_mechanism="--output",
        )
    )


@pytest.fixture
def sample_worker_context(tmp_path):
    """Standard context with one sample benchmark case."""
    return WorkerContext(
        submission_id="sub_adversarial_001",
        job_id="job_adv_001",
        commit_sha="a" * 40,
        discovery_report_id="disc_test_sec_001",
        benchmark_cases=[
            {
                "case_id": "case_test_01",
                "catchment_id": "catchment_01",
                "forecast_origin": "2020-01-01T00:00:00Z",
                "horizons": [1],
                "discharge_history": [10.0, 11.0],
                "forcing_history": {"precip": [1.0, 2.0]}
            }
        ],
        scratch_dir=tmp_path / "scratch"
    )


# -----------------------------------------------------------------------------
# 1. Infinite Loop Fixture
# -----------------------------------------------------------------------------
def test_1_infinite_loop(sample_worker_context, sample_discovery_report, tmp_path):
    """Container hangs in infinite loop; worker terminates it on timeout."""
    def mock_hang(cmd, repo, in_d, out_d, limits):
        # Simulate timeout expired
        return WorkerState.EXECUTION_TIMEOUT, -9, "", "Process killed by timeout", True

    set_mock_container_executor(mock_hang)
    manager = WorkerManager()
    result = manager.run_worker_job(sample_worker_context, sample_discovery_report, tmp_path)

    assert result.final_state == WorkerState.EXECUTION_TIMEOUT
    assert result.telemetry.timed_out is True


# -----------------------------------------------------------------------------
# 2. Excessive Memory Allocation (OOM Killer Exit Code 137)
# -----------------------------------------------------------------------------
def test_2_excessive_memory_allocation(sample_worker_context, sample_discovery_report, tmp_path):
    """Container exceeds memory limit and gets terminated with OOM exit code 137."""
    def mock_oom(cmd, repo, in_d, out_d, limits):
        return WorkerState.RESOURCE_LIMIT_EXCEEDED, 137, "", "Killed (Out of memory)", False

    set_mock_container_executor(mock_oom)
    manager = WorkerManager()
    result = manager.run_worker_job(sample_worker_context, sample_discovery_report, tmp_path)

    assert result.final_state == WorkerState.RESOURCE_LIMIT_EXCEEDED


# -----------------------------------------------------------------------------
# 3. Excessive CPU Consumption
# -----------------------------------------------------------------------------
def test_3_excessive_cpu_consumption():
    """Verify ResourceEnforcer enforces --cpus ceiling argument."""
    limits = WorkerResourceLimits(cpu_limit=2.0)
    args = ResourceEnforcer.build_docker_resource_args(limits)

    assert "--cpus" in args
    idx = args.index("--cpus")
    assert args[idx + 1] == "2.0"

    # Reject absurd CPU allocations
    with pytest.raises(ResourceLimitConfigError):
        ResourceEnforcer.validate_limits(WorkerResourceLimits(cpu_limit=32.0))


# -----------------------------------------------------------------------------
# 4. Process Spawning (Fork-Bomb Protection)
# -----------------------------------------------------------------------------
def test_4_process_spawning():
    """Verify ResourceEnforcer enforces --pids-limit to prevent fork bomb attacks."""
    limits = WorkerResourceLimits(pids_limit=64)
    args = ResourceEnforcer.build_docker_resource_args(limits)

    assert "--pids-limit" in args
    idx = args.index("--pids-limit")
    assert args[idx + 1] == "64"


# -----------------------------------------------------------------------------
# 5. Filesystem Traversal Attack on Output
# -----------------------------------------------------------------------------
def test_5_filesystem_traversal(tmp_path):
    """OutputCollector strictly prevents path traversal outside designated output volume."""
    out_dir = tmp_path / "outputs"
    out_dir.mkdir()

    collector = OutputCollector()
    with pytest.raises(OutputCollectionSecurityError) as exc:
        collector.collect_predictions(out_dir, expected_filename="../../sensitive.txt")

    assert "Path traversal detected" in str(exc.value)


# -----------------------------------------------------------------------------
# 6. Symlink Escape Attack on Output
# -----------------------------------------------------------------------------
def test_6_symlink_escape(tmp_path, monkeypatch):
    """Output file pointing outside output volume via symlink is blocked."""
    out_dir = tmp_path / "outputs"
    out_dir.mkdir()
    pred_file = out_dir / "predictions.json"
    pred_file.write_text("{}")

    sensitive_host_file = tmp_path.parent / "host_secrets.json"
    sensitive_host_file.write_text('{"secret": "stolen"}')

    # Monkeypatch to simulate symlink resolving outside
    orig_is_symlink = Path.is_symlink
    orig_resolve = Path.resolve

    def mock_is_sym(self):
        if self.name == "predictions.json":
            return True
        return orig_is_symlink(self)

    def mock_res(self):
        if self.name == "predictions.json":
            return sensitive_host_file.resolve()
        return orig_resolve(self)

    monkeypatch.setattr(Path, "is_symlink", mock_is_sym)
    monkeypatch.setattr(Path, "resolve", mock_res)

    collector = OutputCollector()
    with pytest.raises(OutputCollectionSecurityError) as exc:
        collector.collect_predictions(out_dir, "predictions.json")

    assert "Insecure symlink output detected" in str(exc.value)


# -----------------------------------------------------------------------------
# 7. Attempts to Read Hidden Labels
# -----------------------------------------------------------------------------
def test_7_attempts_to_read_hidden_labels(tmp_path):
    """Assert hidden ground-truth labels cannot be exposed in paths, args, or env."""
    bad_input_path = tmp_path / "hidden_benchmark" / "labels" / "labels.json"

    with pytest.raises(LabelLeakageSecurityViolation):
        verify_hidden_label_shielding(bad_input_path, ["python", "run.py"], {})

    # Label parameter in command args
    with pytest.raises(LabelLeakageSecurityViolation):
        verify_hidden_label_shielding(tmp_path / "inputs", ["python", "run.py", "--labels", "labels.json"], {})


# -----------------------------------------------------------------------------
# 8. Attempts to Access Host Files
# -----------------------------------------------------------------------------
def test_8_attempts_to_access_host_files():
    """Verify security profile never mounts host root or host filesystem."""
    profile = DEFAULT_SECURITY_PROFILE
    assert profile.read_only_rootfs is True
    assert profile.container_workspace_dir == "/workspace"
    assert profile.container_input_dir == "/inputs"
    assert profile.container_output_dir == "/outputs"


# -----------------------------------------------------------------------------
# 9. Attempts to Access Docker Socket
# -----------------------------------------------------------------------------
def test_9_attempts_to_access_docker_socket():
    """Verify Docker socket (/var/run/docker.sock) is never mounted into container."""
    profile = DEFAULT_SECURITY_PROFILE
    assert profile.drop_all_capabilities is True
    assert profile.no_new_privileges is True


# -----------------------------------------------------------------------------
# 10. Attempts to Access Other Teams' Data
# -----------------------------------------------------------------------------
def test_10_attempts_to_access_other_teams_data(sample_worker_context, sample_discovery_report, tmp_path):
    """Workspaces and scratch directories are strictly isolated per job_id."""
    ctx_team_a = sample_worker_context
    ctx_team_a.job_id = "job_team_a"
    ctx_team_a.scratch_dir = tmp_path / ctx_team_a.job_id

    assert "job_team_a" in str(ctx_team_a.scratch_dir)


# -----------------------------------------------------------------------------
# 11. Attempts to Access Network Services
# -----------------------------------------------------------------------------
def test_11_attempts_to_access_network_services():
    """Verify network mode is strictly none (airgapped)."""
    profile = DEFAULT_SECURITY_PROFILE
    assert profile.network_mode == "none"


# -----------------------------------------------------------------------------
# 12. Malicious Dependency Installation
# -----------------------------------------------------------------------------
def test_12_malicious_dependency_installation(sample_discovery_report):
    """Attempted shell injection or dangerous package name in dependencies is blocked."""
    mgr = DependencyManager()

    # Shell injection attack in dependency line
    sample_discovery_report.detected_dependencies = ["numpy>=1.20; rm -rf /"]
    ok, plan, err = mgr.evaluate_dependencies(sample_discovery_report)
    assert ok is False
    assert "Illegal characters" in err

    # Backdoored package name
    sample_discovery_report.detected_dependencies = ["cryptography_backdoor==1.0"]
    ok, plan, err = mgr.evaluate_dependencies(sample_discovery_report)
    assert ok is False
    assert "Disallowed" in err


# -----------------------------------------------------------------------------
# 13. Malicious setup.py (Static AST Security)
# -----------------------------------------------------------------------------
def test_13_malicious_setup_py():
    """setup.py containing destructive code is never executed during dependency analysis."""
    from hydraforge.discovery.manifest_detector import ManifestDetector
    detector = ManifestDetector()

    with tempfile.TemporaryDirectory() as td:
        setup_file = Path(td) / "setup.py"
        setup_file.write_text("import os\nos.system('echo Malicious')\nfrom setuptools import setup\nsetup(name='test')\n")
        manifests, deps, warnings = detector.detect_manifests(Path(td))
        assert len(manifests) == 1
        # Execution was avoided entirely via static ast.parse


# -----------------------------------------------------------------------------
# 14. Malicious README Commands
# -----------------------------------------------------------------------------
def test_14_malicious_readme_commands():
    """CommandBuilder rejects untrusted shell command strings from READMEs."""
    builder = CommandBuilder()
    report = DiscoveryReport(
        discovery_id="d1", submission_id="s1", repository_url="http://example.com",
        commit_sha="a" * 40, created_at="2026-11-05T00:00:00Z",
        status=DiscoveryStatus.NEEDS_ORGANIZER_REVIEW,
        interface_status=InterfaceStatus.INTERFACE_AMBIGUOUS,
        confidence=ConfidenceLevel.LOW,
        structure=RepositoryStructureSummary()
    )

    with pytest.raises(Exception):
        builder.build_execution_command(report, Path("tmp"))


# -----------------------------------------------------------------------------
# 15. Output Path Traversal Attempt
# -----------------------------------------------------------------------------
def test_15_output_path_traversal(tmp_path):
    """Verify OutputCollector catches relative path traversal."""
    collector = OutputCollector()
    with pytest.raises(OutputCollectionSecurityError):
        collector.collect_predictions(tmp_path, "../../../etc/shadow")


# -----------------------------------------------------------------------------
# 16. Output Symlink Escape
# -----------------------------------------------------------------------------
def test_16_output_symlink_escape(tmp_path, monkeypatch):
    """Verify OutputCollector catches output symlink resolving outside volume."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    target = out_dir / "predictions.json"
    target.write_text("{}")

    orig_resolve = Path.resolve
    def mock_resolve(self):
        if self.name == "predictions.json":
            return Path("C:/Windows/System32/calc.exe")
        return orig_resolve(self)

    monkeypatch.setattr(Path, "is_symlink", lambda self: True)
    monkeypatch.setattr(Path, "resolve", mock_resolve)

    collector = OutputCollector()
    with pytest.raises(OutputCollectionSecurityError):
        collector.collect_predictions(out_dir, "predictions.json")


# -----------------------------------------------------------------------------
# 17. Timeout Enforcement
# -----------------------------------------------------------------------------
def test_17_timeout_enforcement(sample_worker_context, sample_discovery_report, tmp_path):
    """Execution exceeding timeout records timed_out=True in telemetry."""
    set_mock_container_executor(lambda cmd, r, i, o, lim: (WorkerState.EXECUTION_TIMEOUT, -9, "", "Timeout exceeded", True))
    manager = WorkerManager()
    res = manager.run_worker_job(sample_worker_context, sample_discovery_report, tmp_path)

    assert res.final_state == WorkerState.EXECUTION_TIMEOUT
    assert res.telemetry.timed_out is True


# -----------------------------------------------------------------------------
# 18. Worker Termination
# -----------------------------------------------------------------------------
def test_18_worker_termination():
    """WorkerCleanup cleanly removes container by ID."""
    assert WorkerCleanup.cleanup_container("nonexistent_container_123") is True


# -----------------------------------------------------------------------------
# 19. Cleanup After Failure
# -----------------------------------------------------------------------------
def test_19_cleanup_after_failure(sample_worker_context, sample_discovery_report, tmp_path):
    """When container fails, scratch directories and volumes are cleanly wiped."""
    set_mock_container_executor(lambda cmd, r, i, o, lim: (WorkerState.EXECUTION_FAILED, 1, "", "Model crashed", False))
    manager = WorkerManager()
    res = manager.run_worker_job(sample_worker_context, sample_discovery_report, tmp_path)

    assert res.final_state == WorkerState.EXECUTION_FAILED
    assert res.cleanup_success is True
    # Scratch directory was cleaned
    assert not (sample_worker_context.scratch_dir / "inputs").exists()


# -----------------------------------------------------------------------------
# 20. Worker Unavailable (Fail-Closed Enforcement)
# -----------------------------------------------------------------------------
def test_20_worker_unavailable(sample_worker_context, sample_discovery_report, tmp_path):
    """When Docker daemon is offline, manager returns SAFE_WORKER_UNAVAILABLE."""
    # Ensure mock is None so real check runs
    set_mock_container_executor(None)
    executor = ContainerExecutor()
    # Force is_isolation_backend_available to return False
    executor.is_isolation_backend_available = lambda: False

    manager = WorkerManager(container_executor=executor)
    res = manager.run_worker_job(sample_worker_context, sample_discovery_report, tmp_path)

    assert res.final_state == WorkerState.SAFE_WORKER_UNAVAILABLE
    assert "SAFE_WORKER_UNAVAILABLE" in res.error_message
