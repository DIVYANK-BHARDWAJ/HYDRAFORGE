import React from 'react';

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  dockerOnline: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({ activeTab, setActiveTab, dockerOnline }) => {
  const tabs = [
    { id: 'portal', label: 'Challenge Portal' },
    { id: 'register', label: 'Register & Submit' },
    { id: 'track', label: 'Track Submission' },
    { id: 'leaderboard', label: 'Leaderboard' },
    { id: 'benchmark', label: 'Benchmark Partitions' },
    { id: 'organizer', label: 'Organizer Console 🔒', isOrganizer: true },
  ];

  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3 cursor-pointer" onClick={() => setActiveTab('portal')}>
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center font-black text-xl shadow-lg shadow-cyan-500/20">
            H
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-cyan-400 via-sky-300 to-blue-400 bg-clip-text text-transparent">
                HYDRAFORGE
              </span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-cyan-950 border border-cyan-800 text-cyan-300">
                v1.0.0
              </span>
            </div>
            <p className="text-xs text-slate-400">BASINSHIFT Hydrological Challenge</p>
          </div>
        </div>

        <nav className="flex space-x-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-slate-800 text-cyan-400 border border-slate-700'
                  : tab.isOrganizer
                  ? 'text-sky-300 border border-slate-800 hover:bg-slate-800/60'
                  : 'text-slate-300 hover:bg-slate-800/50 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2 px-2.5 py-1 rounded-full border border-slate-800 bg-slate-950 text-xs font-mono">
            <span
              className={`w-2 h-2 rounded-full ${
                dockerOnline ? 'bg-emerald-400 shadow-emerald-400/50 shadow-sm animate-pulse' : 'bg-amber-400'
              }`}
            />
            <span className="text-slate-300">{dockerOnline ? 'Docker Online' : 'Docker Offline (Fail-Closed)'}</span>
          </div>
        </div>
      </div>
    </header>
  );
};

