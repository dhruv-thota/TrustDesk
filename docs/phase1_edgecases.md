# Phase 1 — Edge Cases & Failure Scenarios: Foundation, Database, and Dataset Ingestion

**Document Version:** 1.0.0  
**Phase:** Phase 1 — Foundation, Database, and Dataset Ingestion  
**Status:** Pre-Implementation Specification  
**Role:** Senior Software Architect, Test Architect & QA Engineer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md) (§3.1, §3.5, §6, §7)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md) (§2.1, §3.2, §3.3, §4.1, §4.3, §4.4, §8.5)  
- [docs/implementation_plan.md](file:///Users/dhruv/Desktop/TrustDesk/docs/implementation_plan.md) (Phase 1 Specification)  
- [docs/unresolved.md](file:///Users/dhruv/Desktop/TrustDesk/docs/unresolved.md) (`U-003`, `U-010`, `U-013`)

---

## A. Phase Overview

- **Phase Number & Name:** Phase 1 — Foundation, Database, and Dataset Ingestion
- **Objective:** Establish the Python/FastAPI project structure, local PostgreSQL 15 environment with Alembic migrations, source database models, and an idempotent dataset ingestion pipeline that validates and persists raw customers, orders, tickets, knowledge base documents, and tool catalog entries while strictly distinguishing naturally absent foreign keys from invalid references and preserving all original identifiers.
- **Relevant Implementation Plan Sections:** `docs/implementation_plan.md` §3 (Phase 1)
- **Dependencies:** Docker/Docker Compose for local PostgreSQL 15, Python 3.11+, and source dataset files in `data/`.
- **Scope Boundaries:**
  - *Included:* Core project scaffolding, configuration loading, database engine/sessionmaker, source SQLAlchemy models (`customers`, `orders`, `tickets`, `kb_documents`), Alembic migrations, dataset ingestion CLI with deduplication, foreign key quarantine policy, tool catalog scope enforcement (`start_refund_review` only), and `GET /api/v1/health`.
  - *Excluded:* Knowledge base section chunking and FTS GIN indexing (strictly owned by Phase 3); Redis and RQ worker setup (Phase 7); AI provider integration (Phase 4); action approvals (Phase 5); React frontend (Phase 6).
- **Related Unresolved Decision IDs:**
  - `U-003`: Source dataset schema and foreign key quarantine policy (Blocked pending files in `data/`).
  - `U-010`: Local development orchestration baseline (Addressed via Docker Compose PostgreSQL).
  - `U-013`: Tool catalog ingestion and scope enforcement (Blocked pending files in `data/`).

---

## B. Pre-Implementation Edge Cases

The following edge cases and boundary scenarios are identified through requirement analysis and architectural review prior to implementation.

---

### P1-EC-001: Ingestion Re-execution and Idempotency
- **ID:** `P1-EC-001`
- **Title:** Consecutive Ingestion Invocations on Identical Data
- **Category:** Database Integrity / Idempotency
- **Precondition:** The database schema is migrated to `head`, and initial ingestion has already completed successfully.
- **Trigger/Input:** The ingestion command (`python -m trustdesk.cli ingest --data-dir ./data`) is executed a second time on the same source data.
- **Expected Behavior:** The command completes with exit code 0; all records are updated or preserved via `ON CONFLICT (...) DO UPDATE`; no duplicate primary keys or unique constraint violations are raised; database row counts remain identical before and after.
- **Forbidden Behavior:** Primary key collisions, unhandled `IntegrityError` exceptions, duplicate rows created, or data corruption.
- **Verification Method:** Integration test executing `ingest_dataset()` twice in sequence and asserting identical row counts in `customers`, `orders`, `tickets`, and `kb_documents`.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 1.C.5, 1.F.2); `docs/architecture.md` §4.4
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_ingestion_idempotency_and_repeatability` in `tests/integration/test_ingestion.py`)

---

### P1-EC-002: Naturally Absent (Null) Foreign Key Reference on Ticket
- **ID:** `P1-EC-002`
- **Title:** Support Ticket Ingested Without an Associated Order
- **Category:** Data Quality / Relational Integrity
- **Precondition:** Database migrated; orders and customers loaded.
- **Trigger/Input:** A ticket record in the dataset has no `order_id` (field is null, missing, or empty string `""` because the customer has a general pre-sales or account question).
- **Expected Behavior:** Ingestion sets the relational column `tickets.order_id = NULL`; the ticket record is persisted successfully; foreign key constraints pass without warnings.
- **Forbidden Behavior:** Rejecting the ticket, crashing with a null-pointer error, or fabricating an artificial dummy order record.
- **Verification Method:** Ingestion test with a ticket fixture where `order_id` is null; query `tickets` table and assert `order_id IS NULL`.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 1.C.5); `docs/architecture.md` §4.3 (Table 3), §4.4
- **Unresolved Dependencies:** `U-003`
- **Verification Status:** **PASSED** (Verified via `test_naturally_null_foreign_key_handling` in `tests/integration/test_ingestion.py`)

---

### P1-EC-003: Invalid Non-Null Foreign Key Reference with Quarantine
- **ID:** `P1-EC-003`
- **Title:** Ticket References Non-Existent Order ID (Quarantine Policy)
- **Category:** Data Quality / Relational Integrity / Quarantine
- **Precondition:** Database migrated; orders table populated with valid order IDs (e.g., `ORD-001`, `ORD-002`).
- **Trigger/Input:** An ingested ticket record contains `order_id = "ORD-MISSING-999"`, which does not exist in `orders`.
- **Expected Behavior:** Ingestion **must not silently discard** the invalid reference. The raw unresolvable string is preserved in `tickets.raw_metadata["unresolved_order_id"] = "ORD-MISSING-999"`; the relational column `tickets.order_id` is set to `NULL` to maintain database foreign key integrity; a structured warning log is emitted containing the ticket ID and unresolved order reference.
- **Forbidden Behavior:** Silently dropping the order ID string without audit trace, creating an invalid orphaned foreign key violation, or crashing the entire batch ingestion.
- **Verification Method:** Ingestion test with a fixture ticket containing an invalid non-null `order_id`; assert `tickets.order_id IS NULL`, `tickets.raw_metadata->>'unresolved_order_id' == 'ORD-MISSING-999'`, and structured warning emitted.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 1.C.5, 1.F.3); `docs/unresolved.md` `U-003`
- **Unresolved Dependencies:** `U-003`
- **Verification Status:** **PASSED** (Verified via `test_invalid_non_null_foreign_key_quarantine_policy` in `tests/integration/test_ingestion.py`)

---

### P1-EC-004: Missing Mandatory Parent Customer Entity
- **ID:** `P1-EC-004`
- **Title:** Ticket References Non-Existent Customer ID
- **Category:** Database Integrity / Relational Integrity
- **Precondition:** Database migrated; customers table loaded.
- **Trigger/Input:** An ingested ticket record contains `customer_id = "CUST-NONEXISTENT"`, which does not exist in `customers`.
- **Expected Behavior:** Because customer identity is a mandatory foreign key for ticket ownership, the ingestion pipeline rejects or quarantines the orphaned ticket into an ingestion quarantine log table (`quarantined_records`); the valid records in the batch continue processing; a structured error log is recorded.
- **Forbidden Behavior:** Creating an unlinked ticket that violates `NOT NULL` customer constraints or corrupting the relational customer relationship.
- **Verification Method:** Ingestion test with a fixture ticket containing an invalid customer ID; verify ticket is not inserted into `tickets` table and quarantine record is logged.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 1.C.5); `docs/architecture.md` §4.3 (Table 3)
- **Unresolved Dependencies:** `U-003`
- **Verification Status:** **PASSED** (Verified via `test_mandatory_parent_customer_reference_validation` in `tests/integration/test_ingestion.py`)

---

### P1-EC-005: Preservation of Original Alphanumeric Identifiers
- **ID:** `P1-EC-005`
- **Title:** Exact Preservation of Knowledge Base Document IDs
- **Category:** Data Integrity / Traceability
- **Precondition:** Database migrated.
- **Trigger/Input:** Knowledge base documents containing alphanumeric identifiers (e.g., `KB-REFUND-001`, `KB-WAR-002`, `KB-ADVERSARIAL-001`) are ingested.
- **Expected Behavior:** Document IDs are stored verbatim as primary keys in `kb_documents.kb_id`; characters, hyphens, and case are preserved exactly without slugification, lowercasing, or substitution with synthetic integer IDs.
- **Forbidden Behavior:** Replacing original IDs with auto-incrementing integers, UUIDs, or altering string casing (e.g., converting to `kb_refund_1`).
- **Verification Method:** Integration test asserting `SELECT kb_id FROM kb_documents` returns exact matching strings from source files.
- **Related Requirement:** `docs/problem_statement.md` §3.1; `docs/architecture.md` §4.3 (Table 4), §4.4
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_identifier_preservation_for_kb_documents` in `tests/integration/test_ingestion.py`)

