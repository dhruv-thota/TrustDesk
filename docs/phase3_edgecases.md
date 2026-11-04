# Phase 3 — Edge Cases & Failure Scenarios: Knowledge-Base Retrieval and Citation Infrastructure

**Document Version:** 1.1.0  
**Phase:** Phase 3 — Knowledge-Base Retrieval and Citation Infrastructure  
**Status:** Verified Post-Implementation Specification  
**Role:** Senior Software Architect, Test Architect & QA Engineer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md) (§3.4, §3.5, §4)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md) (§4.3, §6.1–6.5)  
- [docs/implementation_plan.md](file:///Users/dhruv/Desktop/TrustDesk/docs/implementation_plan.md) (§2, §3 Phase 3)  
- [docs/conventions.md](file:///Users/dhruv/Desktop/TrustDesk/docs/conventions.md) (§1.2, §2, §3, §6, §7)  
- [docs/unresolved.md](file:///Users/dhruv/Desktop/TrustDesk/docs/unresolved.md) (`U-005`, `U-007`, `U-011`)

---

## A. Phase Overview

- **Phase Number & Name:** Phase 3 — Knowledge-Base Retrieval and Citation Infrastructure
- **Objective:** Build the deterministic RAG retrieval foundation without requiring a live LLM by implementing policy document sectioning, PostgreSQL Full-Text Search (FTS) indexing, the `PolicyRetrievalInterface` abstraction, and citation provenance validation.
- **Relevant Implementation Plan Sections:** `docs/implementation_plan.md` §3 (Phase 3)
- **Dependencies:** Phase 1 complete (raw knowledge base documents persisted in `kb_documents`); Phase 2 complete (authenticated ticket and context APIs active).
- **Scope Boundaries:**
  - *Included:* Alembic migration for `kb_sections` and GIN index `idx_kb_sections_fts`, `KBSection` SQLAlchemy ORM model, `PolicyRetrievalInterface` abstraction, `PostgresFtsRetrievalAdapter` with PostgreSQL FTS (`plainto_tsquery`, `ts_rank_cd`), markdown heading sectioning with deterministic IDs `{kb_id}#sec-{index}`, long section sub-chunking (>1,500 characters), multi-query result merging and deduplication, citation provenance validation service, CLI commands (`chunk-policies`, `search-policies`), and automated unit/integration tests.
  - *Excluded:* Live LLM provider calls or prompt assembly (Phase 4); Level 3 deterministic date math ($\Delta t$) against order delivery dates (Phase 4); sensitive action proposal and approval (Phase 5); React UI components (Phase 6); Qdrant vector retrieval or embeddings (Post-MVP; `U-011`).
- **Related Unresolved Decision IDs:**
  - `U-005`: Authoritative Policy Eligibility Rules & Reference Events (Phase 3 retrieval unblocked via `data/kb_documents.json`; Phase 4 date checks pending).
  - `U-007`: Retrieval Parameter Tuning & Multi-Intent Strategy (Phase 3 baseline approved; empirical tuning deferred to Phase 7).
  - `U-011`: Post-MVP Semantic Retrieval (Qdrant) Integration (Confirmed deferred to post-MVP).

---

## B. Pre-Implementation Anticipated Edge Cases

The following edge cases and boundary failure scenarios are derived directly from the authoritative problem statement, architecture, implementation plan, and approved Phase 3 baseline constraints.

---

### P3-EC-001: Zero Matching Policy Sections (Unrelated Inquiry)
- **ID:** `P3-EC-001`
- **Title:** Retrieval on Query With Zero Relevant Policy Matches
- **Category:** Retrieval / Boundary Handling
- **Precondition:** `kb_sections` populated with standard company policies (`KB-REFUND-001`, `KB-WAR-002`, `KB-SHIPPING-001`, `KB-ADVERSARIAL-001`).
- **Trigger/Input:** Caller invokes `search_policies(query="how do I cook lasagna at home?")`.
- **Expected Behavior:** `PostgresFtsRetrievalAdapter` executes search cleanly and returns an empty list (`[]`); citation validation or downstream caller detects empty evidence and flags `insufficient_evidence = True`.
- **Forbidden Behavior:** Raising an unhandled database exception, hallucinating irrelevant sections with zero lexical match, or crashing the process.
- **Verification Method:** Integration test executing `search_policies` with nonsensical/unrelated query terms and asserting `len(results) == 0`.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 3.F.1); `docs/architecture.md` §6.3, §6.5
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_zero_match_query_insufficient_evidence` in `tests/integration/test_retrieval.py` and `test_empty_retrieved_evidence_insufficient_evidence` in `tests/unit/test_citation_validation.py`)

---

### P3-EC-002: Multi-Policy Inquiry Retrieval & Merging
- **ID:** `P3-EC-002`
- **Title:** Customer Inquiry Spanning Multiple Distinct Policy Domains
- **Category:** Retrieval / Multi-Intent Handling
- **Precondition:** `kb_sections` contains shipping (`KB-SHIPPING-001`), refund (`KB-REFUND-001`), and warranty (`KB-WAR-002`) sections.
- **Trigger/Input:** Retrieval executed with multiple queries covering separate domains (e.g., `["in-transit carrier delay", "refund review approval process"]`).
- **Expected Behavior:** Multi-query search retrieves sections from both `KB-SHIPPING-001` and `KB-REFUND-001` (or `KB-WAR-002`), merges them, deduplicates by `section_id`, and ranks results deterministically using `ts_rank_cd`.
- **Forbidden Behavior:** Returning duplicate sections with identical `section_id`, dropping sections from one policy entirely, or introducing non-deterministic ordering.
- **Verification Method:** Integration test passing compound queries to the retrieval adapter and asserting returned sections contain both policy IDs with unique section IDs.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 3.F.2); `docs/architecture.md` §6.3
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_multi_query_retrieval_and_deduplication` in `tests/integration/test_retrieval.py`)

---

### P3-EC-003: Citation Hallucination Detection (Unretrieved Section Reference)
- **ID:** `P3-EC-003`
- **Title:** Citation References a Validly Formatted Section ID Not Present in Retrieved Evidence
- **Category:** Citation Provenance / Hallucination Prevention
- **Precondition:** Retrieved evidence set contains `[KB-REFUND-001#sec-0, KB-REFUND-001#sec-1]`.
- **Trigger/Input:** Caller presents cited section list containing `[KB-REFUND-001#sec-0, KB-REFUND-001#sec-99]`.
- **Expected Behavior:** `validate_citation_provenance` inspects cited references against retrieved evidence; detects that `KB-REFUND-001#sec-99` is not in the retrieved set; returns `ProvenanceResult(has_valid_provenance=False, invalid_citations=[...])`.
- **Forbidden Behavior:** Returning `has_valid_provenance = True` solely because `KB-REFUND-001` exists, or silently dropping the unretrieved citation.
- **Verification Method:** Unit test asserting `has_valid_provenance == False` when one or more cited section IDs are absent from retrieved evidence.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 3.F.3); `docs/architecture.md` §6.5 (Level 1)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_hallucinated_citation_provenance_rejected` in `tests/unit/test_citation_validation.py`)

---

### P3-EC-004: Adversarial Policy Ingestion and Inert Retrieval
- **ID:** `P3-EC-004`
- **Title:** Search Matches Adversarial Document `KB-ADVERSARIAL-001`
- **Category:** Security / Data Inertness
- **Precondition:** `KB-ADVERSARIAL-001` is ingested and chunked in `kb_sections`.
- **Trigger/Input:** Caller invokes search with adversarial keywords (e.g., `"administrative debug mode master secret"`).
- **Expected Behavior:** `PostgresFtsRetrievalAdapter` returns matching section as a standard, inert `PolicySectionMatch` Pydantic object containing text data. No system directive is executed, no secrets are disclosed, and no permissions are escalated.
- **Forbidden Behavior:** Executing embedded shell commands, altering backend authorization, or bypassing retrieval ranking.
- **Verification Method:** Integration test asserting retrieved adversarial section is returned strictly as typed data.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 3.F.4); `docs/problem_statement.md` §3.5
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_adversarial_policy_retrieval_inertness` in `tests/integration/test_retrieval.py`)

