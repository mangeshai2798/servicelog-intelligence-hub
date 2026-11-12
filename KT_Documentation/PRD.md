# Product Requirements Document (PRD)

## 1. Product Overview

- **Product Name:** ServiceLog Intelligence Hub (Universal Enterprise Edition)
- **One-Line Description:** An ultra-generic, offline-first operational log monitoring, root cause analysis (RCA), and autonomous forensic query intelligence platform powered by SQLite FTS5 and a local in-memory small language model (Qwen 2.5 3B).
- **Product Type:** Internal Observability Tool / SRE Diagnostic Platform / Enterprise Log Analyzer
- **Primary Platform:** Web (Desktop-optimized responsive Single-Page Dashboard with a high-performance Python FastAPI backend)

---

## 2. Problem

### What problem are we solving?
Modern software architectures generate gigabytes of distributed, heterogeneous operational log files across distinct microservices and monolithic pipelines. When incidents occur, site reliability engineers (SREs), DevOps teams, and developers must manually grep, filter, and trace log files across disparate servers to correlate failures, isolate transaction lifecycles, and diagnose system crashes. 

Existing centralized APM tools (e.g., Datadog, Splunk) are cost-prohibitive, complex to configure, and require streaming private application data to third-party clouds—violating strict data sovereignty, GDPR, and security policies for offline, sovereign, or air-gapped environments.

### Why does this problem matter?
Mean Time to Resolution (MTTR) during mission-critical outages directly impacts business revenue, SLA breach penalties, and engineer burnout. Engineering teams need immediate, zero-cloud forensic insights, automated root cause extraction, and conversational querying over raw log streams running entirely on local workstation hardware.

### How are users solving this today?
- **Manual Command-Line Tools:** `grep`, `awk`, `sed`, `less`, and custom ad-hoc bash scripts.
- **Heavy Enterprise SIEMs:** Elastic/Kibana, Splunk, Datadog (resource-heavy, high monthly compute/storage cloud costs, network dependencies).
- **Generic Cloud LLMs:** Pasting confidential proprietary log snippets into ChatGPT or Claude, which breaches data security guidelines and fails when log files exceed prompt context limits.

---

## 3. Goals

### Primary Goal
Provide an ultra-generic, plug-and-play log intelligence engine where an operator can drop *any* structured or semi-structured log file from *any* domain into a designated directory (`service_logs/`) or upload via UI, and immediately receive automated statistical telemetry, error signature clustering, break-flow detection, and sub-second natural language forensic query answers without hardcoded schemas or cloud dependencies.

### Secondary Goals
1. **100% Offline Data Sovereignty:** Run local neural inference (`Qwen/Qwen2.5-3B-Instruct` via PyTorch) completely in-memory with zero cloud API keys or external network egress.
2. **Sub-Millisecond Ground Truth Retrieval:** Utilize an embedded SQLite Full-Text Search (FTS5) index for sub-10ms exact-match target line lookups, transaction audits, and surrounding context windows.
3. **Zero-Hardcoding Dynamic Customization:** Ensure all application branding, SLA targets, service discovery, and telemetry parameters are driven dynamically via `.env` configuration and backend APIs.
4. **Transparent Telemetry & Forensic Auditability:** Display live generation statistics (Time to First Token, tokens per second, neural generation latency, total pipeline latency) alongside line-level source code evidence.

---

## 4. Target Users

### User Type 1: Site Reliability Engineers (SREs) & DevOps
- **Description:** Engineers responsible for maintaining application uptime, diagnosing production alerts, and conducting post-incident postmortems.
- **Needs:** Rapid triage, error signature breakdown, timeline correlation, break-flow identification (where a service halted prematurely).
- **Pain Points:** Digging through gigabytes of raw logs across multiple servers during high-pressure incidents; slow search queries in legacy tools.

### User Type 2: Software Developers & QA Engineers
- **Description:** Engineers building and testing features across distributed microservices.
- **Needs:** Tracing individual transaction IDs (e.g., `TX-9021`), viewing preceding and succeeding log lines around a crash, verifying API payload errors.
- **Pain Points:** Hard-to-reproduce bugs; inability to view the chronological execution flow across multiple decoupled services.

### User Type 3: Engineering Managers & Operations Leads
- **Description:** Technical leaders overseeing system health, SLA adherence, and team productivity.
- **Needs:** High-level dashboard overviews, operational SLA compliance percentages, service health distribution, and failure trend charts.
- **Pain Points:** Lack of consolidated visibility into service error frequencies; unreadable raw log files.

