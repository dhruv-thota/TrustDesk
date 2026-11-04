# TrustDesk — Authoritative Development Conventions

**Document Version:** 1.1.0  
**Status:** Authoritative / Active  
**Effective Date:** 2026-11-01  
**Target Repository:** `TrustDesk`  
**Applies To:** All Implementation Phases, Architectural Refinements, Evaluations, and Documentation Lifecycles

---

## 1. Purpose, Authority Hierarchy, and Document Ecosystem

### 1.1 Purpose
This document establishes the binding, non-negotiable software engineering, implementation, testing, evaluation, git hygiene, and documentation rules for the TrustDesk project. Every engineer, autonomous coding agent, and technical reviewer working on TrustDesk must comply with these standards without exception.

### 1.2 Document Authority Hierarchy
When navigating project specifications, rules, and technical decisions, the following order of precedence is strictly authoritative. Lower-level documents must never override, dilute, or contradict higher-level documents:

```
┌────────────────────────────────────────────────────────┐
│  Level 1: docs/problem_statement.md                     │
│  (Defines core problem, business scope & boundaries)   │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│  Level 2: docs/architecture.md                         │
│  (Defines technical architecture, components & flows)  │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│  Level 3: docs/unresolved.md                           │
│  (Living register of approved decisions & open gates)  │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│  Level 4: docs/implementation_plan.md                  │
│  (8-phase sequencing, deliverables & dependencies)    │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│  Level 5: docs/conventions.md (THIS DOCUMENT)          │
│  (Authoritative engineering & lifecycle conventions)  │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│  Level 6: docs/phaseX_edgecases.md & phaseX_evals.md   │
│  (Phase-specific validation gates & expected results)  │
└────────────────────────────────────────────────────────┘
```

1. **`docs/problem_statement.md`** governs all business goals, product behavior, and explicit operational scope boundaries.
2. **`docs/architecture.md`** governs all technical contracts, data models, integration boundaries, security controls, and component interactions.
3. **`docs/unresolved.md`** governs the authoritative state of decisions, pending evidence, and resolved trade-offs. If an item is recorded as open in `unresolved.md`, it is legally unresolved regardless of text elsewhere.
4. **`docs/implementation_plan.md`** governs phase sequencing, component allocation across phases, and phase-specific prerequisites.
5. **`docs/conventions.md`** governs code standards, architecture practices, testing rigor, edge-case tracking, walkthrough creation, and git hygiene.
6. **`docs/phaseX_edgecases.md` and `docs/phaseX_evals.md`** govern the granular verification cases, metrics, and quality gates for Phase `X`.

### 1.3 Conflict Resolution Protocol
If any two documents present conflicting requirements:
1. Immediately halt any active implementation touching the conflict.
2. Determine which document occupies higher precedence in the hierarchy.
3. If the conflict involves an unapproved assumption or an ambiguous interface, follow the **Mandatory Clarification Procedure** (§2).
4. Never silently choose one conflicting interpretation.
5. Record the discrepancy and the formal resolution in `docs/unresolved.md`.

---

## 2. Mandatory Rule — Never Assume Unclear Requirements

### 2.1 The Core Non-Assumption Principle
**At any point during development, if a requirement, expected behavior, technical decision, data contract, error condition, security rule, or implementation detail is unclear, ambiguous, or unstated, the developer or AI must not invent an assumption.**

Do not treat:
- A personal or model preference as authorization.
- An "industry standard" or "common convention" as authorization.
- A proposed option in a prior chat message as authorization.
- An unconfirmed recommendation as authorization.

### 2.2 The 10-Step Mandatory Clarification Procedure
When uncertainty or missing specifications arise:

```
[1. HALT IMPLEMENTATION]
        │
        ▼
[2. REVIEW AUTHORITATIVE DOCS]
        │
        ▼
[3. CHECK docs/unresolved.md]
        │
        ▼
[4. ISOLATE THE EXACT AMBIGUITY]
        │
        ▼
[5. FORMULATE SPECIFIC QUESTION]
        │
        ▼
[6. OUTLINE ALTERNATIVES & TRADEOFFS]
        │
        ▼
[7. ASK USER FOR EXPLICIT DECISION]
        │
        ▼
[8. WAIT FOR USER RESPONSE (NO SPECULATIVE CODE)]
        │
        ▼
[9. RECORD DECISION IN docs/unresolved.md]
        │
        ▼
[10. RESUME IMPLEMENTATION]
```

1. **Stop immediately:** Halt work on the affected component, schema, or workflow.
2. **Review documentation:** Thoroughly examine `problem_statement.md`, `architecture.md`, `unresolved.md`, and the active phase documentation.
3. **Check the decision register:** Verify whether the question is already tracked or resolved in `docs/unresolved.md`.
4. **Isolate the ambiguity:** Pinpoint the precise code path, schema field, boundary condition, or business rule that lacks an authoritative contract.
5. **Formulate a specific question:** Frame a clear, objective question explaining what is ambiguous and where it blocks implementation.
6. **Present alternatives:** If applicable, present realistic technical options, including trade-offs, database implications, and failure modes.
7. **Request user decision:** Ask the user explicitly for a binding choice.
8. **Wait for response:** Do not write speculative or temporary placeholder code while waiting.
9. **Record resolution:** Once the user responds, record the approved decision, rationale, and timestamp/evidence in `docs/unresolved.md`.
10. **Resume work:** Proceed with implementation adhering strictly to the newly recorded decision.

### 2.3 Distinction Between Routine Choices and Consequential Requirements
- **Routine Implementation Choices:** Standard syntax, private helper function decomposition, standard variable naming following PEP 8, idiomatic loop constructs, or straightforward unit test structuring within approved boundaries do not require clarification.
- **Consequential Requirements (Always Require Approval):** Any ambiguity touching data loss, quarantine policies, foreign key integrity, schema structure, external API interfaces, security policies, human authorization thresholds, monetary action semantics, or error handling contracts must follow the 10-step clarification procedure.

---

## 3. Mandatory Rule — Documentation-Driven Implementation

### 3.1 Pre-Phase Mandatory Document Reading
Before writing a single line of code, modifying any configuration, or generating migrations for any phase `X`, the implementer must read all seven authoritative documents:

1. `docs/problem_statement.md`
2. `docs/architecture.md`
3. `docs/implementation_plan.md`
4. `docs/conventions.md`
5. `docs/unresolved.md`
6. `docs/phaseX_edgecases.md`
7. `docs/phaseX_evals.md`

