
# TrustDesk — Problem Statement

## 1. Project Overview

**TrustDesk** is an AI-assisted customer support operations application designed to help human support agents process customer tickets accurately, efficiently, and safely.

The system combines traditional backend services with AI capabilities to:

- Retrieve customer tickets and their associated customer and order information.
- Automatically classify tickets by issue category, priority, and escalation requirement.
- Retrieve relevant company policies using Retrieval-Augmented Generation (RAG).
- Generate customer-response drafts grounded in retrieved policy evidence.
- Recommend a refund-review action when appropriate, subject to explicit human approval.
- Protect against prompt injection, sensitive-data exposure, unsupported claims, and unauthorized actions.
- Record AI execution traces and evaluate system behavior against supplied test cases.

**TrustDesk is an internal support-agent tool, not a customer-facing chatbot.**

The AI assists agents with decisions and response preparation. It does not independently authorize sensitive business operations.

---

## 2. Core Problem

Customer support agents must understand customer complaints, inspect related orders, identify applicable company policies, determine urgency, and prepare appropriate responses.

Performing these activities manually can be time-consuming and inconsistent.

Introducing AI creates additional risks:

- Incorrect ticket classification.
- Responses that contradict company policies.
- Fabricated or unsupported policy citations.
- Incorrect refund or warranty eligibility calculations.
- Prompt injection through customer messages or knowledge documents.
- Exposure of sensitive customer information.
- Unauthorized or duplicate operational actions.

TrustDesk must reduce repetitive support work while ensuring that business decisions remain verifiable, controlled, and auditable.

---

## 3. Required Functional Scope

### 3.1 Data Ingestion and Persistence

The application must load the supplied project data:

- Customers
- Orders
- Support tickets
- Knowledge-base documents
- Tool catalog
- Evaluation cases

PostgreSQL must persist the operational data required by the application, including:

- Customers, orders, and tickets
- Knowledge documents and their original identifiers
- AI-generated drafts and triage results
- Proposed and executed tool actions
- Human approval decisions
- AI execution traces
- Evaluation results and relevant job states

The application must preserve original identifiers from the supplied dataset, particularly knowledge-base document IDs such as `KB-REFUND-001`.

Return and warranty policy windows must be evaluated relative to the ticket's `created_at` timestamp, not the current system date.

### 3.2 Ticket Management APIs

The backend must expose authenticated REST APIs that allow the support-agent interface to:

- List available support tickets.
- Retrieve an individual ticket.
- Retrieve the customer and order context associated with a ticket.
- Trigger AI triage and draft generation.
- Retrieve generated results and supporting citations.
- Inspect and approve or reject a proposed refund-review action.
- Retrieve evaluation results and relevant execution statuses.

The frontend must communicate through backend APIs rather than accessing databases or AI providers directly.

### 3.3 AI Ticket Triage

The system must analyze a support ticket and produce structured classification results.

**Allowed categories:**

- `shipping`
- `refund`
- `warranty`
- `billing`
- `account_security`
- `general`

**Allowed priorities:**

- `low`
- `medium`
- `high`
- `urgent`

Each triage result must also include an escalation flag indicating whether human intervention is required.

LLM output must be validated against a defined schema before it is accepted or persisted as a valid result.

Invalid or failed AI responses must not be silently treated as successful classifications.

### 3.4 Policy Retrieval and Grounded Draft Generation

TrustDesk must use RAG to retrieve relevant company policy evidence before generating customer-response drafts.

The retrieval system must:

- Index company policy documents into searchable sections.
- Preserve the original knowledge-base document ID for every indexed section.
- Maintain a reference identifying the specific section within its original document.
- Retrieve multiple relevant sections when a ticket involves more than one policy.
- Supply retrieved evidence together with relevant ticket and order context to the LLM.
- Include original knowledge-base document IDs in generated citations.
- Validate citations against retrieved documents.
- Avoid unsupported policy claims and escalate cases where sufficient evidence is unavailable.

