# Phase 2 — Edge Cases & Failure Scenarios: Authenticated Ticket and Context APIs

**Document Version:** 1.1.0  
**Phase:** Phase 2 — Authenticated Ticket and Context APIs  
**Status:** Verified Post-Implementation Specification  
**Role:** Senior Software Architect, Test Architect & QA Engineer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md) (§3.2, §3.5)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md) (§4.3, §5.1, §5.2, §5.3, §5.4, §9.1)  
- [docs/implementation_plan.md](file:///Users/dhruv/Desktop/TrustDesk/docs/implementation_plan.md) (Phase 2 Specification)  
- [docs/conventions.md](file:///Users/dhruv/Desktop/TrustDesk/docs/conventions.md) (§5.2, §5.3, §6, §7)  
- [docs/unresolved.md](file:///Users/dhruv/Desktop/TrustDesk/docs/unresolved.md) (`U-010`, `U-012`)

---

## A. Phase Overview

- **Phase Number & Name:** Phase 2 — Authenticated Ticket and Context APIs
- **Objective:** Build deterministic backend APIs for support-ticket management, customer profile retrieval, and linked-order context assembly, protected by server-side demo bearer token authentication that maps to a verified internal agent identity.
- **Relevant Implementation Plan Sections:** `docs/implementation_plan.md` §3 (Phase 2)
- **Dependencies:** Phase 1 complete and verified. Source customers, orders, and tickets persisted in PostgreSQL 15.
- **Scope Boundaries:**
  - *Included:* Authentication dependency (`verify_demo_token`), fixed demo agent identity mapping (`DEMO_AGENT_IDENTITY`), Pydantic ticket/context schemas, ticket query & context assembly service, ticket REST endpoints (`GET /api/v1/tickets`, `GET /api/v1/tickets/{ticket_id}`, `GET /api/v1/tickets/{ticket_id}/context`), standardized JSON error handlers, and comprehensive automated test suites.
  - *Excluded:* Knowledge base chunking, FTS search, and citation provenance (Phase 3); AI ticket triage and grounded draft generation (Phase 4); sensitive action proposal, approval, and idempotency (Phase 5); React dashboard (Phase 6); background worker and evaluation runner (Phase 7); production JWT/OIDC/RBAC (Post-MVP).
- **Related Unresolved Decision IDs:**
  - `U-010`: Local development setup (Resolved via Docker Compose PostgreSQL on port 5433).
  - `U-012`: Post-MVP production authentication and RBAC (Confirmed demo bearer token for MVP).

---

## B. Pre-Implementation Edge Cases

The following edge cases and boundary conditions are derived directly from the authoritative architecture, implementation plan, and error-handling standards, and have all been verified by automated tests.

---

### P2-EC-001: Unauthenticated or Malformed Bearer Token Request
- **ID:** `P2-EC-001`
- **Title:** Missing, Empty, or Incorrect Bearer Token on Protected API Endpoints
- **Category:** Security / Authentication
- **Precondition:** FastAPI application running with protected ticket endpoints.
- **Trigger/Input:** A client sends an HTTP request to any `/api/v1/tickets*` endpoint without an `Authorization` header, with an empty header, with an invalid scheme (e.g., `Basic xyz`), or with an invalid token string (`Bearer wrong_token`).
- **Expected Behavior:** The authentication dependency rejects the request immediately; API returns HTTP 401 Unauthorized with the standardized error envelope: `{"error": {"code": "UNAUTHORIZED", "message": "...", "details": {}}}`.
- **Forbidden Behavior:** Returning HTTP 200 OK, returning HTTP 500 Internal Server Error, or leaking internal token values in the error response.
- **Verification Method:** Automated unit tests in `tests/unit/test_security.py` and integration tests in `tests/integration/test_ticket_api.py`.
- **Related Requirement:** `docs/architecture.md` §5.2, §5.4; `docs/implementation_plan.md` §3 (Phase 2.F.1)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_verify_demo_token_missing`, `test_verify_demo_token_invalid_secret`, `test_verify_demo_token_malformed_scheme`, `test_verify_demo_token_empty_token` in `tests/unit/test_security.py` and `test_unauthenticated_requests_rejected` in `tests/integration/test_ticket_api.py`)

---

### P2-EC-002: Ticket Without Linked Order (`order_id = NULL`)
- **ID:** `P2-EC-002`
- **Title:** Context Assembly for Ticket Having No Associated Order
- **Category:** Domain / Relational Integrity
- **Precondition:** A ticket exists in the database where `order_id IS NULL` (general customer inquiry or pre-sales question).
- **Trigger/Input:** Client requests `GET /api/v1/tickets/{ticket_id}/context` for a ticket with `order_id = NULL`.
- **Expected Behavior:** API returns HTTP 200 OK; the response envelope contains complete ticket details, full customer profile, `order = null`, and any past tickets belonging to that customer.
- **Forbidden Behavior:** Raising an `AttributeError` or `NoneType` exception, failing database join, returning HTTP 404, or fabricating a dummy order.
- **Verification Method:** Integration test querying context for a ticket created without an order reference.
- **Related Requirement:** `docs/architecture.md` §4.3 (Table 3), §5.3; `docs/implementation_plan.md` §3 (Phase 2.F.2)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_get_ticket_context_unlinked_order_is_null` in `tests/integration/test_ticket_api.py` and `test_ticket_context_schema_unlinked_order_is_none` in `tests/unit/test_ticket_schemas.py`)

---

### P2-EC-003: Non-Existent Ticket ID Lookup
- **ID:** `P2-EC-003`
- **Title:** Request for Ticket Detail or Context Using Unknown Ticket ID
- **Category:** API Contract / Error Handling
- **Precondition:** Target ticket ID (e.g., `TIK-NONEXISTENT-999`) does not exist in `tickets` table.
- **Trigger/Input:** Client sends authenticated request to `GET /api/v1/tickets/TIK-NONEXISTENT-999` or `GET /api/v1/tickets/TIK-NONEXISTENT-999/context`.
- **Expected Behavior:** API returns HTTP 404 Not Found with standardized error payload: `{"error": {"code": "TICKET_NOT_FOUND", "message": "Ticket with ID 'TIK-NONEXISTENT-999' was not found.", "details": {"ticket_id": "TIK-NONEXISTENT-999"}}}`.
- **Forbidden Behavior:** Returning HTTP 500, returning HTTP 200 with `null` body, or crashing the process.
- **Verification Method:** Automated test requesting non-existent ID and asserting HTTP 404 and error body.
- **Related Requirement:** `docs/architecture.md` §5.3, §5.4; `docs/implementation_plan.md` §3 (Phase 2.F.3)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_get_ticket_detail_not_found` and `test_get_ticket_context_not_found` in `tests/integration/test_ticket_api.py`)

---

### P2-EC-004: Agent Identity Tampering via Client Headers
- **ID:** `P2-EC-004`
- **Title:** Client Passes Custom Agent Identity Header to Override Server Identity
- **Category:** Security / Authorization
- **Precondition:** Client provides a valid demo bearer token.
- **Trigger/Input:** Client supplies request headers attempting identity forgery (e.g., `X-Agent-ID: rogue-agent-999`, `X-Agent-Role: supervisor`).
- **Expected Behavior:** The backend completely ignores client-supplied agent identity headers; the request context is strictly bound to the server-configured `DEMO_AGENT_IDENTITY` (`agent_id: "demo-agent-001"`, `name: "Demo Support Agent"`, `role: "agent"`).
- **Forbidden Behavior:** Adopting the client's `X-Agent-ID` or granting elevated permissions based on request headers.
- **Verification Method:** Automated unit and API tests asserting that verified identity matches server constant regardless of client headers.
- **Related Requirement:** `docs/architecture.md` §5.2, §9.1; `docs/implementation_plan.md` §3 (Phase 2.F.4)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_verify_demo_token_identity_tampering_immunity` in `tests/unit/test_security.py`)

---

### P2-EC-005: Ticket Filtering Yielding Zero Matching Records
- **ID:** `P2-EC-005`
- **Title:** Filter by Non-Existent Customer ID or Unmatched Status
- **Category:** API Contract / Query Semantics
- **Precondition:** Database contains tickets, but none match the filter query (e.g., `?customer_id=CUST-NONE` or `?status=closed` when all tickets are open).
- **Trigger/Input:** Authenticated request to `GET /api/v1/tickets?customer_id=CUST-NONE`.
- **Expected Behavior:** API returns HTTP 200 OK with `{"items": [], "total": 0, "limit": 50, "offset": 0}` (an empty collection, not a 404 error).
- **Forbidden Behavior:** Raising HTTP 404 Not Found or raising an unhandled query exception.
- **Verification Method:** Automated test issuing unmatched query parameter and verifying empty list with total = 0.
- **Related Requirement:** `docs/architecture.md` §5.3; `docs/implementation_plan.md` §3 (Phase 2.C.3)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_list_tickets_empty_result` in `tests/integration/test_ticket_api.py`)

---

### P2-EC-006: Pagination Query Parameter Boundary Conditions
- **ID:** `P2-EC-006`
- **Title:** Invalid, Negative, or Out-of-Bounds Pagination Parameters
- **Category:** Validation / API Contract
- **Precondition:** Protected ticket list endpoint is active.
- **Trigger/Input:** Client requests `GET /api/v1/tickets?limit=0`, `GET /api/v1/tickets?limit=-5`, `GET /api/v1/tickets?limit=500`, or `GET /api/v1/tickets?offset=-1`.
- **Expected Behavior:** FastAPI Pydantic query validation rejects invalid parameters with HTTP 422 Unprocessable Entity and standard error envelope (`code: "VALIDATION_ERROR"`). For valid large `offset` beyond `total` count, returns HTTP 200 with `items = []` and accurate `total`.
- **Forbidden Behavior:** Allowing negative limits or SQL syntax errors (`OFFSET -1`), or returning raw unhandled 500.
- **Verification Method:** Automated API tests asserting HTTP 422 for negative/zero limits, and HTTP 200 with empty items for out-of-range offsets.
- **Related Requirement:** `docs/architecture.md` §5.1, §5.4; `docs/conventions.md` §5.2.2
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_list_tickets_invalid_pagination_returns_422` in `tests/integration/test_ticket_api.py`)

