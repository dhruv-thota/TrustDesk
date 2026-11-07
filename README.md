# TrustDesk — AI-Assisted Customer Support Operations Platform

**Document Version:** 1.0.0  
**Phase:** Phase 8 Final Verification  
**Target Environment:** Local Python Virtualenv + Docker Compose + Node.js  

TrustDesk is an internal operations platform designed to assist human customer support agents in triaging customer inquiries, drafting policy-grounded responses, and safely initiating controlled, non-autonomous operational actions (specifically `start_refund_review`).

---

## 1. Project Overview & Problem Solved

Customer support teams face high ticket volumes, strict return and warranty policies, and the risk of costly errors when issuing refunds or replacement promises. Traditional AI chatbot integrations often fail in enterprise support because they:
1. **Act autonomously:** Direct tool execution by LLMs risks hallucinated refunds and financial loss.
2. **Hallucinate policy terms:** Generic LLMs invent return windows or promise promotional discounts that contradict company policies.
3. **Lack auditable provenance:** Responses are generated without citations linking claims back to actual policy documents.
4. **Vulnerable to prompt injection:** Customers can trick models into granting unauthorized returns or exposing internal system instructions.

### The TrustDesk Solution
TrustDesk eliminates autonomous execution by placing the human support agent in the loop:
- **AI Recommendation Only:** The AI analyzes tickets, retrieves relevant policy documents via PostgreSQL Full-Text Search (FTS), and drafts suggested responses with explicit citation chips.
- **Strict Grounding:** Responses are validated across three levels (citation provenance, quoted snippet support & discount defense, and temporal eligibility calculations).
- **Human Approval Gate:** Operational actions (`start_refund_review`) can **never** be executed autonomously. They are persisted in `pending_approval` state and strictly require an authenticated human agent to review, adjust, and approve.
- **No Money Disbursement:** TrustDesk registers formal investigation reviews; it does not communicate with bank gateways or disburse funds.

---

## 2. Internal Support-Agent Workflow

TrustDesk supports four canonical operational workflows (`docs/architecture.md` §12):

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ 1. Ticket Queue │ ────> │ 2. AI Triage    │ ────> │ 3. RAG Retrieval│
│ Select inquiry  │       │ Category & Pri. │       │ Postgres FTS    │
└─────────────────┘       └─────────────────┘       └────────┬────────┘
                                                             │
┌─────────────────┐       ┌─────────────────┐                ▼
│ 6. Audit Trace  │ <──── │ 5. Human Review │ <──── ┌─────────────────┐
│ Immutable log   │       │ Approve / Reject│       │ 4. Grounded     │
└─────────────────┘       └─────────────────┘       │    Draft + Action│
                                                    └─────────────────┘