### 3.2 Pre-Phase Workspace Inspection
In addition to the documents, the implementer must inspect:
- Relevant codebase files from previously completed phases.
- Existing automated test suites (`tests/`).
- Existing Alembic database migrations (`alembic/versions/`).
- Relevant raw datasets (`data/`).
- Walkthroughs from prior phases (`walkthroughs/phase{X-1}_walkthrough.md`) if relevant context is needed.

### 3.3 Scope and Acceptance Criteria Baseline
- The exact phase scope, deliverables, test cases, and completion gates must be verified before implementing.
- Never rely on conversational memory or partial summaries when physical documentation files are available in the repository.
- Verify that all prerequisites listed in `docs/implementation_plan.md` for phase `X` are satisfied and verified before starting.

---

## 4. Mandatory Rule — Strict Scope Control

### 4.1 Prohibited Scope Expansions
Developers and autonomous agents are strictly forbidden from unilaterally introducing:
- **Unapproved features:** E.g., live chatbot widgets, automatic email dispatching, user profile management, dark-mode toggles not in spec.
- **New operational tools:** Only the six approved tools (`search_knowledge_base`, `fetch_ticket_history`, `check_order_status`, `check_policy_rules`, `fetch_customer_profile`, `start_refund_review`) are permitted.
- **Autonomous monetary transfers:** The system must never initiate real bank transfers, payment gateway refund webhooks, or automated financial transactions. `start_refund_review` registers a formal review request in the support workflow; it never disburses funds.
- **Unplanned APIs:** Endpoints not specified in `architecture.md` or `implementation_plan.md`.
- **New database entities:** Tables, relationships, or columns not specified in `architecture.md` or approved via `unresolved.md`.
- **New external services / frameworks:** Replacing Redis, RQ, FastAPI, React, Vite, or Tailwind with alternate technologies.
- **Unrequested architecture patterns:** Event-sourcing, CQRS, GraphQL layers, or distributed microservices when a modular monolith is specified.
- **Premature optimizations:** Custom thread pools, complex caching layers, or micro-benchmarking abstractions where standard implementations suffice.
- **Post-MVP functionality:** Features explicitly deferred to future phases (e.g., Qdrant vector search `U-011`, production JWT/OIDC authentication `U-012`, fine-grained enterprise RBAC).

### 4.2 Scope Modification Protocol
If an unforeseen technical reality demands a scope adjustment:
1. **Explain the proposed change:** Define the exact nature of the change.
2. **Justify necessity:** Detail why the current approved architecture cannot proceed without this change.
3. **Assess impact:** Enumerate all affected phases, database models, API contracts, and evaluation cases.
4. **Obtain explicit user approval:** Present the proposal to the user and wait for formal authorization.
5. **Update documentation first:** Update `docs/architecture.md`, `docs/implementation_plan.md`, and `docs/unresolved.md` before any code implementation begins.

---

## 5. Software Engineering and Coding Standards

### 5.1 Modularity and Separation of Concerns

The TrustDesk backend is organized as a clean, modular monolith under the root package `trustdesk/` with explicit physical and logical separation:

```
trustdesk/
├── api/                  # Delivery Layer: FastAPI routes, dependency injection, request/response models
│   └── v1/
│       ├── tickets.py
│       ├── health.py
│       ├── rag.py
│       ├── actions.py
│       └── ...
├── core/                 # Foundation: Configuration (Pydantic BaseSettings), logging, security, database session
│   ├── config.py
│   ├── database.py
│   ├── logging.py
│   └── security.py
├── models/               # Persistence Layer: Declarative SQLAlchemy 2.0 ORM models
│   ├── customer.py
│   ├── order.py
│   ├── ticket.py
│   ├── knowledge.py
│   └── ...
├── schemas/              # Contract Layer: Pydantic v2 schemas for requests, responses, internal DTOs
│   ├── ticket.py
│   ├── agent.py
│   └── ...
├── services/             # Domain / Business Layer: Pure business logic, workflows, policy evaluations
│   ├── ticket_service.py
│   ├── ingestion.py
│   ├── rag_service.py
│   └── ...
├── adapters/             # External Boundaries: AI Provider adapters (live / mock), search adapters
│   ├── ai/
│   │   ├── base.py       # AIProviderAdapter / AIProviderInterface
│   │   └── mock.py       # MockAIProvider (Live provider selection open in U-006)
│   └── search/           # PostgresFtsRetrievalAdapter (MVP baseline)
├── tools/                # Agent Tool Implementations: Deterministic catalog tools
│   ├── base.py
│   ├── catalog.py
│   └── executor.py
├── workers/              # Asynchronous Tasks: Background RQ worker jobs reusing domain services
│   └── tasks.py
└── cli.py                # CLI Entrypoint: Database management, dataset ingestion (python -m trustdesk.cli)
```

#### Modularity Rules:
1. **Thin Route Handlers:** FastAPI routes in `trustdesk/api/` must only parse/validate HTTP requests, invoke domain services, handle HTTP status mapping, and return validated Pydantic responses. Route handlers must never execute raw SQL, construct complex AI prompts, or contain business logic.
2. **Encapsulated Business Logic:** All domain logic, workflow orchestration, rule verification, and validation reside in `trustdesk/services/`.
3. **Persistence Isolation:** Database operations must use SQLAlchemy sessions injected via FastAPI dependencies or context managers. Complex queries must be encapsulated within repository helpers or service methods, never in routes.
4. **External Provider Abstraction:** All LLM operations must be accessed through `AIProviderAdapter` in `trustdesk/adapters/ai/base.py`. No service or route may import a vendor-specific SDK directly. Live provider selection (Anthropic vs OpenAI vs Gemini vs mock) is an **open decision tracked in `U-006`**. All AI code must remain strictly provider-agnostic.
5. **Policy Retrieval Boundary:** Retrieval logic must be decoupled behind `PolicyRetrievalInterface`. The MVP baseline implementation is `PostgresFtsRetrievalAdapter` using native PostgreSQL Full-Text Search (`tsvector`, English dictionary, `ts_rank_cd`). Vector embeddings and Qdrant integration are post-MVP enhancements tracked in `U-011`.
6. **Worker Logic Reuse:** Background RQ tasks in `trustdesk/workers/` must invoke the identical service methods in `trustdesk/services/` that synchronous routes call. Never duplicate business logic between API routes and background workers.

---

### 5.2 Software Design Principles
1. **Single Responsibility Principle (SRP):** Each module, class, and function must have one well-defined responsibility. A route handles HTTP; a service calculates refund eligibility; a repository persists records.
2. **Dependency Inversion Principle (DIP):** High-level domain services must depend on abstractions (interfaces/protocols), not concrete SDK instances.
3. **Don't Repeat Yourself (DRY):** Common logic (e.g., ticket state transition validation, citation formatting) must reside in a single canonical service method.
4. **Keep It Simple, Stupid (KISS):** Choose the simplest design that satisfies the verifiable requirements. Avoid speculative complexity.
5. **You Aren't Gonna Need It (YAGNI):** Do not write code, models, or hooks for anticipated future capabilities not required by the active phase.
6. **Composition Over Inheritance:** Prefer functional composition, service injection, and helper modules over deep class inheritance hierarchies.

