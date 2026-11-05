import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { SubmissionRecord } from '../types';

export const OrganizerConsole: React.FC = () => {
  const [token, setToken] = useState<string>(localStorage.getItem('hydraforge_organizer_token') || '');
  const [username, setUsername] = useState('organizer');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);

  const [submissions, setSubmissions] = useState<SubmissionRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSub, setSelectedSub] = useState<SubmissionRecord | null>(null);
  const [organizerNotes, setOrganizerNotes] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError(null);
    try {
      const data = await api.organizerLogin(username, password);
      setToken(data.token);
      localStorage.setItem('hydraforge_organizer_token', data.token);
    } catch (err: any) {
      setLoginError(err.message || 'Login failed');
    }
  };

  const handleLogout = () => {
    setToken('');
    localStorage.removeItem('hydraforge_organizer_token');
    setSubmissions([]);
  };

  const fetchSubmissions = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const list = await api.organizerListSubmissions(token, statusFilter || undefined, searchTerm || undefined);
      setSubmissions(list);
    } catch (err) {
      console.error(err);
      if (String(err).includes('401') || String(err).includes('Unauthorized')) {
        handleLogout();
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (token) {
      fetchSubmissions();
    }
  }, [token, statusFilter]);

  const handleUpdateReview = async (submissionId: string, status: string) => {
    if (!token) return;
    try {
      await api.organizerUpdateReview(token, submissionId, status);
      fetchSubmissions();
      if (selectedSub && selectedSub.submission_id === submissionId) {
        setSelectedSub({ ...selectedSub, organizer_review_status: status });
      }
    } catch (err: any) {
      alert(`Update failed: ${err.message}`);
    }
  };

  const handleSaveNotes = async (submissionId: string) => {
    if (!token) return;
    try {
      await api.organizerUpdateNotes(token, submissionId, organizerNotes);
      alert('Internal review notes saved.');
      fetchSubmissions();
    } catch (err: any) {
      alert(`Failed to save notes: ${err.message}`);
    }
  };

  const handleEvaluate = async (submissionId: string) => {
    if (!token) return;
    if (!confirm('Initiate automated evaluation on this submission? (Anchored to captured commit)')) return;
    try {
      const res = await api.organizerEvaluateSubmission(token, submissionId);
      alert(`Evaluation completed! Status: ${res.submission_status}`);
      fetchSubmissions();
    } catch (err: any) {
      alert(`Evaluation blocked safely: ${err.message}`);
      fetchSubmissions();
    }
  };

  if (!token) {
    return (
      <div className="max-w-md mx-auto my-12 bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-xl">
        <h2 className="text-xl font-bold text-white text-center mb-2">Organizer Authentication</h2>
        <p className="text-xs text-slate-400 text-center mb-6">
          Access restricted to BASINSHIFT challenge organizers and evaluators.
        </p>

        {loginError && (
          <div className="p-3 mb-4 rounded-xl border border-rose-800 bg-rose-950/40 text-rose-200 text-xs">
            {loginError}
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-xs uppercase font-semibold text-slate-400 mb-1">Username</label>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label className="block text-xs uppercase font-semibold text-slate-400 mb-1">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter organizer password"
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
            />
          </div>
          <button
            type="submit"
            className="w-full py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-sm shadow-lg shadow-cyan-500/20 transition mt-2 cursor-pointer"
          >
            Authenticate Session
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Organizer Submissions Console</h2>
          <p className="text-xs text-slate-400 mt-1">
            Review participant registrations, verify websites & GitHub commits, manage notes, and initiate evaluations.
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={fetchSubmissions}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition cursor-pointer"
          >
            Refresh
          </button>
          <button
            onClick={handleLogout}
            className="px-3 py-1.5 rounded-lg bg-rose-950 hover:bg-rose-900 text-rose-300 text-xs font-semibold border border-rose-800 transition cursor-pointer"
          >
            Logout
          </button>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="flex flex-wrap gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
        >
          <option value="">All Review Statuses</option>
          <option value="UNDER_REVIEW">Under Review</option>
          <option value="ACCEPTED">Accepted</option>
          <option value="REJECTED">Rejected</option>
        </select>

        <div className="flex gap-2">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetchSubmissions()}
            placeholder="Search team, repository, or ID..."
            className="bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 min-w-[220px]"
          />
          <button
            onClick={fetchSubmissions}
            className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 cursor-pointer"
          >
            Search
          </button>
        </div>
      </div>

      {/* Submissions Table */}
      {loading ? (
        <div className="p-12 text-center text-slate-400 font-mono">Loading participant submissions...</div>
      ) : submissions.length === 0 ? (
        <div className="p-12 text-center text-slate-400 bg-slate-900 border border-slate-800 rounded-xl">
          No participant submissions match your filters.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900 shadow">
          <table className="w-full text-left text-sm font-sans">
            <thead className="bg-slate-950/70 border-b border-slate-800 text-[11px] font-mono uppercase tracking-wider text-slate-400">
              <tr>
                <th className="py-3 px-4">ID / Time</th>
                <th className="py-3 px-4">Team Name</th>
                <th className="py-3 px-4">GitHub Repository</th>
                <th className="py-3 px-4">Deployed Website</th>
                <th className="py-3 px-4">Captured Commit</th>
                <th className="py-3 px-4">Verification</th>
                <th className="py-3 px-4">Review</th>
                <th className="py-3 px-4">Evaluation</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
              {submissions.map((sub) => (
                <tr key={sub.submission_id} className="hover:bg-slate-800/40">
                  <td className="py-3 px-4">
                    <div className="text-cyan-400 font-bold">{sub.submission_id.slice(0, 10)}...</div>
                    <div className="text-[10px] text-slate-500 font-sans">{new Date(sub.submitted_at).toLocaleDateString()}</div>
                  </td>
                  <td className="py-3 px-4 font-sans font-bold text-white">
                    {sub.team_name}
                  </td>
                  <td className="py-3 px-4">
                    <a
                      href={sub.repository_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-cyan-400 underline hover:text-cyan-300 break-all"
                    >
                      {sub.repository_url.replace('https://github.com/', '')}
                    </a>
                  </td>
                  <td className="py-3 px-4">
                    {sub.deployed_website_url ? (
                      <div>
                        <a
                          href={sub.deployed_website_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-cyan-400 underline hover:text-cyan-300 text-xs font-sans"
                        >
                          Visit Site ↗
                        </a>
                        <div className="text-[10px] text-slate-400">{sub.website_status || 'PENDING'}</div>
                      </div>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    <code className="text-[11px] text-white bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800" title={sub.commit_sha || ''}>
                      {sub.commit_sha ? sub.commit_sha.slice(0, 8) : 'PENDING'}
                    </code>
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] border ${
                        sub.verification_status === 'VERIFIED'
                          ? 'bg-emerald-950 border-emerald-800 text-emerald-300'
                          : sub.verification_status === 'FAILED'
                          ? 'bg-rose-950 border-rose-800 text-rose-300'
                          : 'bg-amber-950 border-amber-800 text-amber-300'
                      }`}
                    >
                      {sub.verification_status}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] border ${
                        sub.organizer_review_status === 'ACCEPTED'
                          ? 'bg-emerald-950 border-emerald-800 text-emerald-300'
                          : sub.organizer_review_status === 'REJECTED'
                          ? 'bg-rose-950 border-rose-800 text-rose-300'
                          : 'bg-amber-950 border-amber-800 text-amber-300'
                      }`}
                    >
                      {sub.organizer_review_status}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-sans text-xs">
                    <div className="text-slate-300 font-medium">{sub.submission_status}</div>
                    {sub.evaluation_final_score !== null && sub.evaluation_final_score !== undefined && (
                      <div className="text-cyan-400 font-mono font-bold">{sub.evaluation_final_score.toFixed(2)} pts</div>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div className="flex items-center justify-end space-x-1 font-sans">
                      <button
                        onClick={() => {
                          setSelectedSub(sub);
                          setOrganizerNotes(sub.organizer_notes || '');
                        }}
                        className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-slate-700 cursor-pointer"
                      >
                        Inspect
                      </button>
                      {sub.organizer_review_status !== 'ACCEPTED' && (
                        <button
                          onClick={() => handleUpdateReview(sub.submission_id, 'ACCEPTED')}
                          className="px-2 py-1 rounded bg-emerald-950 hover:bg-emerald-900 text-emerald-300 text-xs border border-emerald-800 cursor-pointer"
                        >
                          Accept
                        </button>
                      )}
                      {sub.organizer_review_status !== 'REJECTED' && (
                        <button
                          onClick={() => handleUpdateReview(sub.submission_id, 'REJECTED')}
                          className="px-2 py-1 rounded bg-rose-950 hover:bg-rose-900 text-rose-300 text-xs border border-rose-800 cursor-pointer"
                        >
                          Reject
                        </button>
                      )}
                      {sub.organizer_review_status === 'ACCEPTED' && sub.submission_status !== 'EVALUATION_COMPLETED' && (
                        <button
                          onClick={() => handleEvaluate(sub.submission_id)}
                          className="px-2 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold text-xs shadow-sm cursor-pointer"
                        >
                          Evaluate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Details and Notes Inspection Modal */}
      {selectedSub && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full max-h-[85vh] overflow-y-auto p-6 space-y-6 shadow-2xl">
            <div className="flex justify-between items-center border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-white">{selectedSub.team_name}</h3>
                <p className="text-xs text-slate-400">ID: {selectedSub.submission_id} • Submitted: {new Date(selectedSub.submitted_at).toLocaleString()}</p>
              </div>
              <button
                onClick={() => setSelectedSub(null)}
                className="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs cursor-pointer"
              >
                ✕ Close
              </button>
            </div>

            <div className="space-y-4 text-xs font-mono">
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                <h4 className="font-sans font-bold text-sm text-cyan-400">Submission Details</h4>
                <div>
                  <strong>Repository:</strong>{' '}
                  <a href={selectedSub.repository_url} target="_blank" rel="noopener noreferrer" className="text-cyan-400 underline">
                    {selectedSub.repository_url}
                  </a>
                </div>
                <div><strong>Default Branch:</strong> <code>{selectedSub.default_branch || 'HEAD'}</code></div>
                <div><strong>Captured Commit SHA:</strong> <code className="text-cyan-300">{selectedSub.commit_sha || 'Pending verification'}</code></div>
                <div>
                  <strong>Deployed Website:</strong>{' '}
                  <a href={selectedSub.deployed_website_url} target="_blank" rel="noopener noreferrer" className="text-cyan-400 underline">
                    {selectedSub.deployed_website_url}
                  </a>
                </div>
                <div><strong>Website Status:</strong> {selectedSub.website_status || 'PENDING'}</div>
                {selectedSub.website_error && (
                  <div className="text-rose-400"><strong>Website Error / Notice:</strong> {selectedSub.website_error}</div>
                )}
                <div><strong>Verification Details:</strong> {selectedSub.verification_details || 'N/A'}</div>
              </div>

              <div>
                <label className="font-sans font-bold text-sm text-white block mb-1">
                  Organizer Private Review Notes (Confidential)
                </label>
                <textarea
                  value={organizerNotes}
                  onChange={(e) => setOrganizerNotes(e.target.value)}
                  placeholder="Record internal verification notes, rationale, or instructions..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-white font-sans focus:outline-none focus:border-cyan-500 min-h-[90px]"
                />
                <div className="mt-2 flex justify-end">
                  <button
                    onClick={() => handleSaveNotes(selectedSub.submission_id)}
                    className="px-4 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs cursor-pointer"
                  >
                    Save Internal Notes
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