---

## 5. User Stories

1. **As an SRE**, I want to drop new service log files into the `service_logs/` directory or upload them via the dashboard so that the system immediately parses, indexes, and surfaces errors without manual regex configuration.
2. **As an incident responder**, I want to ask natural language questions (e.g., *"Why did the payment service fail between 14:10 and 14:25?"*) so that the system extracts the exact error signatures, affected transactions, and root cause in seconds.
3. **As a developer**, I want to query a specific line number (e.g., *"Inspect line 124 in CustomerManagement.log"*) so that I can see the exact target log entry along with its 4 preceding and 4 succeeding lines.
4. **As a QA engineer**, I want to track a transaction ID across all services so that I can audit its chronological execution lifecycle and see exactly which component caused it to abort.
5. **As an IT administrator**, I want all telemetry, branding, and service names to be read from `.env` and database tables so that our team can rebrand and adapt the application for any client environment without altering code.

---

## 6. Core Features

### Feature 1: Universal Generic Log Ingestion & SQLite FTS5 Indexing
- **Purpose:** Automatically scans, parses, deduplicates, and indexes operational log files regardless of format or domain.
- **User Flow:** 
  1. User deposits log files into `service_logs/` or clicks **Upload Log File** on the dashboard.
  2. The parser analyzes timestamp formats, log severity levels (`INFO`, `WARN`, `ERROR`, `FATAL`), service scopes, components, transaction IDs, and error messages.
  3. Structured records are loaded into SQLite `logs` table and synchronized with an `FTS5` full-text search virtual table.
- **Inputs:** Raw `.log` or `.txt` files.
- **Outputs:** Structured database records, indexed FTS virtual tables, and refreshed operational metrics.
- **Acceptance Criteria:**
  - Ingests standard formats (`YYYY-MM-DD HH:MM:SS`, ISO 8601, bracketed timestamps).
  - Automatically identifies service names from file naming patterns or content headers.
  - Sub-second ingestion for files up to 50,000 lines.
- **Edge Cases:** Corrupted lines, missing timestamps, multiline Java stack traces (concatenated to parent log entry).

### Feature 2: Dual-Path AI Query Engine (Local Qwen SLM + Deterministic RAG)
- **Purpose:** Answers complex natural language queries using local in-memory SLM reasoning grounded with deterministic SQLite retrieval.
- **User Flow:**
  1. User types an operational question in the dashboard search bar (with optional service scope filter).
  2. Backend query engine analyzes query intent (line lookup, transaction audit, time window, break flow, general RCA).
  3. Sub-millisecond SQLite queries pull exact ground-truth facts.
  4. Local `Qwen/Qwen2.5-3B-Instruct` model synthesizes the answer with dynamic metrics capture.
  5. If model attempts generic refusal, a deterministic safeguard automatically substitutes structured database evidence.
- **Inputs:** Natural language query string, service filter (optional).
- **Outputs:** Markdown answer, telemetry badges (TTFT, tokens/sec, latency), verifiable forensic log snippets/audit tables.
- **Acceptance Criteria:**
  - Total pipeline latency < 3.5 seconds on CPU.
  - Complete local execution with zero internet access required.
  - Exact file names and line numbers cited in output.
- **Edge Cases:** Hallucination / refusal interception; malformed query strings; empty database.

### Feature 3: Executive Metrics Dashboard & Service Triage
- **Purpose:** Real-time visual telemetry of overall system health, SLA compliance, error distributions, and root cause summaries.
- **User Flow:** Operator opens dashboard; overview cards render Total Records, Successful Records, Success Rate %, and Error Logs. A dynamic service selector filters metrics and charts in real time.
- **Inputs:** Dynamic API call to `/api/overview` and `/api/services`.
- **Outputs:** Stat cards, Chart.js error breakdown visualizations, RCA cause rankings.

### Feature 4: Interactive Log Explorer with Live Pagination & Full-Text Search
- **Purpose:** High-performance tabular explorer allowing engineers to paginate, search, and inspect millions of log rows.
- **User Flow:** User selects service, level, date, or enters a keyword; table instantly updates via server-side pagination.
- **Inputs:** Query params (`service`, `level`, `date`, `search`, `page`, `page_size`).
- **Outputs:** JSON paged records rendered into styled HTML table with severity badges.

