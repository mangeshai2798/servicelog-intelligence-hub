import time
import uuid
import shutil
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Query, UploadFile, File, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import (
    STATIC_DIR,
    LOGS_DIR,
    HOST,
    PORT,
    DEBUG,
    APP_NAME,
    APP_TITLE,
    APP_TAGLINE,
    APP_SUBTITLE,
    APP_ORG_NAME,
    APP_NAV_BADGE,
    SLA_TARGET_PERCENT
)
from app.logger import (
    logger,
    log_system_startup,
    get_recent_backend_logs,
    BACKEND_LOG_FILE
)
from app.parser import parser
from app.analyzer import analyzer
from app.query_engine import query_engine
from app.ai_service import ai_service
from app.db import init_db, sync_logs_to_db, query_logs_from_db
from app.models import (
    OverviewMetrics,
    ServiceSummary,
    ErrorCauseSummary,
    QueryRequest,
    QueryResponse,
    LogsResponse,
    LogEntry,
    AISettingsRequest,
    AISettingsResponse
)

# Modern FastAPI Lifespan Handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Lifecycle
    log_system_startup(HOST, PORT, DEBUG)
    logger.info("[STARTUP-SCAN] Performing initial scan and indexing of service logs...")
    entries = parser.parse_all()
    overview = analyzer.get_overview()

    # Initialize SQLite database and sync logs with indexed search
    init_db()
    sync_logs_to_db(entries)

    logger.info(
        f"[STARTUP-INDEX-COMPLETE] Indexed {len(entries):,} log lines across {overview.total_log_files} file(s). "
        f"Total Records: {overview.total_records_processed:,} | Success Rate: {overview.success_rate_percent}%"
    )

    # Pre-warm local Qwen 2.5 3B model
    try:
        from app.ai_service import LocalQwenEngine
        logger.info("[STARTUP-WARMUP] Pre-initializing and warming up Local Qwen 2.5 3B SLM...")
        LocalQwenEngine.get_instance(ai_service.model_name).load_model()
    except Exception as ex:
        logger.warning(f"[STARTUP-WARMUP-FAILED] Qwen warmup error: {ex}")

    yield
    # Shutdown Lifecycle
    logger.info("[SHUTDOWN] ServiceLog Intelligence Hub Backend gracefully shutting down.")

app = FastAPI(
    title="ServiceLog Intelligence Hub API",
    description="Real-time Service Log Monitoring, Automated Root Cause Analysis & Intelligent Q&A",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Granular Request/Response Logging Middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    req_id = str(uuid.uuid4())[:8]
    client_ip = request.client.host if request.client else "unknown"
    start_time = time.time()
    
    # Exclude high-frequency polling from log clutter if desired, but user requested exhaustive logging:
    logger.info(f"[HTTP-REQ] [{req_id}] {request.method} {request.url.path} from {client_ip}")
    if request.query_params:
        logger.debug(f"[HTTP-REQ-PARAMS] [{req_id}] Query: {dict(request.query_params)}")

    try:
        response: Response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000.0
        logger.info(
            f"[HTTP-RES] [{req_id}] {request.method} {request.url.path} -> "
            f"Status {response.status_code} in {duration_ms:.2f}ms"
        )
        response.headers["X-Request-ID"] = req_id
        if request.url.path.startswith("/static") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000.0
        tb = traceback.format_exc()
        logger.error(f"[HTTP-ERR] [{req_id}] Unhandled error after {duration_ms:.2f}ms: {exc}\n{tb}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "request_id": req_id, "error": str(exc)}
        )

# Endpoints
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": "1.0.0",
        "model": ai_service.model_name,
        "provider": ai_service.provider,
        "local_llm_ready": ai_service.is_configured()
    }

@app.get("/api/config")
def get_app_config():
    """Returns dynamic application branding, configuration, and SLA thresholds from .env."""
    return {
        "app_name": APP_NAME,
        "app_title": APP_TITLE,
        "app_tagline": APP_TAGLINE,
        "app_subtitle": APP_SUBTITLE,
        "app_org_name": APP_ORG_NAME,
        "app_nav_badge": APP_NAV_BADGE,
        "sla_target_percent": SLA_TARGET_PERCENT,
        "model_name": ai_service.model_name,
        "provider": ai_service.provider
    }