```

1. **Ticket Ingestion & Context Loading:** An agent selects an open ticket. The system loads full customer profile, order history, and delivery tracking.
2. **AI Triage:** The agent requests triage classification. The system assigns a category (`refund`, `warranty`, `shipping`, `billing`, `account_security`, `general`), priority, and escalation alert.
3. **RAG Policy Retrieval:** PostgreSQL Full-Text Search queries structured knowledge base sections (`kb_sections`) using title weighting (`'A'`) and content weighting (`'B'`) via `ts_rank_cd`.
4. **Grounded Draft Generation:** A draft response is generated citing specific policy sections. Dates are calculated relative to `ticket.created_at` against confirmed delivery dates. If evidence is missing or return windows have expired, the system flags the draft and recommends human escalation.
5. **Human Action Approval / Rejection:** If eligible, the system proposes `start_refund_review` in `pending_approval` status. The human agent inspects the action card and explicitly clicks **Approve** (with server-validated token and request idempotency key) or **Reject**.
6. **Immutable Audit Logging:** Every triage, draft generation, and action approval writes a complete trace to PostgreSQL `execution_traces`.

---

## 3. Technology Stack

- **Backend Runtime:** Python 3.12 (PEP 8, strict type hints, Pydantic v2, SQLAlchemy 2.0).
- **Web Framework:** FastAPI (RESTful API, asynchronous route handling, standardized error envelopes).
- **Authoritative Database:** PostgreSQL 15 (SQLAlchemy 2.0 ORM, Alembic migrations, native Full-Text Search with `tsvector`, English dictionary, and GIN index).
- **Asynchronous Task Queue:** Redis 7 + Python RQ (background worker processing long-running evaluation benchmarks).
- **Frontend Dashboard:** React 18 + Vite + Tailwind CSS (responsive support-agent workspace with ticket queue, triage panel, draft viewer, and action card).
- **AI Model Abstraction:** `AIProviderAdapter` (supports offline deterministic `MockAIProvider`, Airtribe-compatible `OpenRouterAIProvider` via OpenAI-compatible API, and Google Gemini `LiveAIProvider` via `google-genai`).

---

## 4. High-Level Architecture

TrustDesk is organized as a clean, modular monolith:

```
TrustDesk/
├── trustdesk/
│   ├── api/v1/           # REST endpoints (tickets, triage, drafts, actions, evaluations, jobs, health)
│   ├── core/             # Configuration (pydantic-settings), database session, security, logging
│   ├── models/           # SQLAlchemy 2.0 declarative ORM models
│   ├── schemas/          # Pydantic v2 schemas for request/response validation
│   ├── services/         # Domain services (triage, draft grounding, citations, actions, ingestion)
│   ├── eval/             # Offline evaluation runner, metrics calculations, dataset loader
│   ├── worker/           # Background RQ worker and job service
│   └── cli.py            # Administrative CLI (dataset ingestion, policy chunking, FTS search)
├── frontend/             # React 18 + Vite support-agent dashboard
├── alembic/              # Database schema migrations (001 through 005)
├── data/                 # Operational source datasets & golden eval cases
├── tests/                # Automated pytest suites (unit, integration, adversarial, e2e)
├── docker-compose.yml    # PostgreSQL 15 & Redis 7 container orchestration
└── pyproject.toml        # Python project dependencies & build configuration
```

---

## 5. Prerequisites

Before running TrustDesk, ensure your system has:
- **Docker & Docker Compose** (v20.10+ / Compose v2.0+)
- **Python 3.11+** (Python 3.12.6 recommended)
- **Node.js 18+ & npm** (for frontend dashboard)
- **Git**

---

## 6. Environment Configuration

Copy the example configuration to `.env`:

```bash
cp .env.example .env
```

The default `.env` configuration is pre-tuned for local development:

```ini
# Database Configuration (Docker Compose maps PostgreSQL to port 5433)
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/trustdesk
DATABASE_URL_TEST=postgresql+psycopg://postgres:postgres@localhost:5433/trustdesk_test
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=trustdesk
POSTGRES_PORT=5433

# Redis Task Broker
REDIS_URL=redis://localhost:6379/0

# Authentication & Security
TRUSTDESK_DEMO_TOKEN=demo_secret_token_123

# Application Settings
ENVIRONMENT=development
LOG_LEVEL=INFO
APP_HOST=0.0.0.0
APP_PORT=8000

# AI Provider Configuration
# Supported options: "mock" (default, deterministic offline), "openrouter" (live LLM via OpenRouter), "live" (Google Gemini)
AI_PROVIDER=mock

# OpenRouter Configuration (required when AI_PROVIDER=openrouter)
# OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxx
# OPENROUTER_MODEL=openai/gpt-5-mini
# OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
# OPENROUTER_SITE_URL=http://localhost:5173
# OPENROUTER_SITE_NAME=TrustDesk

