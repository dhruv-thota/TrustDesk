# Phase 6 — Edge Cases & Failure Scenarios: Internal Support-Agent Dashboard

**Document Version:** 1.1.0  
**Phase:** Phase 6 — Internal Support-Agent Dashboard  
**Status:** Verified Post-Implementation Specification  
**Role:** Senior Software Architect, Test Architect & QA Engineer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md) (§3.6)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md) (§3.1, §5.2, §8.5, §12.1–12.3, §13)  
- [docs/implementation_plan.md](file:///Users/dhruv/Desktop/TrustDesk/docs/implementation_plan.md) (§2, §3 Phase 6)  
- [docs/conventions.md](file:///Users/dhruv/Desktop/TrustDesk/docs/conventions.md) (§1.2, §2, §3, §6, §7)  
- [docs/unresolved.md](file:///Users/dhruv/Desktop/TrustDesk/docs/unresolved.md) (`U-001`, `U-002`, `U-008`, `U-014`)

---

## A. Phase Overview

- **Phase Number & Name:** Phase 6 — Internal Support-Agent Dashboard
- **Objective:** Construct the minimal, robust internal support-agent web dashboard using React, Vite, and Tailwind CSS. The dashboard provides authenticated support agents with ticket queue browsing, customer and order context inspection, on-demand AI triage classification, display-only grounded draft and citation review with clipboard copy, human-governed approval/rejection of `start_refund_review` recommendations, and discovery/recovery of existing proposed actions across browser sessions.
- **Relevant Implementation Plan Sections:** `docs/implementation_plan.md` §3 (Phase 6)
- **Dependencies:** Phase 1 complete (relational database and schema persistence); Phase 2 complete (authenticated ticket and context APIs); Phase 3 complete (knowledge base FTS policy retrieval); Phase 4 complete (AI triage and cited grounded draft generation); Phase 5 complete (action approval, row locking, persistent idempotency, and uniqueness constraints); `U-014` approved and implemented (action discovery route `GET /api/v1/tickets/{ticket_id}/actions`).
- **Scope Boundaries:**
  - *Included:* Vite + React setup in `frontend/`; Tailwind CSS styling; `DemoSessionBar` for local bearer token entry and `sessionStorage` persistence; `TicketList` queue table with status filtering and pagination; `TicketContext` displaying customer profile, order details, purchased items, and customer ticket history; `TriagePanel` for triggering and viewing AI triage; `DraftViewer` for display-only draft presentation, policy citation chips, grounding badges, and clipboard copy; `ActionApprovalCard` for reviewing payload, entering human notes, submitting approval with client-generated `Idempotency-Key`, or submitting rejection; read-only backend endpoint `GET /api/v1/tickets/{ticket_id}/actions` for action discovery (`U-014`); Vitest + React Testing Library component tests.
  - *Excluded:* No customer-facing chatbot widgets; no payment gateway integration or monetary fund transfers; no `create_replacement_order` action; no autonomous action execution by AI; no draft editing / WYSIWYG CRUD endpoints; no agent-to-agent internal chat; no production OAuth2/JWT RBAC platform (deferred to post-MVP `U-012`); no evaluation results dashboard (deferred to Phase 7/8).
- **Related Resolved Decision IDs:**
  - `U-001`: Refund-Review Business-Operation Uniqueness Scoped to `(ticket_id, action_type)`.
  - `U-002`: Draft Grounding & Validation Result Semantics (3-Level verification).
  - `U-008`: Sensitive-Action Approval and Failure Retry Contract.
  - `U-014`: Active Action Discovery on Ticket Context via `GET /api/v1/tickets/{ticket_id}/actions`.

---

## B. Pre-Implementation Anticipated Edge Cases

The following 18 edge cases and failure scenarios were derived from the authoritative problem statement, architecture specification, implementation plan, and approved Phase 6 decisions. All 18 cases have been implemented and verified.

---

### P6-EC-001: Backend API Service Unreachable / Network Offline
- **ID:** `P6-EC-001`
- **Title:** Backend Server Is Offline, Crashing, or Network Connection Fails
- **Category:** Network Resilience / Global Error Handling
- **Precondition:** Support agent opens dashboard in browser while backend server is stopped or unreachable.
- **Trigger/Input:** Any API call issued by the frontend (`client.js`) fails with network error or returns HTTP 503 (`DATABASE_UNAVAILABLE`).
- **Expected Behavior:** Dashboard displays a persistent, global notification banner: *"Unable to connect to TrustDesk backend. Check server status."* with a "Retry Connection" button. The application does not crash into an unhandled white-screen or React rendering boundary failure.
- **Forbidden Behavior:** Unhandled JavaScript Promise rejection freezing the UI, displaying empty broken cards without explanation, or leaking stack traces.
- **Verification Method:** Mock network rejection in API client tests and verify global error banner renders cleanly.
- **Related Requirement:** `docs/implementation_plan.md` §6.F.1; `docs/architecture.md` §3.1
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `renders global offline banner when backend connection fails (P6-EC-001, EG-P6-11)` in `frontend/tests/App.test.jsx`)

---

### P6-EC-002: Unauthenticated Agent Session / Missing Bearer Token
- **ID:** `P6-EC-002`
- **Title:** User Attempts Protected Actions Without Setting Demo Bearer Token
- **Category:** Authentication / Session Safety
- **Precondition:** `sessionStorage` contains no `trustdesk_demo_token` (e.g., initial clean session).
- **Trigger/Input:** User accesses dashboard views or attempts to browse tickets.
- **Expected Behavior:** `DemoSessionBar` prominently indicates "Unauthenticated" status and opens a modal prompting the user to enter the demo bearer token. Protected action triggers ("Run AI Triage", "Generate Draft", "Approve", "Reject") remain disabled or prompt authentication before dispatching HTTP calls.
- **Forbidden Behavior:** Dispatching requests with `Authorization: Bearer undefined` or `Bearer null`, or failing silently.
- **Verification Method:** Vitest component test asserting disabled buttons and session prompt when `sessionStorage` is empty.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.2, §6.F.2; `docs/architecture.md` §9.1
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `displays unauthenticated state when sessionStorage is empty (P6-EC-002)` in `frontend/tests/DemoSessionBar.test.jsx`)

---

### P6-EC-003: Invalid Bearer Token Submitted (HTTP 401 Unauthorized)
- **ID:** `P6-EC-003`
- **Title:** API Rejects Bearer Token as Invalid or Malformed
- **Category:** Authentication / Security Handling
- **Precondition:** An invalid or mistyped token is entered in `DemoSessionBar` and stored in `sessionStorage`.
- **Trigger/Input:** Any authenticated API endpoint returns HTTP 401 with error code `UNAUTHORIZED`.
- **Expected Behavior:** API client intercepts the 401 response, clears the invalid token from `sessionStorage`, updates `DemoSessionBar` state to unauthenticated, and presents a visual alert: *"Authentication failed: Invalid or missing bearer token."*
- **Forbidden Behavior:** Retrying the 401 request in an infinite loop, or silently keeping the invalid token in storage.
- **Verification Method:** Mock 401 response in API client test and verify token eviction and alert presentation.
- **Related Requirement:** `docs/implementation_plan.md` §6.F.2; `docs/architecture.md` §9.1
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `displays authentication error alert when 401 alert prop is provided (P6-EC-003)` in `frontend/tests/DemoSessionBar.test.jsx`)

