#!/usr/bin/env python3
"""
ServiceLog Intelligence Hub Launcher
Run this script to launch the FastAPI server and open the web dashboard.
Auto-detects and runs in the local .venv virtual environment.
"""
import sys
import os
import subprocess
import webbrowser
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"

# If running outside .venv on Windows and .venv exists, re-exec inside .venv
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    print(f"[Launcher] Switching interpreter to virtual environment: {VENV_PYTHON}")
    res = subprocess.call([str(VENV_PYTHON)] + sys.argv)
    sys.exit(res)

BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
APP_NAME = os.getenv("APP_NAME", "ServiceLog Intelligence Hub")

try:
    import uvicorn
    import fastapi
except ImportError:
    print("[Launcher] Dependencies missing. Installing from backend/requirements.txt...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(BACKEND_DIR / "requirements.txt")])
    import uvicorn

def open_browser():
    """
    Waits until the FastAPI backend has fully completed its startup lifecycle
    (log scanning, SQLite indexing, and local Qwen model warmup),
    confirming http://{HOST}:{PORT}/api/health returns 200 OK before
    launching the browser. This guarantees the web page only opens when all
    telemetry and charts are 100% ready.
    """
    url = f"http://{HOST}:{PORT}"
    health_url = f"{url}/api/health"
    print(f"\n[Launcher] Backend initialization in progress for {APP_NAME}...")
    print("[Launcher] Waiting for application startup to complete before opening browser...")
    
    start_time = time.time()
    max_wait_seconds = 45.0
    is_ready = False
    
    import urllib.request
    
    while time.time() - start_time < max_wait_seconds:
        try:
            req = urllib.request.Request(
                health_url,
                headers={"User-Agent": "ServiceLogHub-Launcher/1.0"}
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    is_ready = True
                    break
        except Exception:
            time.sleep(0.4)
            
    if is_ready:
        elapsed = round(time.time() - start_time, 2)
        print(f"\n[+] Backend startup sequence complete in {elapsed}s! Opening ServiceLog Intelligence Hub at: {url}\n")
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"[!] Could not open browser automatically: {e}")
    else:
        print(f"\n[!] Backend took longer than {max_wait_seconds}s to initialize. Visit {url} in your browser.\n")

if __name__ == "__main__":
    print("=" * 75)
    print(f"  {APP_NAME} & Observability Backend")
    print(f"  Python: {sys.executable}")
    print(f"  Live UI: http://{HOST}:{PORT}")
    print(f"  Backend Execution Logs: logs/backend.log")
    print("=" * 75)

    # Launch browser in background daemon thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Run Uvicorn server with auto-reload enabled
    uvicorn.run(
        "app.main:app",
        app_dir=str(BACKEND_DIR),
        host=HOST,
        port=PORT,
        reload=DEBUG,
        reload_dirs=[str(BACKEND_DIR)],
        log_level="info"
    )