---

### 5.3 Python Backend Standards

#### 5.3.1 Language & Tooling Baseline
- **Python Version:** Python 3.11+
- **Type Checking:** Strict type hints throughout. All function signatures and return types must be fully annotated.
- **Import Style:** Absolute imports from `trustdesk.` (e.g., `from trustdesk.core.config import settings`). Wildcard imports (`from module import *`) are strictly prohibited.
- **Imports Sorting:** Standard library first, third-party libraries second, local application modules third (PEP 8 / `isort` convention).

#### 5.3.2 Naming Conventions
- **Modules and packages:** `snake_case` (e.g., `ticket_service.py`, `ingestion.py`)
- **Classes and Exception types:** `PascalCase` (e.g., `TicketService`, `InvalidTicketStateException`)
- **Functions, methods, and variables:** `snake_case` (e.g., `calculate_refund_limit()`, `customer_id`)
- **Constants and Enum members:** `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES`, `TicketStatus.OPEN`)
- **Pydantic Schemas:** `PascalCase` with descriptive suffixes (e.g., `TicketCreateRequest`, `TicketDetailResponse`)
- **SQLAlchemy Models:** `PascalCase` matching singular entity names (e.g., `Ticket`, `Customer`, `Order`, `KnowledgeDocument`)

#### 5.3.3 Type Hints & Modern Annotations
- Always use `from __future__ import annotations` or modern standard collections (`list[str]`, `dict[str, Any]`, `tuple[int, ...]`, `X | None`).
- Use `typing.Annotated` for FastAPI dependencies and Pydantic field constraints.
- Avoid raw `Any` where a specific union, generic type, or TypedDict can be defined.

#### 5.3.4 Pydantic v2 Standards
- Use Pydantic v2 idioms exclusively (`model_config = ConfigDict(...)`, `@field_validator`, `@model_validator(mode='after')`).
- Enable ORM mode using `model_config = ConfigDict(from_attributes=True)` on all response schemas.
- Explicitly validate string lengths, numeric bounds, regex patterns, and optional/required fields.
- *[Illustrative Example — Non-Normative]:*
  ```python
  from pydantic import BaseModel, ConfigDict, Field

  class TicketResponse(BaseModel):
      model_config = ConfigDict(from_attributes=True)

      ticket_id: str = Field(..., description="Unique ticket identifier from dataset")
      customer_id: str = Field(..., description="Associated customer ID")
      order_id: str | None = Field(None, description="Optional associated order ID")
      status: str = Field(..., max_length=32)
  ```

#### 5.3.5 SQLAlchemy 2.0 Standards
- Use SQLAlchemy 2.0 `DeclarativeBase` and `Mapped[T]` with `mapped_column()` syntax.
- Always declare explicit column types, foreign key constraints, nullable flags, and default values.
- *[Illustrative Example — Non-Normative]:*
  ```python
  from datetime import datetime
  from sqlalchemy import String, DateTime, ForeignKey, func, Text
  from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

  class Base(DeclarativeBase):
      pass

  class Ticket(Base):
      __tablename__ = "tickets"

      ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
      customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), nullable=False, index=True)
      order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.order_id"), nullable=True, index=True)
      subject: Mapped[str] = mapped_column(String(255), nullable=False)
      message: Mapped[str] = mapped_column(Text, nullable=False)
      status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
  ```
- Never use legacy `session.query(Model)` syntax. Use `select(Model).where(...)` syntax exclusively.
- Database sessions must be managed via context managers or FastAPI `Depends(get_db)`. Ensure sessions are closed in all code paths.

#### 5.3.6 Alembic Migrations
- All database schema modifications must be executed via Alembic migrations in `alembic/versions/`.
- Every migration must have:
  - A deterministic revision identifier.
  - An informative migration message (e.g., `create_source_tables`).
  - Fully implemented `upgrade()` and `downgrade()` functions.
  - Explicit foreign key constraint names and index names.
- Never manually modify the database schema outside Alembic.

#### 5.3.7 Dependency Injection via FastAPI
- Utilize `FastAPI.Depends` for database sessions, authentication, and service instantiation.
- *[Illustrative Example — Non-Normative]:*
  ```python
  @router.get("/{ticket_id}", response_model=TicketDetailResponse)
  async def get_ticket(
      ticket_id: str,
      db: AsyncSession = Depends(get_db),
      service: TicketService = Depends(get_ticket_service),
      user: CurrentUser = Depends(require_authenticated_user),
  ) -> TicketDetailResponse:
      return await service.get_ticket_by_id(db, ticket_id)
  ```

#### 5.3.8 Exception Handling Standards
- Define custom domain exceptions in `trustdesk/core/exceptions.py` inheriting from `TrustDeskException`.
- Map domain exceptions to standardized HTTP responses using custom FastAPI exception handlers in `trustdesk/main.py`.
- **Never silently suppress exceptions:** `except Exception: pass` is strictly prohibited.
- When re-raising or transforming exceptions, preserve the original traceback using `raise NewException(...) from exc`.
- *[Illustrative Example — Non-Normative]:*
  ```json
  {
    "error_code": "TICKET_NOT_FOUND",
    "message": "Ticket with ID 't-1234' does not exist.",
    "details": {},
    "timestamp": "2026-11-01T17:00:00Z"
  }
  ```

#### 5.3.9 Structured Logging
- Use standard Python `logging` configured via `trustdesk/core/logging.py` outputting structured JSON or clean contextual logs.
- Log records must include contextual fields: `timestamp`, `level`, `logger`, `module`, `trace_id`, `ticket_id` (when available).
- **Security & Privacy Rule:** Never log raw API secrets, tokens, customer passwords, or unmasked PII.

#### 5.3.10 Configuration Management
- Use Pydantic `BaseSettings` with `SettingsConfigDict` in `trustdesk/core/config.py`.
- All environment variables must have strict types, sensible development defaults (where safe), and explicit validation.
- Production secrets (API keys, database passwords) must not have hardcoded fallback values.

---

### 5.4 Database, Integrity, and Transaction Standards

#### 5.4.1 PostgreSQL 15+ as Authoritative Persistence Baseline
- PostgreSQL 15+ is the single authoritative source of truth for all operational records, ticket states, audit trails, and policy full-text search vectors.
- Redis is strictly an ephemeral queue broker for background RQ tasks; no persistent business records or audit logs may reside solely in Redis.

