import re
import time
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

from app.parser import LogParser, parser
from app.logger import logger
from app.models import (
    LogEntry,
    OverviewMetrics,
    ServiceSummary,
    ErrorCauseSummary,
)

class LogAnalyzer:
    def __init__(self, log_parser: LogParser = parser):
        self.parser = log_parser
        self._metrics_cache: Dict[str, Tuple[int, int, int]] = {}
        self._metrics_len_cache: Dict[str, int] = {}
        self._break_cache: Dict[str, Optional[LogEntry]] = {}
        self._cached_overview: Optional[OverviewMetrics] = None
        self._last_entries_len: int = 0

    def _calculate_file_metrics(self, file_name: str, entries: List[LogEntry]) -> Tuple[int, int, int]:
        """
        Dynamically extracts total records processed, successful, and failed for a set of log entries.
        Cached per file.
        """
        if file_name in self._metrics_cache and len(entries) == self._metrics_len_cache.get(file_name, 0):
            return self._metrics_cache[file_name]

        start_t = time.time()
        messages = [e.message for e in entries]
        
        # 1. Operational granular successes (generic regex across any domain)
        re_succ = re.compile(
            r'(?:record(?:s)?\s+(?:inserted|added|created|processed|written|exported)|'
            r'added\s+in\s+database|writing\s+operation|approved|completed|'
            r'successfully\s*:\s*true|file uploaded successfully|processed successfully|'
            r'status\s*:\s*(?:success|ok|200))',
            re.I
        )
        operational_succ = sum(1 for m in messages if re_succ.search(m))
        
        # 2. Operational failures & unhandled errors (generic regex)
        re_fail = re.compile(
            r'(?:updated to failed|operation failed|transaction failed|status\s*:\s*failed|rejected|failure|unhandled)',
            re.I
        )
        failed_markers = sum(1 for m in messages if re_fail.search(m))
        error_entries = [e for e in entries if e.level in ["ERROR", "FATAL", "CRITICAL"]]
        unhandled_errors = len(error_entries)

        # 3. Explicit batch / item counts (generic regex for any domain)
        re_batch = re.compile(
            r'(?:total\s+(?:records|items|transactions|payments|events|rows|files)\s*:\s*|(?:[a-zA-Z0-9_]+)\s+Count\s*[:=]\s*)(\d+)',
            re.I
        )
        batch_counts = []
        for m in messages:
            counts = re_batch.findall(m)
            if counts:
                batch_counts.extend([int(c) for c in counts])
        max_batch = max(batch_counts) if batch_counts else 0

        # Dynamic Synthesis
        if operational_succ > 0:
            succ = operational_succ
            fail = failed_markers + (unhandled_errors // 2 if unhandled_errors > 1 else unhandled_errors)
            total = succ + fail
        elif max_batch > 0:
            succ = max_batch
            fail = 1 if unhandled_errors > 0 else 0
            total = succ + fail
        else:
            succ = sum(1 for e in entries if e.level in ["INFO", "DEBUG"])
            fail = unhandled_errors + failed_markers
            total = succ + fail

        res = (total, succ, fail)
        self._metrics_cache[file_name] = res
        self._metrics_len_cache[file_name] = len(entries)
        
        calc_ms = (time.time() - start_t) * 1000.0
        logger.debug(
            f"[ANALYZER-METRICS] '{file_name}': processed={total:,}, succ={succ:,}, fail={fail:,} (calc: {calc_ms:.1f}ms)"
        )
        return res

    def _detect_service_break(self, file_name: str, entries: List[LogEntry]) -> Optional[LogEntry]:
        """
        Dynamically detects if a service execution crashed or broke before completion.
        """
        if file_name in self._break_cache:
            return self._break_cache[file_name]

        re_halt = re.compile(r'(?:total\s+\w+\s*:\s*0|service end|batch aborted|process terminated|halt|service break)', re.I)
        re_fatal = re.compile(r'(?:system\.exception|unhandled|fatal|panic|critical)', re.I)

        res = None
        for idx, e in enumerate(entries):
            if e.level in ["ERROR", "FATAL", "CRITICAL"]:
                subsequent = entries[idx+1:idx+6]
                sub_text = " ".join([s.message for s in subsequent])
                if re_halt.search(sub_text) or re_fatal.search(e.message):
                    res = e
                    break

        self._break_cache[file_name] = res
        if res:
            logger.warning(f"[ANALYZER-BREAK-DETECTED] '{file_name}' suffered service break at {res.timestamp}: {res.message[:120]}")
        return res

    def get_overview(self, service: Optional[str] = None) -> OverviewMetrics:
        entries = self.parser.parse_all()
        files = self.parser.get_log_files()

        # Group entries by file once
        entries_by_file: Dict[str, List[LogEntry]] = defaultdict(list)
        for e in entries:
            entries_by_file[e.file_name].append(e)

        if not service or service == "ALL":
            if self._cached_overview and len(entries) == self._last_entries_len:
                logger.debug("[ANALYZER-CACHE-HIT] Serving OverviewMetrics from cache.")
                return self._cached_overview

            start_t = time.time()
            logger.info(f"[ANALYZER-OVERVIEW-START] Synthesizing system KPIs across {len(files)} files and {len(entries)} lines")

            dates = sorted(list(set(e.date for e in entries)))
            latest_date = dates[-1] if dates else "N/A"
            current_system_date = datetime.now().strftime("%Y-%m-%d")

            records_processed = 0
            successful_records = 0
            failed_records = 0
            error_logs_count = sum(1 for e in entries if e.level == "ERROR")
            service_breaks_count = 0

            for f in files:
                svc_entries = entries_by_file.get(f.name, [])
                tot, succ, fail = self._calculate_file_metrics(f.name, svc_entries)
                records_processed += tot
                successful_records += succ
                failed_records += fail

                if self._detect_service_break(f.name, svc_entries):
                    service_breaks_count += 1

            success_rate = (successful_records / records_processed * 100) if records_processed > 0 else 100.0

            overview = OverviewMetrics(
                total_log_files=len(files),
                total_log_lines=len(entries),
                total_records_processed=records_processed,
                successful_records=successful_records,
                failed_records=failed_records,
                success_rate_percent=round(success_rate, 2),
                total_error_logs=error_logs_count,
                service_breaks_count=service_breaks_count,
                services_count=len(set(e.service for e in entries)),
                dates_available=dates,
                latest_log_date=latest_date,
                current_system_date=current_system_date
            )

            self._cached_overview = overview
            self._last_entries_len = len(entries)
            
            dur_ms = (time.time() - start_t) * 1000.0
            logger.info(
                f"[ANALYZER-OVERVIEW-COMPLETE] Processed: {records_processed:,} | Succ: {successful_records:,} "
                f"({overview.success_rate_percent}%) | Fail: {failed_records:,} | Errors: {error_logs_count} | Breaks: {service_breaks_count} "
                f"(computed in {dur_ms:.1f}ms)"
            )
            return overview
        else:
            # Service-specific overview
            svc_entries = [e for e in entries if e.service == service]
            svc_files = [f for f in files if any(e.service == service for e in entries_by_file.get(f.name, []))]

            dates = sorted(list(set(e.date for e in svc_entries)))
            latest_date = dates[-1] if dates else "N/A"
            current_system_date = datetime.now().strftime("%Y-%m-%d")

            records_processed = 0
            successful_records = 0
            failed_records = 0
            error_logs_count = sum(1 for e in svc_entries if e.level == "ERROR")
            service_breaks_count = 0

            for f in svc_files:
                f_entries = entries_by_file.get(f.name, [])
                tot, succ, fail = self._calculate_file_metrics(f.name, f_entries)
                records_processed += tot
                successful_records += succ
                failed_records += fail

                if self._detect_service_break(f.name, f_entries):
                    service_breaks_count += 1

            success_rate = (successful_records / records_processed * 100) if records_processed > 0 else 100.0

            return OverviewMetrics(
                total_log_files=len(svc_files),
                total_log_lines=len(svc_entries),
                total_records_processed=records_processed,
                successful_records=successful_records,
                failed_records=failed_records,
                success_rate_percent=round(success_rate, 2),
                total_error_logs=error_logs_count,
                service_breaks_count=service_breaks_count,
                services_count=1,
                dates_available=dates,
                latest_log_date=latest_date,
                current_system_date=current_system_date
            )

    def get_services_summary(self) -> List[ServiceSummary]:
        start_t = time.time()
        entries = self.parser.parse_all()
        files = self.parser.get_log_files()
        summaries: List[ServiceSummary] = []

        entries_by_file: Dict[str, List[LogEntry]] = defaultdict(list)
        for e in entries:
            entries_by_file[e.file_name].append(e)

        for f in files:
            svc_entries = entries_by_file.get(f.name, [])
            total_lines = len(svc_entries)
            error_count = sum(1 for e in svc_entries if e.level == "ERROR")
            warn_count = sum(1 for e in svc_entries if e.level in ["WARN", "WARNING"])
            last_entry = svc_entries[-1] if svc_entries else None
            last_run = last_entry.timestamp if last_entry else "N/A"
            svc_name = svc_entries[0].service if svc_entries else self.parser.detect_service_name(f.name)

            tot, succ, fail = self._calculate_file_metrics(f.name, svc_entries)
            breaking_error = self._detect_service_break(f.name, svc_entries)

            if breaking_error:
                status = "CRITICAL_BREAK"
            elif error_count > 0:
                status = "WARNING"
            elif fail > 0:
                status = "HEALTHY"
            else:
                status = "OPTIMAL"

            # Dynamic output files extraction
            output_files = []
            for e in svc_entries:
                if "output file name :" in e.message:
                    m = re.search(r'output file name\s*:\s*([^\r\n|]+)', e.message)
                    if m:
                        fname = m.group(1).strip()
                        if fname and fname not in output_files:
                            output_files.append(fname)

            # Dynamic key notes synthesis
            key_notes = []
            if breaking_error:
                first_line = breaking_error.message.split("\n")[0]
                key_notes.append(f"Service broke due to: {first_line[:100]}")
            
            entity_types = list(set(re.findall(r'(?:BillType|DataType|RecordType|Category|Type|Action|EntityType|Resource|Table|Queue|Topic)\s*[:= ]\s*([A-Za-z0-9_-]+)', " ".join(e.message for e in svc_entries), re.I)))
            if entity_types:
                key_notes.append(f"Entity types processed: {', '.join(entity_types)}.")

            batches = len(re.findall(r'Service Start\b', " ".join(e.message for e in svc_entries), re.I))
            if batches > 1:
                key_notes.append(f"Executed across {batches} scheduled batches.")

            if succ > 0:
                key_notes.append(f"{succ:,} operations completed successfully.")
            if fail > 0:
                key_notes.append(f"{fail:,} operations failed or rejected.")

            if not key_notes:
                key_notes.append(f"Processed {tot:,} records with status {status}.")

            summaries.append(ServiceSummary(
                name=svc_name,
                file_name=f.name,
                status=status,
                last_run=last_run,
                total_lines=total_lines,
                records_processed=tot,
                successful_records=succ,
                failed_records=fail,
                errors_count=error_count,
                warnings_count=warn_count,
                output_files=output_files,
                key_notes=key_notes
            ))

        dur_ms = (time.time() - start_t) * 1000.0
        logger.info(f"[ANALYZER-SERVICES-COMPLETE] Generated summaries for {len(summaries)} service(s) in {dur_ms:.1f}ms")
        return summaries

    def get_error_causes(self, service: Optional[str] = None) -> List[ErrorCauseSummary]:
        start_t = time.time()
        entries = self.parser.parse_all()
        error_entries = [e for e in entries if e.level == "ERROR"]

        # Dynamic error clustering
        clusters: Dict[str, List[LogEntry]] = defaultdict(list)
        for e in error_entries:
            exc_m = re.search(r'([A-Za-z0-9_.]*(?:Exception|Error|Fault))', e.message)
            exc_type = exc_m.group(1) if exc_m else "GeneralError"
            
            first_line = e.message.split("\n")[0]
            norm = re.sub(r'\b[A-Za-z0-9]{12,}\b', '<ID>', first_line)
            norm = re.sub(r'\b\d+\b', '<NUM>', norm)
            key = f"{e.service}:{exc_type}:{norm[:65]}"
            clusters[key].append(e)

        causes: List[ErrorCauseSummary] = []
        cause_idx = 1

        for key, grp_entries in clusters.items():
            sample_entry = grp_entries[0]
            svc = sample_entry.service
            first_line = sample_entry.message.split("\n")[0]
            
            exc_m = re.search(r'([A-Za-z0-9_.]*(?:Exception|Error|Fault))', sample_entry.message)
            exc_type = exc_m.group(1) if exc_m else "ApplicationException"

            is_break = any(self._detect_service_break(sample_entry.file_name, [e]) is not None for e in grp_entries)

            all_text = " ".join([e.message for e in grp_entries])
            tx_ids = list(set(re.findall(r'(?:TransactionId|paymentid|Account Number|Invoice)\s*[:=]\s*["\']?([A-Za-z0-9_-]+)', all_text, re.I)))[:8]

            if "FormatException" in exc_type or "Base64" in first_line:
                title = f"Base64 / String Format Exception in {svc}"
                root_cause = "Non-encoded or invalid string payload was passed directly to a format converter (e.g. Convert.FromBase64String) without validation."
                recommendation = "Validate string format / Base-64 signature before decoding, or wrap conversion in a defensive try/catch block."
            elif "NotFound" in first_line or "Not Found" in first_line or is_break:
                title = f"Service Halting Exception: Entity Not Found in {svc}"
                root_cause = f"Repository queried for a record that was absent from the database, throwing an unhandled {exc_type} that aborted the batch."
                recommendation = "Implement defensive null/existence checking before accessing entity records, and isolate records to prevent whole-batch failure."
            elif "Timeout" in exc_type or "Connection" in exc_type:
                title = f"Network / Timeout Error in {svc}"
                root_cause = "Remote endpoint or database connection failed or timed out during execution."
                recommendation = "Check remote endpoint health and configure resilient exponential backoff retry policies."
            else:
                title = f"{exc_type} in {svc}"
                root_cause = f"Application encountered: {first_line[:120]}"
                recommendation = "Inspect application stack trace at the referenced file and line number and add defensive handling."

            causes.append(ErrorCauseSummary(
                cause_id=f"ERR-{cause_idx:02d}",
                title=title,
                error_type=exc_type + (" (Critical Break)" if is_break else ""),
                service=svc,
                count=len(grp_entries),
                affected_transactions=tx_ids,
                description=f"Recorded {len(grp_entries)} occurrence(s) in {svc}. Message: {first_line[:140]}.",
                root_cause=root_cause,
                recommendation=recommendation,
                sample_stack_trace=sample_entry.stack_trace or first_line
            ))
            cause_idx += 1

        # Check for business rejections / return codes dynamically
        re_biz = re.compile(r'(?:returncode|rejectcode|failurecode|updated to failed)', re.I)
        biz_failed_entries = [e for e in entries if re_biz.search(e.message)]
        if biz_failed_entries:
            all_biz_text = " ".join([e.message for e in biz_failed_entries])
            return_codes = list(set(re.findall(r'(?:returncode|rejectcode|reason)\s*[:=]\s*["\']?([A-Za-z0-9]+)["\']?', all_biz_text, re.I)))
            tx_ids = list(set(re.findall(r'(?:TransactionId|RecordId|OrderId|paymentid)\s*[:=]?\s*["\']?([A-Za-z0-9_-]+)', all_biz_text, re.I)))[:8]
            
            codes_str = ", ".join(return_codes) if return_codes else "Business Rejections"
            causes.append(ErrorCauseSummary(
                cause_id=f"ERR-{cause_idx:02d}",
                title=f"Business Network Return Failures ({codes_str})",
                error_type="Business Rejection (External Flow Return)",
                service=biz_failed_entries[0].service,
                count=len(biz_failed_entries),
                affected_transactions=tx_ids,
                description=f"Received {len(biz_failed_entries)} business network rejection(s) with return codes: {codes_str}.",
                root_cause="External network/clearinghouse rejects or business rule exceptions. The service handled these by updating transaction status to failed.",
                recommendation="Investigate business reject codes with counterparties or notify originating parties to remediate account/data issues.",
                sample_stack_trace="External Network Return (No software stack trace)."
            ))

        # Filter by service if specified
        if service and service != "ALL":
            causes = [c for c in causes if c.service == service]

        dur_ms = (time.time() - start_t) * 1000.0
        logger.info(f"[ANALYZER-RCA-COMPLETE] Discovered {len(causes)} root causes (service={service}) in {dur_ms:.1f}ms")
        return causes

    def get_timeline(self, service: Optional[str] = None) -> List[Dict[str, Any]]:
        entries = self.parser.parse_all()
        if service and service != "ALL":
            entries = [e for e in entries if e.service == service]

        buckets = defaultdict(lambda: {"total": 0, "errors": 0, "infos": 0, "debugs": 0})

        for e in entries:
            hour = e.time.split(":")[0] if ":" in e.time else "00"
            key = f"{e.date} {hour}:00"
            buckets[key]["total"] += 1
            if e.level == "ERROR":
                buckets[key]["errors"] += 1
            elif e.level == "INFO":
                buckets[key]["infos"] += 1
            elif e.level == "DEBUG":
                buckets[key]["debugs"] += 1

        timeline = []
        for k in sorted(buckets.keys()):
            timeline.append({
                "time_bucket": k,
                **buckets[k]
            })
        logger.debug(f"[ANALYZER-TIMELINE] Generated {len(timeline)} chronological timeline buckets (service={service}).")
        return timeline

analyzer = LogAnalyzer()
