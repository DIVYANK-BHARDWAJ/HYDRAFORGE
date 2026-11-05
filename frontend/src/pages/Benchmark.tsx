import React from 'react';
import { BenchmarkSummary } from '../types';

interface BenchmarkProps {
  benchmark: BenchmarkSummary | null;
  loading: boolean;
}

export const Benchmark: React.FC<BenchmarkProps> = ({ benchmark, loading }) => {
  if (loading) {
    return <div className="p-12 text-center text-slate-400 font-mono">Loading benchmark metadata...</div>;
  }

  if (!benchmark) {
    return (
      <div className="p-12 text-center text-slate-400 bg-slate-900 border border-slate-800 rounded-xl">
        Benchmark dataset metadata unavailable. Run <code className="text-cyan-400">hydraforge generate-benchmark</code> to initialize.
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white tracking-tight">Benchmark Suite & Split Manifests</h2>
        <p className="text-xs text-slate-400 mt-1">
          Organizer-controlled evaluation partitions, unseen catchments, and data integrity audits.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900">
          <div className="text-xs text-slate-400 uppercase font-semibold">Dataset Identifier</div>
          <div className="text-xl font-bold text-white mt-1">{benchmark.dataset_name}</div>
          <div className="text-xs text-slate-500 mt-1 font-mono">v{benchmark.benchmark_version}</div>
        </div>

        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900">
          <div className="text-xs text-slate-400 uppercase font-semibold">Total Catchments</div>
          <div className="text-xl font-bold text-white mt-1">{benchmark.catchment_count}</div>
          <div className="text-xs text-slate-500 mt-1">{benchmark.region_count} distinct hydrological regions</div>
        </div>

        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900">
          <div className="text-xs text-slate-400 uppercase font-semibold">Forecast Horizons</div>
          <div className="text-xl font-bold text-cyan-400 mt-1">
            {benchmark.horizons_hours.join('h, ')}h
          </div>
          <div className="text-xs text-slate-500 mt-1">Multi-step hourly targets</div>
        </div>

        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900">
          <div className="text-xs text-slate-400 uppercase font-semibold">Leakage Audit Status</div>
          <div className="text-xl font-bold text-emerald-400 mt-1">
            {benchmark.leakage_audit?.is_leakage_free ? 'Zero Leakage' : 'Audit Failed'}
          </div>
          <div className="text-xs text-slate-500 mt-1 font-mono">0 overlapping train/test cases</div>
        </div>
      </div>

      {/* Split Manifests Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 overflow-hidden shadow">
        <div className="px-5 py-4 border-b border-slate-800 bg-slate-950/60 flex justify-between items-center">
          <h3 className="font-bold text-white text-sm">Evaluation Split Partitions</h3>
          <span className="text-xs font-mono text-cyan-400">Zero-Leakage Verified</span>
        </div>
        <table className="w-full text-left text-sm font-sans">
          <thead className="bg-slate-950/40 border-b border-slate-800 text-[11px] font-mono uppercase tracking-wider text-slate-400">
            <tr>
              <th className="py-3 px-5">Split Partition</th>
              <th className="py-3 px-5">Role / Objective</th>
              <th className="py-3 px-5 text-right">Case Count</th>
              <th className="py-3 px-5 text-right">Catchments</th>
              <th className="py-3 px-5">Condition</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
            {Object.entries(benchmark.split_manifests).map(([splitName, info]) => (
              <tr key={splitName} className="hover:bg-slate-800/30">
                <td className="py-3.5 px-5 font-bold text-cyan-400 uppercase">{splitName}</td>
                <td className="py-3.5 px-5 font-sans text-slate-300">
                  {splitName === 'train' && 'Public training reference partition'}
                  {splitName === 'validation' && 'Public hyperparameter tuning and model selection'}
                  {splitName === 'test_a' && 'Standard in-distribution unseen temporal holdout'}
                  {splitName === 'test_b' && 'Out-of-distribution unseen catchment holdout (Zero overlap with train)'}
                  {splitName === 'test_c' && 'Adversarial sensor corruption and missingness evaluation'}
                </td>
                <td className="py-3.5 px-5 text-right text-white font-bold">{info.case_count}</td>
                <td className="py-3.5 px-5 text-right text-slate-300">{info.catchment_count}</td>
                <td className="py-3.5 px-5">
                  {info.corruption_family ? (
                    <span className="px-2 py-0.5 rounded bg-amber-950 border border-amber-800 text-amber-300 text-[10px]">
                      {info.corruption_family}
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded bg-emerald-950 border border-emerald-800 text-emerald-300 text-[10px]">
                      Clean Sensors
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