#### 5.4.2 Source Data Ingestion & Identifier Preservation
- Source datasets in `data/` represent external operational truth (`customers`, `orders`, `tickets`, `kb_documents`, `tool_catalog`).
- **Preserve Source Identifiers Directly:** Original alphanumeric identifiers (`customer_id`, `order_id`, `ticket_id`, `kb_id` like `KB-REFUND-001`, `KB-ADVERSARIAL-001`) must be stored directly as the primary keys of their respective tables. Do not invent surrogate integer IDs or replace them with random UUIDs.
- **Relational Integrity and Foreign Key Ingestion Policy (`U-003`):**
  - *Naturally Absent Optional References:* A ticket that naturally references no order (`order_id IS NULL`, missing, or empty string because the customer inquiry is general or pre-sales) is completely valid domain behavior. Store `order_id = NULL` cleanly without error or warning.
  - *Missing Mandatory Parent Entities:* If a ticket references a mandatory customer entity that does not exist in `customers`, the system must **never** silently accept the record or invent a dummy customer. The record must be rejected with an explicit validation error or quarantined according to the approved ingestion policy (`U-003`), preventing orphaned tickets.
  - *Invalid Non-Null References:* If a ticket references an `order_id` that does not exist in `orders`, **never silently discard the invalid reference**. The raw unresolvable string must be retained in structured metadata (e.g., `tickets.raw_metadata["unresolved_order_id"] = "ORD-INVALID"`), while the relational column `order_id` is set to `NULL` to preserve relational foreign key integrity. A structured ingestion warning must be logged.
  - Do not invent unapproved database entities or standalone quarantine tables unless explicitly authorized by approved documentation.

#### 5.4.3 Transaction Boundaries & Ingestion Transactions
- Every database write operation must execute inside an explicit database transaction boundary (`with session.begin():` or `async with session.begin():`).
- If an unhandled error occurs during a transaction, the session must roll back completely before raising.
- Never commit partial state across coupled operations (e.g., recording a triage classification and updating ticket status must occur atomically).
- The exact ingestion transaction boundary (single batch transaction vs. per-file commit) remains subject to source dataset format verification under `U-003` / `U-010`.

#### 5.4.4 Concurrency Control for Sensitive Operations
- Sensitive operational mutations (approving or rejecting a proposed action, ticket status changes, assigning tickets) must enforce concurrency controls to prevent race conditions:
  - Use row-level locking (`SELECT ... FOR UPDATE`) within the transaction to serialize concurrent updates.
  - Verify record status prior to mutation (e.g., ensuring action is currently `pending_approval`).
  - Transaction-level advisory locks (`pg_try_advisory_xact_lock`) may be utilized where coarse-grained pipeline serialization is warranted, but row-level locking remains the primary approved mechanism.

#### 5.4.5 Persistent Idempotency for Sensitive Actions
- The table guarding sensitive operational mutations is `ACTION_IDEMPOTENCY` (or `action_idempotency`), tracking `idempotency_key`, `action_id`, `request_hash`, `status` (`in_progress`, `completed`, `failed`), `response_payload`, and `created_at` per `docs/architecture.md` §4.2, §4.3.
- Do not mandate universal idempotency keys across unrelated non-mutating endpoints or read-only queries.

#### 5.4.6 Operation Verification
- Never assume a database operation succeeded without verifying the outcome (e.g., checking `rowcount` or fetching the persisted record).

---

### 5.5 AI Integration, Grounding, and Safety Standards

#### 5.5.1 AI Provider Abstraction
- All AI model interactions must pass through `AIProviderAdapter` in `trustdesk/adapters/ai/base.py`:
  - Concrete adapters encapsulate vendor-specific API clients, request formatting, timeout handling, and response parsing.
  - A deterministic `MockAIProvider` must be provided for isolated, reproducible testing without external network access.
  - **Live Provider Selection is Open (`U-006`):** The selection of the primary live LLM provider (Anthropic, OpenAI, or Gemini) is an open decision tracked in `docs/unresolved.md` (`U-006`). Backend services must remain strictly provider-agnostic.
- Direct imports of vendor SDKs outside the adapter package are strictly prohibited.

#### 5.5.2 Runtime Validation of Model Outputs
- All structured outputs from the LLM (triage classifications, generated draft text, citation references, action proposals) must be strictly validated at runtime against Pydantic schemas (`TriageResultSchema`, `DraftResponseSchema`, `ActionRecommendationSchema`).
- If model output violates the Pydantic schema or produces malformed JSON, handle the error gracefully: record the failure trace and trigger deterministic fallback escalation. Never propagate raw unvalidated model output to internal services or the frontend.

#### 5.5.3 Advisory Semantics & Non-Execution
- **AI outputs are strictly advisory recommendations.**
- All AI-generated responses must be clearly distinguished with appropriate metadata (`proposed_by = 'ai'`).
- Model outputs must **never** directly execute sensitive actions.
- The `start_refund_review` tool only generates a proposed action record in the `proposed_actions` table with `status = 'pending_approval'` for human agent review. It does not issue refunds, execute monetary transactions, or call payment APIs.

#### 5.5.4 Untrusted Content Isolation (Prompt Injection Defense)
- All customer messages, ticket bodies, and retrieved knowledge base chunks must be treated as **lower-trust data**.
- Isolate untrusted content using structural delimiter tags (e.g., `<customer_message>`, `<retrieved_policy>`) within prompts.
- Maintain a strict system prompt instructing the model to disregard instructions contained inside untrusted input delimiters.
- Defense in depth relies on backend validation and lack of autonomous tool-execution privileges, not prompt delimiters alone.

#### 5.5.5 Citation Provenance vs. Claim Correctness
- **Citation Provenance:** The system must record exactly which policy documents, section IDs, and text snippets were retrieved and presented to the LLM (`has_valid_provenance`).
- **Claim Correctness:** The presence of a citation does **not** prove that the LLM's statement is factually or legally accurate.
- Both metrics must be tracked independently:
  - *Provenance Check:* Did the model cite real, retrieved sections from the provided evidence set?
  - *Policy Check / Factuality:* Does backend deterministic verification confirm dates, eligibility windows, and policy constraints?
- *Crucial Semantic Rule:* An order being ineligible for a refund does **not** make a draft ungrounded; a draft that correctly explains ineligibility according to cited policy is 100% grounded (`U-002`).

#### 5.5.6 Mandatory Abstention & Escalation
- If retrieval yields insufficient evidence, or if policy eligibility rules are ambiguous, the system must **abstain** from drafting a definitive resolution.
- In abstention scenarios:
  - Set `tickets.status = 'escalated'`.
  - Set `triage_results.needs_escalation = True` and record the reasoning.
  - Set `draft_responses.escalation_suggested = True`.
