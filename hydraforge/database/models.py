"""Database Record Models and Types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class JobRecord:
    job_id: str
    repository_url: str
    commit_sha: str
    submission_metadata: Optional[Dict[str, Any]]
    contract_version: str
    benchmark_version: str
    scoring_version: str
    execution_backend: str
    job_status: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    failure_reason: Optional[str]
    final_score: Optional[float]
    report_hash: Optional[str]


@dataclass
class ResultRecord:
    result_id: str
    job_id: str
    total_score: float
    forecast_skill: float
    event_detection: float
    generalization: float
    calibration: float
    robustness: float
    efficiency: float
    full_report_json: str


@dataclass
class SubmissionRecord:
    submission_id: str
    team_name: str
    repository_url: str
    deployed_website_url: str
    commit_sha: Optional[str] = None
    default_branch: str = "main"
    website_status: str = "PENDING"
    submitted_at: str = ""
    verification_status: str = "PENDING"
    verification_details: Optional[str] = None
    organizer_review_status: str = "UNDER_REVIEW"
    organizer_notes: Optional[str] = None
    submission_status: str = "SUBMITTED"
    linked_evaluation_job_id: Optional[str] = None
    # Optional metadata
    team_leader: Optional[str] = None
    contact_email: Optional[str] = None
    team_members: Optional[str] = None
    institution: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    programming_language: Optional[str] = None
    model_architecture: Optional[str] = None
    training_datasets: Optional[str] = None
    dataset_sources: Optional[str] = None
    dataset_licenses: Optional[str] = None
    pretrained_models: Optional[str] = None
    inference_time_data: Optional[str] = None
    provenance_notes: Optional[str] = None
    declaration_status: bool = True