---

### P6-EC-004: Empty Ticket Queue / Filter Returns Zero Matches
- **ID:** `P6-EC-004`
- **Title:** Ticket Queue Returns Empty Item List for Current Filter
- **Category:** UI Layout / Empty State Presentation
- **Precondition:** Backend database contains no tickets matching the applied status filter (e.g., `status=closed` when all are `open`).
- **Trigger/Input:** `GET /api/v1/tickets?status=closed` returns `TicketListResponseSchema` with `items: []`, `total: 0`.
- **Expected Behavior:** `TicketList` renders a clean, accessible empty-state placeholder: *"No tickets match the selected status filter."* along with a "Clear Filter" action button. Pagination controls are disabled or hidden.
- **Forbidden Behavior:** Crashing on `.map()` over undefined items, displaying a blank white box, or endless loading spinner.
- **Verification Method:** Component test rendering `TicketList` with `items: []` and asserting empty state message.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.3.a, §6.C.4
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `renders clean empty state with Clear Filter button when queue returns 0 records (P6-EC-004)` in `frontend/tests/TicketList.test.jsx`)

---

### P6-EC-005: Ticket with Null / Unlinked Order
- **ID:** `P6-EC-005`
- **Title:** Support Ticket Contains No Associated Order Reference
- **Category:** Data Presentation / Context Handling
- **Precondition:** Ticket was ingested with `order_id: null` (general inquiry or pre-order ticket).
- **Trigger/Input:** Agent selects ticket; `GET /api/v1/tickets/{id}/context` returns `order: null`.
- **Expected Behavior:** `TicketContext` displays customer details cleanly and displays an informational card in the order section: *"No Order Linked to Ticket"*.
- **Forbidden Behavior:** JavaScript TypeError attempting to read properties of `null` (`order.items`), or rendering broken empty order cards.
- **Verification Method:** Component test rendering `TicketContext` with `order: null` and verifying graceful fallback display.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.3.b; `docs/architecture.md` §4.1
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `renders "No Order Linked to Ticket" gracefully when order is null (P6-EC-005)` in `frontend/tests/TicketContext.test.jsx`)