- **Retrieval Threshold Calibration is Open (`U-007`):** Numerical relevance thresholds and chunking weights are open decisions tracked in `docs/unresolved.md` (`U-007`). Do not hardcode arbitrary relevance thresholds (such as `0.65`) as mandatory contracts until calibrated against `data/eval_cases.jsonl`.
- Approved ticket statuses in `docs/architecture.md` §4.3 are: `open`, `in_review`, `escalated`, `closed`. Do not invent new statuses such as `ESCALATED_TO_HUMAN`.

#### 5.5.7 Deterministic Backend Enforcement
- Never rely on the LLM to enforce security constraints, policy rules, or tool parameter validation.
- All policy constraints ($\Delta t = \text{ticket.created\_at} - \text{order.reference\_date}$) and tool arguments must be validated deterministically by backend code before any action proposal is recorded.

---

### 5.6 Frontend Development Standards

#### 5.6.1 Stack Baseline
- **Framework:** React 18+ with Vite
- **Styling:** Tailwind CSS (v3.x). Use utility classes, consistent color tokens, and responsive layouts.
- **Language:** JavaScript or TypeScript with clean, well-defined prop interfaces.

#### 5.6.2 Separation of Concerns & API Communication
- All HTTP requests to the backend must be centralized in dedicated API client modules (e.g., `src/api/client.js`, `src/api/tickets.js`).
- UI components must never perform direct `fetch()` or `axios()` calls with raw URLs inline.
- Use clean async hooks or state management wrappers for API interactions.

#### 5.6.3 Comprehensive UI State Handling
Every data-fetching component must explicitly implement and render four fundamental states:
1. **Loading State:** Skeleton loaders or subtle spinners during in-flight network requests.
2. **Error State:** User-friendly error messages with retry options if a request fails.
3. **Empty State:** Clear, helpful messaging and guidance when zero records are returned (e.g., no tickets in queue).
4. **Unauthorized State:** Clear notification if the user lacks permissions or authentication for an action or resource.

#### 5.6.4 Security & Secret Hygiene in the Browser
- **Zero Secrets Rule:** Never embed backend secrets, database connection strings, private API keys, or authentication tokens into frontend source code or Vite build bundles via `VITE_*` environment variables.
- **Approved Demo Authentication Architecture:** For the MVP local demonstration:
  1. The backend uses `DEMO_BEARER_TOKEN` (or `TRUSTDESK_DEMO_TOKEN`), configured securely on the server via environment variables.
  2. The React dashboard accepts or selects a demo bearer token through the approved top-bar interaction.
  3. The frontend stores the token exclusively in `sessionStorage` for the current browser session (cleared upon closing the tab/browser).
  4. The token must never be hardcoded into frontend source code or embedded into the Vite build through `VITE_*` environment variables.
  5. All API requests send the token using the standard `Authorization: Bearer <token>` HTTP header.
  6. The backend validates the token against server configuration and maps it to the approved fixed demo-agent identity (`agent_id: "agent_demo_01"`).
  7. The frontend must not treat possession of the token as sufficient authorization for sensitive actions; deterministic backend authorization, state checks, and approval controls remain strictly mandatory.
- **Post-MVP Deferral:** Production multi-tenant authentication, enterprise identity providers, OAuth2/OIDC, and fine-grained RBAC remain strictly deferred to post-MVP under `U-012`.

#### 5.6.5 Scope Alignment
- Do not implement UI buttons, forms, or views for features not authorized in the approved project scope (e.g., no live bank transfer screens, no customer deletion tools).
- Keep UI controls synchronized with backend permissions and ticket states (e.g., disabled approval buttons when a proposed action is already `executed` or `rejected`).

---

### 5.7 Code Readability, Maintainability, and Hygiene
1. **Descriptive Names:** Variables, functions, and classes must reveal intent. Avoid cryptic single-letter names except for standard loop indexes (`i`, `j`).
2. **Short, Focused Functions:** Functions should ideally perform a single task and fit on a single screen (under 40 lines where practical).
3. **No Dead Code:** Remove commented-out code blocks, unused imports, abandoned test scripts, and temporary print statements before completing any phase.
4. **Purposeful Comments:** Document *why* something is done (business rules, edge case handling, non-obvious algorithms), not *what* the code does. Preserve existing docstrings.
5. **No Unrelated Refactoring:** Never refactor unrelated files or modules outside the approved scope of the active phase.

---

## 6. Testing, Quality Assurance, and Evaluation Standards

### 6.1 Mandatory Testing Within Every Phase
Testing is an integral deliverable of every phase, not an activity postponed to the end of the project. A phase is not complete until all its planned tests and evaluations are implemented, executed, and passing.

### 6.2 The 8-Step Phase Testing Protocol
For every implementation phase `X`:

```
[1. Read docs/phaseX_evals.md]
        │
        ▼
[2. Implement Planned Unit, Integration & API Tests]
        │
        ▼
[3. Execute Automated & Verification Test Suite]
        │
        ▼
[4. Verify Actual Results Against Expected Results]
        │
        ▼
[5. Record Execution Evidence & Logs]
        │
        ▼
[6. Investigate & Fix Failures (No Test Weakening)]
        │
        ▼
[7. Add Regression Tests for Discovered Defects]
        │
        ▼
[8. Update docs/phaseX_evals.md with Final Results]
```

1. **Review Evaluation Matrix:** Read `docs/phaseX_evals.md` to identify all required evaluation IDs, test categories, target metrics, and verification methods.
2. **Implement Test Cases:** Write automated tests covering planned evaluation cases in `tests/`.
3. **Execute Suite:** Run the test suite using `pytest` with appropriate flags (e.g., `pytest tests/unit tests/integration -v`) along with any planned CLI or schema inspection checks.
4. **Compare Outcomes:** Compare observed outcomes against the documented expected behavior and pass/fail thresholds.
5. **Document Evidence:** Capture raw terminal output, test run summaries, and timing metrics.
6. **Investigate Defects:** If a test fails, investigate the root cause in the application logic. **Never modify or weaken test assertions merely to make them pass.**
7. **Add Regression Tests:** For every bug or unexpected failure encountered during testing, write an explicit regression test case.
8. **Synchronize Evaluation Register:** Update the results, pass/fail status, execution timestamps, and notes in `docs/phaseX_evals.md`.

