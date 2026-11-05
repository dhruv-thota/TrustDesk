import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TriagePanel from '../src/components/TriagePanel';
import * as client from '../src/api/client';

describe('TriagePanel (EG-P6-05, P6-EC-008)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockTriage = {
    category: 'refund',
    priority: 'high',
    needs_escalation: true,
    reasoning: 'Customer requesting refund for damaged item within 30-day window.',
    is_fallback: false,
    sanitized_diagnostics: {},
  };

  it('triggers AI triage on button click and renders category, priority, and escalation alert (EG-P6-05)', async () => {
    vi.spyOn(client, 'runTriage').mockResolvedValueOnce(mockTriage);
    const onTriageComplete = vi.fn();

    render(
      <TriagePanel
        ticketId="TIK-001"
        triageResult={null}
        onTriageComplete={onTriageComplete}
      />
    );

    const button = screen.getByRole('button', { name: /Run AI Triage/i });
    fireEvent.click(button);

    expect(screen.getByText(/Classifying.../i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('triage-category-badge')).toHaveTextContent('refund');
      expect(screen.getByTestId('triage-priority-badge')).toHaveTextContent('high');
      expect(screen.getByTestId('triage-escalation-badge')).toHaveTextContent('Supervisor Review Required');
      expect(screen.getByText(mockTriage.reasoning)).toBeInTheDocument();
      expect(onTriageComplete).toHaveBeenCalledWith(mockTriage);
    });
  });

  it('renders prominent fallback alert when is_fallback is true (P6-EC-008)', () => {
    const fallbackTriage = {
      ...mockTriage,
      is_fallback: true,
      category: 'general',
      priority: 'medium',
      reasoning: 'Upstream AI provider unavailable. System assigned safe default classification.',
    };

    render(
      <TriagePanel ticketId="TIK-001" triageResult={fallbackTriage} />
    );

    expect(screen.getByTestId('triage-fallback-alert')).toBeInTheDocument();
    expect(
      screen.getByText(/Automated Triage Unavailable \(System Fallback Applied\)/i)
    ).toBeInTheDocument();
  });

  it('displays error alert with retry button when triage call fails', async () => {
    vi.spyOn(client, 'runTriage').mockRejectedValueOnce(
      new Error('AI provider connection timed out')
    );

    render(<TriagePanel ticketId="TIK-001" triageResult={null} />);

    fireEvent.click(screen.getByRole('button', { name: /Run AI Triage/i }));

    await waitFor(() => {
      expect(screen.getByText('AI provider connection timed out')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
    });
  });
});

