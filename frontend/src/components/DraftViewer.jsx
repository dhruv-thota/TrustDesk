import React, { useState } from 'react';
import { generateDraft } from '../api/client';

export default function DraftViewer({ ticketId, draftResult: initialDraft, onDraftComplete, onProposeAction }) {
  const [draft, setDraft] = useState(initialDraft || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(null);
  const [expandedCitation, setExpandedCitation] = useState(null);

  const handleGenerateDraft = async () => {
    if (!ticketId) return;
    setLoading(true);
    setError(null);
    setCopyError(null);
    try {
      const res = await generateDraft(ticketId);
      setDraft(res);
      if (onDraftComplete) onDraftComplete(res);
    } catch (err) {
      setError(err.message || 'Draft generation failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyToClipboard = async () => {
    if (!draft?.draft_text) return;
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(draft.draft_text);
        setCopied(true);
        setCopyError(null);
        setTimeout(() => setCopied(false), 2500);
      } else {
        throw new Error('Clipboard API not available');
      }
    } catch {
      setCopyError('Automatic copy unavailable. Please select and copy text manually.');
      setTimeout(() => setCopyError(null), 4000);
    }
  };

  const toggleCitation = (idx) => {
    setExpandedCitation(expandedCitation === idx ? null : idx);
  };

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 p-4">
      <div className="flex items-center justify-between border-b border-gray-100 pb-2.5 mb-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
          <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider">
            Grounded Response Draft
          </h3>
          <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-gray-100 text-gray-600">
            Display-Only
          </span>
        </div>
        <button
          type="button"
          onClick={handleGenerateDraft}
          disabled={loading || !ticketId}
          className="px-3 py-1 text-xs font-medium rounded bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 transition flex items-center gap-1.5 shadow-sm"
        >
          {loading ? (
            <>
              <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              Generating...
            </>
          ) : (
            'Generate Draft Response'
          )}
        </button>
      </div>

      {error && (
        <div className="p-3 mb-3 text-xs bg-rose-50 border border-rose-200 text-rose-700 rounded flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={handleGenerateDraft}
            className="text-xs font-semibold text-rose-800 underline hover:text-rose-900 ml-2"
          >
            Retry
          </button>
        </div>
      )}

      {!draft && !loading && !error && (
        <div className="p-4 text-center text-xs text-gray-500 bg-gray-50 rounded border border-dashed border-gray-200">
          Click "Generate Draft Response" to retrieve policy evidence and prepare a grounded customer response.
        </div>
      )}

      {draft && (
        <div className="space-y-3 text-xs">
          {/* Grounding & Escalation Status Bar */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Level 3 Grounded Badge */}
            <span
              data-testid="draft-grounded-badge"
              className={`px-2.5 py-0.5 rounded font-semibold text-[11px] border ${
                draft.is_grounded
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                  : 'bg-amber-50 text-amber-800 border-amber-300'
              }`}
            >
              {draft.is_grounded ? '✓ Policy Grounded' : '⚠ Ungrounded / Unverified'}
            </span>

            {/* Level 1 Provenance Badge */}
            <span
              data-testid="draft-provenance-badge"
              className={`px-2 py-0.5 rounded text-[11px] font-medium border ${
                draft.has_valid_provenance
                  ? 'bg-blue-50 text-blue-700 border-blue-200'
                  : 'bg-rose-50 text-rose-700 border-rose-200'
              }`}
            >
              {draft.has_valid_provenance ? 'Valid Citation Provenance' : 'Invalid Provenance'}
            </span>

            {/* Escalation Flag */}
            {draft.escalation_suggested && (
              <span
                data-testid="draft-escalation-badge"
                className="px-2.5 py-0.5 rounded bg-rose-100 text-rose-800 border border-rose-300 font-bold uppercase text-[11px]"
              >
                Escalation Required
              </span>
            )}
          </div>

          {/* Supervisor Review Escalation Banner */}
          {draft.escalation_suggested && (
            <div
              className="p-3 bg-amber-50 border-l-4 border-amber-500 text-amber-900 rounded-r"
              data-testid="draft-escalation-alert"
            >
              <div className="font-bold flex items-center gap-1.5 mb-1">
                <span>⚠ Supervisor Review Required: Insufficient Policy Grounding</span>
              </div>
              {draft.escalation_reason && (
                <p className="text-amber-800 leading-relaxed font-normal">
                  {draft.escalation_reason}
                </p>
              )}
            </div>
          )}

          {/* Read-Only Draft Text Box */}
          <div className="relative">
            <div
              data-testid="draft-text-container"
              className="p-3.5 bg-gray-50 border border-gray-200 rounded text-gray-900 font-sans text-xs leading-relaxed whitespace-pre-wrap select-text max-h-64 overflow-y-auto"
            >
              {draft.draft_text}
            </div>

            <div className="mt-2 flex items-center justify-between">
              <span className="text-[11px] text-gray-500 italic">
                Generated response is display-only. Review thoroughly before communicating.
              </span>
              <button
                type="button"
                onClick={handleCopyToClipboard}
                className="px-2.5 py-1 text-xs font-medium rounded bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300 transition flex items-center gap-1"
              >
                {copied ? (
                  <span className="text-emerald-600 font-bold">✓ Copied to Clipboard</span>
                ) : (
                  'Copy to Clipboard'
                )}
              </button>
            </div>

            {copyError && (
              <p className="text-[11px] text-amber-600 mt-1 font-medium">{copyError}</p>
            )}
          </div>

          {/* Supporting Policy Citations */}
          {Array.isArray(draft.citations) && draft.citations.length > 0 && (
            <div className="mt-3 pt-2.5 border-t border-gray-100">
              <span className="font-semibold text-gray-700 block mb-1.5">
                Supporting Policy Citations ({draft.citations.length}):
              </span>
              <div className="flex flex-wrap gap-2">
                {draft.citations.map((c, idx) => {
                  const isExpanded = expandedCitation === idx;
                  const chipLabel = c.section_id || `${c.kb_id}#sec-0`;
                  return (
                    <div key={idx} className="relative">
                      <button
                        type="button"
                        onClick={() => toggleCitation(idx)}
                        data-testid="citation-chip"
                        className={`px-2.5 py-1 text-[11px] font-mono rounded-full border transition flex items-center gap-1.5 ${
                          c.is_valid_provenance
                            ? 'bg-blue-50 text-blue-800 border-blue-200 hover:bg-blue-100'
                            : 'bg-rose-50 text-rose-800 border-rose-300 hover:bg-rose-100'
                        }`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
                        {chipLabel}
                      </button>

                      {isExpanded && (
                        <div className="mt-1 p-2.5 bg-slate-900 text-slate-100 rounded shadow-lg text-[11px] max-w-sm z-10 border border-slate-700">
                          <div className="flex justify-between items-center mb-1 text-[10px] text-slate-400">
                            <span>Policy ID: <strong className="text-white">{c.kb_id}</strong></span>
                            <span>{c.section_id}</span>
                          </div>
                          {c.quoted_snippet ? (
                            <p className="italic text-slate-200 bg-slate-800 p-1.5 rounded border-l-2 border-blue-400">
                              "{c.quoted_snippet}"
                            </p>
                          ) : (
                            <p className="text-slate-400 italic">No direct quoted snippet extracted.</p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* AI Action Recommendation Banner */}
          {draft.suggested_action && draft.suggested_action.should_recommend && (
            <div
              className="mt-3 p-3 bg-purple-50 border border-purple-200 rounded-lg flex items-center justify-between gap-3"
              data-testid="action-recommendation-banner"
            >
              <div>
                <span className="text-xs font-bold text-purple-900 block">
                  AI Recommendation: {draft.suggested_action.action_type}
                </span>
                <p className="text-xs text-purple-800 mt-0.5">
                  {draft.suggested_action.reasoning || 'Context indicates an operational refund review may be warranted.'}
                </p>
              </div>
              {onProposeAction && (
                <button
                  type="button"
                  onClick={() => onProposeAction(draft.suggested_action)}
                  className="px-3 py-1.5 text-xs font-semibold rounded bg-purple-600 hover:bg-purple-500 text-white shadow-sm transition whitespace-nowrap"
                >
                  Propose Refund Review
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

