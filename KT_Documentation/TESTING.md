# Testing Strategy & Quality Assurance

## 1. Testing Goals

The test suite guarantees the reliability, latency thresholds, and accuracy of the log monitoring and query platform:
1. **Parser Resilience:** Validate that `parser.py` accurately extracts fields from arbitrary log formats without crashing on malformed lines.
2. **Database Integrity:** Ensure SQLite FTS5 triggers keep the full-text search index perfectly synchronized with raw log insertions and deletions.
3. **Query Engine Accuracy:** Verify that natural language queries correctly extract ground-truth facts (line context windows, transaction lifecycles, error break-flows).
4. **Latency Verification:** Benchmark Time to First Token (TTFT) and total query latency against established SLA targets.
5. **Zero Cloud Leakage:** Ensure no network calls are initiated during neural generation or log indexing.

---

## 2. Test Types

### Unit Testing
- **Regex & Parsing:** Test individual log line regex patterns, timestamp format parsers, and status normalizers in `parser.py`.
- **Database Functions:** Verify helper functions in `db.py` (`get_log_line_with_context()`, `get_transaction_lifecycle()`, `search_logs_dynamic()`).
- **Statistical Aggregations:** Test `analyzer.py` calculations (SLA percentages, total error counts, break-flow detections).

### Integration Testing
- **FastAPI Endpoints:** Test `/api/overview`, `/api/services`, `/api/query`, `/api/logs`, and `/api/upload` using HTTP test clients.
- **Log Upload & Ingestion:** Upload sample `.log` files and verify that database tables and FTS5 indexes update correctly.
- **AI Service Integration:** Test `ai_service.generate_response()` to ensure prompt assembly, streaming callbacks, and metric extraction succeed.

### End-to-End & Performance Benchmarking
- **Latency Benchmarks:** Run `backend/calculate_response_time.py` to test end-to-end response times and token generation speeds.
- **Dashboard UI Validation:** Validate frontend rendering, dynamic configuration loading, filter pill responsiveness, and real-time query stopwatch in the browser.

---

## 3. Testing Tools & Frameworks

| Tool | Purpose | Usage / Invocation |
| :--- | :--- | :--- |
| **Python `unittest` / `pytest`** | Unit & integration test execution | `pytest tests/` or `python -m unittest discover` |
| **`calculate_response_time.py`** | Performance benchmarking tool | `python backend/calculate_response_time.py --benchmark` |
| **`python -m py_compile`** | Python syntax validation | `python -m py_compile backend/app/<module>.py` |
| **`httpx` / `requests`** | REST API contract testing | Integrated inside test scripts |
| **Chrome DevTools** | Frontend rendering & network auditing | F12 Console & Network panel audit |

---

## 4. Test File Structure

```text
Logs_Monitoring_Project/
├── backend/
│   ├── calculate_response_time.py   # Latency benchmark suite & live API tester
│   └── tests/                        # Automated test suite
│       ├── __init__.py
│       ├── test_parser.py           # Unit tests for log format regexes
│       ├── test_db.py               # Unit tests for SQLite & FTS5 operations
│       ├── test_analyzer.py         # Unit tests for metrics calculation
│       └── test_api.py              # Integration tests for FastAPI endpoints
```

---

## 5. Critical User Flows & Verification Steps

### Flow 1: Log Ingestion & Reindexing
- **Steps:**
  1. Deposit a new `.log` file into `service_logs/` (or upload via `POST /api/upload`).
  2. Invoke `POST /api/reindex`.
  3. Query `GET /api/overview`.
- **Expected Result:** HTTP 200; `total_records_processed` and `total_log_files` increment; new service name appears in `/api/services`.

### Flow 2: Natural Language Forensic Query
- **Steps:**
  1. Send `POST /api/query` with `{"query": "what is the latest error in PaymentGatewayService", "service": "PaymentGatewayService"}`.
- **Expected Result:** HTTP 200; returns non-empty `answer`, `category` citing Local Qwen 2.5, `metrics` containing `ttft_s`, `speed_tok_s`, and `evidence` array with exact line numbers.

### Flow 3: Line Number Context Extraction
- **Steps:**
  1. Send `POST /api/query` with `{"query": "inspect line 120 in OrderProcessingService.log"}`.
- **Expected Result:** Answer includes an exact Line Context Window with target line marked by `▶` and preceding/succeeding lines.

### Flow 4: Transaction Lifecycle Audit
- **Steps:**
  1. Send `POST /api/query` with `{"query": "trace transaction TX-9021"}`.
- **Expected Result:** Answer renders a chronological markdown audit table showing step-by-step service, component, line number, and event messages.

---

## 6. Coverage Targets & Priority Matrix

- **Overall Coverage Target:** > 80% across core backend modules.
- **High Priority (Must be 100% verified):**
  - `parser.py`: Zero unhandled exceptions on unexpected log strings.
  - `query_engine.py`: Refusal interception logic and fallback substitution.
  - `db.py`: Parameterized SQL statement execution and FTS5 synchronization.
  - `ai_service.py`: Memory safety and graceful fallback when offline model is unavailable.

---

## 7. Quality Assurance Commands

### 1. Syntax & Compilation Check
```powershell
python -m py_compile backend/app/main.py backend/app/query_engine.py backend/app/db.py backend/app/parser.py backend/app/analyzer.py backend/app/ai_service.py
```

### 2. Live Performance Benchmark (Direct SLM + RAG)
```powershell
python backend/calculate_response_time.py --benchmark
```

### 3. Live HTTP API Endpoint Test
```powershell
python backend/calculate_response_time.py --api
```

### 4. Direct Single-Query Verification
```powershell
python backend/calculate_response_time.py "Why did PaymentGatewayService fail?"
```

---

## 8. Definition of Done (Testing Checklist)

A change or pull request is ready for deployment only when:
- [x] All modified Python files pass `python -m py_compile` without errors.
- [x] Static type analysis (Pyright / Pylance) reports zero uninitialized variables or type assignment errors.
- [x] `calculate_response_time.py` executes successfully with valid TTFT and latency metrics.
- [x] Live API test against `/api/query` returns valid JSON response with evidence.
- [x] Frontend console has zero uncaught JavaScript exceptions during user flows.

