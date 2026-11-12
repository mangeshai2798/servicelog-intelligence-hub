"""
===============================================================================
ServiceLog Intelligence Hub - Response Generation Timing & Benchmark Tool
Calculates high-precision time required to generate responses via:
1. Direct Local Qwen 2.5 3B SLM Inference & RAG Pipeline
2. Live HTTP API Endpoint (/api/query) against the active dashboard server
===============================================================================
Usage:
  python backend/calculate_response_time.py
  python backend/calculate_response_time.py "what is the latest error"
  python backend/calculate_response_time.py "what is the latest error in <ServiceName>" --service <ServiceName>
  python backend/calculate_response_time.py --benchmark
  python backend/calculate_response_time.py --api
===============================================================================
"""

import sys
import os
import time
import json
import argparse
import subprocess
from pathlib import Path

# Resolve directory locations dynamically whether invoked from root or backend/
CURRENT_DIR = Path(__file__).resolve().parent
if CURRENT_DIR.name == "backend":
    BACKEND_DIR = CURRENT_DIR
    ROOT_DIR = CURRENT_DIR.parent
else:
    ROOT_DIR = CURRENT_DIR
    BACKEND_DIR = CURRENT_DIR / "backend"

# Auto-detect and switch to local .venv virtual environment if not already active
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    res = subprocess.call([str(VENV_PYTHON), str(Path(__file__).resolve())] + sys.argv[1:])
    sys.exit(res)

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def measure_direct_query(query: str, service: str = "ALL"):
    """
    Directly invokes query_engine and ai_service in-process,
    measuring exact RAG preparation, TTFT, neural generation, and total latency.
    """
    print("\n" + "=" * 80)
    print(f"🚀 Initializing ServiceLog Query Engine & Local Qwen 2.5 SLM...")
    print(f"• Query   : \"{query}\"")
    print(f"• Service : {service}")
    print("=" * 80)

    from app.parser import parser
    from app.analyzer import analyzer
    from app.ai_service import ai_service
    from app.query_engine import query_engine
    from app.db import init_db, sync_logs_to_db

    # Ensure logs are parsed and DB initialized
    t0_prep = time.perf_counter()
    entries = parser.parse_all()
    init_db()
    sync_logs_to_db(entries)
    prep_dur_ms = (time.perf_counter() - t0_prep) * 1000.0

    print(f"✓ Ingested {len(entries):,} log entries into SQLite ({prep_dur_ms:.1f}ms)")
    print(f"✓ Model Provider: {ai_service.provider} | Model: {ai_service.model_name}")
    print(f"⏱️  Executing query through autonomous RAG pipeline...")

    # Execute query with timing
    t0_query = time.perf_counter()
    response = query_engine.answer_query(
        query=query,
        service=None if service == "ALL" else service
    )
    t1_query = time.perf_counter()

    total_elapsed_s = t1_query - t0_query
    total_elapsed_ms = total_elapsed_s * 1000.0

    ttft_s = getattr(response, "ttft_s", None)
    gen_time_s = getattr(response, "generation_time_s", None)
    speed = getattr(response, "tokens_per_sec", None)
    tokens = getattr(response, "tokens_count", None)

    # Display clean ASCII report
    print("\n" + "=" * 80)
    print("⏱️  [RESPONSE GENERATION TIMING REPORT]")
    print(f"• Query                     : \"{query}\"")
    print(f"• Service Scope             : {service}")
    print(f"• Category                  : {response.category}")
    print(f"• Model                     : {ai_service.model_name}")
    print("-" * 80)
    print("📊 Latency & Performance Breakdown:")
    if ttft_s is not None and ttft_s > 0:
        print(f"  • Time to First Token (TTFT) : {ttft_s:.3f} s")
    if gen_time_s is not None and gen_time_s > 0:
        tokens_str = f"{tokens} tokens" if tokens else ""
        speed_str = f"{speed:.1f} tok/s" if speed else ""
        print(f"  • Neural Generation Duration : {gen_time_s:.2f} s ({speed_str} | {tokens_str})")
    print(f"  • Total End-to-End Latency   : {total_elapsed_s:.2f} s ({total_elapsed_ms:.1f} ms)")
    print("=" * 80)

    print("\n📝 Generated Operational Response:")
    print("-" * 80)
    print(response.answer)
    print("-" * 80)

    return {
        "query": query,
        "service": service,
        "total_elapsed_s": round(total_elapsed_s, 3),
        "total_elapsed_ms": round(total_elapsed_ms, 1),
        "ttft_s": round(ttft_s, 3) if ttft_s else None,
        "gen_time_s": round(gen_time_s, 2) if gen_time_s else None,
        "speed_tok_s": round(speed, 1) if speed else None,
        "tokens": tokens,
        "category": response.category
    }