---

### P6-EC-006: Ticket with Quarantined / Unresolvable Order Reference
- **ID:** `P6-EC-006`
- **Title:** Ticket Has Raw Unresolvable Order Reference Preserved in Metadata
- **Category:** Data Integrity / Defensive Display
- **Precondition:** Ticket was ingested with an invalid non-null order ID, preserved in `raw_metadata["unresolved_order_id"] = "ORD-MISSING-..."` with relational `order_id = null`.
- **Trigger/Input:** Agent inspects ticket context; `order` is `null`, but `ticket.raw_metadata` contains `unresolved_order_id`.
- **Expected Behavior:** `TicketContext` renders order status banner: *"Quarantined Order Reference: ORD-MISSING-... (Unresolvable in order database)"*, informing the agent that the customer mentioned an order identifier not found in the primary database.
- **Forbidden Behavior:** Silently discarding the quarantined identifier or fabricating an order record.
- **Verification Method:** Component test rendering context with `ticket.raw_metadata.unresolved_order_id` present.
- **Related Requirement:** `docs/architecture.md` §4.1, §4.3; `docs/unresolved.md` `U-003`
- **Unresolved Dependencies:** None (`U-003` resolved).
- **Verification Status:** **PASSED** (Verified via `renders quarantined order reference banner when raw_metadata contains unresolved_order_id (P6-EC-006)` in `frontend/tests/TicketContext.test.jsx`)

---

### P6-EC-007: Customer with Single Ticket History (Empty Past Tickets)
- **ID:** `P6-EC-007`
- **Title:** Customer Has No Prior Tickets Beyond the Active Selected Ticket
- **Category:** Context Presentation / Boundary Condition
- **Precondition:** Selected ticket is the first and only ticket submitted by the customer.
- **Trigger/Input:** `GET /api/v1/tickets/{id}/context` returns `past_tickets: []`.
- **Expected Behavior:** `TicketContext` history panel displays: *"No previous support tickets for this customer."* Active ticket is not duplicated inside the history section.
- **Forbidden Behavior:** Crashing on past tickets render, or listing the current active ticket inside past tickets.
- **Verification Method:** Component test asserting empty history message when `past_tickets` is empty list.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.3.b
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `renders empty past tickets message when customer has no past tickets (P6-EC-007)` in `frontend/tests/TicketContext.test.jsx`)

---

### P6-EC-008: AI Triage Provider Failure / Fallback Result
- **ID:** `P6-EC-008`
- **Title:** AI Triage Upstream Service Fails and Backend Returns Fallback Classification
- **Category:** AI Resilience / Visual Flagging
- **Precondition:** Upstream LLM provider times out or returns malformed data during triage; backend applies deterministic fallback.
- **Trigger/Input:** `POST /api/v1/tickets/{id}/triage` returns `TriageResultSchema` with `is_fallback: true`, `category: "general"`, `priority: "medium"`, `needs_escalation: true`.
- **Expected Behavior:** `TriagePanel` renders the classification badges accompanied by a distinct amber warning badge: *"Automated Triage Unavailable (System Fallback Applied)"* along with the recorded reasoning.
- **Forbidden Behavior:** Displaying the fallback as a confident AI classification without visual distinction.
- **Verification Method:** Component test rendering triage result with `is_fallback: true` and asserting warning banner visibility.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.3.c; `docs/architecture.md` §7.4
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `renders prominent fallback alert when is_fallback is true (P6-EC-008)` in `frontend/tests/TriagePanel.test.jsx`)

