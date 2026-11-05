import React from 'react';
import { SystemStatus as SystemStatusType } from '../types';

interface SystemStatusProps {
  system: SystemStatusType | null;
  loading: boolean;
  onRefresh: () => void;
}

export const SystemStatus: React.FC<SystemStatusProps> = ({ system, loading, onRefresh }) => {
  if (loading) {
    return <div className="p-12 text-center text-slate-400 font-mono">Loading system diagnostic telemetry...</div>;
  }

  if (!system) {
    return <div className="p-12 text-center text-slate-400">System status unavailable.</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">System Telemetry & Security Diagnostics</h2>
          <p className="text-xs text-slate-400 mt-1">Host health, container execution readiness, and security enforcement status.</p>
        </div>
        <button
          onClick={onRefresh}
          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition"
        >
          Refresh Status
        </button>
      </div>

      {system.security_warnings.length > 0 && (
        <div className="p-4 rounded-xl border border-amber-800/80 bg-amber-950/40 text-amber-200 space-y-1">
          <div className="font-bold text-xs uppercase tracking-wider text-amber-300">Security & Isolation Alerts:</div>
          {system.security_warnings.map((warn, i) => (
            <div key={i} className="text-xs font-mono">{warn}</div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Isolation and Runners */}
        <div className="p-6 rounded-xl border border-slate-800 bg-slate-900 space-y-4">
          <h3 className="font-bold text-white text-sm uppercase tracking-wider text-slate-400">Execution Backends</h3>
          <div className="space-y-3 font-mono text-xs">
            <div className="flex justify-between items-center py-2 border-b border-slate-800">
              <span className="text-slate-300">Docker Daemon</span>
              <span className={system.execution_backends.docker_daemon_available ? 'text-emerald-400 font-bold' : 'text-amber-400 font-bold'}>
                {system.execution_backends.docker_daemon_available ? 'ONLINE' : 'OFFLINE'}
              </span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-slate-800">
              <span className="text-slate-300">Untrusted Execution Isolation</span>
              <span className={system.execution_backends.untrusted_execution_ready ? 'text-emerald-400' : 'text-amber-400 font-bold'}>
                {system.execution_backends.untrusted_execution_ready ? 'READY (Containerized)' : 'FAIL-CLOSED (Locked)'}
              </span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-slate-800">
              <span className="text-slate-300">Local Trusted Runner</span>
              <span className="text-emerald-400 font-bold">READY (Test Fixtures Only)</span>
            </div>
            <div className="flex justify-between items-center py-2">
              <span className="text-slate-300">Network Policy</span>
              <span className="text-cyan-400 font-bold">--network none (Airgapped)</span>
            </div>
          </div>
        </div>

        {/* Hardware & Runtime */}
        <div className="p-6 rounded-xl border border-slate-800 bg-slate-900 space-y-4">
          <h3 className="font-bold text-white text-sm uppercase tracking-wider text-slate-400">Host Hardware Telemetry</h3>
          <div className="space-y-3 font-mono text-xs">
            <div className="flex justify-between items-center py-2 border-b border-slate-800">
              <span className="text-slate-300">Logical CPU Cores</span>
              <span className="text-white font-bold">{system.hardware_telemetry.cpu_cores_logical} cores</span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-slate-800">
              <span className="text-slate-300">Total Host Memory</span>
              <span className="text-white font-bold">{system.hardware_telemetry.total_memory_mb} MB</span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-slate-800">
              <span className="text-slate-300">Available Host Memory</span>
              <span className="text-white font-bold">{system.hardware_telemetry.available_memory_mb} MB</span>
            </div>
            <div className="flex justify-between items-center py-2">
              <span className="text-slate-300">Memory Usage</span>
              <span className="text-cyan-400 font-bold">{system.hardware_telemetry.memory_usage_percent}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

