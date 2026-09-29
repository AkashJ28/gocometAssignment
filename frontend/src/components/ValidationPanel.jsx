import React from 'react';
import { ShieldCheck, CheckCircle2, XCircle, AlertTriangle, Scale, ArrowRight } from 'lucide-react';

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
  const rules = validation.rules || [];

  const getOverallBadge = () => {
    if (overall === 'match') {
      return {
        bg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
        icon: CheckCircle2,
        label: 'MATCH (All Customer Rules Passed)',
      };
    }
    if (overall === 'mismatch') {
      return {
        bg: 'bg-rose-500/10 border-rose-500/30 text-rose-400',
        icon: XCircle,
        label: 'MISMATCH (Discrepancies Flagged)',
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

  const mismatchesCount = rules.filter((r) => (r.status || '').toLowerCase() === 'mismatch').length;
  const matchesCount = rules.filter((r) => (r.status || '').toLowerCase() === 'match').length;
  const uncertainsCount = rules.filter((r) => (r.status || '').toLowerCase() === 'uncertain').length;

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 overflow-hidden shadow-lg">
      {/* Header & Overall Status */}
      <div className="p-4 border-b border-slate-700/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-800">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-sky-400" />
            Customer Rule Validation Engine (UI-03)
          </h3>
          <p className="text-xs text-slate-400">
            Automated verification against expected consignee, ports, and trade parameters
          </p>
        </div>

        {/* Big Overall Badge */}
        <div className={`px-3 py-1.5 rounded-lg border font-semibold text-xs flex items-center gap-2 ${overallBadge.bg}`}>
          <OverallIcon className="w-4 h-4" />
          <span>{overallBadge.label}</span>
        </div>
      </div>

      {/* Summary Counts */}
      <div className="grid grid-cols-3 divide-x divide-slate-700/60 bg-slate-900/40 text-center py-2 border-b border-slate-700/60 text-xs">
        <div>
          <span className="text-emerald-400 font-bold font-mono">{matchesCount}</span>
          <span className="text-slate-400 ml-1.5">Rules Matched</span>
        </div>
        <div>
          <span className="text-rose-400 font-bold font-mono">{mismatchesCount}</span>
          <span className="text-slate-400 ml-1.5">Mismatches</span>
        </div>
        <div>
          <span className="text-amber-400 font-bold font-mono">{uncertainsCount}</span>
          <span className="text-slate-400 ml-1.5">Uncertain / Low Conf</span>
        </div>
      </div>

      {/* Rules Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-900/60 text-slate-400 border-b border-slate-700/60 font-semibold uppercase tracking-wider">
              <th className="py-3 px-4">Rule / Field</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Found Extracted Value</th>
              <th className="py-3 px-4">Expected Requirement</th>
              <th className="py-3 px-4">Discrepancy Analysis / Fuzzy Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/40 font-mono">
            {rules.map((rule, idx) => {
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
                    status === 'mismatch' ? 'bg-rose-950/10' : ''
                  }`}
                >
                  <td className="py-3 px-4 font-sans font-medium text-slate-200">
                    <div>{rule.rule_name || rule.field_name}</div>
                    <span className="text-[10px] text-slate-400 font-mono">Field: {rule.field_name}</span>
                  </td>

                  <td className="py-3 px-4 whitespace-nowrap">
                    <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-sans border uppercase ${statusBadge}`}>
                      {status}
                    </span>
                  </td>

                  <td className="py-3 px-4 text-slate-200">
                    {rule.found_value !== null && rule.found_value !== undefined ? (
                      <span className="font-sans font-medium">{String(rule.found_value)}</span>
                    ) : (
                      <span className="text-slate-500 italic">None</span>
                    )}
                  </td>

                  <td className="py-3 px-4 text-slate-300">
                    {rule.expected_value !== null && rule.expected_value !== undefined ? (
                      <span className="font-sans text-sky-300">{String(rule.expected_value)}</span>
                    ) : (
                      <span className="text-slate-500 italic">N/A</span>
                    )}
                  </td>

                  <td className="py-3 px-4 text-slate-300 font-sans text-[11px] min-w-[200px]">
                    <div className="flex flex-col gap-1">
                      {rule.discrepancy_reason ? (
                        <span className={status === 'mismatch' ? 'text-rose-300 font-medium' : 'text-slate-300'}>
                          {rule.discrepancy_reason}
                        </span>
                      ) : (
                        <span className="text-emerald-400/80">Requirement satisfied</span>
                      )}
                      {rule.fuzzy_match_score !== undefined && rule.fuzzy_match_score !== null && (
                        <span className="text-[10px] font-mono text-slate-400">
                          Similarity score: {(rule.fuzzy_match_score * 100).toFixed(1)}%
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