---

### P6-EC-009: Grounded Draft Generation Timeout / Upstream Provider Error
- **ID:** `P6-EC-009`
- **Title:** Upstream Provider Times Out (HTTP 504) or Returns Provider Error (HTTP 502)
- **Category:** AI Resilience / Error Presentation
- **Precondition:** Agent clicks "Generate Draft Response". Upstream AI provider hangs (>15s) or returns an unrecoverable failure.
- **Trigger/Input:** `POST /api/v1/tickets/{id}/draft` returns HTTP 504 Gateway Timeout or HTTP 502 Bad Gateway.
- **Expected Behavior:** `DraftViewer` stops the loading spinner, preserves the existing ticket context without clearing UI, and displays an inline error alert: *"The upstream AI provider timed out after 15 seconds."* with a "Retry" button.
- **Forbidden Behavior:** Infinite loading spinner, freezing the browser tab, or unhandled HTTP error crashing the ticket view.
- **Verification Method:** Mock 504 Gateway Timeout response in `DraftViewer` test and assert error alert and retry button.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.4; `docs/architecture.md` §7.1
- **Unresolved Dependencies:** None (`U-006` resolved).
- **Verification Status:** **PASSED** (Verified via `renders error alert with retry button when draft generation fails with 504 Gateway Timeout (P6-EC-009)` in `frontend/tests/DraftViewer.test.jsx`)

---

### P6-EC-010: Response Draft with Ungrounded Evidence / Escalation Flagged
- **ID:** `P6-EC-010`
- **Title:** Draft Generated with Missing Policy Evidence or Date Inconsistency
- **Category:** Grounding Visibility / Safety Gate
- **Precondition:** Ticket inquiry involves unretrieved policies, unresolvable delivery dates, or expired return windows.
- **Trigger/Input:** `POST /api/v1/tickets/{id}/draft` returns `DraftResponseSchema` with `is_grounded: false`, `escalation_suggested: true`, `escalation_reason: "Order delivered 45 days ago, exceeding 30-day refund window."`.
- **Expected Behavior:** `DraftViewer` renders the draft text with a prominent amber alert banner: *"Supervisor Review Required: Insufficient Policy Grounding"*, displaying `escalation_reason` directly below the banner. Grounding badge shows "⚠ Ungrounded / Unverified".
- **Forbidden Behavior:** Displaying the draft with a green "Grounded" badge, or omitting the supervisor review escalation warning.
- **Verification Method:** Component test rendering draft with `escalation_suggested: true` and asserting escalation alert presence.
- **Related Requirement:** `docs/implementation_plan.md` §6.F.3; `docs/architecture.md` §6.5; `docs/unresolved.md` `U-002`
- **Unresolved Dependencies:** None (`U-002` resolved).
- **Verification Status:** **PASSED** (Verified via `renders supervisor review required banner when draft has escalation_suggested=true (P6-EC-010)` in `frontend/tests/DraftViewer.test.jsx`)

---

### P6-EC-011: Citation Chips with Null or Missing Quoted Snippets
- **ID:** `P6-EC-011`
- **Title:** Generated Citation References Policy Section but Contains No Supporting Snippet
- **Category:** Citation Traceability / Defensive Rendering
- **Precondition:** AI draft includes a valid citation where `quoted_snippet: null` or empty string.
- **Trigger/Input:** `DraftCitationSchema` has `kb_id: "KB-REFUND-001"`, `section_id: "KB-REFUND-001#sec-2"`, `quoted_snippet: null`.
- **Expected Behavior:** Citation chip renders `KB-REFUND-001#sec-2` cleanly. Clicking displays policy reference badge without rendering broken, blank, or literal `null` snippet text, falling back to: *"No direct quoted snippet extracted."*
- **Forbidden Behavior:** Displaying literal text `"null"`, `"undefined"`, or throwing an exception when expanding chip details.
- **Verification Method:** Component test rendering citation chips with `quoted_snippet: null`.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.3.d; `docs/schemas/draft.py`
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `handles citation with null quoted_snippet safely without throwing or displaying literal null (P6-EC-011)` in `frontend/tests/DraftViewer.test.jsx`)

