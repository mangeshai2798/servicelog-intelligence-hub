# pyright: reportMissingImports=false
# pyright: reportMissingTypeStubs=false
"""
Dynamic Local In-Memory Qwen Intelligence Engine
Dedicated offline SLM reasoning service for multi-service log observability.
Runs 100% locally via PyTorch and Hugging Face Transformers.
Dynamically configurable via .env (supports 0.5B, 1.5B/1B, and 3B models).
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

DEFAULT_QWEN_MODEL = os.getenv("LOCAL_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
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
        try:
            import sys
            sys.stdout.flush()
        except Exception:
            pass

    @property
    def ttft(self):
        return (self.first_token_t - self.start_t) if (self.start_t and self.first_token_t) else 0.0


# In-memory local Qwen pipeline loader & runner (Singleton)
class LocalQwenEngine:
    """In-memory singleton runner for Qwen SLM models (0.5B, 1.5B/1B, 3B) using PyTorch & Transformers."""
    _instance: Any = None
    _tokenizer: Any = None
    _model: Any = None
    _is_warmed_up: bool = False
    _model_id: str = DEFAULT_QWEN_MODEL

    @classmethod
    def unload_model(cls):
        """Strictly unloads model and tokenizer from memory and forces garbage collection."""
        if cls._model is not None or cls._tokenizer is not None:
            logger.info(f"[LOCAL-QWEN] Unloading active model '{cls._model_id}' from memory...")
        cls._model = None
        cls._tokenizer = None
        cls._is_warmed_up = False
        cls._instance = None
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        logger.info("[LOCAL-QWEN] Model unloaded and RAM cleared.")

    @classmethod
    def get_instance(cls, model_id: Optional[str] = None):
        chosen_id = model_id or os.getenv("LOCAL_MODEL", DEFAULT_QWEN_MODEL)
        if cls._instance is None:
            cls._model_id = chosen_id
            cls._instance = cls(model_id=chosen_id)
        elif chosen_id != cls._instance.model_id:
            # When model switches, clear cached in-memory instances to reload the target model
            cls.unload_model()
            cls._model_id = chosen_id
            cls._instance = cls(model_id=chosen_id)
        return cls._instance

    def __init__(self, model_id: str = DEFAULT_QWEN_MODEL):
        self.model_id = model_id or DEFAULT_QWEN_MODEL

    def load_model(self) -> bool:
        if LocalQwenEngine._model is not None and LocalQwenEngine._tokenizer is not None:
            return True
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM

            # CPU Thread Tuning: Pin to physical Performance Cores to avoid Intel hybrid E-core stalling
            torch_threads = int(os.getenv("TORCH_THREADS", "4"))
            torch.set_num_threads(torch_threads)
            if hasattr(torch, "set_num_interop_threads"):
                try:
                    torch.set_num_interop_threads(1)
                except Exception:
                    pass
            logger.info(f"[LOCAL-QWEN] Applied PyTorch thread configuration: threads={torch_threads} (interop=1)")

            project_root = Path(__file__).resolve().parent.parent.parent
            env_model_path = os.getenv("MODEL_PATH", "").strip()

            target_path = None

            # 1. Check explicit MODEL_PATH from .env only if compatible with requested model
            if env_model_path:
                cand = Path(env_model_path)
                if not cand.is_absolute():
                    cand = project_root / cand
                short_id = self.model_id.split("/")[-1].lower()
                env_model_id = os.getenv("LOCAL_MODEL", "").strip().lower()
                if cand.exists() and ((cand / "config.json").exists() or any(cand.glob("*.safetensors"))):
                    if short_id in str(cand).lower() or self.model_id.lower() == env_model_id:
                        target_path = str(cand)

            # 2. Check candidate local folder under models/ derived from model_id
            if not target_path:
                short_id = self.model_id.split("/")[-1]
                cand = project_root / "models" / short_id
                if cand.exists() and ((cand / "config.json").exists() or any(cand.glob("*.safetensors"))):
                    target_path = str(cand)

            # 3. Check alias directories under models/ for 0.5B, 1.5B/1B, and 3B
            if not target_path:
                aliases = [
                    "Qwen2.5-0.5B-Instruct",
                    "Qwen2.5-1.5B-Instruct",
                    "Qwen2.5-1B-Instruct",
                    "Qwen2.5-3B-Instruct"
                ]
                m_lower = self.model_id.lower()
                for a in aliases:
                    if a.lower() in m_lower or (("1.5b" in m_lower or "1b" in m_lower) and "1" in a):
                        cand = project_root / "models" / a
                        if cand.exists() and ((cand / "config.json").exists() or any(cand.glob("*.safetensors"))):
                            target_path = str(cand)
                            break

            # 4. Fallback to model_id directly (downloads or loads from Hugging Face cache)
            if not target_path:
                target_path = self.model_id

            # Select optimal dtype: bfloat16 for 1.5B/3B to cut RAM by 50% and prevent page-thrashing; float32 for 0.5B
            chosen_dtype = torch.bfloat16 if ("3b" in self.model_id.lower() or "1.5b" in self.model_id.lower() or "1b" in self.model_id.lower()) else torch.float32
            logger.info(f"[LOCAL-QWEN] Loading '{target_path}' into memory ({chosen_dtype})...")

            try:
                tokenizer = AutoTokenizer.from_pretrained(target_path, local_files_only=True)
            except Exception:
                tokenizer = AutoTokenizer.from_pretrained(target_path)

            try:
                model = AutoModelForCausalLM.from_pretrained(target_path, dtype=chosen_dtype, local_files_only=True)
            except Exception:
                model = AutoModelForCausalLM.from_pretrained(target_path, dtype=chosen_dtype)

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

            # CPU Thread Tuning
            torch_threads = int(os.getenv("TORCH_THREADS", "4"))
            if torch.get_num_threads() != torch_threads:
                torch.set_num_threads(torch_threads)

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
            ttft = streamer.ttft
            prompt_len = model_inputs["input_ids"].shape[-1]
            gen_tokens = outputs[0][prompt_len:]
            text = tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()  # type: ignore

            num_tokens = len(gen_tokens)
            pure_gen_time = max(total_time - ttft, 0.001) if ttft > 0 else total_time
            speed = num_tokens / pure_gen_time if num_tokens > 0 else 0.0
            overall_speed = num_tokens / total_time if total_time > 0 else 0.0

            logger.info(
                f"[LOCAL-QWEN-STATS] TTFT: {ttft:.3f}s | Gen: {pure_gen_time:.2f}s | "
                f"Total: {total_time:.2f}s | Pure Speed: {speed:.1f} tok/s (overall: {overall_speed:.1f}) | Tokens: {num_tokens} (prompt: {prompt_len})"
            )

            return {
                "text": text,
                "ttft": ttft,
                "total_time": total_time,
                "generation_time": pure_gen_time,
                "speed": speed,
                "overall_speed": overall_speed,
                "num_tokens": num_tokens,
                "prompt_tokens": prompt_len
            }
        except Exception as e:
            logger.error(f"[LOCAL-QWEN-GEN-FAILED] Generation error: {e}", exc_info=True)
            return None


class AIService:
    """Dynamic Local In-Memory Qwen SLM AI Service."""
    def __init__(self):
        self.provider: str = DEFAULT_PROVIDER
        self.model_name: str = os.getenv("LOCAL_MODEL", DEFAULT_QWEN_MODEL)
        self.endpoint_url: str = "local-in-memory"
        self.api_key: Optional[str] = None
        logger.info(f"[LOCAL-AI-INIT] Initialized Local Qwen Engine: Model='{self.model_name}' (Offline In-Memory)")

    def set_model(self, model_name: str):
        """Allows dynamically switching the model at runtime, ensuring previous model is unloaded first."""
        if model_name and model_name != self.model_name:
            logger.info(f"[LOCAL-AI-SWITCH] Switching active model from '{self.model_name}' to '{model_name}'")
            LocalQwenEngine.unload_model()
            self.model_name = model_name
            engine = LocalQwenEngine.get_instance(model_name)
            logger.info(f"[LOCAL-AI-SWITCH] Switched active model to: '{self.model_name}'")

    def unload_model(self):
        """Strictly unloads active model from memory and frees RAM."""
        LocalQwenEngine.unload_model()

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
        dynamic_forensic_events = context.get("dynamic_forensic_events", [])
        break_flow = context.get("break_flow")
        line_context = context.get("line_context")
        tx_lifecycle = context.get("tx_lifecycle")
        error_signatures = context.get("error_signatures", [])
        component_breakdown = context.get("component_breakdown", [])
        error_templates = context.get("error_templates", [])
        active_service = context.get('active_service') or context.get('detected_service')

        context_summary = {
            "total_files": overview.get('total_log_files', 0),
            "total_records": overview.get('total_records_processed', 0),
            "total_errors": overview.get('total_error_logs', 0),
            "total_causes": len(causes)
        }
        log_llm_call_start(self.model_name, user_query, context_summary)

        q_lower = user_query.lower()
        dynamic_pruning = os.getenv("DYNAMIC_PROMPT_PRUNING", "True").lower() == "true"

        # Query intent classification for intelligent prompt pruning & token budgeting
        has_forensic = bool(dynamic_forensic_events or break_flow)
        is_forensic_intent = has_forensic or any(k in q_lower for k in [
            "break", "halt", "crash", "restart", "stop", "fail", "failure", "error", "exception",
            "why did", "how did", "what happened", "when did", "investigate", "cause"
        ])
        is_line_intent = "line" in q_lower or bool(line_context)
        is_tx_intent = bool(tx_lifecycle) or any(k in q_lower for k in ["transaction", "tx", "payment", "guid", "txid", "orderid"])
        is_component_intent = any(k in q_lower for k in ["component", "method", "module", "subsystem"])
        is_template_intent = any(k in q_lower for k in ["template", "pattern", "drain", "cluster"])
        is_signature_intent = "signature" in q_lower
        is_count_kpi_intent = any(k in q_lower for k in ["how many", "count", "number of", "total", "sla", "rate", "throughput"])
        is_service_summary_intent = any(k in q_lower for k in ["services", "monitored", "overview", "summary", "pipelines", "status"]) and not is_forensic_intent

        prompt_sections = []

        # 1. System Overview & KPIs (High-density compact summary)
        if dynamic_pruning:
            prompt_sections.append(
                "1. SYSTEM OVERVIEW & KPIS:\n"
                f"- Monitored Pipelines: {len(services)} active | Total Files: {overview.get('total_log_files', 0)} ({overview.get('total_log_lines', 0):,} lines)\n"
                f"- Throughput: {overview.get('total_records_processed', 0):,} records processed ({overview.get('success_rate_percent', 0)}% SLA success)\n"
                f"- System Errors: {overview.get('total_error_logs', 0)} explicit errors | Service Breaks: {overview.get('service_breaks_count', 0)}\n"
                f"- Real-world Date: {overview.get('current_system_date', 'N/A')} | Latest Log Date: {overview.get('latest_log_date', 'N/A')}"
            )
        else:
            prompt_sections.append(
                f"1. SYSTEM OVERVIEW & KPIS:\n"
                f"- Total Log Files: {overview.get('total_log_files', 0)}\n"
                f"- Total Log Lines: {overview.get('total_log_lines', 0):,}\n"
                f"- Total Records Processed: {overview.get('total_records_processed', 0):,}\n"
                f"- Successful Records: {overview.get('successful_records', 0):,}\n"
                f"- Failed Records: {overview.get('failed_records', 0):,}\n"
                f"- Overall System Success Rate: {overview.get('success_rate_percent', 0)}%\n"
                f"- Total Explicit ERROR Logs: {overview.get('total_error_logs', 0)}\n"
                f"- Service Breaks / Crashes: {overview.get('service_breaks_count', 0)}\n"
                f"- Dates Found in Logs: {overview.get('dates_available', [])}\n"
                f"- Latest Recorded Date in Logs: {overview.get('latest_log_date', 'N/A')}\n"
                f"- Today's Real-world Date: {overview.get('current_system_date', 'N/A')}"
            )

        # 2. Service Telemetry (Pruned to targeted service for forensic queries; full otherwise)
        if dynamic_pruning and (is_forensic_intent or is_line_intent or is_tx_intent):
            target_svc = active_service
            if not target_svc and dynamic_forensic_events:
                target_svc = dynamic_forensic_events[0]["target"].get("service")
            if target_svc:
                s_obj = next((s for s in services if s.get('name', '').lower() == target_svc.lower()), None)
                if s_obj:
                    notes = "; ".join(s_obj.get('key_notes', []))
                    prompt_sections.append(
                        f"2. FOCUSED SERVICE TELEMETRY:\n"
                        f"• Service: {s_obj.get('name')} (File: {s_obj.get('file_name')})\n"
                        f"  Status: {s_obj.get('status')} | Processed: {s_obj.get('records_processed', 0):,} | Errors: {s_obj.get('errors_count', 0)}\n"
                        f"  Operational Notes: {notes}"
                    )
        else:
            svc_lines = []
            for s in services:
                notes = "; ".join(s.get('key_notes', []))
                svc_lines.append(
                    f"• Service: {s.get('name')} (File: {s.get('file_name')})\n"
                    f"  Status: {s.get('status')} | Records Processed: {s.get('records_processed', 0):,} | "
                    f"Successful: {s.get('successful_records', 0):,} | Failed/Errors: {s.get('failed_records', 0)} / {s.get('errors_count', 0)}\n"
                    f"  Operational Notes: {notes}"
                )
            if svc_lines:
                prompt_sections.append("2. ALL MONITORED SERVICES:\n" + "\n\n".join(svc_lines))

        # 3. Dynamic Forensic Evidence & Surrounding Execution Context
        if dynamic_forensic_events:
            ev_lines = ["3. DYNAMIC FORENSIC EVIDENCE & SURROUNDING EXECUTION CONTEXT (AUTONOMOUS LOG DISCOVERY):"]
            for idx, item in enumerate(dynamic_forensic_events[:2], 1):
                t = item["target"]
                prec = item.get("preceding", [])
                succ = item.get("succeeding", [])
                is_break = item.get("is_break_event", False)
                ev_lines.append(
                    f"--- [Forensic Discovery #{idx}{' (CRITICAL BREAK / HALT)' if is_break else ''}] ---\n"
                    f"Service: {t.get('service')} (File: {t.get('file_name')} | Line: {t.get('line_number')})\n"
                    f"Timestamp: {t.get('timestamp')} | Level: {t.get('level')} | Status: {t.get('status')} | Component: {t.get('component')}\n"
                    f"Message: {t.get('message', '').strip()}"
                )
                if t.get("transaction_id"):
                    ev_lines.append(f"Transaction ID: {t.get('transaction_id')}")
                if t.get("stack_trace"):
                    ev_lines.append(f"Stack Trace: {t.get('stack_trace', '')[:250]}")
                if prec:
                    ev_lines.append("Preceding Execution Flow in Batch:")
                    for p in prec:
                        ev_lines.append(f"  Line {p.get('line_number')}: [{p.get('time')}] [{p.get('level')}] [{p.get('component')}]: {p.get('message', '')[:110]}")
                if succ:
                    ev_lines.append("Succeeding Execution Flow in Batch:")
                    for s in succ:
                        ev_lines.append(f"  Line {s.get('line_number')}: [{s.get('time')}] [{s.get('level')}] [{s.get('component')}]: {s.get('message', '')[:110]}")
            prompt_sections.append("\n".join(ev_lines))
        elif break_flow:
            be = break_flow.get("break_entry", {})
            pre = break_flow.get("preceding_flow", [])
            bf_lines = [
                "3. CRITICAL SERVICE BREAK & FLOW RECONSTRUCTION:",
                f"- Halted Service: {be.get('service')} (Line {be.get('line_number')} in {be.get('file_name')})",
                f"- Break Timestamp: {be.get('timestamp')}",
                f"- Exception / Halting Error: {be.get('message', '').splitlines()[0]}"
            ]
            if be.get("transaction_id"):
                bf_lines.append(f"- Impacted Transaction ID: {be.get('transaction_id')}")
            if pre:
                bf_lines.append("- Preceding execution flow in batch:")
                for p in pre:
                    bf_lines.append(f"  * [{p.get('time')}] [{p.get('component')}]: {p.get('message', '')[:120]}")
            prompt_sections.append("\n".join(bf_lines))

        # 4. Line Context Window (if line inspection requested)
        if line_context and line_context.get("target") and is_line_intent:
            t = line_context["target"]
            prec = line_context.get("preceding", [])
            succ = line_context.get("succeeding", [])
            lc_lines = [f"4. EXACT LINE INSPECTION (File: {t.get('file_name')}):"]
            for p in prec:
                lc_lines.append(f"   Line {p.get('line_number')}: [{p.get('time')}] [{p.get('level')}] {p.get('message', '')[:110]}")
            lc_lines.append(f"▶ TARGET LINE {t.get('line_number')}: [{t.get('time')}] [{t.get('level')}] {t.get('message', '')}")
            if t.get('stack_trace'):
                lc_lines.append(f"   Stack Trace: {t.get('stack_trace')[:250]}")
            for s in succ:
                lc_lines.append(f"   Line {s.get('line_number')}: [{s.get('time')}] [{s.get('level')}] {s.get('message', '')[:110]}")
            prompt_sections.append("\n".join(lc_lines))

        # 5. Transaction Lifecycle (if transaction requested)
        if tx_lifecycle and is_tx_intent:
            target_tx = context.get("target_tx_id", "Unknown")
            tx_lines = [f"5. COMPLETE TRANSACTION LIFECYCLE FOR {target_tx}:"]
            for idx, event in enumerate(tx_lifecycle[:8], 1):
                tx_lines.append(f"   {idx}. Line {event.get('line_number')} in {event.get('file_name')} [{event.get('timestamp')}] [{event.get('service')}]: {event.get('message', '')[:120]}")
            prompt_sections.append("\n".join(tx_lines))

        # 6. RCA Causes (Included for RCA/system queries, or pruned if forensic evidence is already complete)
        if causes and (not dynamic_pruning or not is_forensic_intent or is_service_summary_intent):
            cause_lines = ["6. IDENTIFIED ROOT CAUSE ANALYSIS (RCA) CLUSTERS:"]
            for c in causes[:2]:
                cause_lines.append(
                    f"• [{c.get('cause_id')}] {c.get('title')} ({c.get('count')} occurrences):\n"
                    f"  Service: {c.get('service')} | Root Cause: {c.get('root_cause')}\n"
                    f"  Recommendation: {c.get('recommendation')}"
                )
            prompt_sections.append("\n".join(cause_lines))

        # 7. Recent Errors (Only if no forensic events found)
        if latest_errors and not dynamic_forensic_events and not break_flow:
            err_lines = ["7. RECENT ERROR LOG ENTRIES:"]
            for e in latest_errors[:3]:
                err_lines.append(f"• [{e.get('timestamp')}] [{e.get('service')}] {e.get('message')[:160]}")
            prompt_sections.append("\n".join(err_lines))

        # 8. Component Activity (Only if component intent or not dynamic pruning)
        if component_breakdown and (is_component_intent or not dynamic_pruning):
            comp_lines = ["8. COMPONENT ACTIVITY & RELIABILITY METRICS:"]
            for comp in component_breakdown[:5]:
                comp_lines.append(f"• {comp.get('component')} ({comp.get('service')}): {comp.get('total_events')} events | {comp.get('error_events')} errors ({comp.get('error_rate_pct')}% error rate)")
            prompt_sections.append("\n".join(comp_lines))

        # 9. Drain3 Error Templates (Only if template intent or not dynamic pruning)
        if error_templates and (is_template_intent or not dynamic_pruning):
            tmpl_lines = ["9. DRAIN3 MINED STRUCTURAL ERROR TEMPLATES:"]
            for t in error_templates[:4]:
                tmpl_lines.append(f"• [Template #{t.get('cluster_id')}] ({t.get('count')} in {t.get('service')}): {t.get('template')}")
            prompt_sections.append("\n".join(tmpl_lines))

        # 10. Error Signatures (Only if signature intent or not dynamic pruning)
        if error_signatures and (is_signature_intent or not dynamic_pruning):
            sig_lines = ["10. AGGREGATED ERROR SIGNATURES:"]
            for sig in error_signatures[:4]:
                sig_lines.append(f"• [{sig.get('service')}] {sig.get('error_type')} ({sig.get('occurrence_count')} hits): {sig.get('sample_message')[:120]}")
            prompt_sections.append("\n".join(sig_lines))

        # Scope instructions
        if active_service:
            scope_instructions = f"*** ACTIVE USER FOCUS SCOPE: {active_service} ***\nAnswer specifically within the context of '{active_service}'."
        else:
            scope_instructions = f"*** ACTIVE USER FOCUS SCOPE: ALL SERVICES ***\nCover all {len(services)} active pipelines."

        ground_truth_body = "\n\n".join(prompt_sections)

        system_prompt = f"""You are an Autonomous Site Reliability Engineering (SRE) & Observability AI Agent powered by Local Qwen ({self.model_name}).
