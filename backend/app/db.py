import re
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from app.logger import logger
from app.models import LogEntry
from app.config import DATA_DIR

# Database file location dynamically resolved from DATA_DIR in .env
DB_DIR = DATA_DIR
DB_PATH = DB_DIR / "logs.db"

def get_db_path() -> Path:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def init_db():
    """Initializes the SQLite schema with indexed columns and FTS5 full-text search."""
    conn = get_connection()
    try:
        with conn:
            conn.executescript("""
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

            CREATE INDEX IF NOT EXISTS idx_service_date ON service_logs(service, batch_date);
            CREATE INDEX IF NOT EXISTS idx_level ON service_logs(level);
            CREATE INDEX IF NOT EXISTS idx_status ON service_logs(status);
            CREATE INDEX IF NOT EXISTS idx_batch_date ON service_logs(batch_date);
            CREATE INDEX IF NOT EXISTS idx_file_name ON service_logs(file_name);
            CREATE INDEX IF NOT EXISTS idx_tx_id ON service_logs(transaction_id);
            CREATE INDEX IF NOT EXISTS idx_file_line ON service_logs(file_name, line_number);
            CREATE INDEX IF NOT EXISTS idx_timestamp ON service_logs(timestamp);

            -- Scalable Ingestion Tracker for multi-GB log streaming
            CREATE TABLE IF NOT EXISTS ingestion_state (
                file_name TEXT PRIMARY KEY,
                file_size INTEGER NOT NULL,
                last_mtime REAL NOT NULL,
                last_line_number INTEGER NOT NULL,
                total_entries_indexed INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            -- Pre-aggregated Error Signatures Table for instant sub-millisecond retrieval
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

            -- FTS5 Virtual Table for full-text and semantic keyword log search
            CREATE VIRTUAL TABLE IF NOT EXISTS service_logs_fts USING fts5(
                message,
                stack_trace,
                component,
                service,
                transaction_id,
                content='service_logs',
                content_rowid='id'
            );

            -- Keep FTS5 table in sync with service_logs
            CREATE TRIGGER IF NOT EXISTS trg_service_logs_ai AFTER INSERT ON service_logs BEGIN
                INSERT INTO service_logs_fts(rowid, message, stack_trace, component, service, transaction_id)
                VALUES (new.id, new.message, new.stack_trace, new.component, new.service, new.transaction_id);
            END;

            CREATE TRIGGER IF NOT EXISTS trg_service_logs_ad AFTER DELETE ON service_logs BEGIN
                INSERT INTO service_logs_fts(service_logs_fts, rowid, message, stack_trace, component, service, transaction_id)
                VALUES ('delete', old.id, old.message, old.stack_trace, old.component, old.service, old.transaction_id);
            END;

            CREATE TRIGGER IF NOT EXISTS trg_service_logs_au AFTER UPDATE ON service_logs BEGIN
                INSERT INTO service_logs_fts(service_logs_fts, rowid, message, stack_trace, component, service, transaction_id)
                VALUES ('delete', old.id, old.message, old.stack_trace, old.component, old.service, old.transaction_id);
                INSERT INTO service_logs_fts(rowid, message, stack_trace, component, service, transaction_id)
                VALUES (new.id, new.message, new.stack_trace, new.component, new.service, new.transaction_id);
            END;
            """)
        logger.info(f"[SQLITE-INIT] Database initialized successfully at: {DB_PATH}")
    finally:
        conn.close()

