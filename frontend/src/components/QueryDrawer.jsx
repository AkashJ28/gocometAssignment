import React, { useState } from 'react';
import { X, Send, Database, Clock, Sparkles, AlertCircle, Code2, Table as TableIcon, HelpCircle, CheckCircle2 } from 'lucide-react';
import { executeNlQuery } from '../api';

const SAMPLE_QUERIES = [
  'Show all approved documents',
  'How many documents had incoterm FOB?',
  'List all consignees and their invoice numbers',
  'Which documents have gross weight greater than 10000 kg?',
  'Show total LLM token cost across all runs',
];

export default function QueryDrawer({ isOpen, onClose }) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleExecute = async (queryString) => {
    const q = queryString || query;
    if (!q.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const data = await executeNlQuery(q);
      setResult(data);
    } catch (err) {
      setError(err.message || 'Failed to execute query');
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const handleChipClick = (q) => {
    setQuery(q);
    handleExecute(q);
  };

  // Determine answer, SQL, and tabular data format
  const groundedAnswer = result?.grounded_answer || result?.answer;
  const sqlQuery = result?.sql_query || result?.generated_sql;
  
  const columns = result?.columns || (result?.data && result.data.length > 0 ? Object.keys(result.data[0]) : []);
  const rows = result?.rows || (result?.data ? result.data.map((item) => Object.values(item)) : []);
  const rowCount = result?.row_count ?? rows.length;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-slate-950/70 backdrop-blur-sm flex justify-end">
      <div className="w-full max-w-3xl bg-slate-900 border-l border-slate-800 h-full flex flex-col shadow-2xl animate-in slide-in-from-right duration-300">
        {/* Drawer Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/95 sticky top-0 z-10">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                Natural Language Query Console (STOR-02 / STOR-03)
              </h2>
              <p className="text-xs text-slate-400">
                Text-to-SQL engine with read-only AST safety validation on PostgreSQL
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Query Input Box */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-sky-400" />
              Ask a question about trade documents, extractions, validations, or costs:
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleExecute()}
                placeholder="e.g. Show all approved documents or What was the highest gross weight?"
                className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500 font-sans"
              />
              <button
                type="button"
                onClick={() => handleExecute()}
                disabled={loading || !query.trim()}
                className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition shadow-sm"
              >
                {loading ? (
                  <span className="inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Run Query</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Sample Query Chips */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-semibold text-slate-400">Sample Questions:</span>
            <div className="flex flex-wrap gap-1.5">
              {SAMPLE_QUERIES.map((sq, idx) => (
                <button
                  key={idx}
                  onClick={() => handleChipClick(sq)}
                  disabled={loading}
                  className="text-[11px] px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-sky-300 border border-slate-700/60 transition text-left"
                >
                  {sq}
                </button>
              ))}
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5 text-rose-400" />
              <div className="space-y-1">
                <strong>Query Execution Error:</strong>
                <p className="text-rose-200/90 font-mono text-[11px]">{error}</p>
              </div>
            </div>
          )}

          {/* Query Results */}
          {result && (
            <div className="space-y-4 pt-1">
              {/* Natural Language Grounded Answer */}
              {groundedAnswer && (
                <div className="p-4 rounded-xl bg-slate-800/90 border border-slate-700/80 shadow-md">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-300 mb-2">
                    <span className="flex items-center gap-1.5 text-emerald-400">
                      <Sparkles className="w-3.5 h-3.5" />
                      Grounded Operator Answer:
                    </span>
                    <span className="text-[11px] text-slate-400 flex items-center gap-1 font-mono">
                      <Clock className="w-3 h-3 text-amber-400" />
                      {result.execution_time_ms ? `${Math.round(result.execution_time_ms)}ms` : '0ms'}
                    </span>
                  </div>
                  <p className="text-xs text-slate-100 leading-relaxed font-sans font-medium">
                    {groundedAnswer}
                  </p>
                </div>
              )}

              {/* Generated SQL */}
              {sqlQuery && (
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-slate-400">
                    <span className="flex items-center gap-1">
                      <Code2 className="w-3.5 h-3.5 text-sky-400" />
                      Generated Read-Only SQL Query:
                    </span>
                    <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 font-medium">
                      AST Guard Validated (Read-Only)
                    </span>
                  </div>
                  <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg overflow-x-auto">
                    <code className="text-xs font-mono text-sky-300 whitespace-pre-wrap select-all">
                      {sqlQuery}
                    </code>
                  </div>
                </div>
              )}

              {/* Structured SQL Data Table */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[11px] font-semibold text-slate-400">
                  <span className="flex items-center gap-1">
                    <TableIcon className="w-3.5 h-3.5 text-indigo-400" />
                    Structured Database Records ({rowCount} row{rowCount === 1 ? '' : 's'}):
                  </span>
                </div>

                {rows.length > 0 && columns.length > 0 ? (
                  <div className="max-h-72 overflow-auto rounded-lg border border-slate-800 bg-slate-950">
                    <table className="w-full text-left text-[11px] border-collapse">
                      <thead>
                        <tr className="bg-slate-900 border-b border-slate-800 text-slate-300 font-semibold sticky top-0 z-10">
                          {columns.map((col, cIdx) => (
                            <th key={cIdx} className="p-2.5 whitespace-nowrap text-slate-400 font-mono text-[10px] uppercase tracking-wider">
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                        {rows.map((row, rIdx) => (
                          <tr key={rIdx} className="hover:bg-slate-900/60 transition-colors">
                            {row.map((val, cIdx) => (
                              <td key={cIdx} className="p-2.5 whitespace-nowrap max-w-xs truncate text-[11px]" title={val !== null ? String(val) : ''}>
                                {val !== null && val !== undefined ? (
                                  String(val)
                                ) : (
                                  <span className="text-slate-600 italic">NULL</span>
                                )}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-xs text-slate-500 italic p-4 bg-slate-950 rounded-lg border border-slate-800 text-center">
                    Query completed with 0 matching rows.
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
