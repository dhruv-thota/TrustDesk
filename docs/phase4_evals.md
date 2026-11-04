# Phase 4 — Testing & Evaluation Specification: AI Triage and Grounded Draft Generation

**Document Version:** 1.1.0  
**Phase:** Phase 4 — AI Triage and Grounded Draft Generation  
**Status:** Verified Post-Implementation Specification  
**Role:** Senior Software Architect, Test Architect & QA Engineer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md) (§3.3, §3.4, §3.5, §3.7, §4)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md) (§3.7, §4.3, §6.4–6.5, §7.1–7.5, §8.1–8.5)  
- [docs/implementation_plan.md](file:///Users/dhruv/Desktop/TrustDesk/docs/implementation_plan.md) (§2, §3 Phase 4)  
- [docs/phase4_edgecases.md](file:///Users/dhruv/Desktop/TrustDesk/docs/phase4_edgecases.md) (Phase 4 Edge Cases)  
- [docs/conventions.md](file:///Users/dhruv/Desktop/TrustDesk/docs/conventions.md) (§1.2, §2, §3, §6, §7)  
- [docs/unresolved.md](file:///Users/dhruv/Desktop/TrustDesk/docs/unresolved.md) (`U-002`, `U-005`, `U-006`)

---

## A. Phase Evaluation Objective

The objective of Phase 4 evaluation is to objectively verify that:
1. AI ticket triage strictly validates category, priority, and escalation against defined Pydantic runtime schemas.
2. Provider timeouts (15s) and malformed outputs reliably trigger safe fallback objects marked as AI failures.
3. Synchronous triage and draft endpoints authenticate requests, assemble context, and execute with zero unhandled exceptions.
4. RAG-based draft generation retrieves policy sections using the Phase 3 common retrieval interface and includes structured citations.
5. Level 1 citation provenance validation reliably flags unretrieved or hallucinated section identifiers.
6. Level 3 deterministic policy checks independently verify return and warranty eligibility relative to `ticket.created_at` against authoritative order `delivery_date` ($\Delta t \le 30$ calendar days for refunds; $\Delta t \le 365$ calendar days for warranty).
7. A response draft accurately explaining customer ineligibility under policy rules is recognized as 100% grounded (`is_grounded = True`, `escalation_suggested = False`).
8. Inquiries with zero matching policy evidence or missing order delivery dates reliably trigger human escalation (`escalation_suggested = True`).
9. Action recommendation evaluation returns strictly advisory schemas (`ActionRecommendationSchema`) with zero autonomous execution privileges.
10. Sanitized execution traces are persisted in PostgreSQL without exposing raw customer PII, prompt secrets, or unredacted credentials.
11. Automated test suites run 100% deterministically and offline against `MockAIProvider`.
12. All 70 existing Phase 1–3 regression tests continue to pass without weakened assertions.

---

## B. Evaluation Scope

- **Components Under Test:**
  - `trustdesk/schemas/triage.py` (`TicketCategory`, `TicketPriority`, `TriageResultSchema`)
  - `trustdesk/schemas/draft.py` (`DraftResponseSchema`, `ActionRecommendationSchema`, `CitationSchema`)
  - `trustdesk/services/ai/base.py` (`AIProviderAdapter` abstract contract)
  - `trustdesk/services/ai/mock_provider.py` (`MockAIProvider` deterministic mock)
  - `trustdesk/services/ai/live_provider.py` (`LiveAIProvider` Gemini adapter structure and timeout logic)
  - `trustdesk/services/draft_service.py` (Prompt assembly, grounding verification, and Level 3 policy checks)
  - `trustdesk/api/v1/triage.py` (`POST /api/v1/tickets/{id}/triage`)
  - `trustdesk/api/v1/drafts.py` (`POST /api/v1/tickets/{id}/draft`)
  - `trustdesk/models/` and Alembic migration `003_create_phase4_tables.py` (`triage_results`, `draft_responses`, `draft_citations`, `execution_traces`)
- **Database Operations Under Test:**
  - Alembic migration `003_create_phase4_tables.py` forward and rollback execution.
  - Relational persistence of triage results and draft responses with foreign key cascade/set-null integrity.
  - Persistence of sanitized diagnostics and telemetry in JSONB columns.
- **Security & Safety Boundaries:**
  - Input framing in XML delimiters (`<untrusted_customer_message>`, `<policy_evidence>`).
  - Strict prohibition of tool/database side-effects during AI recommendation evaluation.
  - Redaction of sensitive customer PII, raw prompt secrets, and API credentials from `execution_traces`.
- **Explicit Exclusions:**
  - No autonomous execution of sensitive actions (Phase 5).
  - No action proposal and approval endpoints (Phase 5).
  - No asynchronous queue or Redis RQ background worker processing (Phase 7).
  - No React dashboard UI rendering (Phase 6).
  - No live LLM calls during regular automated CI/pytest runs (all automated tests run against `MockAIProvider`).

---

## C. Evaluation Environment

- **Required Services:**
  - PostgreSQL 15 containerized via Docker Compose binding to host port 5433 (`docker-compose.yml`).
- **Required Configuration:**
  ```ini
  DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/trustdesk
  TRUSTDESK_DEMO_TOKEN=demo_secret_token_123
  LOG_LEVEL=DEBUG
  ENVIRONMENT=test
  GEMINI_API_KEY=mock_key_for_testing
  ```
- **Test Execution Rule:**
  - All automated unit and integration tests run strictly against `MockAIProvider`.
  - Zero external network requests are made during `pytest`.

---

## D. Detailed Evaluation Gates

---

### EG-P4-01: Triage Runtime Schema Validation
- **Evaluation ID:** `EG-P4-01`
- **Objective:** Verify strict Pydantic runtime schema validation on triage classifications.
- **Test Type:** Unit Test (`tests/unit/test_triage_schemas.py`)
- **Expected Behavior:** Permitted categories (`shipping`, `refund`, `warranty`, `billing`, `account_security`, `general`) and permitted priorities (`low`, `medium`, `high`, `urgent`) parse successfully. Any other category or priority string (e.g. `"security"`, `"critical"`, `"unknown"`) immediately triggers Pydantic `ValidationError`.
- **Evidence Required:** Unit test asserting successful parsing of all 6 categories and 4 priorities, and explicit `ValidationError` on disallowed values.
- **Dependencies:** None.
- **Status:** **PASSED** (Verified via `test_permitted_categories_and_priorities_parse_cleanly`, `test_disallowed_categories_raise_validation_error`, `test_disallowed_priorities_raise_validation_error` in `tests/unit/test_triage_schemas.py`)

---

### EG-P4-02: Triage Escalation Semantics
- **Evaluation ID:** `EG-P4-02`
- **Objective:** Verify that high-risk inquiries trigger mandatory human escalation in triage output.
- **Test Type:** Unit Test (`tests/unit/test_triage_schemas.py`)
- **Expected Behavior:** Inquiries involving suspected account takeover or credential exposure are assigned `category = 'account_security'` and must have `needs_escalation = True`. Inquiries expressing severe distress, legal threats, or ambiguous policy coverage have `needs_escalation = True`.
- **Evidence Required:** Unit tests asserting `needs_escalation == True` for account security, distress, and ambiguous inquiry fixtures.
- **Dependencies:** None.
- **Status:** **PASSED** (Verified via `test_account_security_forces_escalation`, `test_distress_keywords_trigger_escalation` in `tests/unit/test_triage_schemas.py`)

---

### EG-P4-03: Authenticated Triage Endpoint
- **Evaluation ID:** `EG-P4-03`
- **Objective:** Verify that `POST /api/v1/tickets/{ticket_id}/triage` operates correctly with server-validated authentication.
- **Test Type:** Integration Test (`tests/integration/test_ai_workflows.py`)
- **Expected Behavior:** Request with valid `Authorization: Bearer demo_secret_token_123` returns HTTP 200 with structured JSON matching `TriageResultSchema`. Request without token returns HTTP 401 Unauthorized. Request for non-existent ticket returns HTTP 404 Not Found.
- **Evidence Required:** API integration tests verifying HTTP 200, 401, and 404 response codes and payload structures.
- **Dependencies:** Phase 2 `verify_demo_token`.
- **Status:** **PASSED** (Verified via `test_authenticated_triage_endpoint_success`, `test_triage_endpoint_missing_token_returns_401`, `test_triage_endpoint_nonexistent_ticket_returns_404` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-04: Triage Database Persistence
- **Evaluation ID:** `EG-P4-04`
- **Objective:** Verify that triage outcomes and sanitized diagnostics are persisted to PostgreSQL.
- **Test Type:** Integration Test (`tests/integration/test_ai_workflows.py`)
- **Expected Behavior:** Executing triage creates a row in `triage_results` with valid foreign key to `tickets.ticket_id`, correct `category`, `priority`, `needs_escalation`, `reasoning`, and `sanitized_diagnostics` JSONB payload.
- **Evidence Required:** Database inspection query asserting persisted row matches endpoint response and contains sanitized diagnostics.
- **Dependencies:** Alembic migration `003_create_phase4_tables.py`.
- **Status:** **PASSED** (Verified via `test_authenticated_triage_endpoint_success`, `test_triage_service_persists_result_and_trace` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-05: Provider Timeout Handling & Bounded Retry
- **Evaluation ID:** `EG-P4-05`
- **Objective:** Verify system resilience when external AI provider calls hang or exceed timeout SLA.
- **Test Type:** Unit Test (`tests/unit/test_ai_failure_handling.py`) & Integration Test (`tests/integration/test_ai_workflows.py`)
- **Expected Behavior:** When the provider call exceeds the 15-second SLA, the adapter triggers at most one bounded retry with backoff. If still failing, adapter catches timeout exception and returns a fallback triage object (`category='general'`, `priority='medium'`, `needs_escalation=True`, `is_fallback=True`), logging duration and model diagnostics. Draft endpoint returns HTTP 504 Gateway Timeout.
- **Evidence Required:** Unit test with mock provider simulating timeout, asserting single retry attempt and valid fallback triage object with `is_fallback == True`; draft endpoint integration test asserting HTTP 504 on timeout.
- **Dependencies:** Approved timeout and error code contract.
- **Status:** **PASSED** (Verified via `test_live_provider_timeout_and_retry`, `test_mock_provider_timeout_simulation` in `tests/unit/test_ai_failure_handling.py` and `test_triage_simulated_timeout_fallback`, `test_draft_provider_timeout_returns_504` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-06: Malformed AI Output Fallback
- **Evaluation ID:** `EG-P4-06`
- **Objective:** Verify system resilience when external AI provider returns non-JSON or invalid schema fields.
- **Test Type:** Unit Test (`tests/unit/test_ai_failure_handling.py`) & Integration Test (`tests/integration/test_ai_workflows.py`)
- **Expected Behavior:** When the LLM outputs unstructured prose or JSON missing required fields, the parsing exception is caught cleanly; adapter returns fallback triage object with `is_fallback = True`, records sanitized error diagnostics, and marks the classification as an AI failure. Draft endpoint returns HTTP 502 Bad Gateway.
- **Evidence Required:** Unit test injecting invalid JSON string into adapter, asserting fallback object returned without raising unhandled exception; draft endpoint integration test asserting HTTP 502.
- **Dependencies:** None.
- **Status:** **PASSED** (Verified via `test_mock_provider_malformed_simulation`, `test_triage_service_fallback_on_provider_malformed_output` in `tests/unit/test_ai_failure_handling.py` and `test_draft_provider_malformed_returns_502` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-07: Grounded Draft Generation Endpoint
- **Evaluation ID:** `EG-P4-07`
- **Objective:** Verify that `POST /api/v1/tickets/{ticket_id}/draft` coordinates RAG retrieval, prompt assembly, and draft generation.
- **Test Type:** Integration Test (`tests/integration/test_ai_workflows.py`)
- **Expected Behavior:** Endpoint retrieves relevant policy sections using `PolicyRetrievalInterface`, invokes provider with context and evidence, executes 3-level grounding validation, persists results to `draft_responses` and `draft_citations`, and returns HTTP 200 with `DraftResponseSchema`.
- **Evidence Required:** Integration test verifying HTTP 200, returned draft text, citation array, and database records in `draft_responses` and `draft_citations`.
- **Dependencies:** Phase 3 retrieval adapter and Alembic migration `003`.
- **Status:** **PASSED** (Verified via `test_authenticated_draft_endpoint_refund_within_window` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-08: Citation Provenance Validation (Level 1)
- **Evaluation ID:** `EG-P4-08`
- **Objective:** Verify that Level 1 citation provenance validator detects unretrieved or hallucinated section identifiers.
- **Test Type:** Unit & Integration Tests (`tests/unit/test_draft_grounding.py`, `tests/integration/test_ai_workflows.py`)
- **Expected Behavior:** Drafts citing section IDs present in the retrieved evidence set return `has_valid_provenance = True`. Drafts citing unretrieved section IDs return `has_valid_provenance = False`, `is_grounded = False`, and `escalation_suggested = True`.
- **Evidence Required:** Automated test asserting `has_valid_provenance` is `True` for valid citations and `False` with `invalid_citations` populated for hallucinated references.
- **Dependencies:** `trustdesk/services/citation_service.py`.
- **Status:** **PASSED** (Verified via `test_level1_citation_provenance_valid`, `test_level1_citation_provenance_hallucinated_section_rejected` in `tests/unit/test_draft_grounding.py` and `test_draft_hallucinated_citation_rejected` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-09: Deterministic Temporal Policy Check (Level 3)
- **Evaluation ID:** `EG-P4-09`
- **Objective:** Verify deterministic backend calculation of return and warranty policy windows.
- **Test Type:** Unit Test (`tests/unit/test_draft_grounding.py`)
- **Expected Behavior:** Return eligibility is calculated strictly as $\Delta t = \text{ticket.created\_at} - \text{order.delivery\_date}$. If $\Delta t \le 30$ calendar days, the order is eligible. If $\Delta t > 30$ days, the order is ineligible. If an LLM draft claims eligibility for an order with $\Delta t > 30$ days, Level 3 check detects the contradiction and sets `is_grounded = False` and `escalation_suggested = True`.
- **Evidence Required:** Unit test testing boundary values ($\Delta t = 29, 30, 31$ days) and asserting correct Level 3 rejection of hallucinated eligibility.
- **Dependencies:** Approved `U-005` decision.
- **Status:** **PASSED** (Verified via `test_level3_date_math_within_window`, `test_level3_date_math_exceeds_window`, `test_level3_date_math_warranty_window` in `tests/unit/test_draft_grounding.py` and `test_draft_claims_eligibility_on_expired_order_flagged_ungrounded` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-10: Grounded Ineligibility Verification
- **Evaluation ID:** `EG-P4-10`
- **Objective:** Verify that a draft accurately explaining that a customer is ineligible is recognized as 100% grounded.
- **Test Type:** Integration Test (`tests/integration/test_ai_workflows.py`)
- **Expected Behavior:** For an order delivered 45 days prior to ticket creation, a draft citing `KB-REFUND-001` that accurately explains that the order is outside the 30-day return window is evaluated as `has_valid_provenance = True`, `is_grounded = True`, and `escalation_suggested = False`.
- **Evidence Required:** Automated test verifying that factual refusal of an ineligible claim produces `is_grounded == True` and `escalation_suggested == False`.
- **Dependencies:** Approved `U-002` decision.
- **Status:** **PASSED** (Verified via `test_draft_grounded_ineligibility_on_expired_order` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-11: Insufficient Evidence Escalation
- **Evaluation ID:** `EG-P4-11`
- **Objective:** Verify that inquiries with zero retrieved policy evidence or missing delivery dates escalate to human supervision.
- **Test Type:** Integration Test (`tests/integration/test_ai_workflows.py`)
- **Expected Behavior:** When retrieval yields 0 policy sections, or when a refund inquiry involves a ticket with missing `order_id` or `delivery_date = NULL`, the draft service attaches an explicit escalation notice, sets `escalation_suggested = True`, and marks `is_grounded = False`.
- **Evidence Required:** Integration test for unindexed topics and unlinked orders asserting `escalation_suggested == True`.
- **Dependencies:** Approved `U-005` decision.
- **Status:** **PASSED** (Verified via `test_draft_insufficient_evidence_escalates`, `test_draft_null_order_id_escalates`, `test_draft_missing_delivery_date_escalates` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-12: Advisory Action Recommendation Contract
- **Evaluation ID:** `EG-P4-12`
- **Objective:** Verify that action recommendation evaluation outputs advisory data only, with zero direct execution privileges.
- **Test Type:** Unit & Integration Tests (`tests/unit/test_draft_grounding.py`, `tests/integration/test_ai_workflows.py`)
- **Expected Behavior:** `evaluate_action_recommendation` returns `ActionRecommendationSchema(action_type="start_refund_review", should_recommend=bool, payload=dict, reasoning=str)`. Calling this method creates ZERO rows in `proposed_actions` and performs ZERO database writes.
- **Evidence Required:** Test asserting return type matches `ActionRecommendationSchema` and database query asserting `proposed_actions` row count is unchanged.
- **Dependencies:** Architecture §7.1.
- **Status:** **PASSED** (Verified via `test_advisory_action_recommendation_contract` in `tests/unit/test_draft_grounding.py` and `test_authenticated_draft_endpoint_refund_within_window` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-13: Sanitized Execution Trace Recording
- **Evaluation ID:** `EG-P4-13`
- **Objective:** Verify that AI execution traces are recorded in PostgreSQL with customer PII and raw secrets redacted.
- **Test Type:** Integration Test (`tests/integration/test_ai_workflows.py`)
- **Expected Behavior:** Every triage and draft generation run persists a record to `execution_traces` capturing `ticket_id`, `run_type`, `retrieved_kb_ids`, `guardrail_outcome`, `final_status`, and `sanitized_telemetry`. Telemetry JSONB contains latency and model identifier, strictly without raw prompts, customer passwords, or API keys.
- **Evidence Required:** Database inspection asserting `execution_traces` contains expected audit fields and contains no raw customer message or credential strings.
- **Dependencies:** Alembic migration `003_create_phase4_tables.py`.
- **Status:** **PASSED** (Verified via `test_trace_sanitization_no_credentials_or_secrets` in `tests/integration/test_ai_workflows.py`)

---

### EG-P4-14: Phase 1–3 Regression Suite
- **Evaluation ID:** `EG-P4-14`
- **Objective:** Guarantee that all previously completed and verified Phase 1, 2, and 3 capabilities remain unbroken.
- **Test Type:** Full Test Suite Execution (`pytest`)
- **Expected Behavior:** All 70 existing unit and integration tests (Phase 1 foundation and ingestion, Phase 2 ticket context and auth, Phase 3 policy chunking, FTS retrieval, and citation validation) pass cleanly with zero failures.
- **Evidence Required:** Execution of `pytest` demonstrating 70 existing tests passing without modified assertions (totaling 107 passing tests with 37 Phase 4 tests).
- **Dependencies:** Existing test suite.
- **Status:** **PASSED** (Verified via full test run: 107 passed across `tests/unit/` and `tests/integration/` in 3.85s)

---

## E. Evaluation Summary Dashboard

| Evaluation Gate ID | Area / Capability | Test Type | Current Status | Supporting Verification Evidence |
|---|---|---|:---:|---|
| **EG-P4-01** | Triage Runtime Schema Validation | Unit | **PASSED** | `tests/unit/test_triage_schemas.py` (3 tests) |
| **EG-P4-02** | Triage Escalation Semantics | Unit | **PASSED** | `tests/unit/test_triage_schemas.py` (2 tests) |
| **EG-P4-03** | Authenticated Triage Endpoint | Integration | **PASSED** | `tests/integration/test_ai_workflows.py` (3 tests) |
| **EG-P4-04** | Triage Database Persistence | Integration | **PASSED** | `tests/integration/test_ai_workflows.py` (2 tests) |
| **EG-P4-05** | Provider Timeout Handling & Bounded Retry | Unit / Integration | **PASSED** | `tests/unit/test_ai_failure_handling.py` & `test_ai_workflows.py` |
| **EG-P4-06** | Malformed AI Output Fallback | Unit / Integration | **PASSED** | `tests/unit/test_ai_failure_handling.py` & `test_ai_workflows.py` |
| **EG-P4-07** | Grounded Draft Generation Endpoint | Integration | **PASSED** | `tests/integration/test_ai_workflows.py` |
| **EG-P4-08** | Citation Provenance Validation (Level 1) | Unit / Integration | **PASSED** | `tests/unit/test_draft_grounding.py` & `test_ai_workflows.py` |
| **EG-P4-09** | Deterministic Temporal Policy Check (Level 3) | Unit / Integration | **PASSED** | `tests/unit/test_draft_grounding.py` & `test_ai_workflows.py` |
| **EG-P4-10** | Grounded Ineligibility Verification | Integration | **PASSED** | `tests/integration/test_ai_workflows.py` |
| **EG-P4-11** | Insufficient Evidence Escalation | Integration | **PASSED** | `tests/integration/test_ai_workflows.py` (3 tests) |
| **EG-P4-12** | Advisory Action Recommendation Contract | Unit / Integration | **PASSED** | `tests/unit/test_draft_grounding.py` & `test_ai_workflows.py` |
| **EG-P4-13** | Sanitized Execution Trace Recording | Integration | **PASSED** | `tests/integration/test_ai_workflows.py` |
| **EG-P4-14** | Phase 1–3 Regression Suite (70 tests) | Full Suite | **PASSED** | Full suite execution: 107/107 tests passed (70 regression + 37 Phase 4) |

---

## F. Planned Verification Commands

```bash
# Unit test verification
pytest tests/unit/test_triage_schemas.py tests/unit/test_ai_failure_handling.py tests/unit/test_draft_grounding.py

# Integration test verification
pytest tests/integration/test_ai_workflows.py

# Full regression verification
pytest

# Manual API smoke test (with local dev server running)
curl -X POST -H "Authorization: Bearer demo_secret_token_123" http://localhost:8000/api/v1/tickets/TIK-001/triage
curl -X POST -H "Authorization: Bearer demo_secret_token_123" http://localhost:8000/api/v1/tickets/TIK-001/draft
```

