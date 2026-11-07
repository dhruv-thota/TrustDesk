# TrustDesk — AI-Assisted Customer Support Operations Platform

**Document Version:** 1.0.0  
**Target Environment:** Docker Compose (Complete 5-Service Stack) | Local Python Virtualenv & Node.js  

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

- **Container Orchestration:** Docker Compose v2 (5 isolated services: `postgres`, `redis`, `backend`, `worker`, `frontend`).
- **Backend Runtime:** Python 3.12 (PEP 8, strict type hints, Pydantic v2, SQLAlchemy 2.0).
- **Web Framework:** FastAPI (RESTful API, asynchronous route handling, standardized error envelopes).
- **Authoritative Database:** PostgreSQL 15 (SQLAlchemy 2.0 ORM, Alembic migrations, native Full-Text Search with `tsvector`, English dictionary, and GIN index).
- **Asynchronous Task Queue:** Redis 7 + Python RQ (background worker processing long-running evaluation benchmarks).
- **Frontend Dashboard:** React 18 + Vite + Tailwind CSS (responsive support-agent workspace served via Nginx with API reverse proxy).
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
│   ├── Dockerfile        # Multi-stage production build (Node 20 builder -> Nginx 1.27 runner)
│   └── nginx.conf        # Production reverse proxy (SPA routing + /api/ upstream proxy)
├── alembic/              # Database schema migrations (001 through 005)
├── data/                 # Operational source datasets & golden eval cases
├── tests/                # Automated pytest suites (unit, integration, adversarial, e2e)
├── Dockerfile            # Shared Python 3.12-slim container for backend and worker
├── entrypoint.sh         # Container entrypoint (migration + data ingestion + uvicorn)
├── docker-compose.yml    # Complete 5-service container orchestration
└── pyproject.toml        # Python project dependencies & build configuration
```

---

## 5. Quick Start — Docker Compose (Recommended)

Run the entire TrustDesk application stack with a single command. No local Python or Node.js environment is required on the host.

### 5.1 Prerequisites
- **Docker & Docker Compose** (Docker v20.10+ / Compose v2.0+)
- **Git**

### 5.2 Launch the Stack

1. **Clone the repository:**
   ```bash
   git clone https://github.com/dhruv-ahuja/TrustDesk.git
   cd TrustDesk
   ```

2. **Create your environment configuration:**
   ```bash
   cp .env.example .env
   ```
   *(The default `.env` is pre-configured with deterministic `AI_PROVIDER=mock` and requires zero external credentials).*

3. **Start all 5 services:**
   ```bash
   docker compose up --build -d
   ```

4. **Verify container health:**
   ```bash
   docker compose ps
   ```
   All five containers (`trustdesk-postgres`, `trustdesk-redis`, `trustdesk-backend`, `trustdesk-worker`, and `trustdesk-frontend`) will report status `healthy` (or `running`).

> [!NOTE]
> **Automated Database Seeding:** On startup, the backend container entrypoint automatically executes `alembic upgrade head` and seeds all 4 demo tickets, customers, orders, and knowledge base documents via `python -m trustdesk.cli ingest --data-dir ./data`. The RQ background worker starts automatically once the backend is healthy.

### 5.3 Service Access URLs

| Component | URL | Description |
| :--- | :--- | :--- |
| **Support Agent Dashboard** | [http://localhost:5173](http://localhost:5173) | React 18 web application served via Nginx |
| **Interactive API Documentation** | [http://localhost:8000/docs](http://localhost:8000/docs) | FastAPI interactive Swagger UI |
| **Alternative API Specs** | [http://localhost:8000/redoc](http://localhost:8000/redoc) | FastAPI ReDoc interface |
| **API Health Endpoint** | [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health) | Database and Redis connectivity check |
| **PostgreSQL Host Port** | `localhost:5433` | PostgreSQL 15 database instance |
| **Redis Host Port** | `localhost:6379` | Redis 7 asynchronous broker |

---

### 5.4 Recommended 5-Step Evaluation / Demo Walkthrough

1. **Open the Dashboard:** Navigate to [http://localhost:5173](http://localhost:5173) in your browser.
2. **Authenticate:** Click **Set Demo Token** in the top navigation bar. This stores `demo_secret_token_123` in browser `sessionStorage` and immediately loads the 4 pre-seeded demo tickets in the queue.
3. **Select a Ticket:** Click ticket **`TIK-001`** (Customer damaged blender refund inquiry). Review the loaded customer profile, order history, and delivery timestamp.
4. **Run AI Triage & Draft:**
   - Click **Run Triage**: View the automated categorization (`refund`), high priority, and reason trace.
   - Click **Generate Draft**: Review the policy-grounded draft response with interactive citation chips linking directly to the cited Return & Refund policy sections.
5. **Human Approval Gate:**
   - Inspect the proposed action card (`start_refund_review`).
   - Click **Approve** (or **Reject**). Notice that the approval executes with an automated server-verified idempotency key and row-level database lock, recording an immutable trace in `execution_traces`.
6. **(Optional) Run Asynchronous Evaluations:**
   - Navigate to the **Evaluations** tab.
   - Click **Run Benchmark** to trigger the 18-case offline evaluation suite.
   - Watch live progress polled from the backend as the background RQ worker processes all test cases asynchronously without blocking the UI.

---

### 5.5 Operational & Lifecycle Commands

- **Stream service logs:**
  ```bash
  docker compose logs -f
  # Or stream a specific service:
  docker compose logs -f backend
  ```

- **Stop the stack (Preserves database data):**
  ```bash
  docker compose stop
  # OR
  docker compose down
  ```

- **Start the stack back up:**
  ```bash
  docker compose up -d
  ```

- **Rebuild after making code edits:**
  ```bash
  docker compose up --build -d
  ```

> [!CAUTION]
> **Data Persistence Warning:**
> PostgreSQL data is stored in the persistent Docker named volume `postgres_data`. Normal `docker compose down` or `docker compose stop` will **never** wipe your database.
> Never run `docker compose down -v` unless you explicitly intend to delete the persistent volume and erase all database records.

---

### 5.6 Submission Verification

Evaluators can verify that all five Docker services are actively running and healthy in a single step:

```bash
docker compose ps
```

Expected output confirms all services are healthy and ready to receive traffic:
- `trustdesk-backend`: `Up (healthy)` on `http://localhost:8000` (FastAPI REST service)
- `trustdesk-frontend`: `Up (healthy)` on `http://localhost:5173` (React 18 SPA via Nginx)
- `trustdesk-postgres`: `Up (healthy)` on `localhost:5433` (PostgreSQL 15 storage)
- `trustdesk-redis`: `Up (healthy)` on `localhost:6379` (Redis 7 task queue)
- `trustdesk-worker`: `Up` (Python RQ background evaluation worker)

