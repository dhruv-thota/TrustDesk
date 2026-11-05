import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from '../src/App';
import * as client from '../src/api/client';

describe('App Dashboard (EG-P6-08, EG-P6-11, P6-EC-001, P6-EC-018)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockTickets = [
    {
      ticket_id: 'TIK-001',
      customer_id: 'CUST-001',
      subject: 'Damaged item inquiry',
      status: 'open',
      created_at: '2026-11-01T10:00:00Z',
    },
  ];

  const mockContext = {
    ticket: {
      ticket_id: 'TIK-001',
      customer_id: 'CUST-001',
      order_id: 'ORD-001',
      subject: 'Damaged item inquiry',
      message: 'Item arrived damaged.',
      status: 'open',
      created_at: '2026-11-01T10:00:00Z',
      raw_metadata: {},
    },
    customer: {
      customer_id: 'CUST-001',
      name: 'Alice Johnson',
      email: 'alice@example.com',
      created_at: '2025-01-15T09:00:00Z',
    },
    order: {
      order_id: 'ORD-001',
      customer_id: 'CUST-001',
      order_date: '2026-10-25T14:00:00Z',
      delivery_date: '2026-10-28T16:00:00Z',
      status: 'delivered',
      total_amount: 99.99,
      items: [],
    },
    past_tickets: [],
  };

  const mockDiscoveredAction = {
    action_id: 'discovered-action-uuid-123',
    ticket_id: 'TIK-001',
    action_type: 'start_refund_review',
    status: 'pending_approval',
    proposed_by: 'ai',
    created_at: '2026-11-04T10:00:00Z',
    action_payload: { order_id: 'ORD-001', reason: 'Discovered pending review' },
  };

  it('renders "No Ticket Selected" placeholder initially', async () => {
    vi.spyOn(client, 'fetchTickets').mockResolvedValueOnce({
      items: mockTickets,
      total: 1,
      limit: 10,
      offset: 0,
    });

    render(<App />);

    expect(screen.getByText('No Ticket Selected')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('TIK-001')).toBeInTheDocument();
    });
  });

  it('recovers pending action via Action Discovery upon ticket selection (P6-EC-018, EG-P6-08)', async () => {
    vi.spyOn(client, 'fetchTickets').mockResolvedValueOnce({
      items: mockTickets,
      total: 1,
      limit: 10,
      offset: 0,
    });
    vi.spyOn(client, 'fetchTicketContext').mockResolvedValueOnce(mockContext);
    const discoverySpy = vi
      .spyOn(client, 'fetchTicketActions')
      .mockResolvedValueOnce([mockDiscoveredAction]);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('TIK-001')).toBeInTheDocument();
    });

    // Select ticket
    fireEvent.click(screen.getByText('Damaged item inquiry'));

    await waitFor(() => {
      expect(discoverySpy).toHaveBeenCalledWith('TIK-001');
      // ActionApprovalCard mounted automatically with recovered pending action!
      expect(screen.getByText('ID: discovered-action-uuid-123')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Approve Review/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Reject Review/i })).toBeInTheDocument();
    });
  });

  it('renders global offline banner when backend connection fails (P6-EC-001, EG-P6-11)', async () => {
    vi.spyOn(client, 'fetchTickets').mockResolvedValueOnce({
      items: mockTickets,
      total: 1,
      limit: 10,
      offset: 0,
    });
    vi.spyOn(client, 'fetchTicketContext').mockRejectedValueOnce(
      new client.ApiError('Server offline', 0, 'NETWORK_ERROR')
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('TIK-001')).toBeInTheDocument();
    });

    // Select ticket
    fireEvent.click(screen.getByText('Damaged item inquiry'));

    await waitFor(() => {
      expect(screen.getByTestId('global-network-error-banner')).toBeInTheDocument();
      expect(
        screen.getByText(/Unable to connect to TrustDesk backend. Check server status./i)
      ).toBeInTheDocument();
    });
  });
});