# Google Gemini Configuration (required when AI_PROVIDER=live)
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash
```

> [!NOTE]
> All automated tests (`pytest`) and offline evaluations run 100% offline using `MockAIProvider` without requiring live API keys or incurring network latency.

### 6.1 Switching Between Mock and OpenRouter AI Modes

TrustDesk's architecture cleanly isolates model inference behind the `AIProviderAdapter` protocol. To switch between offline mock mode and live LLM inference:

1. **Deterministic Mock Mode (Default):**
   ```ini
   AI_PROVIDER=mock
   ```
   Uses `MockAIProvider`. No external calls are made. Safe for automated CI, unit tests, and repeatable local demos.

2. **OpenRouter Live Mode (Airtribe Integration):**
   ```ini
   AI_PROVIDER=openrouter
   OPENROUTER_API_KEY=sk-or-v1-your-airtribe-key
   OPENROUTER_MODEL=openai/gpt-5-mini
   OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
   ```
   Uses `OpenRouterAIProvider` over OpenRouter's OpenAI-compatible endpoint. Features:
   - **Structured Output & Robust Parsing:** Requests strict JSON output schemas, and handles markdown fences automatically.
   - **Bounded Latency & Retries:** 15-second per-request timeout with at most one automatic retry for transient errors or rate limits (429).
   - **Untrusted Input Tagging:** Customer messages and retrieved policies are tagged with XML delimiters to neutralize prompt injection attempts.
   - **Advisory-Only Safety Boundary:** The model cannot trigger operational actions. Draft responses undergo deterministic 3-level guardrail verification (citation provenance check against retrieved sections, quoted snippet validation, and temporal eligibility calculations relative to `ticket.created_at`).
   - **Graceful Triage Fallback:** If the external API is unreachable or times out, the backend gracefully catches provider errors and marks triage for manual human escalation without crashing the service.

---

## 7. Infrastructure Startup (Docker Compose)

Start PostgreSQL 15 and Redis 7 in the background:

```bash
docker compose up -d
```

Verify that both containers are running and healthy:

```bash
docker compose ps
```

PostgreSQL is available on host port `5433` (to avoid conflicting with any local PostgreSQL instance on 5432). Redis is available on port `6379`.

### 7.1 Data Persistence & Test Isolation

TrustDesk stores development database records in a persistent named Docker volume (`postgres_data`).

- **Normal Startup (Preserves Data):**
  ```bash
  docker compose up -d
  ```
- **Normal Shutdown (Preserves Data):**
  ```bash
  docker compose stop
  # OR
  docker compose down
  ```
- **Destructive Commands to AVOID:**
  > [!CAUTION]
  > Never run `docker compose down -v` or `docker volume rm trustdesk_postgres_data` unless you explicitly intend to delete the persistent database volume and wipe all data.

- **Automated Test Isolation:**
  All backend tests (`pytest`) run strictly against the isolated test database `DATABASE_URL_TEST` (`trustdesk_test`). Running `pytest tests/` will never truncate or modify your development tickets, customers, or orders.

- **Verifying Development Ticket Counts:**
  ```bash
  ./.venv/bin/python -c '
  from trustdesk.core.config import settings
  from sqlalchemy import create_engine, text
  with create_engine(settings.database_url).connect() as conn:
      print("Tickets in Dev DB:", conn.execute(text("SELECT count(*) FROM tickets;")).scalar())
  '
  ```

- **Restoring Demo Data (Idempotent):**
  If records ever need to be restored or re-synced, use the existing idempotent CLI ingestion command:
  ```bash
  python -m trustdesk.cli ingest --data-dir ./data
  ```

- **Browser Session Authentication Note:**
  In accordance with security conventions (`docs/conventions.md`), the demo bearer token is stored strictly in browser `sessionStorage` (which is naturally cleared when closing a tab or browser window). When opening a fresh browser window at `http://localhost:5173`, click **Set Demo Token** in the top navigation bar to authenticate and populate the ticket queue.

---

## 8. Database Migrations

Set up your Python virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Apply all Alembic database schema migrations (001 through 005):

```bash
alembic upgrade head
```

