# Phase 5 — Testing & Evaluation Specification: Guardrails and Human-Approved Refund Review

**Document Version:** 1.1.0  
**Phase:** Phase 5 — Guardrails and Human-Approved Refund Review  
**Status:** Verified Post-Implementation Specification  
**Role:** Senior Software Architect, Test Architect & QA Engineer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md) (§3.5, §3.7)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md) (§4.3, §5.3, §5.4, §8.5, §9.1–9.2, §11)  
- [docs/implementation_plan.md](file:///Users/dhruv/Desktop/TrustDesk/docs/implementation_plan.md) (§2, §3 Phase 5)  
- [docs/phase5_edgecases.md](file:///Users/dhruv/Desktop/TrustDesk/docs/phase5_edgecases.md) (Phase 5 Edge Cases)  
- [docs/conventions.md](file:///Users/dhruv/Desktop/TrustDesk/docs/conventions.md) (§1.2, §2, §3, §6, §7)  
- [docs/unresolved.md](file:///Users/dhruv/Desktop/TrustDesk/docs/unresolved.md) (`U-001`, `U-008`)

---

## A. Phase Evaluation Objective

The objective of Phase 5 evaluation is to objectively verify that:
1. Operational action proposals persist with canonical status `pending_approval` linked to valid support tickets.
2. Action execution strictly requires authenticated human approval; AI advisory recommendations have zero autonomous execution rights.
3. The approver identity (`reviewed_by`) is stamped exclusively from server-verified session credentials, preventing client-supplied identity forgery.
4. Human rejection transitions the action to canonical terminal status `rejected` and records decision notes.
5. Persistent request idempotency guarantees that identical-key replays return cached responses with zero duplicate execution side effects.
6. Key reuse with tampered payloads or targeting a different action ID is detected and rejected with HTTP 409 Conflict.
7. Business-operation uniqueness is strictly enforced via PostgreSQL partial unique index `idx_unique_active_refund_review`, preventing multiple active reviews per ticket.
8. Concurrent approval requests serialize safely using PostgreSQL row-level locks (`SELECT ... FOR UPDATE`), preventing race conditions.
9. Confirmed business validation failures commit status `failed` to PostgreSQL to preserve an immutable audit trail while returning HTTP 422.
10. Transient database errors roll back cleanly, preserving `pending_approval` for a subsequent retry.
11. Prompt injection attacks (including `KB-ADVERSARIAL-001`) cannot bypass approval gates or trigger autonomous actions.
12. All 107 existing Phase 1–4 regression tests continue to pass without weakened assertions (134 total tests passing).

---

## B. Evaluation Scope

- **Components Under Test:**
  - `trustdesk/models/action.py` (`ProposedAction`, `ActionIdempotency` models)
  - `trustdesk/schemas/action.py` (Pydantic proposal, approval, rejection, and idempotency schemas)
  - `trustdesk/services/action_service.py` (Action lifecycle orchestration, row locks, idempotency, failure commit)
  - `trustdesk/api/v1/actions.py` (`POST /propose`, `POST /approve`, `POST /reject`)
  - `alembic/versions/004_create_phase5_action_tables.py` (DDL migration, foreign keys, partial unique index)
  - `trustdesk/core/security.py` (`verify_demo_token` identity binding)
  - `trustdesk/tools/catalog.py` (Tool scope enforcement)
- **Database Operations Under Test:**
  - Forward and downgrade migration execution for `proposed_actions` and `action_idempotency`.
  - Transactional serialization using `SELECT ... FOR UPDATE`.
  - Enforcement of partial unique index `idx_unique_active_refund_review`.
  - Discrete transaction commits for failure audit preservation vs. rollback for transient errors.
- **Security & Safety Boundaries Under Test:**
  - Prohibition of autonomous execution by LLM models.
  - Strict scope limitation: `start_refund_review` is the only supported operational action; payments and replacement orders are prohibited.
  - Prohibition of client-supplied approver identity spoofing (`X-Agent-ID`).
  - Resistance to prompt injection and policy-override instructions.
- **Explicit Exclusions:**
  - No payment gateway integrations, monetary calculations, or fund disbursements.
  - No asynchronous background queue processing (Redis / RQ) — deferred to Phase 7.
  - No frontend UI dashboard — deferred to Phase 6.

---

## C. Test Environment and Execution Strategy

### 1. Mandatory Real PostgreSQL Integration Testing
Per approved conventions and `U-010`, all concurrency, row-locking, and partial-unique-index tests execute against a containerized PostgreSQL 15+ database running on host port 5433 (via `docker-compose.yml`).
- Concurrency tests launch multithreaded workers issuing simultaneous HTTP requests to verify row serialization under actual PostgreSQL lock contention.
- Partial unique indexes are enforced directly by the PostgreSQL relational engine.

### 2. Test Suite Organization
- `tests/unit/test_action_schemas.py`: 4 unit tests verifying proposal schema constraints, unsupported action rejection, and canonical request hashing.
- `tests/integration/test_action_approval.py`: 17 integration tests verifying proposal, approval, rejection, idempotency replay, payload tampering, business failure commits, DB rollbacks, and identity binding.
- `tests/integration/test_concurrency.py`: 3 multithreaded integration tests verifying double-approval serialization and proposal deduplication.
- `tests/adversarial/test_guardrails.py`: 3 adversarial tests verifying prompt injection inertness (`KB-ADVERSARIAL-001`) and unsupported action blocking.

---

## D. Detailed Evaluation Gates

---

### EG-P5-01: Action Proposal Creation
- **Evaluation ID:** `EG-P5-01`
- **Objective:** Verify that proposing a refund review creates an action record with status `pending_approval`.
- **Test Type:** Integration Test (`tests/integration/test_action_approval.py`)
- **Expected Behavior:** `POST /api/v1/tickets/{ticket_id}/actions/refund-review/propose` with valid authentication returns HTTP 201 Created and response matching `ProposedActionSchema`. A database record is inserted in `proposed_actions` with `status = 'pending_approval'`, `action_type = 'start_refund_review'`, and `ticket_id` matching the request.
- **Evidence Required:** Database inspection query verifying row inserted with correct status and foreign key.
- **Dependencies:** Migration `004`, `ProposedAction` model.
- **Status:** **PASSED** (Verified via `test_propose_refund_review_success` in `tests/integration/test_action_approval.py`)

---

### EG-P5-02: Authenticated Human Approval Execution
- **Evaluation ID:** `EG-P5-02`
- **Objective:** Verify that an authenticated agent can approve a pending action, transitioning it to `executed`.
- **Test Type:** Integration Test (`tests/integration/test_action_approval.py`)
- **Expected Behavior:** `POST /api/v1/actions/{action_id}/approve` with valid token and `Idempotency-Key` returns HTTP 200 OK with `ActionExecutionResultSchema`. `proposed_actions.status` updates to `executed`; `reviewed_by` is stamped with server-verified `demo-agent-001`; `reviewed_at` and `executed_at` timestamps are populated; `action_idempotency` records `status = 'completed'` with cached response payload; `execution_traces` records an audit entry with `final_status = 'success'`.
- **Evidence Required:** Database inspection asserting action status `executed`, `reviewed_by == 'demo-agent-001'`, idempotency record `completed`, and trace record present.
- **Dependencies:** `verify_demo_token`, `action_service`.
- **Status:** **PASSED** (Verified via `test_approve_action_success` in `tests/integration/test_action_approval.py`)

---

### EG-P5-03: Authenticated Human Rejection
- **Evaluation ID:** `EG-P5-03`
- **Objective:** Verify that an authenticated agent can reject a pending action, transitioning it to terminal `rejected`.
- **Test Type:** Integration Test (`tests/integration/test_action_approval.py`)
- **Expected Behavior:** `POST /api/v1/actions/{action_id}/reject` with valid token returns HTTP 200 OK. `proposed_actions.status` transitions to `rejected`; `reviewed_by` is stamped with server-verified `demo-agent-001`; `review_notes` records human comments; `reviewed_at` is populated; `executed_at` remains NULL.
- **Evidence Required:** Database inspection asserting row status `rejected` and null `executed_at`.
- **Dependencies:** `verify_demo_token`, `action_service`.
- **Status:** **PASSED** (Verified via `test_reject_action_success` in `tests/integration/test_action_approval.py`)

---

### EG-P5-04: Identical-Key Idempotent Replay
- **Evaluation ID:** `EG-P5-04`
- **Objective:** Verify that replaying an approval request with an existing idempotency key and matching payload returns the cached result without duplicate execution.
- **Test Type:** Integration Test (`tests/integration/test_action_approval.py`)
- **Expected Behavior:** A second `POST /api/v1/actions/{action_id}/approve` request with the same `Idempotency-Key` and matching body returns HTTP 200 OK with the exact cached response payload. Database records show no changes to `executed_at` timestamp and no duplicate execution trace rows.
- **Evidence Required:** Assert HTTP 200 response body matches original response; assert execution trace count for the action equals 1.
- **Dependencies:** `ActionIdempotency` caching logic.
- **Status:** **PASSED** (Verified via `test_approve_action_idempotent_replay` in `tests/integration/test_action_approval.py`)

---

### EG-P5-05: Terminal Action Re-Approval Conflict
- **Evaluation ID:** `EG-P5-05`
- **Objective:** Verify that attempting to approve an already-executed or already-rejected action with a fresh key is rejected.
- **Test Type:** Integration Test (`tests/integration/test_action_approval.py`)
- **Expected Behavior:** Calling `POST /api/v1/actions/{action_id}/approve` on an action whose status is `executed`, `rejected`, or `failed` using a fresh `Idempotency-Key` aborts the transaction and returns HTTP 409 Conflict with standard error code `ACTION_ALREADY_PROCESSED`.
- **Evidence Required:** Assert HTTP 409 status code and `ACTION_ALREADY_PROCESSED` error code.
- **Dependencies:** State validation under row lock.
- **Status:** **PASSED** (Verified via `test_approve_action_already_processed_with_new_key` and `test_approve_attempt_on_failed_action_conflict` in `tests/integration/test_action_approval.py`)

---

### EG-P5-06: Idempotency Key Reuse with Tampered Payload
- **ID:** `EG-P5-06`
- **Objective:** Verify that reusing an idempotency key with different payload parameters or targeting a different action is detected and rejected.
- **Test Type:** Integration Test (`tests/integration/test_action_approval.py`)
- **Expected Behavior:** Submitting an approval request with an existing `Idempotency-Key` but altered body parameters or a different `action_id` detects a `request_hash` mismatch. The service aborts the transaction and returns HTTP 409 Conflict with error code `IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD`.
- **Evidence Required:** Assert HTTP 409 status code and `IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD` error code.
- **Dependencies:** Request SHA256 hashing.
- **Status:** **PASSED** (Verified via `test_approve_action_key_reuse_with_different_payload_conflict` in `tests/integration/test_action_approval.py`)

---

### EG-P5-07: Business-Operation Uniqueness Enforcement
- **Evaluation ID:** `EG-P5-07`
- **Objective:** Verify that the PostgreSQL partial unique index prevents multiple active refund reviews for the same ticket.
- **Test Type:** Integration Test (`tests/integration/test_action_approval.py` & `tests/integration/test_concurrency.py`)
- **Expected Behavior:** When a ticket has an existing action with status `pending_approval` or `executed`, any attempt to call `POST /api/v1/tickets/{ticket_id}/actions/refund-review/propose` triggers a unique constraint violation and returns HTTP 409 Conflict with error code `ACTIVE_REVIEW_ALREADY_EXISTS`.
- **Evidence Required:** Assert HTTP 409 on second proposal call; assert `proposed_actions` count for ticket equals 1.
- **Dependencies:** `idx_unique_active_refund_review` partial unique index.
- **Status:** **PASSED** (Verified via `test_propose_duplicate_active_refund_review_rejected` in `tests/integration/test_action_approval.py` and `test_concurrent_proposals_on_same_ticket` in `tests/integration/test_concurrency.py`)

---

### EG-P5-08: Concurrent Double-Approval Serialization
- **Evaluation ID:** `EG-P5-08`
- **Objective:** Verify that concurrent approval requests are serialized cleanly without race conditions.
- **Test Type:** Integration Test (`tests/integration/test_concurrency.py`)
- **Expected Behavior:** When two simultaneous approval requests are issued using multithreaded workers for the same action:
  - If sharing the same `Idempotency-Key`: one executes successfully, and the other returns cached replay; exactly one execution occurs.
  - If using different `Idempotency-Key`s: one commits `executed`, and the other receives HTTP 409 Conflict (`ACTION_ALREADY_PROCESSED`).
  Zero database deadlocks, zero unhandled 500 errors, and zero duplicate execution traces.
- **Evidence Required:** Verification against running PostgreSQL 15+ container with concurrent async workers asserting single commit.
- **Dependencies:** PostgreSQL `SELECT ... FOR UPDATE` row locking.
- **Status:** **PASSED** (Verified via `test_concurrent_double_approval_same_idempotency_key` and `test_concurrent_approval_different_idempotency_keys` in `tests/integration/test_concurrency.py`)

---

### EG-P5-09: Confirmed Business Failure Audit Preservation
- **Evaluation ID:** `EG-P5-09`
- **Objective:** Verify that business execution failures commit status `failed` to preserve the audit trail while returning HTTP 422.
- **Test Type:** Integration Test (`tests/integration/test_action_approval.py`)
- **Expected Behavior:** If business rule validation fails during execution (e.g., simulated failure or invalid parameters), the service updates `proposed_actions.status = 'failed'`, records failure diagnostics, commits the transaction to PostgreSQL, and returns HTTP 422 Unprocessable Entity with standard error contract (`BUSINESS_RULE_VIOLATION`).
- **Evidence Required:** Database query verifying `status == 'failed'` committed in `proposed_actions` and audit trace persisted in `execution_traces`.
- **Dependencies:** Transactional commit-on-failure logic.
- **Status:** **PASSED** (Verified via `test_approve_action_business_failure_commits_failed_state` in `tests/integration/test_action_approval.py`)

---

### EG-P5-10: Transient Database Crash Rollback
- **Evaluation ID:** `EG-P5-10`
- **Objective:** Verify that transient database exceptions cause a clean rollback, leaving the action in `pending_approval`.
- **Test Type:** Integration Test (`tests/integration/test_action_approval.py`)
- **Expected Behavior:** When a transient database operational error or connection termination occurs before commit, SQLAlchemy rolls back the transaction. The database row remains in `pending_approval` with null timestamps, allowing a subsequent retry to proceed.
- **Evidence Required:** Database inspection verifying row retains `pending_approval` after simulated operational exception.
- **Dependencies:** SQLAlchemy transaction rollback semantics.
- **Status:** **PASSED** (Verified via `test_transient_db_error_rolls_back_to_pending_approval` in `tests/integration/test_action_approval.py`)

---

### EG-P5-11: Prompt Injection Adversarial Gate
- **Evaluation ID:** `EG-P5-11`
- **Objective:** Verify that adversarial prompt injection cannot bypass the human approval gate or trigger automated actions.
- **Test Type:** Adversarial Integration Test (`tests/adversarial/test_guardrails.py`)
- **Expected Behavior:** Submitting tickets containing injection directives from `KB-ADVERSARIAL-001` or raw prompt injection text generates advisory drafts and recommendations, but **never** triggers action execution. Zero actions transition to `executed` without an explicit HTTP request to `/approve` signed by an authenticated human agent.
- **Evidence Required:** Test submitting adversarial tickets and inspecting database to confirm zero actions in `executed` status without manual approval.
- **Dependencies:** Action gate architecture.
- **Status:** **PASSED** (Verified via `test_prompt_injection_cannot_execute_action` and `test_adversarial_kb_document_inertness` in `tests/adversarial/test_guardrails.py`)

---

### EG-P5-12: Prior-Phase Regression Protection
- **Evaluation ID:** `EG-P5-12`
- **Objective:** Verify that Phase 5 changes do not break or regress any existing Phase 1–4 functionality.
- **Test Type:** Regression Test Suite (`tests/unit/`, `tests/integration/`)
- **Expected Behavior:** All 107 existing automated tests (37 Phase 4 tests, 70 Phase 1–3 tests) pass cleanly without modification or weakened assertions (134 total tests passing).
- **Evidence Required:** Pytest execution report demonstrating 134/134 passing tests.
- **Dependencies:** All prior phases.
- **Status:** **PASSED** (Verified via full test suite run: 134 passed in 4.92s)

---

## E. Evaluation Summary Dashboard

| Gate ID | Evaluation Name | Target Area | Verification Type | Status |
|---|---|---|---|:---:|
| **EG-P5-01** | Action Proposal Creation | Action Lifecycle | Integration | **PASSED** |
| **EG-P5-02** | Authenticated Approval | Human-in-the-Loop Gate | Integration | **PASSED** |
| **EG-P5-03** | Authenticated Rejection | Human-in-the-Loop Gate | Integration | **PASSED** |
| **EG-P5-04** | Identical-Key Idempotent Replay | Request Idempotency | Integration | **PASSED** |
| **EG-P5-05** | Terminal Action Conflict | State Machine | Integration | **PASSED** |
| **EG-P5-06** | Payload Tampering Detection | Security / Idempotency | Integration | **PASSED** |
| **EG-P5-07** | Business Uniqueness Enforcement | Relational Constraints | Integration | **PASSED** |
| **EG-P5-08** | Concurrent Double-Approval Lock | Concurrency / Locking | Integration (PostgreSQL) | **PASSED** |
| **EG-P5-09** | Business Failure Audit Commit | Audit Integrity | Integration | **PASSED** |
| **EG-P5-10** | Transient DB Crash Rollback | Transaction Atomicity | Integration | **PASSED** |
| **EG-P5-11** | Prompt Injection Gate Robustness | AI Safety & Guardrails | Adversarial | **PASSED** |
| **EG-P5-12** | Prior-Phase Regression Suite | System Integrity | Regression | **PASSED** |
