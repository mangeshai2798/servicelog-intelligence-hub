# pyright: reportMissingImports=false
# pyright: reportMissingTypeStubs=false
"""
Local In-Memory Qwen 2.5 3B Intelligence Engine
Dedicated offline SLM reasoning service for multi-service log observability.
Runs 100% locally via PyTorch and Hugging Face Transformers.
"""

import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, TYPE_CHECKING

from app.config import WORKSPACE_DIR
from app.logger import (
    logger,
    log_llm_call_start,
    log_llm_call_complete,
    log_llm_call_error
)

if TYPE_CHECKING:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, TextStreamer
else:
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, TextStreamer
    except (ImportError, ModuleNotFoundError):
        torch = None
        AutoTokenizer = None
        AutoModelForCausalLM = None
        class TextStreamer:  # type: ignore
            def __init__(self, *args, **kwargs):
                self.next_tokens_are_prompt = False
            def put(self, value): pass

DEFAULT_QWEN_MODEL = os.getenv("LOCAL_MODEL", "Qwen/Qwen2.5-3B-Instruct")
DEFAULT_MODEL = DEFAULT_QWEN_MODEL
DEFAULT_PROVIDER = "qwen"

# Custom Streamer to stream tokens in real-time and measure Time-To-First-Token (TTFT)
class StreamCapture(TextStreamer):  # type: ignore
    """Custom Streamer to stream tokens in real-time and measure Time-To-First-Token (TTFT)."""
    def __init__(self, tokenizer, **kwargs):
        super().__init__(tokenizer, skip_prompt=True, skip_special_tokens=True, **kwargs)
        self.start_t = None
        self.first_token_t = None

    def start_timing(self):
        self.start_t = time.perf_counter()
        self.first_token_t = None

    def put(self, value):
        if not self.next_tokens_are_prompt and self.first_token_t is None and self.start_t is not None:
            self.first_token_t = time.perf_counter()
        super().put(value)

    @property
    def ttft(self):
        return (self.first_token_t - self.start_t) if (self.start_t and self.first_token_t) else 0.0


