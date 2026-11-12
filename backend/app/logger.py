import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.config import BASE_DIR

# Dedicated directory for backend internal execution logs
SYSTEM_LOGS_DIR = BASE_DIR / "logs"
SYSTEM_LOGS_DIR.mkdir(parents=True, exist_ok=True)

BACKEND_LOG_FILE = SYSTEM_LOGS_DIR / "backend.log"

class SafeConsoleStream:
    """Wrapper around stdout to ensure UTF-8 characters do not crash Windows charmap terminals."""
    def __init__(self, stream):
        self.stream = stream

    def write(self, s: str):
        try:
            self.stream.write(s)
        except UnicodeEncodeError:
            self.stream.write(s.encode(getattr(self.stream, "encoding", "utf-8") or "utf-8", errors="backslashreplace").decode("latin-1", errors="replace"))

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass

def setup_logger(name: str = "backend") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Standard clean format
    log_format = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-7s] [%(name)s:%(funcName)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console Handler (Safe UTF-8)
    safe_stdout = SafeConsoleStream(sys.stdout)
    console_handler = logging.StreamHandler(safe_stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # 2. Rotating File Handler (10 MB, 5 backups, UTF-8)
    try:
        file_handler = RotatingFileHandler(
            filename=str(BACKEND_LOG_FILE),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not initialize file logger at {BACKEND_LOG_FILE}: {e}")

    logger.propagate = False
    return logger

logger = setup_logger("backend")

def log_system_startup(host: str, port: int, debug: bool, env_name: str = ".venv"):
    """Logs full backend initialization parameters."""
    logger.info("=" * 80)
    logger.info("ServiceLog Intelligence Hub Backend - STARTUP SEQUENCE")
    logger.info("=" * 80)
    logger.info(f"Python Runtime: {sys.version.split()[0]} ({sys.executable})")
    logger.info(f"Active Virtual Environment: {env_name} (Resolved: {sys.prefix})")
    logger.info(f"Workspace Directory: {BASE_DIR}")
    logger.info(f"Backend Execution Log File: {BACKEND_LOG_FILE}")
    logger.info(f"Server Target: http://{host}:{port} (Debug: {debug})")

def log_llm_call_start(model: str, query: str, context_summary: Dict[str, Any]):
    """Logs the exact LLM request dispatch with payload details."""
    logger.info(f"[LLM-CALL-START] Dispatching query to Local Qwen SLM model '{model}'")
    logger.info(f"[LLM-CALL-START] User Query: \"{query}\"")
    logger.debug(
        f"[LLM-CALL-PAYLOAD] Context Summary: files={context_summary.get('total_files')}, "
        f"records={context_summary.get('total_records')}, "
        f"errors={context_summary.get('total_errors')}, "
        f"causes={context_summary.get('total_causes')}"
    )

def log_llm_call_complete(model: str, latency_ms: float, response_length: int, usage: Optional[Dict[str, Any]] = None):
    """Logs successful LLM completion with latency and token metrics."""
    usage_info = f", tokens={usage}" if usage else ""
    logger.info(
        f"[LLM-CALL-SUCCESS] Completed in {latency_ms:.2f}ms | Model: {model} | "
        f"Response Length: {response_length} chars{usage_info}"
    )

def log_llm_call_error(model: str, latency_ms: float, error_msg: str):
    """Logs LLM failure with full diagnostics."""
    logger.error(
        f"[LLM-CALL-ERROR] Failed after {latency_ms:.2f}ms | Model: {model} | Error: {error_msg}"
    )

def get_recent_backend_logs(max_lines: int = 150) -> List[str]:
    """Returns the most recent lines from backend.log for live inspection."""
    if not BACKEND_LOG_FILE.exists():
        return ["Backend log file not yet created."]
    
    try:
        with open(BACKEND_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return [line.rstrip() for line in lines[-max_lines:]]
    except Exception as e:
        return [f"Error reading backend log file: {e}"]

