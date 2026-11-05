import React, { useState, useEffect } from 'react';
import { approveAction, rejectAction, proposeRefundReview } from '../api/client';

export default function ActionApprovalCard({
  ticketId,
  orderId,
  action: initialAction,
  onActionUpdated,
}) {
  const [action, setAction] = useState(initialAction || null);
  const [reviewNotes, setReviewNotes] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorAlert, setErrorAlert] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Stable client-side idempotency key for this action approval lifecycle
  const [idempotencyKey, setIdempotencyKey] = useState(() => {
    return typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `key-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  });

  useEffect(() => {
    setAction(initialAction || null);
    setErrorAlert(null);
    setSuccessMsg(null);
    setShowRejectModal(false);
    // Refresh idempotency key when target action changes
    if (initialAction?.action_id) {
      const newKey = typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `key-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      setIdempotencyKey(newKey);
    }
  }, [initialAction?.action_id, initialAction?.status]);

  const handlePropose = async () => {
    if (!ticketId) return;
    setIsSubmitting(true);
    setErrorAlert(null);
    try {
      const res = await proposeRefundReview(ticketId, {
        payload: {
          order_id: orderId || null,
          reason: 'Agent-initiated refund review inquiry',
        },
        notes: reviewNotes || 'Proposed via Support-Agent Dashboard',
      });
      setAction(res);
      setSuccessMsg('Refund review proposed successfully. Awaiting human authorization.');
      if (onActionUpdated) onActionUpdated(res);
    } catch (err) {
      if (err.status === 409) {
        setErrorAlert('An active or executed refund review already exists for this ticket.');
      } else {
        setErrorAlert(err.message || 'Failed to propose refund review.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleApprove = async () => {
    if (!action?.action_id) return;
    setIsSubmitting(true);
    setErrorAlert(null);
    setSuccessMsg(null);

    try {
      // Send approval with preserved stable idempotencyKey
      const res = await approveAction(
        action.action_id,
        {
          notes: reviewNotes || null,
          parameters: action.action_payload || {},
        },
        idempotencyKey
      );

      const updatedAction = {
        ...action,
        status: res.status || 'executed',
        reviewed_by: res.reviewed_by,
        reviewed_at: res.reviewed_at,
        executed_at: res.executed_at,
      };
      setAction(updatedAction);
      setSuccessMsg('Refund review registered and executed successfully.');
      if (onActionUpdated) onActionUpdated(updatedAction);
    } catch (err) {
      if (err.status === 409) {
        if (err.code === 'ACTION_ALREADY_PROCESSED') {
          setErrorAlert('This action has already been processed by another agent.');
          setAction((prev) => ({ ...prev, status: 'executed' }));
        } else if (err.code === 'IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD') {
          setErrorAlert('Idempotency conflict: key reused with mismatched payload.');
        } else {
          setErrorAlert(err.message || 'Conflict processing action approval.');
        }
      } else if (err.status === 422) {
        setErrorAlert(`Action execution rejected: ${err.message || 'Business eligibility rules failed.'}`);
        setAction((prev) => ({ ...prev, status: 'failed' }));
      } else {
        // Network or server timeout: retain the SAME idempotencyKey for retry!
        setErrorAlert(`${err.message || 'Network failure during approval.'} You may retry without duplicate execution.`);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async (e) => {
    e?.preventDefault();
    if (!action?.action_id) return;
    if (!rejectReason.trim()) {
      setErrorAlert('A rejection reason is required.');
      return;
    }

    setIsSubmitting(true);
    setErrorAlert(null);
    try {
      const res = await rejectAction(action.action_id, {
        reason: rejectReason.trim(),
        notes: reviewNotes || null,
      });
      setAction(res);
      setShowRejectModal(false);
      setSuccessMsg('Refund review recommendation rejected.');
      if (onActionUpdated) onActionUpdated(res);
    } catch (err) {
      if (err.status === 409) {
        setErrorAlert('Action was already processed and cannot be rejected.');
        setAction((prev) => ({ ...prev, status: 'already_processed' }));
      } else {
        setErrorAlert(err.message || 'Failed to reject action.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const isPending = action?.status === 'pending_approval';
  const isExecuted = action?.status === 'executed';
  const isRejected = action?.status === 'rejected';
  const isFailed = action?.status === 'failed';

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200 p-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 pb-2.5 mb-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-rose-500"></span>
          <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider">
            Operational Action Gate
          </h3>
        </div>
        <span className="text-[11px] font-mono text-gray-500">
          start_refund_review only
        </span>
      </div>

      {/* Status Alerts */}
      {errorAlert && (
        <div
          className="p-3 mb-3 text-xs bg-rose-50 border border-rose-200 text-rose-800 rounded font-medium flex items-center justify-between"
          data-testid="action-error-alert"
        >
          <span>{errorAlert}</span>
          <button
            type="button"
            onClick={() => setErrorAlert(null)}
            className="text-xs text-rose-600 hover:text-rose-900 ml-2"
          >
            Dismiss
          </button>
        </div>
      )}

      {successMsg && (
        <div
          className="p-3 mb-3 text-xs bg-emerald-50 border border-emerald-200 text-emerald-800 rounded font-medium"
          data-testid="action-success-alert"
        >
          {successMsg}
        </div>
      )}

      {/* No Action Proposed View */}
      {!action && (
        <div className="text-xs text-gray-600 space-y-3">
          <p className="text-gray-500 bg-gray-50 p-3 rounded border border-dashed border-gray-200 text-center">
            No active refund review proposal for this ticket.
          </p>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={handlePropose}
              disabled={isSubmitting || !ticketId}
              className="px-3 py-1.5 text-xs font-semibold rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50 transition shadow-sm"
            >
              {isSubmitting ? 'Proposing...' : 'Propose Refund Review'}
            </button>
          </div>
        </div>
      )}

      {/* Action Present */}
      {action && (
        <div className="space-y-3 text-xs">
          {/* Action Status Pill */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Status:</span>
              <span
                data-testid="action-status-badge"
                className={`px-2.5 py-0.5 rounded font-bold uppercase text-[11px] ${
                  isPending
                    ? 'bg-amber-100 text-amber-900 border border-amber-300 animate-pulse'
                    : isExecuted
                    ? 'bg-emerald-100 text-emerald-900 border border-emerald-300'
                    : isRejected
                    ? 'bg-rose-100 text-rose-900 border border-rose-300'
                    : 'bg-red-100 text-red-900 border border-red-300'
                }`}
              >
                {action.status}
              </span>
            </div>
            <span className="text-[11px] font-mono text-gray-500">
              ID: {action.action_id}
            </span>
          </div>

          {/* Action Details Card */}
          <div className="bg-gray-50 border border-gray-200 rounded p-3 space-y-1.5 text-gray-800">
            <div className="flex justify-between">
              <span className="text-gray-500">Action Type:</span>
              <span className="font-semibold text-gray-900">{action.action_type}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Proposed By:</span>
              <span className="capitalize font-medium text-gray-800">{action.proposed_by || 'agent'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Proposed At:</span>
              <span className="text-gray-700">
                {action.created_at ? new Date(action.created_at).toLocaleString() : '—'}
              </span>
            </div>
            {action.reviewed_by && (
              <div className="flex justify-between">
                <span className="text-gray-500">Reviewed By:</span>
                <span className="font-semibold text-gray-900">{action.reviewed_by}</span>
              </div>
            )}
            {action.reviewed_at && (
              <div className="flex justify-between">
                <span className="text-gray-500">Reviewed At:</span>
                <span className="text-gray-700">{new Date(action.reviewed_at).toLocaleString()}</span>
              </div>
            )}
            {action.executed_at && (
              <div className="flex justify-between">
                <span className="text-gray-500">Executed At:</span>
                <span className="text-gray-700">{new Date(action.executed_at).toLocaleString()}</span>
              </div>
            )}

            {/* Action Payload Inspection */}
            {action.action_payload && Object.keys(action.action_payload).length > 0 && (
              <div className="mt-2 pt-2 border-t border-gray-200">
                <span className="font-semibold text-gray-700 block mb-1">Action Payload Parameters:</span>
                <pre
                  data-testid="action-payload-preview"
                  className="bg-slate-900 text-slate-100 p-2 rounded text-[11px] overflow-x-auto font-mono"
                >
                  {JSON.stringify(action.action_payload, null, 2)}
                </pre>
              </div>
            )}

            {action.review_notes && (
              <div className="mt-2 pt-2 border-t border-gray-200 text-gray-700">
                <span className="font-semibold text-gray-900 block mb-0.5">Review Notes:</span>
                <p className="italic bg-white p-2 rounded border border-gray-200">{action.review_notes}</p>
              </div>
            )}
          </div>

          {/* Action Approval Controls (Only for pending_approval) */}
          {isPending && (
            <div className="space-y-3 pt-2">
              <div>
                <label htmlFor="agent-notes-input" className="block font-semibold text-gray-700 mb-1">
                  Human Agent Reviewer Notes:
                </label>
                <input
                  id="agent-notes-input"
                  type="text"
                  placeholder="Optional review notes or decision justification..."
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  disabled={isSubmitting}
                  className="w-full px-3 py-1.5 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              <div className="flex items-center justify-between gap-3 pt-1">
                <span className="text-[11px] text-gray-500 font-mono">
                  Key: {idempotencyKey.substring(0, 12)}...
                </span>

                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    onClick={() => setShowRejectModal(true)}
                    disabled={isSubmitting}
                    className="px-3 py-1.5 text-xs font-semibold rounded bg-rose-600 hover:bg-rose-500 text-white disabled:opacity-50 transition shadow-sm"
                  >
                    Reject Review
                  </button>

                  <button
                    type="button"
                    onClick={handleApprove}
                    disabled={isSubmitting}
                    className="px-3 py-1.5 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 transition shadow-sm flex items-center gap-1.5"
                  >
                    {isSubmitting ? (
                      <>
                        <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                        Executing...
                      </>
                    ) : (
                      'Approve Review'
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Terminal State Notices */}
          {isExecuted && (
            <div className="p-3 bg-emerald-50 border-l-4 border-emerald-500 text-emerald-900 rounded-r text-xs">
              <strong>Formal Review Registered:</strong> Operational refund review has been executed in support records. Direct payments or monetary disbursements are not performed by TrustDesk.
            </div>
          )}

          {isRejected && (
            <div className="p-3 bg-rose-50 border-l-4 border-rose-500 text-rose-900 rounded-r text-xs">
              <strong>Recommendation Rejected:</strong> The review request was declined by the agent. Under system rules, a new proposal may be created if customer circumstances change.
            </div>
          )}

          {isFailed && (
            <div className="p-3 bg-red-50 border-l-4 border-red-500 text-red-900 rounded-r text-xs">
              <strong>Execution Failed:</strong> Downstream business rule evaluation rejected the review. The failure record is preserved for audit.
            </div>
          )}
        </div>
      )}

      {/* Reject Reason Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-5 text-xs space-y-3">
            <h4 className="text-sm font-bold text-gray-900 border-b border-gray-100 pb-2">
              Reject Refund Review Recommendation
            </h4>
            <p className="text-gray-600">
              Please enter an explicit reason for declining this refund-review recommendation:
            </p>
            <textarea
              rows={3}
              placeholder="e.g. Ineligible due to customer damage, order outside window, or requested by mistake..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="w-full p-2 border border-gray-300 rounded focus:ring-1 focus:ring-rose-500 focus:outline-none"
            />
            <div className="flex justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setShowRejectModal(false)}
                className="px-3 py-1.5 rounded bg-gray-100 text-gray-700 hover:bg-gray-200 font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleReject}
                disabled={isSubmitting || !rejectReason.trim()}
                className="px-3 py-1.5 rounded bg-rose-600 hover:bg-rose-500 text-white font-semibold disabled:opacity-50"
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

