import React, { useState } from 'react';
import { api } from '../services/api';

interface NewEvaluationProps {
  onSuccess: () => void;
  dockerOnline: boolean;
}

export const NewEvaluation: React.FC<NewEvaluationProps> = ({ onSuccess, dockerOnline }) => {
  const [repoUrl, setRepoUrl] = useState('');
  const [commitSha, setCommitSha] = useState('');
  const [teamName, setTeamName] = useState('');
  const [submissionName, setSubmissionName] = useState('');
  const [isTrusted, setIsTrusted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successResult, setSuccessResult] = useState<any | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessResult(null);
    setSubmitting(true);

    try {
      const res = await api.submitEvaluation({
        repository_url: repoUrl.trim(),
        commit_sha: commitSha.trim(),
        team_name: teamName.trim() || undefined,
        submission_name: submissionName.trim() || undefined,
        is_trusted: isTrusted,
      });
      setSuccessResult(res);
      onSuccess();
    } catch (err: any) {
      setErrorMsg(err.message || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  const loadTrustedMock = () => {
    setRepoUrl('tests/fixtures/mock_submission');
    setCommitSha('0000000000000000000000000000000000000000');
    setTeamName('HydraTeam');
    setSubmissionName('MockForecaster-v1');
    setIsTrusted(true);
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">Evaluate Repository</h2>
        <p className="text-xs text-slate-400 mt-1">
          Submit an immutable GitHub commit SHA or trusted test fixture for automated multi-split evaluation.
        </p>
      </div>

      {!dockerOnline && (
        <div className="p-4 rounded-xl border border-amber-800/80 bg-amber-950/30 text-amber-200 text-xs space-y-2">
          <div className="font-bold flex items-center space-x-2">
            <span>⚠️ Fail-Closed Security Policy Active</span>
          </div>
          <p>
            The Docker daemon is currently offline. To protect against malicious code execution, HYDRAFORGE
            strictly prohibits running untrusted participant code outside isolated containers.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={loadTrustedMock}
              className="px-3 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 font-semibold border border-amber-700/50 transition"
            >
              Load Trusted Mock Fixture (Organizer Test Mode)
            </button>
          </div>
        </div>
      )}

      {errorMsg && (
        <div className="p-4 rounded-xl border border-rose-800 bg-rose-950/40 text-rose-200 text-xs">
          <div className="font-bold">Evaluation Blocked</div>
          <p className="mt-1 font-mono whitespace-pre-wrap">{errorMsg}</p>
        </div>
      )}

      {successResult && (
        <div className="p-4 rounded-xl border border-emerald-800 bg-emerald-950/40 text-emerald-200 text-xs space-y-2">
          <div className="font-bold text-sm">Evaluation Completed Successfully!</div>
          <div className="grid grid-cols-2 gap-2 font-mono">
            <div>Job ID: <span className="text-white">{successResult.job_id}</span></div>
            <div>Score: <span className="text-cyan-400 font-bold">{successResult.final_score} / 100</span></div>
            <div>Status: <span className="text-emerald-400">{successResult.status}</span></div>
            <div>Report Hash: <span className="text-slate-400">{successResult.report_hash?.slice(0, 16)}...</span></div>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-2xl p-6 space-y-5 shadow-lg">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Team Name
            </label>
            <input
              type="text"
              value={teamName}
              onChange={(e) => setTeamName(e.target.value)}
              placeholder="e.g. RiverWatchers"
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500 font-sans"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Submission / Model Name
            </label>
            <input
              type="text"
              value={submissionName}
              onChange={(e) => setSubmissionName(e.target.value)}
              placeholder="e.g. HydroTransformer-v2"
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500 font-sans"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
            Git Repository URL <span className="text-rose-400">*</span>
          </label>
          <input
            type="text"
            required
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/organization/repository.git"
            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500 font-mono"
          />
          <p className="text-[11px] text-slate-500 mt-1 font-mono">
            Allowed domains: github.com, gitlab.com. Private IPs, localhost, and file URLs are rejected.
          </p>
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
            Immutable Commit SHA <span className="text-rose-400">*</span>
          </label>
          <input
            type="text"
            required
            maxLength={40}
            value={commitSha}
            onChange={(e) => setCommitSha(e.target.value)}
            placeholder="40-character hexadecimal Git commit hash"
            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500 font-mono"
          />
          <p className="text-[11px] text-slate-500 mt-1 font-mono">
            Mutable branch references (main, master, HEAD) are rejected to guarantee reproducibility.
          </p>
        </div>

        <div className="pt-2 flex items-center space-x-2">
          <input
            type="checkbox"
            id="trustedCheckbox"
            checked={isTrusted}
            onChange={(e) => setIsTrusted(e.target.checked)}
            className="rounded border-slate-800 text-cyan-500 focus:ring-0 bg-slate-950"
          />
          <label htmlFor="trustedCheckbox" className="text-xs text-slate-300 font-medium">
            Explicitly mark submission as trusted organizer fixture (enables local runner when Docker is offline)
          </label>
        </div>

        <div className="pt-4 border-t border-slate-800 flex justify-end space-x-3">
          <button
            type="submit"
            disabled={submitting}
            className="px-6 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 font-bold text-sm shadow-lg shadow-cyan-500/20 transition"
          >
            {submitting ? 'Executing Evaluation...' : 'Run Automated Evaluation'}
          </button>
        </div>
      </form>
    </div>
  );
};

