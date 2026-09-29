import React, { useState, useEffect } from 'react';
import { X, Terminal, Activity, DollarSign, Clock, Cpu, RefreshCw } from 'lucide-react';
import { getRunsTelemetry } from '../api';

export default function TelemetryDrawer({ isOpen, onClose }) {
  const [telemetry, setTelemetry] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchTelemetry = async () => {
    setLoading(true);
    try {
      const data = await getRunsTelemetry(100, 0);
      setTelemetry(data);
    } catch (err) {
      console.error('Failed to load telemetry:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchTelemetry();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const metrics = telemetry?.metrics || {
    total_runs: 0,
    total_cost_usd: 0,
    total_tokens: 0,
    avg_latency_ms: 0,
  };
  const runs = telemetry?.runs || [];

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-950/60 backdrop-blur-sm flex justify-end">
      <div className="w-full max-w-3xl bg-slate-900 border-l border-slate-800 h-full flex flex-col shadow-2xl animate-in slide-in-from-right duration-300">
        {/* Drawer Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">System Observability & Trace Log (OBS-01)</h2>
              <p className="text-xs text-slate-400">
                Detailed database traces of LLM invocations, token usage, latency, and costs
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchTelemetry}
              disabled={loading}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Refresh Telemetry"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Global Summary Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 bg-slate-950/50 border-b border-slate-800">
          <div className="bg-slate-900/80 p-3 rounded-lg border border-slate-800">
            <span className="text-[11px] text-slate-400 flex items-center gap-1">
              <Activity className="w-3.5 h-3.5 text-sky-400" /> Total Invocations
            </span>
            <div className="text-lg font-bold font-mono text-white mt-1">
              {metrics.total_runs}
            </div>
          </div>
          <div className="bg-slate-900/80 p-3 rounded-lg border border-slate-800">
            <span className="text-[11px] text-slate-400 flex items-center gap-1">
              <DollarSign className="w-3.5 h-3.5 text-emerald-400" /> Total Cost (USD)
            </span>
            <div className="text-lg font-bold font-mono text-emerald-400 mt-1">
              ${Number(metrics.total_cost_usd || 0).toFixed(5)}
            </div>
          </div>
          <div className="bg-slate-900/80 p-3 rounded-lg border border-slate-800">
            <span className="text-[11px] text-slate-400 flex items-center gap-1">
              <Cpu className="w-3.5 h-3.5 text-purple-400" /> Total Tokens
            </span>
            <div className="text-lg font-bold font-mono text-purple-300 mt-1">
              {metrics.total_tokens?.toLocaleString() || 0}
            </div>
          </div>
          <div className="bg-slate-900/80 p-3 rounded-lg border border-slate-800">
            <span className="text-[11px] text-slate-400 flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-amber-400" /> Avg Latency
            </span>
            <div className="text-lg font-bold font-mono text-amber-300 mt-1">
              {Math.round(metrics.avg_latency_ms || 0)}ms
            </div>
          </div>
        </div>

        {/* Runs Table */}
        <div className="flex-1 overflow-auto p-4">
          <div className="border border-slate-800 rounded-lg overflow-hidden bg-slate-950">
            <table className="w-full text-left text-[11px] border-collapse">
              <thead>
                <tr className="bg-slate-900 text-slate-400 border-b border-slate-800 font-semibold sticky top-0">
                  <th className="p-2.5">Node</th>
                  <th className="p-2.5">Model</th>
                  <th className="p-2.5">Latency</th>
                  <th className="p-2.5">Tokens (P/C/T)</th>
                  <th className="p-2.5">Cost</th>
                  <th className="p-2.5">Status</th>
                  <th className="p-2.5">Timestamp</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                {runs.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="p-6 text-center text-slate-500 italic">
                      No run records found in database.
                    </td>
                  </tr>
                ) : (
                  runs.map((r) => (
                    <tr key={r.id} className="hover:bg-slate-900/50">
                      <td className="p-2.5 font-sans font-medium text-slate-200">
                        {r.node_name}
                      </td>
                      <td className="p-2.5 text-slate-400 truncate max-w-[120px]" title={r.model_name}>
                        {r.model_name ? r.model_name.replace('models/', '') : 'N/A'}
                      </td>
                      <td className="p-2.5 text-slate-200">
                        {Math.round(r.latency_ms)}ms
                      </td>
                      <td className="p-2.5 text-slate-400" title={`Prompt: ${r.prompt_tokens}, Completion: ${r.completion_tokens}, Thinking: ${r.thinking_tokens}`}>
                        {r.prompt_tokens}/{r.completion_tokens}/{r.thinking_tokens}
                      </td>
                      <td className="p-2.5 text-emerald-400">
                        ${(r.cost_usd || 0).toFixed(5)}
                      </td>
                      <td className="p-2.5">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-sans ${
                            r.status === 'SUCCESS'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                          }`}
                        >
                          {r.status}
                        </span>
                      </td>
                      <td className="p-2.5 text-slate-500 text-[10px]">
                        {r.created_at ? r.created_at.replace('T', ' ').slice(0, 19) : ''}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