Analyze the service execution logs, diagnostic metrics, record throughput, and errors.
Rely strictly on the verified ground-truth context provided below.

====================== LIVE GROUND TRUTH FROM INGESTED LOGS ======================
{ground_truth_body}
==================================================================================

{scope_instructions}

CORE INSTRUCTIONS:
1. Synthesize a concise, direct, helpful, professional response in GitHub-flavored Markdown.
2. Rely strictly on the ground truth provided above. Cite specific service names, filenames, timestamps, line numbers, and error messages.
3. If the user asks why/how a service broke or halted, cite the exact exception, line number, timestamp, and preceding events from the forensic evidence.
4. Be concise and eliminate fluff.
"""

        # Direct focus hint
        direct_hints = []
        if dynamic_forensic_events:
            top_ev = dynamic_forensic_events[0]["target"]
            direct_hints.append(
                f"Direct Ground Truth: Matched operational log event in '{top_ev.get('service')}' at line {top_ev.get('line_number')} "
                f"([{top_ev.get('level')}], Status: {top_ev.get('status')}): \"{top_ev.get('message', '')[:100]}\"."
            )
        if is_component_intent and component_breakdown:
            top_err_comp = max(component_breakdown, key=lambda c: c.get("error_events", 0))
            direct_hints.append(f"Direct Ground Truth: Top error component is '{top_err_comp.get('component')}' in '{top_err_comp.get('service')}' with {top_err_comp.get('error_events')} errors.")
        if is_line_intent and line_context and line_context.get("target"):
            t = line_context["target"]
            direct_hints.append(f"Direct Ground Truth: Line {t.get('line_number')} in '{t.get('file_name')}' is: \"{t.get('message', '')[:100]}\".")
        if is_tx_intent and tx_lifecycle:
            direct_hints.append(f"Direct Ground Truth: Transaction '{context.get('target_tx_id')}' has {len(tx_lifecycle)} recorded events.")

        augmented_user_query = f"{user_query}\n\n[Ground-Truth Facts from Database: {' '.join(direct_hints)}]" if direct_hints else user_query

        # Dynamic max token budgeting
        env_max = os.getenv("MAX_NEW_TOKENS")
        configured_max = int(env_max) if env_max and env_max.isdigit() else 220
        if any(k in q_lower for k in ["how did", "why did", "break", "halt", "line", "status", "count", "latest error"]):
            budget_max_tokens = min(configured_max, 95)
        elif is_component_intent or is_template_intent:
            budget_max_tokens = min(configured_max, 120)
        else:
            budget_max_tokens = min(configured_max, 180)

        try:
            logger.info(f"[LOCAL-QWEN-CALL] Dispatching query to Local In-Memory Qwen engine ({self.model_name}) | Budget Tokens: {budget_max_tokens}...")
            engine = LocalQwenEngine.get_instance(self.model_name)
            res = engine.generate(system_prompt, augmented_user_query, max_new_tokens=budget_max_tokens)
            if res and res.get("text"):
                latency_ms = res["total_time"] * 1000.0
                log_llm_call_complete(self.model_name, latency_ms, len(res["text"]), None)
                if return_metrics:
                    return {
                        "text": res["text"],
                        "ttft_s": res.get("ttft", 0.0),
                        "generation_time_s": res.get("generation_time", res.get("total_time", 0.0)),
                        "total_time_s": res.get("total_time", 0.0),
                        "speed": res.get("speed", 0.0),
                        "overall_speed": res.get("overall_speed", 0.0),
                        "num_tokens": res.get("num_tokens", 0),
                        "prompt_tokens": res.get("prompt_tokens", 0)
                    }
                return res["text"]
            logger.warning("[LOCAL-QWEN-EMPTY] Qwen local generation returned empty.")
            return None
        except Exception as e:
            logger.error(f"[LOCAL-QWEN-ERROR] Error executing query with Local Qwen: {e}", exc_info=True)
            return None

# Singleton instance
ai_service = AIService()
