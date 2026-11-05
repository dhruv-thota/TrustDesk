# Phase 6 — Testing & Evaluation Specification: Internal Support-Agent Dashboard

**Document Version:** 1.1.0  
**Phase:** Phase 6 — Internal Support-Agent Dashboard  
**Status:** Verified Post-Implementation Specification  
**Role:** Senior Software Architect, Test Architect & QA Engineer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md) (§3.6)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md) (§3.1, §5.2, §8.5, §12.1–12.3, §13)  
- [docs/implementation_plan.md](file:///Users/dhruv/Desktop/TrustDesk/docs/implementation_plan.md) (§2, §3 Phase 6)  
- [docs/conventions.md](file:///Users/dhruv/Desktop/TrustDesk/docs/conventions.md) (§1.2, §2, §3, §6, §7)  
- [docs/phase6_edgecases.md](file:///Users/dhruv/Desktop/TrustDesk/docs/phase6_edgecases.md) (Phase 6 Anticipated Edge Cases)  
- [docs/unresolved.md](file:///Users/dhruv/Desktop/TrustDesk/docs/unresolved.md) (`U-001`, `U-002`, `U-008`, `U-014`)

---

## A. Phase Evaluation Objective

The objective of Phase 6 evaluation is to objectively verify that:
1. The frontend application builds cleanly without errors or bundle warnings using Vite and Tailwind CSS.
2. The demo bearer token is managed safely in browser session memory (`sessionStorage`) and is never leaked or bundled into static client-side build artifacts.
3. Support agents can browse the ticket queue with status filtering and pagination, rendering ticket metadata, category, and priority badges accurately.
4. Ticket context displays comprehensive customer profile information, itemized order details, and customer past ticket history.
5. AI triage classification can be triggered on demand, displaying structured category, priority, and escalation indicators with fallback state awareness.
6. Policy-grounded draft responses render in a strictly display-only viewer with clear provenance, policy grounding badges, clickable citation chips, and clipboard copy convenience.
7. Clickable policy citation chips maintain complete traceability back to authoritative `kb_id` and `section_id` references.
8. The dashboard discovers and recovers existing proposed actions via `GET /api/v1/tickets/{ticket_id}/actions` (`U-014`), mounting the approval card seamlessly across page refreshes and re-selections.
9. Human approval of `start_refund_review` strictly requires authenticated agent submission, transmits a client-generated `Idempotency-Key`, retains that key across transient retries, and disables multi-click submissions in flight.
10. Human rejection transitions the action to terminal status `rejected` and records agent review notes.
11. Concurrency conflicts (HTTP 409), business eligibility failures (HTTP 422), and backend outages (HTTP 503) are surfaced with explicit, non-crashing visual alerts.
12. All 134 existing automated backend tests across Phases 1–5 plus 5 new `U-014` action-discovery tests (139 total tests) pass with zero regressions.

---

## B. Evaluation Scope

- **Components Under Test:**
  - `frontend/src/App.jsx` (Root layout, master-detail state, global error banner)
  - `frontend/src/api/client.js` (Fetch wrapper, `Authorization` interceptor, error normalizer)
  - `frontend/src/components/DemoSessionBar.jsx` (Demo bearer token input, session indicator, session clear)
  - `frontend/src/components/TicketList.jsx` (Queue table, pagination, status filter)
  - `frontend/src/components/TicketContext.jsx` (Customer profile, order details, SKU table, past tickets)
  - `frontend/src/components/TriagePanel.jsx` (Triage trigger, category/priority badges, escalation notice)
  - `frontend/src/components/DraftViewer.jsx` (Display-only draft text, grounding badges, citation chips, copy button)
  - `frontend/src/components/ActionApprovalCard.jsx` (Payload display, notes input, approve/reject triggers, idempotency key)
  - `trustdesk/api/v1/actions.py` (`GET /api/v1/tickets/{ticket_id}/actions` read-only endpoint under `U-014`)
  - `trustdesk/main.py` (Local Vite CORS scoping)
- **Security & Safety Boundaries Under Test:**
  - Zero hardcoding of `TRUSTDESK_DEMO_TOKEN` in frontend bundle or `.env` files.
  - Prohibition of client-side autonomous execution of actions by AI models.
  - Strict display-only contract for drafts (no client-side draft mutation or backend draft editing CRUD).
  - Client-side button disabling and in-flight loading guards against double-clicks.
  - Preservation of client `Idempotency-Key` across transient network retries.
- **Explicit Exclusions:**
  - No customer-facing chatbot widgets or public portals.
  - No payment gateway integrations or financial fund disbursements.
  - No `create_replacement_order` action.
  - No background queue processing (Redis / RQ) — deferred to Phase 7.
  - No evaluation suite runner UI — deferred to Phase 7 / 8.

---

## C. Test Environment and Execution Strategy

### 1. Test Tooling Stack
- **Unit and Component Testing:** Vitest v2.1.9 + React Testing Library v16.0.1 + jsdom v25.0.1.
- **Mocking Strategy:** `vi.fn()` and `vi.spyOn(client, ...)` for predictable, offline API response mocking.
- **Production Build Verification:** `npm run build` executed against clean frontend workspace.
- **Backend Integration Testing:** pytest against PostgreSQL on port 5433 verifying the new `GET /api/v1/tickets/{ticket_id}/actions` route, CORS preflights, and confirming 139 tests pass.
- **Known Verification Limitation:** Verification relies on Vitest component tests in jsdom and FastAPI backend integration tests. Full live-browser end-to-end testing (e.g. Playwright/Cypress) was not mandated in Phase 6 scope and was not performed.

### 2. Test Suite Organization
- `frontend/tests/DemoSessionBar.test.jsx`: 5 tests.
- `frontend/tests/TicketList.test.jsx`: 5 tests.
- `frontend/tests/TicketContext.test.jsx`: 4 tests.
- `frontend/tests/TriagePanel.test.jsx`: 3 tests.
- `frontend/tests/DraftViewer.test.jsx`: 7 tests.
- `frontend/tests/ActionApprovalCard.test.jsx`: 7 tests.
- `frontend/tests/App.test.jsx`: 3 tests.
- `tests/integration/test_action_approval.py`: 22 backend integration tests (including 5 new Phase 6 tests).

---

## D. Detailed Evaluation Gates

All 12 evaluation gates have been executed and verified.

---

### EG-P6-01: Frontend Clean Production Build
- **Evaluation ID:** `EG-P6-01`
- **Objective:** Verify that the frontend application compiles and bundles cleanly with zero syntax, CSS, or dependency errors.
- **Test Type:** Automated Build Command (`npm run build`)
- **Expected Behavior:** Running `cd frontend && npm run build` exits with code 0, emitting compiled assets into `frontend/dist` without build warnings or chunk errors.
- **Evidence:** Command exited with code 0. `vite v5.4.21 building for production... 38 modules transformed. dist/index.html (0.47 kB), dist/assets/index-*.css (24.69 kB), dist/assets/index-*.js (186.63 kB). Built in 777ms.`
- **Status:** **PASSED**

---

### EG-P6-02: Demo Session Security & Secret Protection
- **Evaluation ID:** `EG-P6-02`
- **Objective:** Verify that the demo bearer token is stored exclusively in `sessionStorage` and is never bundled in static client artifacts.
- **Test Type:** Automated Component Test & Static Bundle Inspection
- **Expected Behavior:** `DemoSessionBar` stores entered tokens in `sessionStorage.getItem('trustdesk_demo_token')`. Bundle inspection (`grep -rn "demo_secret_token_123" frontend/dist/`) returns 0 matches. Static files contain no baked-in secrets.
- **Evidence:** `grep -rn "demo_secret_token_123" frontend/dist/` returned `NO_SECRETS_FOUND`. Component test `allows agent to enter and save demo bearer token to sessionStorage (EG-P6-02)` passed.
- **Status:** **PASSED**

---

### EG-P6-03: Ticket Queue Rendering & Status Filtering
- **Evaluation ID:** `EG-P6-03`
- **Objective:** Verify that the ticket queue table renders ticket records, badges, pagination controls, and responds to status filter selections.
- **Test Type:** Component Test (`frontend/tests/TicketList.test.jsx`)
- **Expected Behavior:** Renders ticket rows matching `TicketListResponseSchema`. Status filter triggers API call with updated `status` query param. Pagination controls update `offset`. Empty queue renders empty placeholder.
- **Evidence:** Tests `renders ticket queue with items, status badges, and total count (EG-P6-03)` and `applies status filter when a filter button is clicked (EG-P6-03)` passed.
- **Status:** **PASSED**

---

### EG-P6-04: Context Panel & Order Details Presentation
- **Evaluation ID:** `EG-P6-04`
- **Objective:** Verify that the context panel presents customer profile data, linked order details, purchased item SKUs, and past ticket history.
- **Test Type:** Component Test (`frontend/tests/TicketContext.test.jsx`)
- **Expected Behavior:** Renders customer name, email, and ID. If order is present, renders order status, date, and SKU items table. If order is `null`, renders "No linked order" banner. Past tickets list renders prior customer tickets cleanly.
- **Evidence:** Test `renders customer profile, order details, SKU table, and past tickets (EG-P6-04)` passed.
- **Status:** **PASSED**

---

### EG-P6-05: AI Triage Execution & Visual Flagging
- **Evaluation ID:** `EG-P6-05`
- **Objective:** Verify that triggering AI triage issues an authenticated POST request and renders category, priority, and escalation alerts accurately.
- **Test Type:** Component Test (`frontend/tests/TriagePanel.test.jsx`)
- **Expected Behavior:** Clicking "Run AI Triage" calls `POST /api/v1/tickets/{id}/triage`. On return, renders category badge, priority badge, reasoning text, and an amber alert if `needs_escalation == true`. If `is_fallback == true`, renders fallback notice.
- **Evidence:** Test `triggers AI triage on button click and renders category, priority, and escalation alert (EG-P6-05)` passed.
- **Status:** **PASSED**

---

### EG-P6-06: Grounded Draft Display & Copy Convenience
- **Evaluation ID:** `EG-P6-06`
- **Objective:** Verify that response drafts render in a display-only container with grounding status badges and a functional clipboard copy button.
- **Test Type:** Component Test (`frontend/tests/DraftViewer.test.jsx`)
- **Expected Behavior:** Clicking "Generate Draft Response" calls `POST /api/v1/tickets/{id}/draft`. Draft text renders in read-only container. If `escalation_suggested == true`, renders supervisor review alert with `escalation_reason`. Clicking "Copy to Clipboard" invokes `navigator.clipboard.writeText` and displays transient "Copied!" feedback.
- **Evidence:** Tests `renders grounded draft text in display-only container with citation chips (EG-P6-06, EG-P6-07)` and `copies draft text to clipboard on Copy to Clipboard click` passed.
- **Status:** **PASSED**

---

### EG-P6-07: Citation Chip Rendering & Traceability
- **Evaluation ID:** `EG-P6-07`
- **Objective:** Verify that policy citations render as clickable chips with original `kb_id` and `section_id` identifiers, supporting quote inspection.
- **Test Type:** Component Test (`frontend/tests/DraftViewer.test.jsx`)
- **Expected Behavior:** Renders citation chips with text `{kb_id}#{section_id}` (e.g. `KB-REFUND-001#sec-1`). Clicking a chip expands the supporting quote snippet. Null snippets are handled cleanly without error.
- **Evidence:** Tests `renders grounded draft text in display-only container with citation chips (EG-P6-06, EG-P6-07)` and `expands citation chip to reveal supporting quote snippet on click (EG-P6-07)` passed.
- **Status:** **PASSED**

---

### EG-P6-08: Action Discovery & Pending-Action Recovery
- **Evaluation ID:** `EG-P6-08`
- **Objective:** Verify that selecting a ticket or refreshing the browser queries `GET /api/v1/tickets/{ticket_id}/actions` and automatically recovers any pending refund review.
- **Test Type:** Integration Component Test (`frontend/tests/App.test.jsx`)
- **Expected Behavior:** Upon ticket selection, frontend issues `GET /api/v1/tickets/{ticket_id}/actions`. If an action with `status == 'pending_approval'` is returned, `ActionApprovalCard` mounts automatically with the active `action_id` and payload, presenting "Approve Review" and "Reject Review" buttons.
- **Evidence:** Test `recovers pending action via Action Discovery upon ticket selection (P6-EC-018, EG-P6-08)` passed.
- **Status:** **PASSED**

---

### EG-P6-09: Human Approval Execution & Idempotency Key Retention
- **Evaluation ID:** `EG-P6-09`
- **Objective:** Verify that approving an action requires human review notes, transmits a client-generated `Idempotency-Key`, retains that key across retries, and disables multi-click submissions.
- **Test Type:** Component Test (`frontend/tests/ActionApprovalCard.test.jsx`)
- **Expected Behavior:** Clicking "Approve Review" sets `isSubmitting: true` (disabling buttons), sends `POST /api/v1/actions/{id}/approve` with mandatory header `Idempotency-Key: <UUID>`. On network failure followed by retry, the identical `Idempotency-Key` is re-sent. On 200 OK, transitions to "Executed" badge.
- **Evidence:** Tests `submits human approval with Idempotency-Key and updates state to executed (EG-P6-09)` and `retains the SAME Idempotency-Key across transient retry attempts (P6-EC-013, EG-P6-09)` passed.
- **Status:** **PASSED**

---

### EG-P6-10: Human Rejection Workflow
- **Evaluation ID:** `EG-P6-10`
- **Objective:** Verify that an agent can reject a pending refund review, providing rejection reason and comments, transitioning the card to "Rejected".
- **Test Type:** Component Test (`frontend/tests/ActionApprovalCard.test.jsx`)
- **Expected Behavior:** Clicking "Reject Review" sends `POST /api/v1/actions/{id}/reject` with reason and notes. On 200 OK, updates status badge to "Rejected" and hides approval/rejection controls.
- **Evidence:** Test `submits human rejection with explicit rejection reason (EG-P6-10)` passed.
- **Status:** **PASSED**

---

### EG-P6-11: Conflict, Error & Offline Safety Presentation
- **Evaluation ID:** `EG-P6-11`
- **Objective:** Verify that backend HTTP 409 Conflict, HTTP 422 Business Failure, and HTTP 503 Server Offline errors are rendered with clear, non-crashing visual alerts.
- **Test Type:** Component Test (`frontend/tests/ActionApprovalCard.test.jsx` & `App.test.jsx`)
- **Expected Behavior:** HTTP 409 displays "Already Processed" alert; HTTP 422 displays "Eligibility Rules Failed" alert; network disconnection displays global top banner with retry button. No unhandled JavaScript exceptions occur.
- **Evidence:** Tests `handles HTTP 409 Conflict when action is already processed (P6-EC-014, EG-P6-11)`, `handles HTTP 422 Business Rule Violation and transitions status to failed (P6-EC-015, EG-P6-11)`, and `renders global offline banner when backend connection fails (P6-EC-001, EG-P6-11)` passed.
- **Status:** **PASSED**

---

### EG-P6-12: Backend Regression & Preserved Semantics
- **Evaluation ID:** `EG-P6-12`
- **Objective:** Verify that introducing the read-only action discovery endpoint (`GET /api/v1/tickets/{ticket_id}/actions`) causes zero regressions in the backend baseline.
- **Test Type:** Backend Integration Test Suite (`.venv/bin/pytest -v`)
- **Expected Behavior:** All 134 existing automated tests in `tests/` pass cleanly without modified assertions or skipped cases, and new unit/integration tests for the action discovery route pass.
- **Evidence:** `.venv/bin/pytest -v` output: 139 passed in 5.51s across all 10 test modules (0 failures, 0 errors).
- **Status:** **PASSED**

---

## E. Evaluation Gate Summary & Traceability Matrix

| Gate ID | Target Verification Area | Primary Component | Verification Tool / Command | Status |
|---|---|---|---|:---:|
| `EG-P6-01` | Production Build Cleanliness | Frontend Bundle | `cd frontend && npm run build` | **PASSED** |
| `EG-P6-02` | Demo Secret Protection | `DemoSessionBar.jsx` | Vitest & `grep` bundle check | **PASSED** |
| `EG-P6-03` | Ticket Queue & Filtering | `TicketList.jsx` | Vitest Component Test | **PASSED** |
| `EG-P6-04` | Context & Order Details | `TicketContext.jsx` | Vitest Component Test | **PASSED** |
| `EG-P6-05` | AI Triage & Visual Badges | `TriagePanel.jsx` | Vitest Component Test | **PASSED** |
| `EG-P6-06` | Grounded Draft Display & Copy | `DraftViewer.jsx` | Vitest Component Test | **PASSED** |
| `EG-P6-07` | Citation Traceability | `DraftViewer.jsx` | Vitest Component Test | **PASSED** |
| `EG-P6-08` | Action Discovery Recovery | `ActionApprovalCard.jsx` | Vitest & Mock Client Test | **PASSED** |
| `EG-P6-09` | Approval & Idempotency Key | `ActionApprovalCard.jsx` | Vitest Component Test | **PASSED** |
| `EG-P6-10` | Rejection Workflow | `ActionApprovalCard.jsx` | Vitest Component Test | **PASSED** |
| `EG-P6-11` | Error & Offline Alerting | `App.jsx`, `ActionCard.jsx` | Vitest Component Test | **PASSED** |
| `EG-P6-12` | Backend Regression (139 Tests)| Backend APIs & Services | `.venv/bin/pytest -v` | **PASSED** |
