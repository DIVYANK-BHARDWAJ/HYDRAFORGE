"""
hydraforge/api/services/submission_service.py
Participant Submission Intake, Server-Side GitHub & Website Verification.
Enforces the 3-field participant submission contract:
  1. Team Name
  2. GitHub Repository URL
  3. Deployed Website URL
Captures immutable HEAD commit SHA server-side, validates website against SSRF,
and preserves submissions without code execution.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from hydraforge.database.models import SubmissionRecord
from hydraforge.database.repository import EvaluationRepository
from hydraforge.runner.docker_runner import DockerRunner
from hydraforge.submission.github_verifier import resolve_github_head_commit
from hydraforge.submission.repository import (
    RepositorySecurityError,
    validate_repository_url,
)
from hydraforge.submission.website_verifier import (
    WebsiteSecurityError,
    check_website_availability,
    validate_website_url,
)


class SubmissionValidationError(Exception):
    """Raised when participant submission fails validation."""
    pass


class SubmissionService:
    """Manages the participant submission pipeline, server-side verification, and evaluation."""

    def __init__(self, repository: Optional[EvaluationRepository] = None) -> None:
        self.repo = repository or EvaluationRepository()

    def register_submission(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Enforce the strict 2-field participant submission contract:
          1. Team Name (required)
          2. GitHub Repository URL (required)
        Rejects all unexpected fields. Automatically discovers default branch and HEAD commit SHA.
        """
        try:
            # Reject unexpected participant-supplied fields
            allowed_fields = {"team_name", "repository_url"}
            extra_fields = set(data.keys()) - allowed_fields
            if extra_fields:
                raise SubmissionValidationError(
                    f"Unexpected field(s) in submission: {sorted(list(extra_fields))}. "
                    "Participant submission must contain exactly two fields: 'team_name' and 'repository_url'."
                )

            # 1. Team Name
            team_name = str(data.get("team_name", "")).strip()
            if not team_name:
                raise SubmissionValidationError("Team name is required.")
            if len(team_name) > 100:
                raise SubmissionValidationError("Team name must not exceed 100 characters.")

            # 2. GitHub Repository URL
            repo_url = str(data.get("repository_url", "")).strip()
            if not repo_url:
                raise SubmissionValidationError("GitHub repository URL is required.")

            try:
                clean_repo_url = validate_repository_url(repo_url)
            except RepositorySecurityError as e:
                raise SubmissionValidationError(f"Invalid repository URL: {e}")

            # Security: Reject submitted credentials/tokens
            for k, val in data.items():
                s = str(val).lower()
                if "ghp_" in s or "github_pat_" in s or "bearer " in s:
                    raise SubmissionValidationError(
                        "Security violation: Do not submit GitHub Personal Access Tokens or credentials."
                    )

            # Check duplicate submission
            if self.repo.check_duplicate_submission(team_name, clean_repo_url):
                raise SubmissionValidationError(
                    f"A submission for team '{team_name}' with repository '{clean_repo_url}' already exists."
                )

            # Server-Side GitHub Verification & Commit SHA Capture
            gh_ok, default_branch, head_sha, gh_details = resolve_github_head_commit(clean_repo_url)

            # Generate unpredictable submission ID
            submission_id = f"sub_{uuid.uuid4().hex}"
            now_iso = datetime.now(timezone.utc).isoformat()

            verification_status = "VERIFIED" if gh_ok and head_sha else "PENDING"
            submission_status = "UNDER_REVIEW" if gh_ok and head_sha else "SUBMITTED"

            sub_record = SubmissionRecord(
                submission_id=submission_id,
                team_name=team_name,
                repository_url=clean_repo_url,
                deployed_website_url="",
                commit_sha=head_sha,
                default_branch=default_branch or "main",
                website_status="N/A",
                submitted_at=now_iso,
                verification_status=verification_status,
                verification_details=gh_details,
                organizer_review_status="UNDER_REVIEW",
                organizer_notes=None,
                submission_status=submission_status,
                linked_evaluation_job_id=None,
            )

            self.repo.insert_submission(sub_record)

            return True, {
                "submission_id": submission_id,
                "team_name": team_name,
                "repository_url": clean_repo_url,
                "commit_sha": head_sha,
                "default_branch": default_branch or "main",
                "verification_status": verification_status,
                "verification_details": gh_details,
                "submitted_at": now_iso,
                "submission_status": submission_status,
                "message": (
                    "Submission received successfully. Store your Submission ID safely "
                    "to check verification status and evaluation progress on the participant portal."
                ),
            }

        except SubmissionValidationError as e:
            return False, {"error": "VALIDATION_ERROR", "message": str(e)}
        except Exception as e:
            return False, {"error": "INTERNAL_ERROR", "message": f"Unexpected error: {str(e)}"}

    def verify_submission(self, submission_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Server-side re-verification of GitHub repository and deployed website.
        Never executes participant code.
        """
        sub = self.repo.get_submission(submission_id, include_private_notes=True)
        if not sub:
            return False, {"error": "NOT_FOUND", "message": f"Submission '{submission_id}' not found."}

        repo_url = sub["repository_url"]
        website_url = sub.get("deployed_website_url", "")

        # 1. GitHub verification
        gh_ok, default_branch, head_sha, gh_details = resolve_github_head_commit(repo_url)

        # 2. Website verification
        ws_ok, ws_status, ws_details = check_website_availability(website_url) if website_url else (False, "UNVERIFIED", "")

        ver_status = "VERIFIED" if gh_ok and head_sha else "FAILED"
        self.repo.update_submission_verification(
            submission_id=submission_id,
            verification_status=ver_status,
            commit_sha=head_sha,
            default_branch=default_branch,
            verification_details=gh_details
        )
        if ws_status:
            self.repo.update_submission_website(submission_id, ws_status, ws_details)

        return True, {
            "submission_id": submission_id,
            "verification_status": ver_status,
            "commit_sha": head_sha,
            "website_status": ws_status,
            "details": gh_details
        }

    def get_public_status(self, submission_id: str) -> Optional[Dict[str, Any]]:
        """Return safe participant-visible submission status."""
        sub = self.repo.get_submission(submission_id, include_private_notes=False)
        if not sub:
            return None

        return {
            "submission_id": sub["submission_id"],
            "team_name": sub["team_name"],
            "repository_url": sub["repository_url"],
            "deployed_website_url": sub.get("deployed_website_url"),
            "commit_sha": sub.get("commit_sha"),
            "default_branch": sub.get("default_branch", "main"),
            "website_status": sub.get("website_status", "PENDING"),
            "submitted_at": sub["submitted_at"],
            "verification_status": sub["verification_status"],
            "verification_details": sub.get("verification_details"),
            "review_status": sub["organizer_review_status"],
            "submission_status": sub["submission_status"],
            "linked_evaluation_job_id": sub.get("linked_evaluation_job_id"),
            "evaluation_job_status": sub.get("evaluation_job_status"),
            "final_score": sub.get("evaluation_final_score"),
        }

    def get_confirmation(self, submission_id: str) -> Optional[Dict[str, Any]]:
        """Return safe submission confirmation details."""
        sub = self.repo.get_submission(submission_id, include_private_notes=False)
        if not sub:
            return None
        return {
            "submission_id": sub["submission_id"],
            "team_name": sub["team_name"],
            "repository_url": sub["repository_url"],
            "deployed_website_url": sub.get("deployed_website_url"),
            "commit_sha": sub.get("commit_sha"),
            "default_branch": sub.get("default_branch", "main"),
            "website_status": sub.get("website_status", "PENDING"),
            "submitted_at": sub["submitted_at"],
            "submission_status": sub["submission_status"],
        }

    def organizer_list_submissions(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return full submissions list for organizers including internal review notes."""
        return self.repo.list_submissions(
            limit=limit,
            offset=offset,
            review_status=status,
            search=search,
            include_private_notes=True
        )

    def organizer_get_submission(self, submission_id: str) -> Optional[Dict[str, Any]]:
        """Return complete submission record with internal notes for organizers."""
        return self.repo.get_submission(submission_id, include_private_notes=True)

    def organizer_update_review(
        self,
        submission_id: str,
        review_status: str,
        notes: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Update review status (ACCEPTED / REJECTED) and optionally add review notes."""
        if review_status not in ("ACCEPTED", "REJECTED", "UNDER_REVIEW"):
            return False, {"error": "INVALID_STATUS", "message": "Status must be ACCEPTED, REJECTED, or UNDER_REVIEW."}

        ok = self.repo.update_submission_review(submission_id, review_status, notes)
        if not ok:
            return False, {"error": "NOT_FOUND", "message": f"Submission '{submission_id}' not found."}

        return True, {
            "submission_id": submission_id,
            "organizer_review_status": review_status,
            "review_status": review_status,
            "notes": notes
        }

    def organizer_update_notes(self, submission_id: str, notes: str) -> Tuple[bool, Dict[str, Any]]:
        """Update internal organizer notes."""
        ok = self.repo.update_submission_notes(submission_id, notes)
        if not ok:
            return False, {"error": "NOT_FOUND", "message": f"Submission '{submission_id}' not found."}
        return True, {"submission_id": submission_id, "organizer_notes": notes}

    def organizer_evaluate_submission(
        self,
        submission_id: str,
        is_trusted: bool = False
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Initiate automated evaluation for an ACCEPTED submission.
        Uses the captured immutable commit SHA, NEVER the latest HEAD at evaluation time.
        Strict Fail-Closed Rule:
        If Docker daemon is unavailable, execution is BLOCKED safely,
        and submission status is updated to:
        'EVALUATION PENDING — SAFE EXECUTION WORKER UNAVAILABLE'.
        """
        sub = self.repo.get_submission(submission_id, include_private_notes=True)
        if not sub:
            return False, {"error": "NOT_FOUND", "message": f"Submission '{submission_id}' not found."}

        if sub["organizer_review_status"] != "ACCEPTED" and not is_trusted:
            return False, {
                "error": "SUBMISSION_NOT_ACCEPTED",
                "message": (
                    f"Submission '{submission_id}' cannot be evaluated because review status is "
                    f"'{sub['organizer_review_status']}'. Organizers must approve (ACCEPT) the submission first."
                )
            }

        # Captured immutable commit SHA check
        captured_commit_sha = sub.get("commit_sha")
        if not captured_commit_sha:
            return False, {
                "error": "COMMIT_NOT_CAPTURED",
                "message": (
                    f"Submission '{submission_id}' has no captured commit SHA. "
                    "Ensure repository verification succeeds before initiating evaluation."
                )
            }

        # Check Docker execution backend availability
        docker = DockerRunner()
        docker_available = docker.is_docker_daemon_available()

        if not docker_available and not is_trusted:
            pending_msg = "EVALUATION PENDING — SAFE EXECUTION WORKER UNAVAILABLE"
            self.repo.update_submission_status(submission_id, pending_msg)
            return False, {
                "error": "SAFE_WORKER_UNAVAILABLE",
                "message": (
                    f"{pending_msg}: The Docker daemon is offline. Untrusted code cannot be executed in this environment. "
                    f"Submission has been held safely in review queue."
                ),
                "submission_status": pending_msg
            }

        from hydraforge.api.services.evaluation_service import EvaluationService
        eval_service = EvaluationService(repository=self.repo)

        self.repo.update_submission_status(submission_id, "EVALUATION_QUEUED")

        # Crucial requirement: Must evaluate using the captured immutable commit SHA!
        success, res = eval_service.submit_evaluation(
            repository_url=sub["repository_url"],
            commit_sha=captured_commit_sha,
            submission_metadata={
                "submission_id": sub["submission_id"],
                "team_name": sub["team_name"],
                "deployed_website_url": sub.get("deployed_website_url"),
            },
            is_trusted=is_trusted
        )

        if not success:
            self.repo.update_submission_status(submission_id, "EVALUATION_FAILED")
            return False, res

        job_id = res["job_id"]
        self.repo.link_evaluation_job(submission_id, job_id)
        final_status = "EVALUATION_COMPLETED" if res["status"] == "COMPLETED" else "EVALUATION_FAILED"
        self.repo.update_submission_status(submission_id, final_status)

        return True, {
            "submission_id": submission_id,
            "job_id": job_id,
            "captured_commit_evaluated": captured_commit_sha,
            "evaluation_result": res,
            "submission_status": final_status
        }
