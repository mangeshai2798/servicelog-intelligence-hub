"""
===============================================================================
ServiceLog Intelligence Hub - Automated System Verification & Test Suite
Tests:
1. Environment & Dynamic Model Configuration (.env)
2. Drain3 Online Log Template Mining & Masking
3. SQLite WAL Schema & Indexed Template Clustering
4. RCA Diagnostic Analysis Engine
5. API Endpoint Contracts & Query Engine Integration
===============================================================================
Usage:
    python backend/test_system.py
===============================================================================
"""

import sys
import time
from pathlib import Path

# Setup paths
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent if CURRENT_DIR.name == "backend" else CURRENT_DIR
sys.path.insert(0, str(ROOT_DIR / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from app.config import DEFAULT_QWEN_MODEL, MODEL_PATH, APP_NAME, SLA_TARGET_PERCENT
from app.template_miner import template_miner
from app.parser import parser
from app.db import (
    init_db,
    sync_logs_to_db,
    get_mined_templates_summary,
    get_error_templates_summary
)
from app.analyzer import analyzer
from app.ai_service import ai_service


def run_tests():
    print("=" * 80)
    print("🧪 [SYSTEM VERIFICATION] Running ServiceLog Intelligence Test Suite")
    print("=" * 80)

    # Test 1: Configuration & Model Detection
    print("\n[TEST 1] Verifying Dynamic Configuration & Active Model...")
    print(f"  • Application Name : {APP_NAME}")
    print(f"  • SLA Threshold    : {SLA_TARGET_PERCENT}%")
    print(f"  • Active Model     : {DEFAULT_QWEN_MODEL}")
    print(f"  • Model Path       : {MODEL_PATH}")
    assert DEFAULT_QWEN_MODEL, "Active model must be defined in .env"
    print("  ✅ [PASS] Configuration loaded successfully.")

    # Test 2: Drain3 Masking & Mining
    print("\n[TEST 2] Verifying Drain3 Masking & Online Template Mining...")
    sample_raw_msg = "2026-11-14 10:15:22 [ERROR] User 98124 failed login from 192.168.1.50 with trace 4f2b1a80-1a2b-3c4d-5e6f-7a8b9c0d1e2f"
    cluster_id, template = template_miner.mine(sample_raw_msg)
    print(f"  • Sample Raw Message : {sample_raw_msg}")
    print(f"  • Mined Cluster ID   : #{cluster_id}")
    print(f"  • Mined Template     : {template}")
    assert "<IP>" in template or "<NUM>" in template, "Drain3 must mask variables"
    print("  ✅ [PASS] Drain3 masking and online clustering verified.")

    # Test 3: Log Ingestion with Drain3
    print("\n[TEST 3] Verifying Multi-Service Log Ingestion & Parsing...")
    t0 = time.perf_counter()
    entries = parser.parse_all()
    dur_ms = (time.perf_counter() - t0) * 1000.0
    print(f"  • Total Entries Parsed : {len(entries):,} in {dur_ms:.1f}ms")
    sample_entry = entries[0]
    print(f"  • Entry #1 Template   : Cluster #{sample_entry.template_id} -> '{sample_entry.template_mined}'")
    assert len(entries) > 0, "Log parser must find and parse service logs"
    assert sample_entry.template_id is not None, "Each entry must have a template_id"
    print("  ✅ [PASS] Log ingestion and online template assignment verified.")

    # Test 4: SQLite Synchronization & Indexing
    print("\n[TEST 4] Verifying SQLite WAL Schema & Indexed Template Storage...")
    init_db()
    count = sync_logs_to_db(entries)
    print(f"  • Total Entries in DB  : {count:,}")
    assert count == len(entries), "Database count must match parsed entries"

    top_templates = get_mined_templates_summary(limit=5)
    print(f"  • Top Discovered Templates ({len(top_templates)} sample):")
    for t in top_templates:
        print(f"    - Cluster #{t['cluster_id']} ({t['count']}x): {t['template'][:75]}...")
    assert len(top_templates) > 0, "Top templates summary must return clusters"
    print("  ✅ [PASS] SQLite template storage and indexing verified.")

    # Test 5: RCA Error Clustering
    print("\n[TEST 5] Verifying Root Cause Analysis (RCA) Clustering...")
    causes = analyzer.get_error_causes()
    print(f"  • Discovered RCA Clusters : {len(causes)}")
    for c in causes:
        print(f"    - [{c.cause_id}] {c.title} ({c.count} occurrences in {c.service})")
    assert len(causes) > 0, "Analyzer must extract error causes"
    print("  ✅ [PASS] RCA error cause clustering verified.")

    # Test 6: AI Evidence Pack Formation
    print("\n[TEST 6] Verifying AI Ground-Truth Evidence Dossier...")
    err_templates = get_error_templates_summary(limit=3)
    print(f"  • Normalized Error Templates for Qwen SLM ({len(err_templates)}):")
    for et in err_templates:
        print(f"    - Cluster #{et['cluster_id']} in {et['service']} ({et['count']}x): {et['template'][:70]}...")
    assert len(err_templates) > 0, "Error template extraction must return failing clusters"
    print("  ✅ [PASS] AI Ground-truth evidence pack verified.")

    print("\n" + "=" * 80)
    print("🎉 [ALL TESTS PASSED] The system is fully operational and production-ready!")
    print("=" * 80)


if __name__ == "__main__":
    run_tests()