### 6.3 Test Categories & Scope Alignment
- **Unit Tests:** Fast, isolated tests of pure business logic, Pydantic schemas, and individual utility functions with mocked external dependencies.
- **Integration Tests:** Verification of database transactions, Alembic migrations, foreign key enforcement, repository queries, and Redis/RQ task dispatching.
- **API Contract Tests:** Validation of FastAPI endpoints, HTTP response codes, headers, and payload schemas against the contracts in `architecture.md`.
- **Retrieval & RAG Evaluations:** Automated testing of policy search accuracy, Top-K recall, MRR, citation provenance, and prompt injection resilience.
- **Demo Authentication & Security Tests:** Verifying server-validated demo bearer token enforcement, unauthorized access rejection (HTTP 401), and secret leak prevention. (Do not introduce production RBAC tests before RBAC is in scope; RBAC is deferred to post-MVP under `U-012`).

### 6.4 Non-Negotiable Verification Rules
- **No Claim Without Execution:** Never claim a test passed unless it was physically executed in the environment and exited with status 0.
- **Zero Fabrication:** Never fabricate test outputs, execution logs, performance figures, coverage percentages, or evaluation results. Do not claim 100% runtime coverage merely because every planned evaluation case has a mapping.
- **Verification Methods:** Not every evaluation must be a unit test. Inspection and integration verifications (e.g., database schema catalog checks, Alembic CLI rollforward, file count assertions) are approved verification methods when specified in `docs/phaseX_evals.md`.
- **Blocked Test Protocol:** If a planned evaluation case cannot be executed because a genuine external dependency is unresolved or deferred:
  1. Mark its status as `BLOCKED` in `docs/phaseX_evals.md`.
  2. Document the exact blocking reason and reference the relevant `docs/unresolved.md` item.
  3. A phase cannot pass its completion gate if mandatory non-deferred evaluations are blocked without user authorization. Never declare a blocked evaluation passed.

---

## 7. Edge Case Documentation Lifecycle

### 7.1 Purpose & Structure of `docs/phaseX_edgecases.md`
Every phase `X` has a dedicated edge-case document containing two distinct, permanent sections:
1. **Pre-Implementation Edge Cases:** Edge cases identified during architectural planning before implementation began.
2. **Implementation-Discovered Edge Cases:** Edge cases discovered during active coding, data inspection, integration, or failure testing.

### 7.2 Discovered Edge Case Protocol & Naming Convention
Whenever a genuinely new edge case, unexpected data anomaly, or unanticipated boundary condition is uncovered during implementation:
1. Halt and verify whether the edge case is already covered under Pre-Implementation Edge Cases.
2. If genuine and novel, add it to the **Implementation-Discovered Edge Cases** section in `docs/phaseX_edgecases.md`.
3. **Reconciled Naming Convention:** Discovered edge cases must follow the established `P{X}-EC-###` numbering sequence, continuing sequentially from the last pre-implementation edge case (e.g., starting at `P1-EC-013` for Phase 1). This preserves unique, stable IDs without renumbering existing cases or introducing conflicting ID prefixes.
4. Record the required fields:
   - **ID:** `P{X}-EC-###`
   - **Title:** Concise, descriptive summary.
   - **Category:** Domain / Data Integrity / Security / Concurrency.
   - **Triggering Condition:** Exact input, query, or state that causes the anomaly.
   - **Observed Behavior:** What actually occurred before mitigation.
   - **Expected Behavior:** What the system should authoritatively do.
   - **Resolution / Mitigation:** The code, schema, or configuration fix applied.
   - **Automated Test Reference:** The specific test file and test function validating the fix.
5. Create a corresponding evaluation entry in `docs/phaseX_evals.md`.
6. Add an automated regression test in `tests/`.

### 7.3 Edge Case Lifecycle Rules
- **No Speculative Padding:** Do not add theoretical or speculative entries to the Discovered section if no actual anomaly occurred during implementation.
- **No Duplication:** Do not duplicate an existing pre-implementation edge case merely because it was tested and confirmed.
- **Unchanged Section Integrity:** If zero new edge cases are uncovered during a phase, leave the Implementation-Discovered section explicitly noted as: *"No implementation-discovered edge cases encountered during Phase X."*

---

## 8. Unresolved Decision Register Lifecycle

### 8.1 Purpose & Role of `docs/unresolved.md`
`docs/unresolved.md` is the project's permanent, living register of unresolved questions, architectural ambiguities, dataset dependencies, and binding decisions. It prevents unverified assumptions from silently corrupting the codebase.

### 8.2 Mandatory Review Triggers
The implementer must review and consult `docs/unresolved.md`:
1. **At the start of every phase** before planning or writing code.
2. **Whenever an ambiguous requirement or unexpected condition arises** (§2).
3. **Immediately after the user provides an explicit decision** on an open issue.
4. **Whenever a dataset inspection or technical discovery reveals a new dependency.**
5. **At the end of every phase** during the post-implementation synchronization gate.

### 8.3 Item Resolution Protocol
When an open unresolved item is formally decided:
1. Locate the item by its permanent ID (e.g., `U-001`, `U-003`).
2. Update its status from `OPEN` or `BLOCKED` to `RESOLVED`.
3. Document the approved decision, technical details, and user authorization date.
4. Record supporting evidence (e.g., test results, dataset analysis, migration filename).
5. Preserve the complete historical context and original ID.
6. Move the entry to the Resolved Items section in accordance with the established document formatting.

### 8.4 New Uncertainty Creation Protocol
When a genuine new ambiguity arises:
1. Check existing entries to ensure it is not already tracked.
2. Assign the next sequential ID (e.g., `U-014`).
3. Fill out all standard fields: Title, Category, Impacted Phases, Description, Blocking Impact, Options Considered, and Recommendation.
4. Follow the **Mandatory Clarification Procedure** (§2) to seek user approval before implementing affected components.

### 8.5 Integrity Rules
- Never remove, delete, or renumber existing IDs.
- Never mark an item resolved merely because the implementer chose an assumption to proceed.
- Never alter unrelated entries during updates.

---

## 9. Mandatory Phase Walkthrough Documentation

### 9.1 Purpose and Personal Study Role
After every implementation phase is completed and verified, the implementer must author a comprehensive phase walkthrough document at:
```
walkthroughs/phaseX_walkthrough.md
```
*(e.g., `walkthroughs/phase1_walkthrough.md` for Phase 1)*

The `walkthroughs/` directory serves as personal study, technical education, and architectural review documentation. It enables any developer to understand the codebase deeply and independently without needing past conversation logs.

### 9.2 Git Exclusion Requirement
The `walkthroughs/` directory must be strictly excluded from git tracking:
- The root `.gitignore` file must contain `/walkthroughs/`.
- Walkthrough files must **never** be committed, staged, or pushed to the public git repository.
- Verify exclusion using `git status --ignored` before finishing any task.