---

### P1-EC-006: Ingestion of Adversarial Knowledge Base Document
- **ID:** `P1-EC-006`
- **Title:** Ingestion of Poisoned Prompt Content (`KB-ADVERSARIAL-001`)
- **Category:** Security / Data Sanitization
- **Precondition:** Database migrated.
- **Trigger/Input:** Ingesting `KB-ADVERSARIAL-001`, which contains prompt injection strings (e.g., system override instructions, delimiter escapes, or secret disclosure commands).
- **Expected Behavior:** The document is ingested strictly as passive text data in `kb_documents.raw_content`; SQL special characters and escape sequences are safely parameterized; no administrative commands are executed.
- **Forbidden Behavior:** SQL injection vulnerabilities, script execution, or ingestion failure due to malicious formatting.
- **Verification Method:** Ingestion test verifying `KB-ADVERSARIAL-001` is persisted verbatim in PostgreSQL via parameterized queries.
- **Related Requirement:** `docs/problem_statement.md` §3.5; `docs/architecture.md` §8.2, §8.3
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_identifier_preservation_for_kb_documents` in `tests/integration/test_ingestion.py`)

---

### P1-EC-007: Tool Catalog Unsupported Action Restrictions
- **ID:** `P1-EC-007`
- **Title:** Tool Catalog Contains Prohibited or Out-of-Scope Actions
- **Category:** Security / Scope Enforcement
- **Precondition:** Database migrated.
- **Trigger/Input:** Ingesting `tool_catalog.*`, which may define multiple operational actions (e.g., `start_refund_review`, `create_replacement_order`, `issue_direct_refund`).
- **Expected Behavior:** Ingestion registers all catalog entries in the tool registry, but the backend explicitly flags `start_refund_review` as `is_supported = True` and all other actions (including `create_replacement_order`) as `is_supported = False` (`in_scope = False`), enforcing TrustDesk's architectural boundary.
- **Forbidden Behavior:** Enabling `create_replacement_order` or financial refund disbursement as executable operational actions.
- **Verification Method:** Inspect tool registry records in database or memory and assert only `start_refund_review` is enabled.
- **Related Requirement:** `docs/problem_statement.md` §3.5; `docs/architecture.md` §8.5; `docs/unresolved.md` `U-013`
- **Unresolved Dependencies:** `U-013`
- **Verification Status:** **PASSED** (Verified via `test_tool_catalog_scope_enforcement` in `tests/integration/test_ingestion.py`)

---

### P1-EC-008: Database Unreachable at Startup
- **ID:** `P1-EC-008`
- **Title:** Application Startup with Unavailable Database
- **Category:** Failure Recovery / Resilience
- **Precondition:** PostgreSQL container is stopped or network is down.
- **Trigger/Input:** FastAPI application starts, or `GET /api/v1/health` is requested.
- **Expected Behavior:** Database connection pool raises a connection timeout/refusal; the error is caught; `/api/v1/health` returns HTTP 503 Service Unavailable with `{"status": "unhealthy", "database": "disconnected"}`; the application does not crash silently or hang indefinitely.
- **Forbidden Behavior:** Returning HTTP 200 OK while database is down, hanging on connection indefinitely, or crashing without returning an HTTP response.
- **Verification Method:** Integration test executing health check client against an invalid `DATABASE_URL` and asserting HTTP 503 response.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 1.C.6, 1.F.1)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_health_check_database_disconnected` in `tests/integration/test_health.py`)

