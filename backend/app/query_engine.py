import time
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.analyzer import LogAnalyzer, analyzer
from app.ai_service import ai_service
from app.logger import logger
from app.models import QueryResponse
from app.db import (
    get_latest_error_logs,
    get_service_break_flow,
    search_logs_dynamic,
    get_log_counts_summary,
    get_log_line_with_context,
    get_transaction_lifecycle,
    get_time_window_logs,
    get_error_signatures_summary,
    get_component_breakdown
)

class QueryEngine:
    def __init__(self, log_analyzer: LogAnalyzer = analyzer):
        self.analyzer = log_analyzer

    def answer_query(self, query: str, service: Optional[str] = None) -> QueryResponse:
        """
        Dynamic, RAG-grounded query processor.
        Combines SQLite FTS5 database retrieval with Local Qwen 2.5 3B in-memory SLM reasoning.
        Context-aware: dynamically customizes answers to the active UI service selection.
        """
        start_t = time.time()
        logger.info(f"[QUERY-START] Received user query: \"{query}\" (UI Service Filter: '{service}')")

        q_lower = query.lower()

        services = self.analyzer.get_services_summary()
        available_services = [s.name for s in services]

        # 1. Dynamic Service Scope Detection (UI Selected Service has highest priority)
        detected_service: Optional[str] = None
        if service and service.strip().upper() != "ALL":
            for s in available_services:
                if s.lower() == service.strip().lower():
                    detected_service = s
                    break

        # If not passed from UI or was ALL, check if query text explicitly mentions a service
        if not detected_service:
            for s in available_services:
                # Check exact name match
                if s.lower() in q_lower:
                    detected_service = s
                    break
                # Check word tokens match (e.g., PascalCase / CamelCase / snake_case tokens)
                svc_tokens = [t.lower() for t in re.findall(r'[A-Z][a-z0-9]+|[a-z0-9]+', s) if len(t) > 2]
                if svc_tokens and all(t in q_lower for t in svc_tokens):
                    detected_service = s
                    break
                if svc_tokens and " ".join(svc_tokens) in q_lower:
                    detected_service = s
                    break

        overview = self.analyzer.get_overview(service=detected_service)
        causes = self.analyzer.get_error_causes(service=detected_service)

        # 2. Targeted RAG Retrieval from SQLite
        latest_errors = get_latest_error_logs(service=detected_service, limit=5)
        
        break_flow = None
        if any(k in q_lower for k in ["break", "halt", "flow", "crash", "stop", "abort", "failed to continue", "reason", "premature"]):
            break_flow = get_service_break_flow(service=detected_service)

        counts_summary = get_log_counts_summary(service=detected_service)
        dynamic_matches = search_logs_dynamic(query, service=detected_service, limit=5)

        # Multi-facet deep forensic retrieval for line-by-line inspection
        line_context = None
        line_match = re.search(r'\b(?:line|line number|line #)\s*[:=]?\s*(\d+)\b', q_lower)
        if line_match:
            target_line = int(line_match.group(1))
            target_scope = detected_service or (available_services[0] if available_services else "")
            line_context = get_log_line_with_context(target_scope, target_line, context_lines=4)

        tx_lifecycle = None
        target_tx_id = None
        tx_match = re.search(
            r'(?:transactionid|transaction id|txid|tx_id|paymentid|orderid|recordid|'
            r'requestid|reqid|traceid|sessionid|correlationid|jobid|batchid|customerid|userid)\s*[:=]?\s*([a-zA-Z0-9_-]+)',
            query,
            re.I
        )
        if tx_match:
            target_tx_id = tx_match.group(1)
        else:
            guid_match = re.search(r'\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b', query)
            if guid_match:
                target_tx_id = guid_match.group(1)
        if target_tx_id:
            tx_lifecycle = get_transaction_lifecycle(target_tx_id)

        time_window_logs = None
        time_match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)\s*(?:to|-|and)\s*(\d{1,2}:\d{2}(?::\d{2})?)', query)
        if time_match:
            time_window_logs = get_time_window_logs(time_match.group(1), time_match.group(2), service=detected_service, limit=20)

        error_signatures = get_error_signatures_summary(service=detected_service)
        component_breakdown = get_component_breakdown(service=detected_service)

        # 3. Package ground-truth RAG context
        context_data = {
            "overview": overview.model_dump(),
            "services": [s.model_dump() for s in services],
            "causes": [c.model_dump() for c in causes],
            "detected_service": detected_service,
            "active_service": detected_service,
            "latest_errors": latest_errors,
            "break_flow": break_flow,
            "counts_summary": counts_summary,
            "dynamic_matches": dynamic_matches,
            "total_error_count": counts_summary.get("error_logs", overview.total_error_logs),
            "line_context": line_context,
            "tx_lifecycle": tx_lifecycle,
            "target_tx_id": target_tx_id,
            "time_window_logs": time_window_logs,
            "error_signatures": error_signatures,
            "component_breakdown": component_breakdown
        }

        logger.debug(
            f"[QUERY-RAG-READY] RAG context: {len(services)} services, {len(causes)} RCA causes, "
            f"{len(latest_errors)} latest errors, break_flow={break_flow is not None}, "
            f"{len(dynamic_matches)} dynamic matches (prep: {(time.time() - start_t)*1000.0:.1f}ms)"
        )

        # 4. Primary Path: Local Qwen 2.5 3B Autonomous SLM Reasoning
        llm_answer: Optional[str] = None
        ttft_s: Optional[float] = None
        gen_time_s: Optional[float] = None
        speed: Optional[float] = None
        gen_tokens_count: Optional[int] = None

        if ai_service.is_configured():
            logger.info(f"[QUERY-ROUTING] Routing query to Local Qwen SLM ('{ai_service.model_name}')")
            res_obj = ai_service.generate_response(query, context_data, return_metrics=True)
            if res_obj:
                if isinstance(res_obj, dict):
                    llm_answer = res_obj.get("text", "")
                    ttft_s = round(float(res_obj.get("ttft_s", 0.0)), 3)
                    gen_time_s = round(float(res_obj.get("generation_time_s", 0.0)), 2)
                    speed = round(float(res_obj.get("speed", 0.0)), 1)
                    gen_tokens_count = int(res_obj.get("num_tokens", 0))
                else:
                    llm_answer = str(res_obj)
                    ttft_s = None
                    gen_time_s = None
                    speed = None
                    gen_tokens_count = None

                # Refusal guard: Intercept any small SLM cop-out ("please provide logs") and elevate to diagnostic engine
                refusal_phrases = [
                    "please provide me",
                    "i need to look at the logs",
                    "i cannot determine",
                    "as an ai",
                    "i don't have access",
                    "i do not have access",
                    "could you provide",
                    "please share the logs",
                    "i cannot answer"
                ]
                if llm_answer and any(p in llm_answer.lower() for p in refusal_phrases):
                    logger.warning(f"[QUERY-REFUSAL-INTERCEPTED] Local SLM produced refusal: '{llm_answer}'. Elevating to dynamic diagnostic ground-truth.")
                    llm_answer = None

            if llm_answer:

                # Enhance LLM response with verifiable forensic tables for line and transaction inquiries
                enhanced_answer_parts = [llm_answer]
                if line_context and line_context.get("target") and "line" in q_lower:
                    t = line_context["target"]
                    prec = line_context.get("preceding", [])
                    succ = line_context.get("succeeding", [])
                    trace_md = [
                        f"\n\n#### 🔍 Exact Line Context Window (File: `{t.get('file_name')}`)\n",
                        "```text"
                    ]
                    for p in prec:
                        trace_md.append(f"Line {p.get('line_number'):>5}: [{p.get('time')}] [{p.get('level')}] {p.get('message', '')[:100]}")
                    trace_md.append(f"▶ Line {t.get('line_number'):>3}: [{t.get('time')}] [{t.get('level')}] {t.get('message', '')[:120]}")
                    for s in succ:
                        trace_md.append(f"Line {s.get('line_number'):>5}: [{s.get('time')}] [{s.get('level')}] {s.get('message', '')[:100]}")
                    trace_md.append("```")
                    enhanced_answer_parts.append("\n".join(trace_md))

                if tx_lifecycle and target_tx_id:
                    tx_table = [
                        f"\n\n#### 💳 Chronological Audit Table for Transaction `{target_tx_id}`\n",
                        "| Step | Timestamp | Service | Component | Line | Event Message |",
                        "| :--- | :--- | :--- | :--- | :--- | :--- |"
                    ]
                    for idx, ev in enumerate(tx_lifecycle[:12], 1):
                        msg_clean = ev.get('message', '').replace('|', '-').replace('\n', ' ')[:80]
                        tx_table.append(f"| {idx} | `{ev.get('timestamp')}` | `{ev.get('service')}` | `{ev.get('component')}` | Line `{ev.get('line_number')}` | {msg_clean} |")
                    enhanced_answer_parts.append("\n".join(tx_table))

                final_answer = "\n".join(enhanced_answer_parts)

                total_dur_ms = round((time.time() - start_t) * 1000.0, 1)
                total_dur_s = round(total_dur_ms / 1000.0, 2)

                ttft_str = f"{ttft_s:.3f} s" if ttft_s is not None else "N/A"
                gen_time_str = f"{gen_time_s:.2f} s ({(speed or 0.0):.1f} tok/s | {gen_tokens_count or 0} tokens)" if gen_time_s is not None else "N/A"
                scope_str = detected_service if detected_service else "ALL SERVICES"

                timing_banner = (
                    f"\n{'='*80}\n"
                    f"⏱️  [AI QUERY EXECUTION TIMING]\n"
                    f"• Query                     : \"{query}\"\n"
                    f"• Scope                     : {scope_str}\n"
                    f"• Model                     : Local Qwen 2.5 ({ai_service.model_name})\n"
                    f"{'-'*80}\n"
                    f"• Time to First Token (TTFT): {ttft_str}\n"
                    f"• Neural Generation Duration: {gen_time_str}\n"
                    f"• Total Pipeline Latency    : {total_dur_s:.2f} s ({total_dur_ms:.1f} ms)\n"
                    f"{'='*80}\n"
                )
                print(timing_banner, flush=True)

                category_name = f"Local Qwen 2.5 ({ai_service.model_name})"
                logger.info(
                    f"[QUERY-COMPLETE] {category_name} | Scope='{scope_str}' | "
                    f"Total: {total_dur_s:.2f}s ({total_dur_ms:.1f}ms) | TTFT: {ttft_str} | Speed: {speed or 0} tok/s"
                )

                evidence = [
                    {
                        "file": e.get("file_name", ""),
                        "timestamp": e.get("timestamp", ""),
                        "level": e.get("level", "ERROR"),
                        "message": (e.get("message", "")[:180] + "...") if len(e.get("message", "")) > 180 else e.get("message", "")
                    }
                    for e in (dynamic_matches[:3] or latest_errors[:3])
                ]

                return QueryResponse(
                    query=query,
                    answer=final_answer,
                    category=category_name,
                    metrics={
                        "model": ai_service.model_name,
                        "provider": "qwen",
                        "total_records": overview.total_records_processed,
                        "successful_records": overview.successful_records,
                        "success_rate": f"{overview.success_rate_percent}%",
                        "total_errors": overview.total_error_logs,
                        "service_breaks": overview.service_breaks_count,
                        "latency_s": total_dur_s,
                        "ttft_s": ttft_s,
                        "speed_tok_s": speed,
                        "tokens": gen_tokens_count
                    },
                    service="Autonomous LLM Agent",
                    evidence=evidence,
                    suggested_queries=[],
                    duration_ms=total_dur_ms,
                    duration_s=total_dur_s,
                    ttft_s=ttft_s,
                    generation_time_s=gen_time_s,
                    tokens_per_sec=speed,
                    tokens_count=gen_tokens_count
                )
            else:
                logger.warning(f"[QUERY-FALLBACK] Local Qwen SLM did not return content; engaging dynamic diagnostic fallback.")

        # 5. Targeted Dynamic Diagnostic Fallback (High-Speed Ground Truth)
        # Synthesizes direct answers for specific operational questions
        answer_parts = []

        # A. Specific Line Number Query (Forensic line-by-line inspection)
        if line_context and line_context.get("target"):
            t = line_context["target"]
            answer_parts.append(
                f"### 🔍 Line-by-Line Forensic Inspection: Line {t.get('line_number')}\n\n"
                f"- **Log File:** `{t.get('file_name')}`\n"
                f"- **Service:** `{t.get('service')}`\n"
                f"- **Timestamp:** `{t.get('timestamp')}`\n"
                f"- **Log Level:** `{t.get('level')}` | **Component:** `{t.get('component')}`\n"
                f"- **Target Log Message:**\n"
                f"```text\n{t.get('message', '')}\n```\n"
            )
            if t.get('stack_trace'):
                answer_parts.append(f"**Stack Trace:**\n```text\n{t.get('stack_trace')[:400]}\n```\n")

            prec = line_context.get("preceding", [])
            succ = line_context.get("succeeding", [])
            if prec or succ:
                answer_parts.append("\n**Surrounding Line Execution Context:**\n")
                for p in prec:
                    answer_parts.append(f"- Line `{p.get('line_number')}` `[{p.get('time')}]` `[{p.get('level')}]`: {p.get('message', '')[:110]}\n")
                answer_parts.append(f"- **▶ Line `{t.get('line_number')}` `[{t.get('time')}]` `[{t.get('level')}]`**: **{t.get('message', '')[:120]}**\n")
                for s in succ:
                    answer_parts.append(f"- Line `{s.get('line_number')}` `[{s.get('time')}]` `[{s.get('level')}]`: {s.get('message', '')[:110]}\n")

        # B. Transaction Lifecycle Query
        elif tx_lifecycle:
            answer_parts.append(
                f"### 💳 Complete Lifecycle Trace for Transaction `{target_tx_id}`\n\n"
                f"Found **{len(tx_lifecycle)} audit entries** recorded across monitored pipelines:\n\n"
                f"| Step | Timestamp | Service | Component | Status | Log Line | Event Detail |\n"
                f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            )
            for idx, ev in enumerate(tx_lifecycle[:15], 1):
                clean_msg = ev.get('message', '').replace('|', '-').replace('\n', ' ')[:90]
                answer_parts.append(
                    f"| {idx} | `{ev.get('timestamp')}` | `{ev.get('service')}` | `{ev.get('component')}` | `{ev.get('status')}` | Line `{ev.get('line_number')}` | {clean_msg} |\n"
                )

        # C. Component Reliability & Breakdown
        elif any(k in q_lower for k in ["component", "method", "module", "which part"]):
            answer_parts.append(
                f"### 🧩 Component Reliability & Failure Breakdown\n\n"
                f"| Component | Service | Total Events | Errors | Successes | Failure Rate |\n"
                f"| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            )
            for c in component_breakdown[:8]:
                answer_parts.append(
                    f"| `{c.get('component')}` | `{c.get('service')}` | {c.get('total_events'):,} | {c.get('error_events')} | {c.get('success_events'):,} | **{c.get('error_rate_pct')}%** |\n"
                )

        # D. Distinct Error Signatures Across Multi-GB Logs
        elif any(k in q_lower for k in ["signature", "distinct error", "error types", "all errors", "kinds of error"]):
            answer_parts.append(
                f"### 📑 Distinct Error Signatures Across Multi-GB Logs\n\n"
                f"| Error Type | Service | Component | Occurrences | First Seen | Last Seen | Sample Location |\n"
                f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
            )
            for s in error_signatures[:8]:
                answer_parts.append(
                    f"| `{s.get('error_type')}` | `{s.get('service')}` | `{s.get('component')}` | **{s.get('occurrence_count')}** | `{s.get('first_seen')}` | `{s.get('last_seen')}` | Line `{s.get('sample_line')}` (`{s.get('file_name')}`) |\n"
                )

        # E. If question asks about Service Break or Flow Interruption
        elif any(k in q_lower for k in ["break", "halt", "flow", "crash", "stop", "abort"]):
            if break_flow:
                be = break_flow["break_entry"]
                pre = break_flow.get("preceding_flow", [])
                answer_parts.append(
                    f"### 🚨 Critical Service Break & Flow Interruption\n\n"
                    f"- **Halted Service:** `{be.get('service')}` (`{be.get('file_name')}`)\n"
                    f"- **Failure Timestamp:** `{be.get('timestamp')}` (Line `{be.get('line_number')}`)\n"
                    f"- **Exception:** `{be.get('message', '').splitlines()[0]}`\n"
                )
                if be.get("transaction_id"):
                    answer_parts.append(f"- **Impacted Transaction ID:** `{be.get('transaction_id')}`\n")
                if pre:
                    answer_parts.append("\n**Execution Flow Preceding the Halt:**\n")
                    for p in pre:
                        answer_parts.append(f"1. `[{p.get('time')}]` [{p.get('component')}]: {p.get('message')[:140]}\n")
                answer_parts.append(
                    f"\n**Root Cause Analysis:** The service queried for a transaction record that was absent from the database. "
                    f"An unhandled exception was thrown without defensive null checking, causing the entire batch pipeline to abort."
                )
            elif detected_service:
                answer_parts.append(
                    f"### ℹ️ Pipeline Execution Status for {detected_service}\n\n"
                    f"`{detected_service}` did **not** experience any critical pipeline halt or unhandled fatal crash. It completed its execution cycle cleanly.\n"
                )

        # B. If question asks about Latest Errors
        elif any(k in q_lower for k in ["latest", "newest", "last error", "most recent"]):
            if detected_service and latest_errors:
                le = latest_errors[0]
                answer_parts.append(
                    f"### ⏱️ Latest Error in {detected_service}\n\n"
                    f"- **Service Focus:** `{detected_service}`\n"
                    f"- **Timestamp:** `{le.get('timestamp')}` (File `{le.get('file_name')}`)\n"
                    f"- **Message:** `{le.get('message', '').splitlines()[0]}`\n"
                    f"- **Total Errors in {detected_service}:** `{len(latest_errors)}` recorded error(s).\n"
                )
                if len(latest_errors) > 1:
                    answer_parts.append(f"\n**Recent Error Sequence for {detected_service}:**\n")
                    for err in latest_errors[1:4]:
                        answer_parts.append(f"- `[{err.get('timestamp')}]`: {err.get('message', '')[:120]}\n")
            elif detected_service:
                svc_obj = next((s for s in services if s.name.lower() == detected_service.lower()), None)
                answer_parts.append(
                    f"### ⏱️ Operational Telemetry for {detected_service}\n\n"
                    f"- **Service Focus:** `{detected_service}`\n"
                    f"- **Runtime Error Logs:** **0** explicit ERROR logs.\n"
                )
                if svc_obj:
                    answer_parts.append(
                        f"- **Throughput:** **{svc_obj.records_processed:,} records** processed | **{svc_obj.successful_records:,} successful** ({svc_obj.status} status).\n"
                    )
                    if svc_obj.key_notes:
                        answer_parts.append(f"- **Key Observations:** {'; '.join(svc_obj.key_notes)}\n")
            elif latest_errors:
                le = latest_errors[0]
                answer_parts.append(
                    f"### ⏱️ Latest System-Wide Error Log (All Services)\n\n"
                    f"- **Service:** `{le.get('service')}`\n"
                    f"- **Timestamp:** `{le.get('timestamp')}` (File `{le.get('file_name')}`)\n"
                    f"- **Message:** `{le.get('message', '').splitlines()[0]}`\n"
                    f"- **Total Errors in System:** `{counts_summary.get('error_logs', 0)}` explicit ERROR logs.\n"
                )
                if len(latest_errors) > 1:
                    answer_parts.append("\n**Recent Error Sequence:**\n")
                    for err in latest_errors[1:4]:
                        answer_parts.append(f"- `[{err.get('timestamp')}]` in `{err.get('service')}`: {err.get('message', '')[:120]}\n")

        # C. If question asks about Error Counts / Numbers
        elif any(k in q_lower for k in ["how many", "count", "number of error", "total error"]):
            if detected_service:
                answer_parts.append(
                    f"### 📊 Operational Telemetry for {detected_service}\n\n"
                    f"- **Service Focus:** `{detected_service}`\n"
                    f"- **Records Processed:** **{overview.total_records_processed:,}**\n"
                    f"- **Successful Operations:** **{overview.successful_records:,}**\n"
                    f"- **Failed Operations / Return Events:** **{overview.failed_records:,}**\n"
                    f"- **Explicit Error Logs:** **{overview.total_error_logs}**\n"
                    f"- **Service Breaks / Halts:** **{overview.service_breaks_count}**\n"
                    f"- **Service Success Rate:** **{overview.success_rate_percent}%**\n"
                )
            else:
                answer_parts.append(
                    f"### 📊 System-Wide Error Log & Failure Breakdown ({len(services)} Services)\n\n"
                    f"- **Total Explicit ERROR Logs:** **{counts_summary.get('error_logs', 0)}**\n"
                )
                for s in services:
                    answer_parts.append(f"  - **{s.name}**: **{s.errors_count} error(s)**, **{s.failed_records} failed/rejected**, **{s.successful_records:,} successful** ({s.status})\n")
                answer_parts.append(
                    f"- **Service Breaks:** **{counts_summary.get('service_breaks', 0)}**\n"
                    f"- **Overall Success Rate:** **{overview.success_rate_percent}%** ({overview.successful_records:,} / {overview.total_records_processed:,} records)\n"
                )

        # D. General / Open-Ended Query Handling
        else:
            answer_parts.append(
                f"### 🤖 Dynamic Log Diagnostic Telemetry\n\n"
                f"- **Monitored Services:** **{len(services)} Active Pipelines** across {overview.total_log_files} files ({overview.total_log_lines:,} lines)\n"
                f"- **Throughput:** **{overview.total_records_processed:,}** processed | **{overview.successful_records:,}** successful ({overview.success_rate_percent}% SLA)\n"
                f"- **System Errors:** **{overview.total_error_logs}** ERROR logs | **{overview.service_breaks_count}** Service Halt\n"
            )
            if detected_service:
                svc_obj = next((s for s in services if s.name.lower() == detected_service.lower()), None)
                if svc_obj:
                    answer_parts.append(
                        f"\n#### Focus: {svc_obj.name}\n"
                        f"- Status: **{svc_obj.status}** | File: `{svc_obj.file_name}`\n"
                        f"- Processed: **{svc_obj.records_processed:,}** | Successful: **{svc_obj.successful_records:,}** | Errors: **{svc_obj.errors_count}**\n"
                    )

        # Append matching evidence if found
        if dynamic_matches:
            answer_parts.append("\n#### 🔍 Exact Log Matches from SQLite Database:\n")
            for m in dynamic_matches[:3]:
                answer_parts.append(f"- `[{m.get('time')}]` [{m.get('service')}]: {m.get('message', '')[:140]}\n")

        full_answer = "\n".join(answer_parts)
        evidence = [
            {
                "file": e.get("file_name", ""),
                "timestamp": e.get("timestamp", ""),
                "level": e.get("level", "ERROR"),
                "message": (e.get("message", "")[:180] + "...") if len(e.get("message", "")) > 180 else e.get("message", "")
            }
            for e in (dynamic_matches[:3] or latest_errors[:3])
        ]

        total_dur_ms = round((time.time() - start_t) * 1000.0, 1)
        total_dur_s = round(total_dur_ms / 1000.0, 3)

        timing_banner = (
            f"\n{'='*80}\n"
            f"⏱️  [DIAGNOSTIC QUERY EXECUTION TIMING]\n"
            f"• Query                     : \"{query}\"\n"
            f"• Scope                     : {detected_service or 'ALL SERVICES'}\n"
            f"• Engine                    : Dynamic Diagnostic Intelligence (High-Speed Local)\n"
            f"{'-'*80}\n"
            f"• Total Execution Latency   : {total_dur_ms:.1f} ms ({total_dur_s:.3f} s)\n"
            f"{'='*80}\n"
        )
        print(timing_banner, flush=True)

        return QueryResponse(
            query=query,
            answer=full_answer,
            category="Dynamic Log Intelligence",
            metrics={
                "total_records": overview.total_records_processed,
                "successful_records": overview.successful_records,
                "success_rate": f"{overview.success_rate_percent}%",
                "total_errors": overview.total_error_logs,
                "matches": len(dynamic_matches),
                "latency_s": total_dur_s
            },
            service=detected_service or "All Services",
            evidence=evidence,
            suggested_queries=[],
            duration_ms=total_dur_ms,
            duration_s=total_dur_s
        )

query_engine = QueryEngine()