### 9.3 Walkthrough Structure & Content Requirements
Every `phaseX_walkthrough.md` must be thoroughly written and contain the following ten standardized sections (A through J):

#### A. Phase Overview
- Phase number and official title.
- Core objective of the phase.
- Approved implementation scope satisfied.
- Prerequisites verified prior to execution.
- Final completion status and date.

#### B. What Was Implemented
For every meaningful file, module, and component created or modified:
- File path and module name.
- Primary responsibility and architectural layer.
- Key classes, functions, models, and schemas introduced.
- How the component works internally.
- How it interacts with other components across boundaries.
- Technical rationale explaining why this implementation design was chosen.

#### C. Architecture and Execution Flow
- Detailed explanation of the implemented request, data, and execution flows.
- Include clear Mermaid sequence diagrams or ASCII architectural flowcharts.
- Concise pseudocode or step-by-step logic traces for critical paths.
- **Rule:** Never document speculative architecture that was not actually implemented in code.

#### D. Database Changes
Where applicable:
- New tables, columns, indexes, and constraints added.
- Entity-relationship details and foreign key relationships.
- Alembic migration version IDs and filenames.
- Transaction boundaries, concurrency locks, and idempotency guarantees.
- Rationale for schema design choices.

#### E. Testing and Evaluation
- Summary of test suites implemented (`tests/unit/`, `tests/integration/`, etc.).
- Coverage of planned evaluation cases from `docs/phaseX_evals.md`.
- Exact commands executed in the terminal (e.g., `pytest tests/ -v`).
- Actual test outcomes, assertion results, and performance measurements.
- Real failures encountered during testing, root causes identified, fixes applied, and retest outcomes.
- Any remaining limitations or blocked evaluations.

#### F. Edge Cases
- Anticipated edge cases from `docs/phaseX_edgecases.md` verified.
- Genuinely discovered edge cases added during implementation.
- How each significant edge case was mitigated in code.
- Specific regression tests implemented to prevent regression.

#### G. Decisions Made
- Key technical decisions made during the phase.
- Formal user approvals received and clarification questions resolved.
- Alternatives considered and trade-off analysis.
- Rationale for the chosen approach.
- Cross-references to resolved IDs in `docs/unresolved.md`.

#### H. Problems and Debugging
- Real technical difficulties, unexpected package incompatibilities, or subtle bugs encountered during implementation.
- Diagnostic steps taken to isolate the problem.
- Technical explanation of the resolution.
- **Rule:** Do not invent artificial problems if implementation was straightforward.

#### I. Learning Notes
- Educational, clear explanations of key technical concepts, design patterns, or libraries introduced in this phase (e.g., SQLAlchemy 2.0 async sessions, Full-Text Search indexing, Pydantic v2 validation internals).
- Written in clear pedagogical language to foster independent developer mastery.

#### J. Final Verification and Limitations
- Concise bulleted summary of what is complete and working.
- Summary of what has been verified with concrete test proof.
- Open questions or items deferred to subsequent phases.
- Known technical limitations affecting upcoming phases.

---

## 10. Mandatory Post-Implementation Synchronization Protocol

### 10.1 The 13-Step Synchronization Protocol
Upon finishing the code and testing for any phase `X`, the implementer must execute the following 13-step synchronization protocol in sequence before reporting completion:

```
[1. Execute All Applicable Evaluations]
                │
                ▼
[2. Review docs/phaseX_edgecases.md]
                │
                ▼
[3. Record Discovered Edge Cases (if any)]
                │
                ▼
[4. Review docs/phaseX_evals.md]
                │
                ▼
[5. Record Actual Test Results & Evidence]
                │
                ▼
[6. Review docs/unresolved.md]
                │
                ▼
[7. Close Resolved Items with Evidence]
                │
                ▼
[8. Add Genuinely New Unresolved Items (if any)]
                │
                ▼
[9. Verify Implementation Against Plan]
                │
                ▼
[10. Generate walkthroughs/phaseX_walkthrough.md]
                │
                ▼
[11. Inspect Git Working Tree via git status]
                │
                ▼
[12. Deliver Phase Completion Report]
                │
                ▼
[13. STOP AND WAIT FOR USER APPROVAL]
```

1. **Execute All Evaluations:** Run the complete automated test suite and record exit codes and test summaries.
2. **Review Edge Cases Document:** Open and examine `docs/phaseX_edgecases.md`.
3. **Record Discovered Edge Cases:** Document any genuine implementation-discovered edge cases in §7.
4. **Review Evaluation Document:** Open and examine `docs/phaseX_evals.md`.
5. **Record Actual Results:** Update evaluation tables with exact test results, pass/fail status, and execution evidence.
6. **Review Decision Register:** Open and examine `docs/unresolved.md`.
7. **Close Resolved Items:** Mark items resolved during the phase as `RESOLVED`, adding clear technical evidence.
8. **Add New Uncertainties:** If new technical questions emerged that affect future phases, log them with permanent IDs.
9. **Verify Against Plan:** Audit all delivered files against `docs/implementation_plan.md` section for Phase `X`.
10. **Create Walkthrough:** Author `walkthroughs/phaseX_walkthrough.md` covering all required sections (A through J).
11. **Inspect Git Working Tree:** Run `git status` to verify changed, added, deleted, and untracked files. Ensure no accidental secrets or stray files exist.
12. **Deliver Phase Completion Report:** Present a structured report summarizing deliverables, test outcomes, resolved items, and working tree status.
13. **Halt and Await Approval:** **Stop immediately.** Do not begin work on phase `X+1` until the user provides explicit written authorization.

---

## 11. Git and Repository Hygiene Standards

### 11.1 No Automatic Git Commits, Pushes, or Repository History Changes

> [!CAUTION]
> **This is a non-negotiable project rule. The default is always: leave all changes uncommitted and unpushed.**

Developers and autonomous AI agents must strictly adhere to the following ten binding rules:

1. **Never execute `git add`, `git commit`, or `git push` automatically.**
2. **Never create or switch branches, merge, rebase, cherry-pick, reset, tag, or otherwise modify repository history without explicit user authorization.**
3. **Never force-push or perform destructive Git operations without specific prior authorization.**
4. **Approval to implement a phase does not imply approval to commit, push, stage, or change branches.**
5. **Approval to create or modify documentation does not imply Git authorization.**
6. **Completing a phase does not authorize any Git mutation.**
7. **Do not infer authorization from a previous phase or previous Git operation.**
8. **Before any Git-mutating operation, obtain explicit authorization identifying the intended operation.**
9. **Read-only commands such as `git status`, `git diff`, and `git log` are permitted.**
10. **At the end of each phase, report changed, added, deleted, and untracked files. Wait for the user to decide what to stage, commit, or push.**

