# Phase 3 — Testing & Evaluation Specification: Knowledge-Base Retrieval and Citation Infrastructure

**Document Version:** 1.1.0  
**Phase:** Phase 3 — Knowledge-Base Retrieval and Citation Infrastructure  
**Status:** Verified Post-Implementation Specification  
**Role:** Senior Software Architect, Test Architect & QA Engineer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md) (§3.4, §3.5, §4)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md) (§4.3, §6.1–6.5)  
- [docs/implementation_plan.md](file:///Users/dhruv/Desktop/TrustDesk/docs/implementation_plan.md) (§2, §3 Phase 3)  
- [docs/phase3_edgecases.md](file:///Users/dhruv/Desktop/TrustDesk/docs/phase3_edgecases.md) (Phase 3 Edge Cases)  
- [docs/conventions.md](file:///Users/dhruv/Desktop/TrustDesk/docs/conventions.md) (§1.2, §2, §3, §6, §7)  
- [docs/unresolved.md](file:///Users/dhruv/Desktop/TrustDesk/docs/unresolved.md) (`U-005`, `U-007`, `U-011`)

---

## A. Phase Evaluation Objective

The objective of Phase 3 evaluation is to objectively verify that:
1. Knowledge base documents are deterministically parsed and split into structured sections identified by `{kb_id}#sec-{index}` with parent document IDs preserved.
2. Long sections exceeding 1,500 characters are sub-chunked deterministically while preserving heading context.
3. PostgreSQL full-text search (FTS) index `idx_kb_sections_fts` is generated and active on `search_vector` combining title (weight `'A'`) and body (weight `'B'`).
4. The abstract `PolicyRetrievalInterface` is implemented by `PostgresFtsRetrievalAdapter` without leaking database implementation details to callers.
5. Search queries targeting refund, shipping, and warranty domains accurately rank relevant policy sections using `ts_rank_cd`.
6. Multiple query execution merges and deduplicates sections by `section_id` with deterministic ordering.
7. Empty and unrelated search queries cleanly return zero results and signal `insufficient_evidence = True`.
8. Adversarial policy text (`KB-ADVERSARIAL-001`) is retrieved strictly as inert data without executing directives.
9. Citation provenance validation reliably differentiates valid citations from hallucinated section references (Level 1 provenance check).
10. Section derivation is automatically integrated into dataset ingestion and also available via standalone CLI commands (`chunk-policies`, `search-policies`).
11. Phase 1 foundation endpoints and Phase 2 ticket/context APIs continue to function cleanly with zero regressions.

---

## B. Evaluation Scope

- **Components Under Test:**
  - `trustdesk/models/knowledge.py` (`KBSection` model and relationship to `KnowledgeDocument`)
  - `trustdesk/services/knowledge_service.py` (Markdown parsing, header splitting, sub-chunking, database persistence)
  - `trustdesk/services/retrieval/base.py` (`PolicyRetrievalInterface` ABC, `PolicySectionMatch` Pydantic model)
  - `trustdesk/services/retrieval/postgres_fts.py` (`PostgresFtsRetrievalAdapter` implementing FTS, ranking, and deduplication)
  - `trustdesk/services/citation_service.py` (`validate_citation_provenance` Level 1 provenance validation)
  - `trustdesk/services/ingestion.py` (Integrated knowledge section derivation upon ingestion)
  - `trustdesk/cli.py` (`chunk-policies` and `search-policies` commands)
- **Database Operations Under Test:**
  - Alembic migration `002_create_kb_sections_fts.py` execution.
  - GIN indexing and `tsvector` generation on `(title 'A', content 'B')`.
  - `ts_rank_cd` scoring and ordering.
  - Idempotent upsert / replacement on `kb_sections`.
- **Security & Data Integrity Boundaries:**
  - Strict preservation of parent `kb_id` (`KB-REFUND-001`, `KB-WAR-002`, `KB-SHIPPING-001`, `KB-ADVERSARIAL-001`).
  - Inert handling of adversarial document content.
  - Prohibition of unvalidated citations.
- **Explicit Exclusions:**
  - No live LLM provider calls or prompt generation (Phase 4).
  - No Level 3 deterministic date math ($\Delta t$) against order dates (Phase 4).
  - No refund review action proposals or approvals (Phase 5).
  - No React frontend UI components (Phase 6).
  - No Qdrant vector retrieval or embeddings (Post-MVP; `U-011`).

---

## C. Evaluation Environment

- **Required Services:**
  - PostgreSQL 15 running on port 5433 via Docker Compose (`docker-compose.yml`).
- **Required Configuration:**
  ```ini
  DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/trustdesk
  TRUSTDESK_DEMO_TOKEN=demo_secret_token_123
  LOG_LEVEL=DEBUG
  ENVIRONMENT=test
  ```
- **Test Database Strategy:**
  - Integration tests use active PostgreSQL session.
  - Migrations run to `head`.
  - Section tables populated from `data/kb_documents.json` or controlled test fixtures.
  - Cascade truncations ensure clean isolation between tests.

---

## D. Detailed Evaluation Cases

---

### P3-EV-001: Markdown Heading Structural Chunking
- **ID:** `P3-EV-001`
- **Title:** Splitting Markdown Policy Documents on `##` Section Headings
- **Requirement Being Verified:** `docs/architecture.md` §6.1; `docs/implementation_plan.md` §3 (Phase 3.C.1)
- **Test Level:** Unit Test (`tests/unit/test_knowledge_chunking.py`)
- **Preconditions:** Raw markdown documents with multiple `## ` headers (e.g., `KB-REFUND-001`).
- **Execution Procedure:** Call `parse_markdown_sections` with document containing multiple `## ` headings.
- **Expected Outcome:** Returns structured sections with deterministic IDs `{kb_id}#sec-{index}` (`KB-REFUND-001#sec-0`, `KB-REFUND-001#sec-1`, etc.), extracted titles, and body content without header markdown syntax.
- **Pass/Fail Threshold:** Exact section count and correct identifier format matching parent `kb_id`.
- **Actual Result / Evidence:** PASSED. Verified in `test_parse_markdown_sections_heading_splitting` and `test_all_dataset_kb_documents_chunking` in `tests/unit/test_knowledge_chunking.py`.
- **Status:** **PASSED**

---

### P3-EV-002: Long Section Sub-Chunking Boundary
- **ID:** `P3-EV-002`
- **Title:** Sub-Chunking Sections Exceeding 1,500 Characters
- **Requirement Being Verified:** `docs/architecture.md` §6.1; Approved Pre-Implementation Audit Decision Q2
- **Test Level:** Unit Test (`tests/unit/test_knowledge_chunking.py`)
- **Preconditions:** Markdown document containing a section body with >1,500 characters (~2,400 chars).
- **Execution Procedure:** Run `parse_markdown_sections` with `max_chars=1500`.
- **Expected Outcome:** Long section is split into deterministic sub-chunks with unique IDs (`{kb_id}#sec-0-sub-0`, `{kb_id}#sec-0-sub-1`), each $\le$ 1,500 characters on paragraph/sentence boundaries, with parent section title preserved in each sub-chunk.
- **Pass/Fail Threshold:** No sub-chunk exceeds max length; total content is preserved without loss.
- **Actual Result / Evidence:** PASSED. Verified in `test_parse_markdown_sections_subchunking_threshold` in `tests/unit/test_knowledge_chunking.py`.
- **Status:** **PASSED**

---

### P3-EV-003: Database Migration & FTS GIN Index Creation
- **ID:** `P3-EV-003`
- **Title:** `kb_sections` Schema Creation and GIN Index Verification
- **Requirement Being Verified:** `docs/architecture.md` §4.3 (Table 4); `docs/implementation_plan.md` §3 (Phase 3.C.1)
- **Test Level:** Integration Test (`tests/integration/test_retrieval.py`)
- **Preconditions:** Alembic migration `002_create_kb_sections_fts` applied to PostgreSQL database.
- **Execution Procedure:** Inspect database schema via SQLAlchemy `inspect(engine)`.
- **Expected Outcome:** Table `kb_sections` exists; primary key is `section_id`; foreign key to `kb_documents.kb_id` exists with `ON DELETE CASCADE`; GIN index `idx_kb_sections_fts` is active on `search_vector`.
- **Pass/Fail Threshold:** All columns, foreign keys, and indexes match architecture specification.
- **Actual Result / Evidence:** PASSED. Verified in `test_kb_sections_schema_and_indexes` in `tests/integration/test_retrieval.py`.
- **Status:** **PASSED**

---

### P3-EV-004: Keyword Search on Refund Policy Terms
- **ID:** `P3-EV-004`
- **Title:** Ranking Precision for Return and Refund Queries
- **Requirement Being Verified:** `docs/architecture.md` §6.3; `docs/implementation_plan.md` §3 (Phase 3.E)
- **Test Level:** Integration Test (`tests/integration/test_retrieval.py`)
- **Preconditions:** Policies from `data/kb_documents.json` ingested and indexed.
- **Execution Procedure:** Invoke `search_policies(query="refund window 30 days return eligibility", limit=5)`.
- **Expected Outcome:** Sections from `KB-REFUND-001` rank at top of returned list with positive relevance scores (`ts_rank_cd > 0`).
- **Pass/Fail Threshold:** `results[0].kb_id == "KB-REFUND-001"`.
- **Actual Result / Evidence:** PASSED. Verified in `test_refund_policy_search_ranking` in `tests/integration/test_retrieval.py`.
- **Status:** **PASSED**

---

### P3-EV-005: Keyword Search on Shipping Policy Terms
- **ID:** `P3-EV-005`
- **Title:** Ranking Precision for Shipping and Delivery SLA Queries
- **Requirement Being Verified:** `docs/architecture.md` §6.3; `docs/implementation_plan.md` §3 (Phase 3.E)
- **Test Level:** Integration Test (`tests/integration/test_retrieval.py`)
- **Preconditions:** Policies ingested and indexed.
- **Execution Procedure:** Invoke `search_policies(query="shipping delivery transit carrier tracer delay", limit=5)`.
- **Expected Outcome:** Sections from `KB-SHIPPING-001` rank at top of returned list.
- **Pass/Fail Threshold:** `results[0].kb_id == "KB-SHIPPING-001"`.
- **Actual Result / Evidence:** PASSED. Verified in `test_shipping_policy_search_ranking` in `tests/integration/test_retrieval.py`.
- **Status:** **PASSED**

---

### P3-EV-006: Keyword Search on Warranty Policy Terms
- **ID:** `P3-EV-006`
- **Title:** Ranking Precision for Hardware Warranty Queries
- **Requirement Being Verified:** `docs/architecture.md` §6.3; `docs/implementation_plan.md` §3 (Phase 3.E)
- **Test Level:** Integration Test (`tests/integration/test_retrieval.py`)
- **Preconditions:** Policies ingested and indexed.
- **Execution Procedure:** Invoke `search_policies(query="hardware defects warranty stuck pixels", limit=5)`.
- **Expected Outcome:** Sections from `KB-WAR-002` rank at top of returned list.
- **Pass/Fail Threshold:** `results[0].kb_id == "KB-WAR-002"`.
- **Actual Result / Evidence:** PASSED. Verified in `test_warranty_policy_search_ranking` in `tests/integration/test_retrieval.py`.
- **Status:** **PASSED**

---

### P3-EV-007: Multi-Query Retrieval & Deterministic Deduplication
- **ID:** `P3-EV-007`
- **Title:** Multi-Intent Query Search with Section Deduplication
- **Requirement Being Verified:** `docs/architecture.md` §6.3; Approved Pre-Implementation Audit Decision Q2
- **Test Level:** Integration Test (`tests/integration/test_retrieval.py`)
- **Preconditions:** Policies ingested and indexed.
- **Execution Procedure:** Execute search supplying multiple queries covering shipping and refund issues (`["in-transit carrier delay", "refund review approval process"]`).
- **Expected Outcome:** Returned results include sections from both `KB-SHIPPING-001` and `KB-REFUND-001`; every `section_id` in the returned list is unique; results are deterministically ordered.
- **Pass/Fail Threshold:** Both policy IDs present in results; `len(results) == len({r.section_id for r in results})`.
- **Actual Result / Evidence:** PASSED. Verified in `test_multi_query_retrieval_and_deduplication` in `tests/integration/test_retrieval.py`.
- **Status:** **PASSED**

---

### P3-EV-008: Adversarial KB Content Retrieval as Inert Data
- **ID:** `P3-EV-008`
- **Title:** Inert Retrieval of Adversarial Policy Content
- **Requirement Being Verified:** `docs/architecture.md` §6.4; `docs/problem_statement.md` §3.5
- **Test Level:** Integration Test (`tests/integration/test_retrieval.py`)
- **Preconditions:** `KB-ADVERSARIAL-001` ingested and indexed.
- **Execution Procedure:** Invoke `search_policies(query="administrative debug mode master secret", limit=5)`.
- **Expected Outcome:** Returns matching section from `KB-ADVERSARIAL-001` as a typed `PolicySectionMatch` model with text content. No system commands execute, no environment variables or secrets leak.
- **Pass/Fail Threshold:** Result is valid `PolicySectionMatch`; no privilege escalation occurs.
- **Actual Result / Evidence:** PASSED. Verified in `test_adversarial_policy_retrieval_inertness` in `tests/integration/test_retrieval.py`.
- **Status:** **PASSED**

---

### P3-EV-009: Zero Match Query & Insufficient Evidence Signaling
- **ID:** `P3-EV-009`
- **Title:** Empty Search Results and Insufficient Evidence Flag
- **Requirement Being Verified:** `docs/architecture.md` §6.3, §6.5; `docs/implementation_plan.md` §3 (Phase 3.C.5)
- **Test Level:** Integration Test (`tests/integration/test_retrieval.py`)
- **Preconditions:** Standard policy database active.
- **Execution Procedure:** Invoke `search_policies(query="how do I cook lasagna with pasta and cheese?", limit=5)`.
- **Expected Outcome:** Returns empty list `[]`; downstream citation service or caller cleanly handles empty results and signals `insufficient_evidence = True`.
- **Pass/Fail Threshold:** `len(results) == 0`; no database errors raised.
- **Actual Result / Evidence:** PASSED. Verified in `test_zero_match_query_insufficient_evidence` in `tests/integration/test_retrieval.py` and `test_empty_retrieved_evidence_insufficient_evidence` in `tests/unit/test_citation_validation.py`.
- **Status:** **PASSED**

---

### P3-EV-010: Valid Citation Provenance Verification
- **ID:** `P3-EV-010`
- **Title:** Provenance Validation of Accurately Retrieved Policy Citations
- **Requirement Being Verified:** `docs/architecture.md` §6.5 (Level 1); `docs/implementation_plan.md` §3 (Phase 3.C.4)
- **Test Level:** Unit Test (`tests/unit/test_citation_validation.py`)
- **Preconditions:** Evidence set containing `[KB-REFUND-001#sec-0, KB-REFUND-001#sec-1]`.
- **Execution Procedure:** Call `validate_citation_provenance` with cited sections `[KB-REFUND-001#sec-0]`.
- **Expected Outcome:** Returns `ProvenanceResult(has_valid_provenance=True, invalid_citations=[])`.
- **Pass/Fail Threshold:** `has_valid_provenance is True`; `invalid_citations` is empty.
- **Actual Result / Evidence:** PASSED. Verified in `test_valid_citation_provenance` in `tests/unit/test_citation_validation.py`.
- **Status:** **PASSED**

---

### P3-EV-011: Hallucinated Citation Provenance Rejection
- **ID:** `P3-EV-011`
- **Title:** Rejection of Citations Not Present in Retrieved Evidence Set
- **Requirement Being Verified:** `docs/architecture.md` §6.5 (Level 1); `docs/implementation_plan.md` §3 (Phase 3.C.4)
- **Test Level:** Unit Test (`tests/unit/test_citation_validation.py`)
- **Preconditions:** Evidence set containing `[KB-REFUND-001#sec-0]`.
- **Execution Procedure:** Call `validate_citation_provenance` with cited section `KB-REFUND-001#sec-99` or `KB-UNKNOWN#sec-0`.
- **Expected Outcome:** Returns `ProvenanceResult(has_valid_provenance=False, invalid_citations=[...])` identifying the unretrieved reference.
- **Pass/Fail Threshold:** `has_valid_provenance is False`; invalid reference captured in `invalid_citations`.
- **Actual Result / Evidence:** PASSED. Verified in `test_hallucinated_citation_provenance_rejected` and `test_unknown_parent_kb_id_rejected` in `tests/unit/test_citation_validation.py`.
- **Status:** **PASSED**

---

### P3-EV-012: Ingestion Pipeline Automatic Chunking Integration
- **ID:** `P3-EV-012`
- **Title:** End-to-End Ingestion Populates Both `kb_documents` and `kb_sections`
- **Requirement Being Verified:** Approved Pre-Implementation Audit Decision Q4
- **Test Level:** Integration Test (`tests/integration/test_ingestion.py`)
- **Preconditions:** PostgreSQL database ready.
- **Execution Procedure:** Call `ingest_dataset(session=session, data_dir="./data")`.
- **Expected Outcome:** `kb_documents` is populated, followed by automatic section derivation populating `kb_sections`. Re-running ingestion produces identical row counts without error.
- **Pass/Fail Threshold:** `summary["kb_sections"] == 9`; repeated execution is idempotent.
- **Actual Result / Evidence:** PASSED. Verified in `test_ingest_dataset_derives_kb_sections` and `test_ingestion_idempotency_and_repeatability` in `tests/integration/test_ingestion.py`.
- **Status:** **PASSED**

---

### P3-EV-013: Standalone CLI Chunking & Search Commands
- **ID:** `P3-EV-013`
- **Title:** Execution of CLI Management Commands `chunk-policies` and `search-policies`
- **Requirement Being Verified:** `docs/implementation_plan.md` §3 (Phase 3.H); Approved Pre-Implementation Audit Decision Q4
- **Test Level:** Integration Test / CLI Invocation (`tests/integration/test_retrieval.py`)
- **Preconditions:** Populated `kb_documents`.
- **Execution Procedure:** Execute CLI commands `python -m trustdesk.cli chunk-policies` and `python -m trustdesk.cli search-policies "refund" "window" --limit 3`.
- **Expected Outcome:** `chunk-policies` outputs successful section derivation count; `search-policies` outputs matching policy section matches with ranking scores; exit code is 0.
- **Pass/Fail Threshold:** Exit code 0; expected CLI summary outputs printed.
- **Actual Result / Evidence:** PASSED. Verified in `test_cli_chunk_policies_and_search` in `tests/integration/test_retrieval.py`.
- **Status:** **PASSED**

---

### P3-EV-014: Phase 1 & Phase 2 Regression Protection
- **ID:** `P3-EV-014`
- **Title:** Regression Protection Across Phase 1 and Phase 2 Test Suites
- **Requirement Being Verified:** AI Execution Rules 10 & 15
- **Test Level:** Full Regression Suite
- **Preconditions:** Phase 3 schema migrations and models active.
- **Execution Procedure:** Run full test suite:
  ```bash
  pytest tests/unit tests/integration
  ```
- **Expected Outcome:** All 48 pre-existing unit and integration tests plus all 22 new Phase 3 tests pass with 100% success.
- **Pass/Fail Threshold:** 0 failures, 0 errors across 70 total tests.
- **Actual Result / Evidence:** PASSED. All 70 tests passed in 7.48s with 0 failures and 0 errors.
- **Status:** **PASSED**
