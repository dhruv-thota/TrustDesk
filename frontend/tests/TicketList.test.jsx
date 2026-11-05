import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import TicketList from '../src/components/TicketList';
import * as client from '../src/api/client';

describe('TicketList (EG-P6-03, P6-EC-004)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockTickets = [
    {
      ticket_id: 'TIK-001',
      customer_id: 'CUST-001',
      subject: 'Damaged item received in shipment',
      status: 'open',
      created_at: '2026-11-01T10:00:00Z',
    },
    {
      ticket_id: 'TIK-002',
      customer_id: 'CUST-002',
      subject: 'Request refund for unopened item',
      status: 'pending',
      created_at: '2026-11-02T14:30:00Z',
    },
  ];

  it('renders ticket queue with items, status badges, and total count (EG-P6-03)', async () => {
    vi.spyOn(client, 'fetchTickets').mockResolvedValueOnce({
      items: mockTickets,
      total: 2,
      limit: 10,
      offset: 0,
    });

    render(<TicketList onSelectTicket={vi.fn()} />);

    expect(screen.getByText(/Loading tickets.../i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('TIK-001')).toBeInTheDocument();
      expect(screen.getByText('TIK-002')).toBeInTheDocument();
      expect(screen.getByText('Damaged item received in shipment')).toBeInTheDocument();
      expect(screen.getByText('(2 total)')).toBeInTheDocument();
    });
  });

  it('triggers onSelectTicket callback when a ticket row is clicked', async () => {
    vi.spyOn(client, 'fetchTickets').mockResolvedValueOnce({
      items: mockTickets,
      total: 2,
      limit: 10,
      offset: 0,
    });

    const onSelectTicket = vi.fn();
    render(<TicketList onSelectTicket={onSelectTicket} />);

    await waitFor(() => {
      expect(screen.getByText('TIK-001')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Damaged item received in shipment'));
    expect(onSelectTicket).toHaveBeenCalledWith('TIK-001');
  });

  it('applies status filter when a filter button is clicked (EG-P6-03)', async () => {
    const fetchSpy = vi.spyOn(client, 'fetchTickets').mockResolvedValue({
      items: [mockTickets[0]],
      total: 1,
      limit: 10,
      offset: 0,
    });

    render(<TicketList onSelectTicket={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('TIK-001')).toBeInTheDocument();
    });

    // Click 'Open' status filter button
    fireEvent.click(screen.getByRole('button', { name: /^Open$/i }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'open' })
      );
    });
  });

  it('renders clean empty state with Clear Filter button when queue returns 0 records (P6-EC-004)', async () => {
    vi.spyOn(client, 'fetchTickets').mockResolvedValueOnce({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
    });

    render(<TicketList onSelectTicket={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByTestId('empty-ticket-state')).toBeInTheDocument();
      expect(
        screen.getByText('No tickets match the selected status filter.')
      ).toBeInTheDocument();
    });
  });

  it('displays error message and retry button when fetchTickets fails', async () => {
    vi.spyOn(client, 'fetchTickets').mockRejectedValueOnce(
      new Error('Failed to load tickets from server')
    );

    render(<TicketList onSelectTicket={vi.fn()} />);

    await waitFor(() => {
      expect(
        screen.getByText('Failed to load tickets from server')
      ).toBeInTheDocument();
      expect(screen.getByText('Try again')).toBeInTheDocument();
    });
  });
});

