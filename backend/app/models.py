from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class LogEntry(BaseModel):
    id: int
    file_name: str
    timestamp: str
    date: str
    time: str
    level: str
    component: str
    message: str
    service: str
    url: Optional[str] = ""
    action: Optional[str] = ""
    stack_trace: Optional[str] = None
    line_number: int
    transaction_id: Optional[str] = None
    status: Optional[str] = None
    batch_date: Optional[str] = None

class ErrorCauseSummary(BaseModel):
    cause_id: str
    title: str
    error_type: str
    service: str
    count: int
    affected_transactions: List[str] = []
    description: str
    root_cause: str
    recommendation: str
    sample_stack_trace: Optional[str] = None

class ServiceSummary(BaseModel):
    name: str
    file_name: str
    status: str  # "OPTIMAL", "HEALTHY", "WARNING", "CRITICAL_BREAK"
    last_run: str
    total_lines: int
    records_processed: int
    successful_records: int
    failed_records: int
    errors_count: int
    warnings_count: int
    output_files: List[str] = []
    key_notes: List[str] = []

class OverviewMetrics(BaseModel):
    total_log_files: int
    total_log_lines: int
    total_records_processed: int
    successful_records: int
    failed_records: int
    success_rate_percent: float
    total_error_logs: int
    service_breaks_count: int
    services_count: int
    dates_available: List[str]
    latest_log_date: str
    current_system_date: str

class QueryRequest(BaseModel):
    query: str
    service: Optional[str] = None

class QueryResponse(BaseModel):
    query: str
    answer: str
    category: str
    metrics: Optional[Dict[str, Any]] = None
    service: Optional[str] = None
    evidence: List[Dict[str, Any]] = []
    suggested_queries: List[str] = []
    duration_ms: float = 0.0
    duration_s: float = 0.0
    ttft_s: Optional[float] = None
    generation_time_s: Optional[float] = None
    tokens_per_sec: Optional[float] = None
    tokens_count: Optional[int] = None

class LogsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    logs: List[LogEntry]

class AISettingsRequest(BaseModel):
    api_key: Optional[str] = ""
    model: Optional[str] = "Qwen/Qwen2.5-3B-Instruct"
    provider: Optional[str] = "qwen"
    endpoint_url: Optional[str] = "local-in-memory"

class AISettingsResponse(BaseModel):
    is_configured: bool
    model: str
    masked_key: str
    provider: Optional[str] = "qwen"
    endpoint_url: Optional[str] = "local-in-memory"
    message: str
