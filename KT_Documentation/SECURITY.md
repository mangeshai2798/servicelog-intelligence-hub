# Security Guidelines & Policies

## 1. Authentication

- **Architecture:** Local Intranet / Air-Gapped Appliance Model
- **Current Mode:** Internal Trusted Operator (Single-tenant SRE workstation or bastion host).
- **Extensibility:** The FastAPI framework is designed to integrate OAuth2 / JWT bearer tokens or reverse-proxy headers (`X-Forwarded-User`, `X-Forwarded-Email`) when deployed behind enterprise identity gateways (e.g., Cloudflare Access, AWS ALB, NGINX auth_request).

---

## 2. Authorization & RBAC

| Role | Scope | Permissions |
| :--- | :--- | :--- |
| **SRE / Admin** | Complete System | Read overview, query logs, trigger reindex, upload service logs, modify local AI settings. |
| **Viewer / Auditor** | Read-Only | View dashboard metrics, search logs, execute AI queries (mutation endpoints disabled). |

Authorization is strictly verified server-side in API route dependencies.

---

## 3. Secrets Management & Zero-Hardcoding Principles

1. **No Hardcoded Secrets:** Credentials, database passwords, and API keys must **never** be hardcoded anywhere in the codebase.
2. **Local AI Execution (Zero Keys Required):** The primary neural reasoning engine (`Qwen/Qwen2.5-3B-Instruct`) runs strictly offline in local RAM. **No OpenAI, Anthropic, or cloud API keys are required or sent over the network.**
3. **Source Control Hygiene:** All secrets, `.env` files, temporary logs, and SQLite database files (`*.db`, `*.sqlite`, `*.log`) are explicitly listed in `.gitignore`.
4. **Environment Isolation:** Configuration parameters are loaded exclusively at runtime via `python-dotenv` into `backend/app/config.py`.

---

## 4. Environment Variables Matrix

| Variable Name | Classification | Default Value | Purpose |
| :--- | :--- | :--- | :--- |
| `APP_NAME` | Public (UI) | `ServiceLog Intelligence Hub` | Top-level branding string. |
| `APP_ORG_NAME` | Public (UI) | `LogTrax Enterprise` | Organization identifier. |
| `SLA_TARGET_PERCENT` | Public (UI) | `95.0` | Operational SLA threshold. |
| `HOST` | Private (Infra) | `127.0.0.1` | Network interface binding. |
| `PORT` | Private (Infra) | `8000` | Backend listening port. |
| `DEBUG` | Private (Infra) | `True` | Debug mode logging switch. |
| `LOGS_DIR` | Private (Infra) | `service_logs` | Local path to ingested log files. |
| `DATA_DIR` | Private (Infra) | `backend/data` | Path to embedded SQLite database. |
| `PROVIDER` | Private (AI) | `qwen` | Inference provider identifier. |
| `LOCAL_MODEL` | Private (AI) | `Qwen/Qwen2.5-3B-Instruct` | Local Hugging Face model identifier. |

---

## 5. API Security & Threat Mitigation

### Input Validation
- Every incoming payload is validated using **Pydantic v2 schemas** (`QueryRequest`, `AISettingsRequest`).
- Malformed inputs, unexpected data types, or oversized strings are automatically rejected with standard HTTP 422 Unprocessable Entity responses.

### CORS Configuration
- In local development mode, CORS is configured via `CORSMiddleware`:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],  # Restricted to specific enterprise origins in production
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

### Directory Traversal Prevention
- Log file access and queries validate target file names against resolved path boundaries inside `LOGS_DIR`.
- Requests containing `../`, `..\\`, or absolute paths outside the designated folder are blocked.

### SQL Injection Prevention
- All database queries in `backend/app/db.py` use **parameterized SQL statements** (`?` placeholders).
- User input is never concatenated directly into raw SQL strings.
- FTS5 full-text queries sanitize special query characters (`"`, `*`, `AND`, `OR`, `NEAR`) before dispatching to SQLite.

---

## 6. Data Protection & Sovereignty

- **Air-Gapped Operation:** All neural token generation and data querying happens on the local CPU/RAM. Zero customer logs or queries leave the host machine.
- **Data at Rest:** SQLite database files reside on local storage. File-level permissions (`chmod 600` on Linux/macOS) should be enforced in production.
- **Retention Policies:** Storage footprint is bounded by disk size; manual or cron-based purges of older `.log` files in `service_logs/` can be executed safely.

---

## 7. Logging Rules & Redaction

### Never Log:
- Passwords, hashes, secret tokens, or Bearer credentials.
- Credit card numbers, CVVs, or Social Security numbers.
- Raw API keys or authorization headers.

### Always Log:
- HTTP request ID, method, path, client IP, and response latency.
- Ingestion events (file name, lines indexed, parse duration).
- Query execution timings (TTFT, generation duration, tokens/sec).
- Unhandled application exceptions with sanitized stack traces.

---

## 8. File Upload Security (`POST /api/upload`)

1. **Extension Whitelisting:** Only files ending with the `.log` extension are permitted. All executable or script extensions (`.exe`, `.sh`, `.py`, `.js`, `.bat`) are rejected immediately.
2. **File Size Limit:** Recommended maximum upload size: 100 MB per file.
3. **Streaming Ingestion:** Uploaded files are streamed to disk buffer using `shutil.copyfileobj` to prevent RAM exhaustion.
4. **Path Sanitization:** File names are stripped of directory traversal tokens (`Path(filename).name`) before writing to `LOGS_DIR`.

---

## 9. Security Audit Checklist

- [x] Zero external API keys or cloud LLM endpoints required.
- [x] Parameterized SQL queries prevent SQL injection across all database functions.
- [x] File upload endpoint enforces strict `.log` extension whitelisting.
- [x] Path traversal protections prevent accessing files outside `service_logs/`.
- [x] Pydantic v2 validates all incoming JSON request bodies.
- [x] Passwords and credentials masked during parsing and logging.
- [x] Cache-Control headers prevent browser caching of sensitive operational telemetry.
- [x] Sensitive files (`.env`, `logs.db`) included in `.gitignore`.

