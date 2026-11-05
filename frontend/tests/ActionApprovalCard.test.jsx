import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ActionApprovalCard from '../src/components/ActionApprovalCard';
import * as client from '../src/api/client';

describe('ActionApprovalCard (EG-P6-09, EG-P6-10, P6-EC-012, P6-EC-013, P6-EC-014, P6-EC-015)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockPendingAction = {
    action_id: '123e4567-e89b-12d3-a456-426614174000',
    ticket_id: 'TIK-001',
    action_type: 'start_refund_review',
    status: 'pending_approval',
    proposed_by: 'ai',
    created_at: '2026-11-04T12:00:00Z',
    action_payload: {
      order_id: 'ORD-001',
      reason: 'Delivered item cracked within window',
    },
  };

  it('renders pending action payload and reviewer controls (EG-P6-09)', () => {
    render(
      <ActionApprovalCard
        ticketId="TIK-001"
        orderId="ORD-001"
        action={mockPendingAction}
      />
    );

    expect(screen.getByTestId('action-status-badge')).toHaveTextContent('pending_approval');
    expect(screen.getByTestId('action-payload-preview')).toBeInTheDocument();
    expect(screen.getByLabelText(/Human Agent Reviewer Notes/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Approve Review/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Reject Review/i })).toBeInTheDocument();
  });

  it('submits human approval with Idempotency-Key and updates state to executed (EG-P6-09)', async () => {
    const approveSpy = vi.spyOn(client, 'approveAction').mockResolvedValueOnce({
      action_id: mockPendingAction.action_id,
      ticket_id: 'TIK-001',
      action_type: 'start_refund_review',
      status: 'executed',
      reviewed_by: 'demo-agent-001',
      reviewed_at: '2026-11-04T12:05:00Z',
      executed_at: '2026-11-04T12:05:00Z',
      execution_details: { registered: true },
    });

    const onActionUpdated = vi.fn();
    render(
      <ActionApprovalCard
        ticketId="TIK-001"
        orderId="ORD-001"
        action={mockPendingAction}
        onActionUpdated={onActionUpdated}
      />
    );

    // Enter reviewer notes
    const notesInput = screen.getByLabelText(/Human Agent Reviewer Notes/i);
    fireEvent.change(notesInput, { target: { value: 'Verified delivery photo. Approved.' } });

    fireEvent.click(screen.getByRole('button', { name: /Approve Review/i }));

    await waitFor(() => {
      expect(approveSpy).toHaveBeenCalledWith(
        mockPendingAction.action_id,
        {
          notes: 'Verified delivery photo. Approved.',
          parameters: mockPendingAction.action_payload,
        },
        expect.any(String) // Valid UUID Idempotency-Key
      );
      expect(screen.getByTestId('action-status-badge')).toHaveTextContent('executed');
      expect(screen.getByTestId('action-success-alert')).toHaveTextContent('executed successfully');
      expect(onActionUpdated).toHaveBeenCalled();
    });
  });

  it('retains the SAME Idempotency-Key across transient retry attempts (P6-EC-013, EG-P6-09)', async () => {
    // 1st call fails with network error
    const approveSpy = vi
      .spyOn(client, 'approveAction')
      .mockRejectedValueOnce(new client.ApiError('Network connection dropped', 0, 'NETWORK_ERROR'))
      // 2nd call succeeds
      .mockResolvedValueOnce({
        action_id: mockPendingAction.action_id,
        status: 'executed',
        reviewed_by: 'demo-agent-001',
      });

    render(
      <ActionApprovalCard
        ticketId="TIK-001"
        orderId="ORD-001"
        action={mockPendingAction}
      />
    );

    const approveBtn = screen.getByRole('button', { name: /Approve Review/i });

    // 1st attempt
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(screen.getByTestId('action-error-alert')).toBeInTheDocument();
    });

    const firstKey = approveSpy.mock.calls[0][2];
    expect(firstKey).toBeDefined();

    // Retry attempt
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(approveSpy).toHaveBeenCalledTimes(2);
      const secondKey = approveSpy.mock.calls[1][2];
      // Key must be IDENTICAL across retries!
      expect(secondKey).toBe(firstKey);
      expect(screen.getByTestId('action-status-badge')).toHaveTextContent('executed');
    });
  });

  it('disables action buttons while submission is in-flight to prevent multi-clicks (P6-EC-012)', async () => {
    let resolveApprove;
    const pendingPromise = new Promise((resolve) => {
      resolveApprove = resolve;
    });
    vi.spyOn(client, 'approveAction').mockReturnValueOnce(pendingPromise);

    render(
      <ActionApprovalCard
        ticketId="TIK-001"
        orderId="ORD-001"
        action={mockPendingAction}
      />
    );

    const approveBtn = screen.getByRole('button', { name: /Approve Review/i });
    const rejectBtn = screen.getByRole('button', { name: /Reject Review/i });

    fireEvent.click(approveBtn);

    // Button should be disabled during in-flight call
    expect(approveBtn).toBeDisabled();
    expect(rejectBtn).toBeDisabled();
    expect(screen.getByText(/Executing.../i)).toBeInTheDocument();

    // Resolve call
    resolveApprove({
      action_id: mockPendingAction.action_id,
      status: 'executed',
      reviewed_by: 'demo-agent-001',
    });

    await waitFor(() => {
      expect(screen.getByTestId('action-status-badge')).toHaveTextContent('executed');
    });
  });

  it('submits human rejection with explicit rejection reason (EG-P6-10)', async () => {
    const rejectSpy = vi.spyOn(client, 'rejectAction').mockResolvedValueOnce({
      action_id: mockPendingAction.action_id,
      ticket_id: 'TIK-001',
      action_type: 'start_refund_review',
      status: 'rejected',
      reviewed_by: 'demo-agent-001',
      review_notes: 'Item damaged by customer after delivery.',
    });

    render(
      <ActionApprovalCard
        ticketId="TIK-001"
        orderId="ORD-001"
        action={mockPendingAction}
      />
    );

    // Click Reject Review to open modal
    fireEvent.click(screen.getByRole('button', { name: /Reject Review/i }));

    expect(screen.getByText('Reject Refund Review Recommendation')).toBeInTheDocument();

    // Enter rejection reason
    const reasonInput = screen.getByPlaceholderText(/Ineligible due to customer damage/i);
    fireEvent.change(reasonInput, { target: { value: 'Item damaged by customer after delivery.' } });

    // Confirm
    fireEvent.click(screen.getByRole('button', { name: /Confirm Rejection/i }));

    await waitFor(() => {
      expect(rejectSpy).toHaveBeenCalledWith(mockPendingAction.action_id, {
        reason: 'Item damaged by customer after delivery.',
        notes: null,
      });
      expect(screen.getByTestId('action-status-badge')).toHaveTextContent('rejected');
    });
  });

  it('handles HTTP 409 Conflict when action is already processed (P6-EC-014, EG-P6-11)', async () => {
    vi.spyOn(client, 'approveAction').mockRejectedValueOnce(
      new client.ApiError('Action already processed', 409, 'ACTION_ALREADY_PROCESSED')
    );

    render(
      <ActionApprovalCard
        ticketId="TIK-001"
        orderId="ORD-001"
        action={mockPendingAction}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Approve Review/i }));

    await waitFor(() => {
      expect(
        screen.getByText('This action has already been processed by another agent.')
      ).toBeInTheDocument();
      expect(screen.getByTestId('action-status-badge')).toHaveTextContent('executed');
    });
  });

  it('handles HTTP 422 Business Rule Violation and transitions status to failed (P6-EC-015, EG-P6-11)', async () => {
    vi.spyOn(client, 'approveAction').mockRejectedValueOnce(
      new client.ApiError('Order delivery date missing or outside policy', 422, 'BUSINESS_RULE_VIOLATION')
    );

    render(
      <ActionApprovalCard
        ticketId="TIK-001"
        orderId="ORD-001"
        action={mockPendingAction}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Approve Review/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/Action execution rejected: Order delivery date missing/i)
      ).toBeInTheDocument();
      expect(screen.getByTestId('action-status-badge')).toHaveTextContent('failed');
    });
  });
});

