import React, { useState } from 'react';
import { api } from '../services/api';
import { PublicSubmissionStatus } from '../types';

export const ParticipantStatusTracking: React.FC = () => {
  const [submissionId, setSubmissionId] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusData, setStatusData] = useState<PublicSubmissionStatus | null>(null);

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!submissionId.trim()) return;

    setErrorMsg(null);
    setLoading(true);

    try {
      const data = await api.getPublicSubmissionStatus(submissionId.trim());
      setStatusData(data);
    } catch (err: any) {
      setStatusData(null);
      setErrorMsg(err.message || 'Submission ID not found.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">Track Submission Status</h2>
        <p className="text-xs text-slate-400 mt-1">
          Enter your unique Submission ID to inspect repository verification, review progress, and official results.
        </p>
      </div>

      <form onSubmit={handleLookup} className="flex gap-3">
        <input
          type="text"
          required
          value={submissionId}
          onChange={(e) => setSubmissionId(e.target.value)}
          placeholder="e.g. sub_389ab2f409..."
          className="flex-1 bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500 font-mono"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-6 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 disabled:opacity-50 text-slate-950 font-bold text-sm shadow-lg shadow-cyan-500/20 transition"
        >
          {loading ? 'Searching...' : 'Lookup'}
        </button>
      </form>

      {errorMsg && (
        <div className="p-4 rounded-xl border border-rose-800 bg-rose-950/40 text-rose-200 text-xs font-mono">
          {errorMsg}
        </div>
      )}

      {statusData && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-2">
            <div>
              <h3 className="text-xl font-bold text-white">{statusData.project_name}</h3>
              <p className="text-xs text-slate-400">Team: {statusData.team_name}</p>
            </div>
            <span
              className={`px-3 py-1 rounded-full text-xs font-mono font-bold self-start sm:self-center border ${
                statusData.submission_status === 'ACCEPTED' || statusData.submission_status === 'EVALUATION_COMPLETED'
                  ? 'bg-emerald-950 border-emerald-800 text-emerald-300'
                  : statusData.submission_status === 'REJECTED'
                  ? 'bg-rose-950 border-rose-800 text-rose-300'
                  : 'bg-cyan-950 border-cyan-800 text-cyan-300'
              }`}
            >
              {statusData.submission_status}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 font-mono text-xs">
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-slate-400 block text-[11px] uppercase tracking-wider mb-1">
                Repository Verification
              </span>
              <span
                className={`font-bold ${
                  statusData.verification_status === 'VERIFIED' ? 'text-emerald-400' : 'text-amber-400'
                }`}
              >
                {statusData.verification_status}
              </span>
              <p className="text-slate-400 text-[11px] mt-1">
                {statusData.verification_details || 'Verified repository format.'}
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800">
              <span className="text-slate-400 block text-[11px] uppercase tracking-wider mb-1">
                Organizer Review Status
              </span>
              <span
                className={`font-bold ${
                  statusData.review_status === 'ACCEPTED'
                    ? 'text-emerald-400'
                    : statusData.review_status === 'REJECTED'
                    ? 'text-rose-400'
                    : 'text-amber-400'
                }`}
              >
                {statusData.review_status}
              </span>
              <p className="text-slate-400 text-[11px] mt-1">Official evaluation clearance</p>
            </div>
          </div>

          <div className="p-5 rounded-xl bg-slate-950 border border-slate-800 flex justify-between items-center">
            <div>
              <span className="text-slate-400 block text-[11px] uppercase tracking-wider mb-1">
                Evaluation Score
              </span>
              <span className="text-sm font-semibold text-cyan-400">
                {statusData.evaluation_job_status || 'Evaluation not run yet'}
              </span>
            </div>
            <div className="text-right">
              <span className="text-3xl font-extrabold text-white font-mono">
                {statusData.final_score !== null && statusData.final_score !== undefined
                  ? statusData.final_score.toFixed(2)
                  : '—'}
              </span>
              <span className="text-xs text-slate-500 ml-1">/100</span>
            </div>
          </div>

          <div className="text-[11px] text-slate-500 font-mono space-y-1">
            <div>Repository: <span className="text-slate-400">{statusData.repository_url}</span></div>
            <div>Commit SHA: <span className="text-cyan-400">{statusData.commit_sha}</span></div>
            <div>Submitted: <span className="text-slate-400">{new Date(statusData.submitted_at).toLocaleString()}</span></div>
          </div>
        </div>
      )}
    </div>
  );
};

