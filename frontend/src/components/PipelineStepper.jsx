import React from 'react';
import { CheckCircle2, Clock, Cpu, AlertTriangle, FileSearch, ShieldCheck, GitFork, Loader2 } from 'lucide-react';

const STAGES = [
  {
    id: 'extractor',
    title: '1. Extractor Agent',
    description: 'Multimodal OCR & Field Grounding',
    icon: FileSearch,
    nodeName: 'extractor',
  },
  {
    id: 'validator',
    title: '2. Validator Agent',
    description: 'Deterministic Rule Evaluation',
    icon: ShieldCheck,
    nodeName: 'validator',
  },
  {
    id: 'router',
    title: '3. Router Agent',
    description: 'Outcome & Response Drafting',
    icon: GitFork,
    nodeName: 'router',
  },
];

export default function PipelineStepper({ bundle, isProcessing }) {
  const runs = bundle?.runs || [];
  const validation = bundle?.validation;
  const decision = bundle?.decision;

  const getStageTelemetry = (nodeName) => {
    return runs.find((r) => r.node_name?.toLowerCase().includes(nodeName));
  };

  const getStageStatus = (stageId) => {
    if (isProcessing) {
      return { state: 'running', text: 'Processing...' };
    }
    if (!bundle) {
      return { state: 'pending', text: 'Idle' };
    }

    if (stageId === 'extractor') {
      if (bundle.extraction) return { state: 'success', text: 'Extracted' };
      return { state: 'pending', text: 'Waiting' };
    }

    if (stageId === 'validator') {
      if (validation) {
        const overall = (validation.overall_status || '').toLowerCase();
        if (overall === 'match') return { state: 'success', text: 'Rules Passed' };
        if (overall === 'mismatch') return { state: 'alert', text: 'Mismatch Flagged' };
        return { state: 'warning', text: 'Uncertain' };
      }
      return { state: 'pending', text: 'Waiting' };
    }

    if (stageId === 'router') {
      if (decision) {
        const dec = (decision.decision || '').toLowerCase();
        if (dec === 'auto_approve') return { state: 'success', text: 'Auto Approved' };
        if (dec === 'amendment_request') return { state: 'alert', text: 'Amendment Drafted' };
        return { state: 'warning', text: 'Human Review' };
      }
      return { state: 'pending', text: 'Waiting' };
    }

    return { state: 'pending', text: 'Pending' };
  };

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 p-5 shadow-lg">
      <div className="flex items-center justify-between mb-4 pb-2 border-b border-slate-700/50">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
          Live Pipeline Execution & Telemetry (UI-01)
        </h3>
        {bundle?.document && (
          <span className="text-xs text-slate-400">
            Doc ID: <code className="text-sky-300 font-mono">{bundle.document.id.slice(0, 8)}...</code>
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative">
        {STAGES.map((stage, idx) => {
          const status = getStageStatus(stage.id);
          const telemetry = getStageTelemetry(stage.nodeName);
          const Icon = stage.icon;

          let badgeColor = 'bg-slate-700 text-slate-300 border-slate-600';
          let iconBg = 'bg-slate-700/60 text-slate-400';
          let borderHighlight = 'border-slate-700/70';

          if (status.state === 'running') {
            badgeColor = 'bg-sky-500/20 text-sky-300 border-sky-500/30';
            iconBg = 'bg-sky-500/20 text-sky-400';
            borderHighlight = 'border-sky-500/50 ring-1 ring-sky-500/30';
          } else if (status.state === 'success') {
            badgeColor = 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30';
            iconBg = 'bg-emerald-500/20 text-emerald-400';
            borderHighlight = 'border-emerald-500/40';
          } else if (status.state === 'alert') {
            badgeColor = 'bg-rose-500/20 text-rose-300 border-rose-500/30';
            iconBg = 'bg-rose-500/20 text-rose-400';
            borderHighlight = 'border-rose-500/40';
          } else if (status.state === 'warning') {
            badgeColor = 'bg-amber-500/20 text-amber-300 border-amber-500/30';
            iconBg = 'bg-amber-500/20 text-amber-400';
            borderHighlight = 'border-amber-500/40';
          }

          return (
            <div
              key={stage.id}
              className={`bg-slate-900/70 rounded-xl p-4 border ${borderHighlight} transition-all relative overflow-hidden`}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2.5">
                  <div className={`p-2 rounded-lg ${iconBg}`}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-slate-200">{stage.title}</h4>
                    <p className="text-xs text-slate-400">{stage.description}</p>
                  </div>
                </div>
              </div>

              {/* Status Badge */}
              <div className="mt-3 flex items-center justify-between pt-2 border-t border-slate-800/80">
                <span className={`text-xs px-2.5 py-0.5 rounded-full font-medium border flex items-center gap-1.5 ${badgeColor}`}>
                  {status.state === 'running' ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : status.state === 'success' ? (
                    <CheckCircle2 className="w-3 h-3" />
                  ) : status.state === 'alert' || status.state === 'warning' ? (
                    <AlertTriangle className="w-3 h-3" />
                  ) : (
                    <Clock className="w-3 h-3" />
                  )}
                  {status.text}
                </span>

                {/* Micro Telemetry */}
                {telemetry ? (
                  <div className="text-[11px] text-slate-400 flex items-center gap-2 font-mono">
                    <span title="Latency">{Math.round(telemetry.latency_ms)}ms</span>
                    <span className="text-slate-600">&bull;</span>
                    <span title="Prompt + Completion tokens">
                      {(telemetry.prompt_tokens || 0) + (telemetry.completion_tokens || 0)} tok
                    </span>
                    <span className="text-slate-600">&bull;</span>
                    <span title="Cost">${(telemetry.cost_usd || 0).toFixed(5)}</span>
                  </div>
                ) : (
                  <span className="text-[11px] text-slate-500 italic">No trace yet</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
