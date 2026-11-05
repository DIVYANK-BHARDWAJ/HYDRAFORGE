import { OverviewStats, LeaderboardEntry, BenchmarkSummary, SystemStatus, EvaluationJobSummary } from '../types';

const API_BASE = '/api/v1';

export const api = {
  async getOverview(): Promise<OverviewStats> {
    const res = await fetch(`${API_BASE}/overview`);
    if (!res.ok) throw new Error('Failed to fetch overview metrics');
    return res.json();
  },

  async getLeaderboard(version = '1.0.0'): Promise<LeaderboardEntry[]> {
    const res = await fetch(`${API_BASE}/leaderboard?version=${encodeURIComponent(version)}`);
    if (!res.ok) throw new Error('Failed to fetch leaderboard');
    const data = await res.json();
    return data.leaderboard;
  },

  async getBenchmark(): Promise<BenchmarkSummary> {
    const res = await fetch(`${API_BASE}/benchmark`);
    if (!res.ok) throw new Error('Failed to fetch benchmark details');
    return res.json();
  },

  async getSystemStatus(): Promise<SystemStatus> {
    const res = await fetch(`${API_BASE}/system`);
    if (!res.ok) throw new Error('Failed to fetch system telemetry');
    return res.json();
  },

  async listEvaluations(limit = 100, offset = 0): Promise<EvaluationJobSummary[]> {
    const res = await fetch(`${API_BASE}/evaluations?limit=${limit}&offset=${offset}`);
    if (!res.ok) throw new Error('Failed to fetch evaluation jobs');
    const data = await res.json();
    return data.jobs;
  },

  async submitEvaluation(payload: {
    repository_url: string;
    commit_sha: string;
    team_name?: string;
    submission_name?: string;
    is_trusted?: boolean;
  }) {
    const res = await fetch(`${API_BASE}/evaluations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repository_url: payload.repository_url,
        commit_sha: payload.commit_sha,
        is_trusted: payload.is_trusted || false,
        metadata: {
          team_name: payload.team_name,
          submission_name: payload.submission_name,
        }
      })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.message || data.error || 'Submission failed');
    }
    return data;
  },

  // Phase 4B Participant Portal APIs
  async registerParticipantSubmission(payload: any) {
    const res = await fetch(`${API_BASE}/submissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || data.error || 'Registration failed');
    return data;
  },

  async getPublicSubmissionStatus(submissionId: string) {
    const res = await fetch(`${API_BASE}/submissions/${encodeURIComponent(submissionId)}/status`);
    if (!res.ok) throw new Error('Submission ID not found');
    return res.json();
  },

  async getSubmissionConfirmation(submissionId: string) {
    const res = await fetch(`${API_BASE}/submissions/${encodeURIComponent(submissionId)}/confirmation`);
    if (!res.ok) throw new Error('Confirmation not found');
    return res.json();
  },

  // Phase 4B Organizer Protected APIs
  async organizerLogin(username: string, password: string) {
    const res = await fetch(`${API_BASE}/organizer/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || 'Login failed');
    return data;
  },

  async organizerListSubmissions(token: string, status?: string, search?: string) {
    let url = `${API_BASE}/organizer/submissions?limit=100`;
    if (status) url += `&status=${encodeURIComponent(status)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const res = await fetch(url, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Failed to fetch organizer submissions');
    const data = await res.json();
    return data.submissions;
  },

  async organizerGetSubmission(token: string, submissionId: string) {
    const res = await fetch(`${API_BASE}/organizer/submissions/${encodeURIComponent(submissionId)}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) throw new Error('Failed to fetch submission details');
    return res.json();
  },

  async organizerUpdateReview(token: string, submissionId: string, status: string, notes?: string) {
    const res = await fetch(`${API_BASE}/organizer/submissions/${encodeURIComponent(submissionId)}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ status, notes })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || 'Update failed');
    return data;
  },

  async organizerUpdateNotes(token: string, submissionId: string, notes: string) {
    const res = await fetch(`${API_BASE}/organizer/submissions/${encodeURIComponent(submissionId)}/notes`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ notes })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || 'Notes update failed');
    return data;
  },

  async organizerEvaluateSubmission(token: string, submissionId: string) {
    const res = await fetch(`${API_BASE}/organizer/submissions/${encodeURIComponent(submissionId)}/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || data.error || 'Evaluation request blocked');
    return data;
  }
};