### 11.2 Working Tree Hygiene & Reviewed State
- **Uncommitted Changes are Permitted:** A "clean Git working tree" (zero modified or untracked files) is **not** required. Uncommitted and untracked working files are expected and normal during development.
- **Reviewed State Required:** The implementer must inspect `git status` before reporting completion to ensure:
  - No committed or untracked secrets (`.env`, credentials, private keys).
  - No committed build outputs (`dist/`, `node_modules/`, `__pycache__/`, `.pytest_cache/`).
  - No committed personal walkthrough files (`/walkthroughs/`).
  - No unintended file touches outside the active phase scope.
- **Prohibition on Auto-Cleanup:** Never automatically stage, commit, push, delete, or reset files to manufacture a clean working tree.

---

## 12. Definition of Done (DoD)

A development phase `X` is **authoritatively complete** if and only if all eleven of the following criteria are satisfied:

1. [ ] **Scope Compliance:** All deliverables specified in `docs/implementation_plan.md` for Phase `X` exist and adhere to the architectural contracts in `docs/architecture.md`.
2. [ ] **No Scope Creep:** Zero unapproved features, operational tools, endpoints, database entities, or dependencies have been added.
3. [ ] **Tests Executed & Passing:** All planned unit, integration, and verification tests corresponding to `docs/phaseX_evals.md` have been executed and passed (100% pass rate for active mandatory cases).
4. [ ] **Evidence Recorded:** Genuine terminal logs, test summaries, and execution metrics are documented in `docs/phaseX_evals.md`.
5. [ ] **Pre-Implementation Edge Cases Verified:** All anticipated edge cases in `docs/phaseX_edgecases.md` have been evaluated and verified.
6. [ ] **Discovered Edge Cases Documented:** Any novel edge cases discovered during implementation are recorded with permanent `P{X}-EC-###` IDs and regression tests.
7. [ ] **Unresolved Register Synchronized:** All decisions resolved during Phase `X` are updated in `docs/unresolved.md` with supporting evidence.
8. [ ] **Walkthrough Created:** `walkthroughs/phaseX_walkthrough.md` is fully written covering sections A through J, and is confirmed ignored by git.
9. [ ] **Reviewed Working Tree:** The working tree has been inspected via `git status`, contains no accidental secrets or untracked clutter, and all modified/untracked files are documented in the completion report. Changes remain uncommitted and unpushed pending explicit user Git instruction.
10. [ ] **Completion Report Delivered:** A formal Phase Completion Report has been delivered to the user.
11. [ ] **User Approval Received:** The user has reviewed the deliverables and explicitly approved completion of the phase.

> [!CAUTION]
> If any single criterion above is unmet, the phase cannot be claimed as complete. It must be reported as in-progress, blocked, or awaiting approval.

---

## 13. Precision Terminology and Anti-Vagueness Dictionary

### 13.1 Authoritative Contrast Pairs
To prevent ambiguity and misleading claims, all documentation, comments, and reports must adhere strictly to these technical distinctions:

| Term A | Term B | Distinct Operational Meaning |
| :--- | :--- | :--- |
| **Planned** | **Implemented** | *Planned* means specified in a design document; *Implemented* means physical code exists in the repository. |
| **Implemented** | **Tested** | *Implemented* means the code is written; *Tested* means an automated or structured test has executed against that code. |
| **Tested** | **Passed** | *Tested* means a test ran; *Passed* means the test exited with zero errors and met all assertion criteria. |
| **Proposed** | **Approved** | *Proposed* means suggested in conversation or docs; *Approved* means the user explicitly authorized it. |
| **Resolved** | **Deferred** | *Resolved* means an authoritative decision was made with evidence; *Deferred* means intentionally postponed to a future phase. |
| **Missing Source Data** | **Invalid Source Data** | *Missing data* is a permissible null/absent field (e.g. ticket without order); *Invalid data* violates relational integrity or schema constraints and requires structured retention/warning or rejection. |
| **Citation Provenance** | **Claim Correctness** | *Citation provenance* tracks which chunk was retrieved; *Claim correctness* measures whether the generated text is factually true. |
| **AI Recommendation** | **Backend Execution** | *AI recommendation* is an advisory proposal; *Backend execution* is a deterministic, authorized system mutation. |
| **Request Idempotency** | **Business Uniqueness** | *Request idempotency* ensures replaying an identical HTTP request produces the same response; *Business uniqueness* prevents duplicate business operations (e.g., duplicate tickets for the same incident). |
| **Operational Failure** | **Business Validation Failure** | *Operational failure* is a 5xx crash, network timeout, or database outage; *Business failure* is a 4xx validation rejection (e.g., ticket closed, customer ineligible). |

### 13.2 Prohibited Vague Phrases
The following ambiguous phrases are strictly banned from technical documents, code comments, and completion reports:

| Prohibited Vague Phrase | Why It Is Unacceptable | Mandatory Observable Replacement |
| :--- | :--- | :--- |
| *"Handle appropriately"* | Hides undefined behavior and error contracts. | State the exact HTTP code, exception type, and rollback behavior (e.g., *"Raise `TicketNotFoundException`, returning HTTP 404 with JSON error body"*). |
| *"Use best practices"* | Vague model assumption; subjective. | Specify the exact pattern and standard (e.g., *"Use SQLAlchemy 2.0 `select()` syntax with explicit async session management"*). |
| *"Ensure robustness"* | Non-testable hand-waving. | State the concrete failure mode and test (e.g., *"Wrap DB commit in a retry loop handling `OperationalError` up to 3 times with exponential backoff"*). |
| *"Optimize as needed"* | Invites premature optimization or dead code. | Specify performance thresholds (e.g., *"Ensure response latency p95 is under 200ms on a 10,000-row test dataset"*). |
| *"Make reasonable assumptions"* | Directly violates non-assumption rule. | Follow the **Mandatory Clarification Procedure** (§2) and await user decision. |
| *"Draft is ungrounded because customer is ineligible"* | Conflates business outcome with grounding. | Grounding evaluates whether the policy citations support the statement. If the policy says "no refunds after 30 days" and the draft states "you are ineligible because 30 days have passed", the draft is **fully grounded**. |

---

## 14. Compliance and Operational Enforcement

1. **Continuous Verification:** This document must be checked at every step of development. Autonomous agents must verify compliance prior to issuing final turn responses.
2. **Zero Tolerance for Hallucinated Results:** Any claim of passing evaluations or successful execution without verified terminal evidence is treated as a critical operational failure.
3. **Phase 1 Implementation Gate:** Implementation of Phase 1 must not begin until the user has formally reviewed and approved `docs/conventions.md`.