def extract_metadata(entry: LogEntry) -> Tuple[Optional[str], str]:
    """Extracts transaction_id and normalized status from entry content across any domain."""
    msg = entry.message or ""
    msg_lower = msg.lower()

    # 1. Extract transaction id or entity identifier (universal pattern across any domain)
    tx_match = re.search(
        r'(?:TransactionId|Transaction Id|txId|tx_id|PaymentId|RecordId|OrderId|'
        r'InvoiceId|RequestId|ReqId|TraceId|Trace_Id|SessionId|CorrelationId|JobId|'
        r'BatchId|CustomerId|UserId|EventId|MessageId)\s*[:=]\s*([A-Za-z0-9_-]+)',
        msg,
        re.I
    )
    tx_id = tx_match.group(1).strip() if tx_match else None

    # 2. Extract operational status dynamically
    is_err_level = entry.level.upper() in ["ERROR", "FATAL", "CRITICAL"]
    if is_err_level or "system.exception" in msg_lower or "unhandled" in msg_lower:
        if (
            "unhandled" in msg_lower
            or "fatal" in msg_lower
            or "panic" in msg_lower
            or "critical" in msg_lower
            or "service break" in msg_lower
            or "halt" in msg_lower
            or "aborted" in msg_lower
            or "terminated" in msg_lower
            or "crash" in msg_lower
            or "system.exception" in msg_lower
        ):
            status = "SERVICE_BREAK"
        else:
            status = "ERROR"
    elif (
        "failed" in msg_lower
        or "failure" in msg_lower
        or "rejected" in msg_lower
        or "error during execution" in msg_lower
    ):
        status = "FAILED"
    elif (
        re.search(
            r'(?:record(?:s)?\s+(?:inserted|added|created|processed|written|exported)|'
            r'added\s+in\s+database|writing\s+operation|approved|completed|'
            r'uploaded\s+successfully|processed\s+successfully|status\s*:\s*(?:success|ok|200))',
            msg_lower
        )
    ):
        status = "SUCCESS"
    else:
        status = "PROCESSED" if entry.level == "INFO" else entry.level

    return tx_id, status

