# API Documentation & Contract Specification

## Conventions

- **Base URL:** `http://127.0.0.1:8000` (or configured `HOST:PORT` from `.env`)
- **Authentication:** Local internal operator (Bearer token extensible via reverse proxy)
- **Versioning Strategy:** URI path-based (`/api/v1` alias mapped to `/api`)
- **Data Format:** JSON (`application/json; charset=utf-8`) for data endpoints; `multipart/form-data` for file uploads
- **Pagination Strategy:** Zero-based or 1-based page index with limit (`page=1&page_size=50`)
- **Standard Error Format:**
  ```json
  {
    "detail": "Error message description",
    "request_id": "a1b2c3d4",
    "error": "Optional internal exception details (if debug enabled)"
  }
  ```

---

## Endpoint Catalog

---

### 1. `GET /api/config`

- **Purpose:** Fetches dynamic application branding, title, organization name, navigation badges, and operational SLA targets loaded from `.env`. Enables zero-hardcoding on the UI.
- **Required Permission:** Public / Viewer
- **Parameters:** None
- **Success Response (HTTP 200):**
  ```json
  {
    "app_name": "ServiceLog Intelligence Hub",
    "app_title": "ServiceLog Intelligence Hub | Enterprise Observability & Root Cause Analysis",
    "app_tagline": "Beyond Observability",
    "app_subtitle": "Autonomous Log Intelligence, SRE Diagnostic Triage & Multi-Service Monitoring",
    "app_org_name": "LogTrax Enterprise",
    "app_nav_badge": "Observability Hub",
    "sla_target_percent": 95.0,
    "model_name": "Qwen/Qwen2.5-3B-Instruct",
    "provider": "qwen"
  }
  ```
- **Error Responses:** HTTP 500 on configuration read failure.
- **Idempotency:** Idempotent (Safe `GET`).

---

### 2. `GET /api/health`

- **Purpose:** Health check endpoint reporting backend operational status, model readiness, and version metadata.
- **Required Permission:** Public
- **Parameters:** None
- **Success Response (HTTP 200):**
  ```json
  {
    "status": "ok",
    "service": "ServiceLog Intelligence Hub",
    "version": "1.0.0",
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "provider": "qwen",
    "local_llm_ready": true
  }
  ```
- **Idempotency:** Idempotent.

---

### 3. `GET /api/overview`

- **Purpose:** Returns high-level executive telemetry: total records processed, successful records, error count, service breaks count, overall success percentage, and SLA compliance.
- **Required Permission:** Public / Viewer
- **Query Parameters:**
  - `service` (*optional*, string): Filter metrics to a specific service name.
- **Success Response (HTTP 200):**
  ```json
  {
    "total_records_processed": 142500,
    "successful_records": 138650,
    "success_rate_percent": 97.3,
    "total_error_logs": 3850,
    "service_breaks_count": 42,
    "total_log_files": 4,
    "sla_target_percent": 95.0,
    "is_sla_met": true,
    "current_system_date": "2026-11-10"
  }
  ```
- **Idempotency:** Idempotent.

---

### 4. `GET /api/services`

- **Purpose:** Discovers and lists all monitored services, their record counts, error totals, individual success percentages, and last-active timestamps.
- **Required Permission:** Public / Viewer
- **Parameters:** None
- **Success Response (HTTP 200):**
  ```json
  [
    {
      "service_name": "PaymentGatewayService",
      "total_records": 48200,
      "success_records": 46500,
      "error_records": 1700,
      "success_rate": 96.47,
      "last_activity": "2026-11-10 14:22:15",
      "status": "HEALTHY"
    },
    {
      "service_name": "OrderProcessingService",
      "total_records": 52100,
      "success_records": 51200,
      "error_records": 900,
      "success_rate": 98.27,
      "last_activity": "2026-11-10 14:22:18",
      "status": "HEALTHY"
    }
  ]
  ```
- **Idempotency:** Idempotent.

---

### 5. `GET /api/errors/causes`

- **Purpose:** Returns aggregated Root Cause Analysis (RCA) clusters, categorizing exceptions, failure counts, and affected services.
- **Required Permission:** Public / Viewer
- **Query Parameters:**
  - `service` (*optional*, string): Scope results to a specific service.
