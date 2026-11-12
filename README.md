# 🚀 ServiceLog Intelligence Hub

An enterprise-grade, ultra-generic **Service Log Monitoring, Automated Root Cause Analysis (RCA), and Autonomous Diagnostic Q&A Platform**.

Designed for high-volume distributed microservices, financial settlement pipelines, and mission-critical enterprise systems. Powered by a high-throughput **FastAPI backend**, an indexed **SQLite WAL & FTS5 full-text engine**, a **100% offline Local In-Memory Qwen 2.5 3B Small Language Model (SLM)**, and a modern **Executive UI Dashboard** with real-time telemetry, visual charts, and sub-millisecond forensic search.

---

## 🌟 Key Highlights & System Capabilities

* **100% Offline & Privacy-Compliant**: Powered by an in-memory `Qwen/Qwen2.5-3B-Instruct` model running locally in PyTorch via CPU tensors. Zero external API calls, zero cloud dependencies, and zero data leakage.
* **Ultra-Generic Architecture**: No hardcoded service names, file names, or UI text. Everything is driven dynamically from the log content, database metadata, and the centralized [`.env`](file:///.env) configuration file.
* **Multi-Gigabyte Scalability (O(1) RAM Ingestion)**: Streams log files line-by-line using Python generator iterators without loading entire files into memory. Handles gigabytes of logs in constant memory (< 35 MB RAM).
* **Forensic SQLite & FTS5 Search**: Sub-millisecond lookups for line-by-line inspection (with surrounding 8-line context windows), end-to-end transaction lifecycle tracing, time intervals, and token-level BM25 full-text search.
* **High-Precision Telemetry & Response Timing**: Tracks and displays exact Time to First Token (TTFT), neural generation duration, token generation speed (tokens/sec), and end-to-end latency directly on the UI and in the terminal.
* **Smart Startup Lifecycle**: The single-command launcher automatically polls backend health and only opens the browser when log scanning, SQLite indexing, and local model warmup are 100% completed.

---

## 📌 Executive Summary of Current Ingested Logs

The system dynamically discovers, indexes, and correlates all `.log` files placed in the configured logs directory:

| Service Name | Source File | Records Processed | Successful | Failed / Errors | Status | Operational Findings |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DorchesterPaymentExport** | `log-2026-09-22_PaymentExport.log` | **200** | **199** | **1** | 🔴 **CRITICAL BREAK** | Export succeeded for *Treasurer Bill* (199 payments). **Fatal break** occurred on *Window-Add* due to missing transaction `C49527762P89519320`. |
| **ACHStatusUpdate** | `log-2026-10-13_ACHStatus.log` | **1,296** | **1,272** | **24** | 🟢 **HEALTHY** | Processed across 3 scheduled batches (00:30, 05:30, 09:30). 1,272 approved; 24 bank returns (`R01` Insufficient Funds, `R24` Duplicate). |
| **DorchesterDailyPaymentReport** | `log-2026-10-13_DailyPaymentFile.log` | **1** | **1** | **0** | 🟢 **OPTIMAL** | Daily payment report generated and exported with 1 CC payment. Email notifications and FTP upload completed. |
| **IntelliPaySettledPayments** | `log-2026-10-13_Settledment.log` | **866** | **838** | **28** | 🟡 **WARNING** | 2,630 gateway responses handled. 838 added to DB. 56 error logs (`System.FormatException` in `DecodeBase64` on `'IVRCC'` comments). |
| **SYSTEM TOTAL** | **4 Log Files** | **2,363** | **2,310** | **53** | **97.76% Success** | **57 explicit ERROR log lines** across 35,860 indexed entries. |

---

## 🛠️ Architecture & Project Structure

```
Logs_Monitoring_Project/
├── .env                                         # Centralized dynamic configuration (UI, ports, SLA, models)
├── .env.example                                 # Template environment file
├── run_dashboard.py                             # Single-command launcher with readiness polling
├── start.bat                                    # Windows one-click batch launcher
├── pyrightconfig.json                           # Workspace typing configuration
├── README.md                                    # Master project documentation
├── KT_Documents/                                # Dedicated Knowledge Transfer (KT) documentation directory
│   ├── README.md                                # Architectural & operational guide
│   ├── response_generation_logic.md             # End-to-end query execution & RAG documentation
│   └── SCALABILITY_AND_INTELLIGENCE_ARCHITECTURE.md # Multi-GB streaming & intelligence architecture
├── service_logs/                                # Dedicated directory to dump service logs for analysis
│   ├── log-2026-09-22_PaymentExport.log         # Sample service log (Export pipeline)
│   ├── log-2026-10-13_ACHStatus.log             # Sample service log (ACH settlement)
│   ├── log-2026-10-13_DailyPaymentFile.log      # Sample service log (Daily reporting)
│   └── log-2026-10-13_Settledment.log           # Sample service log (Gateway settlements)
├── backend/
│   ├── requirements.txt                         # Python package requirements
│   ├── calculate_response_time.py               # Response generation timing & benchmark script
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py                            # Dynamic environment variable loader (.env)
│   │   ├── logger.py                            # Safe UTF-8 rotating execution logger (logs/backend.log)
│   │   ├── models.py                            # Pydantic data schemas & response models
│   │   ├── parser.py                            # O(1) RAM streaming log parser & regex extractor
│   │   ├── analyzer.py                          # Dynamic KPI aggregation, metrics & RCA engine
│   │   ├── db.py                                # SQLite WAL, B-Tree indexes & FTS5 full-text engine
│   │   ├── ai_service.py                        # In-memory Local Qwen 2.5 3B SLM & StreamCapture
│   │   ├── query_engine.py                      # Multi-intent query deconstructor, RAG & safeguards
│   │   └── main.py                              # FastAPI REST API, lifespan handler & static mounts
│   └── data/
│       └── logs.db                              # High-performance SQLite database & FTS5 tables
├── frontend/
│   ├── index.html                               # Single-page executive monitoring dashboard
│   ├── css/
│   │   └── style.css                            # Glassmorphism, animations, dark/light themes
│   └── js/
│       ├── app.js                               # State management, API bindings, live stopwatch & modals
│       ├── charts.js                            # Dynamic Chart.js visualizations
│       └── vendor/                              # Local vendor libraries (Chart.js, Lucide, Marked, Tailwind)
├── logs/
│   └── backend.log                              # Rotating backend execution log file
└── models/
    └── Qwen2.5-3B-Instruct/                     # Project-local weights for offline neural inference
```

---

## ⚡ Quick Start

### 1. Launch the Application
Run the launcher from PowerShell or terminal:
```powershell
python run_dashboard.py
```
*Or simply double-click **`start.bat`** on Windows.*

> [!NOTE]
> `run_dashboard.py` automatically detects and activates the dedicated `.venv` virtual environment, checks backend readiness via `/api/health`, and opens the browser at `http://127.0.0.1:8000` only after log indexing and model warmup are complete.

### 2. Measure Response Generation Time & Run Benchmarks
To measure response latency, Time to First Token (TTFT), token generation speed, and answer quality directly from the CLI:
```powershell
# Run a single forensic query with high-precision timing report
python backend/calculate_response_time.py "what is the latest error"

# Run a service-scoped query
python backend/calculate_response_time.py "what is the latest error" --service DorchesterPaymentExport

# Run line-by-line inspection
python backend/calculate_response_time.py "what happened on line 435"

# Run 10-query automated benchmark suite
python backend/calculate_response_time.py --benchmark
```

### 3. Inspect Live Backend Logs
Every startup event, HTTP request, SQLite index operation, query classification, and LLM token timing is recorded in `logs/backend.log`:
- **In Dashboard UI:** Click **"Backend Logs"** in the navigation bar to open the live terminal viewer with real-time polling.
- **In PowerShell:**
  ```powershell
  Get-Content -Path logs\backend.log -Wait -Tail 30
  ```

---

## ⚙️ Environment Configuration (`.env`)

All application settings, UI branding, network addresses, and local model parameters are configured centrally in [`.env`](file:///.env):

```ini
# Application Branding & Identity (Dynamic UI)
APP_NAME=ServiceLog Intelligence Hub
APP_TITLE=ServiceLog Intelligence Hub | Enterprise Observability & Root Cause Analysis
APP_TAGLINE=Beyond Observability
APP_SUBTITLE=Autonomous Log Intelligence, SRE Diagnostic Triage & Multi-Service Monitoring
APP_ORG_NAME=LogTrax Enterprise
APP_NAV_BADGE=Observability Hub

# Operational SLA Threshold (Percentage)
SLA_TARGET_PERCENT=95.0

# Network Host & Port
HOST=127.0.0.1
PORT=8000
DEBUG=True

# Directory Paths
LOGS_DIR=service_logs
DATA_DIR=backend/data

# Strictly Offline Local In-Memory Qwen 2.5 SLM Configuration
PROVIDER=qwen
LOCAL_MODEL=Qwen/Qwen2.5-3B-Instruct
MODEL_PATH=models/Qwen2.5-3B-Instruct
MAX_NEW_TOKENS=220
```

---

## 🌐 REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves the responsive executive UI dashboard. |
| `GET` | `/api/health` | System health, model readiness, and provider status. |
| `GET` | `/api/config` | Returns dynamic UI branding, organization name, and SLA thresholds from `.env`. |
| `GET` | `/api/overview` | Synthesizes system-wide or service-scoped KPI metrics (records processed, successes, errors, SLA %). |
| `GET` | `/api/services` | Returns operational summaries, status indicators, and key notes for all discovered services. |
| `GET` | `/api/errors/causes` | Returns structured Root Cause Analysis (RCA) records (`ERR-01`, `ERR-02`, etc.). |
| `GET` | `/api/timeline` | Hourly activity, transaction throughput, and error distribution for timeline charts. |
| `GET` | `/api/logs` | Paginated, filterable log query endpoint (by `service`, `level`, `date`, `search`, `page`, `page_size`). |
| `POST` | `/api/query` | Natural language forensic query engine (`{"query": "...", "service": "..."}`). Returns answer and timing telemetry. |
| `GET` | `/api/system/logs` | Returns recent execution lines from `logs/backend.log` for live terminal inspection. |
| `POST` | `/api/reindex` | Triggers a live rescan and SQLite re-indexing of all log files. |
| `POST` | `/api/upload` | Ingests a newly uploaded `.log` file and updates database indexes dynamically. |

---

## 📊 Dashboard Visualizations & Features

1. **Executive KPI Cards**: Real-time totals for processed records, successful throughput, error volume, SLA percentage, and active service counts.
2. **AI Forensic Assistant**: Accepts free-form natural language queries, automatically routing through the SQLite RAG layer to the local in-memory Qwen model.
3. **Live Latency & Speed Telemetry**: Renders an execution badge with duration in seconds/milliseconds, Time to First Token (TTFT), and generation speed (tok/s).
4. **Interactive Chart.js Visualizations**:
   - Success vs. Error Donut chart with live percentage indicator.
   - Service Volume comparison grouped bar chart.
   - Root Cause distribution horizontal bar chart.
   - Hourly activity and error timeline line chart.
5. **Root Cause Analysis (RCA) Cards**: In-depth forensic diagnosis, affected transactions, exception classes, and engineering remediation recommendations.
6. **Filterable Log Explorer**: Search and filter by service, severity level (`ERROR`, `INFO`, `DEBUG`), date, or free text, with modal drilldown for complete stack traces.
7. **Dynamic Log Ingestion**: Upload new `.log` files directly via the UI to immediately incorporate them into metrics and search indexes.
