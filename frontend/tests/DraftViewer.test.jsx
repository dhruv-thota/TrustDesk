import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import DraftViewer from '../src/components/DraftViewer';
import * as client from '../src/api/client';

describe('DraftViewer (EG-P6-06, EG-P6-07, P6-EC-009, P6-EC-010, P6-EC-011, P6-EC-017)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockDraft = {
    ticket_id: 'TIK-001',
    draft_text: 'Dear customer, per KB-REFUND-001 your order delivered on 2026-10-28 is eligible for return within 30 days.',
    has_valid_provenance: true,
    is_grounded: true,
    escalation_suggested: false,
    escalation_reason: null,
    citations: [
      {
        kb_id: 'KB-REFUND-001',
        section_id: 'KB-REFUND-001#sec-1',
        quoted_snippet: 'Items delivered within the last 30 days qualify for refund review.',
        is_valid_provenance: true,
      },
    ],
    suggested_action: {
      action_type: 'start_refund_review',
      should_recommend: true,
      reasoning: 'Customer request falls within verified 30-day return window.',
      payload: { order_id: 'ORD-001' },
    },
  };

  it('renders grounded draft text in display-only container with citation chips (EG-P6-06, EG-P6-07)', async () => {
    vi.spyOn(client, 'generateDraft').mockResolvedValueOnce(mockDraft);

    render(<DraftViewer ticketId="TIK-001" draftResult={null} />);

    fireEvent.click(screen.getByRole('button', { name: /Generate Draft Response/i }));

    expect(screen.getByText(/Generating.../i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('draft-text-container')).toHaveTextContent(mockDraft.draft_text);
      expect(screen.getByTestId('draft-grounded-badge')).toHaveTextContent('✓ Policy Grounded');
      expect(screen.getByTestId('draft-provenance-badge')).toHaveTextContent('Valid Citation Provenance');
      expect(screen.getByTestId('citation-chip')).toHaveTextContent('KB-REFUND-001#sec-1');
    });
  });

  it('expands citation chip to reveal supporting quote snippet on click (EG-P6-07)', () => {
    render(<DraftViewer ticketId="TIK-001" draftResult={mockDraft} />);

    const chip = screen.getByTestId('citation-chip');
    fireEvent.click(chip);

    expect(
      screen.getByText(/"Items delivered within the last 30 days qualify for refund review."/)
    ).toBeInTheDocument();
  });

  it('handles citation with null quoted_snippet safely without throwing or displaying literal null (P6-EC-011)', () => {
    const draftWithNullSnippet = {
      ...mockDraft,
      citations: [
        {
          kb_id: 'KB-REFUND-001',
          section_id: 'KB-REFUND-001#sec-2',
          quoted_snippet: null,
          is_valid_provenance: true,
        },
      ],
    };

    render(<DraftViewer ticketId="TIK-001" draftResult={draftWithNullSnippet} />);

    const chip = screen.getByTestId('citation-chip');
    fireEvent.click(chip);

    expect(screen.getByText('No direct quoted snippet extracted.')).toBeInTheDocument();
  });

  it('renders supervisor review required banner when draft has escalation_suggested=true (P6-EC-010)', () => {
    const ungroundedDraft = {
      ...mockDraft,
      is_grounded: false,
      escalation_suggested: true,
      escalation_reason: 'Order delivered 45 days ago, exceeding 30-day refund window.',
    };

    render(<DraftViewer ticketId="TIK-001" draftResult={ungroundedDraft} />);

    expect(screen.getByTestId('draft-escalation-alert')).toBeInTheDocument();
    expect(
      screen.getByText(/Supervisor Review Required: Insufficient Policy Grounding/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText('Order delivered 45 days ago, exceeding 30-day refund window.')
    ).toBeInTheDocument();
  });

  it('copies draft text to clipboard on Copy to Clipboard click', async () => {
    const writeTextSpy = vi.fn().mockResolvedValueOnce(undefined);
    Object.assign(navigator, {
      clipboard: { writeText: writeTextSpy },
    });

    render(<DraftViewer ticketId="TIK-001" draftResult={mockDraft} />);

    fireEvent.click(screen.getByRole('button', { name: /Copy to Clipboard/i }));

    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalledWith(mockDraft.draft_text);
      expect(screen.getByText(/✓ Copied to Clipboard/i)).toBeInTheDocument();
    });
  });

  it('handles clipboard API failure gracefully with fallback notification (P6-EC-017)', async () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockRejectedValueOnce(new Error('Permission denied')),
      },
    });

    render(<DraftViewer ticketId="TIK-001" draftResult={mockDraft} />);

    fireEvent.click(screen.getByRole('button', { name: /Copy to Clipboard/i }));

    await waitFor(() => {
      expect(
        screen.getByText('Automatic copy unavailable. Please select and copy text manually.')
      ).toBeInTheDocument();
    });
  });

  it('renders error alert with retry button when draft generation fails with 504 Gateway Timeout (P6-EC-009)', async () => {
    vi.spyOn(client, 'generateDraft').mockRejectedValueOnce(
      new Error('The upstream AI provider timed out after 15 seconds.')
    );

    render(<DraftViewer ticketId="TIK-001" draftResult={null} />);

    fireEvent.click(screen.getByRole('button', { name: /Generate Draft Response/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/The upstream AI provider timed out after 15 seconds./i)
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
    });
  });
});

