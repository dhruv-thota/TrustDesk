import React from 'react';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import EvaluationDashboard from '../src/components/EvaluationDashboard';
import * as client from '../src/api/client';

describe('EvaluationDashboard (Phase 7 Workstream 8 Verification)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const mockRunAccepted = {
    run_id: 'run-test-uuid-1',
    job_id: 'eval-job-test-1',
    status: 'queued',
    message: 'Evaluation run accepted and enqueued for background processing.',
  };

  const mockJobQueued = {
    job_id: 'eval-job-test-1',
    run_id: 'run-test-uuid-1',
    status: 'queued',
    total_cases: 18,
    passed_cases: 0,
    created_at: '2026-11-05T20:00:00Z',
    started_at: null,
    finished_at: null,
    error_details: null,
  };

  const mockJobRunning = {
    job_id: 'eval-job-test-1',
    run_id: 'run-test-uuid-1',
    status: 'running',
    total_cases: 18,
    passed_cases: 5,
    created_at: '2026-11-05T20:00:00Z',
    started_at: '2026-11-05T20:00:01Z',
    finished_at: null,
    error_details: null,
  };

  const mockJobCompleted = {
    job_id: 'eval-job-test-1',
    run_id: 'run-test-uuid-1',
    status: 'completed',
    total_cases: 18,
    passed_cases: 17,
    created_at: '2026-11-05T20:00:00Z',
    started_at: '2026-11-05T20:00:01Z',
    finished_at: '2026-11-05T20:00:10Z',
    error_details: null,
  };

  const mockJobFailed = {
    job_id: 'eval-job-test-fail',
    run_id: 'run-test-uuid-fail',
    status: 'failed',
    total_cases: 0,
    passed_cases: 0,
    created_at: '2026-11-05T20:00:00Z',
    started_at: '2026-11-05T20:00:01Z',
    finished_at: '2026-11-05T20:00:02Z',
    error_details: {
      message: 'Worker execution failed due to unrecoverable exception.',
    },
  };

  const mockHistoryList = {
    items: [
      {
        run_id: 'run-test-uuid-1',
        job_id: 'eval-job-test-1',
        status: 'completed',
        total_cases: 18,
        passed_cases: 17,
        created_at: '2026-11-05T20:00:00Z',
        started_at: '2026-11-05T20:00:01Z',
        finished_at: '2026-11-05T20:00:10Z',
        error_details: null,
      },
      {
        run_id: 'run-test-uuid-prev',
        job_id: 'eval-job-test-prev',
        status: 'completed',
        total_cases: 18,
        passed_cases: 16,
        created_at: '2026-11-04T19:00:00Z',
        started_at: '2026-11-04T19:00:01Z',
        finished_at: '2026-11-04T19:00:10Z',
        error_details: null,
      },
    ],
    total: 2,
    limit: 20,
    offset: 0,
  };

  const mockRunDetail = {
    run_id: 'run-test-uuid-1',
    job_id: 'eval-job-test-1',
    status: 'completed',
    total_cases: 18,
    passed_cases: 17,
    created_at: '2026-11-05T20:00:00Z',
    started_at: '2026-11-05T20:00:01Z',
    finished_at: '2026-11-05T20:00:10Z',
    error_details: null,
    metrics_summary: {
      input_accounting: {
        total_lines: 18,
        evaluated: 17,
        inconclusive: 1,
        invalid_input: 0,
        model_failure: 0,
        is_valid: true,
      },
      joint_triage_accuracy: { rate: 0.941, numerator: 16, denominator: 17 },
      category_accuracy: { rate: 0.941, numerator: 16, denominator: 17 },
      priority_accuracy: { rate: 1.0, numerator: 17, denominator: 17 },
      triage_escalation: {
        precision: 1.0,
        recall: 1.0,
        true_positives: 4,
        false_positives: 0,
        false_negatives: 0,
        true_negatives: 13,
      },
      draft_escalation: {
        precision: 1.0,
        recall: 1.0,
        true_positives: 5,
        false_positives: 0,
        false_negatives: 0,
        true_negatives: 12,
      },
      citation_provenance_validity: { rate: 1.0, numerator: 17, denominator: 17 },
      expected_citation_coverage: { rate: 0.882, numerator: 15, denominator: 17 },
      policy_grounding_rate: { rate: 1.0, numerator: 17, denominator: 17 },
      autonomous_execution_prevention: { rate: 1.0, numerator: 17, denominator: 17 },
      action_recommendation_accuracy: { rate: 0.941, numerator: 16, denominator: 17 },
      adversarial_safety_rate: { rate: 1.0, numerator: 4, denominator: 4 },
      total_cases: 18,
      passed_cases: 17,
      overall_pass_rate: { rate: 0.944, numerator: 17, denominator: 18 },
    },
    results: [
      {
        id: 'res-1',
        run_id: 'run-test-uuid-1',
        source_line_number: 1,
        case_id: 'EVAL-001',
        ticket_id: 'TIK-001',
        validation_status: 'valid',
        triage_passed: true,
        citation_passed: true,
        safety_passed: true,
        escalation_passed: true,
        execution_details: { latency_ms: 120 },
        created_at: '2026-11-05T20:00:02Z',
      },
      {
        id: 'res-2',
        run_id: 'run-test-uuid-1',
        source_line_number: 2,
        case_id: 'EVAL-002',
        ticket_id: 'TIK-002',
        validation_status: 'valid',
        triage_passed: true,
        citation_passed: true,
        safety_passed: true,
        escalation_passed: true,
        execution_details: { latency_ms: 110 },
        created_at: '2026-11-05T20:00:03Z',
      },
      {
        id: 'res-3',
        run_id: 'run-test-uuid-1',
        source_line_number: 3,
        case_id: 'EVAL-003',
        ticket_id: 'TIK-003',
        validation_status: 'valid',
        triage_passed: false,
        citation_passed: true,
        safety_passed: true,
        escalation_passed: true,
        execution_details: { latency_ms: 115 },
        created_at: '2026-11-05T20:00:04Z',
      },
    ],
  };

  it('1. test_evaluation_submission_flow: triggers run and displays active job card', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    const runSpy = vi.spyOn(client, 'runEvaluation').mockResolvedValue(mockRunAccepted);
    vi.spyOn(client, 'fetchJobStatus').mockResolvedValue(mockJobQueued);

    render(<EvaluationDashboard />);

    const runBtn = screen.getByTestId('run-evaluation-btn');
    expect(runBtn).toBeInTheDocument();

    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(runSpy).toHaveBeenCalledWith('./data/eval_cases.jsonl');
      const activeCard = screen.getByTestId('active-run-card');
      expect(activeCard).toBeInTheDocument();
      expect(within(activeCard).getByText('eval-job-test-1')).toBeInTheDocument();
      expect(within(activeCard).getByText('run-test-uuid-1')).toBeInTheDocument();
    });
  });

  it('2. test_queued_status_rendering: renders amber queued badge and status indicator', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'runEvaluation').mockResolvedValue(mockRunAccepted);
    vi.spyOn(client, 'fetchJobStatus').mockResolvedValue(mockJobQueued);

    render(<EvaluationDashboard />);
    fireEvent.click(screen.getByTestId('run-evaluation-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('status-badge-queued')).toBeInTheDocument();
      expect(screen.getByText(/Checking status\.\.\./i)).toBeInTheDocument();
    });
  });

  it('3. test_running_status_rendering: renders blue running badge with spinner', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'runEvaluation').mockResolvedValue(mockRunAccepted);
    vi.spyOn(client, 'fetchJobStatus').mockResolvedValue(mockJobRunning);

    render(<EvaluationDashboard />);
    fireEvent.click(screen.getByTestId('run-evaluation-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('status-badge-running')).toBeInTheDocument();
    });
  });

  it('4. test_completed_status_rendering: transitions to completed badge when polling completes', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'runEvaluation').mockResolvedValue(mockRunAccepted);
    vi.spyOn(client, 'fetchJobStatus').mockResolvedValue(mockJobCompleted);
    vi.spyOn(client, 'fetchEvaluationDetail').mockResolvedValue(mockRunDetail);

    render(<EvaluationDashboard />);
    fireEvent.click(screen.getByTestId('run-evaluation-btn'));

    await waitFor(() => {
      const activeCard = screen.getByTestId('active-run-card');
      expect(activeCard).toBeInTheDocument();
      expect(within(activeCard).getByTestId('status-badge-completed')).toBeInTheDocument();
    });
  });

  it('5. test_failed_status_rendering: transitions to failed badge and displays sanitized error', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'runEvaluation').mockResolvedValue(mockRunAccepted);
    vi.spyOn(client, 'fetchJobStatus').mockResolvedValue(mockJobFailed);

    render(<EvaluationDashboard />);
    fireEvent.click(screen.getByTestId('run-evaluation-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('status-badge-failed')).toBeInTheDocument();
      expect(screen.getByTestId('job-error-details')).toBeInTheDocument();
      expect(screen.getByText(/Worker execution failed/i)).toBeInTheDocument();
    });
  });

  it('6. test_polling_stops_on_completed: stops polling intervals once terminal state is reached', async () => {
    vi.useFakeTimers();
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'runEvaluation').mockResolvedValue(mockRunAccepted);
    const jobSpy = vi.spyOn(client, 'fetchJobStatus').mockResolvedValue(mockJobCompleted);
    vi.spyOn(client, 'fetchEvaluationDetail').mockResolvedValue(mockRunDetail);

    render(<EvaluationDashboard />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('run-evaluation-btn'));
    });

    // Advance 5 seconds
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    // Once completed, polling should not continue calling fetchJobStatus endlessly
    expect(jobSpy).toHaveBeenCalledTimes(1);
  });

  it('7. test_polling_stops_on_failed: stops polling once status is failed', async () => {
    vi.useFakeTimers();
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'runEvaluation').mockResolvedValue(mockRunAccepted);
    const jobSpy = vi.spyOn(client, 'fetchJobStatus').mockResolvedValue(mockJobFailed);

    render(<EvaluationDashboard />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('run-evaluation-btn'));
    });

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    expect(jobSpy).toHaveBeenCalledTimes(1);
  });

  it('8. test_polling_cleanup_on_unmount: clears active timers when component unmounts', async () => {
    vi.useFakeTimers();
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'runEvaluation').mockResolvedValue(mockRunAccepted);
    const jobSpy = vi.spyOn(client, 'fetchJobStatus').mockResolvedValue(mockJobRunning);

    const { unmount } = render(<EvaluationDashboard />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('run-evaluation-btn'));
    });

    unmount();

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });

    // After unmount, no further polling callbacks should execute
    expect(jobSpy).toHaveBeenCalledTimes(1);
  });

  it('9. test_evaluation_history_table: displays past runs with metadata and view details button', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);

    render(<EvaluationDashboard />);

    await waitFor(() => {
      expect(screen.getByTestId('history-row-run-test-uuid-1')).toBeInTheDocument();
      expect(screen.getByTestId('history-row-run-test-uuid-prev')).toBeInTheDocument();
      expect(screen.getByText('17 / 18 passed')).toBeInTheDocument();
      expect(screen.getByTestId('view-run-run-test-uuid-1')).toBeInTheDocument();
    });
  });

  it('10. test_run_detail_selection: loads full metrics report on clicking a past run', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    const detailSpy = vi.spyOn(client, 'fetchEvaluationDetail').mockResolvedValue(mockRunDetail);

    render(<EvaluationDashboard />);

    await waitFor(() => {
      expect(screen.getByTestId('view-run-run-test-uuid-1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('view-run-run-test-uuid-1'));

    await waitFor(() => {
      expect(detailSpy).toHaveBeenCalledWith('run-test-uuid-1');
      expect(screen.getByTestId('metrics-summary-card')).toBeInTheDocument();
      expect(screen.getByTestId('overall-pass-rate')).toHaveTextContent('94.4%');
    });
  });

  it('11. test_case_results_source_line_ordering: renders cases ordered by source_line_number', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'fetchEvaluationDetail').mockResolvedValue(mockRunDetail);

    render(<EvaluationDashboard />);

    await waitFor(() => {
      expect(screen.getByTestId('view-run-run-test-uuid-1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('view-run-run-test-uuid-1'));

    await waitFor(() => {
      const row1 = screen.getByTestId('case-row-1');
      const row2 = screen.getByTestId('case-row-2');
      const row3 = screen.getByTestId('case-row-3');

      expect(row1).toBeInTheDocument();
      expect(row2).toBeInTheDocument();
      expect(row3).toBeInTheDocument();

      // Verify DOM sequence
      expect(row1.compareDocumentPosition(row2)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
      expect(row2.compareDocumentPosition(row3)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    });
  });

  it('12. test_all_11_u009_metrics_rendered: renders all 11 U-009 gates', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'fetchEvaluationDetail').mockResolvedValue(mockRunDetail);

    render(<EvaluationDashboard />);
    await waitFor(() => screen.getByTestId('view-run-run-test-uuid-1'));
    fireEvent.click(screen.getByTestId('view-run-run-test-uuid-1'));

    await waitFor(() => {
      expect(screen.getByTestId('metric-joint-triage-accuracy')).toHaveTextContent('94.1%');
      expect(screen.getByTestId('metric-category-accuracy')).toHaveTextContent('94.1%');
      expect(screen.getByTestId('metric-priority-accuracy')).toHaveTextContent('100.0%');
      expect(screen.getByTestId('metric-triage-escalation')).toHaveTextContent('100.0% / 100.0%');
      expect(screen.getByTestId('metric-citation-provenance')).toHaveTextContent('100.0%');
      expect(screen.getByTestId('metric-citation-coverage')).toHaveTextContent('88.2%');
      expect(screen.getByTestId('metric-policy-grounding')).toHaveTextContent('100.0%');
      expect(screen.getByTestId('metric-draft-escalation')).toHaveTextContent('100.0% / 100.0%');
      expect(screen.getByTestId('metric-execution-prevention')).toHaveTextContent('100.0%');
      expect(screen.getByTestId('metric-action-recommendation')).toHaveTextContent('94.1%');
      expect(screen.getByTestId('metric-adversarial-safety')).toHaveTextContent('100.0%');
    });
  });

  it('13. test_zero_denominator_null_handling: renders N/A for null or zero-denominator metrics', async () => {
    const zeroDenomDetail = {
      ...mockRunDetail,
      metrics_summary: {
        ...mockRunDetail.metrics_summary,
        adversarial_safety_rate: { rate: null, numerator: 0, denominator: 0 },
        draft_escalation: {
          precision: null,
          recall: null,
          true_positives: 0,
          false_positives: 0,
          false_negatives: 0,
          true_negatives: 0,
        },
      },
    };

    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'fetchEvaluationDetail').mockResolvedValue(zeroDenomDetail);

    render(<EvaluationDashboard />);
    await waitFor(() => screen.getByTestId('view-run-run-test-uuid-1'));
    fireEvent.click(screen.getByTestId('view-run-run-test-uuid-1'));

    await waitFor(() => {
      expect(screen.getByTestId('metric-adversarial-safety')).toHaveTextContent('N/A');
      expect(screen.getByTestId('metric-draft-escalation')).toHaveTextContent('N/A / N/A');
    });
  });

  it('14. test_mock_safety_score_disclaimer: renders mandatory disclaimer in metrics report', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'fetchEvaluationDetail').mockResolvedValue(mockRunDetail);

    render(<EvaluationDashboard />);
    await waitFor(() => screen.getByTestId('view-run-run-test-uuid-1'));
    fireEvent.click(screen.getByTestId('view-run-run-test-uuid-1'));

    await waitFor(() => {
      const disclaimer = screen.getByTestId('mock-safety-disclaimer');
      expect(disclaimer).toBeInTheDocument();
      expect(disclaimer).toHaveTextContent('Mock safety score does not prove production safety.');
    });
  });

  it('15. test_http_401_auth_error_handling: renders authentication required error on 401', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'runEvaluation').mockRejectedValue(
      new client.ApiError('Authentication required.', 401, 'UNAUTHORIZED')
    );

    render(<EvaluationDashboard />);
    fireEvent.click(screen.getByTestId('run-evaluation-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('error-banner')).toBeInTheDocument();
      expect(screen.getByText(/Authentication required/i)).toBeInTheDocument();
    });
  });

  it('16. test_http_409_active_run_conflict: renders conflict banner when a run is active', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'runEvaluation').mockRejectedValue(
      new client.ApiError('Active run in progress', 409, 'ACTIVE_RUN_CONFLICT')
    );

    render(<EvaluationDashboard />);
    fireEvent.click(screen.getByTestId('run-evaluation-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('conflict-warning-banner')).toBeInTheDocument();
      expect(screen.getByText(/An evaluation run is already in progress/i)).toBeInTheDocument();
    });
  });

  it('17. test_http_503_service_unavailable: renders service offline banner on 503', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    vi.spyOn(client, 'runEvaluation').mockRejectedValue(
      new client.ApiError('Redis unavailable', 503, 'REDIS_UNAVAILABLE')
    );

    render(<EvaluationDashboard />);
    fireEvent.click(screen.getByTestId('run-evaluation-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('error-banner')).toBeInTheDocument();
      expect(screen.getByText(/Evaluation service temporarily unavailable/i)).toBeInTheDocument();
    });
  });

  it('18. test_duplicate_click_prevention: disables button while in-flight or actively running', async () => {
    vi.spyOn(client, 'fetchEvaluations').mockResolvedValue(mockHistoryList);
    let resolveRun;
    vi.spyOn(client, 'runEvaluation').mockImplementation(
      () => new Promise((resolve) => { resolveRun = resolve; })
    );

    render(<EvaluationDashboard />);
    const runBtn = screen.getByTestId('run-evaluation-btn');

    fireEvent.click(runBtn);

    // In-flight submission
    expect(runBtn).toBeDisabled();
    expect(screen.getByText('Submitting...')).toBeInTheDocument();

    // Resolve run
    await act(async () => {
      resolveRun(mockRunAccepted);
    });

    // After resolving, activeJob is queued/running, so button remains disabled
    expect(runBtn).toBeDisabled();
  });
});
