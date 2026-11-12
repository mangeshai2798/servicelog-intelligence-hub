# Database Architecture & Data Model

## 1. Database Engine

- **Engine:** SQLite 3 (with `FTS5` Full-Text Search extension)
- **File Location:** `backend/data/logs.db` (dynamically configured via `DATA_DIR` in `.env`)
- **Concurrency & Journaling Mode:**
  - `PRAGMA journal_mode = WAL;` (Write-Ahead Logging enables non-blocking concurrent reads during bulk writes)
  - `PRAGMA synchronous = NORMAL;` (Maximizes write throughput while preserving ACID integrity against app crashes)
  - `check_same_thread = False;` (Allows shared multi-threaded FastAPI execution)

---

## 2. Naming Conventions

- **Tables:** Snake_case, pluralized or descriptive nouns (e.g., `service_logs`, `ingestion_state`, `error_signatures`).
- **Columns:** Snake_case (e.g., `transaction_id`, `line_number`, `stack_trace`, `file_name`).
- **Primary Keys:** Standard `id` (INTEGER AUTOINCREMENT) for relational tables; descriptive primary key for state tables (`file_name`, `signature_id`).
- **Timestamps:** ISO 8601 string format (`YYYY-MM-DD HH:MM:SS`) or epoch timestamps for high-precision comparison.
- **Indexes:** Prefixed with `idx_` followed by target table/columns (e.g., `idx_service_date`, `idx_file_line`).

---

## 3. Schema Definitions

### Table 1: `service_logs`
Primary relational repository storing parsed log events from all uploaded and ingested services.

```sql
CREATE TABLE IF NOT EXISTS service_logs (
    id INTEGER PRIMARY KEY,
    file_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    level TEXT NOT NULL,
    component TEXT NOT NULL,
    message TEXT NOT NULL,
    service TEXT NOT NULL,
    url TEXT DEFAULT '',
    action TEXT DEFAULT '',
    stack_trace TEXT,
    line_number INTEGER,
    transaction_id TEXT,
    status TEXT NOT NULL,
    batch_date TEXT NOT NULL
);
```

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | No (PK) | Unique auto-incrementing log record identifier. |
| `file_name` | `TEXT` | No | Name of the source file (e.g., `PaymentGatewayService.log`). |
| `timestamp` | `TEXT` | No | Full timestamp string as parsed from the raw log line. |
| `date` | `TEXT` | No | Extracted date component (`YYYY-MM-DD`). |
| `time` | `TEXT` | No | Extracted time component (`HH:MM:SS`). |
| `level` | `TEXT` | No | Normalized severity level (`INFO`, `WARN`, `ERROR`, `FATAL`). |
| `component` | `TEXT` | No | Internal thread, logger name, or component module. |
| `message` | `TEXT` | No | The primary log payload or exception message. |
| `service` | `TEXT` | No | Service name derived from file name or log header. |
| `url` | `TEXT` | Yes | HTTP endpoint or RPC URI, if present in log line. |
| `action` | `TEXT` | Yes | Controller action or method name, if detected. |
| `stack_trace` | `TEXT` | Yes | Multiline exception stack trace accompanying the error. |
| `line_number` | `INTEGER` | Yes | 1-based line number inside the physical source log file. |
| `transaction_id` | `TEXT` | Yes | Extracted business ID (GUID, transactionId, orderId, reqId). |
| `status` | `TEXT` | No | Normalized health status (`SUCCESS`, `FAIL`, `SERVICE_BREAK`). |
| `batch_date` | `TEXT` | No | Ingestion partition date key for fast range filtering. |

---

### Table 2: `ingestion_state`
Tracks file metadata to ensure fast, incremental ingestion without re-reading unchanged files.

```sql
CREATE TABLE IF NOT EXISTS ingestion_state (
    file_name TEXT PRIMARY KEY,
    file_size INTEGER NOT NULL,
    last_mtime REAL NOT NULL,
    last_line_number INTEGER NOT NULL,
    total_entries_indexed INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
```

---

### Table 3: `error_signatures`
Pre-aggregated error signature clusters used for instant sub-millisecond root cause analysis and dashboard summaries.

```sql
CREATE TABLE IF NOT EXISTS error_signatures (
    signature_id TEXT PRIMARY KEY,
    service TEXT NOT NULL,
    error_type TEXT NOT NULL,
    sample_message TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    count INTEGER NOT NULL,
    sample_line_number INTEGER,
    sample_file TEXT,
    sample_stack_trace TEXT
);
```

---

