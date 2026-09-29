import React from 'react';
import { ShieldCheck, Activity, Database, DollarSign, Clock, HelpCircle, Terminal } from 'lucide-react';

export default function Header({
  healthStatus,
  telemetry,
  onOpenQueryDrawer,
  onOpenTelemetryDrawer,
}) {
  const isHealthy = healthStatus === 'healthy';
  const isChecking = healthStatus === 'checking';

  return (
    <header className="bg-slate-900/90 border-b border-slate-800 backdrop-blur sticky top-0 z-30 px-6 py-3.5">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Brand & Outcome Guarantee */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-sky-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-sky-500/20">
            <ShieldCheck className="w-6 h-6 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-lg text-white tracking-tight">GoComet Nova DAW</span>
              <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-sky-500/10 text-sky-400 border border-sky-500/20">
                v1.0 POC
              </span>
            </div>
            <p className="text-xs text-slate-400 flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              Autonomous Trade Document Verification &bull; <strong className="text-slate-300">Zero Silent Approvals</strong>
            </p>
          </div>
        </div>

        {/* Global Telemetry Stats & Controls */}
        <div className="flex items-center gap-3 sm:gap-4 flex-wrap justify-end">
          {/* Health Badge */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60 text-xs">
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                isHealthy
                  ? 'bg-emerald-500 shadow-sm shadow-emerald-500/50 animate-pulse'
                  : isChecking
                  ? 'bg-amber-400 animate-spin'
                  : 'bg-rose-500'
              }`}
            />
            <span className="font-medium text-slate-300">
              {isHealthy ? 'Backend Ready' : isChecking ? 'Connecting...' : 'Offline'}
            </span>
          </div>

          {/* Quick Metrics */}
          {telemetry && (
            <div className="hidden lg:flex items-center gap-3 text-xs bg-slate-800/60 px-3 py-1.5 rounded-lg border border-slate-700/50">
              <div className="flex items-center gap-1 text-slate-300" title="Total pipeline executions">
                <Activity className="w-3.5 h-3.5 text-sky-400" />
                <span>{telemetry.total_runs ?? 0} runs</span>
              </div>
              <span className="text-slate-600">&bull;</span>
              <div className="flex items-center gap-1 text-slate-300" title="Total API cost">
                <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
                <span>${(telemetry.total_cost_usd ?? 0).toFixed(4)}</span>
              </div>
              <span className="text-slate-600">&bull;</span>
              <div className="flex items-center gap-1 text-slate-300" title="Average execution latency">
                <Clock className="w-3.5 h-3.5 text-amber-400" />
                <span>{telemetry.avg_latency_ms ? Math.round(telemetry.avg_latency_ms) : 0}ms avg</span>
              </div>
            </div>
          )}

          {/* NL Query Drawer Button */}
          <button
            onClick={onOpenQueryDrawer}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium transition shadow-sm shadow-sky-600/30"
            title="Ask Natural Language Query (Text-to-SQL)"
          >
            <Database className="w-3.5 h-3.5" />
            <span>NL Query</span>
          </button>

          {/* Telemetry Modal / Drawer Button */}
          <button
            onClick={onOpenTelemetryDrawer}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-xs font-medium transition"
            title="View Pipeline Runs & Observability Telemetry"
          >
            <Terminal className="w-3.5 h-3.5 text-indigo-400" />
            <span>Telemetry</span>
          </button>
        </div>
      </div>
    </header>
  );
}
