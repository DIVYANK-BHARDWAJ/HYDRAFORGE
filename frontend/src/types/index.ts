export interface OverviewStats {
  total_evaluation_jobs: number;
  completed_evaluations: number;
  failed_evaluations: number;
  pending_evaluations: number;
  leaderboard_size: number;
  average_score: number | null;
  benchmark_version: string;
  scoring_version: string;
  execution_backend_status: {
    docker_daemon_online: boolean;
    untrusted_execution_ready: boolean;
    trusted_local_runner_available: boolean;
  };
}

export interface LeaderboardEntry {
  rank: number;
  job_id: string;
  team_name: string;
  submission_name: string;
  repository_url: string;
  commit_sha: string;
  total_score: number;
  forecast_skill: number;
  event_detection: number;
  generalization: number;
  calibration: number;
  robustness: number;
  efficiency: number;
  completed_at: string;
  benchmark_version: string;
  scoring_version: string;
}

export interface BenchmarkSummary {
  dataset_name: string;
  benchmark_version: string;
  catchment_count: number;
  region_count: number;
  regions: string[];
  horizons_hours: number[];
  available_splits: string[];
  split_manifests: Record<string, { case_count: number; catchment_count: number; corruption_family: string | null }>;
  leakage_audit: {
    is_leakage_free: boolean;
    overlap_count: number;
    audit_timestamp: string;
  };
}

export interface SystemStatus {
  application: string;
  version: string;
  python_version: string;
  database_status: string;
  execution_backends: {
    docker_daemon_available: boolean;
    docker_runner_ready: boolean;
    local_test_runner_available: boolean;
    untrusted_execution_ready: boolean;
  };
  hardware_telemetry: {
    cpu_cores_logical: number;
    total_memory_mb: number;
    available_memory_mb: number;
    memory_usage_percent: number;
  };
  benchmark_readiness: {
    synthetic_suite_ready: boolean;
    genuine_caravan_ready: boolean;
  };
  security_warnings: string[];
}

export interface EvaluationJobSummary {
  job_id: string;
  repository_url: string;
  commit_sha: string;
  submission_metadata: {
    team_name?: string;
    submission_name?: string;
  } | null;
  contract_version: string;
  benchmark_version: string;
  scoring_version: string;
  execution_backend: string;
  job_status: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  failure_reason: string | null;
  final_score: number | null;
  report_hash: string | null;
}

export interface ParticipantSubmissionPayload {
  team_name: string;
  team_leader: string;
  contact_email: string;
  institution?: string;
  team_members?: string[];
  project_name: string;
  project_description: string;
  programming_language: string;
  model_architecture: string;
  repository_url: string;
  commit_sha: string;
  training_datasets: string;
  dataset_sources: string;
  dataset_licenses: string;
  pretrained_models: string;
  inference_time_data: string;
  provenance_notes: string;
  declarations: {
    authority_to_submit: boolean;
    accurate_disclosures: boolean;
    license_compliance: boolean;
    inference_rules_compliance: boolean;
    no_hidden_label_access: boolean;
    agreed_to_rules: boolean;
  };
}

export interface SubmissionRecord {
  submission_id: string;
  team_name: string;
  team_leader: string;
  contact_email: string;
  team_members: string[] | string | null;
  institution: string | null;
  project_name: string;
  project_description: string;
  repository_url: string;
  commit_sha: string;
  deployed_website_url?: string;
  default_branch?: string;
  website_status?: string;
  website_error?: string | null;
  programming_language?: string;
  model_architecture: string;
  training_datasets: string;
  dataset_sources: string;
  dataset_licenses: string;
  pretrained_models: string;
  inference_time_data: string;
  provenance_notes: string;
  submitted_at: string;
  verification_status: string;
  verification_details: string | null;
  organizer_review_status: string;
  organizer_notes?: string;
  submission_status: string;
  linked_evaluation_job_id: string | null;
  evaluation_job_status?: string | null;
  evaluation_final_score?: number | null;
}

export interface PublicSubmissionStatus {
  submission_id: string;
  team_name: string;
  project_name: string;
  repository_url: string;
  commit_sha: string;
  submitted_at: string;
  verification_status: string;
  verification_details: string | null;
  review_status: string;
  submission_status: string;
  linked_evaluation_job_id: string | null;
  evaluation_job_status: string | null;
  final_score: number | null;
}

