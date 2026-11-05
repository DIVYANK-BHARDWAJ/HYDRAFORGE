import React from 'react';

interface ParticipantPortalProps {
  onNavigateRegister: () => void;
  onNavigateTrack: () => void;
}

export const ParticipantPortal: React.FC<ParticipantPortalProps> = ({
  onNavigateRegister,
  onNavigateTrack,
}) => {
  return (
    <div className="space-y-10">
      {/* Hero Banner */}
      <div className="rounded-2xl border border-slate-800 bg-gradient-to-r from-slate-900 via-slate-900/90 to-cyan-950/40 p-8 sm:p-12 shadow-xl relative overflow-hidden">
        <div className="relative z-10 max-w-3xl">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-cyan-950/80 border border-cyan-800 text-cyan-300 text-xs font-mono mb-5">
            <span>BASINSHIFT 2026</span>
            <span>•</span>
            <span>Machine Learning for Hydrology</span>
          </div>
          <h1 className="text-3xl sm:text-5xl font-black text-white tracking-tight leading-tight">
            Train anywhere. Predict anywhere.{' '}
            <span className="bg-gradient-to-r from-cyan-400 to-sky-300 bg-clip-text text-transparent">
              Prove your model.
            </span>
          </h1>
          <p className="mt-4 text-slate-300 text-base sm:text-lg leading-relaxed">
            BASINSHIFT is an automated scientific benchmark evaluating river-discharge forecasting models,
            uncertainty calibration, and unseen-catchment generalization under real-world distribution shift.
            Participants may train using any scientifically valid, legally permissible dataset.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <button
              onClick={onNavigateRegister}
              className="px-6 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-sm sm:text-base shadow-lg shadow-cyan-500/25 transition"
            >
              Submit Your Project →
            </button>
            <a
              href="#guidelines-section"
              className="px-6 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-sm sm:text-base border border-slate-700 transition"
            >
              Submission Guidelines
            </a>
            <button
              onClick={onNavigateTrack}
              className="px-6 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 font-semibold text-sm sm:text-base border border-slate-800 transition"
            >
              Track Your Submission
            </button>
          </div>
        </div>
      </div>

      {/* Challenge Overview */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-6 sm:p-8">
        <h2 className="text-xl sm:text-2xl font-bold text-white mb-3">Challenge Overview</h2>
        <p className="text-slate-300 text-sm sm:text-base leading-relaxed mb-4">
          Accurate river-discharge prediction is essential for early flood warning, reservoir management, and climate adaptation.
          Standard hydrological ML models often degrade catastrophically when transferred to ungauged river basins or exposed to extreme meteorological shifts.
        </p>
        <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
          HYDRAFORGE evaluates submitted GitHub repositories containing trained models or forecasting agents against organizer-controlled,
          unseen benchmark catchments and hidden ground-truth labels. The scoring engine evaluates your architecture across six distinct deterministic dimensions.
        </p>
      </div>

      {/* Evaluation Dimensions */}
      <div>
        <h2 className="text-xl sm:text-2xl font-bold text-white mb-2">Evaluation Dimensions</h2>
        <p className="text-xs sm:text-sm text-slate-400 mb-6 font-mono">
          * Weights are provisional until organizer ratification. Composite score is bounded in [0, 100].
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition">
            <div className="flex justify-between items-baseline mb-2">
              <span className="font-bold text-cyan-400 text-base">1. Forecast Skill</span>
              <span className="font-mono text-sm font-bold text-white">25 pts</span>
            </div>
            <p className="text-xs sm:text-sm text-slate-400">
              Continuous discharge accuracy evaluated via Nash-Sutcliffe Efficiency (NSE), MAE, and RMSE against a persistence baseline.
            </p>
          </div>

          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition">
            <div className="flex justify-between items-baseline mb-2">
              <span className="font-bold text-cyan-400 text-base">2. Event Detection</span>
              <span className="font-mono text-sm font-bold text-white">25 pts</span>
            </div>
            <p className="text-xs sm:text-sm text-slate-400">
              Skill in detecting Q95 high-flow and Q99 extreme flood peaks using prevalence-normalized AUPRC, Brier Skill Score, and CSI.
            </p>
          </div>

          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition">
            <div className="flex justify-between items-baseline mb-2">
              <span className="font-bold text-cyan-400 text-base">3. Generalization</span>
              <span className="font-mono text-sm font-bold text-white">20 pts</span>
            </div>
            <p className="text-xs sm:text-sm text-slate-400">
              Performance retention on completely unseen catchments (Test B) with penalties for cross-regional disparity.
            </p>
          </div>

          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition">
            <div className="flex justify-between items-baseline mb-2">
              <span className="font-bold text-cyan-400 text-base">4. Calibration</span>
              <span className="font-mono text-sm font-bold text-white">15 pts</span>
            </div>
            <p className="text-xs sm:text-sm text-slate-400">
              Probabilistic interval validity: 90% prediction interval coverage error, sharpness, CRPS, and PIT histogram uniformity.
            </p>
          </div>

          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition">
            <div className="flex justify-between items-baseline mb-2">
              <span className="font-bold text-cyan-400 text-base">5. Robustness</span>
              <span className="font-mono text-sm font-bold text-white">10 pts</span>
            </div>
            <p className="text-xs sm:text-sm text-slate-400">
              Resilience to paired adversarial corruptions: Gaussian sensor noise, historical data missingness, and sensor bias shifts.
            </p>
          </div>

          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition">
            <div className="flex justify-between items-baseline mb-2">
              <span className="font-bold text-cyan-400 text-base">6. Efficiency</span>
              <span className="font-mono text-sm font-bold text-white">5 pts</span>
            </div>
            <p className="text-xs sm:text-sm text-slate-400">
              Inference computational footprint: latency per sample (&lt;50 ms target) and peak resident container RAM (&lt;4 GB).
            </p>
          </div>
        </div>
      </div>

      {/* Guidelines Section */}
      <div id="guidelines-section" className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 space-y-6">
        <h2 className="text-xl sm:text-2xl font-bold text-white">Submission Requirements & Rules</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="space-y-2">
            <h4 className="font-bold text-cyan-400 text-sm uppercase tracking-wider">Repository & Manifest</h4>
            <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
              Submissions must be hosted on public GitHub or GitLab repositories, anchored to an immutable 40-character commit SHA.
              Must include a compliant <code className="text-slate-200">submission_manifest.json</code>.
            </p>
          </div>

          <div className="space-y-2">
            <h4 className="font-bold text-cyan-400 text-sm uppercase tracking-wider">Open Dataset Policy</h4>
            <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
              Participants may train using any scientifically relevant, legally permissible training dataset.
              All datasets, licenses, sources, and preprocessing steps must be fully disclosed.
            </p>
          </div>

          <div className="space-y-2">
            <h4 className="font-bold text-cyan-400 text-sm uppercase tracking-wider">Challenge Logistics</h4>
            <ul className="text-xs sm:text-sm text-slate-400 space-y-1 font-mono">
              <li>• Submission Deadline: To be announced</li>
              <li>• Awards & Prizes: To be announced</li>
              <li>• Team Size Limits: To be announced</li>
              <li>• Evaluator: HYDRAFORGE v1.0.0</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