### Table 4: `service_logs_fts` (FTS5 Virtual Table)
High-performance full-text search index mapping directly to `service_logs`.

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS service_logs_fts USING fts5(
    message,
    stack_trace,
    component,
    service,
    transaction_id,
    content='service_logs',
    content_rowid='id'
);
```

---

## 4. Triggers & Synchronization

To guarantee 100% data consistency between `service_logs` and the `FTS5` virtual table, SQLite triggers automatically mirror insert, update, and delete mutations:

```sql
-- Trigger 1: Auto-index on INSERT
CREATE TRIGGER IF NOT EXISTS trg_service_logs_ai AFTER INSERT ON service_logs BEGIN
    INSERT INTO service_logs_fts(rowid, message, stack_trace, component, service, transaction_id)
    VALUES (new.id, new.message, new.stack_trace, new.component, new.service, new.transaction_id);
END;

-- Trigger 2: Auto-delete on DELETE
CREATE TRIGGER IF NOT EXISTS trg_service_logs_ad AFTER DELETE ON service_logs BEGIN
    INSERT INTO service_logs_fts(service_logs_fts, rowid, message, stack_trace, component, service, transaction_id)
    VALUES ('delete', old.id, old.message, old.stack_trace, old.component, old.service, old.transaction_id);
END;

-- Trigger 3: Auto-update on UPDATE
CREATE TRIGGER IF NOT EXISTS trg_service_logs_au AFTER UPDATE ON service_logs BEGIN
    INSERT INTO service_logs_fts(service_logs_fts, rowid, message, stack_trace, component, service, transaction_id)
    VALUES ('delete', old.id, old.message, old.stack_trace, old.component, old.service, old.transaction_id);
    INSERT INTO service_logs_fts(rowid, message, stack_trace, component, service, transaction_id)
    VALUES (new.id, new.message, new.stack_trace, new.component, new.service, new.transaction_id);
END;
```

---

## 5. Indexes & Performance Optimization

B-tree indexes are tailored to support sub-10ms query execution across high-frequency dashboard access patterns:

| Index Name | Columns Indexed | Optimization Purpose |
| :--- | :--- | :--- |
| `idx_service_date` | `(service, batch_date)` | Speeds up service-filtered daily aggregate overviews. |
| `idx_level` | `(level)` | Instant counting of `ERROR`, `WARN`, `INFO` records. |
| `idx_status` | `(status)` | Sub-millisecond calculation of `SERVICE_BREAK` and `FAIL` rates. |
| `idx_file_name` | `(file_name)` | Quick file-scoped purges and re-indexing scans. |
| `idx_tx_id` | `(transaction_id)` | Enables instantaneous cross-service transaction lifecycle queries. |
| `idx_file_line` | `(file_name, line_number)` | Powers line context window lookups (target line ± 4 lines). |
| `idx_timestamp` | `(timestamp)` | Optimizes time-window queries (e.g., between 14:10 and 14:30). |

---

## 6. Data Validation & Normalization Rules

1. **Timestamp Normalization:** Timestamps in standard patterns (`YYYY-MM-DD HH:MM:SS,fff` or `ISO 8601`) are parsed and decomposed into `date` and `time` columns for clean SQL indexing.
2. **Transaction ID Extraction:** Regex automatically discovers identifiers across standard keys: `TransactionId`, `tx_id`, `OrderId`, `PaymentId`, `RequestId`, `CorrelationId`, and UUID/GUID formats.
3. **Severity Level Canonicalization:** Normalized into uppercase: `INFO`, `DEBUG`, `WARN`, `WARNING` (mapped to `WARN`), `ERROR`, `FATAL`, `CRITICAL` (mapped to `FATAL`).
4. **Status Assignment:**
   - Lines with unhandled exceptions, panics, or premature halts are tagged `SERVICE_BREAK`.
   - General error lines are tagged `FAIL`.
   - Normal operations are tagged `SUCCESS`.

---

## 7. Soft Delete vs. Hard Delete

- **Ingestion Re-syncing:** When a file is modified or reindexed via `POST /api/reindex` or `POST /api/upload`, records for that `file_name` are cleanly deleted and re-inserted inside an atomic SQLite transaction.
- **Log Permanence:** The database acts as an indexed cache of the raw filesystem logs. No soft deletion flag is required because the source logs on disk remain the immutable ground truth.

---

## 8. Auditing & Telemetry Tracking

- `ingestion_state` tracks `last_mtime`, `last_line_number`, and `total_entries_indexed` per file.
- All incoming HTTP queries receive a unique `req_id` (`uuid.uuid4()[:8]`), logged with total execution duration in milliseconds.

---

## 9. Sensitive Data & Privacy

- SQLite database is stored locally in `backend/data/logs.db` and is ignored by version control (`.gitignore`).
- Password and API key masking logic in `parser.py` redacts credential tokens matching `Bearer\s+[A-Za-z0-9._-]+` or `password\s*[:=]\s*[^\s]+`.

---

## 10. Seed Data

Sample operational multi-service logs are provided in `service_logs/`:
- `CustomerManagementService.log`
- `InventoryManagementService.log`
- `OrderProcessingService.log`
- `PaymentGatewayService.log`

