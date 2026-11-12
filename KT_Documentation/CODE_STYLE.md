# Code Style & Conventions

## 1. General Principles

1. **Clarity Over Cleverness:** Write readable, self-describing Python and JavaScript code. Avoid dense one-liners or esoteric metaprogramming.
2. **Zero Hardcoding Rule:** Never hardcode application names, SLA thresholds, service names, or model identifiers. Read values from `.env` or derive them from database metadata.
3. **Single Responsibility:** Each module, class, and function must have a focused, clearly defined operational purpose.
4. **Preserve Working Behavior:** When extending or refactoring, preserve existing working functionality and maintain backwards-compatible API contracts.
5. **No Dead Code:** Remove unused variables, deprecated scripts, commented-out debug blocks, and obsolete endpoints before committing.

---

## 2. Naming Conventions

### Python (Backend)
- **Files / Modules:** Snake_case (e.g., `query_engine.py`, `ai_service.py`, `models.py`).
- **Classes:** PascalCase (e.g., `LogAnalyzer`, `QueryEngine`, `LocalQwenEngine`, `OverviewMetrics`).
- **Functions & Methods:** Snake_case (e.g., `answer_query()`, `sync_logs_to_db()`, `get_transaction_lifecycle()`).
- **Variables:** Snake_case with descriptive names (e.g., `gen_tokens_count`, `detected_service`, `total_dur_ms`). Avoid single-letter variables except for standard loop indices (`i`, `idx`).
- **Constants:** Upper snake_case (e.g., `SLA_TARGET_PERCENT`, `DEFAULT_PAGE_SIZE`, `DB_PATH`).
- **Type Annotations:** Use Python standard typing (`Optional[str]`, `List[Dict[str, Any]]`, `Tuple[int, List[Dict[str, Any]]]`).

### JavaScript (Frontend)
- **Files:** Kebab-case or snake_case (e.g., `app.js`, `charts.js`).
- **Functions:** CamelCase (e.g., `loadDashboardConfig()`, `renderQueryResponse()`, `initCharts()`).
- **Variables:** CamelCase (e.g., `activeServiceFilter`, `responseContainer`, `stopwatchInterval`).
- **DOM Element References:** Suffix with descriptive role (e.g., `querySubmitBtn`, `serviceFilterContainer`, `logTableBody`).

### Database & APIs
- **Database Tables & Columns:** Snake_case (e.g., `service_logs`, `transaction_id`, `line_number`).
- **REST Endpoints:** Kebab-case or lowercase noun-based URIs (e.g., `/api/overview`, `/api/errors/causes`, `/api/settings/ai`).

---

## 3. Directory & Folder Layout

```text
Logs_Monitoring_Project/
├── backend/
│   ├── app/                 # All FastAPI backend application code
│   └── data/                # Persistent SQLite databases and caches
├── frontend/
│   ├── css/                 # CSS stylesheets and design tokens
│   ├── js/                  # Application JavaScript logic
│   └── img/                 # Static branding assets
├── service_logs/            # Ingested operational log files
└── KT_Documentation/       # Single source of truth documentation
```

---

## 4. Import Ordering Rules

Follow PEP 8 import grouping with an empty line separating each group:
1. **Standard Library Imports:** (`time`, `re`, `uuid`, `pathlib`, `typing`)
2. **Third-Party Frameworks & Libraries:** (`fastapi`, `pydantic`, `torch`, `transformers`)
3. **Local Application Modules:** (`from app.config import ...`, `from app.logger import logger`)

Example from `backend/app/query_engine.py`:
```python
import time
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.analyzer import LogAnalyzer, analyzer
from app.ai_service import ai_service
from app.logger import logger
from app.models import QueryResponse
from app.db import get_log_line_with_context
```

---

## 5. Functions & Method Design

- **Length:** Keep functions under 60 lines where possible. Extract complex sub-routines into helper functions.
- **Explicit Return Types:** Always annotate return types (e.g., `-> QueryResponse:`, `-> Dict[str, Any]:`).
- **Defensive Variable Scoping:** Avoid variable name collisions and shadowing. Never reuse variable names for different types within the same function scope (e.g., do not name a string-list `tokens` and later an integer token count `tokens`).

---

## 6. Error Handling & Resilience

- **Fail-Safe Fallbacks:** When interacting with external or compute-heavy processes (like PyTorch neural inference), wrap execution in try-except blocks and fall back gracefully to deterministic logic.
- **Never Swallow Errors Silently:** Always log the exception with descriptive context and stack trace via `logger.error(...)`.
- **Informative HTTP Status Codes:**
  - `400 Bad Request` for invalid user input or missing parameters.
  - `404 Not Found` when a requested log file or resource does not exist.
  - `422 Unprocessable Entity` for Pydantic schema validation failures.
  - `500 Internal Server Error` with a unique request ID returned to the client.

---

## 7. Comments & Documentation

- **Docstrings:** Provide concise docstrings for all classes and public module functions.
- **Explain "Why", Not "What":** Avoid obvious comments that merely repeat code syntax. Explain architectural tradeoffs, edge-case handling, or regex intent.
- **Example:**
  ```python
  # Good: Explains the reason for refusal interception
  # Small language models can occasionally produce generic refusals on complex multi-turn prompts.
  # Intercept cop-out phrases and substitute deterministic SQLite evidence.
  if llm_answer and any(p in llm_answer.lower() for p in refusal_phrases):
      logger.warning("Refusal detected. Elevating to dynamic diagnostic ground-truth.")
      llm_answer = None
  ```

---

## 8. Logging Standards

- Use the centralized logger from `app.logger` (`from app.logger import logger`).
- Never use raw `print()` for backend operational logging (use `logger.info()`, `logger.warning()`, `logger.error()`).
- High-visibility terminal execution banners (such as benchmark timing blocks) are reserved for CLI tools and final query completion summaries.
- Structured log format: `[YYYY-MM-DD HH:MM:SS] [LEVEL] [module:function:line] - Message`

---

## 9. Formatting & Linters

- **Python Formatter:** Black / Ruff (line length: 120 characters).
- **Type Checking:** Pyright / Mypy in strict mode. All arguments, returns, and variables must be cleanly typed without unresolved unions.
- **JavaScript Formatter:** Prettier (2 spaces indentation, semicolons enabled).

---

## 10. Do's and Don'ts

### DO:
- ✅ Keep all branding and thresholds in `.env`.
- ✅ Test all changes with `python -m py_compile backend/app/<file>.py`.
- ✅ Use parameterized SQL queries (`?`) for all SQLite database interactions.
- ✅ Bundle third-party frontend dependencies locally in `frontend/js/vendor/`.
- ✅ Update the relevant `.md` files in `KT_Documentation/` whenever architecture or API contracts change.

### DON'T:
- ❌ Do not hardcode service names, company names, or colors in Python or JS files.
- ❌ Do not make outbound network requests for third-party AI APIs during query processing.
- ❌ Do not commit `.env`, `logs.db`, or raw cache folders.
- ❌ Do not use unvalidated raw user strings in file paths or SQL queries.
- ❌ Do not introduce heavyweight Node.js / NPM build requirements for the frontend.

