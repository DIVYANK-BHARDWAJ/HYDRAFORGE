"""HYDRAFORGE Command-Line Interface (CLI)."""

from __future__ import annotations

import json
from pathlib import Path
import click

from hydraforge import __version__
from hydraforge.api.services.benchmark_service import BenchmarkService
from hydraforge.api.services.evaluation_service import EvaluationService
from hydraforge.api.services.leaderboard_service import LeaderboardService
from hydraforge.database.migrations import apply_migrations


@click.group()
@click.version_option(version=__version__, prog_name="HYDRAFORGE")
def cli():
    """HYDRAFORGE — The Intelligence Evaluation Engine."""
    pass


@cli.command("serve")
@click.option("--host", default="127.0.0.1", help="Bind host address.")
@click.option("--port", default=5000, type=int, help="Port to listen on.")
def serve_command(host: str, port: int):
    """Start the HYDRAFORGE REST API and Organizer Web Dashboard."""
    from hydraforge.api.main import create_app
    click.echo(f"Starting HYDRAFORGE server on http://{host}:{port}")
    click.echo("API Endpoints:")
    click.echo(f"  - Health:      http://{host}:{port}/health")
    click.echo(f"  - Overview:    http://{host}:{port}/api/v1/overview")
    click.echo(f"  - Leaderboard: http://{host}:{port}/api/v1/leaderboard")
    click.echo(f"  - Dashboard:   http://{host}:{port}/")
    app = create_app()
    app.run(host=host, port=port, debug=False)


@cli.command("evaluate")
@click.option("--repo", required=True, help="GitHub repository URL or local path for trusted test.")
@click.option("--commit", required=True, help="Immutable 40-character commit SHA.")
@click.option("--trusted", is_flag=True, default=False, help="Explicitly mark submission as trusted developer fixture.")
@click.option("--team", default="Developer", help="Team name.")
@click.option("--name", default="Submission", help="Submission name.")
def evaluate_command(repo: str, commit: str, trusted: bool, team: str, name: str):
    """Submit a repository for automated evaluation."""
    apply_migrations()
    service = EvaluationService()

    meta = {"team_name": team, "submission_name": name}
    click.echo(f"Evaluating submission '{name}' by '{team}'...")
    click.echo(f"Repository: {repo} @ {commit}")

    success, res = service.submit_evaluation(
        repository_url=repo,
        commit_sha=commit,
        submission_metadata=meta,
        is_trusted=trusted
    )

    if not success:
        click.secho(f"\n[EVALUATION BLOCKED / REJECTED]: {res.get('error')}", fg="red", bold=True)
        click.echo(res.get("message"))
        return

    click.secho(f"\n[EVALUATION {res['status']}]: Final Score: {res.get('final_score')} / 100.0", fg="green", bold=True)
    click.echo(f"Job ID: {res['job_id']}")
    click.echo(f"Audit Hash: {res.get('report_hash')}")


@cli.command("leaderboard")
@click.option("--version", default="1.0.0", help="Benchmark version.")
def leaderboard_command(version: str):
    """Print the current official leaderboard."""
    apply_migrations()
    service = LeaderboardService()
    entries = service.get_leaderboard(benchmark_version=version)

    if not entries:
        click.echo(f"No completed evaluations found for benchmark version {version}.")
        return

    click.secho(f"\n=== HYDRAFORGE OFFICIAL LEADERBOARD (v{version}) ===", fg="cyan", bold=True)
    header = f"{'Rank':<5} {'Team':<20} {'Submission':<25} {'Total':<8} {'Skill':<7} {'Event':<7} {'Gen':<6} {'Calib':<7} {'Rob':<6} {'Eff':<6}"
    click.echo(header)
    click.echo("-" * len(header))

    for e in entries:
        click.echo(
            f"{e['rank']:<5} {e['team_name'][:18]:<20} {e['submission_name'][:23]:<25} "
            f"{e['total_score']:<8.2f} {e['forecast_skill']:<7.2f} {e['event_detection']:<7.2f} "
            f"{e['generalization']:<6.2f} {e['calibration']:<7.2f} {e['robustness']:<6.2f} {e['efficiency']:<6.2f}"
        )


@cli.command("benchmark")
def benchmark_command():
    """Display benchmark dataset summary, partitions, and leakage status."""
    service = BenchmarkService()
    summary = service.get_benchmark_summary()

    click.secho(f"\n=== HYDRAFORGE BENCHMARK SUMMARY (v{summary['benchmark_version']}) ===", fg="cyan", bold=True)
    click.echo(f"Dataset:     {summary['dataset_name']}")
    click.echo(f"Catchments:  {summary['catchment_count']}")
    click.echo(f"Regions:     {summary['region_count']} ({', '.join(summary['regions'])})")
    click.echo(f"Splits:      {', '.join(summary['available_splits'])}")
    click.echo(f"Leakage-Free: {summary['leakage_audit']['is_leakage_free']}")


@cli.command("generate-benchmark")
@click.option("--output", default="data/benchmark", help="Output directory path.")
@click.option("--seed", default=42, type=int, help="Deterministic random seed.")
def generate_benchmark_command(output: str, seed: int):
    """Generate a deterministic synthetic hydrological benchmark suite."""
    from hydraforge.benchmark.config import BenchmarkConfig
    from hydraforge.benchmark.synthetic import generate_synthetic_benchmark

    cfg = BenchmarkConfig(random_seed=seed)
    click.echo(f"Generating synthetic benchmark into '{output}' (seed={seed})...")
    sum_data, audit = generate_synthetic_benchmark(Path(output), cfg)

    click.secho("Generation complete!", fg="green", bold=True)
    click.echo(f"Leakage audit: {'PASS (Zero Leakage)' if audit.is_leakage_free else 'FAIL'}")
    click.echo(f"Cases: {sum_data['case_counts']}")


@cli.command("validate-predictions")
@click.argument("prediction_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def validate_predictions_command(prediction_file: Path):
    """Validate a participant prediction JSON file against contract v1.0.0."""
    from scripts.validate_submission import validate_prediction_payload
    try:
        with open(prediction_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        click.secho(f"Error parsing JSON: {e}", fg="red")
        raise click.Abort()

    valid, errors = validate_prediction_payload(data)
    if valid:
        num_preds = len(data.get("predictions", []))
        click.secho(f"SUCCESS: '{prediction_file.name}' is valid according to HYDRAFORGE Contract v1.0.0.", fg="green", bold=True)
        click.echo(f"Verified {num_preds} forecast lead-days with all bounds, orderings, and probabilities valid.")
    else:
        click.secho(f"VALIDATION FAILED: Found {len(errors)} error(s) in '{prediction_file.name}':", fg="red", bold=True)
        for err in errors:
            click.echo(f"  - {err}")
        raise click.Abort()