---

### P6-EC-012: Double-Click Prevention on Action Approval Submission
- **ID:** `P6-EC-012`
- **Title:** Rapid Multiple Clicks on "Approve Review" Button
- **Category:** Concurrency Defense / Frontend Debouncing
- **Precondition:** Action card is in `pending_approval` state.
- **Trigger/Input:** Agent rapidly clicks "Approve Review" multiple times in quick succession.
- **Expected Behavior:** Action button immediately enters disabled state (`isSubmitting: true`) upon the first click, displaying a loading spinner. Subsequent clicks are ignored by the browser. Only a single HTTP POST request is dispatched to `/api/v1/actions/{id}/approve`.
- **Forbidden Behavior:** Dispatching multiple concurrent HTTP requests from the client.
- **Verification Method:** Vitest simulation triggering double-clicks and verifying that `fetch` is invoked exactly once.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.4, §6.G; `docs/phase5_edgecases.md` `P5-EC-001`
- **Unresolved Dependencies:** None (`U-001`, `U-008` resolved).
- **Verification Status:** **PASSED** (Verified via `disables action buttons while submission is in-flight to prevent multi-clicks (P6-EC-012)` in `frontend/tests/ActionApprovalCard.test.jsx`)

---

### P6-EC-013: Retrying Approval with Stable Idempotency Key Replay
- **ID:** `P6-EC-013`
- **Title:** Transient Network Dropout Followed by User Retry Preserves Idempotency Key
- **Category:** Idempotency Protection / Retry Safety
- **Precondition:** Agent clicks "Approve Review"; request reaches backend and executes, but network connection drops before HTTP 200 response reaches browser.
- **Trigger/Input:** UI presents error notice that retry will not duplicate execution; agent clicks "Approve Review" again. The client resends `POST /api/v1/actions/{id}/approve` with the **identical** `Idempotency-Key` and payload.
- **Expected Behavior:** Backend returns cached HTTP 200 OK (`ActionExecutionResultSchema`). The UI receives the completed response, marks status as "Executed", and displays execution details without duplicate processing.
- **Forbidden Behavior:** Generating a new `Idempotency-Key` on retry, which would trigger HTTP 409 Conflict (`ACTION_ALREADY_PROCESSED`).
- **Verification Method:** Mock initial network error followed by successful 200 replay with identical key in component test.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.3.e; `docs/architecture.md` §8.5; `docs/unresolved.md` `U-008`
- **Unresolved Dependencies:** None (`U-008` resolved).
- **Verification Status:** **PASSED** (Verified via `retains the SAME Idempotency-Key across transient retry attempts (P6-EC-013, EG-P6-09)` in `frontend/tests/ActionApprovalCard.test.jsx`)

---

### P6-EC-014: Approval Submission Conflict on Terminal Action (HTTP 409)
- **ID:** `P6-EC-014`
- **Title:** Action Already Processed by Another Agent or Window
- **Category:** State Synchronization / Concurrency Alerting
- **Precondition:** Action in view was executed or rejected in another tab or by another agent.
- **Trigger/Input:** Current agent submits approval with a fresh key; backend returns HTTP 409 Conflict with `ACTION_ALREADY_PROCESSED`.
- **Expected Behavior:** `ActionApprovalCard` catches HTTP 409, halts submission, disables approval/rejection controls, updates status badge to "Executed" (terminal state), and displays warning: *"This action has already been processed by another agent."*
- **Forbidden Behavior:** Leaving the approval button enabled, or reporting an unhandled 500 error.
- **Verification Method:** Mock HTTP 409 response on approval call and assert status update and warning message.
- **Related Requirement:** `docs/implementation_plan.md` §6.F.4; `docs/architecture.md` §8.5; `docs/unresolved.md` `U-008`
- **Unresolved Dependencies:** None (`U-008` resolved).
- **Verification Status:** **PASSED** (Verified via `handles HTTP 409 Conflict when action is already processed (P6-EC-014, EG-P6-11)` in `frontend/tests/ActionApprovalCard.test.jsx`)

---