---

### P1-EC-009: Missing Source Dataset Directory or Files
- **ID:** `P1-EC-009`
- **Title:** Ingestion Executed on Empty or Missing Data Directory
- **Category:** Input Validation / CLI Error Handling
- **Precondition:** Directory `./data` does not exist or lacks mandatory files (`customers.json`, etc.).
- **Trigger/Input:** Running `python -m trustdesk.cli ingest --data-dir ./nonexistent_path`.
- **Expected Behavior:** Ingestion CLI terminates immediately with exit code 1; emits a clear error message identifying missing directory or specific missing files; no database connection is opened and no partial migration is left in an uncommitted state.
- **Forbidden Behavior:** Crashing with an unhandled Python traceback or silently succeeding with zero records.
- **Verification Method:** CLI test calling `trustdesk.cli ingest` on non-existent path and asserting exit code 1 and error output.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 1.C.5, 1.F)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_ingestion_missing_directory_handling` in `tests/integration/test_ingestion.py`)

---

### P1-EC-010: Corrupted / Malformed JSON in Source Data File
- **ID:** `P1-EC-010`
- **Title:** Ingestion Encountering Malformed Source File
- **Category:** Input Validation / Transactional Integrity
- **Precondition:** Database migrated.
- **Trigger/Input:** A source JSON file contains a syntax error (e.g., trailing comma, unclosed bracket).
- **Expected Behavior:** Ingestion validator catches JSON syntax error before database execution; aborts the operation; rolls back the current database transaction; displays specific file and line error; no partially parsed corrupted batch is committed.
- **Forbidden Behavior:** Committing a partial batch of corrupted records or leaving an open transaction lock in PostgreSQL.
- **Verification Method:** Ingestion test with a fixture file containing malformed JSON; assert transaction rollback and clean error message.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 1.C.5)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_ingestion_corrupted_json_handling` in `tests/integration/test_ingestion.py`)