---

### P2-EC-007: Context Assembly for Ticket with Quarantined Foreign Key
- **ID:** `P2-EC-007`
- **Title:** Context Retrieval for Ticket Containing Unresolved Quarantined Order Reference
- **Category:** Data Integrity / Metadata Preservation
- **Precondition:** Ingestion stored a ticket with `order_id = NULL` and `raw_metadata["unresolved_order_id"] = "ORD-MISSING-999"` per Phase 1 quarantine policy (`P1-EC-003`).
- **Trigger/Input:** Client requests `GET /api/v1/tickets/{ticket_id}/context`.
- **Expected Behavior:** API returns HTTP 200 OK; `order` field is `null`; the ticket's `raw_metadata` correctly contains the quarantined `unresolved_order_id` string for audit traceability without error.
- **Forbidden Behavior:** Silently stripping metadata, crashing on null order join, or attempting to query a non-existent order.
- **Verification Method:** Integration test retrieving context for a quarantined ticket fixture.
- **Related Requirement:** `docs/architecture.md` §4.3 (Table 3), §4.4; `docs/unresolved.md` `U-003`
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_get_ticket_context_quarantined_reference` in `tests/integration/test_ticket_api.py`)

---

### P2-EC-008: Customer Context with No Prior Ticket History
- **ID:** `P2-EC-008`
- **Title:** Context Assembly for First-Time Customer with Single Ticket
- **Category:** Domain / Query Semantics
- **Precondition:** Customer has exactly one ticket in the database.
- **Trigger/Input:** Client requests `GET /api/v1/tickets/{ticket_id}/context`.
- **Expected Behavior:** API returns HTTP 200 OK; `past_tickets` list is empty (`[]`) because the current ticket is excluded from its own past tickets collection.
- **Forbidden Behavior:** Including the active ticket inside `past_tickets`, returning `null`, or raising an exception.
- **Verification Method:** Integration test asserting `ticket.ticket_id NOT IN [t.ticket_id for t in context.past_tickets]`.
- **Related Requirement:** `docs/architecture.md` §5.3 (Table TicketContextSchema)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_get_ticket_context_customer_single_ticket_history_is_empty` in `tests/integration/test_ticket_api.py`)

