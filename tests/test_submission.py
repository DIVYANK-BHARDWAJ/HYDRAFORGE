"""Unit tests for submission intake, URL sanitization, and commit verification."""

from pathlib import Path
import pytest

from hydraforge.schema import ValidationError
from hydraforge.submission.integrity import compute_tree_hash
from hydraforge.submission.manifest_loader import load_submission_manifest
from hydraforge.submission.repository import (
    RepositoryIntake,
    RepositorySecurityError,
    validate_commit_sha,
    validate_repository_url,
)
from hydraforge.submission.validation import validate_submission_package


def test_repository_url_valid():
    assert validate_repository_url("https://github.com/team-hydro/model") == "https://github.com/team-hydro/model"
    assert validate_repository_url("https://gitlab.com/research/flood-ai") == "https://gitlab.com/research/flood-ai"


def test_repository_url_rejects_ssrf_and_protocols():
    # Localhost
    with pytest.raises(RepositorySecurityError, match="SSRF Prevention"):
        validate_repository_url("https://localhost/repo.git")

    with pytest.raises(RepositorySecurityError, match="SSRF Prevention"):
        validate_repository_url("https://127.0.0.1/repo.git")

    # Private IP
    with pytest.raises(RepositorySecurityError, match="SSRF Prevention"):
        validate_repository_url("https://192.168.1.50/repo.git")

    # Unsupported schemes
    with pytest.raises(RepositorySecurityError, match="Only 'https' is permitted"):
        validate_repository_url("file:///etc/passwd")

    with pytest.raises(RepositorySecurityError, match="Only 'https' is permitted"):
        validate_repository_url("http://github.com/repo")

    with pytest.raises(RepositorySecurityError, match="Only 'https' is permitted"):
        validate_repository_url("git://github.com/repo")

    # Unapproved hosting domains
    with pytest.raises(RepositorySecurityError, match="Unapproved Git hosting domain"):
        validate_repository_url("https://evil-untrusted-server.com/repo.git")


def test_commit_sha_valid_and_mutable_rejection():
    valid_sha = "0123456789abcdef0123456789abcdef01234567"
    assert validate_commit_sha(valid_sha) == valid_sha

    # Branch names (mutable) must be rejected
    with pytest.raises(RepositorySecurityError, match="Mutable branch names"):
        validate_commit_sha("main")

    with pytest.raises(RepositorySecurityError, match="Mutable branch names"):
        validate_commit_sha("master")

    # Short SHAs must be rejected
    with pytest.raises(RepositorySecurityError, match="Invalid commit SHA"):
        validate_commit_sha("0123456")

    # Invalid characters
    with pytest.raises(RepositorySecurityError, match="Invalid commit SHA"):
        validate_commit_sha("0123456789abcdef0123456789abcdef0123456g")


def test_manifest_loader_valid(tmp_path: Path):
    manifest_file = tmp_path / "submission_manifest.json"
    manifest_file.write_text(
        '{"team_name": "T1", "submission_name": "S1", "contract_version": "1.0.0", "entrypoint": "model.py"}',
        encoding="utf-8"
    )
    m = load_submission_manifest(tmp_path)
    assert m.team_name == "T1"
    assert m.entrypoint == "model.py"


def test_manifest_loader_missing(tmp_path: Path):
    with pytest.raises(ValidationError, match="Mandatory submission manifest not found"):
        load_submission_manifest(tmp_path)


def test_tree_hash_deterministic(tmp_path: Path):
    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.txt"
    f1.write_text("print('hello')", encoding="utf-8")
    f2.write_text("data 123", encoding="utf-8")

    h1 = compute_tree_hash(tmp_path)
    h2 = compute_tree_hash(tmp_path)
    assert h1 == h2
    assert len(h1) == 64

