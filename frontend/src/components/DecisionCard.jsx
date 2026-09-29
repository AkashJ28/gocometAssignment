import React, { useState, useEffect } from 'react';
import { GitFork, CheckCircle2, UserCheck, MailQuestion, Copy, Check, Sparkles, Send } from 'lucide-react';

export default function DecisionCard({ decision }) {
  const [emailText, setEmailText] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (decision?.email_draft) {
      setEmailText(decision.email_draft);
    } else {
      setEmailText('');
    }
  }, [decision]);

  if (!decision) {
    return (
      <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 p-8 text-center text-slate-500">
        <GitFork className="w-10 h-10 mx-auto mb-2 text-slate-600" />
        <p className="text-sm font-medium">No routing decision rendered yet.</p>
        <p className="text-xs text-slate-500 mt-1">Decision Agent will evaluate validation findings and determine outcome.</p>
      </div>
    );
  }

  const decType = (decision.decision || '').toLowerCase();

  const getDecisionBadge = () => {
    if (decType === 'auto_approve') {
      return {
        label: 'AUTO APPROVE',
        desc: 'All trade fields matched customer baseline requirements with high confidence.',
        bg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
        icon: CheckCircle2,
      };
    }
    if (decType === 'amendment_request') {
      return {
        label: 'AMENDMENT REQUEST',
        desc: 'Concrete rule mismatch detected. Drafted amendment request prepared for supplier/shipper.',
        bg: 'bg-purple-500/10 border-purple-500/30 text-purple-400',
        icon: MailQuestion,
      };
    }
    return {
      label: 'HUMAN REVIEW',
      desc: 'Uncertain confidence or borderline validation requires Cargo Operator intervention.',
      bg: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
      icon: UserCheck,
    };
  };

  const badgeInfo = getDecisionBadge();
  const Icon = badgeInfo.icon;

  const handleCopy = () => {
    if (!emailText) return;
    navigator.clipboard.writeText(emailText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 overflow-hidden shadow-lg">
      {/* Header */}
      <div className="p-4 border-b border-slate-700/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-800">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <GitFork className="w-4 h-4 text-purple-400" />
            Router / Decision Agent Outcome (UI-04)
          </h3>
          <p className="text-xs text-slate-400">
            Autonomous decision routing and automated amendment response drafting
          </p>
        </div>

        {/* Outcome Badge */}
        <div className={`px-4 py-2 rounded-xl border font-bold text-xs tracking-wider flex items-center gap-2 ${badgeInfo.bg}`}>
          <Icon className="w-4 h-4" />
          <span>{badgeInfo.label}</span>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* Rationale Box */}
        <div className="bg-slate-900/70 rounded-xl p-4 border border-slate-700/60">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-300 mb-2">
            <Sparkles className="w-3.5 h-3.5 text-sky-400" />
            Decision Rationale & Autonomous Reasoning:
          </div>
          <p className="text-xs text-slate-300 leading-relaxed font-sans">
            {decision.reasoning || 'No structured rationale provided.'}
          </p>
          <div className="mt-3 pt-2 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-500">
            <span>Evaluated by Router Agent</span>
            <span>Policy: Zero Silent Approvals strictly enforced</span>
          </div>
        </div>

        {/* Draft Amendment Email (if amendment or email draft exists) */}
        {(decType === 'amendment_request' || emailText) && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <MailQuestion className="w-3.5 h-3.5 text-purple-400" />
                Draft Amendment Email (Editable by Cargo Operator):
              </label>
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-slate-500 font-mono">
                  {emailText.length} characters
                </span>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="flex items-center gap-1 text-xs px-2.5 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200 transition"
                  title="Copy email to clipboard"
                >
                  {copied ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400 font-medium">Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>Copy Draft</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="relative">
              <textarea
                rows={6}
                value={emailText}
                onChange={(e) => setEmailText(e.target.value)}
                placeholder="Draft amendment email..."
                className="w-full bg-slate-900/90 border border-purple-500/30 rounded-xl p-3 text-xs text-slate-200 font-mono leading-relaxed focus:outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500"
              />
            </div>
            <p className="text-[11px] text-slate-400 italic">
              Note: This is an operator draft for review. Under Part 1 scope, emails are not sent automatically.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
