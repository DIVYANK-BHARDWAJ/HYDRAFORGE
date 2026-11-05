import React, { useState } from 'react';
import { api } from '../services/api';

interface ParticipantRegistrationProps {
  onSuccess: (submissionId: string) => void;
}

export const ParticipantRegistration: React.FC<ParticipantRegistrationProps> = ({ onSuccess }) => {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successInfo, setSuccessInfo] = useState<any | null>(null);

  // Strictly exactly two fields
  const [teamName, setTeamName] = useState('');
  const [repoUrl, setRepoUrl] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessInfo(null);
    setSubmitting(true);

    const payload = {
      team_name: teamName.trim(),
      repository_url: repoUrl.trim(),
    };

    try {
      const res = await api.registerParticipantSubmission(payload);
      setSuccessInfo(res);
      onSuccess(res.submission_id);
    } catch (err: any) {
      setErrorMsg(err.message || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">Participant Project Submission</h2>
        <p className="text-xs text-slate-400 mt-1">
          Fast registration for the BASINSHIFT challenge. Exactly two fields required: Team Name and GitHub Repository URL.
          Our evaluation engine automatically discovers your repository default branch and captures the immutable HEAD commit SHA.
        </p>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-xl border border-rose-800 bg-rose-950/40 text-rose-200 text-xs font-mono">
          <strong>Registration Error:</strong> {errorMsg}
        </div>
      )}

      {successInfo && (
        <div className="p-5 rounded-xl border border-emerald-800 bg-emerald-950/40 text-emerald-200 space-y-2">
          <div className="font-bold text-sm">Submission Received Successfully!</div>
          <div className="font-mono text-xs">
            Submission ID: <span className="text-white font-bold">{successInfo.submission_id}</span>
          </div>
          <div className="text-xs text-slate-300 space-y-1 pt-1">
            <div>• Repository: <span className="font-mono text-cyan-300">{successInfo.repository_url}</span></div>
            <div>• Locked Commit: <span className="font-mono text-white">{successInfo.commit_sha || 'Pending verification'}</span></div>
            <div>• Default Branch: <span className="font-mono text-cyan-300">{successInfo.default_branch || 'main'}</span></div>
          </div>
          <p className="text-xs text-slate-400 pt-2">
            Store this Submission ID safely to monitor verification, review decisions, and official benchmark evaluation scores.
          </p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1">
            1. Team Name <span className="text-rose-400">*</span>
          </label>
          <input
            type="text"
            required
            value={teamName}
            onChange={(e) => setTeamName(e.target.value)}
            placeholder="e.g. AlpineHydro Lab"
            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-cyan-500"
          />
          <p className="text-[11px] text-slate-500 mt-1">Official team or organization name shown on the leaderboard.</p>
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-300 mb-1">
            2. GitHub Repository URL <span className="text-rose-400">*</span>
          </label>
          <input
            type="url"
            required
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/organization/repository"
            className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-white font-mono focus:outline-none focus:border-cyan-500"
          />
          <p className="text-[11px] text-slate-500 mt-1">Must be a public GitHub repository. No participant token or manual commit hash required.</p>
        </div>

        <div className="pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="w-full py-3 px-6 rounded-xl font-bold text-sm bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 shadow-lg shadow-cyan-500/20 disabled:opacity-50 transition-all cursor-pointer"
          >
            {submitting ? 'Verifying & Submitting...' : 'Submit Project for BASINSHIFT Review →'}
          </button>
        </div>
      </form>
    </div>
  );
};