---

### P3-EC-005: Policy Document Without Markdown `##` Subheaders
- **ID:** `P3-EC-005`
- **Title:** Chunking a Policy Document That Contains No Second-Level Markdown Headings
- **Category:** Knowledge Chunking / Schema Normalization
- **Precondition:** A policy document in `kb_documents` contains only a top-level `# Title` and plain text body with no `## ` section headers.
- **Trigger/Input:** Knowledge chunking service processes the document.
- **Expected Behavior:** Chunking service treats the entire document content as a single section with deterministic identifier `{kb_id}#sec-0`, setting `section_title` to the document title or a standardized header, and indexes it into `kb_sections`.
- **Forbidden Behavior:** Raising an `IndexError`, dropping the document from indexing, or generating malformed empty section IDs.
- **Verification Method:** Unit test with a synthetic markdown document lacking `##` headers asserting a single `{kb_id}#sec-0` record is created.
- **Related Requirement:** `docs/architecture.md` §6.1; Approved Pre-Implementation Audit Decision Q1
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_parse_markdown_sections_no_subheaders` in `tests/unit/test_knowledge_chunking.py`)

---

### P3-EC-006: Empty or Whitespace-Only Retrieval Query
- **ID:** `P3-EC-006`
- **Title:** Retrieval Invocation With Empty, None, or Whitespace-Only String
- **Category:** API / Retrieval Input Sanitization
- **Precondition:** Retrieval adapter initialized with valid database session.
- **Trigger/Input:** Caller invokes `search_policies(query="")`, `search_policies(query="   ")`, or multiple empty queries.
- **Expected Behavior:** Adapter sanitizes input, short-circuits execution before invoking PostgreSQL tsquery, and cleanly returns an empty list (`[]`).
- **Forbidden Behavior:** Passing an empty string to `plainto_tsquery` causing database syntax errors or returning all rows in the table.
- **Verification Method:** Unit and integration tests passing empty and whitespace queries to `search_policies` asserting `[]` return.
- **Related Requirement:** `docs/conventions.md` §6; Approved Pre-Implementation Audit Decision Q1
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_empty_and_whitespace_query_sanitization` in `tests/integration/test_retrieval.py` and `test_parse_markdown_empty_content` in `tests/unit/test_knowledge_chunking.py`)

