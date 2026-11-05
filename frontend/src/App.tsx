import React, { useEffect, useState } from 'react';
import { Navbar } from './components/Navbar';
import { ParticipantPortal } from './pages/ParticipantPortal';
import { ParticipantRegistration } from './pages/ParticipantRegistration';
import { ParticipantStatusTracking } from './pages/ParticipantStatusTracking';
import { Leaderboard } from './pages/Leaderboard';
import { Benchmark } from './pages/Benchmark';
import { OrganizerConsole } from './pages/OrganizerConsole';
import { api } from './services/api';
import { OverviewStats, LeaderboardEntry, BenchmarkSummary, SystemStatus as SystemStatusType } from './types';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('portal');
  const [_stats, setStats] = useState<OverviewStats | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [benchmark, setBenchmark] = useState<BenchmarkSummary | null>(null);
  const [system, setSystem] = useState<SystemStatusType | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const refreshData = async () => {
    setLoading(true);
    try {
      const [overviewData, lbData, bmData, sysData] = await Promise.all([
        api.getOverview().catch(() => null),
        api.getLeaderboard().catch(() => []),
        api.getBenchmark().catch(() => null),
        api.getSystemStatus().catch(() => null),
      ]);
      setStats(overviewData);
      setLeaderboard(lbData);
      setBenchmark(bmData);
      setSystem(sysData);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshData();
  }, []);

  const dockerOnline = Boolean(system?.execution_backends.docker_daemon_available);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        dockerOnline={dockerOnline}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'portal' && (
          <ParticipantPortal
            onNavigateRegister={() => setActiveTab('register')}
            onNavigateTrack={() => setActiveTab('track')}
          />
        )}

        {activeTab === 'register' && (
          <ParticipantRegistration
            onSuccess={() => {
              refreshData();
              setActiveTab('track');
            }}
          />
        )}

        {activeTab === 'track' && <ParticipantStatusTracking />}

        {activeTab === 'leaderboard' && (
          <Leaderboard
            entries={leaderboard}
            loading={loading}
            onRefresh={refreshData}
          />
        )}

        {activeTab === 'benchmark' && (
          <Benchmark benchmark={benchmark} loading={loading} />
        )}

        {activeTab === 'organizer' && <OrganizerConsole />}
      </main>

      <footer className="border-t border-slate-900 bg-slate-950 py-6 text-center text-xs text-slate-500 font-mono">
        HYDRAFORGE Evaluation Platform • BASINSHIFT Challenge 2026 • Deterministic Metric Engine
      </footer>
    </div>
  );
};

export default App;