- **Success Response (HTTP 200):**
  ```json
  [
    {
      "cause": "Database connection pool timeout",
      "count": 142,
      "service": "OrderProcessingService",
      "severity": "HIGH",
      "sample_message": "Timeout waiting for connection from pool after 30000ms"
    },
    {
      "cause": "HTTP 504 Gateway Timeout upstream",
      "count": 89,
      "service": "PaymentGatewayService",
      "severity": "CRITICAL",
      "sample_message": "Payment vendor failed to acknowledge webhook"
    }
  ]
  ```
- **Idempotency:** Idempotent.

---

### 6. `GET /api/timeline`

- **Purpose:** Hourly and daily time-series distribution of errors and overall activity for rendering telemetry trend charts in Chart.js.
- **Required Permission:** Public / Viewer
- **Query Parameters:**
  - `service` (*optional*, string): Scope timeline to a specific service.
- **Success Response (HTTP 200):**
  ```json
  {
    "labels": ["10:00", "11:00", "12:00", "13:00", "14:00"],
    "total_series": [1200, 1450, 1800, 1600, 2100],
    "error_series": [12, 18, 95, 42, 180]
  }
  ```
- **Idempotency:** Idempotent.

---

### 7. `GET /api/logs`

- **Purpose:** Server-side paginated log search and exploration with multi-field filtering (service, level, date, full-text keyword search).
- **Required Permission:** Public / Viewer
- **Query Parameters:**
  - `service` (*optional*, string): Filter by service name.
  - `level` (*optional*, string): Severity level (`INFO`, `WARN`, `ERROR`, `FATAL`).
  - `date` (*optional*, string): Filter by date string (`YYYY-MM-DD`).
  - `search` (*optional*, string): Free-text keyword query matching via SQLite FTS5.
  - `status_filter` (*optional*, string): `SUCCESS`, `FAIL`, or `SERVICE_BREAK`.
  - `page` (*optional*, int, default: 1): Page number (1-based).
  - `page_size` (*optional*, int, default: 50, max: 500): Entries per page.
- **Success Response (HTTP 200):**
  ```json
  {
    "total": 1250,
    "page": 1,
    "page_size": 50,
    "logs": [
      {
        "id": 1042,
        "file_name": "PaymentGatewayService.log",
        "timestamp": "2026-11-10 14:22:15,102",
        "date": "2026-11-10",
        "time": "14:22:15",
        "level": "ERROR",
        "component": "PaymentProcessorThread-4",
        "message": "Transaction failed: Bank response code 504 Gateway Timeout",
        "service": "PaymentGatewayService",
        "line_number": 3412,
        "transaction_id": "TX-99410",
        "status": "FAIL",
        "batch_date": "2026-11-10"
      }
    ]
  }
  ```
- **Idempotency:** Idempotent.

---

### 8. `POST /api/query`

- **Purpose:** Submits an operational question to the dual-path query engine (Local Qwen 2.5 3B SLM grounded with SQLite FTS5 RAG).
- **Required Permission:** Public / Operator
- **Request Body:**
  ```json
  {
    "query": "Why did PaymentGatewayService fail at 14:22?",
    "service": "PaymentGatewayService"
  }
  ```
