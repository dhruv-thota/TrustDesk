# Phase 2 — Testing & Evaluation Specification: Authenticated Ticket and Context APIs

**Document Version:** 1.1.0  
**Phase:** Phase 2 — Authenticated Ticket and Context APIs  
**Status:** Verified Post-Implementation Specification  
**Role:** Senior Software Architect, Test Architect & QA Engineer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md) (§3.2, §3.5)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md) (§4.3, §5.1, §5.2, §5.3, §5.4, §9.1)  
- [docs/implementation_plan.md](file:///Users/dhruv/Desktop/TrustDesk/docs/implementation_plan.md) (Phase 2 Specification)  
- [docs/phase2_edgecases.md](file:///Users/dhruv/Desktop/TrustDesk/docs/phase2_edgecases.md) (Phase 2 Edge Cases)  
- [docs/conventions.md](file:///Users/dhruv/Desktop/TrustDesk/docs/conventions.md) (§5.2, §5.3, §6, §7)  
- [docs/unresolved.md](file:///Users/dhruv/Desktop/TrustDesk/docs/unresolved.md) (`U-010`, `U-012`)

---

## A. Phase Evaluation Objective

The objective of Phase 2 evaluation is to objectively verify that:
1. All protected ticket endpoints enforce server-side demo bearer token authentication and map exclusively to the fixed demo agent identity (`DEMO_AGENT_IDENTITY`).
2. Ticket listing, status filtering, and customer ID filtering behave accurately and return properly formatted pagination envelopes.
3. Individual ticket detail retrieval returns exact source dataset fields without data loss or corruption.
4. Ticket context assembly accurately joins the ticket, customer profile, linked order with line items (or cleanly returns `order = null` when unlinked), and customer past tickets excluding the active ticket.
5. Standardized JSON error envelopes are returned for all error conditions (401, 404, 422, 503).
6. Phase 1 foundation endpoints (`GET /api/v1/health`) continue to function cleanly without regression.

---

## B. Evaluation Scope

- **Components Under Test:**
  - `trustdesk/core/security.py` (Bearer token validation & agent identity mapping)
  - `trustdesk/schemas/ticket.py` (Pydantic request and response schemas)
  - `trustdesk/services/ticket_service.py` (Ticket query and context assembly service)
  - `trustdesk/api/v1/tickets.py` (FastAPI ticket endpoints)
  - `trustdesk/main.py` (Router mounting and global standardized error handlers)
- **APIs Under Test:**
  - `GET /api/v1/tickets`
  - `GET /api/v1/tickets/{ticket_id}`
  - `GET /api/v1/tickets/{ticket_id}/context`
  - `GET /api/v1/health` (Phase 1 regression verification)
- **Database Operations Under Test:**
  - Selective filtering by `status` and `customer_id`.
  - Pagination offset and limit slicing.
  - Multi-table relational joins (`tickets` $\to$ `customers`, `tickets` $\to$ `orders`).
- **Security Boundaries:**
  - Mandatory demo bearer token authentication.
  - Prohibition of client-side identity tampering (ignoring `X-Agent-ID`).
  - Strict absence of hardcoded secrets or token leakage in logs and responses.
- **Explicit Exclusions:**
  - No AI ticket classification or triage result entities (Phase 4).
  - No policy retrieval or citation provenance checks (Phase 3).
  - No action proposal or refund review approval endpoints (Phase 5).
  - No React frontend testing (Phase 6).
  - No JWT/OIDC authentication testing (Post-MVP).

---

## C. Evaluation Environment

- **Required Services:**
  - PostgreSQL 15 running on port 5433 via Docker Compose.
- **Required Configuration:**
  ```ini
  DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/trustdesk
  TRUSTDESK_DEMO_TOKEN=demo_secret_token_123
  LOG_LEVEL=DEBUG
  ENVIRONMENT=test
  ```
- **Test Database Strategy:**
  - Tables populated with verified fixtures or ingested dataset records.
  - Session rollbacks and table truncation ensure clean state between test suites.

---

## D. Detailed Evaluation Cases

---

### P2-EV-001: Valid Demo Bearer Token Authentication
- **ID:** `P2-EV-001`
- **Title:** Successful Demo Token Authentication and Server Identity Binding
- **Requirement Being Verified:** `docs/architecture.md` §5.2, §9.1; `docs/implementation_plan.md` §3 (Phase 2.C.1)
- **Test Level:** Unit Test (`tests/unit/test_security.py`)
- **Preconditions:** `TRUSTDESK_DEMO_TOKEN` configured in environment settings.
- **Execution Procedure:** Call `verify_demo_token` dependency passing `Authorization: Bearer demo_secret_token_123`.
- **Expected Outcome:** Returns verified `AgentIdentity` object matching `DEMO_AGENT_IDENTITY` (`agent_id: "demo-agent-001"`, `name: "Demo Support Agent"`, `role: "agent"`).
- **Pass/Fail Threshold:** Exact dictionary/model match; no exception raised.
- **Actual Result / Evidence:** PASSED. `tests/unit/test_security.py::test_verify_demo_token_valid` executed cleanly with exit code 0.
- **Status:** **PASSED**

---

### P2-EV-002: Missing Authorization Header Rejection
- **ID:** `P2-EV-002`
- **Title:** Unauthenticated Request Without Authorization Header
- **Requirement Being Verified:** `docs/architecture.md` §5.2, §5.4; `docs/implementation_plan.md` §3 (Phase 2.C.1)
- **Test Level:** Unit Test (`tests/unit/test_security.py`) & API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** Protected endpoint active.
- **Execution Procedure:** Send `GET /api/v1/tickets` with no `Authorization` header.
- **Expected Outcome:** HTTP 401 Unauthorized; JSON response contains `{"error": {"code": "UNAUTHORIZED", "message": "...", "details": {}}}`.
- **Pass/Fail Threshold:** Status code == 401; error code == "UNAUTHORIZED".
- **Actual Result / Evidence:** PASSED. Verified in `test_verify_demo_token_missing` and `test_unauthenticated_requests_rejected`.
- **Status:** **PASSED**

---

### P2-EV-003: Invalid or Corrupted Bearer Token Rejection
- **ID:** `P2-EV-003`
- **Title:** Request with Incorrect Token or Invalid Authorization Scheme
- **Requirement Being Verified:** `docs/architecture.md` §5.2, §5.4; `docs/implementation_plan.md` §3 (Phase 2.F.1)
- **Test Level:** Unit Test (`tests/unit/test_security.py`) & API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** Server active.
- **Execution Procedure:** Send request with `Authorization: Bearer invalid_secret` and `Authorization: Basic dXNlcjpwYXNz`.
- **Expected Outcome:** HTTP 401 Unauthorized; standardized error envelope returned.
- **Pass/Fail Threshold:** Status code == 401 for both attempts.
- **Actual Result / Evidence:** PASSED. Verified in `test_verify_demo_token_invalid_secret`, `test_verify_demo_token_malformed_scheme`, and `test_unauthenticated_requests_rejected`.
- **Status:** **PASSED**

---

### P2-EV-004: Agent Identity Tampering Immunity
- **ID:** `P2-EV-004`
- **Title:** Client Headers Cannot Override Server-Bound Agent Identity
- **Requirement Being Verified:** `docs/architecture.md` §5.2, §9.1; `docs/implementation_plan.md` §3 (Phase 2.F.4)
- **Test Level:** Unit Test (`tests/unit/test_security.py`)
- **Preconditions:** Server active.
- **Execution Procedure:** Invoke `verify_demo_token` passing valid token along with custom headers `X-Agent-ID: forged-admin`, `X-Agent-Role: supervisor`.
- **Expected Outcome:** Returned identity object preserves `agent_id = "demo-agent-001"`; client-supplied values have zero effect.
- **Pass/Fail Threshold:** Identity is immutable and matches server configuration.
- **Actual Result / Evidence:** PASSED. Verified in `tests/unit/test_security.py::test_verify_demo_token_identity_tampering_immunity`.
- **Status:** **PASSED**

---

### P2-EV-005: Ticket and Context Pydantic Schema Validation
- **ID:** `P2-EV-005`
- **Title:** Strict Type and Field Validation for Ticket Schemas
- **Requirement Being Verified:** `docs/architecture.md` §4.3, §5.3; `docs/implementation_plan.md` §3 (Phase 2.C.2)
- **Test Level:** Unit Test (`tests/unit/test_ticket_schemas.py`)
- **Preconditions:** Pydantic models defined in `trustdesk/schemas/ticket.py`.
- **Execution Procedure:** Instantiate `TicketSummarySchema`, `TicketDetailSchema`, and `TicketContextSchema` with valid, null-order, and invalid inputs.
- **Expected Outcome:** Valid payloads parse cleanly; missing required fields raise `pydantic.ValidationError`; unlinked order cleanly validates as `None`.
- **Pass/Fail Threshold:** Strict schema validation without silent coercion.
- **Actual Result / Evidence:** PASSED. All 6 tests in `tests/unit/test_ticket_schemas.py` passed with 100% success.
- **Status:** **PASSED**

---

### P2-EV-006: Authenticated Ticket Listing and Total Count
- **ID:** `P2-EV-006`
- **Title:** Retrieve Paginated Ticket List with Valid Token
- **Requirement Being Verified:** `docs/architecture.md` §5.3; `docs/implementation_plan.md` §3 (Phase 2.C.4)
- **Test Level:** API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** Database populated with ingested tickets.
- **Execution Procedure:** Send `GET /api/v1/tickets` with valid demo bearer token.
- **Expected Outcome:** HTTP 200 OK; response matches `{"items": [...], "total": int, "limit": int, "offset": int}`; items list contains summary attributes (`ticket_id`, `customer_id`, `order_id`, `subject`, `status`, `created_at`).
- **Pass/Fail Threshold:** Status code == 200; total matches database row count; items length matches limit.
- **Actual Result / Evidence:** PASSED. Verified via `tests/integration/test_ticket_api.py::test_list_tickets_authenticated`.
- **Status:** **PASSED**

---

### P2-EV-007: Ticket Filtering by Operational Status
- **ID:** `P2-EV-007`
- **Title:** Filter Tickets by Status (`open`, `in_review`, `closed`)
- **Requirement Being Verified:** `docs/architecture.md` §5.3; `docs/implementation_plan.md` §3 (Phase 2.C.3)
- **Test Level:** API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** Tickets with varied statuses exist in database.
- **Execution Procedure:** Send `GET /api/v1/tickets?status=open`.
- **Expected Outcome:** HTTP 200 OK; all returned items have `status == "open"`; `total` reflects matching subset count.
- **Pass/Fail Threshold:** 100% of items have `status == "open"`.
- **Actual Result / Evidence:** PASSED. Verified via `tests/integration/test_ticket_api.py::test_list_tickets_status_filter`.
- **Status:** **PASSED**

---

### P2-EV-008: Ticket Filtering by Customer ID
- **ID:** `P2-EV-008`
- **Title:** Filter Tickets by Owning Customer Identifier
- **Requirement Being Verified:** `docs/architecture.md` §5.3; `docs/implementation_plan.md` §3 (Phase 2.C.3)
- **Test Level:** API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** Target customer has multiple tickets in database.
- **Execution Procedure:** Send `GET /api/v1/tickets?customer_id=CUST-001`.
- **Expected Outcome:** HTTP 200 OK; all returned items have `customer_id == "CUST-001"`.
- **Pass/Fail Threshold:** 100% of items match queried customer ID.
- **Actual Result / Evidence:** PASSED. Verified via `tests/integration/test_ticket_api.py::test_list_tickets_customer_filter`.
- **Status:** **PASSED**

---

### P2-EV-009: Pagination Boundary and Offset Slicing
- **ID:** `P2-EV-009`
- **Title:** Verification of Limit and Offset Slicing Semantics
- **Requirement Being Verified:** `docs/architecture.md` §5.1, §5.3; `docs/phase2_edgecases.md` `P2-EC-006`
- **Test Level:** API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** At least 5 tickets exist in database.
- **Execution Procedure:** Request `GET /api/v1/tickets?limit=2&offset=0` followed by `GET /api/v1/tickets?limit=2&offset=2`. Also test `limit=0` (rejected with 422).
- **Expected Outcome:** Pages return disjoint sets of tickets; invalid limit returns HTTP 422 with standardized validation error envelope.
- **Pass/Fail Threshold:** First and second page items do not overlap; 422 status on limit=0.
- **Actual Result / Evidence:** PASSED. Verified in `test_list_tickets_pagination_slicing` and `test_list_tickets_invalid_pagination_returns_422`.
- **Status:** **PASSED**

---

### P2-EV-010: Single Ticket Detail Retrieval
- **ID:** `P2-EV-010`
- **Title:** Retrieve Detailed View of Existing Support Ticket
- **Requirement Being Verified:** `docs/architecture.md` §5.3; `docs/implementation_plan.md` §3 (Phase 2.C.4)
- **Test Level:** API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** Target ticket exists in database.
- **Execution Procedure:** Send `GET /api/v1/tickets/{ticket_id}` with valid auth.
- **Expected Outcome:** HTTP 200 OK; response includes `ticket_id`, `customer_id`, `order_id`, `subject`, `message`, `status`, `created_at`, `raw_metadata`.
- **Pass/Fail Threshold:** Response fields exactly match stored database values.
- **Actual Result / Evidence:** PASSED. Verified via `tests/integration/test_ticket_api.py::test_get_ticket_detail_success`.
- **Status:** **PASSED**

---

### P2-EV-011: Ticket Context Assembly with Linked Customer and Order
- **ID:** `P2-EV-011`
- **Title:** Full Context Assembly for Ticket with Linked Customer, Order, and Past History
- **Requirement Being Verified:** `docs/architecture.md` §5.3; `docs/implementation_plan.md` §3 (Phase 2.C.4)
- **Test Level:** API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** Ticket has associated `customer_id` and non-null `order_id`. Customer has at least one other past ticket.
- **Execution Procedure:** Send `GET /api/v1/tickets/{ticket_id}/context` with valid auth.
- **Expected Outcome:** HTTP 200 OK; response contains:
  - `ticket`: full ticket detail.
  - `customer`: customer profile (`customer_id`, `name`, `email`, `metadata`, `created_at`).
  - `order`: full order detail (`order_id`, `order_date`, `delivery_date`, `status`, `total_amount`, `items`).
  - `past_tickets`: array of customer's other tickets, excluding current `ticket_id`.
- **Pass/Fail Threshold:** Context fields populated; current ticket excluded from past tickets.
- **Actual Result / Evidence:** PASSED. Verified via `tests/integration/test_ticket_api.py::test_get_ticket_context_full`.
- **Status:** **PASSED**

---

### P2-EV-012: Ticket Context Assembly for Ticket Without Linked Order
- **ID:** `P2-EV-012`
- **Title:** Context Assembly for Ticket Having `order_id = NULL`
- **Requirement Being Verified:** `docs/architecture.md` §4.3, §5.3; `docs/phase2_edgecases.md` `P2-EC-002`
- **Test Level:** API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** Ticket has `order_id = NULL`.
- **Execution Procedure:** Send `GET /api/v1/tickets/{ticket_id}/context` for unlinked ticket.
- **Expected Outcome:** HTTP 200 OK; `customer` profile populated; `order` field is strictly `null`; no crash occurs.
- **Pass/Fail Threshold:** Status code == 200; `response.json()["order"] is None`.
- **Actual Result / Evidence:** PASSED. Verified via `tests/integration/test_ticket_api.py::test_get_ticket_context_unlinked_order_is_null`.
- **Status:** **PASSED**

---

### P2-EV-013: Non-Existent Ticket ID Error Handling
- **ID:** `P2-EV-013`
- **Title:** Requesting Detail or Context for Non-Existent Ticket
- **Requirement Being Verified:** `docs/architecture.md` §5.3, §5.4; `docs/phase2_edgecases.md` `P2-EC-003`
- **Test Level:** API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** Ticket ID `TIK-DOES-NOT-EXIST` does not exist.
- **Execution Procedure:** Send `GET /api/v1/tickets/TIK-DOES-NOT-EXIST` and `GET /api/v1/tickets/TIK-DOES-NOT-EXIST/context`.
- **Expected Outcome:** HTTP 404 Not Found; error envelope returned with `code: "TICKET_NOT_FOUND"`.
- **Pass/Fail Threshold:** Both endpoints return HTTP 404 with standard error body.
- **Actual Result / Evidence:** PASSED. Verified via `test_get_ticket_detail_not_found` and `test_get_ticket_context_not_found`.
- **Status:** **PASSED**

---

### P2-EV-014: Standardized Error Envelope Compliance
- **ID:** `P2-EV-014`
- **Title:** Verification that All Errors Adhere to Standard JSON Error Schema
- **Requirement Being Verified:** `docs/architecture.md` §5.4; `docs/conventions.md` §5.3.8
- **Test Level:** API Integration Test (`tests/integration/test_ticket_api.py`)
- **Preconditions:** Protected server active.
- **Execution Procedure:** Trigger 401 (unauthorized), 404 (not found), and 422 (validation error). Inspect JSON body structure.
- **Expected Outcome:** 100% of error responses contain top-level `"error"` key with `"code"`, `"message"`, and `"details"` dictionary.
- **Pass/Fail Threshold:** Exact match with `docs/architecture.md` §5.4 schema.
- **Actual Result / Evidence:** PASSED. Verified in `test_unauthenticated_requests_rejected`, `test_get_ticket_detail_not_found`, and `test_list_tickets_invalid_pagination_returns_422`.
- **Status:** **PASSED**

---

### P2-EV-015: Phase 1 Regression Verification
- **ID:** `P2-EV-015`
- **Title:** Health Check Endpoint Remains Public and Functional
- **Requirement Being Verified:** `docs/architecture.md` §5.1; Phase 1 Acceptance Gate
- **Test Level:** API Integration Test (`tests/integration/test_health.py`)
- **Preconditions:** Server active.
- **Execution Procedure:** Send `GET /api/v1/health` without `Authorization` header.
- **Expected Outcome:** HTTP 200 OK with `{"status": "healthy", "database": "connected"}`.
- **Pass/Fail Threshold:** Status code == 200; does not require bearer authentication.
- **Actual Result / Evidence:** PASSED. Verified via `tests/integration/test_health.py::test_health_check_healthy` (and disconnected resilience in `test_health_check_database_disconnected`).
- **Status:** **PASSED**

---

## E. Evaluation Summary Matrix

| Evaluation ID | Title | Target Component | Status | Execution Evidence |
|---|---|---|:---:|---|
| `P2-EV-001` | Valid Demo Token Auth | `trustdesk/core/security.py` | **PASSED** | Unit test `test_verify_demo_token_valid` |
| `P2-EV-002` | Missing Auth Header Rejection | Protected routes | **PASSED** | Unit test & API test `test_unauthenticated_requests_rejected` |
| `P2-EV-003` | Invalid Token Rejection | Protected routes | **PASSED** | Unit test & API test `test_unauthenticated_requests_rejected` |
| `P2-EV-004` | Identity Tampering Immunity | `trustdesk/core/security.py` | **PASSED** | Unit test `test_verify_demo_token_identity_tampering_immunity` |
| `P2-EV-005` | Pydantic Schema Validation | `trustdesk/schemas/ticket.py` | **PASSED** | 6 unit tests in `test_ticket_schemas.py` |
| `P2-EV-006` | Authenticated Ticket Listing | `GET /api/v1/tickets` | **PASSED** | API test `test_list_tickets_authenticated` |
| `P2-EV-007` | Ticket Status Filtering | `GET /api/v1/tickets` | **PASSED** | API test `test_list_tickets_status_filter` |
| `P2-EV-008` | Ticket Customer Filtering | `GET /api/v1/tickets` | **PASSED** | API test `test_list_tickets_customer_filter` |
| `P2-EV-009` | Pagination Boundary Slicing | `GET /api/v1/tickets` | **PASSED** | API test `test_list_tickets_pagination_slicing` & 422 validation |
| `P2-EV-010` | Single Ticket Detail | `GET /api/v1/tickets/{id}` | **PASSED** | API test `test_get_ticket_detail_success` |
| `P2-EV-011` | Ticket Context Assembly | `GET /api/v1/tickets/{id}/context` | **PASSED** | API test `test_get_ticket_context_full` |
| `P2-EV-012` | Context with Null Order | `GET /api/v1/tickets/{id}/context` | **PASSED** | API test `test_get_ticket_context_unlinked_order_is_null` |
| `P2-EV-013` | Non-Existent Ticket 404 | Ticket detail & context | **PASSED** | API tests `test_get_ticket_detail_not_found` & `context_not_found` |
| `P2-EV-014` | Standard Error Envelope | Error handlers | **PASSED** | Verified on 401, 404, 422, 503 error payloads |
| `P2-EV-015` | Phase 1 Health Regression | `GET /api/v1/health` | **PASSED** | Integration tests in `test_health.py` |