---

## 6. Alternative Setup — Local Development (Manual Virtualenv & Node.js)

If you prefer to run the FastAPI backend, RQ worker, or React frontend directly on your host machine without Docker for local development or debugging:

### 6.1 Host Prerequisites
- **Python 3.11+** (Python 3.12.6 recommended)
- **Node.js 18+ & npm**
- **Docker & Docker Compose** (for PostgreSQL and Redis)

### 6.2 Host Environment Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Start PostgreSQL 15 and Redis 7 via Docker Compose:
   ```bash
   docker compose up -d postgres redis
   ```
   PostgreSQL is available on host port `5433`, and Redis is on port `6379`.

3. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

4. Apply database migrations:
   ```bash
   alembic upgrade head
   ```

5. Ingest baseline datasets into PostgreSQL:
   ```bash
   python -m trustdesk.cli ingest --data-dir ./data
   ```

### 6.3 Running Services Locally

- **Start the FastAPI Backend:**
  ```bash
  uvicorn trustdesk.main:app --host 0.0.0.0 --port 8000 --reload
  ```

- **Start the Background Worker (Terminal 2):**
  ```bash
  source .venv/bin/activate
  python -m trustdesk.worker.worker
  ```

- **Start the React Frontend (Terminal 3):**
  ```bash
  npm --prefix frontend install
  npm --prefix frontend run dev
  ```
  The frontend dev server runs at `http://localhost:5173`.

### 6.4 Switching Between Mock and OpenRouter AI Modes

TrustDesk isolates model inference behind the `AIProviderAdapter` protocol:

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
   - **Advisory-Only Safety Boundary:** The model cannot trigger operational actions. Draft responses undergo deterministic 3-level guardrail verification.
   - **Graceful Triage Fallback:** If the external API is unreachable or times out, the backend gracefully catches provider errors and marks triage for manual human escalation without crashing the service.

