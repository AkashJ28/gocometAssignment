import React from 'react';
import { Quote, CheckCircle2, AlertTriangle, HelpCircle, FileCheck, Layers, Eye } from 'lucide-react';

const FIELD_METADATA = [
  { key: 'invoice_number', aliases: ['invoice_num', 'invoice_no'], label: 'Invoice / Doc Number' },
  { key: 'consignee', aliases: ['buyer', 'importer'], label: 'Buyer / Consignee' },
  { key: 'hs_code', aliases: ['tariff_code', 'harmonized_code'], label: 'Harmonized HS Code' },
  { key: 'pol', aliases: ['port_of_loading'], label: 'Port of Loading (POL)' },
  { key: 'pod', aliases: ['port_of_discharge'], label: 'Port of Discharge (POD)' },
  { key: 'incoterm', aliases: ['incoterms'], label: 'Delivery Terms (Incoterm)' },
  { key: 'description', aliases: ['cargo_description', 'merchandise'], label: 'Description of Goods' },
  { key: 'gross_weight', aliases: ['weight'], label: 'Gross Weight' },
];

function getField(extraction, meta) {
  if (!extraction) return null;
  if (extraction[meta.key] !== undefined && extraction[meta.key] !== null) {
    return extraction[meta.key];
  }
  for (const alias of meta.aliases || []) {
    if (extraction[alias] !== undefined && extraction[alias] !== null) {
      return extraction[alias];
    }
  }
  return null;
}

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
    if (conf >= 0.85) {
      return {
        bg: 'bg-emerald-500',
        text: 'text-emerald-400',
        badge: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
      };
    }
    if (conf >= 0.70) {
      return {
        bg: 'bg-amber-500',
        text: 'text-amber-400',
        badge: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
      };
    }
    return {
      bg: 'bg-rose-500',
      text: 'text-rose-400',
      badge: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
    };
  };

  const extractionMethod = extraction.extraction_method || 'text_layer';
  const getMethodBadge = (m) => {
    if (m === 'vision_fallback' || m === 'vision_default') {
      return { label: 'Vision OCR (Rasterized)', color: 'bg-purple-500/10 text-purple-300 border-purple-500/30' };
    }
    return { label: 'Native Text Layer (PyMuPDF)', color: 'bg-sky-500/10 text-sky-300 border-sky-500/30' };
  };

  const methodBadge = getMethodBadge(extractionMethod);

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 overflow-hidden shadow-lg">
      {/* Header */}
      <div className="p-4 border-b border-slate-700/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <FileCheck className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-white">
              Extracted Trade Fields & Source Grounding (UI-02)
            </h3>
            <span className={`text-[10px] px-2 py-0.5 rounded border font-mono font-medium ${methodBadge.color}`}>
              {methodBadge.label}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            All 8 trade fields grounded against document text with confidence calibration
          </p>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-3 text-xs flex-wrap">
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" /> &ge;85% High
          </span>
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" /> 70-84% Medium
          </span>
          <span className="flex items-center gap-1.5 text-slate-400">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" /> &lt;70% Low
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-900/70 text-slate-400 border-b border-slate-700/70 font-semibold uppercase tracking-wider text-[11px]">
              <th className="py-3 px-4 w-44">Field Name</th>
              <th className="py-3 px-4 min-w-[160px]">Extracted Value</th>
              <th className="py-3 px-4 w-36">Confidence</th>
              <th className="py-3 px-4 w-32">Grounding</th>
              <th className="py-3 px-4 min-w-[220px]">Verbatim Source Quote</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/40 text-slate-200">
            {FIELD_METADATA.map((meta) => {
              const rawField = getField(extraction, meta);
              const field = rawField || {
                value: null,
                confidence: 0,
                source_quote: null,
                is_grounded: false,
              };

              const confPercent = Math.round((field.confidence || 0) * 100);
              const confColors = getConfidenceColor(field.confidence || 0);
              const hasValue = field.value !== null && field.value !== undefined && String(field.value).trim() !== '';
              const hasQuote = Boolean(field.source_quote && String(field.source_quote).trim());
              const isGrounded = Boolean(field.is_grounded);

              return (
                <tr key={meta.key} className="hover:bg-slate-700/30 transition-colors">
                  {/* Field Name */}
                  <td className="py-3.5 px-4 font-medium text-slate-300">
                    <span className="block font-semibold">{meta.label}</span>
                    <span className="text-[10px] text-slate-500 font-mono">{meta.key}</span>
                  </td>

                  {/* Extracted Value */}
                  <td className="py-3.5 px-4 font-sans font-medium text-white">
                    {hasValue ? (
                      <span className="inline-block break-words max-w-xs">{String(field.value)}</span>
                    ) : (
                      <span className="text-slate-500 italic font-mono text-[11px]">NOT_FOUND</span>
                    )}
                  </td>

                  {/* Confidence Bar & % */}
                  <td className="py-3.5 px-4">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-slate-700 rounded-full h-1.5 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${confColors.bg}`}
                          style={{ width: `${confPercent}%` }}
                        />
                      </div>
                      <span className={`text-[11px] font-bold font-mono w-9 text-right ${confColors.text}`}>
                        {confPercent}%
                      </span>
                    </div>
                  </td>

                  {/* Grounding Status Badge */}
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    {!hasValue ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-400 border border-slate-700">
                        Absent
                      </span>
                    ) : isGrounded ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="w-3 h-3" />
                        Grounded
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                        <AlertTriangle className="w-3 h-3" />
                        Uncertain
                      </span>
                    )}
                  </td>

                  {/* Source Quote */}
                  <td className="py-3.5 px-4">
                    {hasQuote ? (
                      <div className="flex items-start gap-1.5 p-2 rounded bg-slate-900/80 border border-slate-700/60 text-[11px] text-slate-300">
                        <Quote className="w-3.5 h-3.5 text-sky-400 flex-shrink-0 mt-0.5" />
                        <span className="break-words font-mono select-all">
                          "{field.source_quote}"
                        </span>
                      </div>
                    ) : (
                      <span className="text-slate-500 text-[11px] italic">No verbatim quote</span>
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