- **Success Response (HTTP 200):**
  ```json
  {
    "query": "Why did PaymentGatewayService fail at 14:22?",
    "answer": "At 14:22:15, PaymentGatewayService encountered an unhandled HTTP 504 Gateway Timeout while dispatching transaction TX-99410 to the external banking partner.\n\n#### 🔍 Exact Line Context Window (File: `PaymentGatewayService.log`)\n```text\nLine  3410: [14:22:14] [INFO ] Sending payment authorization request\nLine  3411: [14:22:14] [DEBUG] Awaiting gateway handshake on socket #12\n▶ Line 3412: [14:22:15] [ERROR] Transaction failed: Bank response code 504 Gateway Timeout\nLine  3413: [14:22:15] [WARN ] Retrying connection attempt 1 of 3\n```",
    "category": "Local Qwen 2.5 (Qwen/Qwen2.5-3B-Instruct)",
    "metrics": {
      "model": "Qwen/Qwen2.5-3B-Instruct",
      "provider": "qwen",
      "total_records": 48200,
      "successful_records": 46500,
      "success_rate": "96.47%",
      "total_errors": 1700,
      "service_breaks": 12,
      "latency_s": 2.14,
      "ttft_s": 0.285,
      "speed_tok_s": 58.4,
      "tokens": 125
    },
    "service": "Autonomous LLM Agent",
    "evidence": [
      {
        "file": "PaymentGatewayService.log",
        "timestamp": "2026-11-10 14:22:15",
        "level": "ERROR",
        "message": "Transaction failed: Bank response code 504 Gateway Timeout"
      }
    ],
    "suggested_queries": [],
    "duration_ms": 2140.2,
    "duration_s": 2.14,
    "ttft_s": 0.285,
    "generation_time_s": 2.14,
    "tokens_per_sec": 58.4,
    "tokens_count": 125
  }
  ```
- **Error Responses:**
  - `400 Bad Request` if `query` is empty or whitespace.
  - `500 Internal Server Error` if both neural SLM and deterministic fallback fail.
- **Idempotency:** Safe read query; idempotent.

---

### 9. `POST /api/upload`

- **Purpose:** Ingests and registers a new operational service log file. Stores the file in `service_logs/`, parses log lines, and updates SQLite and FTS5 tables immediately.
- **Required Permission:** Operator / Admin
- **Request Format:** `multipart/form-data`
  - `file`: The `.log` file to upload.
- **Success Response (HTTP 200):**
  ```json
  {
    "status": "uploaded",
    "filename": "AuthService.log",
    "total_entries": 42100,
    "message": "File 'AuthService.log' uploaded and parsed successfully."
  }
  ```
- **Error Responses:**
  - `400 Bad Request` if filename is empty or does not end with `.log`.
  - `500 Internal Server Error` on disk write or parse failure.
- **Side Effects:** Writes file to disk at `service_logs/<filename>`; modifies SQLite database.

---

### 10. `POST /api/reindex`

- **Purpose:** Forces a full filesystem re-scan of `service_logs/`, re-parsing all log lines and re-syncing SQLite tables and FTS5 indexes.
- **Required Permission:** Operator / Admin
- **Parameters:** None
- **Success Response (HTTP 200):**
  ```json
  {
    "status": "success",
    "message": "Successfully reindexed 142500 log entries across 4 files.",
    "overview": {
      "total_records_processed": 142500,
      "successful_records": 138650,
      "success_rate_percent": 97.3,
      "total_error_logs": 3850
    }
  }
  ```
- **Side Effects:** Truncates and rebuilds `service_logs` and `service_logs_fts` data.

---

### 11. `GET /api/system/logs`

- **Purpose:** Returns internal runtime logs generated by the FastAPI backend itself, enabling real-time diagnostic debugging in the UI.
- **Required Permission:** Admin / SRE
- **Query Parameters:**
  - `lines` (*optional*, int, default: 150, min: 10, max: 1000): Number of trailing log lines to return.
- **Success Response (HTTP 200):**
  ```json
  {
    "log_file": "logs/backend.log",
    "lines_returned": 150,
    "logs": [
      "[2026-11-10 10:44:42] [INFO   ] [backend:main:55] - System startup initialized on 127.0.0.1:8000",
      "[2026-11-10 10:44:43] [INFO   ] [backend:query_engine:138] - Routing query to Local Qwen SLM"
    ]
  }
  ```

---

### 12. `GET /api/settings/ai` & `POST /api/settings/ai`

- **Purpose:** Inspect and update configuration settings for the AI inference provider.
- **Success Response (HTTP 200):**
  ```json
  {
    "is_configured": true,
    "model": "Qwen/Qwen2.5-3B-Instruct",
    "masked_key": "local-in-memory",
    "provider": "qwen",
    "endpoint_url": "local-in-memory",
    "message": "Local Qwen 2.5 3B model is active and running in-memory."
  }
  ```

