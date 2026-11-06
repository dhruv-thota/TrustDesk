# Phase 7 — Testing & Evaluation Specification: Background Jobs, Execution Traces, and Evaluation

**Document Version:** 1.1.0  
**Phase:** Phase 7 — Background Jobs, Execution Traces, and Evaluation  
**Status:** Verified Post-Implementation Specification  
**Role:** Senior Software Architect, Test Architect & QA Engineer  
**Authoritative References:**  
- [docs/problem_statement.md](file:///Users/dhruv/Desktop/TrustDesk/docs/problem_statement.md) (§3.7, §3.8, §4, §7)  
- [docs/architecture.md](file:///Users/dhruv/Desktop/TrustDesk/docs/architecture.md) (§2.1, §3.4, §3.5, §4.3 Tables 8 & 9, §10, §11)  
- [docs/implementation_plan.md](file:///Users/dhruv/Desktop/TrustDesk/docs/implementation_plan.md) (§2, §3 Phase 7)  
- [docs/conventions.md](file:///Users/dhruv/Desktop/TrustDesk/docs/conventions.md) (§1.2, §2, §3, §6, §7)  
- [docs/phase7_edgecases.md](file:///Users/dhruv/Desktop/TrustDesk/docs/phase7_edgecases.md) (Verified Edge Cases)  
- [docs/unresolved.md](file:///Users/dhruv/Desktop/TrustDesk/docs/unresolved.md) (`U-004`, `U-007`, `U-009`)

---

## A. Phase Evaluation Objective

The objective of Phase 7 evaluation is to objectively verify that:
1. Redis 7 and the Python RQ worker daemon start cleanly, coordinate tasks via queues and registries, and execute background jobs without blocking interactive HTTP API threads.
2. PostgreSQL database migration `005` creates `eval_runs` and `eval_results` with partial unique index `idx_single_active_eval_run` and composite line constraint `uq_eval_results_run_line`.
3. Simultaneous calls to `POST /api/v1/evaluations/run` are serialized by the database engine, returning HTTP 409 Conflict when an active run exists.
4. Preassigned RQ job IDs guarantee enqueue consistency, and stale queued runs from crashed API processes are safely reconciled.
5. Worker crashes mid-execution are safely reconciled without prematurely failing running jobs or scheduled retries.
6. The evaluation runner parses `data/eval_cases.jsonl`, rejects duplicate valid `case_id`s, executes self-contained fixtures, and enforces the complete input accounting invariant ($N_{\text{total\_lines}} = N_{\text{evaluated}} + N_{\text{inconclusive}} + N_{\text{invalid\_input}} + N_{\text{model\_failure}}$).
7. Evaluation metrics calculate accurately according to the refined contract, reporting separate Triage Escalation Precision/Recall and Draft Escalation Precision/Recall, with zero-denominator queries returning `null` / `"N/A"`.
8. Execution traces and worker telemetry are strictly sanitized, excluding raw prompt text, customer PII, and API secrets.
9. All 263 backend tests across 26 test suites and 52 frontend tests across 8 test suites pass with zero regressions.

---

## B. Evaluation Scope

- **Components Under Test:**
  - `trustdesk/core/redis.py` (Redis client factory and connection pooling)
  - `trustdesk/core/config.py` (`redis_url` configuration settings)
  - `trustdesk/worker/worker.py` (RQ worker daemon entrypoint and safe reconciliation sweep)
  - `trustdesk/worker/tasks.py` (Background evaluation task definitions)
  - `trustdesk/worker/service.py` (Enqueue evaluation run service)
  - `trustdesk/worker/reconciliation.py` (Safe bounded reconciliation routine)
  - `trustdesk/eval/runner.py` (CLI and background evaluation runner engine)
  - `trustdesk/eval/loader.py` (JSONL dataset loader and containment validator)
  - `trustdesk/eval/metrics.py` (Deterministic metric evaluation engine)
  - `trustdesk/schemas/eval.py` (Pydantic schemas for JSONL dataset and metric reporting)
  - `trustdesk/api/v1/evaluations.py` (`POST /run`, `GET /`, `GET /{run_id}`)
  - `trustdesk/api/v1/jobs.py` (`GET /jobs/{job_id}`)
  - `frontend/src/components/EvaluationDashboard.jsx` (Evaluation summary and run inspection dashboard)
  - `alembic/versions/005_create_phase7_eval_tables.py` (Database migration)
- **Security & Safety Boundaries Under Test:**
  - Strict absence of tool execution privileges during evaluation runs.
  - Verification that adversarial documents and customer messages cannot trigger autonomous actions.
  - Zero leakage of customer PII, credit card data, or API keys into `sanitized_telemetry`.
  - Zero cross-talk or race conditions during concurrent enqueue requests.
  - Dataset path containment and symlink escape prevention.
- **Explicit Caveats & Limitations:**
  - *Offline Determinism vs Production Safety:* Automated tests use `MockAIProvider` to verify guardrail plumbing, structural XML delimiters, and deterministic parsing against known adversarial patterns. This verifies system guardrail architecture, not open-world LLM prompt-injection immunity under live unconstrained models.
  - *Component Testing vs Real Browser E2E:* Frontend verification consists of 52 automated tests in Vitest and React Testing Library using jsdom. Full cross-browser automation (e.g. Playwright) is deferred to post-MVP operations.
  - *Explicit Exclusions:* No distributed Celery or Temporal orchestrators; no automatic fine-tuning loops; no Qdrant semantic search (deferred to post-MVP `U-011`); no production JWT / RBAC identity platforms (deferred to post-MVP `U-012`).

---

## C. Test Environment and Execution Strategy

### 1. Test Tooling Stack
- **Unit and Integration Testing:** pytest against PostgreSQL 15 on port 5433 and Redis 7 on port 6379.
- **Mock AI Testing:** Offline deterministic evaluation using `MockAIProvider`.
- **Frontend Verification:** Vitest + React Testing Library for `EvaluationDashboard` component.
- **Regression Protection:** Full test suite execution across backend (`.venv/bin/pytest tests/`) and frontend (`npm --prefix frontend test`).

### 2. Test Suite Organization
- `tests/unit/test_redis_config.py`: Redis client configuration and connection verification.
- `tests/unit/test_eval_schemas.py`: Dataset line schema parsing, pre-flight fatal aborts, path traversal security, and duplicate `case_id` rejection.
- `tests/unit/test_eval_metrics.py`: Mathematical verification of joint accuracy, separate triage/draft escalation, and zero-denominator nulls.
- `tests/integration/test_worker.py`: Background job enqueue, concurrency conflicts, retry idempotency, and bounded worker reconciliation.
- `tests/integration/test_evaluation_runner.py`: End-to-end evaluation suite execution and input accounting.
- `tests/integration/test_evaluation_api.py`: REST routes for job submission, status polling, and run summaries.
- `frontend/tests/EvaluationDashboard.test.jsx`: Frontend tab rendering, job polling, metric cards, and case table display.

---

## D. Detailed Evaluation Gates

All 18 evaluation gates have been executed and verified. Every gate has achieved **PASS / VERIFIED** status.

---

### EG-P7-01: Redis & Background Worker Infrastructure Containerization
- **Gate ID:** `EG-P7-01`
- **Objective:** Verify that Redis 7 is containerized via Docker Compose, accepts connections, and the RQ worker daemon initializes cleanly.
- **Test Type:** Infrastructure & Process Verification
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/unit/test_redis_config.py
  ```
- **Verified Evidence:** Redis responds to `PING` with `PONG`; connection pooling in `trustdesk/core/redis.py` functions correctly; worker entrypoint `trustdesk.worker.worker` imports cleanly and parses CLI arguments.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-02: Evaluation Run Database Migrations
- **Gate ID:** `EG-P7-02`
- **Objective:** Verify that Alembic migration `005_create_phase7_eval_tables` applies cleanly from `head`, creating `eval_runs` and `eval_results` with constraints.
- **Test Type:** Database Migration Verification
- **Verification Command:**
  ```bash
  .venv/bin/alembic upgrade head
  ```
- **Verified Evidence:** Alembic migration `005` applied cleanly to database head. Verified tables `eval_runs` and `eval_results` exist with partial unique index `idx_single_active_eval_run` (`((1)) WHERE status IN ('queued', 'running')`) and composite line constraint `uq_eval_results_run_line` (`(run_id, source_line_number)`).
- **Status:** **PASS / VERIFIED**

---

### EG-P7-03: Dataset JSONL Schema Validation & Duplicate Case ID Rejection
- **Gate ID:** `EG-P7-03`
- **Objective:** Verify that evaluation dataset lines parse into strongly-typed Pydantic schemas, and duplicate valid `case_id` values are rejected during pre-flight validation.
- **Test Type:** Automated Unit Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/unit/test_eval_schemas.py -k "test_all_18_fixture_schemas_valid or test_duplicate_case_id_rejection"
  ```
- **Verified Evidence:** All 18 candidate cases parse into `EvaluationCaseSchema` without errors; synthetic datasets containing duplicate valid `case_id` values raise `DatasetValidationError` and abort before execution.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-04: Per-Run Detailed Results API
- **Gate ID:** `EG-P7-04`
- **Objective:** Verify that `GET /api/v1/evaluations/{run_id}` retrieves detailed aggregate metrics, per-case breakdown, and inconclusive counts for authenticated agents.
- **Test Type:** Automated API Integration Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_evaluation_api.py -k test_evaluation_detail_retrieval
  ```
- **Verified Evidence:** Endpoint requires demo bearer token; returns HTTP 200 with `EvalRunDetailSchema` containing `metrics_summary`, `dataset_health`, and per-case disposition rows ordered by `source_line_number ASC`. Returns HTTP 404 for non-existent UUIDs.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-05: Asynchronous Job Enqueue API
- **Gate ID:** `EG-P7-05`
- **Objective:** Verify that `POST /api/v1/evaluations/run` enqueues an evaluation job to Redis, creates an authoritative `eval_runs` record, and returns HTTP 202 Accepted.
- **Test Type:** Automated API Integration Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_evaluation_api.py -k test_authenticated_evaluation_submission
  ```
- **Verified Evidence:** API inserts `eval_runs` with `status = 'queued'`, enqueues RQ job with matching preassigned `job_id`, and returns HTTP 202 Accepted with `{"job_id": "...", "run_id": "...", "status": "queued"}`.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-06: Job Status Polling & Tracking API
- **Gate ID:** `EG-P7-06`
- **Objective:** Verify that `GET /api/v1/jobs/{job_id}` returns transient execution status and falls back to durable PostgreSQL records if Redis metadata has expired.
- **Test Type:** Automated API Integration Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_evaluation_api.py -k "test_job_polling_queued_status or test_job_polling_running_status or test_job_polling_completed_status"
  ```
- **Verified Evidence:** Endpoint returns HTTP 200 with `JobStatusSchema(job_id, status, run_id, error)`. Expired Redis tasks resolve durable status from `eval_runs` without returning 404.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-07: Historical Evaluation Runs Listing API
- **Gate ID:** `EG-P7-07`
- **Objective:** Verify that `GET /api/v1/evaluations` returns a chronological list of past evaluation runs with aggregate metrics summaries.
- **Test Type:** Automated API Integration Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_evaluation_api.py -k test_evaluation_history_ordering_and_pagination
  ```
- **Verified Evidence:** Endpoint returns HTTP 200 with `list[EvalRunSummarySchema]` ordered by `started_at DESC`, displaying case counts, run statuses, and execution durations.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-08: Dashboard Evaluation Summary View
- **Gate ID:** `EG-P7-08`
- **Objective:** Verify that the support-agent dashboard provides an evaluation tab rendering historical runs, metric cards, and inconclusive breakdowns.
- **Test Type:** Frontend Component Test
- **Verification Command:**
  ```bash
  npm --prefix frontend test -- -t "EvaluationDashboard"
  ```
- **Verified Evidence:** Vitest executes 18 tests in `EvaluationDashboard.test.jsx`. React component mounts cleanly, fetches runs via `client.js`, displays metric summary cards (joint triage accuracy, citation coverage, safety blocking), and renders empty/error states without unhandled exceptions.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-09: Concurrency Control via Partial Unique Index
- **Gate ID:** `EG-P7-09`
- **Objective:** Verify that simultaneous evaluation run submissions are serialized by PostgreSQL partial unique index `idx_single_active_eval_run`, returning HTTP 409 Conflict.
- **Test Type:** Automated Concurrency Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_evaluation_api.py -k test_concurrent_submission_http_409
  ```
- **Verified Evidence:** Second concurrent request triggers `UniqueViolation` intercepted by FastAPI; returns HTTP 409 Conflict with code `EVAL_ALREADY_RUNNING`; the active run proceeds unaffected.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-10: Enqueue Failure & Orphan Recovery Protocol
- **Gate ID:** `EG-P7-10`
- **Objective:** Verify that Redis outages during enqueue mark the database run `failed`, release the unique index slot, and return HTTP 503; stale queued orphans from crashed APIs are repaired on sweep.
- **Test Type:** Automated Integration Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_worker.py -k "test_redis_unavailable_during_enqueue or test_stale_queued_reconciliation"
  ```
- **Verified Evidence:** Redis disconnect updates run to `failed` and returns HTTP 503; stale queued runs older than 60s without Redis jobs transition to `failed` (`enqueue_orphaned`) on reconciliation sweep.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-11: Safe Worker Interruption Reconciliation
- **Gate ID:** `EG-P7-11`
- **Objective:** Verify that the 9-state reconciliation routine detects killed workers without prematurely failing running jobs, scheduled retries, or jobs undergoing transient Redis disconnects.
- **Test Type:** Automated Integration Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_worker.py -k "test_worker_interruption_reconciliation or test_temporary_redis_disconnection_reconciliation"
  ```
- **Verified Evidence:** Orphaned runs with dead heartbeats transition to `failed` (`worker_interrupted`); runs with scheduled retries in `DeferredJobRegistry` remain intact; sweeps during transient Redis outages abort safely without database mutation.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-12: Case-Level Retry Idempotency & Source Line Preservation
- **Gate ID:** `EG-P7-12`
- **Objective:** Verify that retried evaluation jobs upsert records using composite constraint `UNIQUE (run_id, source_line_number)`, preserving line identity without row duplication.
- **Test Type:** Automated Integration Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_evaluation_runner.py -k test_idempotent_line_upsert
  ```
- **Verified Evidence:** Runner retrying an existing run updates existing records via PostgreSQL `ON CONFLICT (run_id, source_line_number) DO UPDATE`; total persisted rows in `eval_results` exactly matches source line count (18 rows).
- **Status:** **PASS / VERIFIED**

---

### EG-P7-13: Metric Calculation Correctness (Separate Escalation Signals)
- **Gate ID:** `EG-P7-13`
- **Objective:** Verify that triage accuracy, citation coverage, unsafe blocking, and separate Triage and Draft Escalation Precision/Recall calculate exactly per formula, returning `null` on zero denominators.
- **Test Type:** Automated Unit Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/unit/test_eval_metrics.py
  ```
- **Verified Evidence:** All 17 unit tests in `test_eval_metrics.py` pass; formulas compute exact quotients; model timeouts score as 0 in accuracy denominator; inconclusive cases are excluded from denominators; zero-denominator metrics return `null` / `"N/A"`.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-14: Adversarial Safety & Injection Blocking Verification
- **Gate ID:** `EG-P7-14`
- **Objective:** Verify that adversarial cases (`EVAL-014` prompt injection and `EVAL-015` adversarial document retrieval) block unauthorized action execution and prevent prompt/secret disclosures.
- **Test Type:** Automated Security Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_evaluation_runner.py -k "test_customer_prompt_injection or test_adversarial_kb_injection"
  ```
- **Verified Evidence:** Runner confirms zero operational actions executed without human approval; master secret `SECRET-KEY-ALPHA-9999` is not disclosed; `safety_passed = true` recorded for both cases.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-15: Execution Trace Sanitization & Telemetry Safety Invariant
- **Gate ID:** `EG-P7-15`
- **Objective:** Verify that background worker traces written to `execution_traces` and `eval_results.execution_details` contain zero raw prompts, customer PII, or API secrets.
- **Test Type:** Automated Unit Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_worker.py -k test_recursive_sanitization
  ```
- **Verified Evidence:** Stored telemetry JSON objects contain only operational fields (`latency_ms`, `tokens`, `model`); regex scans confirm zero matches for customer emails, credit cards, or API keys (`TRUSTDESK_DEMO_TOKEN`, `GEMINI_API_KEY`).
- **Status:** **PASS / VERIFIED**

---

### EG-P7-16: Complete Evaluation Input Accounting Invariant
- **Gate ID:** `EG-P7-16`
- **Objective:** Verify that an evaluation run transitions to `completed` only when every input line has an explicit persisted disposition satisfying $N_{\text{total\_lines}} = N_{\text{evaluated}} + N_{\text{inconclusive}} + N_{\text{invalid\_input}} + N_{\text{model\_failure}}$.
- **Test Type:** Automated Integration Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/integration/test_evaluation_runner.py -k test_complete_input_accounting
  ```
- **Verified Evidence:** Standard 18-case dataset accounting verified:
  - Total input lines: 18
  - Valid evaluatable cases: 16 (includes 15 standard + 1 model failure `EVAL-016`)
  - Inconclusive cases: 1 (`EVAL-017`, missing ground truth labels, excluded from accuracy denominator)
  - Invalid input: 0
  - Model failures: 1 (`EVAL-016`, simulated timeout, included in accuracy denominator with score 0)
  - Invariant verified: $18 = 16 + 1 + 0 + 1$.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-17: Backend Zero-Regression Gate
- **Gate ID:** `EG-P7-17`
- **Objective:** Verify that all 263 existing backend unit, integration, concurrency, and security tests pass with zero failures.
- **Test Type:** Full Regression Test
- **Verification Command:**
  ```bash
  .venv/bin/pytest tests/
  ```
- **Verified Evidence:** Pytest reports 263 passed tests, 11 warnings across 26 test suites in 19.57 seconds with zero failures and zero regressions.
- **Status:** **PASS / VERIFIED**

---

### EG-P7-18: Frontend Zero-Regression Gate
- **Gate ID:** `EG-P7-18`
- **Objective:** Verify that all 52 existing frontend component and interaction tests pass with zero failures.
- **Test Type:** Full Regression Test
- **Verification Command:**
  ```bash
  npm --prefix frontend test -- --watch=false
  ```
- **Verified Evidence:** Vitest reports 52 passed tests across 8 test suites in 1.93 seconds with zero failures. Production build (`npm --prefix frontend run build`) completes cleanly in 929ms.
- **Status:** **PASS / VERIFIED**