---

### P1-EC-011: Timezone Preservation on Order Date and Ticket Created At
- **ID:** `P1-EC-011`
- **Title:** Timezone Accuracy for Temporal Evaluation Timestamps
- **Category:** Data Integrity / Domain Logic
- **Precondition:** Database migrated.
- **Trigger/Input:** Dataset files contain ISO 8601 timestamps with non-UTC timezone offsets (e.g., `2026-10-15T14:30:00-04:00` for `order_date` and `2026-11-01T09:00:00+02:00` for `ticket.created_at`).
- **Expected Behavior:** PostgreSQL stores timestamps as `TIMESTAMPTZ`; timestamps are normalized accurately to UTC; elapsed time calculations ($\Delta t = \text{ticket.created\_at} - \text{order.order\_date}$) accurately reflect absolute elapsed hours regardless of local offset.
- **Forbidden Behavior:** Discarding timezone offsets, assuming system local time, or truncating timestamps to naive dates.
- **Verification Method:** Ingestion test with offset timestamps; query database and assert correct UTC normalization and precise timedelta calculation.
- **Related Requirement:** `docs/problem_statement.md` §3.1; `docs/architecture.md` §4.5
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_timezone_normalization_and_preservation` in `tests/integration/test_ingestion.py`)

---

### P1-EC-012: Ingestion Updates on Conflicting Primary Key with Modified Attributes
- **ID:** `P1-EC-012`
- **Title:** Primary Key Conflict with Updated Source Attributes
- **Category:** Database Integrity / Ingestion Update
- **Precondition:** Database contains initial customer record with email `"old@example.com"`.
- **Trigger/Input:** Ingestion runs with a refreshed dataset where the same `customer_id` has email `"new@example.com"`.
- **Expected Behavior:** PostgreSQL `ON CONFLICT (customer_id) DO UPDATE` updates the email to `"new@example.com"`; record is updated in place without duplicate key errors; `created_at` timestamp is preserved.
- **Forbidden Behavior:** Throwing a duplicate key error or resetting initial registration timestamps.
- **Verification Method:** Ingestion test running initial load, mutating an attribute in source fixture, running second load, and verifying in-place update.
- **Related Requirement:** `docs/architecture.md` §4.4
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_primary_key_conflict_with_updated_source_attributes` in `tests/integration/test_ingestion.py`)

---

## C. Implementation-Discovered Edge Cases

No additional implementation-discovered edge cases were identified during Phase 1 implementation and evaluation.

---

## D. Edge Case Coverage Summary

| Metric | Count |
|---|:---:|
| **Total Anticipated Pre-Implementation Cases** | 12 |
| **Total Implementation-Discovered Cases** | 0 |
| **Cases Passed** | 12 |
| **Cases Failed** | 0 |
| **Cases Blocked** | 0 |
| **Cases Not Tested** | 0 |

---

## E. Open Questions

1. **Exact Source Dataset Format:**  
   Resolved under `U-003`: Source dataset files under `data/` are standard JSON arrays (`customers.json`, `orders.json`, `tickets.json`, `kb_documents.json`).
2. **Tool Catalog Schema:**  
   Resolved under `U-013`: `tool_catalog.json` defines tool specifications with parameters and sensitivity flags; backend restricts operational actions strictly to `start_refund_review`.
