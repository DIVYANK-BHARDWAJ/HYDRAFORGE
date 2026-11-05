import React from 'react';

interface StatCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: string;
  badge?: string;
  badgeColor?: 'emerald' | 'cyan' | 'amber' | 'slate';
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  subtext,
  icon,
  badge,
  badgeColor = 'cyan',
}) => {
  const badgeClasses = {
    emerald: 'bg-emerald-950 text-emerald-400 border-emerald-800',
    cyan: 'bg-cyan-950 text-cyan-400 border-cyan-800',
    amber: 'bg-amber-950 text-amber-400 border-amber-800',
    slate: 'bg-slate-800 text-slate-300 border-slate-700',
  }[badgeColor];

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm hover:border-slate-700 transition">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</span>
        <div className="flex items-center space-x-1.5">
          {icon && <span className="text-xs text-slate-400">{icon}</span>}
          {badge && (
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${badgeClasses}`}>
              {badge}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-baseline space-x-2">
        <span className="text-3xl font-extrabold text-white tracking-tight">{value}</span>
      </div>
      {subtext && <p className="mt-1 text-xs text-slate-400">{subtext}</p>}
    </div>
  );
};

