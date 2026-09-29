import React from 'react';
import { CheckCircle2, Clock, AlertTriangle, XCircle, FileSearch, ShieldCheck, GitFork, Loader2 } from 'lucide-react';

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
    description: 'Autonomous Routing & Reasoning',
    icon: GitFork,
    nodeName: 'router',
  },
];

export default function PipelineStepper({ bundle, isProcessing }) {
  const runs = bundle?.runs || [];
  const validation = bundle?.validation;
  const decision = bundle?.decision;
  const document = bundle?.document;

  const getStageTelemetry = (nodeName) => {
    return runs.find((r) => r.node_name?.toLowerCase().includes(nodeName));
  };

  const getStageStatus = (stageId) => {
    const telem = getStageTelemetry(stageId);

    if (isProcessing) {
      return { state: 'running', text: 'Executing...' };
    }
    if (!bundle) {
      return { state: 'pending', text: 'Idle' };
    }

    if (telem && telem.status === 'FAILED') {
      return { state: 'failed', text: 'Execution Failed', error: telem.error_message };
    }

    if (stageId === 'extractor') {
      if (bundle.extraction) return { state: 'success', text: 'Fields Extracted' };
      return { state: 'pending', text: 'Waiting' };
    }

    if (stageId === 'validator') {
      if (validation) {
        const overall = (validation.overall_status || '').toLowerCase();
        if (overall === 'match') return { state: 'success', text: 'Rules Passed' };
        if (overall === 'mismatch') return { state: 'alert', text: 'Discrepancy Flagged' };
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
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4 pb-2 border-b border-slate-700/60">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Multi-Agent Execution Pipeline (UI-01)
          </h3>
          <p className="text-[11px] text-slate-500">
            LangGraph StateGraph workflow with persistent checkpoints and per-node telemetry
          </p>
        </div>
        {document && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400">Doc:</span>
            <span className="text-sky-300 font-mono font-medium truncate max-w-[200px]" title={document.filename}>
              {document.filename}
            </span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative">
        {STAGES.map((stage) => {
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
          } else if (status.state === 'failed') {
            badgeColor = 'bg-rose-500/20 text-rose-300 border-rose-500/30';
            iconBg = 'bg-rose-500/20 text-rose-400';
            borderHighlight = 'border-rose-500/50';
          } else if (status.state === 'alert') {
            badgeColor = 'bg-purple-500/20 text-purple-300 border-purple-500/30';
            iconBg = 'bg-purple-500/20 text-purple-400';
            borderHighlight = 'border-purple-500/40';
          } else if (status.state === 'warning') {
            badgeColor = 'bg-amber-500/20 text-amber-300 border-amber-500/30';
            iconBg = 'bg-amber-500/20 text-amber-400';
            borderHighlight = 'border-amber-500/40';
          }

          return (
            <div
              key={stage.id}
              className={`bg-slate-900/70 rounded-xl p-4 border ${borderHighlight} transition-all relative overflow-hidden flex flex-col justify-between`}
            >
              <div>
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
              </div>

              {/* Status Badge & Telemetry Footer */}
              <div className="mt-3 pt-2.5 border-t border-slate-800/80 space-y-2">
                <div className="flex items-center justify-between">
                  <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium border flex items-center gap-1.5 ${badgeColor}`}>
                    {status.state === 'running' ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : status.state === 'success' ? (
                      <CheckCircle2 className="w-3 h-3" />
                    ) : status.state === 'failed' ? (
                      <XCircle className="w-3 h-3 text-rose-400" />
                    ) : status.state === 'alert' || status.state === 'warning' ? (
                      <AlertTriangle className="w-3 h-3" />
                    ) : (
                      <Clock className="w-3 h-3" />
                    )}
                    {status.text}
                  </span>

                  {telemetry && (
                    <span className="text-[10px] text-slate-400 font-mono">
                      {Math.round(telemetry.latency_ms)}ms
                    </span>
                  )}
                </div>

                {/* Telemetry Micro Detail */}
                {telemetry ? (
                  <div className="text-[10px] text-slate-400 flex items-center justify-between font-mono bg-slate-950/60 px-2 py-1 rounded border border-slate-800">
                    <span className="truncate max-w-[110px]" title={telemetry.model_name}>
                      {telemetry.model_name ? telemetry.model_name.replace('models/', '') : 'rules_engine'}
                    </span>
                    <span title="Tokens">
                      {(telemetry.prompt_tokens || 0) + (telemetry.completion_tokens || 0)} tok
                    </span>
                    <span className="text-emerald-400 font-medium" title="Cost USD">
                      ${(telemetry.cost_usd || 0).toFixed(5)}
                    </span>
                  </div>
                ) : (
                  <div className="text-[10px] text-slate-500 italic px-1">
                    Node awaiting execution
                  </div>
                )}

                {/* Node Error Message if failed */}
                {status.error && (
                  <div className="text-[10px] text-rose-300 font-mono bg-rose-950/30 p-1.5 rounded border border-rose-500/30 leading-tight">
                    {status.error}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