Policy retrieval must be implemented behind a common interface so that the retrieval engine can be changed without rewriting the ticket-processing and draft-generation workflows.

### 3.5 Guardrails and Sensitive Actions

Customer messages and retrieved documents must be treated as untrusted data, never as authoritative instructions.

The application must implement safeguards against:

- Prompt injection.
- Attempts to bypass identity verification.
- Unsupported discount or coupon claims.
- Requests to reveal hidden instructions, prompts, or secrets.
- Unauthorized access to sensitive information.
- Unsupported or unsafe operational actions.

The supplied adversarial knowledge document `KB-ADVERSARIAL-001` must be included in security evaluation.

Sensitive information supplied to AI providers and recorded in logs must be minimized or redacted where appropriate.

**The only sensitive operational action implemented in scope is `start_refund_review`.**

The action must follow these rules:

1. The AI may recommend starting a refund review.
2. The recommendation must be recorded as a pending action.
3. An authenticated human agent must explicitly approve or reject it.
4. The backend must independently validate authorization and applicable business rules.
5. Only an approved action may execute.
6. Execution must use a persistent idempotency key and transactional protection against duplicate execution.

Starting a refund review does not issue a refund or transfer money.

The application must not implement `create_replacement_order` as an additional sensitive action.

### 3.6 Support-Agent Dashboard

The application must provide a minimal internal dashboard allowing support agents to:

- Browse and inspect tickets.
- View linked customer and order information.
- Trigger AI triage.
- Inspect category, priority, and escalation results.
- Generate and review policy-grounded response drafts.
- Inspect source citations.
- Approve or reject refund-review recommendations.
- View evaluation results.

The interface must prioritize functional completeness and clarity over advanced visual design.

Protected backend operations must require authentication.

### 3.7 Background Processing and Execution Traces

Long-running AI and evaluation operations must execute without blocking unrelated API requests.

The application must support background job execution and job-status tracking.

Each AI execution trace must record, at minimum:

- Ticket identifier
- Run type
- Retrieved knowledge-document identifiers
- Proposed tool actions
- Executed tool actions
- Guardrail outcome
- Final execution status

Execution traces must avoid unnecessary exposure of sensitive information.

### 3.8 Testing and Evaluation

The application must include automated tests and an evaluation runner.

Automated tests must cover:

- REST API behavior and validation.
- Data ingestion and identifier preservation.
- Ticket and order relationships.
- AI structured-output validation.
- Retrieval and citation correctness.
- Refund-review approval and rejection.
- Authorization and duplicate-action prevention.
- Job failures and retries.
- Prompt-injection and other adversarial scenarios.

AI-dependent application tests must support mocked AI responses to provide deterministic results.

A CLI command or API endpoint must execute the supplied evaluation cases from `data/eval_cases.jsonl`.

The evaluation report must measure:

- Ticket triage accuracy.
- Citation coverage and validity.
- Unsafe-action blocking.
- Escalation behavior.

The application must distinguish deterministic software tests from evaluations of actual LLM behavior.

---

## 4. Agreed Technical Architecture

The following architecture decisions define the intended implementation.

| Component | Decision |
|---|---|
| Backend | Python + FastAPI |
| Primary database | PostgreSQL |
| Initial policy retrieval | PostgreSQL Full-Text Search |
| Planned semantic retrieval | Qdrant vector database |
| Retrieval abstraction | Common interface such as `search_policies(query)` |
| AI integration | Provider-independent adapter with mock support |
| AI output validation | Pydantic structured schemas |
| Frontend | React + Tailwind CSS |
| Initial authentication | Server-validated demo bearer token |
| Future authentication improvement | JWT-based authentication with role-based authorization |
| Sensitive action | `start_refund_review` only |
| Action safety | Human approval, backend validation, transactional idempotency |
| Background processing | Redis-backed queue using RQ and a separate Python worker |
| Automated testing | pytest |
| Evaluation | Supplied JSONL cases with CLI/API reporting |

### Retrieval Implementation Strategy