# In-memory local Qwen pipeline loader & runner (Singleton)
class LocalQwenEngine:
    """In-memory singleton runner for Qwen 2.5 (3B / 0.5B) using PyTorch & Transformers."""
    _instance: Any = None
    _tokenizer: Any = None
    _model: Any = None
    _is_warmed_up: bool = False
    _model_id: str = DEFAULT_QWEN_MODEL

    @classmethod
    def get_instance(cls, model_id: Optional[str] = None):
        if cls._instance is None:
            cls._instance = cls(model_id=model_id or DEFAULT_QWEN_MODEL)
        elif model_id and model_id != cls._instance.model_id:
            cls._instance.model_id = model_id
        return cls._instance

    def __init__(self, model_id: str = DEFAULT_QWEN_MODEL):
        self.model_id = model_id or DEFAULT_QWEN_MODEL

    def load_model(self) -> bool:
        if LocalQwenEngine._model is not None and LocalQwenEngine._tokenizer is not None:
            return True
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM

            project_root = Path(__file__).resolve().parent.parent.parent
            clean_name = self.model_id.split("/")[-1]
            local_model_path = project_root / "models" / clean_name
            if not (local_model_path.exists() and (local_model_path / "model.safetensors").exists()):
                for candidate in [project_root / "models" / "Qwen2.5-3B-Instruct", project_root / "models" / "Qwen2.5-0.5B-Instruct"]:
                    if candidate.exists() and (candidate / "model.safetensors").exists():
                        local_model_path = candidate
                        break

            target_path = str(local_model_path) if local_model_path.exists() and (local_model_path / "model.safetensors").exists() else self.model_id
            logger.info(f"[LOCAL-QWEN] Loading '{target_path}' into memory (torch.float32)...")

            try:
                tokenizer = AutoTokenizer.from_pretrained(target_path, local_files_only=True)
            except Exception:
                tokenizer = AutoTokenizer.from_pretrained(target_path)

            try:
                model = AutoModelForCausalLM.from_pretrained(target_path, dtype=torch.float32, local_files_only=True)
            except Exception:
                model = AutoModelForCausalLM.from_pretrained(target_path, dtype=torch.float32)

            if tokenizer is None or model is None:
                logger.error(f"[LOCAL-QWEN-LOAD-FAILED] Failed to initialize tokenizer or model for '{self.model_id}'")
                return False

            model.eval()

            # Warm up the model with a 1-token dummy pass so PyTorch thread pools are ready
            logger.info("[LOCAL-QWEN] Warming up model (1-token dummy pass)...")
            warmup_inputs = tokenizer("warmup", return_tensors="pt")  # type: ignore
            with torch.inference_mode():
                model.generate(**warmup_inputs, max_new_tokens=1)  # type: ignore

            LocalQwenEngine._tokenizer = tokenizer
            LocalQwenEngine._model = model
            LocalQwenEngine._is_warmed_up = True
            logger.info("[LOCAL-QWEN] Model is loaded and warmed up! Ready for instant queries.")
            return True
        except Exception as e:
            logger.error(f"[LOCAL-QWEN-LOAD-FAILED] Error loading '{self.model_id}': {e}", exc_info=True)
            return False

    def is_ready(self) -> bool:
        return LocalQwenEngine._model is not None and LocalQwenEngine._tokenizer is not None

    def generate(self, system_prompt: str, user_prompt: str, max_new_tokens: int = 220) -> Optional[Dict[str, Any]]:
        if not self.is_ready():
            ok = self.load_model()
            if not ok:
                return None

        try:
            import torch
            from transformers import TextStreamer

            tokenizer = LocalQwenEngine._tokenizer
            model = LocalQwenEngine._model

            if tokenizer is None or model is None:
                logger.error("[LOCAL-QWEN] Model or tokenizer is None. Ensure model is loaded.")
                return None

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            model_inputs = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True
            )

            streamer = StreamCapture(tokenizer)
            streamer.start_timing()

            with torch.inference_mode():
                outputs = model.generate(  # type: ignore
                    **model_inputs,
                    streamer=streamer,
                    max_new_tokens=max_new_tokens,
                    do_sample=False
                )

            total_time = time.perf_counter() - streamer.start_t if streamer.start_t else 0.0
            prompt_len = model_inputs["input_ids"].shape[-1]
            gen_tokens = outputs[0][prompt_len:]
            text = tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()  # type: ignore

            num_tokens = len(gen_tokens)
            speed = num_tokens / total_time if total_time > 0 else 0.0

            logger.info(f"[LOCAL-QWEN-STATS] TTFT: {streamer.ttft:.3f}s | Total: {total_time:.2f}s | Speed: {speed:.1f} tok/s | Tokens: {num_tokens}")

            return {
                "text": text,
                "ttft": streamer.ttft,
                "total_time": total_time,
                "speed": speed,
                "num_tokens": num_tokens
            }
        except Exception as e:
            logger.error(f"[LOCAL-QWEN-GEN-FAILED] Generation error: {e}", exc_info=True)
            return None


