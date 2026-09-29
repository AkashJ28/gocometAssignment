import React from 'react';
import { Quote, CheckCircle, AlertTriangle, HelpCircle, FileCheck, Layers } from 'lucide-react';

const FIELD_METADATA = [
  { key: 'invoice_number', label: 'Invoice / Doc Number' },
  { key: 'consignee', label: 'Consignee' },
  { key: 'hs_code', label: 'HS Code' },
  { key: 'port_of_loading', label: 'Port of Loading (POL)' },
  { key: 'port_of_discharge', label: 'Port of Discharge (POD)' },
  { key: 'incoterms', label: 'Incoterms' },
  { key: 'cargo_description', label: 'Cargo Description' },
  { key: 'gross_weight', label: 'Gross Weight' },
];

export default function ExtractedFieldsTable({ extraction }) {
  if (!extraction) {
    return (
      <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 p-8 text-center text-slate-500">
        <Layers className="w-10 h-10 mx-auto mb-2 text-slate-600" />
        <p className="text-sm font-medium">No document extraction available yet.</p>
        <p className="text-xs text-slate-500 mt-1">Upload a document to view extracted trade fields.</p>
      </div>
    );
  }

  const getConfidenceColor = (conf) => {
    if (conf >= 0.85) return { bg: 'bg-emerald-500', text: 'text-emerald-400', badge: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' };
    if (conf >= 0.70) return { bg: 'bg-amber-500', text: 'text-amber-400', badge: 'bg-amber-500/10 text-amber-400 border-amber-500/20' };
    return { bg: 'bg-rose-500', text: 'text-rose-400', badge: 'bg-rose-500/10 text-rose-400 border-rose-500/20' };
  };

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 overflow-hidden shadow-lg">
      <div className="p-4 border-b border-slate-700/80 flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-slate-800">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <FileCheck className="w-4 h-4 text-emerald-400" />
            Extracted Trade Fields & Source Grounding (UI-02)
          </h3>
          <p className="text-xs text-slate-400">
            All 8 key fields with per-field confidence gauges and verbatim text quotes
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" /> &ge; 85% High
          </span>
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" /> 70-84% Medium
          </span>
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" /> &lt; 70% Low
          </span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-900/60 text-slate-400 border-b border-slate-700/60 font-semibold uppercase tracking-wider">
              <th className="py-3 px-4">Field Name</th>
              <th className="py-3 px-4">Extracted Value</th>
              <th className="py-3 px-4">Confidence</th>
              <th className="py-3 px-4">Grounding Status</th>
              <th className="py-3 px-4">Verbatim Source Quote</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/40 font-mono">
            {FIELD_METADATA.map(({ key, label }) => {
              const field = extraction[key] || {
                value: null,
                confidence: 0,
                source_quote: null,
                is_fallback: false,
              };

              const confPercent = Math.round((field.confidence || 0) * 100);
              const confColors = getConfidenceColor(field.confidence || 0);
              const isFallback = field.is_fallback;
              const hasQuote = Boolean(field.source_quote);

              return (
                <tr key={key} className="hover:bg-slate-700/30 transition-colors">
                  {/* Field Name */}
                  <td className="py-3.5 px-4 font-sans font-medium text-slate-300 whitespace-nowrap">
                    {label}
                  </td>

                  {/* Extracted Value */}
                  <td className="py-3.5 px-4 font-sans font-semibold text-slate-100">
                    {field.value !== null && field.value !== undefined ? (
                      String(field.value)
                    ) : (
                      <span className="text-slate-500 italic font-mono text-[11px]">NOT_FOUND</span>
                    )}
                  </td>

                  {/* Confidence Bar & Percentage */}
                  <td className="py-3.5 px-4 min-w-[140px]">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-slate-700 rounded-full h-1.5 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${confColors.bg}`}
                          style={{ width: `${confPercent}%` }}
                        />
                      </div>
                      <span className={`text-[11px] font-bold w-9 text-right ${confColors.text}`}>
                        {confPercent}%
                      </span>
                    </div>
                  </td>

                  {/* Grounding Status Badge */}
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    {isFallback ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-sans font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
                        <AlertTriangle className="w-3 h-3" />
                        Fallback
                      </span>
                    ) : field.confidence >= 0.70 && hasQuote ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-sans font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <CheckCircle className="w-3 h-3" />
                        Verified
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-sans font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                        <HelpCircle className="w-3 h-3" />
                        Uncertain
                      </span>
                    )}
                  </td>

                  {/* Verbatim Source Quote */}
                  <td className="py-3.5 px-4 min-w-[240px]">
                    {hasQuote ? (
                      <div className="flex items-start gap-1.5 p-2 rounded bg-slate-900/80 border border-slate-700/60 text-[11px] text-slate-300">
                        <Quote className="w-3.5 h-3.5 text-sky-400 flex-shrink-0 mt-0.5" />
                        <span className="break-words font-mono select-all">
                          "{field.source_quote}"
                        </span>
                      </div>
                    ) : (
                      <span className="text-slate-500 text-[11px] italic">No direct quote located</span>
                    )}
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