---

## 7. Non-Goals

The following are explicitly **NOT** in scope for this version:
- **Cloud SaaS Multi-Tenancy:** The application is architected as a self-hosted single-tenant local/intranet appliance.
- **Live Syslog/TCP Daemon Ingestion:** Log ingestion occurs via file system monitoring and HTTP file uploads, not direct UDP/TCP syslog port listeners.
- **Distributed Agent Mesh:** Running remote collector daemons (like Vector or Fluentbit) across external clusters is handled outside this core app.
- **Write/Mutating Operations on Source Systems:** The engine is purely read-only and analytical; it does not trigger automated restarts or write to target production services.

---

## 8. MVP Scope

### Must Have
- [x] Dynamic `.env` configuration for branding, SLA thresholds, and model parameters.
- [x] Universal multi-pattern log parser supporting timestamps, levels, components, and transaction IDs.
- [x] SQLite database with FTS5 full-text indexing and B-tree indexes.
- [x] Local in-memory Qwen 2.5 3B neural inference engine running via PyTorch.
- [x] Automated refusal interceptor substituting deterministic forensic evidence.
- [x] Dashboard UI with stat cards, dynamic service filter pills, Chart.js visualizations, and responsive query interface.
- [x] File upload endpoint with automatic parsing and database reindexing.

### Nice to Have
- [x] Detailed execution timing terminal banners with TTFT and token throughput.
- [x] Line context window extractor (target line ± 4 lines).
- [x] Transaction lifecycle chronological audit table generator.

### Future
- [ ] Automated anomaly detection via moving average z-score on log frequency spikes.
- [ ] Export forensic audit report to PDF / Markdown artifact.
- [ ] Webhook alerts for critical break flows to Slack / Microsoft Teams.

---

## 9. Success Metrics

### Primary Metrics
- **Pipeline Query Latency:** Under 3.5 seconds for complete end-to-end AI query response on consumer CPU.
- **FTS5 Forensic Retrieval Speed:** Under 15 milliseconds for targeted SQLite queries over 100,000 log records.
- **Zero Cloud Leakage:** 100% of queries and logs processed locally with zero outbound network calls.

### Secondary Metrics
- **UI First Contentful Paint:** Dashboard loads in under 400ms.
- **Parser Robustness:** > 99.8% line parse success rate on arbitrary service log formats.

---

## 10. Constraints

- **Technical Constraints:** Must run on standard developer laptops (16GB RAM, quad-core CPU, Windows/macOS/Linux) without requiring dedicated Nvidia GPUs.
- **Memory Footprint:** Qwen 2.5 3B model occupies ~5.5 to 6.5 GB of system RAM, operating smoothly within standard 16GB developer laptops.
- **Frameworks:** Python 3.10+, FastAPI, PyTorch, Hugging Face Transformers, SQLite3, HTML5/Tailwind/Vanilla JS.
- **Design Constraints:** Zero external CDN dependencies in production; all vendor libraries (`chart.umd.min.js`, `lucide.min.js`, `marked.min.js`, `tailwindcss.js`) bundled locally.

---

## 11. Assumptions

1. Log files deposited in `service_logs/` contain standard text UTF-8 or ASCII encoding.
2. The user has Python 3.10+ installed and sufficient disk space (~2 GB for PyTorch + Qwen 2.5 weights).
3. Operators access the dashboard via standard modern browsers (Chrome, Edge, Firefox, Safari).

---

## 12. Open Questions

1. *Should we add automatic log rotation or retention policies if `service_logs/` grows beyond 10 GB?* (Current resolution: File upload and disk monitoring is left to host OS, but SQLite indexing remains lightweight).
2. *Would optional GPU acceleration (CUDA / Apple Silicon MPS) be enabled automatically if detected?* (Current resolution: Defaults to CPU for universal compatibility; auto-detects CUDA if available).

---

## 13. Definition of Done

A release or feature is complete when:
- [x] Code adheres to the zero-hardcoding rule (reads branding and thresholds dynamically).
- [x] All unit, integration, and syntax checks pass (`python -m py_compile`).
- [x] Critical user flows (dashboard load, file upload, search filtering, AI natural language query) function reliably.
- [x] Type hints and Pydantic schemas validate all incoming and outgoing payloads.
- [x] Documentation in `KT_Documentation/` matches code behavior without drift.