This creates the source operational tables (`customers`, `orders`, `tickets`, `quarantined_records`), knowledge base tables with FTS indexes (`kb_documents`, `kb_sections`), AI and trace records (`triage_results`, `draft_responses`, `draft_citations`, `execution_traces`), human action approval tables (`proposed_actions`, `action_idempotency`), and evaluation tracking tables (`eval_runs`, `eval_results`).

---

## 9. Dataset Ingestion & Knowledge Base Indexing

Ingest the operational baseline datasets (`customers.json`, `orders.json`, `tickets.json`, `kb_documents.json`, `tool_catalog.json`):

```bash
python -m trustdesk.cli ingest --data-dir ./data
```

This command:
1. Ingests customer profiles and order histories with relational integrity.
2. Ingests support tickets with foreign-key quarantine (unresolvable order references are preserved in `raw_metadata["unresolved_order_id"]`).
3. Ingests policy markdown documents and parses them into discrete sections.
4. Generates PostgreSQL GIN full-text search tsvectors on `kb_sections`.
5. Loads the sensitive tool catalog into memory.

You can test knowledge base search directly via CLI:

```bash
python -m trustdesk.cli search-policies "refund window policy"
```

---

## 10. Backend API Startup

Start the FastAPI application with Uvicorn:

```bash
uvicorn trustdesk.main:app --host 0.0.0.0 --port 8000 --reload
```

The interactive OpenAPI documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health Endpoint: `http://localhost:8000/api/v1/health`

---

## 11. Asynchronous Background Worker Startup

In a separate terminal, start the Python RQ background worker to process asynchronous evaluation jobs:

```bash
source .venv/bin/activate
python -m trustdesk.worker.worker
```

The worker registers a heartbeat with Redis, monitors the queue, and executes evaluation runs without blocking API threads.

---

## 12. Frontend Dashboard Startup

In a separate terminal, install dependencies and launch the React dashboard:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Open your browser to:
```
http://localhost:5173
```

### Dashboard Features:
- **Demo Session Bar:** Selects or sets the demo bearer token stored safely in browser `sessionStorage`.
- **Ticket Queue:** Lists incoming tickets with status badges, priority filters, and search.
- **Context Viewer:** Displays linked customer information, delivery dates, and purchased items.
- **AI Triage Panel:** Triggers classification and displays category, priority, and escalation notices.
- **Draft Response Viewer:** Displays grounded draft responses with interactive citation chips revealing quoted policy snippets.
- **Action Approval Card:** Displays proposed `start_refund_review` actions. Agents can click **Approve** (with automated client-side idempotency keys) or **Reject**.
- **Evaluation Dashboard:** Submits background evaluation runs, tracks live job progress, and renders comprehensive U-009 metric reports.

---

## 13. Running Automated Tests

TrustDesk includes comprehensive unit, integration, adversarial security, and end-to-end integration test suites:

### Run the Security Regression Suite:
```bash
./.venv/bin/pytest tests/adversarial/test_security_regressions.py -v
```

### Run the Full Backend Suite (290 tests):
```bash
./.venv/bin/pytest tests/
```

Includes 11 dedicated unit and boundary tests in `tests/unit/test_openrouter_provider.py` verifying mock and OpenRouter provider contracts, payload serialization, error resilience, rate limit handling, and injection neutralization.

### Run Frontend Component & Interaction Tests (52 tests):
```bash
npm --prefix frontend test -- --watch=false
```

### Build Frontend Production Bundle:
```bash
npm --prefix frontend run build
```

---

## 14. Running Evaluations & Generating Reports

TrustDesk features an automated offline evaluation engine that benchmarks AI triage accuracy, policy grounding, escalation recall, and safety against `data/eval_cases.jsonl`.

### Execute Evaluations via CLI:
```bash
./.venv/bin/python -m trustdesk.eval.runner --eval-file data/eval_cases.jsonl --output-json eval_report.json
```