---

### P3-EC-007: Section Derivation and Indexing Idempotency
- **ID:** `P3-EC-007`
- **Title:** Repeated Ingestion or Re-Chunking Over Identical Raw Documents
- **Category:** Data Integrity / Idempotency
- **Precondition:** `kb_sections` already populated from `kb_documents`.
- **Trigger/Input:** Operator executes `python -m trustdesk.cli chunk-policies` or `python -m trustdesk.cli ingest` multiple consecutive times.
- **Expected Behavior:** Sections are updated or replaced idempotently. No primary key collision errors occur on `section_id`; total section count remains identical; deterministic IDs `{kb_id}#sec-{index}` remain completely stable.
- **Forbidden Behavior:** Duplicating records, mutating section IDs, or generating orphaned child records.
- **Verification Method:** Automated test executing `chunk_all_documents()` twice and asserting identical row counts and section IDs.
- **Related Requirement:** `docs/implementation_plan.md` §3 (Phase 3.C.1); Approved Pre-Implementation Audit Decision Q4
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_section_derivation_and_idempotency` in `tests/integration/test_retrieval.py` and `test_ingest_dataset_derives_kb_sections` in `tests/integration/test_ingestion.py`)

---

### P3-EC-008: Citation Referencing Unknown Parent Policy (`kb_id`)
- **ID:** `P3-EC-008`
- **Title:** Citation Referencing Completely Unrecognized Policy ID
- **Category:** Citation Provenance / Validation
- **Precondition:** Retrieved evidence contains sections from `KB-REFUND-001`.
- **Trigger/Input:** Citation list contains reference `CitationRef(kb_id="KB-FICTIONAL-999", section_id="KB-FICTIONAL-999#sec-0")`.
- **Expected Behavior:** `validate_citation_provenance` identifies that neither the `kb_id` nor the `section_id` was in the retrieved set; returns `has_valid_provenance = False` with the invalid reference identified.
- **Forbidden Behavior:** Raising `KeyError`, throwing unhandled exceptions, or marking provenance valid.
- **Verification Method:** Unit test passing unknown `kb_id` to `validate_citation_provenance` and asserting validation failure.
- **Related Requirement:** `docs/architecture.md` §6.5; Approved Pre-Implementation Audit Decision Q1
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_unknown_parent_kb_id_rejected` in `tests/unit/test_citation_validation.py`)

---