### P6-EC-015: Business Rule Violation During Approval Execution (HTTP 422)
- **ID:** `P6-EC-015`
- **Title:** Action Fails Downstream Business Validation and Commits Failed State
- **Category:** Error Presentation / Audit State Representation
- **Precondition:** Action was pending, but backend business evaluation rejects execution (e.g., missing delivery date or unlinked order).
- **Trigger/Input:** `POST /api/v1/actions/{id}/approve` returns HTTP 422 with `BUSINESS_RULE_VIOLATION`.
- **Expected Behavior:** Action card catches 422, transitions displayed status to "Failed", disables approval button, and displays red error banner: *"Action execution rejected: Business eligibility rules failed."*
- **Forbidden Behavior:** Leaving action in "pending" status or reporting generic internal server error.
- **Verification Method:** Mock HTTP 422 response in component test and assert status transition to "Failed".
- **Related Requirement:** `docs/implementation_plan.md` §6.C.4; `docs/architecture.md` §8.5; `docs/unresolved.md` `U-008`
- **Unresolved Dependencies:** None (`U-008` resolved).
- **Verification Status:** **PASSED** (Verified via `handles HTTP 422 Business Rule Violation and transitions status to failed (P6-EC-015, EG-P6-11)` in `frontend/tests/ActionApprovalCard.test.jsx`)

---

### P6-EC-016: Browser Session Token Retention Across Page Reloads
- **ID:** `P6-EC-016`
- **Title:** Agent Refreshes Browser Tab During Active Support Session
- **Category:** Session Safety / State Persistence
- **Precondition:** Agent has entered demo token in `DemoSessionBar`, stored in `sessionStorage`.
- **Trigger/Input:** Agent presses browser reload (F5 / Cmd+R).
- **Expected Behavior:** On component mount, `client.js` and `DemoSessionBar` read `trustdesk_demo_token` from `sessionStorage`. The session remains authenticated without forcing the agent to re-enter the token.
- **Forbidden Behavior:** Losing authentication on refresh, or migrating token to `localStorage` (violating session-only scope).
- **Verification Method:** Component test verifying token hydration from `sessionStorage` on initial render.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.2, §6.G; `docs/architecture.md` §9.1
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `rehydrates active session token from sessionStorage on mount (P6-EC-016)` in `frontend/tests/DemoSessionBar.test.jsx`)

---

### P6-EC-017: Clipboard Copy API Blocked or Denied
- **ID:** `P6-EC-017`
- **Title:** Browser Clipboard API Is Unavailable or Permission Denied
- **Category:** UX Fallback / Browser API Compatibility
- **Precondition:** Browser environment restricts `navigator.clipboard.writeText` (e.g. non-HTTPS iframe or denied permission).
- **Trigger/Input:** Agent clicks "Copy to Clipboard" in `DraftViewer`.
- **Expected Behavior:** The application handles the Promise rejection gracefully and displays a transient notice: *"Automatic copy unavailable. Please select and copy text manually."* No unhandled exception is thrown.
- **Forbidden Behavior:** Unhandled Promise rejection crashing the UI or showing broken "Copied!" confirmation badge when copy actually failed.
- **Verification Method:** Mock rejected `navigator.clipboard.writeText` in component test and assert graceful error notification.
- **Related Requirement:** `docs/implementation_plan.md` §6.C.3.d
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `handles clipboard API failure gracefully with fallback notification (P6-EC-017)` in `frontend/tests/DraftViewer.test.jsx`)

---

### P6-EC-018: Recovery of Previously Pending Action via Action Discovery
- **ID:** `P6-EC-018`
- **Title:** Agent Selects Ticket or Refreshes Page Where an Action Was Already Proposed
- **Category:** Action Discovery / State Synchronization
- **Precondition:** An action was previously proposed for a ticket (status `pending_approval`), but the current browser session does not have `action_id` in local component memory (e.g. page refresh, different browser tab, or another agent created it).
- **Trigger/Input:** Agent selects ticket; frontend invokes `GET /api/v1/tickets/{ticket_id}/actions` (`U-014`).
- **Expected Behavior:** Backend returns `list[ProposedActionSchema]`. The frontend identifies the active action with `status == 'pending_approval'`, automatically mounts `ActionApprovalCard` populated with the existing `action_id`, payload, and proposed timestamp, and presents the "Approve Review" and "Reject Review" buttons.
- **Forbidden Behavior:** Failing to discover the pending action, forcing the agent to click "Propose Refund Review" and receiving an unexplained HTTP 409 Conflict (`ACTIVE_REVIEW_ALREADY_EXISTS`) with no way to approve the existing action.
- **Verification Method:** Integration test verifying that selecting a ticket with an existing pending action automatically renders the populated `ActionApprovalCard` with valid `action_id`.
- **Related Requirement:** `docs/unresolved.md` `U-014`; `docs/architecture.md` §12.3; `docs/implementation_plan.md` §6.C.3.e
- **Unresolved Dependencies:** None (`U-014` resolved).
- **Verification Status:** **PASSED** (Verified via `recovers pending action via Action Discovery upon ticket selection (P6-EC-018, EG-P6-08)` in `frontend/tests/App.test.jsx`)