> [!NOTE]
> **Evaluation Report Export Limitation:**
> The `--output-json` option exports complete benchmark reports for completed evaluation runs (`eval_run.status == "completed"`). If an evaluation run fails or crashes (e.g. database error, unhandled exception, or `eval_run.status == "failed"`), the runner currently prints all available failure details to `stdout`/`stderr` and terminates with a non-zero exit status (`1`) prior to JSON report artifact serialization.

> [!IMPORTANT]
> **Deterministic Mock vs. Live Evaluation:**
> The 18 golden evaluation cases in `data/eval_cases.jsonl` are calibrated against `MockAIProvider` to verify the evaluation runner, metric accounting invariants, and synthetic failure handling (such as `EVAL-016`, which deliberately simulates an AI provider timeout). While the evaluation runner supports whatever provider is configured in `AI_PROVIDER`, running the benchmark with `AI_PROVIDER=openrouter` will make 18 live LLM calls, consuming API credits and subject to external network latency. For standard verification and CI, keep `AI_PROVIDER=mock`.

### Evaluation Accounting Invariant:
The evaluation engine enforces complete input accounting across all 18 cases:
$$N_{\text{total\_lines}} (18) = N_{\text{evaluated}} (16) + N_{\text{inconclusive}} (1) + N_{\text{invalid\_input}} (0) + N_{\text{model\_failure}} (1)$$
- **16 Evaluated:** Scored against ground-truth triage, citations, and actions.
- **1 Inconclusive (`EVAL-017`):** Missing expected labels; benchmarked but excluded from accuracy denominators.
- **0 Invalid:** Golden dataset contains 0 malformed lines.
- **1 Model Failure (`EVAL-016`):** Simulated 15s provider timeout; counted in denominator as failed.

---

## 15. Security & Human Approval Boundaries

TrustDesk enforces strict security boundaries to prevent financial and operational vulnerabilities:
1. **Advisory Semantics:** AI models have zero permissions to mutate application state or trigger refunds directly.
2. **PostgreSQL Concurrency Locking:** `POST /api/v1/actions/{action_id}/approve` acquires a row lock (`SELECT ... FOR UPDATE`), serializing concurrent approval attempts and preventing double-execution.
3. **Persistent Idempotency:** The `action_idempotency` table verifies request hashes (`SHA256(action_id + ":" + json_payload)`). Replaying an identical key returns cached responses; reusing an existing key with tampered parameters returns `409 Conflict`.
4. **Header Spoofing Defense:** Client-supplied identity headers (`X-Agent-ID`) are ignored; `reviewed_by` is stamped strictly from server-verified bearer token identity.
5. **Path Containment:** Evaluation file paths are validated canonically, preventing directory traversal (`../../etc/passwd`) and symlink escapes.
6. **Prompt Injection Defense:** Customer text is contained inside structural XML delimiters (`<untrusted_customer_message>`), and knowledge base policies are framed as passive evidence.

---

## 16. Known Limitations & Post-MVP Enhancements

- **Post-MVP Semantic Retrieval (`U-011`):** The MVP baseline relies on PostgreSQL Full-Text Search. Vector embeddings and Qdrant hybrid retrieval are deferred to post-MVP.
- **Post-MVP Production Identity (`U-012`):** MVP demonstration uses server-validated demo bearer tokens. Enterprise JWT, OIDC, and multi-role RBAC are planned for post-MVP.
- **Retrieval Fine-Tuning (`U-007`):** MVP baseline parameters (1,500 character sub-chunking, Title `'A'` / Body `'B'` weights) are established; continuous empirical threshold tuning remains open for production calibration.
- **No Monetary Processing:** The platform deliberately does not integrate with Stripe, PayPal, or banking APIs; `start_refund_review` is strictly an internal ticket investigation record.
- **Browser Automation:** Frontend tests run via Vitest and jsdom. Full cross-browser end-to-end automation (e.g. Playwright) is preserved as a post-MVP operational task.

---

## License

Internal proprietary software developed for TrustDesk operations. All rights reserved.