### P3-EC-009: Sub-Chunking Long Markdown Sections (>1,500 Characters)
- **ID:** `P3-EC-009`
- **Title:** Policy Section Exceeding Character Threshold Sub-Chunked Deterministically
- **Category:** Knowledge Chunking / Boundary Splitting
- **Precondition:** A policy section contains 2,400 characters of text under a single `## ` header.
- **Trigger/Input:** Chunking service processes the document with 1,500-character sub-chunking boundary.
- **Expected Behavior:** The long section is split into deterministic sub-chunks (`{kb_id}#sec-{index}-sub-0`, `{kb_id}#sec-{index}-sub-1`) on paragraph/sentence boundaries while preserving parent `kb_id` and heading title context across both sub-chunks.
- **Forbidden Behavior:** Truncating text past 1,500 characters, discarding data, or creating non-deterministic IDs.
- **Verification Method:** Unit test with synthetic long section asserting sub-chunks are generated and total content is preserved.
- **Related Requirement:** `docs/architecture.md` §6.1; Approved Pre-Implementation Audit Decision Q2
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_parse_markdown_sections_subchunking_threshold` in `tests/unit/test_knowledge_chunking.py`)

---

### P3-EC-010: Citation Validation on Empty Citation List
- **ID:** `P3-EC-010`
- **Title:** Provenance Validation When No Policy Citations Are Claimed
- **Category:** Citation Provenance / Boundary Condition
- **Precondition:** Retrieved evidence contains standard policy sections.
- **Trigger/Input:** Caller invokes `validate_citation_provenance(cited_sections=[], retrieved_sections=[...])`.
- **Expected Behavior:** Returns `ProvenanceResult(has_valid_provenance=True, invalid_citations=[], insufficient_evidence=False)`. An empty citation list contains zero ungrounded citations.
- **Forbidden Behavior:** Raising an error on empty list or reporting validation failure.
- **Verification Method:** Unit test asserting `has_valid_provenance == True` for empty citations input.
- **Related Requirement:** `docs/architecture.md` §6.5; Approved Pre-Implementation Audit Decision Q1
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_empty_citations_valid` and `test_empty_citations_and_empty_retrieved` in `tests/unit/test_citation_validation.py`)

---

## C. Implementation-Discovered Edge Cases

*(This section records edge cases discovered during active coding, data inspection, integration, or failure testing. Numbering continues sequentially from `P3-EC-011` per `docs/conventions.md` §7.2.)*

---

### P3-EC-011: Parent Policy Title Context Visibility in PostgreSQL Full-Text Search
- **ID:** `P3-EC-011`
- **Title:** Lexical Disconnect Between Document Title and Sub-Section Headers in FTS
- **Category:** Retrieval / Lexical Coverage
- **Precondition:** Ingested policy documents in `kb_documents` define overall policy domain in document title (e.g. `# Standard Return and Refund Policy` or `title: "Shipping and Delivery SLA"`), while sub-section headers focus narrowly on procedure steps (e.g. `## 1. Overview and Eligibility Window` or `## 2. In-Transit Delays and Lost Shipments`).
- **Trigger/Input:** Caller invokes `search_policies` with compound domain phrases such as `"refund window"` or `"shipping delay"`.
- **Condition & Root Cause:** PostgreSQL FTS `plainto_tsquery('english', 'refund window')` constructs a strict boolean `AND` across terms (`'refund' & 'window'`). Section 1 of `KB-REFUND-001` contains the terms "return" and "window", but the root word "refund" only appears in the parent document title and Section 3. If sections only store the isolated sub-heading (e.g. `"1. Overview and Eligibility Window"`), the section fails the boolean `AND` match despite being the authoritative policy text for refund windows.
- **Implemented Resolution:** `parse_markdown_sections()` in `trustdesk/services/knowledge_service.py` preserves parent document title context by constructing `section_title` as `f"{doc_title} — {raw_heading_title}"`. Because `kb_sections.search_vector` computes a weighted `tsvector` with `section_title` weighted `'A'`, the parent document's policy keywords (e.g., "refund", "shipping", "warranty") are automatically indexed into every child section's search vector with top priority, allowing compound domain queries to match their authoritative procedure sections accurately.
- **Verification Method:** Integration tests executing compound domain queries and asserting that the top matching sections correspond to the expected policy documents.
- **Related Requirement:** `docs/architecture.md` §6.1, §6.3; `docs/implementation_plan.md` §3 (Phase 3.C.1, 3.E)
- **Unresolved Dependencies:** None.
- **Verification Status:** **PASSED** (Verified via `test_refund_policy_search_ranking` and `test_shipping_policy_search_ranking` in `tests/integration/test_retrieval.py`)