def sync_logs_to_db(entries: List[LogEntry], force: bool = False) -> int:
    """
    Synchronizes parsed log entries into SQLite service_logs and service_logs_fts.
    Uses fast bulk insertion inside a single transaction.
    """
    init_db()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM service_logs;")
        current_count = cur.fetchone()[0]

        if not force and current_count == len(entries) and len(entries) > 0:
            logger.debug(f"[SQLITE-SYNC] Database already up to date with {current_count} entries.")
            return current_count

        start_time = time.time()
        logger.info(f"[SQLITE-SYNC-START] Synchronizing {len(entries)} parsed entries into SQLite database...")

        rows = []
        for e in entries:
            tx_id, status = extract_metadata(e)
            rows.append((
                e.id,
                e.file_name,
                e.timestamp,
                e.date,
                e.time,
                e.level,
                e.component,
                e.message,
                e.service,
                e.url or "",
                e.action or "",
                e.stack_trace,
                e.line_number,
                tx_id,
                status,
                e.date
            ))

        with conn:
            # Clear existing data to rebuild cleanly
            conn.execute("DELETE FROM service_logs;")
            conn.execute("DELETE FROM service_logs_fts;")
            conn.executemany(
                """
                INSERT INTO service_logs (
                    id, file_name, timestamp, date, time, level, component,
                    message, service, url, action, stack_trace, line_number,
                    transaction_id, status, batch_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                rows
            )

        duration_ms = (time.time() - start_time) * 1000.0
        logger.info(f"[SQLITE-SYNC-COMPLETE] Successfully committed {len(rows)} entries in {duration_ms:.2f}ms.")
        return len(rows)
    finally:
        conn.close()

def query_logs_from_db(
    service: Optional[str] = None,
    level: Optional[str] = None,
    date: Optional[str] = None,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 50
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Executes an optimized, indexed query against SQLite database with pagination and full-text search.
    """
    init_db()
    conn = get_connection()
    try:
        cur = conn.cursor()
        where_clauses: List[str] = []
        params: List[Any] = []

        # 1. Service filter
        if service and service.lower() != "all":
            where_clauses.append("LOWER(service) = LOWER(?)")
            params.append(service)

        # 2. Log level filter
        if level and level.upper() != "ALL":
            where_clauses.append("UPPER(level) = UPPER(?)")
            params.append(level)

        # 3. Date / batch_date filter
        if date and date.lower() != "all":
            where_clauses.append("date = ?")
            params.append(date)

        # 4. Status filter (Ultra-generic, domain-agnostic)
        if status_filter and status_filter.lower() != "all":
            sf = status_filter.lower()
            if sf in ["errors", "fail", "failed", "error"]:
                where_clauses.append(
                    "(level IN ('ERROR', 'FATAL', 'CRITICAL') OR status IN ('ERROR', 'FAILED', 'SERVICE_BREAK') "
                    "OR LOWER(message) LIKE '%fail%' OR LOWER(message) LIKE '%reject%' OR LOWER(message) LIKE '%unhandled%')"
                )
            elif sf in ["breaks", "service_breaks", "break", "halt"]:
                where_clauses.append(
                    "(status = 'SERVICE_BREAK' OR (level IN ('ERROR', 'FATAL', 'CRITICAL') AND ("
                    "LOWER(message) LIKE '%exception%' OR LOWER(message) LIKE '%unhandled%' "
                    "OR LOWER(message) LIKE '%fatal%' OR LOWER(message) LIKE '%panic%' "
                    "OR LOWER(message) LIKE '%abort%' OR LOWER(message) LIKE '%halt%' "
                    "OR LOWER(message) LIKE '%not found%')))"
                )
            elif sf in ["success", "successful"]:
                where_clauses.append(
                    "(status = 'SUCCESS' OR LOWER(message) LIKE '%success%' "
                    "OR LOWER(message) LIKE '%completed%' OR LOWER(message) LIKE '%approved%' "
                    "OR LOWER(message) LIKE '%inserted%' OR LOWER(message) LIKE '%created%' "
                    "OR LOWER(message) LIKE '%writing operation%')"
                )
            elif sf in ["processed"]:
                where_clauses.append(
                    "(status IN ('SUCCESS', 'PROCESSED', 'FAILED', 'ERROR', 'SERVICE_BREAK') "
                    "OR level IN ('INFO', 'WARN', 'WARNING', 'ERROR', 'FATAL', 'CRITICAL') "
                    "OR LOWER(message) LIKE '%success%' OR LOWER(message) LIKE '%fail%')"
                )

        # 5. Search filter (FTS5 + Substring Fallback)
        if search and search.strip():
            clean_search = search.strip()
            like_term = f"%{clean_search.lower()}%"
            safe_tokens = [re.sub(r'[^a-zA-Z0-9_]', '', t) for t in clean_search.split()]
            safe_tokens = [t for t in safe_tokens if t]
            if safe_tokens:
                fts_expr = " AND ".join(f'"{t}"*' for t in safe_tokens)
                where_clauses.append(
                    "(id IN (SELECT rowid FROM service_logs_fts WHERE service_logs_fts MATCH ?) "
                    "OR LOWER(message) LIKE ? OR LOWER(component) LIKE ? OR LOWER(file_name) LIKE ?)"
                )
                params.extend([fts_expr, like_term, like_term, like_term])
            else:
                where_clauses.append(
                    "(LOWER(message) LIKE ? OR LOWER(component) LIKE ? OR LOWER(file_name) LIKE ?)"
                )
                params.extend([like_term, like_term, like_term])

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Count total matching rows
        count_sql = f"SELECT COUNT(*) FROM service_logs {where_sql};"
        cur.execute(count_sql, params)
        total = cur.fetchone()[0]

        # Paged rows
        offset = max(0, (page - 1) * page_size)
        query_sql = f"""
            SELECT id, file_name, timestamp, date, time, level, component,
                   message, service, url, action, stack_trace, line_number,
                   transaction_id, status, batch_date
            FROM service_logs
            {where_sql}
            ORDER BY id ASC
            LIMIT ? OFFSET ?;
        """
        cur.execute(query_sql, params + [page_size, offset])
        rows = [dict(r) for r in cur.fetchall()]

        return total, rows
    finally:
        conn.close()

def get_latest_error_logs(service: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Retrieves the most recent ERROR logs with full timestamp and trace details."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if service and service.lower() != "all":
            cur.execute("""
                SELECT id, file_name, timestamp, date, time, level, component,
                       message, service, stack_trace, line_number, transaction_id
                FROM service_logs
                WHERE level = 'ERROR' AND LOWER(service) = LOWER(?)
                ORDER BY timestamp DESC, id DESC
                LIMIT ?;
            """, (service, limit))
        else:
            cur.execute("""
                SELECT id, file_name, timestamp, date, time, level, component,
                       message, service, stack_trace, line_number, transaction_id
                FROM service_logs
                WHERE level = 'ERROR'
                ORDER BY timestamp DESC, id DESC
                LIMIT ?;
            """, (limit,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def get_service_break_flow(service: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Reconstructs the exact execution flow leading up to the critical service break.
    Pulls the break entry and the preceding sequence of logs in the same execution batch.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        svc_filter = "AND LOWER(service) = LOWER(?)" if (service and service.lower() != "all") else ""
        params: List[Any] = [service] if (service and service.lower() != "all") else []

        cur.execute(f"""
            SELECT id, file_name, timestamp, date, time, level, component,
                   message, service, stack_trace, line_number, transaction_id
            FROM service_logs
            WHERE (status = 'SERVICE_BREAK'
               OR (level = 'ERROR' AND (
                   LOWER(message) LIKE '%exception%'
                   OR LOWER(message) LIKE '%fatal%'
                   OR LOWER(message) LIKE '%unhandled%'
                   OR LOWER(message) LIKE '%panic%'
                   OR LOWER(message) LIKE '%critical%'
                   OR LOWER(message) LIKE '%halt%'
               )))
               {svc_filter}
            ORDER BY id ASC
            LIMIT 1;
        """, params)
        break_row = cur.fetchone()
        if not break_row:
            return None

        break_dict = dict(break_row)
        break_id = break_dict["id"]
        file_name = break_dict["file_name"]

        # Retrieve the 4 preceding log lines within the same file to show the flow leading to the break
        cur.execute("""
            SELECT id, time, level, component, message, transaction_id
            FROM service_logs
            WHERE file_name = ? AND id < ?
            ORDER BY id DESC
            LIMIT 4;
        """, (file_name, break_id))
        preceding = [dict(r) for r in reversed(cur.fetchall())]

        return {
            "break_entry": break_dict,
            "preceding_flow": preceding
        }
    finally:
        conn.close()

def search_logs_dynamic(query_text: str, service: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Dynamically finds ground-truth log entries matching user terms or transaction IDs.
    Combines FTS5 full-text matching with substring fallback.
    """
    if not query_text or not query_text.strip():
        return []

    conn = get_connection()
    try:
        cur = conn.cursor()
        clean = query_text.strip()
        tokens = [re.sub(r'[^a-zA-Z0-9_]', '', t) for t in clean.split() if len(t) > 2]
        
        where_clauses = []
        params: List[Any] = []

        if service and service.lower() != "all":
            where_clauses.append("LOWER(service) = LOWER(?)")
            params.append(service)

        # Detect transaction IDs (alphanumeric or hex)
        tx_match = re.search(r'\b[A-Za-z0-9_-]{10,}\b', clean)
        if tx_match:
            tx_id = tx_match.group(0)
            where_clauses.append("(transaction_id = ? OR message LIKE ?)")
            params.extend([tx_id, f"%{tx_id}%"])
        elif tokens:
            fts_expr = " OR ".join(f'"{t}"*' for t in tokens[:4])
            where_clauses.append(
                "(id IN (SELECT rowid FROM service_logs_fts WHERE service_logs_fts MATCH ?) "
                "OR LOWER(message) LIKE ?)"
            )
            params.extend([fts_expr, f"%{clean.lower()}%"])
        else:
            where_clauses.append("LOWER(message) LIKE ?")
            params.append(f"%{clean.lower()}%")

        where_sql = "WHERE " + " AND ".join(where_clauses)
        sql = f"""
            SELECT id, file_name, timestamp, date, time, level, component,
                   message, service, stack_trace, line_number, transaction_id
            FROM service_logs
            {where_sql}
            ORDER BY id ASC
            LIMIT ?;
        """
        cur.execute(sql, params + [limit])
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def get_log_counts_summary(service: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves quick aggregate counts from SQLite for instant response."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        svc_filter = "WHERE LOWER(service) = LOWER(?)" if (service and service.lower() != "all") else ""
        svc_param = [service] if (service and service.lower() != "all") else []

        cur.execute(f"SELECT COUNT(*) FROM service_logs {svc_filter};", svc_param)
        total_logs = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM service_logs {'WHERE ' if not svc_filter else svc_filter + ' AND '} level = 'ERROR';", svc_param)
        error_logs = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM service_logs {'WHERE ' if not svc_filter else svc_filter + ' AND '} level = 'INFO';", svc_param)
        info_logs = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM service_logs {'WHERE ' if not svc_filter else svc_filter + ' AND '} (status = 'SERVICE_BREAK' OR (level = 'ERROR' AND LOWER(message) LIKE '%system.exception%'));", svc_param)
        breaks = cur.fetchone()[0]

        return {
            "total_logs": total_logs,
            "error_logs": error_logs,
            "info_logs": info_logs,
            "service_breaks": breaks
        }
    finally:
        conn.close()

def get_log_line_with_context(file_name_or_keyword: str, line_number: int, context_lines: int = 4) -> Dict[str, Any]:
    """
    Retrieves the exact target log entry at a specific line number plus surrounding lines (context).
    Enables deep line-by-line inspection even across multi-GB files.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, file_name, timestamp, date, time, level, component,
                   message, service, stack_trace, line_number, transaction_id
            FROM service_logs
            WHERE (LOWER(file_name) LIKE ? OR LOWER(service) LIKE ?) AND line_number = ?
            LIMIT 1;
        """, (f"%{file_name_or_keyword.lower()}%", f"%{file_name_or_keyword.lower()}%", line_number))
        target_row = cur.fetchone()
        if not target_row:
            cur.execute("""
                SELECT id, file_name, timestamp, date, time, level, component,
                       message, service, stack_trace, line_number, transaction_id
                FROM service_logs
                WHERE (LOWER(file_name) LIKE ? OR LOWER(service) LIKE ?)
                ORDER BY ABS(line_number - ?) ASC
                LIMIT 1;
            """, (f"%{file_name_or_keyword.lower()}%", f"%{file_name_or_keyword.lower()}%", line_number))
            target_row = cur.fetchone()
            if not target_row:
                return {"target": None, "preceding": [], "succeeding": []}

        target = dict(target_row)
        target_id = target["id"]
        fname = target["file_name"]

        cur.execute("""
            SELECT id, time, level, component, message, line_number, transaction_id
            FROM service_logs
            WHERE file_name = ? AND id < ?
            ORDER BY id DESC
            LIMIT ?;
        """, (fname, target_id, context_lines))
        preceding = [dict(r) for r in reversed(cur.fetchall())]

        cur.execute("""
            SELECT id, time, level, component, message, line_number, transaction_id
            FROM service_logs
            WHERE file_name = ? AND id > ?
            ORDER BY id ASC
            LIMIT ?;
        """, (fname, target_id, context_lines))
        succeeding = [dict(r) for r in cur.fetchall()]

        return {
            "target": target,
            "preceding": preceding,
            "succeeding": succeeding
        }
    finally:
        conn.close()

def get_transaction_lifecycle(transaction_id: str) -> List[Dict[str, Any]]:
    """
    Reconstructs the complete end-to-end lifecycle of a transaction across all services line-by-line.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        clean_id = transaction_id.strip()
        cur.execute("""
            SELECT id, file_name, timestamp, date, time, level, component,
                   message, service, stack_trace, line_number, transaction_id, status
            FROM service_logs
            WHERE transaction_id = ? OR message LIKE ?
            ORDER BY timestamp ASC, id ASC;
        """, (clean_id, f"%{clean_id}%"))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def get_time_window_logs(start_time: str, end_time: str, service: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Retrieves chronological log entries within a specific timestamp or time range.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        where_clauses = ["(time BETWEEN ? AND ? OR timestamp BETWEEN ? AND ?)"]
        params = [start_time, end_time, start_time, end_time]

        if service and service.lower() != "all":
            where_clauses.append("LOWER(service) = LOWER(?)")
            params.append(service)

        where_sql = "WHERE " + " AND ".join(where_clauses)
        cur.execute(f"""
            SELECT id, file_name, timestamp, date, time, level, component,
                   message, service, line_number, transaction_id, status
            FROM service_logs
            {where_sql}
            ORDER BY timestamp ASC, id ASC
            LIMIT ?;
        """, params + [limit])
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def get_error_signatures_summary(service: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Aggregates distinct error signatures across the logs with counts, sample traces, and lines.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        svc_clause = "AND LOWER(service) = LOWER(?)" if (service and service.lower() != "all") else ""
        svc_params = [service] if (service and service.lower() != "all") else []

        cur.execute(f"""
            SELECT service, component,
                   CASE 
                       WHEN LOWER(message) LIKE '%format%exception%' THEN 'FormatException'
                       WHEN LOWER(message) LIKE '%nullreference%' THEN 'NullReferenceException'
                       WHEN LOWER(message) LIKE '%notfound%' OR LOWER(message) LIKE '%not found%' THEN 'NotFoundException'
                       WHEN LOWER(message) LIKE '%timeout%' THEN 'TimeoutException'
                       WHEN LOWER(message) LIKE '%unauthorized%' OR LOWER(message) LIKE '%forbidden%' THEN 'AuthException'
                       WHEN LOWER(message) LIKE '%connection%' OR LOWER(message) LIKE '%network%' THEN 'NetworkException'
                       WHEN LOWER(message) LIKE '%system.exception%' OR LOWER(message) LIKE '%exception%' THEN 'SystemException'
                       WHEN LOWER(message) LIKE '%fatal%' OR LOWER(message) LIKE '%panic%' THEN 'FatalError'
                       ELSE 'RuntimeError'
                   END as error_type,
                   COUNT(*) as occurrence_count,
                   MIN(timestamp) as first_seen,
                   MAX(timestamp) as last_seen,
                   MIN(line_number) as sample_line,
                   file_name,
                   SUBSTR(message, 1, 180) as sample_message
            FROM service_logs
            WHERE level = 'ERROR' {svc_clause}
            GROUP BY service, component, error_type
            ORDER BY occurrence_count DESC;
        """, svc_params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def get_component_breakdown(service: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns an operational breakdown of activity and error rates per application component.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        svc_clause = "WHERE LOWER(service) = LOWER(?)" if (service and service.lower() != "all") else ""
        svc_params = [service] if (service and service.lower() != "all") else []

        cur.execute(f"""
            SELECT component, service,
                   COUNT(*) as total_events,
                   SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) as error_events,
                   SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_events,
                   ROUND(SUM(CASE WHEN level = 'ERROR' THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100, 2) as error_rate_pct
            FROM service_logs
            {svc_clause}
            GROUP BY component, service
            ORDER BY total_events DESC
            LIMIT 15;
        """, svc_params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
