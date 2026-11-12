from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

WORKSPACE_DIR = BASE_DIR
LOGS_DIR = Path(os.getenv("LOGS_DIR", "service_logs"))
if not LOGS_DIR.is_absolute():
    LOGS_DIR = BASE_DIR / LOGS_DIR
LOGS_DIR.mkdir(parents=True, exist_ok=True)

STATIC_DIR = BASE_DIR / "frontend"
DATA_DIR = Path(os.getenv("DATA_DIR", "backend/data"))
if not DATA_DIR.is_absolute():
    DATA_DIR = BASE_DIR / DATA_DIR

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# Dynamic Branding & Identity (read from .env)
APP_NAME = os.getenv("APP_NAME", "ServiceLog Intelligence Hub")
APP_TITLE = os.getenv("APP_TITLE", "ServiceLog Intelligence Hub | Enterprise Observability & Root Cause Analysis")
APP_TAGLINE = os.getenv("APP_TAGLINE", "Beyond Observability")
APP_SUBTITLE = os.getenv("APP_SUBTITLE", "Autonomous Log Intelligence, SRE Diagnostic Triage & Multi-Service Monitoring")
APP_ORG_NAME = os.getenv("APP_ORG_NAME", "LogTrax Enterprise")
APP_NAV_BADGE = os.getenv("APP_NAV_BADGE", "Observability Hub")

SLA_TARGET_PERCENT = float(os.getenv("SLA_TARGET_PERCENT", "95.0"))

# Local In-Memory SLM Configuration
DEFAULT_PROVIDER = os.getenv("PROVIDER", "qwen")
DEFAULT_QWEN_MODEL = os.getenv("LOCAL_MODEL", "Qwen/Qwen2.5-3B-Instruct")
MODEL_PATH = os.getenv("MODEL_PATH", "models/Qwen2.5-3B-Instruct")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "220"))
