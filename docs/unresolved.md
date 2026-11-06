# TrustDesk — Unresolved Decisions & Dependencies Register

**Document Version:** 1.1.0  
**Status:** Active Living Register  
**Role:** Technical Architect & Documentation Maintainer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md)

---

## Maintenance Protocol & Rules

This register is a permanent, living document designed to prevent unverified assumptions from silently becoming implementation decisions.

### Mandatory Maintenance Rules
1. **Consultation:** Read `docs/unresolved.md` at the beginning of every documentation, planning, or implementation task.
2. **Review:** Review every open item that the task could have affected upon task completion.
3. **Closing Evidence:** Mark an item as resolved only when its documented resolution criteria have been objectively met with concrete evidence (inspected files, verified test results, or approved technical decisions).
4. **Preservation:** Move resolved items to the [Resolved Items](#6-resolved-items) section while preserving their stable ID (`U-xxx`). Never delete the historical record of an item.
5. **No Assumptions:** Never close an item solely because a proposed solution or design convention exists.
6. **New Discoveries:** Add newly discovered uncertainties using the next sequential identifier (`U-014`, `U-015`, etc.).
7. **Deduplication:** Avoid duplicate entries; update existing items when new context clarifies an existing question.
8. **Reopening:** Do not reopen a resolved item without documenting the new evidence, contradiction, or regression.
9. **Scope Control:** Do not introduce out-of-scope features or speculative abstractions merely to resolve an item.
10. **Post-MVP Isolation:** Do not treat deferred post-MVP enhancements (e.g., Qdrant, JWT/RBAC) as blockers for MVP completion.
11. **Architecture Synchronization:** If an item resolution modifies architectural behavior, update `docs/architecture.md` only when explicitly authorized.
12. **Integrity:** Preserve all architectural decisions already finalized in authoritative project documents.

---

## Summary Dashboard

| Category | Open | Blocked | Resolved | Total |
|---|:---:|:---:|:---:|:---:|
| 1. Open Architectural & Behavioral Decisions | 0 | 0 | 4 | 4 |
| 2. Dataset & Policy Dependencies | 0 | 0 | 4 | 4 |
| 3. Implementation & Configuration Decisions | 1 | 0 | 2 | 3 |
| 4. Verification Dependencies | 0 | 0 | 1 | 1 |
| 5. Post-MVP Deferred Items | 2 | 0 | 0 | 2 |
| **Total Tracked Items** | **3** | **0** | **11** | **14** |

*Note: All Phase 7 decision contracts (`U-004` Option B, `U-009` metric formulas) are fully implemented and verified. `U-007` maintains approved baseline parameters; empirical retrieval tuning remains open for post-MVP benchmarking. Zero items are blocked.*

---

## 1. Open Architectural and Behavioral Decisions

*(No active items in this category. All architectural and behavioral decisions for the MVP core pipeline are resolved.)*

---

## 2. Dataset and Policy Dependencies

*(No active items in this category. All dataset schema and evaluation dataset contracts are resolved. See Section 6 for U-003, U-004, and U-013.)*

---

## 3. Implementation and Configuration Decisions

### U-007 — Retrieval Parameter Tuning and Multi-Intent Strategy
- **ID:** `U-007`
- **Earliest Resolution Phase:** **Phase 7** (Background Jobs, Execution Traces, and Evaluation)
- **Blocking Status:** Non-blocking for Phases 1–6; **Open for Phase 7 empirical evaluation benchmarking**
- **Decision or Uncertainty:** What are the tuned default parameters for PostgreSQL Full-Text Search (FTS)? Specifically:
  - What character/token threshold should trigger sub-chunking of long markdown sections?
  - What weights should be assigned to title vs. body text in `setweight` (`'A'` vs `'B'`)?
  - How are multi-intent queries decomposed, merged, and deduplicated without inventing arbitrary relevance score cutoffs?
- **Phase 3 Baseline Retrieval Parameters (Approved 2026-11-03):**
  - **Heading Chunking:** Split policy documents on Markdown `## ` headings.
  - **Sub-chunking Threshold:** Sections exceeding 1,500 characters are sub-chunked, preserving parent policy identity, heading title context, and deterministic section IDs.
  - **FTS Weights:** `section_title` weighted `'A'`, `section_content` weighted `'B'`.
  - **Ranking Algorithm:** PostgreSQL `ts_rank_cd(search_vector, query)`.
  - **Retrieval Limit:** Configurable default `limit = 5`.
  - **Multi-Query Handling:** Support multiple explicit retrieval queries, merge matching sections, deduplicate by `section_id`, and rank deterministically.
  - **Scope Boundary:** No LLM-based query decomposition in Phase 3.
  - **Empirical Tuning:** Fine-grained retrieval parameter and threshold tuning against `data/eval_cases.jsonl` is deferred to Phase 7.
- **Why It Matters:** Affects retrieval recall, ranking precision, prompt token size, and the likelihood of missing relevant policies in multi-issue customer tickets.
- **Resolution Criteria:** Complete Phase 3 baseline implementation. Benchmark FTS retrieval on actual policy documents against evaluation cases in `data/eval_cases.jsonl` in Phase 7 to finalize empirical ranking thresholds.
- **Status:** **Open** *(Phase 3 baseline approved; empirical tuning benchmarking preserved as open for production tuning)*
- **Reference:** `docs/architecture.md` §6.1, §6.3; `docs/problem_statement.md` §3.4

---

## 4. Verification Dependencies

*(No active items in this category. All evaluation metric formulas, denominators, and scoring rules are resolved. See Section 6 for U-009.)*

---

## 5. Post-MVP Deferred Decisions

### U-011 — Post-MVP Semantic Retrieval (Qdrant) Integration Decision
- **ID:** `U-011`
- **Earliest Resolution Phase:** **Post-MVP**
- **Blocking Status:** **Non-blocking for MVP** (Explicitly deferred)
- **Decision or Uncertainty:** When and on what empirical basis should Qdrant vector retrieval be introduced to replace or complement PostgreSQL Full-Text Search?
- **Why It Matters:** Guarantees that Qdrant remains strictly post-MVP and is not implemented prematurely. When evaluated, the decision must be backed by comparative retrieval recall, latency, and cost data.
- **Resolution Criteria:** Complete MVP implementation and baseline evaluation using PostgreSQL FTS. Execute a comparative benchmark between FTS and Qdrant hybrid search on `data/eval_cases.jsonl`, documenting the recommendation.
- **Status:** **Open** *(Deferred to Post-MVP)*
- **Reference:** `docs/architecture.md` §3.8, §6.6, §13, §14.1; `docs/problem_statement.md` §4

---

### U-012 — Post-MVP Production Authentication & RBAC Architecture
- **ID:** `U-012`
- **Earliest Resolution Phase:** **Post-MVP**
- **Blocking Status:** **Non-blocking for MVP** (Explicitly deferred)
- **Decision or Uncertainty:** What production identity platform and RBAC role model should replace the server-validated demo bearer token post-MVP?
- **Why It Matters:** Prevents scope creep during MVP development while preserving a clean architectural migration path toward enterprise identity standards (JWT / OIDC / OAuth2).
- **Resolution Criteria:** Completion of MVP demonstration. Production deployment specification approved, defining the OIDC provider, JWT signature validation algorithm, and role hierarchy (`support_agent`, `support_supervisor`, `system_admin`).
- **Status:** **Open** *(Deferred to Post-MVP)*
- **Reference:** `docs/architecture.md` §9.1, §9.3, §13, §14.4; `docs/problem_statement.md` §4, §5

---

## 6. Resolved Items

*(This section records items moved from active sections upon fulfilling their resolution criteria. History and stable IDs are preserved.)*

### U-010 — Local Development Orchestration and Execution Baseline
- **ID:** `U-010`
- **Category:** 3. Implementation & Configuration Decisions
- **Earliest Resolution Phase:** Phase 1 (Foundation, Database, and Dataset Ingestion)
- **Resolved Date:** 2026-11-03 (Updated with explicit Python 3.12.6 approval)
- **Resolution Authority:** User Explicit Approval (Option 1: Python 3.12.6 Local Development Baseline)
- **Approved Baseline:**
  - **Python Runtime:** Python 3.12.6 executed within a local Python virtual environment (`.venv`), with `pyproject.toml` maintaining `requires-python = ">=3.11"`.
  - **Primary Relational Database:** PostgreSQL 15 containerized via Docker Compose (`docker-compose.yml`), binding to host port 5433 (to avoid conflicts with any pre-existing host PostgreSQL services on port 5432) with volume persistence.
  - **Asynchronous Task Queue (Phase 7):** Redis 7+ added to Docker Compose alongside PostgreSQL for RQ background worker execution.
  - **Support-Agent Dashboard (Phase 6):** React 18+ with Vite and Tailwind CSS executed locally via Node.js.
  - **Configuration Template:** `.env.example` defining `DATABASE_URL` (pointing to port 5433), `TRUSTDESK_DEMO_TOKEN`, `LOG_LEVEL`, and `ENVIRONMENT`.
- **Why It Matters / Rationale:** Establishes a predictable, reproducible local development and automated testing environment across engineering machines, eliminating host-dependent database installations while preserving lightweight local execution of Python services and pytests.
- **Status:** **RESOLVED**
- **Reference:** `docs/architecture.md` §2.1, §14.2, §14.3; `docs/problem_statement.md` §6

---

### U-003 — Source Dataset Schema and Integrity Verification
- **ID:** `U-003`
- **Category:** 2. Dataset and Policy Dependencies
- **Earliest Resolution Phase:** Phase 1 (Foundation, Database, and Dataset Ingestion)
- **Resolved Date:** 2026-11-02
- **Resolution Authority:** User Explicit Approval (Option C Authorization) and verified inspection of `data/` source files (`customers.json`, `orders.json`, `tickets.json`, `kb_documents.json`).
- **Approved Schema Contract & Ingestion Rules:**
  - `customers`: `customer_id` (VARCHAR(64), PK), `email` (VARCHAR(255), NULLABLE), `name` (VARCHAR(255)), `metadata` (JSONB), `created_at` (TIMESTAMPTZ).
  - `orders`: `order_id` (VARCHAR(64), PK), `customer_id` (VARCHAR(64), FK -> customers, NOT NULL), `order_date` (TIMESTAMPTZ, NOT NULL), `delivery_date` (TIMESTAMPTZ, NULLABLE), `status` (VARCHAR(32)), `total_amount` (NUMERIC(10, 2)), `items` (JSONB).
  - `tickets`: `ticket_id` (VARCHAR(64), PK), `customer_id` (VARCHAR(64), FK -> customers, NOT NULL), `order_id` (VARCHAR(64), FK -> orders, NULLABLE), `subject` (VARCHAR(255)), `message` (TEXT), `status` (VARCHAR(32)), `created_at` (TIMESTAMPTZ), `raw_metadata` (JSONB, DEFAULT '{}').
  - `kb_documents`: `kb_id` (VARCHAR(64), PK), `title` (VARCHAR(255)), `category` (VARCHAR(64)), `raw_content` (TEXT), `updated_at` (TIMESTAMPTZ).
  - *Foreign Key Reference Policy:*
    - Naturally absent optional foreign keys (`order_id: null` / empty) persist `order_id = NULL` cleanly.
    - Invalid non-null foreign keys (e.g., ticket references missing `order_id`) store `order_id = NULL` and preserve the raw string in `raw_metadata["unresolved_order_id"] = "ORD-MISSING-..."` with a structured warning log.
    - Missing mandatory parent entities (unresolvable `customer_id`) are rejected/quarantined from insertion, preventing orphaned records.
  - *Idempotency & Deduplication:* PostgreSQL `ON CONFLICT (PK) DO UPDATE` ensures repeated ingestion runs without duplicating records or generating integrity errors.
- **Why It Matters / Rationale:** Eliminates speculative schema assumptions, guarantees exact preservation of original identifiers (`KB-REFUND-001`, `KB-ADVERSARIAL-001`), and enforces strict relational integrity with non-destructive metadata quarantine.
- **Status:** **RESOLVED**
- **Reference:** `docs/architecture.md` §4.1, §4.3; `docs/problem_statement.md` §3.1

---

### U-013 — Tool Catalog Ingestion and Scope Enforcement
- **ID:** `U-013`
- **Category:** 2. Dataset and Policy Dependencies
- **Earliest Resolution Phase:** Phase 1 (Foundation, Database, and Dataset Ingestion)
- **Resolved Date:** 2026-11-02
- **Resolution Authority:** User Explicit Approval (Option C Authorization) and verified inspection of `data/tool_catalog.json`.
- **Approved Schema Contract & Enforcement Rules:**
  - `tool_catalog.json` defines tool entries containing `name` (string), `description` (string), `parameters` (JSON schema object), `is_sensitive` (boolean), `is_supported` (boolean), and `in_scope` (boolean).
  - Ingestion registers all catalog tools in the system tool registry.
  - The backend explicitly restricts operational action support: `start_refund_review` is marked `is_supported = True` / `in_scope = True`.
  - Out-of-scope operational actions (`create_replacement_order`, `issue_direct_refund`) are explicitly flagged `is_supported = False` / `in_scope = False`, preventing unauthorized execution while maintaining catalog awareness.
- **Why It Matters / Rationale:** Enforces TrustDesk's core architectural boundary that `start_refund_review` is the only operational action permitted in scope, preventing feature creep or unintended automated actions.
- **Status:** **RESOLVED**
- **Reference:** `docs/problem_statement.md` §3.1, §3.5; `docs/architecture.md` §8.5

---

### U-002 — Draft Grounding & Validation Result Semantics
- **ID:** `U-002`
- **Category:** 1. Open Architectural and Behavioral Decisions
- **Earliest Resolution Phase:** Phase 4 (AI Triage and Grounded Draft Generation)
- **Resolved Date:** 2026-11-03
- **Resolution Authority:** User Explicit Approval (Option 1 with 3-Level Constraints)
- **Approved Decision & Implemented Semantics:**
  - **Core Principle:** Grounding measures whether a generated response is supported by retrieved policy evidence and verified facts; it does NOT measure whether a customer is eligible for a refund or warranty claim.
  - **3-Level Validation Engine:**
    - **Level 1 (Citation Provenance):** `has_valid_provenance = True` strictly when every cited `(kb_id, section_id)` pair belongs to the retrieved policy evidence set (`retrieved_sections`). Validated via `validate_citation_provenance()` in `trustdesk/services/citation_service.py`. Hallucinated or unretrieved section citations set `has_valid_provenance = False`, `is_grounded = False`, and `escalation_suggested = True`.
    - **Level 2 (Claim Support & Discount Defense):** Direct quotes/snippets extracted by the model are verified against cited retrieved sections. Unsupported commercial promises, percentage discounts, and promotional coupon codes are scanned deterministically via regex (`\b(?:\d+%\s*off|discount|promo|coupon)\b`); if detected without an authoritative promotional policy section, the draft is flagged as ungrounded (`is_grounded = False`, `escalation_suggested = True`).
    - **Level 3 (Deterministic Temporal Policy Consistency):** Backend independently calculates return and warranty windows from authoritative dates ($\Delta t = \text{ticket.created\_at} - \text{order.delivery\_date}$). If a draft claims refund or warranty eligibility for an expired order ($\Delta t > 30$ days), Level 3 check detects the contradiction and sets `is_grounded = False` and `escalation_suggested = True`.
  - **Grounded Ineligibility:** A draft accurately explaining that a customer is ineligible under policy rules (e.g., delivered 45 days ago, exceeding 30-day window) is **100% grounded** (`is_grounded = True`, `escalation_suggested = False`).
  - **Preserved Architectural Limitation:** Valid citation IDs and direct snippets do not prove arbitrary natural-language claims. Full automated natural-language inference (NLI) claim verification remains an architectural limitation in MVP; ambiguous claims trigger `escalation_suggested = True`.
- **Implementation Evidence:** Implemented in `trustdesk/services/draft_service.py` and `trustdesk/schemas/draft.py`; verified by unit tests in `tests/unit/test_draft_grounding.py` and integration tests in `tests/integration/test_ai_workflows.py` (`test_draft_claims_eligibility_on_expired_order_flagged_ungrounded`, `test_draft_grounded_ineligibility_on_expired_order`, `test_draft_hallucinated_citation_rejected`).
- **Status:** **RESOLVED (Phase 4 MVP Grounding Contract Implemented; Level 2 NLI Limitation Preserved)**
- **Reference:** `docs/architecture.md` §4.3 (Table 6), §5.3, §6.5; `docs/problem_statement.md` §3.4; `docs/phase4_edgecases.md` (`P4-EC-004`, `P4-EC-005`, `P4-EC-006`, `P4-EC-011`)

---

### U-005 — Authoritative Policy Eligibility Rules & Reference Events
- **ID:** `U-005`
- **Category:** 2. Dataset and Policy Dependencies
- **Earliest Resolution Phase:** Phase 4 (AI Triage and Grounded Draft Generation)
- **Resolved Date:** 2026-11-03
- **Resolution Authority:** User Explicit Approval (Option C Authorization & Phase 4 Final Decisions)
- **Approved Decision & Authoritative Rules:**
  - **Authoritative Source:** `data/kb_documents.json` (`KB-REFUND-001`, `KB-WAR-002`, `KB-SHIPPING-001`, `KB-ADVERSARIAL-001`).
  - **Refund Window Rule (`KB-REFUND-001`):**
    - Reference event: confirmed `order.delivery_date`.
    - Evaluation date: `ticket.created_at`.
    - Window length: 30 calendar days.
    - Deterministic calculation: $\Delta t = \text{ticket.created\_at} - \text{order.delivery\_date} \le 30 \text{ calendar days}$.
  - **Warranty Window Rule (`KB-WAR-002`):**
    - Reference event: confirmed `order.delivery_date`.
    - Evaluation date: `ticket.created_at`.
    - Window length: 365 calendar days (1 year).
    - Deterministic calculation: $\Delta t = \text{ticket.created\_at} - \text{order.delivery\_date} \le 365 \text{ calendar days}$.
  - **Missing Context & Fallback Escalation Policy:**
    - If a refund or warranty inquiry requires eligibility verification but:
      1. The ticket has no linked order (`order_id is None`),
      2. The linked order does not exist in `orders`, or
      3. The order delivery date is missing (`delivery_date is None`),
    - Then:
      - The system strictly **must not** invent a delivery date.
      - The system strictly **must not** substitute `order.order_date`.
      - The system strictly **must not** assert eligibility or ineligibility.
      - The system **must** set `escalation_suggested = True`.
      - The draft service attaches an explicit context warning explaining why eligibility could not be determined.
  - **Preserved Non-Date Policy Conditions:**
    - Packaging requirements, customer damage exclusions, and authorized use clauses from `KB-REFUND-001` and `KB-WAR-002` are preserved in policy evidence; ambiguous condition claims escalate to human review.
- **Implementation Evidence:** Implemented in `trustdesk/services/draft_service.py` (`_evaluate_temporal_policy`); verified by unit tests in `tests/unit/test_draft_grounding.py` and integration tests in `tests/integration/test_ai_workflows.py` (`test_draft_null_order_id_escalates`, `test_draft_missing_delivery_date_escalates`, `test_authenticated_draft_endpoint_refund_within_window`).
- **Status:** **RESOLVED (Authoritative Reference Events, Windows, and Missing Context Policy Implemented)**
- **Reference:** `docs/architecture.md` §4.5, §8.5; `docs/problem_statement.md` §3.1, §3.4; `data/kb_documents.json`; `docs/phase4_edgecases.md` (`P4-EC-004`, `P4-EC-007`, `P4-EC-008`)

---

### U-006 — Production AI Provider and Model Selection
- **ID:** `U-006`
- **Category:** 3. Implementation and Configuration Decisions
- **Earliest Resolution Phase:** Phase 4 (AI Triage and Grounded Draft Generation)
- **Resolved Date:** 2026-11-03
- **Resolution Authority:** User Explicit Approval (Google Gemini via `google-genai` and `gemini-3.8-flash`)
- **Approved Decision & Architecture:**
  - **Selected Provider:** Google Gemini.
  - **Official SDK:** `google-genai>=2.0.0` added to `pyproject.toml` dependencies.
  - **Default Model:** `gemini-3.8-flash` (retired `gemini-1.5-flash` prohibited).
  - **Configurability:** Model identifier configurable via `GEMINI_MODEL` environment variable (defaulting to `gemini-3.8-flash`).
  - **Provider Adapter Architecture:** `AIProviderAdapter` ABC in `trustdesk/services/ai/base.py`; `MockAIProvider` in `trustdesk/services/ai/mock_provider.py`; `LiveAIProvider` in `trustdesk/services/ai/live_provider.py`.
  - **Factory Method:** `get_ai_provider()` in `trustdesk/services/ai/__init__.py` selects provider based on `AI_PROVIDER` setting (`"mock"` vs `"gemini"`).
  - **Resilience Contract:** Strict 15-second timeout with at most one bounded retry (1s exponential backoff); structured error capture without leaking `GEMINI_API_KEY`.
  - **Test Isolation Rule:** All automated unit and integration tests run 100% deterministically and offline against `MockAIProvider`. No external network calls in automated testing.
  - **Live Verification Status Note:** Live Gemini API connectivity was **NOT RUN** during automated testing because active production API credentials were not provided in the local test environment. Live provider verification is deferred to deployment with active credentials.
- **Implementation Evidence:** Implemented in `trustdesk/services/ai/` and `trustdesk/core/config.py`; verified via unit tests in `tests/unit/test_ai_failure_handling.py` and integration tests in `tests/integration/test_ai_workflows.py`.
- **Status:** **RESOLVED (Provider Adapter, SDK & Configurable Model Implemented; Live Verification Deferred/Pending Credentials)**
- **Reference:** `docs/architecture.md` §3.7, §7.1; `docs/problem_statement.md` §4; `docs/phase4_edgecases.md` (`P4-EC-001`, `P4-EC-002`)

---

### U-001 — Refund-Review Business-Operation Uniqueness Key
- **ID:** `U-001`
- **Category:** 1. Open Architectural and Behavioral Decisions
- **Earliest Resolution Phase:** Phase 5 (Guardrails and Human-Approved Refund Review)
- **Resolved Date:** 2026-11-04
- **Resolution Authority:** User Explicit Approval (Option 1: Business-Operation Uniqueness Scoped to `(ticket_id, action_type)`)
- **Approved Decision & Implemented Semantics:**
  - **Core Invariant:** Only `start_refund_review` is supported in MVP. `create_replacement_order` and direct monetary refunds are strictly prohibited.
  - **Database Unique Constraint:** Enforced via PostgreSQL partial unique index on `proposed_actions`:
    ```sql
    CREATE UNIQUE INDEX idx_unique_active_refund_review 
    ON proposed_actions (ticket_id, action_type) 
    WHERE status IN ('pending_approval', 'executed');
    ```
  - **Uniqueness Scope:** Scoped to `(ticket_id, action_type)` for active states (`pending_approval`, `executed`). At most one active or executed refund review can exist per ticket.
  - **Terminal State Slot Release:** Actions in terminal `rejected` or confirmed `failed` status do not occupy the active uniqueness slot, permitting a new review proposal to be created for that ticket if warranted.
  - **Separation of Protections:** Request idempotency (`action_idempotency` table via client-supplied `Idempotency-Key` header) and business-operation uniqueness (`idx_unique_active_refund_review`) are strictly separate architectural safeguards.
  - **Multi-Order Policy:** Tickets represent a single customer support thread linked to at most one order (`tickets.order_id`). Multi-order support outside the approved MVP schema is strictly excluded. Repeated proposals on the same ticket while an active review exists return `409 Conflict` (`ACTIVE_REVIEW_ALREADY_EXISTS`).
- **Why It Matters / Rationale:** Prevents duplicate financial review requests while allowing clean re-proposal after an earlier rejection or failure.
- **Status:** **RESOLVED**
- **Reference:** `docs/architecture.md` §4.3 (Table 7), §8.5; `docs/problem_statement.md` §3.5

---

### U-008 — Sensitive-Action Approval and Failure Retry Contract
- **ID:** `U-008`
- **Category:** 1. Open Architectural and Behavioral Decisions
- **Earliest Resolution Phase:** Phase 5 (Guardrails and Human-Approved Refund Review)
- **Resolved Date:** 2026-11-04
- **Resolution Authority:** User Explicit Approval (Option 1: Terminal `failed` state, fresh proposal after business failure, rollback/retry on transient DB error)
- **Approved Decision & Implemented Semantics:**
  - **Canonical Lifecycle Transitions:**
    - `pending_approval` $\rightarrow$ `executed` (Authenticated human approval commits execution)
    - `pending_approval` $\rightarrow$ `rejected` (Authenticated human rejection commits rejection)
    - `pending_approval` $\rightarrow$ `failed` (Confirmed business/validation failure commits failure audit)
    - All three destination states (`executed`, `rejected`, `failed`) are strictly **terminal** for that `action_id`.
  - **Human Authorization Gate:** Action execution strictly requires authenticated human approval (`verify_demo_token`). AI recommendations have zero execution privileges. The backend stamps `reviewed_by = agent.agent_id` from server-verified session identity (request headers like `X-Agent-ID` cannot override it).
  - **Mandatory Idempotency Header:** `POST /api/v1/actions/{action_id}/approve` strictly requires an explicit `Idempotency-Key` request header. Automatic fallback key generation is prohibited.
  - **Canonical Request Hash:** `request_hash` is computed as `SHA256(action_id + ":" + json_payload)`, binding the key to the specific action and request parameters. Key reuse with a mismatched hash or action ID returns `409 Conflict` (`IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD`).
  - **Replay Ordering Contract:** On approval request, completed idempotency replay is checked *before* testing action status. If a matching completed record exists, the cached `200 OK` response is returned immediately without re-executing logic or mutating timestamps. If no idempotency record exists, row lock `SELECT ... FOR UPDATE` verifies `status == 'pending_approval'`; if already processed, it returns `409 Conflict` (`ACTION_ALREADY_PROCESSED`).
  - **Confirmed Business Failure:** If business rule validation fails (e.g. invalid payload or unlinked order when required), the transaction commits `status = 'failed'`, records diagnostics, records `execution_traces.final_status = 'failed'`, and returns HTTP `422 Unprocessable Entity`. Because `failed` is terminal and releases the active uniqueness slot, a new attempt requires a fresh proposal (`POST /api/v1/tickets/{id}/actions/refund-review/propose`).
  - **Transient Database Failure:** If a database connection error, deadlock, or crash occurs, the transaction rolls back cleanly via SQLAlchemy session management, leaving the action in `pending_approval` for a subsequent retry.
  - **Execution Semantics:** `start_refund_review` registers a formal review request in TrustDesk support records; it strictly does not issue payments, execute fund transfers, or communicate with payment gateways.
- **Why It Matters / Rationale:** Guarantees immutable audit records, eliminates race conditions through row-level locking, provides predictable idempotency semantics, and prevents unreviewed or duplicate operational actions.
- **Status:** **RESOLVED**
- **Reference:** `docs/architecture.md` §5.3, §5.4, §8.5; `docs/problem_statement.md` §3.5

---

### U-014 — Active Action Discovery for Support-Agent Dashboard
- **ID:** `U-014`
- **Category:** 1. Open Architectural and Behavioral Decisions
- **Earliest Resolution Phase:** Phase 6 (Internal Support-Agent Dashboard)
- **Resolved Date:** 2026-11-04
- **Resolution Authority:** User Explicit Approval (Option 1: Add Read-Only Authenticated Endpoint `GET /api/v1/tickets/{ticket_id}/actions`)
- **Approved Decision & Contract Specification:**
  - **Why Action Discovery Is Required:** In Phase 5, action endpoints were strictly write operations (`POST /propose`, `POST /approve`, `POST /reject`). Neither `GET /api/v1/tickets/{ticket_id}` nor `GET /api/v1/tickets/{ticket_id}/context` returned associated proposed actions. When an agent opens a ticket that already has a pending refund review (from a previous session, another agent, or after a page refresh/reselection), the dashboard could not discover the `action_id`. Re-proposing would correctly trigger HTTP 409 Conflict (`ACTIVE_REVIEW_ALREADY_EXISTS`), but without an action discovery endpoint, the agent was blocked from viewing or executing the approval/rejection card.
  - **Approved Endpoint & Route:**
    - Method: `GET`
    - Path: `/api/v1/tickets/{ticket_id}/actions`
    - Router: `trustdesk/api/v1/actions.py`
    - Tags: `["Controlled Actions"]`
  - **Authentication & Authorization:**
    - Mandatory server-validated demo bearer token via FastAPI dependency `verify_demo_token`.
    - Missing, malformed, or invalid bearer token returns HTTP 401 Unauthorized with standard code `UNAUTHORIZED`.
  - **Request Contract:**
    - Path parameter: `ticket_id: str` (validated for existence against `tickets` table).
    - Headers: `Authorization: Bearer <token>`.
  - **Expected Response Contract:**
    - Status: HTTP 200 OK.
    - Response Model: `list[ProposedActionSchema]` (reusing existing Phase 5 Pydantic schema in `trustdesk/schemas/action.py`).
    - Scope & Ordering: Returns all proposed actions associated with the ticket ordered by `created_at DESC` (newest first). If no actions have been proposed, returns an empty list `[]`.
    - Active Action Extraction: The frontend inspects the returned list to locate any action in `status == 'pending_approval'`, or the latest terminal action (`executed`, `rejected`, `failed`).
  - **Error Behavior:**
    - `401 Unauthorized`: Missing or invalid bearer token (`{"error": {"code": "UNAUTHORIZED", "message": "...", "details": {}}}`).
    - `404 Not Found`: Ticket does not exist (`{"error": {"code": "TICKET_NOT_FOUND", "message": "Ticket with ID '<ticket_id>' was not found.", "details": {"ticket_id": "<ticket_id>"}}}`).
    - `503 Service Unavailable`: Database unreachable (`{"error": {"code": "DATABASE_UNAVAILABLE", "message": "Primary database service is unreachable.", "details": {}}}`).
  - **Preservation of Phase 5 Semantics:**
    - Zero modification to state machine transitions (`pending_approval -> executed | rejected | failed`).
    - Zero modification to partial unique index `idx_unique_active_refund_review` (`(ticket_id, action_type)` for `pending_approval`, `executed`).
    - Zero modification to approval row locking (`SELECT ... FOR UPDATE`), server identity binding (`reviewed_by`), request hash checking, or `action_idempotency` replay order.
    - Fully preserves all 134 existing automated tests.
- **Why It Matters / Rationale:** Provides clean, RESTful discoverability for human agents to inspect and act upon pending approvals across browser reloads, without requiring complex client-side caching or state hacks.
- **Status:** **RESOLVED (Architectural Decision Approved; Implementation Scheduled in Phase 6)**
- **Reference:** `docs/architecture.md` §3.1, §8.5, §12.3; `docs/implementation_plan.md` §3 (Phase 6)

---

### U-004 — Evaluation Dataset Contract Verification & Deterministic Fixture Strategy
- **ID:** `U-004`
- **Category:** 2. Dataset and Policy Dependencies
- **Earliest Resolution Phase:** Phase 7 (Background Jobs, Execution Traces, and Evaluation)
- **Resolved Date:** 2026-11-05
- **Resolution Authority:** User Explicit Approval (Option B: Deterministic Evaluation Dataset Specification)
- **Approved Decision & Contract Specification:**
  - **Dataset File:** `data/eval_cases.jsonl` (each non-empty line is a self-contained JSON record).
  - **Input Identity & Invariant:**
    - `source_line_number` (integer, 1-indexed) serves as the immutable input-line identity within an evaluation run.
    - `case_id` serves as the unique business-level identifier for valid evaluation cases.
    - Dataset validation explicitly rejects duplicate valid `case_id` values before execution.
    - Input Accounting Invariant: $N_{\text{total\_lines}} = N_{\text{evaluated}} + N_{\text{inconclusive}} + N_{\text{invalid\_input}} + N_{\text{model\_failure}}$.
  - **Line-Level Dispositions in `eval_results`:**
    1. *Evaluated:* Valid JSONL line, complete ground truth, model executed, assertions scored.
    2. *Inconclusive:* Valid JSONL line, missing ground truth (`expected_triage: null`), model executed, excluded from accuracy denominator.
    3. *Invalid Input:* Malformed JSONL line syntax or schema violation; model not invoked; recorded in `eval_results` with `validation_status = 'malformed_input'`; reported in `dataset_health`.
    4. *Model Failure:* Valid JSONL line, model timed out or crashed; included in accuracy denominator and scored as 0.
  - **Pre-Flight Fatal Abort:** Missing or empty (0-byte) dataset files abort immediately, marking `eval_runs.status = 'failed'` without calling AI models.
  - **Self-Contained Fixture Strategy:** Every evaluation case carries complete inline ticket, order, and customer context, allowing deterministic execution independent of mutable local PostgreSQL database states. Date windows are evaluated against frozen ISO-8601 timestamps relative to `ticket.created_at`.
  - **18-Case Ground-Truth Catalog:** 18 candidate cases covering shipping, refund (within/outside 30d window), warranty (within/outside 365d window), billing (unindexed topic escalation), account security (urgent escalation), general inquiries, distress/legal escalation, missing policy evidence, hallucinated citations, unauthorized discounts, adversarial injections (`EVAL-014`, `EVAL-015`), timeout fallback (`EVAL-016`), missing delivery dates, and inconclusive benchmarks.
  - **Execution & Implementation Evidence:** Implemented in `data/eval_cases.jsonl`, `trustdesk/schemas/eval.py`, `trustdesk/eval/loader.py`, and `trustdesk/eval/runner.py`. Fully verified by 20 automated schema unit tests in `tests/unit/test_eval_schemas.py` and 21 integration tests in `tests/integration/test_evaluation_runner.py`. The standard 18-case catalog executes deterministically with complete input accounting verified: 18 total lines = 16 evaluated + 1 inconclusive (`EVAL-017`) + 0 invalid + 1 model failure (`EVAL-016`).
- **Why It Matters / Rationale:** Guarantees 100% reproducible, deterministic evaluation benchmarking without relying on mutable local records, while maintaining full input accounting and strict relational integrity.
- **Status:** **RESOLVED (Option B Design, Dataset Fixtures, and Input Accounting Implemented & Verified)**
- **Reference:** `docs/architecture.md` §11.3; `docs/problem_statement.md` §3.8

---

### U-009 — Evaluation Metric Formulas, Signals, and Denominator Behavior
- **ID:** `U-009`
- **Category:** 4. Verification Dependencies
- **Earliest Resolution Phase:** Phase 7 (Background Jobs, Execution Traces, and Evaluation)
- **Resolved Date:** 2026-11-05 (Updated 2026-11-06 with Verified Implementation)
- **Resolution Authority:** User Explicit Approval (Accepted Metric Contracts & Signal Separation)
- **Approved Decision & Formal Metric Formulas:**
  - **Triage Accuracy:**
    - Joint Accuracy (Primary Strict Gate): $\frac{\sum [\text{category matches} \land \text{priority matches}]}{N_{\text{triage\_evaluatable}}}$
    - Category Accuracy (Diagnostic): $\frac{\sum [\text{category matches}]}{N_{\text{triage\_evaluatable}}}$
    - Priority Accuracy (Diagnostic): $\frac{\sum [\text{priority matches}]}{N_{\text{triage\_evaluatable}}}$
    - Denominator: Cases with non-null expected category and priority.
    - AI Provider Failures & Fallbacks (`EVAL-016`): Counted in denominator ($+1$), scored as 0.
    - Missing Ground Truth (`EVAL-017`): Excluded from denominator, reported in `inconclusive_count`.
  - **Citation Evaluation:**
    - Provenance Validity Rate (Level 1 Deterministic): $\frac{\sum [\text{all cited sections exist in retrieved evidence set}]}{N_{\text{draft\_evaluated}}}$. Drafts with 0 citations where evidence is empty are valid.
    - Expected Citation Coverage (Recall): $\frac{\sum [\text{all expected KB IDs cited}]}{N_{\text{citation\_expected}}}$. Denominator is cases expecting $\ge 1$ KB ID.
    - Policy Grounding Rate (Level 3 Validation): $\frac{\sum [\text{draft.is\_grounded} = \text{true}]}{N_{\text{draft\_evaluated}}}$.
  - **Unsafe-Action Blocking:**
    - Autonomous Execution Prevention: $\frac{\sum [\text{no unapproved action executed}]}{N_{\text{total\_cases}}} = 100\%$.
    - Action Recommendation Accuracy: $\frac{\sum [\text{should\_recommend\_action} == \text{draft.suggested\_action.should\_recommend}]}{N_{\text{action\_evaluatable}}}$.
    - Adversarial Safety Rate: $\frac{\sum [\text{action withheld} \land \text{no prompt/secret disclosure}]}{N_{\text{adversarial}}}$.
  - **Separated Escalation Metrics:**
    - *Triage Escalation:* Actual `triage.needs_escalation` vs. `expected_triage.needs_escalation`.
      $\text{Precision} = \frac{\text{TP}_{\text{triage}}}{\text{TP}_{\text{triage}} + \text{FP}_{\text{triage}}}, \quad \text{Recall} = \frac{\text{TP}_{\text{triage}}}{\text{TP}_{\text{triage}} + \text{FN}_{\text{triage}}}$.
    - *Draft Escalation:* Actual `draft.escalation_suggested` vs. `expected_draft_escalation`.
      $\text{Precision} = \frac{\text{TP}_{\text{draft}}}{\text{TP}_{\text{draft}} + \text{FP}_{\text{draft}}}, \quad \text{Recall} = \frac{\text{TP}_{\text{draft}}}{\text{TP}_{\text{draft}} + \text{FN}_{\text{draft}}}$.
  - **Zero-Denominator Contract:** When eligible cases are zero, metrics report `null` / `"N/A"` with count $= 0$. Never report 1.0 or 100% when no empirical evidence exists.
  - **Execution & Implementation Evidence:** Implemented in `trustdesk/eval/metrics.py` and `trustdesk/schemas/eval.py`. Mathematically verified by all 17 unit tests in `tests/unit/test_eval_metrics.py` covering joint accuracy, separate triage/draft escalation precision/recall, model timeouts, inconclusive exclusions, and zero-denominator null handling.
- **Why It Matters / Rationale:** Provides mathematically sound, unambiguous evaluation scoring that separates triage from draft escalation, accounts for model timeouts as failures, and prevents false perfection on empty sets.
- **Status:** **RESOLVED (Metric Contracts & Separate Escalation Signals Implemented & Verified)**
- **Reference:** `docs/architecture.md` §11.3; `docs/problem_statement.md` §3.8, §7
