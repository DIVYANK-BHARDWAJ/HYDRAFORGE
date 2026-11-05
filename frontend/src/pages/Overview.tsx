import React from 'react';
import { OverviewStats, LeaderboardEntry } from '../types';
import { StatCard } from '../components/StatCard';
import { LeaderboardTable } from '../components/LeaderboardTable';

interface OverviewProps {
  stats: OverviewStats | null;
  leaderboard: LeaderboardEntry[];
  loading: boolean;
  onNavigateSubmit: () => void;
}

export const Overview: React.FC<OverviewProps> = ({
  stats,
  leaderboard,
  loading,
  onNavigateSubmit,
}) => {
  return (
    <div className="space-y-8">
      {/* Hero Banner */}
      <div className="rounded-2xl border border-slate-800 bg-gradient-to-r from-slate-900 via-slate-900/90 to-cyan-950/40 p-8 shadow-xl relative overflow-hidden">
        <div className="relative z-10 max-w-3xl">
          <div className="inline-flex items-center space-x-2 px-2.5 py-1 rounded-full bg-cyan-950/80 border border-cyan-800 text-cyan-300 text-xs font-mono mb-4">
            <span>BASINSHIFT Hydrological Challenge</span>
            <span>•</span>
            <span>Deterministic 6-Axis Evaluation</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
            Train anywhere. Predict anywhere.{' '}
            <span className="bg-gradient-to-r from-cyan-400 to-sky-300 bg-clip-text text-transparent">
              Prove your model.
            </span>
          </h1>
          <p className="mt-3 text-slate-300 text-sm sm:text-base leading-relaxed">
            Automated, reproducible evaluation of hydrological machine-learning submissions against
            unseen catchments, extreme high-flow events, distribution shifts, and adversarial corruptions.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              onClick={onNavigateSubmit}
              className="px-5 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-sm shadow-lg shadow-cyan-500/25 transition"
            >
              Evaluate Submission
            </button>
            <a
              href="#scoring-breakdown"
              className="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-sm border border-slate-700 transition"
            >
              Scoring Dimensions
            </a>
          </div>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Evaluations"
          value={stats?.total_evaluation_jobs ?? 0}
          subtext="Executed evaluation runs"
          badge="Live"
          badgeColor="cyan"
        />
        <StatCard
          label="Ranked Models"
          value={stats?.leaderboard_size ?? 0}
          subtext="Valid completed entries"
          badge="Official"
          badgeColor="emerald"
        />
        <StatCard
          label="Average Score"
          value={stats?.average_score !== null && stats?.average_score !== undefined ? `${stats.average_score.toFixed(1)} / 100` : '—'}
          subtext="Across all validated submissions"
          badge="Normalized"
          badgeColor="amber"
        />
        <StatCard
          label="Execution Boundary"
          value={stats?.execution_backend_status?.docker_daemon_online ? 'Docker Ready' : 'Fail-Closed'}
          subtext={
            stats?.execution_backend_status?.docker_daemon_online
              ? 'Untrusted execution isolated'
              : 'Untrusted submissions blocked'
          }
          badge={stats?.execution_backend_status?.docker_daemon_online ? 'Secured' : 'Locked'}
          badgeColor={stats?.execution_backend_status?.docker_daemon_online ? 'emerald' : 'amber'}
        />
      </div>

      {/* Leaderboard Preview */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">Official Leaderboard Standings</h2>
            <p className="text-xs text-slate-400">Current top-performing hydrological ML architectures</p>
          </div>
        </div>
        <LeaderboardTable entries={leaderboard} loading={loading} />
      </div>

      {/* 6 Dimensions Breakdown */}
      <div id="scoring-breakdown" className="rounded-xl border border-slate-800 bg-slate-900/60 p-6">
        <h3 className="text-lg font-bold text-white mb-4">BASINSHIFT 6-Dimensional Evaluation Contract</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800">
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-cyan-400 text-sm">1. Forecast Skill</span>
              <span className="font-mono text-xs font-bold text-slate-300">25 pts</span>
            </div>
            <p className="text-xs text-slate-400">Persistence-relative Nash-Sutcliffe Efficiency (NSE) and baseline superiority.</p>
          </div>

          <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800">
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-cyan-400 text-sm">2. Event Detection</span>
              <span className="font-mono text-xs font-bold text-slate-300">25 pts</span>
            </div>
            <p className="text-xs text-slate-400">Prevalence-normalized AUPRC, Brier Skill, and Critical Success Index for Q95 and Q99 floods.</p>
          </div>

          <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800">
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-cyan-400 text-sm">3. Generalization</span>
              <span className="font-mono text-xs font-bold text-slate-300">20 pts</span>
            </div>
            <p className="text-xs text-slate-400">Performance retention on unseen catchments (Test B) and regional disparity penalties.</p>
          </div>

          <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800">
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-cyan-400 text-sm">4. Calibration</span>
              <span className="font-mono text-xs font-bold text-slate-300">15 pts</span>
            </div>
            <p className="text-xs text-slate-400">Continuous Ranked Probability Score (CRPS), 90% prediction interval coverage error, and PIT uniformity.</p>
          </div>

          <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800">
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-cyan-400 text-sm">5. Robustness</span>
              <span className="font-mono text-xs font-bold text-slate-300">10 pts</span>
            </div>
            <p className="text-xs text-slate-400">Resistance to paired input corruption: sensor Gaussian noise, missingness, and bias shifts.</p>
          </div>

          <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800">
            <div className="flex justify-between items-center mb-1">
              <span className="font-semibold text-cyan-400 text-sm">6. Efficiency</span>
              <span className="font-mono text-xs font-bold text-slate-300">5 pts</span>
            </div>
            <p className="text-xs text-slate-400">Inference latency per sample (&lt;50ms target) and peak resident container RAM footprint (&lt;4GB).</p>
          </div>
        </div>
      </div>
    </div>
  );
};

