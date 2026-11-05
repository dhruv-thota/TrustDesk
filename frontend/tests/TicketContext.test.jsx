import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import TicketContext from '../src/components/TicketContext';

describe('TicketContext (EG-P6-04, P6-EC-005, P6-EC-006, P6-EC-007)', () => {
  const mockContext = {
    ticket: {
      ticket_id: 'TIK-001',
      customer_id: 'CUST-001',
      order_id: 'ORD-001',
      subject: 'Damaged item received in shipment',
      message: 'The package arrived ripped open and the screen is cracked.',
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
      total_amount: 149.99,
      items: [
        { sku: 'SKU-001', name: 'Wireless Monitor', qty: 1, price: 149.99 },
      ],
    },
    past_tickets: [
      {
        ticket_id: 'TIK-000',
        customer_id: 'CUST-001',
        subject: 'Previous inquiry regarding delivery estimate',
        status: 'closed',
        created_at: '2026-05-10T11:00:00Z',
      },
    ],
  };

  it('renders customer profile, order details, SKU table, and past tickets (EG-P6-04)', () => {
    render(<TicketContext context={mockContext} loading={false} error={null} />);

    // Ticket header & message
    expect(screen.getByText('TIK-001')).toBeInTheDocument();
    expect(screen.getByText('Damaged item received in shipment')).toBeInTheDocument();
    expect(
      screen.getByText('The package arrived ripped open and the screen is cracked.')
    ).toBeInTheDocument();

    // Customer profile
    expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();

    // Order details & items
    expect(screen.getByText('ORD-001')).toBeInTheDocument();
    expect(screen.getByText('Wireless Monitor')).toBeInTheDocument();
    expect(screen.getAllByText('$149.99').length).toBeGreaterThanOrEqual(1);

    // Past tickets
    expect(screen.getByText('TIK-000')).toBeInTheDocument();
    expect(
      screen.getByText('Previous inquiry regarding delivery estimate')
    ).toBeInTheDocument();
  });

  it('renders "No Order Linked to Ticket" gracefully when order is null (P6-EC-005)', () => {
    const unlinkedContext = {
      ...mockContext,
      ticket: { ...mockContext.ticket, order_id: null },
      order: null,
    };

    render(<TicketContext context={unlinkedContext} loading={false} error={null} />);

    expect(screen.getByTestId('no-order-linked')).toBeInTheDocument();
    expect(screen.getByText('No Order Linked to Ticket')).toBeInTheDocument();
  });

  it('renders quarantined order reference banner when raw_metadata contains unresolved_order_id (P6-EC-006)', () => {
    const quarantinedContext = {
      ...mockContext,
      ticket: {
        ...mockContext.ticket,
        order_id: null,
        raw_metadata: { unresolved_order_id: 'ORD-NONEXISTENT-999' },
      },
      order: null,
    };

    render(<TicketContext context={quarantinedContext} loading={false} error={null} />);

    const notice = screen.getByTestId('quarantined-order-notice');
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveTextContent('ORD-NONEXISTENT-999');
    expect(notice).toHaveTextContent('Quarantined Order Reference:');
  });

  it('renders empty past tickets message when customer has no past tickets (P6-EC-007)', () => {
    const singleTicketContext = {
      ...mockContext,
      past_tickets: [],
    };

    render(<TicketContext context={singleTicketContext} loading={false} error={null} />);

    expect(screen.getByTestId('empty-past-tickets')).toBeInTheDocument();
    expect(
      screen.getByText('No previous support tickets for this customer.')
    ).toBeInTheDocument();
  });
});
