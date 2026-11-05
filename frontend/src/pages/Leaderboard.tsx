import React from 'react';
import { LeaderboardEntry } from '../types';
import { LeaderboardTable } from '../components/LeaderboardTable';

interface LeaderboardProps {
  entries: LeaderboardEntry[];
  loading: boolean;
  onRefresh: () => void;
}

export const Leaderboard: React.FC<LeaderboardProps> = ({ entries, loading, onRefresh }) => {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Official Challenge Leaderboard</h2>
          <p className="text-xs text-slate-400 mt-1">
            Ranked by overall composite score across all six deterministic evaluation dimensions.
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <span className="text-xs font-mono text-slate-400">Benchmark: v1.0.0</span>
          <button
            onClick={onRefresh}
            className="px-3 py-1.5 rounded-lg bg-slate-850 hover:bg-slate-800 text-slate-200 text-xs font-semibold border border-slate-700 transition"
          >
            Refresh Rankings
          </button>
        </div>
      </div>

      <LeaderboardTable entries={entries} loading={loading} />

      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 text-xs text-slate-400 space-y-2">
        <h4 className="font-bold text-slate-300">Leaderboard Guarantees:</h4>
        <ul className="list-disc list-inside space-y-1 font-mono text-[11px]">
          <li>Scores are 100% deterministic, computed offline with zero external API calls or LLMs.</li>
          <li>Failed runs or submissions with malformed predictions never receive scores or appear on the leaderboard.</li>
          <li>Ground truth labels for Test A, Test B, and Test C remain physically isolated and organizer-hidden.</li>
        </ul>
      </div>
    </div>
  );
};

