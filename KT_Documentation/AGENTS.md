# AI Coding Agent Instructions & Operational Guidelines

## 1. Project Context

- **Project:** ServiceLog Intelligence Hub (Universal Enterprise Edition)
- **Purpose:** Provide an offline-first, ultra-generic, high-performance operational log monitoring, root cause analysis (RCA), and natural language query intelligence platform.
- **Primary Users:** Site Reliability Engineers (SREs), DevOps Engineers, and Software Developers.
- **Core Technology:** Python 3.10+, FastAPI, SQLite with FTS5, PyTorch, Hugging Face Transformers (`Qwen/Qwen2.5-3B-Instruct`), Vanilla HTML5/CSS/JavaScript.

---

## 2. Source of Truth Documentation

Before making significant modifications to any subsystem, read the relevant documentation inside `KT_Documentation/`:

| Document | Primary Focus |
| :--- | :--- |
| **`PRD.md`** | Core problem, product goals, target personas, feature scope, and acceptance criteria. |
| **`DESIGN_SYSTEM.md`** | Color tokens, typography, component states, spacing scale, and responsive layout rules. |
| **`ARCHITECTURE.md`** | System topology, modular monolith structure, data flows, and technical decisions. |
| **`DATABASE.md`** | SQLite schemas, FTS5 virtual tables, triggers, indexes, and normalization rules. |
| **`SECURITY.md`** | Zero-hardcoding rules, input validation, SQL injection prevention, and offline data privacy. |
| **`CODE_STYLE.md`** | Python and JavaScript naming conventions, import ordering, and error-handling patterns. |
| **`TESTING.md`** | Latency benchmarking, critical user flow tests, compilation checks, and QA commands. |
| **`UX_FLOWS.md`** | Step-by-step user journeys from dashboard initialization to forensic query inspection. |
| **`API.md`** | REST API endpoint contracts, query parameters, request/response JSON payloads. |

> **Directive:** Do not contradict these documents without explicitly identifying the conflict and securing clarification.

---

## 3. General Behavioral Rules

1. **Zero-Hardcoding Absolute Rule:** Never hardcode application names, company branding, service names, SLA percentages, or model names into Python or JavaScript source files. Everything must be sourced dynamically from `.env` or inferred from database records.
2. **Understand Before Modifying:** Thoroughly inspect existing code, call paths, and data models before attempting edits. Do not assume or guess how a feature works.
3. **Preserve Working Functionality:** Under no circumstances should existing, validated functionality be broken or degraded. When adding a new capability, integrate it smoothly into the established architecture.
4. **Offline First & Zero Cloud Egress:** Do not add external cloud AI APIs, remote telemetry SDKs, or cloud storage calls. All inference and analytics must run 100% locally.
5. **No Heavy Frontend Bundlers:** Keep frontend assets purely vanilla ES6 JavaScript and CSS. Do not introduce npm, webpack, vite, or complex framework wrappers.
6. **Defensive Variable Scoping:** Avoid variable name collisions and shadowing. Ensure all variables referenced in return statements or conditional formatting are initialized across all code paths.

---

## 4. Planning Protocol

Before executing any non-trivial task:
1. **Inspect Documentation:** Read the relevant specifications in `KT_Documentation/`.
2. **Inspect Existing Code:** Search and review existing implementations in `backend/app/` or `frontend/`.
3. **Identify Affected Files:** Map out precisely which files require additions or modifications.
4. **Evaluate Side Effects:** Verify that changes do not violate Pydantic schemas, database trigger logic, or frontend DOM bindings.
5. **Draft a Concise Plan:** Formulate a step-by-step plan before making edits.

---

## 5. Implementation Protocol

- **Focused, Surgical Edits:** Make concise, targeted changes rather than wholesale file rewrites.
- **Reuse Existing Patterns:** Follow existing patterns in `db.py`, `analyzer.py`, `query_engine.py`, and `app.js`.
- **Maintain Documentation Integrity:** Preserve all existing comments and docstrings unless they become factually obsolete.
- **Type Safety:** Always provide explicit type annotations (`Optional[str]`, `List[Dict[str, Any]]`) for function parameters and returns.

---

## 6. Validation Protocol

After modifying any file, execute the following verification steps:
1. **Compilation Check:**
   ```powershell
   python -m py_compile backend/app/<modified_file>.py
   ```
2. **Static Type Verification:** Ensure no uninitialized variables or type assignment warnings are reported.
3. **Runtime Import Verification:**
   Verify that modules import cleanly in Python without initialization crashes:
   ```powershell
   python -c "import sys; sys.path.insert(0, 'backend'); from app.query_engine import query_engine; print('Verified!')"
   ```
4. **Benchmark Verification:** When modifying the query pipeline, run `python backend/calculate_response_time.py` to ensure latency metrics remain within bounds.

---

## 7. Documentation Updates

Whenever an implementation change alters:
- An API endpoint contract or schema -> Update `KT_Documentation/API.md`.
- Database schema, table, or index -> Update `KT_Documentation/DATABASE.md`.
- A user-facing screen or interaction -> Update `KT_Documentation/UX_FLOWS.md` and `PRD.md`.
- Coding standards or dependencies -> Update `KT_Documentation/CODE_STYLE.md` and `ARCHITECTURE.md`.

---

## 8. Conflict Handling

If a prompt or user request conflicts with the core architecture, security guidelines, or existing functionality:
- **Do not guess or silently ignore the conflict.**
- Formulate the conflict clearly, present the tradeoffs, and ask for explicit direction.

---

## 9. Completion Criteria

A task is complete only when:
- [x] All requirements in the prompt are satisfied.
- [x] Python code compiles without warnings (`py_compile` succeeds).
- [x] No unrelated files or directories were modified or deleted.
- [x] Zero hardcoding was introduced.
- [x] Documentation in `KT_Documentation/` remains accurate and synchronized.

