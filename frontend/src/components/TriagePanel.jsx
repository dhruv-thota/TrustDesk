import React, { useState } from 'react';
import { runTriage } from '../api/client';

export default function TriagePanel({ ticketId, triageResult: initialTriage, onTriageComplete }) {
  const [triage, setTriage] = useState(initialTriage || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleRunTriage = async () => {
    if (!ticketId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runTriage(ticketId);
      setTriage(res);
      if (onTriageComplete) onTriageComplete(res);
    } catch (err) {
      setError(err.message || 'AI Triage execution failed.');
    } finally {
      setLoading(false);
    }
  };

  const getCategoryColor = (cat) => {
    switch (cat?.toLowerCase()) {
      case 'shipping': return 'bg-sky-100 text-sky-800 border-sky-300';
      case 'refund': return 'bg-amber-100 text-amber-800 border-amber-300';
      case 'warranty': return 'bg-purple-100 text-purple-800 border-purple-300';
      case 'billing': return 'bg-indigo-100 text-indigo-800 border-indigo-300';
      case 'account_security': return 'bg-rose-100 text-rose-800 border-rose-300';
      default: return 'bg-gray-100 text-gray-800 border-gray-300';
    }
  };

  const getPriorityColor = (prio) => {
    switch (prio?.toLowerCase()) {
      case 'urgent': return 'bg-red-600 text-white';
      case 'high': return 'bg-orange-500 text-white';
      case 'medium': return 'bg-blue-600 text-white';
      case 'low': return 'bg-slate-500 text-white';
      default: return 'bg-gray-600 text-white';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 p-4">
      <div className="flex items-center justify-between border-b border-gray-100 pb-2.5 mb-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
          <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider">
            AI Ticket Triage
          </h3>
        </div>
        <button
          type="button"
          onClick={handleRunTriage}
          disabled={loading || !ticketId}
          className="px-3 py-1 text-xs font-medium rounded bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 transition flex items-center gap-1.5 shadow-sm"
        >
          {loading ? (
            <>
              <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              Classifying...
            </>
          ) : (
            'Run AI Triage'
          )}
        </button>
      </div>

      {error && (
        <div className="p-3 mb-3 text-xs bg-rose-50 border border-rose-200 text-rose-700 rounded flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={handleRunTriage}
            className="text-xs font-semibold text-rose-800 underline hover:text-rose-900 ml-2"
          >
            Retry
          </button>
        </div>
      )}

      {!triage && !loading && !error && (
        <div className="p-4 text-center text-xs text-gray-500 bg-gray-50 rounded border border-dashed border-gray-200">
          Click "Run AI Triage" to classify ticket issue category, operational priority, and escalation need.
        </div>
      )}

      {triage && (
        <div className="space-y-3 text-xs">
          {/* Fallback Warning Notice */}
          {triage.is_fallback && (
            <div
              className="p-2.5 bg-amber-50 border border-amber-300 text-amber-800 rounded font-medium flex items-center gap-2"
              data-testid="triage-fallback-alert"
            >
              <span className="inline-block w-2 h-2 rounded-full bg-amber-500"></span>
              Automated Triage Unavailable (System Fallback Applied)
            </div>
          )}

          {/* Badges Row */}
          <div className="flex flex-wrap items-center gap-2">
            <div>
              <span className="text-gray-500 mr-1.5">Category:</span>
              <span
                data-testid="triage-category-badge"
                className={`px-2.5 py-0.5 rounded border font-semibold uppercase text-[11px] ${getCategoryColor(triage.category)}`}
              >
                {triage.category}
              </span>
            </div>

            <div>
              <span className="text-gray-500 mr-1.5">Priority:</span>
              <span
                data-testid="triage-priority-badge"
                className={`px-2 py-0.5 rounded font-semibold uppercase text-[11px] ${getPriorityColor(triage.priority)}`}
              >
                {triage.priority}
              </span>
            </div>

            {triage.needs_escalation && (
              <span
                data-testid="triage-escalation-badge"
                className="px-2.5 py-0.5 rounded bg-rose-100 text-rose-800 border border-rose-300 font-bold uppercase text-[11px] flex items-center gap-1"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-rose-600"></span>
                Supervisor Review Required
              </span>
            )}
          </div>

          {/* Reasoning */}
          {triage.reasoning && (
            <div className="mt-2 bg-gray-50 border border-gray-100 rounded p-2.5 text-gray-700">
              <span className="font-semibold text-gray-900 block mb-0.5">Classification Reasoning:</span>
              <p className="leading-relaxed">{triage.reasoning}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

