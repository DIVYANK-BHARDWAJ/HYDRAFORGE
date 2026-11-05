"""
tests/test_cli.py
Unit tests for the HYDRAFORGE Command-Line Interface (CLI).
Tests help outputs, benchmark inspection, leaderboard display, benchmark generation,
and evaluation command execution.
"""

import tempfile
from pathlib import Path
from click.testing import CliRunner

from hydraforge.cli.commands import cli
from hydraforge.database.connection import DatabaseManager
from hydraforge.database.migrations import apply_migrations


def test_cli_help():
    """Verify CLI top-level help and version options."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "HYDRAFORGE" in result.output
    assert "serve" in result.output
    assert "evaluate" in result.output
    assert "leaderboard" in result.output
    assert "benchmark" in result.output
    assert "generate-benchmark" in result.output


def test_cli_benchmark_command():
    """Verify hydraforge benchmark prints summary and leakage status."""
    runner = CliRunner()
    result = runner.invoke(cli, ["benchmark"])
    assert result.exit_code == 0
    assert "HYDRAFORGE BENCHMARK SUMMARY" in result.output
    assert "Leakage-Free" in result.output


def test_cli_leaderboard_empty():
    """Verify hydraforge leaderboard handles empty state gracefully."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_cli_hydraforge.db"
        DatabaseManager.set_default_path(db_path)
        try:
            runner = CliRunner()
            result = runner.invoke(cli, ["leaderboard"])
            assert result.exit_code == 0
            assert "No completed evaluations found" in result.output
        finally:
            DatabaseManager.set_default_path(None)


def test_cli_evaluate_fail_closed_untrusted_without_docker():
    """Verify hydraforge evaluate fails closed when Docker daemon is offline."""
    runner = CliRunner()
    result = runner.invoke(cli, [
        "evaluate",
        "--repo", "https://github.com/team/model.git",
        "--commit", "a" * 40
    ])
    assert result.exit_code == 0
    assert "UNSAFE_EXECUTION_ENVIRONMENT" in result.output


def test_cli_evaluate_trusted_mock_submission():
    """Verify hydraforge evaluate runs trusted mock fixture successfully."""
    mock_dir = Path("tests/fixtures/mock_submission").resolve()
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_cli_hydraforge.db"
        DatabaseManager.set_default_path(db_path)
        try:
            runner = CliRunner()
            result = runner.invoke(cli, [
                "evaluate",
                "--repo", str(mock_dir),
                "--commit", "0" * 40,
                "--trusted",
                "--team", "CLITestingLab",
                "--name", "CLIBaseline"
            ])
            assert result.exit_code == 0
            assert "EVALUATION COMPLETED" in result.output
            assert "Final Score:" in result.output

            # Now test leaderboard display with this entry present
            lb_res = runner.invoke(cli, ["leaderboard"])
            assert lb_res.exit_code == 0
            assert "OFFICIAL LEADERBOARD" in lb_res.output
            assert "CLITestingLab" in lb_res.output
        finally:
            DatabaseManager.set_default_path(None)


def test_cli_generate_benchmark():
    """Verify hydraforge generate-benchmark generates valid dataset in temp directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = Path(tmp_dir) / "synthetic_bench"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "generate-benchmark",
            "--output", str(out_dir),
            "--seed", "123"
        ])
        assert result.exit_code == 0
        assert "Generation complete!" in result.output
        assert (out_dir / "metadata" / "split_manifests.json").exists()
        assert (out_dir / "inputs" / "test_a" / "inputs.json").exists()
        assert (out_dir / "labels" / "test_a" / "labels.json").exists()

