import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  runEvaluation,
  fetchJobStatus,
  fetchEvaluations,
  fetchEvaluationDetail,
  ApiError,
} from '../api/client';

function formatRate(metric) {
  if (!metric || metric.rate === null || metric.rate === undefined || metric.denominator === 0) {
    return 'N/A';
  }
  return `${(metric.rate * 100).toFixed(1)}%`;
}

function formatFraction(metric) {
  if (!metric || metric.denominator === 0) {
    return 'N/A';
  }
  return `${metric.numerator}/${metric.denominator}`;
}

function formatPR(val) {
  if (val === null || val === undefined) {
    return 'N/A';
  }
  return `${(val * 100).toFixed(1)}%`;
}

export default function EvaluationDashboard() {
  const [datasetPath, setDatasetPath] = useState('./data/eval_cases.jsonl');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeJob, setActiveJob] = useState(null); // { job_id, run_id, status, ... }
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [evalHistory, setEvalHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [errorBanner, setErrorBanner] = useState(null);
  const [conflictWarning, setConflictWarning] = useState(null);
  const [expandedRow, setExpandedRow] = useState(null);

  const pollIntervalRef = useRef(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, []);

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const res = await fetchEvaluations({ limit: 20, offset: 0 });
      if (isMountedRef.current) {
        setEvalHistory(res.items || []);
      }
    } catch (err) {
      if (isMountedRef.current) {
        handleApiError(err, 'Failed to load evaluation history.');
      }
    } finally {
      if (isMountedRef.current) {
        setLoadingHistory(false);
      }
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const loadRunDetail = useCallback(async (runId) => {
    if (!runId) return;
    setLoadingDetail(true);
    setErrorBanner(null);
    try {
      const detail = await fetchEvaluationDetail(runId);
      if (isMountedRef.current) {
        setSelectedDetail(detail);
        setSelectedRunId(runId);
      }
    } catch (err) {
      if (isMountedRef.current) {
        handleApiError(err, `Failed to load details for run ${runId}`);
      }
    } finally {
      if (isMountedRef.current) {
        setLoadingDetail(false);
      }
    }
  }, []);

  const handleApiError = (err, fallbackMsg) => {
    if (err.status === 409) {
      setConflictWarning('An evaluation run is already in progress. Please wait for it to complete.');
    } else if (err.status === 503) {
      setErrorBanner('Evaluation service temporarily unavailable. Background worker or queue is offline.');
    } else if (err.status === 404) {
      setErrorBanner('Evaluation run not found.');
    } else if (err.status === 401) {
      setErrorBanner('Authentication required. Invalid or missing demo token.');
    } else if (err.status === 0 || err.code === 'NETWORK_ERROR') {
      setErrorBanner('Unable to connect to TrustDesk backend. Check server status.');
    } else {
      setErrorBanner(err.message || fallbackMsg);
    }
  };

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const startPolling = useCallback((jobId, runId) => {
    stopPolling();

    const checkStatus = async () => {
      try {
        const jobStatus = await fetchJobStatus(jobId);
        if (!isMountedRef.current) return;

        setActiveJob(jobStatus);

        if (jobStatus.status === 'completed' || jobStatus.status === 'failed') {
          stopPolling();
          loadHistory();
          if (runId) {
            loadRunDetail(runId);
          }
        }
      } catch (err) {
        // Tolerant to transient network errors during polling
        console.warn('Polling error (transient):', err);
      }
    };

    // Immediate first check
    checkStatus();
    // Then every 1000ms
    pollIntervalRef.current = setInterval(checkStatus, 1000);
  }, [stopPolling, loadHistory, loadRunDetail]);

  const handleRunSuite = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setErrorBanner(null);
    setConflictWarning(null);

    try {
      const response = await runEvaluation(datasetPath.trim());
      setActiveJob({
        job_id: response.job_id,
        run_id: response.run_id,
        status: response.status || 'queued',
        created_at: new Date().toISOString(),
      });
      setSelectedRunId(response.run_id);
      startPolling(response.job_id, response.run_id);
      loadHistory();
    } catch (err) {
      handleApiError(err, 'Failed to trigger evaluation suite.');
    } finally {
      if (isMountedRef.current) {
        setIsSubmitting(false);
      }
    }
  };

  const getStatusBadge = (status) => {
    switch (status?.toLowerCase()) {
      case 'queued':
        return (
          <span
            data-testid="status-badge-queued"
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300"
          >
            ● Queued
          </span>
        );
      case 'running':
        return (
          <span
            data-testid="status-badge-running"
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-300"
          >
            <svg
              className="animate-spin -ml-0.5 mr-1.5 h-3 w-3 text-blue-600"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
              ></path>
            </svg>
            Running
          </span>
        );
      case 'completed':
        return (
          <span
            data-testid="status-badge-completed"
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300"
          >
            ✓ Completed
          </span>
        );
      case 'failed':
        return (
          <span
            data-testid="status-badge-failed"
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300"
          >
            ✕ Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
            {status || 'Unknown'}
          </span>
        );
    }
  };

  const metrics = selectedDetail?.metrics_summary;
  const inputAcc = metrics?.input_accounting;

  return (
    <div className="space-y-6" data-testid="evaluation-dashboard">
      {/* 1. Header & Suite Execution Bar */}
      <div className="bg-white rounded-lg shadow border border-gray-200 p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-600"></span>
              Evaluation & Verification Dashboard
            </h2>
            <p className="text-xs text-gray-500 mt-1">
              Autonomous execution suite, U-009 deterministic metric verification, and execution trace inspection.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <label htmlFor="eval-dataset-path" className="text-xs font-medium text-gray-600">
                Dataset:
              </label>
              <input
                id="eval-dataset-path"
                type="text"
                value={datasetPath}
                onChange={(e) => setDatasetPath(e.target.value)}
                placeholder="./data/eval_cases.jsonl"
                className="text-xs px-2.5 py-1.5 border border-gray-300 rounded shadow-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono w-56"
                disabled={isSubmitting}
              />
            </div>

            <button
              type="button"
              data-testid="run-evaluation-btn"
              onClick={handleRunSuite}
              disabled={isSubmitting || activeJob?.status === 'running' || activeJob?.status === 'queued'}
              className="px-4 py-1.5 text-xs font-bold rounded bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 disabled:cursor-not-allowed shadow-sm transition flex items-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <svg className="animate-spin h-3.5 w-3.5 text-white" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>
                  </svg>
                  <span>Submitting...</span>
                </>
              ) : (
                <>
                  <span>▶</span>
                  <span>Run Evaluation Suite</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Conflict Warning (HTTP 409) */}
        {conflictWarning && (
          <div
            data-testid="conflict-warning-banner"
            className="mt-3 p-3 bg-amber-50 border border-amber-300 text-amber-900 rounded text-xs flex items-center justify-between"
          >
            <div className="flex items-center gap-2">
              <span className="font-bold">⚠️ Warning:</span>
              <span>{conflictWarning}</span>
            </div>
            <button
              type="button"
              onClick={() => setConflictWarning(null)}
              className="text-amber-800 hover:text-amber-950 font-bold px-2 py-0.5"
            >
              ✕
            </button>
          </div>
        )}

        {/* Error Banner */}
        {errorBanner && (
          <div
            data-testid="error-banner"
            className="mt-3 p-3 bg-rose-50 border border-rose-300 text-rose-900 rounded text-xs flex items-center justify-between"
          >
            <div className="flex items-center gap-2">
              <span className="font-bold">Error:</span>
              <span>{errorBanner}</span>
            </div>
            <button
              type="button"
              onClick={() => setErrorBanner(null)}
              className="text-rose-800 hover:text-rose-950 font-bold px-2 py-0.5"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* 2. Active Run Status Card (if an active job exists) */}
      {activeJob && (
        <div
          data-testid="active-run-card"
          className="bg-white rounded-lg shadow border border-gray-200 p-4 border-l-4 border-l-indigo-500"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 pb-2 mb-3">
            <div className="flex items-center gap-3">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-700">
                Active Job Status
              </span>
              {getStatusBadge(activeJob.status)}
              {(activeJob.status === 'queued' || activeJob.status === 'running') && (
                <span className="text-xs text-indigo-600 font-medium animate-pulse flex items-center gap-1">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-indigo-600"></span>
                  Checking status...
                </span>
              )}
            </div>

            <div className="text-xs text-gray-500 font-mono">
              Job: <span className="font-semibold text-gray-700">{activeJob.job_id}</span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div>
              <span className="text-gray-500 block">Run ID</span>
              <span className="font-mono text-gray-800 break-all">{activeJob.run_id}</span>
            </div>
            <div>
              <span className="text-gray-500 block">Created At</span>
              <span className="text-gray-800">
                {activeJob.created_at ? new Date(activeJob.created_at).toLocaleTimeString() : '—'}
              </span>
            </div>
            <div>
              <span className="text-gray-500 block">Completed Cases</span>
              <span className="text-gray-800 font-semibold">
                {activeJob.total_cases !== undefined ? `${activeJob.passed_cases || 0} / ${activeJob.total_cases}` : '—'}
              </span>
            </div>
            <div>
              <span className="text-gray-500 block">Finished At</span>
              <span className="text-gray-800">
                {activeJob.finished_at ? new Date(activeJob.finished_at).toLocaleTimeString() : 'In Progress'}
              </span>
            </div>
          </div>

          {activeJob.error_details && (
            <div
              data-testid="job-error-details"
              className="mt-3 p-2.5 bg-rose-50 border border-rose-200 rounded text-xs text-rose-900"
            >
              <div className="font-bold">Failure Details:</div>
              <div className="font-mono text-xs mt-1">
                {activeJob.error_details.message || JSON.stringify(activeJob.error_details)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 3. Evaluation Summary & Metrics Card (U-009 Metric Gates) */}
      {loadingDetail ? (
        <div className="bg-white rounded-lg shadow border border-gray-200 p-8 text-center text-gray-500 text-xs">
          <svg className="animate-spin h-5 w-5 text-indigo-600 mx-auto mb-2" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>
          </svg>
          Loading evaluation metrics & case outcomes...
        </div>
      ) : selectedDetail && metrics ? (
        <div data-testid="metrics-summary-card" className="bg-white rounded-lg shadow border border-gray-200 p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between border-b border-gray-100 pb-3 gap-2">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-gray-900">
                  Evaluation Report — {selectedDetail.run_id}
                </h3>
                {getStatusBadge(selectedDetail.status)}
              </div>
              <p className="text-xs text-gray-500 mt-0.5">
                Evaluated: {new Date(selectedDetail.created_at).toLocaleString()} | Cases: {selectedDetail.total_cases} | Passed: {selectedDetail.passed_cases}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-gray-700">Overall Pass Rate:</span>
              <span
                data-testid="overall-pass-rate"
                className="text-sm font-extrabold px-2.5 py-1 rounded bg-indigo-50 text-indigo-700 border border-indigo-200 font-mono"
              >
                {formatRate(metrics.overall_pass_rate)}
              </span>
            </div>
          </div>

          {/* U-009 Metric Gates Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Column 1: Triage Performance */}
            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-700 border-b border-slate-200 pb-1">
                Triage Performance
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Joint Triage Accuracy:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-joint-triage-accuracy">
                  {formatRate(metrics.joint_triage_accuracy)}
                  <span className="text-slate-400 font-normal ml-1">({formatFraction(metrics.joint_triage_accuracy)})</span>
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Category Accuracy:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-category-accuracy">
                  {formatRate(metrics.category_accuracy)}
                  <span className="text-slate-400 font-normal ml-1">({formatFraction(metrics.category_accuracy)})</span>
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Priority Accuracy:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-priority-accuracy">
                  {formatRate(metrics.priority_accuracy)}
                  <span className="text-slate-400 font-normal ml-1">({formatFraction(metrics.priority_accuracy)})</span>
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Triage Escalation P/R:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-triage-escalation">
                  {formatPR(metrics.triage_escalation?.precision)} / {formatPR(metrics.triage_escalation?.recall)}
                </span>
              </div>
            </div>

            {/* Column 2: Grounding & Citation Quality */}
            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-700 border-b border-slate-200 pb-1">
                Grounding & Citations
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Citation Provenance Validity:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-citation-provenance">
                  {formatRate(metrics.citation_provenance_validity)}
                  <span className="text-slate-400 font-normal ml-1">({formatFraction(metrics.citation_provenance_validity)})</span>
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Expected Citation Coverage:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-citation-coverage">
                  {formatRate(metrics.expected_citation_coverage)}
                  <span className="text-slate-400 font-normal ml-1">({formatFraction(metrics.expected_citation_coverage)})</span>
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Policy Grounding Rate:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-policy-grounding">
                  {formatRate(metrics.policy_grounding_rate)}
                  <span className="text-slate-400 font-normal ml-1">({formatFraction(metrics.policy_grounding_rate)})</span>
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Draft Escalation P/R:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-draft-escalation">
                  {formatPR(metrics.draft_escalation?.precision)} / {formatPR(metrics.draft_escalation?.recall)}
                </span>
              </div>
            </div>

            {/* Column 3: Safety & Guardrails */}
            <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-700 border-b border-slate-200 pb-1">
                Safety & Guardrails
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Autonomous Execution Prev.:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-execution-prevention">
                  {formatRate(metrics.autonomous_execution_prevention)}
                  <span className="text-slate-400 font-normal ml-1">({formatFraction(metrics.autonomous_execution_prevention)})</span>
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Action Recommendation Acc.:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-action-recommendation">
                  {formatRate(metrics.action_recommendation_accuracy)}
                  <span className="text-slate-400 font-normal ml-1">({formatFraction(metrics.action_recommendation_accuracy)})</span>
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-600">Adversarial Safety Rate:</span>
                <span className="font-bold text-slate-800 font-mono" data-testid="metric-adversarial-safety">
                  {formatRate(metrics.adversarial_safety_rate)}
                  <span className="text-slate-400 font-normal ml-1">({formatFraction(metrics.adversarial_safety_rate)})</span>
                </span>
              </div>
            </div>
          </div>

          {/* Input Accounting & Mock Safety Disclaimer Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-gray-50 border border-gray-200 rounded text-xs">
            <div className="flex flex-wrap items-center gap-4 text-gray-600">
              <span className="font-bold text-gray-700">Accounting:</span>
              <span>Total Lines: <strong className="text-gray-900">{inputAcc?.total_lines ?? 0}</strong></span>
              <span>Evaluated: <strong className="text-gray-900">{inputAcc?.evaluated ?? 0}</strong></span>
              <span>Inconclusive: <strong className="text-gray-900">{inputAcc?.inconclusive ?? 0}</strong></span>
              <span>Invalid Input: <strong className="text-gray-900">{inputAcc?.invalid_input ?? 0}</strong></span>
              <span>Model Failure: <strong className="text-gray-900">{inputAcc?.model_failure ?? 0}</strong></span>
            </div>

            {/* Mock Safety Score Disclaimer (Mandatory U-009) */}
            <div
              data-testid="mock-safety-disclaimer"
              className="text-amber-800 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded text-xs italic font-medium"
            >
              ⚠️ Mock safety score does not prove production safety.
            </div>
          </div>

          {/* 4. Case Results Detail Table */}
          {selectedDetail.results && selectedDetail.results.length > 0 && (
            <div className="mt-4 pt-3 border-t border-gray-100">
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-700 mb-2">
                Per-Case Results ({selectedDetail.results.length} cases, ordered by source line)
              </h4>

              <div className="overflow-x-auto border border-gray-200 rounded">
                <table className="min-w-full divide-y divide-gray-200 text-xs">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="px-3 py-2 text-left font-semibold">Line</th>
                      <th className="px-3 py-2 text-left font-semibold">Case ID</th>
                      <th className="px-3 py-2 text-left font-semibold">Ticket ID</th>
                      <th className="px-3 py-2 text-left font-semibold">Validation Status</th>
                      <th className="px-2 py-2 text-center font-semibold">Triage</th>
                      <th className="px-2 py-2 text-center font-semibold">Citation</th>
                      <th className="px-2 py-2 text-center font-semibold">Safety</th>
                      <th className="px-2 py-2 text-center font-semibold">Escalation</th>
                      <th className="px-3 py-2 text-center font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 bg-white" data-testid="case-results-tbody">
                    {selectedDetail.results.map((row) => (
                      <React.Fragment key={row.source_line_number}>
                        <tr
                          data-testid={`case-row-${row.source_line_number}`}
                          className="hover:bg-slate-50 transition"
                        >
                          <td className="px-3 py-2 font-mono text-gray-500">
                            #{row.source_line_number}
                          </td>
                          <td className="px-3 py-2 font-mono font-medium text-gray-800">
                            {row.case_id || '—'}
                          </td>
                          <td className="px-3 py-2 font-mono text-gray-600">
                            {row.ticket_id || '—'}
                          </td>
                          <td className="px-3 py-2">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[11px] font-medium ${
                                row.validation_status === 'valid'
                                  ? 'bg-emerald-50 text-emerald-700'
                                  : row.validation_status === 'inconclusive'
                                  ? 'bg-amber-50 text-amber-700'
                                  : 'bg-rose-50 text-rose-700'
                              }`}
                            >
                              {row.validation_status}
                            </span>
                          </td>
                          <td className="px-2 py-2 text-center">
                            {row.triage_passed ? (
                              <span className="text-emerald-600 font-bold">✓</span>
                            ) : (
                              <span className="text-rose-600 font-bold">✕</span>
                            )}
                          </td>
                          <td className="px-2 py-2 text-center">
                            {row.citation_passed ? (
                              <span className="text-emerald-600 font-bold">✓</span>
                            ) : (
                              <span className="text-rose-600 font-bold">✕</span>
                            )}
                          </td>
                          <td className="px-2 py-2 text-center">
                            {row.safety_passed ? (
                              <span className="text-emerald-600 font-bold">✓</span>
                            ) : (
                              <span className="text-rose-600 font-bold">✕</span>
                            )}
                          </td>
                          <td className="px-2 py-2 text-center">
                            {row.escalation_passed ? (
                              <span className="text-emerald-600 font-bold">✓</span>
                            ) : (
                              <span className="text-rose-600 font-bold">✕</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-center">
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedRow(
                                  expandedRow === row.source_line_number
                                    ? null
                                    : row.source_line_number
                                )
                              }
                              className="text-indigo-600 hover:text-indigo-800 font-medium text-xs"
                            >
                              {expandedRow === row.source_line_number ? 'Hide' : 'Details'}
                            </button>
                          </td>
                        </tr>

                        {expandedRow === row.source_line_number && (
                          <tr className="bg-slate-50">
                            <td colSpan={9} className="px-4 py-3">
                              <div className="p-3 bg-white border border-slate-200 rounded text-xs space-y-2">
                                <div className="font-bold text-gray-700">Execution Details & Diagnostics:</div>
                                <pre className="bg-slate-900 text-slate-100 p-2.5 rounded font-mono text-[11px] overflow-x-auto">
                                  {JSON.stringify(row.execution_details, null, 2)}
                                </pre>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : null}

      {/* 5. Historical Runs List Table */}
      <div className="bg-white rounded-lg shadow border border-gray-200 p-4">
        <div className="flex items-center justify-between border-b border-gray-100 pb-2 mb-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-slate-500"></span>
            <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider">
              Evaluation History
            </h3>
          </div>
          <button
            type="button"
            onClick={loadHistory}
            disabled={loadingHistory}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
          >
            {loadingHistory ? 'Refreshing...' : '↻ Refresh History'}
          </button>
        </div>

        {evalHistory.length === 0 ? (
          <div
            data-testid="no-history-placeholder"
            className="p-6 text-center text-gray-500 text-xs"
          >
            No evaluation runs recorded yet. Click &quot;Run Evaluation Suite&quot; above to trigger your first evaluation.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 text-xs">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold">Run ID</th>
                  <th className="px-3 py-2 text-left font-semibold">Status</th>
                  <th className="px-3 py-2 text-left font-semibold">Created</th>
                  <th className="px-3 py-2 text-left font-semibold">Cases</th>
                  <th className="px-3 py-2 text-right font-semibold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white" data-testid="eval-history-tbody">
                {evalHistory.map((item) => (
                  <tr
                    key={item.run_id}
                    data-testid={`history-row-${item.run_id}`}
                    className={`hover:bg-slate-50 transition ${
                      selectedRunId === item.run_id ? 'bg-indigo-50/50' : ''
                    }`}
                  >
                    <td className="px-3 py-2 font-mono font-medium text-gray-800">
                      {item.run_id}
                    </td>
                    <td className="px-3 py-2">
                      {getStatusBadge(item.status)}
                    </td>
                    <td className="px-3 py-2 text-gray-500">
                      {item.created_at ? new Date(item.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-3 py-2 text-gray-700">
                      {item.passed_cases} / {item.total_cases} passed
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        data-testid={`view-run-${item.run_id}`}
                        onClick={() => loadRunDetail(item.run_id)}
                        className="px-2.5 py-1 text-xs font-semibold rounded bg-white hover:bg-indigo-50 text-indigo-600 border border-indigo-200 transition"
                      >
                        View Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

