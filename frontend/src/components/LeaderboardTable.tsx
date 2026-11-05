import React from 'react';
import { LeaderboardEntry } from '../types';

interface LeaderboardTableProps {
  entries: LeaderboardEntry[];
  loading: boolean;
}

export const LeaderboardTable: React.FC<LeaderboardTableProps> = ({ entries, loading }) => {
  if (loading) {
    return (
      <div className="p-12 text-center text-slate-400 font-mono">
        Loading official leaderboard standings...
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="p-12 text-center text-slate-400 bg-slate-900 border border-slate-800 rounded-xl">
        <p className="text-base font-semibold text-slate-300">No scored submissions yet</p>
        <p className="text-xs text-slate-500 mt-1">Submit a participant repository to populate the official rankings.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900 shadow">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-950/70 border-b border-slate-800 text-[11px] font-mono uppercase tracking-wider text-slate-400">
          <tr>
            <th className="py-3 px-4">Rank</th>
            <th className="py-3 px-4">Team & Model</th>
            <th className="py-3 px-4 text-right">Total Score</th>
            <th className="py-3 px-3 text-right">Skill (25)</th>
            <th className="py-3 px-3 text-right">Events (25)</th>
            <th className="py-3 px-3 text-right">Gen (20)</th>
            <th className="py-3 px-3 text-right">Calib (15)</th>
            <th className="py-3 px-3 text-right">Rob (10)</th>
            <th className="py-3 px-3 text-right">Eff (5)</th>
            <th className="py-3 px-4 text-right">Commit</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
          {entries.map((entry) => (
            <tr key={entry.job_id} className="hover:bg-slate-800/40 transition-colors">
              <td className="py-3 px-4 font-bold">
                {entry.rank === 1 ? (
                  <span className="text-amber-400">🥇 #1</span>
                ) : entry.rank === 2 ? (
                  <span className="text-slate-300">🥈 #2</span>
                ) : entry.rank === 3 ? (
                  <span className="text-amber-600">🥉 #3</span>
                ) : (
                  <span className="text-slate-400">#{entry.rank}</span>
                )}
              </td>
              <td className="py-3 px-4 font-sans">
                <div className="font-semibold text-white">{entry.team_name}</div>
                <div className="text-xs text-slate-400">{entry.submission_name}</div>
              </td>
              <td className="py-3 px-4 text-right">
                <span className="text-base font-extrabold text-cyan-400">
                  {entry.total_score.toFixed(2)}
                </span>
                <span className="text-[10px] text-slate-500 ml-1">/100</span>
              </td>
              <td className="py-3 px-3 text-right text-slate-300">{entry.forecast_skill.toFixed(2)}</td>
              <td className="py-3 px-3 text-right text-slate-300">{entry.event_detection.toFixed(2)}</td>
              <td className="py-3 px-3 text-right text-slate-300">{entry.generalization.toFixed(2)}</td>
              <td className="py-3 px-3 text-right text-slate-300">{entry.calibration.toFixed(2)}</td>
              <td className="py-3 px-3 text-right text-slate-300">{entry.robustness.toFixed(2)}</td>
              <td className="py-3 px-3 text-right text-slate-300">{entry.efficiency.toFixed(2)}</td>
              <td className="py-3 px-4 text-right text-slate-500 font-mono text-[11px]">
                {entry.commit_sha.slice(0, 8)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

