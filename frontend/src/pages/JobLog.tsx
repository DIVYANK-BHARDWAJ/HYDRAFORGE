import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { EvaluationJobSummary } from '../types';

export const JobLog: React.FC = () => {
  const [jobs, setJobs] = useState<EvaluationJobSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const data = await api.listEvaluations(50, 0);
      setJobs(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Evaluation Jobs Audit Log</h2>
          <p className="text-xs text-slate-400 mt-1">Immutable execution history, status transitions, and audit hashes.</p>
        </div>
        <button
          onClick={fetchJobs}
          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition"
        >
          Refresh Jobs
        </button>
      </div>

      {loading ? (
        <div className="p-12 text-center text-slate-400 font-mono">Loading job history...</div>
      ) : jobs.length === 0 ? (
        <div className="p-12 text-center text-slate-400 bg-slate-900 border border-slate-800 rounded-xl">
          No evaluation jobs recorded yet.
        </div>
      ) : (
        <div className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden shadow">
          <table className="w-full text-left text-sm font-sans">
            <thead className="bg-slate-950/60 border-b border-slate-800 text-[11px] font-mono uppercase tracking-wider text-slate-400">
              <tr>
                <th className="py-3 px-4">Job ID</th>
                <th className="py-3 px-4">Team & Model</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Score</th>
                <th className="py-3 px-4">Commit SHA</th>
                <th className="py-3 px-4 text-right">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
              {jobs.map((job) => (
                <tr key={job.job_id} className="hover:bg-slate-800/40">
                  <td className="py-3 px-4 text-cyan-400 font-bold">{job.job_id}</td>
                  <td className="py-3 px-4 font-sans text-white">
                    {job.submission_metadata?.team_name || 'Anonymous'} - {job.submission_metadata?.submission_name || 'Unnamed'}
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-mono border ${
                        job.job_status === 'COMPLETED'
                          ? 'bg-emerald-950 border-emerald-800 text-emerald-300'
                          : job.job_status === 'UNSAFE_EXECUTION_ENVIRONMENT'
                          ? 'bg-amber-950 border-amber-800 text-amber-300'
                          : 'bg-rose-950 border-rose-800 text-rose-300'
                      }`}
                    >
                      {job.job_status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right font-bold text-white">
                    {job.final_score !== null ? `${job.final_score.toFixed(2)}` : '—'}
                  </td>
                  <td className="py-3 px-4 text-slate-400">{job.commit_sha.slice(0, 8)}</td>
                  <td className="py-3 px-4 text-right text-slate-500 font-mono text-[11px]">
                    {new Date(job.created_at).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

