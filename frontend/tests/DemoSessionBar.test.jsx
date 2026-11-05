import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import DemoSessionBar from '../src/components/DemoSessionBar';
import { getDemoToken, setDemoToken, clearDemoToken } from '../src/api/client';

describe('DemoSessionBar (EG-P6-02, P6-EC-002, P6-EC-003, P6-EC-016)', () => {
  beforeEach(() => {
    clearDemoToken();
  });

  it('displays unauthenticated state when sessionStorage is empty (P6-EC-002)', () => {
    render(<DemoSessionBar />);
    expect(screen.getByText('Unauthenticated')).toBeInTheDocument();
    expect(screen.getByText('Set Demo Token')).toBeInTheDocument();
  });

  it('allows agent to enter and save demo bearer token to sessionStorage (EG-P6-02)', () => {
    const onSessionChange = vi.fn();
    render(<DemoSessionBar onSessionChange={onSessionChange} />);

    // Open token modal
    fireEvent.click(screen.getByText('Set Demo Token'));

    // Input token
    const input = screen.getByLabelText(/Demo Bearer Token/i);
    fireEvent.change(input, { target: { value: 'custom_test_token_456' } });
    fireEvent.click(screen.getByText('Save Token'));

    expect(getDemoToken()).toBe('custom_test_token_456');
    expect(onSessionChange).toHaveBeenCalledWith('custom_test_token_456');
    expect(screen.getByText('Demo Session Active')).toBeInTheDocument();
  });

  it('rehydrates active session token from sessionStorage on mount (P6-EC-016)', () => {
    setDemoToken('persisted_token_789');
    render(<DemoSessionBar />);
    expect(screen.getByText('Demo Session Active')).toBeInTheDocument();
    expect(screen.getByText('Change Token')).toBeInTheDocument();
    expect(screen.getByText('Clear Session')).toBeInTheDocument();
  });

  it('clears session from sessionStorage when Clear Session is clicked', () => {
    setDemoToken('token_to_clear');
    const onSessionChange = vi.fn();
    render(<DemoSessionBar onSessionChange={onSessionChange} />);

    fireEvent.click(screen.getByText('Clear Session'));
    expect(getDemoToken()).toBeNull();
    expect(onSessionChange).toHaveBeenCalledWith(null);
    expect(screen.getByText('Unauthenticated')).toBeInTheDocument();
  });

  it('displays authentication error alert when 401 alert prop is provided (P6-EC-003)', () => {
    render(
      <DemoSessionBar
        authErrorAlert="Authentication failed: Invalid or missing bearer token."
      />
    );
    expect(screen.getByText('Unauthenticated')).toBeInTheDocument();
    expect(
      screen.getByText(/Authentication failed: Invalid or missing bearer token/i)
    ).toBeInTheDocument();
  });
});