---

## 7. Running Automated Tests

TrustDesk includes comprehensive unit, integration, adversarial security, and end-to-end integration test suites:

> [!NOTE]
> **Database Test Isolation:** All backend tests (`pytest`) run strictly against an isolated test database `DATABASE_URL_TEST` (`trustdesk_test`), shielding development records from test truncations.

### Run Security Regression Suite:
```bash
./.venv/bin/pytest tests/adversarial/test_security_regressions.py -v
```

### Run Full Backend Suite (290 tests):
```bash
./.venv/bin/pytest tests/
```
*Includes 11 dedicated unit and boundary tests in `tests/unit/test_openrouter_provider.py` verifying mock and OpenRouter provider contracts, payload serialization, error resilience, rate limit handling, and injection neutralization.*

### Run Frontend Component & Interaction Tests (52 tests):
```bash
npm --prefix frontend test -- --watch=false
```

### Build Frontend Production Bundle:
```bash
npm --prefix frontend run build
```

---

## 8. Running Offline Evaluations & Generating Reports

TrustDesk features an automated offline evaluation engine that benchmarks AI triage accuracy, policy grounding, escalation recall, and safety against `data/eval_cases.jsonl`.

### Execute Evaluations via CLI:
```bash
./.venv/bin/python -m trustdesk.eval.runner --eval-file data/eval_cases.jsonl --output-json eval_report.json
```

> [!NOTE]
> **Evaluation Report Export Limitation:**
> The `--output-json` option exports complete benchmark reports for completed evaluation runs (`eval_run.status == "completed"`). If an evaluation run fails or crashes (e.g. database error, unhandled exception, or `eval_run.status == "failed"`), the runner prints all failure details to `stdout`/`stderr` and terminates with a non-zero exit status (`1`) prior to JSON report artifact serialization.

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

## 9. Security & Human Approval Boundaries

TrustDesk enforces strict security boundaries to prevent financial and operational vulnerabilities:
1. **Advisory Semantics:** AI models have zero permissions to mutate application state or trigger refunds directly.
2. **PostgreSQL Concurrency Locking:** `POST /api/v1/actions/{action_id}/approve` acquires a row lock (`SELECT ... FOR UPDATE`), serializing concurrent approval attempts and preventing double-execution.
3. **Persistent Idempotency:** The `action_idempotency` table verifies request hashes (`SHA256(action_id + ":" + json_payload)`). Replaying an identical key returns cached responses; reusing an existing key with tampered parameters returns `409 Conflict`.
4. **Header Spoofing Defense:** Client-supplied identity headers (`X-Agent-ID`) are ignored; `reviewed_by` is stamped strictly from server-verified bearer token identity.
5. **Path Containment:** Evaluation file paths are validated canonically, preventing directory traversal (`../../etc/passwd`) and symlink escapes.
6. **Prompt Injection Defense:** Customer text is contained inside structural XML delimiters (`<untrusted_customer_message>`), and knowledge base policies are framed as passive evidence.
7. **Client Token Isolation:** In accordance with standard browser security practices, authentication bearer tokens are stored strictly in `sessionStorage`, ensuring tokens are automatically expunged when tabs or browser windows are closed.

---

## 10. Known Limitations & Post-MVP Enhancements

- **Post-MVP Semantic Retrieval (`U-011`):** The MVP baseline relies on PostgreSQL Full-Text Search. Vector embeddings and Qdrant hybrid retrieval are deferred to post-MVP.
- **Post-MVP Production Identity (`U-012`):** MVP demonstration uses server-validated demo bearer tokens. Enterprise JWT, OIDC, and multi-role RBAC are planned for post-MVP.
- **Retrieval Fine-Tuning (`U-007`):** MVP baseline parameters (1,500 character sub-chunking, Title `'A'` / Body `'B'` weights) are established; continuous empirical threshold tuning remains open for production calibration.
- **No Monetary Processing:** The platform deliberately does not integrate with Stripe, PayPal, or banking APIs; `start_refund_review` is strictly an internal ticket investigation record.
- **Browser Automation:** Frontend tests run via Vitest and jsdom. Full cross-browser end-to-end automation (e.g. Playwright) is preserved as a post-MVP operational task.

---

## License

Internal proprietary software developed for TrustDesk operations. All rights reserved.