---

## C. Implementation-Discovered Edge Cases

**Zero genuine application-level edge cases were discovered.**

*Note on test-suite DOM matching:* During component test development, an internal query refinement occurred in `frontend/tests/TicketContext.test.jsx` because the quarantined order reference label and ID were rendered in distinct text nodes inside a container (`<strong>Quarantined Order Reference:</strong> {id}`). Testing with container-level matching (`toHaveTextContent`) verified the rendering. As this was a standard testing-library query pattern rather than an application defect or user-facing anomaly, it is not classified as an application edge case.

---

## D. Edge Case Summary & Traceability Matrix

| Case ID | Core Concern | Target Component | Primary Guard / Mechanism | Status |
|---|---|---|---|:---:|
| `P6-EC-001` | Server Offline / Network Down | `App.jsx`, `client.js` | Global error banner & retry trigger | **PASSED** |
| `P6-EC-002` | Missing Demo Token | `DemoSessionBar.jsx` | `sessionStorage` guard & disabled actions | **PASSED** |
| `P6-EC-003` | 401 Unauthorized Response | `client.js`, `DemoSessionBar.jsx` | Auto-evict token & alert modal | **PASSED** |
| `P6-EC-004` | Empty Ticket Queue | `TicketList.jsx` | Empty placeholder banner & reset filter | **PASSED** |
| `P6-EC-005` | Unlinked Order (`order: null`) | `TicketContext.jsx` | "No linked order" informational card | **PASSED** |
| `P6-EC-006` | Quarantined Order Reference | `TicketContext.jsx` | Quarantined reference banner from metadata | **PASSED** |
| `P6-EC-007` | Single Ticket Customer | `TicketContext.jsx` | "No previous tickets" placeholder | **PASSED** |
| `P6-EC-008` | AI Triage Fallback | `TriagePanel.jsx` | Visual "Fallback Applied" badge | **PASSED** |
| `P6-EC-009` | Draft Provider Timeout (504/502)| `DraftViewer.jsx` | Inline error banner & retry button | **PASSED** |
| `P6-EC-010` | Ungrounded Draft Escalation | `DraftViewer.jsx` | Amber supervisor review warning banner | **PASSED** |
| `P6-EC-011` | Null Citation Snippet | `DraftViewer.jsx` | Safe rendering of `kb_id#sec-id` chip | **PASSED** |
| `P6-EC-012` | Double-Click Prevention | `ActionApprovalCard.jsx` | Button disable (`isSubmitting: true`) | **PASSED** |
| `P6-EC-013` | Stable Idempotency Key Replay | `ActionApprovalCard.jsx`, `client.js`| Retained `Idempotency-Key` across retries | **PASSED** |
| `P6-EC-014` | 409 Conflict on Stale Action | `ActionApprovalCard.jsx` | Terminal status transition & conflict alert | **PASSED** |
| `P6-EC-015` | 422 Business Rule Failure | `ActionApprovalCard.jsx` | Terminal status transition to "Failed" | **PASSED** |
| `P6-EC-016` | Tab Refresh State Loss | `DemoSessionBar.jsx`, `client.js` | Hydrate token from `sessionStorage` | **PASSED** |
| `P6-EC-017` | Clipboard API Failure | `DraftViewer.jsx` | Graceful fallback notice to manual copy | **PASSED** |
| `P6-EC-018` | Pending Action Recovery | `ActionApprovalCard.jsx`, `client.js`| `GET /tickets/{id}/actions` discovery | **PASSED** |