The initial MVP will use PostgreSQL Full-Text Search for policy retrieval.

Qdrant will be introduced after the initial working MVP as a planned semantic retrieval enhancement.

The system must preserve a common retrieval interface from the beginning to avoid coupling AI workflows to a specific search database.

The retrieval approaches can then be compared through evaluation before deciding whether semantic or hybrid retrieval should replace or complement full-text search.

### Background Processing Strategy

FastAPI will handle incoming API requests.

Long-running AI and evaluation tasks will be submitted to a Redis-backed RQ queue and processed by a separate Python worker.

PostgreSQL will remain the persistent source for application records, approvals, traces, and evaluation results.

Simple database reads and other short operations do not need to be queued.

### AI Integration Strategy

All LLM calls must pass through a provider adapter.

The application must not depend directly on provider-specific SDK calls throughout its business logic.

This enables provider replacement, predictable mock-based tests, and centralized handling of AI errors.

The exact LLM provider and model will be selected during implementation planning.

---

## 5. Scope Boundaries

### In Scope

- Supplied dataset ingestion.
- REST APIs for ticket and context management.
- AI ticket classification.
- RAG-based policy retrieval.
- Policy-grounded response drafts with citations.
- Human-controlled refund-review action.
- Basic authentication and authorization checks.
- AI safety guardrails.
- Background execution for long-running work.
- Minimal internal support-agent dashboard.
- Automated tests, adversarial tests, and evaluation reports.
- Minimal execution traces.

### Out of Scope

- Customer-facing conversational chatbot.
- Actual refund payment processing.
- Replacement-order creation.
- Autonomous execution of sensitive business actions.
- Full production identity-management platform.
- Advanced enterprise role-management features in the initial MVP.
- Unrelated integrations or features not required by the supplied problem statement.

Any additional feature must be justified against the core requirements before being introduced.

---

## 6. Expected Deliverables

The completed project must include:

- A functioning backend and support-agent frontend.
- Database setup and supplied-data ingestion.
- Working AI triage, policy retrieval, and cited draft generation.
- A safe, approval-gated refund-review workflow.
- Automated tests and evaluation runner.
- Evaluation results and a summary of limitations.
- Setup and execution instructions.
- API and architecture documentation.
- A public GitHub repository.
- A demonstration video.

---

## 7. Definition of Success

TrustDesk is considered functionally complete when:

1. The supplied data can be loaded and accessed reliably.
2. Support agents can browse tickets and linked customer/order information.
3. AI triage produces validated category, priority, and escalation outputs.
4. Relevant policies can be retrieved and cited using their original document IDs.
5. Draft responses are grounded in policy evidence, with unsupported claims rejected or escalated.
6. Prompt-injection and unsafe-action safeguards are implemented and tested.
7. `start_refund_review` cannot execute without authenticated human approval.
8. Repeated action requests cannot create duplicate executions.
9. Long-running operations do not block unrelated API requests.
10. Execution traces and evaluation reports can be inspected.
11. Automated tests and supplied evaluation cases can be executed reproducibly.
12. The application can be set up, demonstrated, and reviewed using its documentation.

No specific accuracy or safety percentage is assumed before evaluation. Actual results and known limitations must be reported.

---

## 8. Implementation Guiding Principle

**Build the smallest complete, reliable TrustDesk system that satisfies the supplied requirements before introducing optional complexity.**

The implementation must prioritize:

- Correctness over feature quantity.
- Deterministic backend validation over trusting LLM output.
- Traceable policy evidence over unsupported AI claims.
- Human authorization over autonomous sensitive actions.
- Testability and clear component boundaries.
- Incremental implementation with verification at every phase.

This document defines **what must be built and the agreed architectural direction**.

The detailed component design belongs in `docs/architecture.md`.

The implementation order, milestones, acceptance criteria, and phase-specific edge cases belong in `docs/implementation_plan.md`.

Coding standards, repository rules, and development workflow requirements belong in `docs/conventions.md`.