class AIService:
    """Strictly Local In-Memory Qwen 2.5 3B AI Service."""
    def __init__(self):
        self.provider: str = DEFAULT_PROVIDER
        self.model_name: str = DEFAULT_QWEN_MODEL
        self.endpoint_url: str = "local-in-memory"
        self.api_key: Optional[str] = None
        logger.info(f"[LOCAL-AI-INIT] Initialized Local Qwen Engine: Model='{self.model_name}' (Offline In-Memory)")

    def is_configured(self) -> bool:
        """Local in-memory Qwen model is always configured and available offline."""
        return True

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": "qwen",
            "is_configured": True,
            "model": self.model_name,
            "endpoint_url": "local-in-memory",
            "masked_key": "Local In-Memory (Active)"
        }

    def generate_response(self, user_query: str, context: Dict[str, Any], return_metrics: bool = False) -> Any:
        overview = context.get('overview', {})
        services = context.get('services', [])
        causes = context.get('causes', [])
        latest_errors = context.get('latest_errors', [])

        context_summary = {
            "total_files": overview.get('total_log_files', 0),
            "total_records": overview.get('total_records_processed', 0),
            "total_errors": overview.get('total_error_logs', 0),
            "total_causes": len(causes)
        }

        log_llm_call_start(self.model_name, user_query, context_summary)

        # Build dynamic context prompt
        svc_lines = []
        for s in services:
            notes = "; ".join(s.get('key_notes', []))
            svc_lines.append(
                f"• Service: {s.get('name')} (File: {s.get('file_name')})\n"
                f"  Status: {s.get('status')} | Records Processed: {s.get('records_processed', 0):,} | "
                f"Successful: {s.get('successful_records', 0):,} | Failed/Errors: {s.get('failed_records', 0)} / {s.get('errors_count', 0)}\n"
                f"  Output Files: {', '.join(s.get('output_files', [])) or 'None'}\n"
                f"  Operational Notes: {notes}"
            )
        services_text = "\n\n".join(svc_lines) if svc_lines else "No services recorded."

        cause_lines = []
        for c in causes:
            affected = f" (Sample Entities: {', '.join(c.get('affected_transactions', []))})" if c.get('affected_transactions') else ""
            cause_lines.append(
                f"• [{c.get('cause_id')}] {c.get('title')} ({c.get('count')} occurrences):\n"
                f"  Service: {c.get('service')} | Type: {c.get('error_type')}{affected}\n"
                f"  Root Cause: {c.get('root_cause')}\n"
                f"  Recommendation: {c.get('recommendation')}\n"
                f"  Stack Trace Snippet: {c.get('sample_stack_trace', '')[:300]}"
            )
        causes_text = "\n\n".join(cause_lines) if cause_lines else "No error causes identified."

        err_lines = []
        for e in latest_errors:
            err_lines.append(f"• [{e.get('timestamp')}] [{e.get('service')}] {e.get('message')[:200]}")
        recent_errors_text = "\n".join(err_lines) if err_lines else "No recent errors recorded."

        break_flow = context.get("break_flow")
        break_flow_text = ""
        if break_flow:
            be = break_flow.get("break_entry", {})
            pre = break_flow.get("preceding_flow", [])
            break_flow_text = (
                f"\n5. CRITICAL SERVICE BREAK & FLOW RECONSTRUCTION:\n"
                f"- Halted Service: {be.get('service')} (Line {be.get('line_number')} in {be.get('file_name')})\n"
                f"- Break Timestamp: {be.get('timestamp')}\n"
                f"- Exception / Halting Error: {be.get('message', '').splitlines()[0]}\n"
            )
            if be.get("transaction_id"):
                break_flow_text += f"- Impacted Transaction ID: {be.get('transaction_id')}\n"
            if pre:
                break_flow_text += "- Preceding execution flow in batch:\n"
                for p in pre:
                    break_flow_text += f"  * [{p.get('time')}] [{p.get('component')}]: {p.get('message', '')[:120]}\n"

        dynamic_matches = context.get("dynamic_matches", [])
        matches_text = ""
        if dynamic_matches:
            matches_text = "\n6. TARGETED DATABASE LOG MATCHES FOR THIS QUERY:\n"
            for m in dynamic_matches[:4]:
                matches_text += f"• [{m.get('timestamp')}] [{m.get('service')}] {m.get('message', '')[:180]}\n"

        line_context = context.get("line_context")
        line_context_text = ""
        if line_context and line_context.get("target"):
            t = line_context["target"]
            prec = line_context.get("preceding", [])
            succ = line_context.get("succeeding", [])
            line_context_text = f"\n7. EXACT LINE-BY-LINE FORENSIC INSPECTION (File: {t.get('file_name')}):\n"
            for p in prec:
                line_context_text += f"   Line {p.get('line_number')}: [{p.get('time')}] [{p.get('level')}] [{p.get('component')}] {p.get('message', '')[:120]}\n"
            line_context_text += f"▶ TARGET LINE {t.get('line_number')}: [{t.get('time')}] [{t.get('level')}] [{t.get('component')}] {t.get('message', '')}\n"
            if t.get('stack_trace'):
                line_context_text += f"   Stack Trace: {t.get('stack_trace')[:300]}\n"
            for s in succ:
                line_context_text += f"   Line {s.get('line_number')}: [{s.get('time')}] [{s.get('level')}] [{s.get('component')}] {s.get('message', '')[:120]}\n"

        tx_lifecycle = context.get("tx_lifecycle")
        tx_lifecycle_text = ""
        if tx_lifecycle:
            target_tx = context.get("target_tx_id", "Unknown")
            tx_lifecycle_text = f"\n8. COMPLETE TRANSACTION LIFECYCLE FOR {target_tx} ({len(tx_lifecycle)} events across multi-GB index):\n"
            for idx, event in enumerate(tx_lifecycle[:10], 1):
                tx_lifecycle_text += f"   {idx}. Line {event.get('line_number')} in {event.get('file_name')} [{event.get('timestamp')}] [{event.get('service')}]: {event.get('message', '')[:140]} (Status: {event.get('status')})\n"

        error_signatures = context.get("error_signatures", [])
        signatures_text = ""
        if error_signatures:
            signatures_text = "\n9. AGGREGATED SYSTEM ERROR SIGNATURES:\n"
            for sig in error_signatures[:5]:
                signatures_text += f"• [{sig.get('service')}] {sig.get('error_type')} ({sig.get('occurrence_count')} occurrences, First: {sig.get('first_seen')}, Last: {sig.get('last_seen')}): Line {sig.get('sample_line')} in {sig.get('file_name')} -> {sig.get('sample_message')}\n"

        component_breakdown = context.get("component_breakdown", [])
        component_text = ""
        if component_breakdown:
            component_text = "\n10. COMPONENT ACTIVITY & RELIABILITY METRICS:\n"
            for comp in component_breakdown[:6]:
                component_text += f"• {comp.get('component')} ({comp.get('service')}): {comp.get('total_events')} events | {comp.get('error_events')} errors ({comp.get('error_rate_pct')}% failure rate)\n"

        active_service = context.get('active_service') or context.get('detected_service')
        services_list = context.get('services', [])
        if active_service:
            svc_info = next((s for s in services_list if s.get('name', '').lower() == active_service.lower()), None)
            notes_str = ""
            if svc_info:
                notes_str = (
                    f"- Status: {svc_info.get('status')} | Processed: {svc_info.get('records_processed', 0):,} records "
                    f"({svc_info.get('successful_records', 0):,} successful, {svc_info.get('failed_records', 0):,} failed/rejected) "
                    f"| Explicit Error Logs: {svc_info.get('errors_count', 0)}.\n"
                    f"- Key Observations: {'; '.join(svc_info.get('key_notes', []))}"
                )
            scope_instructions = f"""
*** ACTIVE USER FOCUS SCOPE IN UI: {active_service} ***
The user is currently focused specifically on the service '{active_service}' in the UI dashboard.
CRITICAL SCOPE RULE:
- You MUST answer the user's question specifically within the context of '{active_service}'.
- If the user asks for 'latest error', 'errors', 'status', or 'throughput', respond with the events and metrics for '{active_service}'.
{notes_str}
- Do NOT provide errors from other services unless the user explicitly asks about all services.
"""
        else:
            svc_count = len(services_list)
            latest_sys_err = context.get('latest_errors', [{}])[0] if context.get('latest_errors') else {}
            err_svc = latest_sys_err.get('service', 'N/A')
            err_time = latest_sys_err.get('timestamp', 'N/A')
            err_msg = latest_sys_err.get('message', '').splitlines()[0] if latest_sys_err.get('message') else 'N/A'
            scope_instructions = f"""
*** ACTIVE USER FOCUS SCOPE: ALL SERVICES (System-Wide) ***
The user has selected 'ALL SERVICES' in the UI dashboard.
Provide a comprehensive answer covering all {svc_count} active pipelines.
If asked for the latest error across all services, report the most recent error in the system: [{err_time}] in '{err_svc}': "{err_msg[:120]}".
"""

        system_prompt = f"""You are an Autonomous Site Reliability Engineering (SRE) & Observability AI Agent powered by Local Qwen 2.5 3B ({self.model_name}).
You analyze service execution logs, diagnostic metrics, record throughput, and errors.
You do NOT rely on fixed templates or hardcoded answers. You dynamically inspect the verified ground-truth context provided below and autonomously reason about how to answer the user's question.

====================== LIVE GROUND TRUTH FROM INGESTED LOGS ======================
1. SYSTEM OVERVIEW & KPIS:
- Total Log Files: {overview.get('total_log_files', 0)}
- Total Log Lines: {overview.get('total_log_lines', 0):,}
- Total Records Processed: {overview.get('total_records_processed', 0):,}
- Successful Records: {overview.get('successful_records', 0):,}
- Failed Records: {overview.get('failed_records', 0):,}
- Overall System Success Rate: {overview.get('success_rate_percent', 0)}%
- Total Explicit ERROR Logs: {overview.get('total_error_logs', 0)}
- Service Breaks / Crashes: {overview.get('service_breaks_count', 0)}
- Dates Found in Logs: {overview.get('dates_available', [])}
- Latest Recorded Date in Logs: {overview.get('latest_log_date', 'N/A')}
- Today's Real-world Date: {overview.get('current_system_date', 'N/A')}

2. ALL MONITORED SERVICES:
{services_text}

3. IDENTIFIED ROOT CAUSE ANALYSIS (RCA) CLUSTERS:
{causes_text}

4. RECENT ERROR LOG ENTRIES & TRACES:
{recent_errors_text}
{break_flow_text}
{matches_text}
{line_context_text}
{tx_lifecycle_text}
{signatures_text}
{component_text}
==================================================================================

{scope_instructions}

CORE INSTRUCTIONS:
1. Autonomously analyze the user's question, determine its intent, and synthesize a clear, helpful, professional response in GitHub-flavored Markdown.
2. Rely strictly on the ground truth provided above. Cite specific service names, filenames, numbers, timestamps, error types, line numbers, and transaction IDs when relevant.
3. If the user asks for numbers (e.g. records processed, successes, failures, counts), provide the exact numbers and use markdown tables or bulleted breakdowns.
4. If the user asks why a service broke, crashed, or errored, explain the technical root cause, stack trace location, and code remediation.
5. If the user asks about 'today' or dates, compare today's date ({overview.get('current_system_date')}) with the latest recorded date ({overview.get('latest_log_date')}).
6. You can answer ANY question the user asks about this system—general, specific, comparative, forensic, or statistical.
"""

        # Build direct focus hint for tiny SLM to prevent conversational refusals
        direct_hints = []
        q_lower = user_query.lower()
        if "component" in q_lower or "method" in q_lower:
            comp_list = context.get("component_breakdown", [])
            if comp_list:
                top_err_comp = max(comp_list, key=lambda c: c.get("error_events", 0))
                direct_hints.append(f"Direct Ground Truth: The component with the most errors is '{top_err_comp.get('component')}' in '{top_err_comp.get('service')}' with {top_err_comp.get('error_events')} errors.")
        if "line" in q_lower and context.get("line_context"):
            t = context["line_context"].get("target")
            if t:
                direct_hints.append(f"Direct Ground Truth: Line {t.get('line_number')} in '{t.get('file_name')}' is: \"{t.get('message', '')[:100]}\".")
        if context.get("tx_lifecycle"):
            direct_hints.append(f"Direct Ground Truth: Transaction '{context.get('target_tx_id')}' has {len(context.get('tx_lifecycle'))} recorded events in the logs.")

        augmented_user_query = f"{user_query}\n\n[Ground-Truth Facts from Database: {' '.join(direct_hints)}]" if direct_hints else user_query

        try:
            logger.info(f"[LOCAL-QWEN-CALL] Dispatching query to Local In-Memory Qwen engine ({self.model_name})...")
            engine = LocalQwenEngine.get_instance(self.model_name)
            res = engine.generate(system_prompt, augmented_user_query, max_new_tokens=220)
            if res and res.get("text"):
                latency_ms = res["total_time"] * 1000.0
                log_llm_call_complete(self.model_name, latency_ms, len(res["text"]), None)
                if return_metrics:
                    return {
                        "text": res["text"],
                        "ttft_s": res.get("ttft", 0.0),
                        "generation_time_s": res.get("total_time", 0.0),
                        "speed": res.get("speed", 0.0),
                        "num_tokens": res.get("num_tokens", 0)
                    }
                return res["text"]
            logger.warning("[LOCAL-QWEN-EMPTY] Qwen local generation returned empty.")
            return None
        except Exception as e:
            logger.error(f"[LOCAL-QWEN-ERROR] Error executing query with Local Qwen: {e}", exc_info=True)
            return None

# Singleton instance
ai_service = AIService()
