import React, { useState, useEffect, useCallback } from 'react';
import DemoSessionBar from './components/DemoSessionBar';
import TicketList from './components/TicketList';
import TicketContext from './components/TicketContext';
import TriagePanel from './components/TriagePanel';
import DraftViewer from './components/DraftViewer';
import ActionApprovalCard from './components/ActionApprovalCard';
import {
  fetchTicketContext,
  fetchTicketActions,
  onAuthError,
  getDemoToken,
} from './api/client';

export default function App() {
  const [selectedTicketId, setSelectedTicketId] = useState(null);
  const [ticketContext, setTicketContext] = useState(null);
  const [ticketAction, setTicketAction] = useState(null);
  const [triageResult, setTriageResult] = useState(null);
  const [draftResult, setDraftResult] = useState(null);

  const [loadingContext, setLoadingContext] = useState(false);
  const [contextError, setContextError] = useState(null);
  const [globalError, setGlobalError] = useState(null);
  const [authErrorAlert, setAuthErrorAlert] = useState(null);
  const [refreshQueueTrigger, setRefreshQueueTrigger] = useState(0);

  // Register 401 Unauthorized listener
  useEffect(() => {
    const unsubscribe = onAuthError(() => {
      setAuthErrorAlert('Authentication failed: Invalid or missing bearer token.');
    });
    return unsubscribe;
  }, []);

  // Load ticket context and discover active actions when a ticket is selected
  const loadTicketData = useCallback(async (ticketId) => {
    if (!ticketId) return;
    setLoadingContext(true);
    setContextError(null);
    setTicketAction(null);
    setTriageResult(null);
    setDraftResult(null);

    try {
      // 1. Fetch Ticket Context
      const ctx = await fetchTicketContext(ticketId);
      setTicketContext(ctx);

      // 2. Discover Existing Proposed Actions (U-014 / P6-EC-018)
      try {
        const actions = await fetchTicketActions(ticketId);
        if (Array.isArray(actions) && actions.length > 0) {
          // Select pending action if exists, otherwise the newest action
          const pending = actions.find((a) => a.status === 'pending_approval');
          setTicketAction(pending || actions[0]);
        } else {
          setTicketAction(null);
        }
      } catch (err) {
        console.warn('Action discovery non-fatal warning:', err);
      }
    } catch (err) {
      if (err.status === 0 || err.code === 'NETWORK_ERROR') {
        setGlobalError('Unable to connect to TrustDesk backend. Check server status.');
      } else {
        setContextError(err.message || 'Failed to load ticket context.');
      }
      setTicketContext(null);
    } finally {
      setLoadingContext(false);
    }
  }, []);

  const handleSelectTicket = (ticketId) => {
    setSelectedTicketId(ticketId);
    loadTicketData(ticketId);
  };

  const handleSessionChange = (newToken) => {
    setAuthErrorAlert(null);
    setGlobalError(null);
    setRefreshQueueTrigger((prev) => prev + 1);
    if (selectedTicketId && newToken) {
      loadTicketData(selectedTicketId);
    }
  };

  const handleProposeFromDraft = (actionRecommendation) => {
    if (!ticketContext?.ticket) return;
    // Set a draft proposal draft in ActionApprovalCard
    setTicketAction({
      action_type: actionRecommendation?.action_type || 'start_refund_review',
      status: 'pending_proposal',
      action_payload: actionRecommendation?.payload || {
        order_id: ticketContext.order?.order_id || null,
        reason: actionRecommendation?.reasoning || 'AI recommended refund review',
      },
    });
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-100 text-slate-900">
      {/* Top Bar with Demo Session Indicator */}
      <DemoSessionBar
        onSessionChange={handleSessionChange}
        authErrorAlert={authErrorAlert}
      />

      {/* Global Server Unreachable Error Banner */}
      {globalError && (
        <div
          data-testid="global-network-error-banner"
          className="bg-rose-600 text-white px-4 py-2.5 text-xs font-semibold flex items-center justify-between shadow-md"
        >
          <div className="flex items-center space-x-2">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-white animate-pulse"></span>
            <span>{globalError}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              setGlobalError(null);
              if (selectedTicketId) loadTicketData(selectedTicketId);
              setRefreshQueueTrigger((p) => p + 1);
            }}
            className="px-2.5 py-1 bg-white text-rose-800 rounded font-bold hover:bg-rose-50 transition"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Main Split-Pane Layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left Column: Ticket Queue (4 cols on lg screens) */}
        <section className="lg:col-span-4 h-[calc(100vh-6rem)] sticky top-4">
          <TicketList
            selectedTicketId={selectedTicketId}
            onSelectTicket={handleSelectTicket}
            refreshTrigger={refreshQueueTrigger}
          />
        </section>

        {/* Right Column: Ticket Workspace (8 cols on lg screens) */}
        <section className="lg:col-span-8 space-y-4">
          {!selectedTicketId ? (
            <div className="bg-white rounded-lg shadow border border-gray-200 p-12 text-center text-gray-500">
              <div className="w-12 h-12 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mx-auto mb-3 text-xl font-bold">
                ✉
              </div>
              <h3 className="text-base font-bold text-gray-800 mb-1">No Ticket Selected</h3>
              <p className="text-xs text-gray-500 max-w-sm mx-auto">
                Select a support ticket from the queue on the left to inspect customer history, run AI triage, review grounded drafts, and manage operational actions.
              </p>
            </div>
          ) : (
            <>
              {/* Context Details Panel */}
              <TicketContext
                context={ticketContext}
                loading={loadingContext}
                error={contextError}
              />

              {/* AI & Operations Panel */}
              {ticketContext && (
                <div className="space-y-4">
                  {/* AI Triage Section */}
                  <TriagePanel
                    ticketId={selectedTicketId}
                    triageResult={triageResult}
                    onTriageComplete={setTriageResult}
                  />

                  {/* Grounded Draft Section */}
                  <DraftViewer
                    ticketId={selectedTicketId}
                    draftResult={draftResult}
                    onDraftComplete={setDraftResult}
                    onProposeAction={handleProposeFromDraft}
                  />

                  {/* Action Approval Card Section */}
                  <ActionApprovalCard
                    ticketId={selectedTicketId}
                    orderId={ticketContext.order?.order_id}
                    action={ticketAction}
                    onActionUpdated={(updated) => {
                      setTicketAction(updated);
                      setRefreshQueueTrigger((p) => p + 1);
                    }}
                  />
                </div>
              )}
            </>
          )}
        </section>
      </main>
    </div>
  );
}