---

### P2-EC-009: Malformed or Injected Authorization Header Values
- **ID:** `P2-EC-009`
- **Title:** Bearer Header Containing Newlines, Control Characters, or Extreme Length
- **Category:** Security / Input Sanitization
- **Precondition:** Protected endpoints active.
- **Trigger/Input:** Client sends `Authorization: Bearer \r\nDROP TABLE tickets;` or a token exceeding 4096 characters.
- **Expected Behavior:** Token comparison safely fails; API returns HTTP 401 Unauthorized without executing SQL, without buffer errors, and without logging the raw input.
- **Forbidden Behavior:** Unhandled server crash, SQL injection, or logging unredacted authorization header payloads.
- **Verification Method:** Unit test in `tests/unit/test_security.py` passing malformed header values.
- **Related Requirement:** `docs/architecture.md` §5.2; `docs/conventions.md` §5.3.9
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_verify_demo_token_malformed_header_injection` in `tests/unit/test_security.py`)

---

### P2-EC-010: Database Connection Unavailable During Ticket API Operations
- **ID:** `P2-EC-010`
- **Title:** Database Connection Drop or Pool Exhaustion During Ticket Requests
- **Category:** Resilience / Error Handling
- **Precondition:** Database is stopped or unreachable while FastAPI server is processing requests.
- **Trigger/Input:** Client sends authenticated request to `GET /api/v1/tickets`.
- **Expected Behavior:** Database operational error is caught by error-handling middleware; API returns HTTP 503 Service Unavailable with standard error code `DATABASE_UNAVAILABLE`; server does not hang or crash.
- **Forbidden Behavior:** Returning an unformatted HTML 500 error or hanging indefinitely.
- **Verification Method:** Integration test with mocked or disconnected database engine asserting HTTP 503 and standard JSON error response.
- **Related Requirement:** `docs/architecture.md` §5.1, §5.4; `docs/implementation_plan.md` §3 (Phase 1.F.1)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_ticket_api_database_disconnected` in `tests/integration/test_ticket_api.py`)

---

## C. Implementation-Discovered Edge Cases

*(This section records edge cases discovered during active coding, data inspection, integration, or failure testing. Numbering continues sequentially from `P2-EC-011` per `docs/conventions.md` §7.2.)*

*No implementation-discovered edge cases encountered during Phase 2.*