def measure_api_query(query: str, service: str = "ALL", base_url: str = "http://127.0.0.1:8000"):
    """
    Measures response generation time via the HTTP API of the running server.
    """
    import urllib.request
    import urllib.error

    endpoint = f"{base_url}/api/query"
    payload = json.dumps({"query": query, "service": service}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    print("\n" + "=" * 80)
    print(f"🌐 Testing Live Backend API: {endpoint}")
    print(f"• Query   : \"{query}\"")
    print(f"• Scope   : {service}")
    print("=" * 80)

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw_body = resp.read().decode("utf-8")
            data = json.loads(raw_body)
    except urllib.error.URLError as e:
        print(f"❌ Failed to reach backend at {endpoint}: {e}")
        print("Please ensure the dashboard is running via 'python run_dashboard.py'.")
        return None

    t1 = time.perf_counter()
    http_latency_s = t1 - t0
    http_latency_ms = http_latency_s * 1000.0

    backend_dur_s = data.get("duration_s", round(http_latency_s, 2))
    backend_dur_ms = data.get("duration_ms", round(http_latency_ms, 1))
    ttft_s = data.get("ttft_s")
    gen_time_s = data.get("generation_time_s")
    speed = data.get("tokens_per_sec")
    tokens = data.get("tokens_count")

    print("\n" + "=" * 80)
    print("⏱️  [HTTP API RESPONSE GENERATION TIMING]")
    print(f"• Query                     : \"{query}\"")
    print(f"• Service Scope             : {service}")
    print(f"• Model / Category          : {data.get('category', 'Local Qwen 2.5')}")
    print("-" * 80)
    print("📊 Measured Metrics:")
    if ttft_s is not None:
        print(f"  • Time to First Token (TTFT) : {ttft_s:.3f} s")
    if gen_time_s is not None:
        print(f"  • Neural Generation Duration : {gen_time_s:.2f} s ({speed or 0:.1f} tok/s | {tokens or 0} tokens)")
    print(f"  • Backend Pipeline Duration  : {backend_dur_s:.2f} s ({backend_dur_ms:.1f} ms)")
    print(f"  • HTTP Total Round-Trip Time : {http_latency_s:.2f} s ({http_latency_ms:.1f} ms)")
    print("=" * 80)

    print("\n📝 Response Content:")
    print("-" * 80)
    print(data.get("answer", ""))
    print("-" * 80)

    return {
        "query": query,
        "service": service,
        "http_latency_s": round(http_latency_s, 3),
        "http_latency_ms": round(http_latency_ms, 1),
        "backend_dur_s": backend_dur_s,
        "backend_dur_ms": backend_dur_ms,
        "ttft_s": ttft_s,
        "speed": speed,
        "tokens": tokens
    }


def run_benchmark():
    """
    Executes a comprehensive benchmark suite of representative queries.
    Dynamically discovers active services and adapts query scope.
    """
    from app.analyzer import analyzer
    services = [s.name for s in analyzer.get_services_summary()]

    benchmark_queries = [
        ("what is the latest error", "ALL"),
        ("what is our system SLA and success rate", "ALL"),
        ("why did the service break", "ALL")
    ]
    for s in services[:3]:
        benchmark_queries.append((f"what is the latest error in {s}", s))

    print("\n" + "=" * 80)
    print("🏁 [LOCAL QWEN 2.5 3B RESPONSE GENERATION BENCHMARK]")
    print(f"Running {len(benchmark_queries)} representative test queries...")
    print("=" * 80)

    results = []
    for idx, (q, svc) in enumerate(benchmark_queries, 1):
        print(f"\n--- [Benchmark {idx}/{len(benchmark_queries)}] Query: '{q}' (Scope: {svc}) ---")
        res = measure_direct_query(q, svc)
        results.append(res)

    # Summary table
    print("\n" + "=" * 80)
    print("📋 BENCHMARK SUMMARY & LATENCY COMPARISON")
    print("=" * 80)
    print(f"{'#':<3} | {'Scope':<26} | {'TTFT':<8} | {'Gen (s)':<9} | {'Speed':<11} | {'Total (s)':<10}")
    print("-" * 80)

    total_times = []
    speeds = []
    for idx, r in enumerate(results, 1):
        ttft_str = f"{r['ttft_s']:.2f}s" if r.get('ttft_s') else "N/A"
        gen_str = f"{r['gen_time_s']:.2f}s" if r.get('gen_time_s') else "N/A"
        speed_str = f"{r['speed_tok_s']:.1f} tok/s" if r.get('speed_tok_s') else "N/A"
        total_str = f"{r['total_elapsed_s']:.2f}s"

        total_times.append(r['total_elapsed_s'])
        if r.get('speed_tok_s'):
            speeds.append(r['speed_tok_s'])

        print(f"{idx:<3} | {r['service'][:26]:<26} | {ttft_str:<8} | {gen_str:<9} | {speed_str:<11} | {total_str:<10}")

    print("-" * 80)
    if total_times:
        avg_time = sum(total_times) / len(total_times)
        min_time = min(total_times)
        max_time = max(total_times)
        avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
        print(f"Summary: Avg = {avg_time:.2f}s | Min = {min_time:.2f}s | Max = {max_time:.2f}s | Avg Speed = {avg_speed:.1f} tok/s")
    print("=" * 80)

    # Save to JSON
    output_path = ROOT_DIR / "benchmark_timing_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Saved benchmark timing results to: {output_path.name}")


if __name__ == "__main__":
    parser_arg = argparse.ArgumentParser(description="Calculate response generation time for ServiceLog AI Hub")
    parser_arg.add_argument("query", nargs="?", default="what is the latest error", help="Query string to evaluate")
    parser_arg.add_argument("--service", default="ALL", help="Target service scope (ALL, ACHStatusUpdate, DorchesterPaymentExport, etc.)")
    parser_arg.add_argument("--api", action="store_true", help="Measure latency via live HTTP API endpoint (http://127.0.0.1:8000/api/query)")
    parser_arg.add_argument("--benchmark", action="store_true", help="Run comprehensive multi-query benchmark suite")
    parser_arg.add_argument("--url", default="http://127.0.0.1:8000", help="Base URL of dashboard server when testing --api")

    args = parser_arg.parse_args()

    if args.benchmark:
        run_benchmark()
    elif args.api:
        measure_api_query(args.query, args.service, base_url=args.url)
    else:
        measure_direct_query(args.query, args.service)

