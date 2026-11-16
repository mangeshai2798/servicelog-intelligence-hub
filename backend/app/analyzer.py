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
        self._cached_services: Optional[List[ServiceSummary]] = None
        self._cached_causes: Dict[str, List[ErrorCauseSummary]] = {}
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

    def clear_cache(self):
        """Clears all in-memory caches when new logs are ingested."""
        self._cached_overview = None
        self._cached_services = None
        self._cached_causes.clear()
        self._metrics_cache.clear()
        self._metrics_len_cache.clear()
        self._break_cache.clear()
        self._last_entries_len = 0
        logger.debug("[ANALYZER-CACHE] In-memory analysis caches cleared.")

    def get_overview(self, service: Optional[str] = None) -> OverviewMetrics:
        """
        Retrieves system KPIs directly from indexed SQLite database.
        Zero multi-file parsing or regex iteration.
        """
        from app.db import get_overview_from_db
        if not service or service.upper() == "ALL":
            if self._cached_overview is not None:
                logger.debug("[ANALYZER-CACHE-HIT] Serving OverviewMetrics from cache.")
                return self._cached_overview
            start_t = time.time()
            overview = get_overview_from_db(service=None)
            self._cached_overview = overview
            dur_ms = (time.time() - start_t) * 1000.0
            logger.info(f"[ANALYZER-OVERVIEW-COMPLETE] Generated Overview from DB in {dur_ms:.1f}ms")
            return overview
        return get_overview_from_db(service=service)

    def get_services_summary(self) -> List[ServiceSummary]:
        """
        Retrieves service summaries directly from indexed SQLite database.
        Zero multi-file parsing or regex iteration.
        """
        from app.db import get_services_summary_from_db
        if self._cached_services is not None:
            logger.debug("[ANALYZER-CACHE-HIT] Serving ServiceSummary from cache.")
            return self._cached_services
        start_t = time.time()
        summaries = get_services_summary_from_db()
        self._cached_services = summaries
        dur_ms = (time.time() - start_t) * 1000.0
        logger.info(f"[ANALYZER-SERVICES-COMPLETE] Generated summaries for {len(summaries)} service(s) from DB in {dur_ms:.1f}ms")
        return summaries

    def get_error_causes(self, service: Optional[str] = None) -> List[ErrorCauseSummary]:
        """
        Discovers error causes directly using SQLite indexed queries and template clusters.
        Zero multi-file parsing or regex iteration.
        """
        from app.db import get_error_causes_from_db
        cache_key = (service or "ALL").lower()
        if cache_key in self._cached_causes:
            logger.debug(f"[ANALYZER-CACHE-HIT] Serving ErrorCauses for '{cache_key}' from cache.")
            return self._cached_causes[cache_key]
        start_t = time.time()
        causes = get_error_causes_from_db(service=service)
        self._cached_causes[cache_key] = causes
        dur_ms = (time.time() - start_t) * 1000.0
        logger.info(f"[ANALYZER-RCA-COMPLETE] Discovered {len(causes)} root causes (service={service}) from DB in {dur_ms:.1f}ms")
        return causes

    def get_timeline(self, service: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Generates chronological timeline buckets directly from indexed SQLite database.
        """
        from app.db import get_timeline_from_db
        return get_timeline_from_db(service=service)

analyzer = LogAnalyzer()