@app.get("/api/system/logs")
def get_system_logs(lines: int = Query(150, ge=10, le=1000)):
    """Provides real-time access to the backend's internal execution logs."""
    recent_logs = get_recent_backend_logs(max_lines=lines)
    return {
        "log_file": str(BACKEND_LOG_FILE),
        "lines_returned": len(recent_logs),
        "logs": recent_logs
    }

@app.get("/api/overview", response_model=OverviewMetrics)
def get_overview(service: Optional[str] = Query(None)):
    return analyzer.get_overview(service=service)

@app.get("/api/services", response_model=List[ServiceSummary])
def get_services():
    return analyzer.get_services_summary()

@app.get("/api/errors/causes", response_model=List[ErrorCauseSummary])
def get_error_causes(service: Optional[str] = Query(None)):
    return analyzer.get_error_causes(service=service)

@app.get("/api/timeline")
def get_timeline(service: Optional[str] = Query(None)):
    return analyzer.get_timeline(service=service)

@app.get("/api/settings/ai")
def get_ai_settings():
    return ai_service.get_status()

@app.post("/api/settings/ai", response_model=AISettingsResponse)
def update_ai_settings(req: AISettingsRequest):
    status = ai_service.get_status()
    return AISettingsResponse(
        is_configured=True,
        model=status["model"],
        masked_key=status["masked_key"],
        provider="qwen",
        endpoint_url="local-in-memory",
        message="Local Qwen 2.5 3B model is active and running in-memory."
    )

@app.post("/api/query", response_model=QueryResponse)
def handle_query(req: QueryRequest):
    if not req.query.strip():
        logger.warning("[QUERY-API] Rejected empty query request.")
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    return query_engine.answer_query(req.query, service=req.service)

@app.get("/api/logs", response_model=LogsResponse)
def get_logs(
    service: Optional[str] = None,
    level: Optional[str] = None,
    date: Optional[str] = None,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500)
):
    total, rows = query_logs_from_db(
        service=service,
        level=level,
        date=date,
        search=search,
        status_filter=status_filter,
        page=page,
        page_size=page_size
    )
    paged_entries = [LogEntry(**r) for r in rows]

    return LogsResponse(
        total=total,
        page=page,
        page_size=page_size,
        logs=paged_entries
    )

@app.post("/api/reindex")
def reindex_logs():
    logger.info("[REINDEX-API] Manual reindex requested via API.")
    entries = parser.parse_all(force=True)
    sync_logs_to_db(entries, force=True)
    overview = analyzer.get_overview()
    return {
        "status": "success",
        "message": f"Successfully reindexed {len(entries)} log entries across {len(parser.get_log_files())} files.",
        "overview": overview
    }

@app.post("/api/upload")
async def upload_log_file(file: UploadFile = File(...)):
    filename = file.filename
    if not filename or not filename.endswith(".log"):
        logger.warning(f"[UPLOAD-API] Rejected upload of invalid file: '{filename}'")
        raise HTTPException(status_code=400, detail="Only .log files with valid names are supported.")
    
    dest_path = LOGS_DIR / filename
    logger.info(f"[UPLOAD-API] Ingesting new service log file: '{filename}' -> {dest_path}")
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Force reindex and sync to SQLite
    entries = parser.parse_all(force=True)
    sync_logs_to_db(entries, force=True)
    logger.info(f"[UPLOAD-API] Ingestion complete. Database updated to {len(entries)} total entries.")
    return {
        "status": "uploaded",
        "filename": filename,
        "total_entries": len(entries),
        "message": f"File '{filename}' uploaded and parsed successfully."
    }

@app.get("/.well-known/appspecific/{path:path}")
def chrome_devtools_dummy(path: str):
    return Response(status_code=204)

@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)

# Mount static files for frontend
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Frontend index.html not found"}
