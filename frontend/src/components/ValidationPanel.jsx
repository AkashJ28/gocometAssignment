import React from 'react';
import { ShieldCheck, CheckCircle2, XCircle, AlertTriangle, Scale, AlertOctagon, HelpCircle } from 'lucide-react';

export default function ValidationPanel({ validation }) {
  if (!validation) {
    return (
      <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 p-8 text-center text-slate-500">
        <Scale className="w-10 h-10 mx-auto mb-2 text-slate-600" />
        <p className="text-sm font-medium">No rule validation results available yet.</p>
        <p className="text-xs text-slate-500 mt-1">Validation rules will execute automatically after extraction.</p>
      </div>
    );
  }

  const overall = (validation.overall_status || 'uncertain').toLowerCase();

  // Normalize rules list from either field_validations dict or rules array
  let rules = [];
  if (Array.isArray(validation.rules)) {
    rules = validation.rules;
  } else if (validation.field_validations && typeof validation.field_validations === 'object') {
    rules = Object.entries(validation.field_validations).map(([key, item]) => ({
      field_name: item.field_name || key,
      status: (item.status || 'uncertain').toLowerCase(),
      expected: item.expected !== undefined ? item.expected : item.expected_value,
      found: item.found !== undefined ? item.found : item.found_value,
      reason: item.reason || item.discrepancy_reason || 'Requirement satisfied',
    }));
  }

  const discrepancies = validation.discrepancies || [];

  const getOverallBadge = () => {
    if (overall === 'match') {
      return {
        bg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
        icon: CheckCircle2,
        label: 'MATCH (All Customer Baseline Rules Passed)',
      };
    }
    if (overall === 'mismatch') {
      return {
        bg: 'bg-rose-500/10 border-rose-500/30 text-rose-400',
        icon: XCircle,
        label: 'MISMATCH (Critical Discrepancies Flagged)',
      };
    }
    return {
      bg: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
      icon: AlertTriangle,
      label: 'UNCERTAIN (Human Review Required)',
    };
  };

  const overallBadge = getOverallBadge();
  const OverallIcon = overallBadge.icon;

  const matchesCount = rules.filter((r) => r.status === 'match').length;
  const mismatchesCount = rules.filter((r) => r.status === 'mismatch').length;
  const uncertainsCount = rules.filter((r) => r.status === 'uncertain').length;

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 overflow-hidden shadow-lg">
      {/* Header & Overall Status */}
      <div className="p-4 border-b border-slate-700/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-800">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-sky-400" />
            Customer Rule Validation Engine (UI-03)
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Rule-based verification against Meridian Robotics trade parameters &bull; Zero silent approvals
          </p>
        </div>

        {/* Big Overall Badge */}
        <div className={`px-3 py-1.5 rounded-lg border font-semibold text-xs flex items-center gap-2 ${overallBadge.bg}`}>
          <OverallIcon className="w-4 h-4 flex-shrink-0" />
          <span>{overallBadge.label}</span>
        </div>
      </div>

      {/* Summary Counts Bar */}
      <div className="grid grid-cols-3 divide-x divide-slate-700/60 bg-slate-900/50 text-center py-2.5 border-b border-slate-700/60 text-xs">
        <div>
          <span className="text-emerald-400 font-bold font-mono text-sm">{matchesCount}</span>
          <span className="text-slate-400 ml-1.5">Rules Matched</span>
        </div>
        <div>
          <span className="text-rose-400 font-bold font-mono text-sm">{mismatchesCount}</span>
          <span className="text-slate-400 ml-1.5">Mismatches</span>
        </div>
        <div>
          <span className="text-amber-400 font-bold font-mono text-sm">{uncertainsCount}</span>
          <span className="text-slate-400 ml-1.5">Uncertain</span>
        </div>
      </div>

      {/* Discrepancies Alert Banner (if any) */}
      {discrepancies.length > 0 && (
        <div className="p-4 bg-rose-500/10 border-b border-rose-500/20 text-rose-300">
          <div className="flex items-center gap-2 font-semibold text-xs mb-2 text-rose-300">
            <AlertOctagon className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <span>{discrepancies.length} Flagged Discrepanc{discrepancies.length === 1 ? 'y' : 'ies'} Requiring Action:</span>
          </div>
          <div className="space-y-2">
            {discrepancies.map((disc, dIdx) => (
              <div key={dIdx} className="bg-slate-900/80 rounded-lg p-2.5 border border-rose-500/30 text-xs">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-semibold text-rose-200 uppercase font-mono text-[11px]">
                    Field: {disc.field_name}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                    {disc.severity || 'CRITICAL'}
                  </span>
                </div>
                <div className="text-slate-300 text-[11px] leading-relaxed">
                  {disc.reason}
                </div>
                <div className="mt-1.5 flex flex-wrap gap-4 text-[10px] font-mono text-slate-400 pt-1 border-t border-slate-800">
                  <span>Found: <strong className="text-rose-300">{disc.found ?? 'None'}</strong></span>
                  <span>Expected: <strong className="text-emerald-300">{disc.expected ?? 'N/A'}</strong></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Full Field Rules Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-900/70 text-slate-400 border-b border-slate-700/70 font-semibold uppercase tracking-wider text-[11px]">
              <th className="py-3 px-4 w-40">Field / Parameter</th>
              <th className="py-3 px-4 w-28">Status</th>
              <th className="py-3 px-4 min-w-[150px]">Found in Document</th>
              <th className="py-3 px-4 min-w-[180px]">Customer Baseline Requirement</th>
              <th className="py-3 px-4 min-w-[220px]">Rule Verification Rationale</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/40 text-slate-200">
            {rules.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-6 text-center text-slate-500 italic">
                  No individual rule validations recorded for this document.
                </td>
              </tr>
            ) : (
              rules.map((rule, idx) => {
                const status = (rule.status || 'uncertain').toLowerCase();
                let statusBadge = 'bg-slate-700 text-slate-300 border-slate-600';
                if (status === 'match') {
                  statusBadge = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
                } else if (status === 'mismatch') {
                  statusBadge = 'bg-rose-500/10 text-rose-400 border-rose-500/20 font-bold';
                } else if (status === 'uncertain') {
                  statusBadge = 'bg-amber-500/10 text-amber-400 border-amber-500/20';
                }

                return (
                  <tr
                    key={idx}
                    className={`hover:bg-slate-700/30 transition-colors ${
                      status === 'mismatch' ? 'bg-rose-950/15' : ''
                    }`}
                  >
                    {/* Field Name */}
                    <td className="py-3.5 px-4 font-medium text-slate-300">
                      <span className="font-semibold block">{rule.field_name}</span>
                    </td>

                    {/* Status Badge */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-sans border uppercase font-medium ${statusBadge}`}>
                        {status}
                      </span>
                    </td>

                    {/* Found Value */}
                    <td className="py-3.5 px-4 text-slate-100 font-sans">
                      {rule.found !== null && rule.found !== undefined && String(rule.found).trim() !== '' ? (
                        <span className="break-words font-medium">{String(rule.found)}</span>
                      ) : (
                        <span className="text-slate-500 italic font-mono text-[11px]">NOT_FOUND</span>
                      )}
                    </td>

                    {/* Expected Value */}
                    <td className="py-3.5 px-4 text-sky-300 font-sans">
                      {rule.expected !== null && rule.expected !== undefined && String(rule.expected).trim() !== '' ? (
                        <span className="break-words">{String(rule.expected)}</span>
                      ) : (
                        <span className="text-slate-500 italic font-mono text-[11px]">N/A</span>
                      )}
                    </td>

                    {/* Reason / Analysis */}
                    <td className="py-3.5 px-4 text-[11px] text-slate-300 font-sans leading-relaxed">
                      <span className={status === 'mismatch' ? 'text-rose-300 font-medium' : 'text-slate-300'}>
                        {rule.reason}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
