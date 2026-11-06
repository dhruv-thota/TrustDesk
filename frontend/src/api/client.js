/**
 * TrustDesk API Client
 *
 * Enforces safe demo session bearer token authentication from sessionStorage,
 * standardized JSON error unwrapping, and dynamic header attachments.
 */

const SESSION_TOKEN_KEY = 'trustdesk_demo_token';
const DEFAULT_API_BASE = 'http://localhost:8000/api/v1';

export class ApiError extends Error {
  constructor(message, status = 0, code = 'UNKNOWN_ERROR', details = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let authErrorListeners = [];

export function onAuthError(listener) {
  authErrorListeners.push(listener);
  return () => {
    authErrorListeners = authErrorListeners.filter(l => l !== listener);
  };
}

function notifyAuthError() {
  authErrorListeners.forEach(fn => {
    try {
      fn();
    } catch (e) {
      console.error('Auth error listener failed:', e);
    }
  });
}

export function getDemoToken() {
  if (typeof window === 'undefined' || !window.sessionStorage) return null;
  return window.sessionStorage.getItem(SESSION_TOKEN_KEY);
}

export function setDemoToken(token) {
  if (typeof window === 'undefined' || !window.sessionStorage) return;
  if (!token) {
    window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
  } else {
    window.sessionStorage.setItem(SESSION_TOKEN_KEY, token.trim());
  }
}

export function clearDemoToken() {
  if (typeof window === 'undefined' || !window.sessionStorage) return;
  window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
}

export function getApiBaseUrl() {
  if (typeof process !== 'undefined' && process.env?.VITE_API_BASE_URL) {
    return process.env.VITE_API_BASE_URL;
  }
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  return DEFAULT_API_BASE;
}

export async function apiRequest(endpoint, options = {}) {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
  const token = getDemoToken();

  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      clearDemoToken();
      notifyAuthError();
      const errorData = await response.json().catch(() => ({}));
      const code = errorData?.error?.code || 'UNAUTHORIZED';
      const msg = errorData?.error?.message || 'Invalid or missing bearer token.';
      throw new ApiError(msg, 401, code, errorData?.error?.details || {});
    }

    if (!response.ok) {
      let errorData = null;
      try {
        errorData = await response.json();
      } catch {
        errorData = { error: { message: response.statusText || 'Request failed' } };
      }
      const code = errorData?.error?.code || 'HTTP_ERROR';
      const msg = errorData?.error?.message || `Request failed with status ${response.status}`;
      const details = errorData?.error?.details || {};
      throw new ApiError(msg, response.status, code, details);
    }

    if (response.status === 204) {
      return null;
    }

    return await response.json();
  } catch (err) {
    if (err instanceof ApiError) {
      throw err;
    }
    // Network or server unreachable failure
    throw new ApiError(
      'Unable to connect to TrustDesk backend. Check server status.',
      0,
      'NETWORK_ERROR',
      { originalError: err.message }
    );
  }
}

// API Endpoints

export async function fetchTickets({ status = null, customer_id = null, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (customer_id) params.set('customer_id', customer_id);
  if (limit) params.set('limit', String(limit));
  if (offset !== undefined) params.set('offset', String(offset));

  const query = params.toString() ? `?${params.toString()}` : '';
  return apiRequest(`/tickets${query}`, { method: 'GET' });
}

export async function fetchTicketContext(ticketId) {
  return apiRequest(`/tickets/${encodeURIComponent(ticketId)}/context`, { method: 'GET' });
}

export async function fetchTicketActions(ticketId) {
  return apiRequest(`/tickets/${encodeURIComponent(ticketId)}/actions`, { method: 'GET' });
}

export async function runTriage(ticketId) {
  return apiRequest(`/tickets/${encodeURIComponent(ticketId)}/triage`, { method: 'POST' });
}

export async function generateDraft(ticketId) {
  return apiRequest(`/tickets/${encodeURIComponent(ticketId)}/draft`, { method: 'POST' });
}

export async function proposeRefundReview(ticketId, { payload = {}, notes = null } = {}) {
  return apiRequest(`/tickets/${encodeURIComponent(ticketId)}/actions/refund-review/propose`, {
    method: 'POST',
    body: JSON.stringify({
      action_type: 'start_refund_review',
      payload,
      notes,
    }),
  });
}

export async function approveAction(actionId, { notes = null, parameters = {} } = {}, idempotencyKey) {
  if (!idempotencyKey) {
    throw new ApiError('Idempotency-Key is mandatory for action approval.', 422, 'MISSING_IDEMPOTENCY_KEY');
  }
  return apiRequest(`/actions/${encodeURIComponent(actionId)}/approve`, {
    method: 'POST',
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify({
      notes,
      parameters,
    }),
  });
}

export async function rejectAction(actionId, { reason = null, notes = null } = {}) {
  return apiRequest(`/actions/${encodeURIComponent(actionId)}/reject`, {
    method: 'POST',
    body: JSON.stringify({
      reason,
      notes,
    }),
  });
}

// Phase 7 Evaluation Endpoints

export async function runEvaluation(datasetPath = './data/eval_cases.jsonl') {
  return apiRequest('/evaluations/run', {
    method: 'POST',
    body: JSON.stringify({
      dataset_path: datasetPath,
    }),
  });
}

export async function fetchJobStatus(jobId) {
  return apiRequest(`/jobs/${encodeURIComponent(jobId)}`, {
    method: 'GET',
  });
}

export async function fetchEvaluations({ limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (limit) params.set('limit', String(limit));
  if (offset !== undefined) params.set('offset', String(offset));

  const query = params.toString() ? `?${params.toString()}` : '';
  return apiRequest(`/evaluations${query}`, {
    method: 'GET',
  });
}

export async function fetchEvaluationDetail(runId) {
  return apiRequest(`/evaluations/${encodeURIComponent(runId)}`, {
    method: 'GET',
  });
}


