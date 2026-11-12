import os
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.config import LOGS_DIR
from app.models import LogEntry
from app.logger import logger

class LogParser:
    def __init__(self, logs_dir: Path = LOGS_DIR):
        self.logs_dir = Path(logs_dir)
        self.cached_entries: List[LogEntry] = []
        self._last_modified_times: Dict[str, float] = {}

    def get_log_files(self) -> List[Path]:
        """Find all service .log files in logs directory, sorted by name, ignoring internal backend logs."""
        if not self.logs_dir.exists():
            logger.warning(f"[PARSER-SCAN] Logs directory does not exist: {self.logs_dir}")
            return []
        
        all_files = list(self.logs_dir.glob("*.log"))
        
        # Graceful fallback: if logs_dir is empty and BASE_DIR has .log files, include them
        from app.config import BASE_DIR
        if not all_files and self.logs_dir != BASE_DIR and BASE_DIR.exists():
            all_files = list(BASE_DIR.glob("*.log"))

        # Exclude backend internal execution logs and temporary test files
        ignored_names = {"backend.log", "system.log", "app.log", "access.log"}
        files = [
            f for f in all_files 
            if f.name.lower() not in ignored_names and not f.name.lower().startswith("backend")
        ]
        files.sort(key=lambda p: p.name)
        return files

    def needs_reparse(self) -> bool:
        """Check if any file was modified, added, or removed."""
        current_files = self.get_log_files()
        if len(current_files) != len(self._last_modified_times):
            logger.info(
                f"[PARSER-CACHE-CHECK] File count changed: current={len(current_files)}, "
                f"cached={len(self._last_modified_times)}. Reparse required."
            )
            return True
            
        for f in current_files:
            mtime = f.stat().st_mtime
            if f.name not in self._last_modified_times:
                logger.info(f"[PARSER-CACHE-CHECK] New file discovered: '{f.name}'. Reparse required.")
                return True
            if self._last_modified_times[f.name] != mtime:
                logger.info(f"[PARSER-CACHE-CHECK] File modified: '{f.name}' (mtime: {mtime}). Reparse required.")
                return True
                
        return False

    def detect_service_name(self, file_name: str, sample_text: str = "") -> str:
        """
        Dynamically extracts service name from log content lifecycle markers or filename.
        No hardcoded service names.
        """
        if sample_text:
            # 1. Look for explicit Service Start / lifecycle pattern
            m = re.search(r'([A-Za-z0-9_]+)\s+Service\s+(?:Start|End|is Working|Method)', sample_text, re.I)
            if m:
                svc = m.group(1).strip()
                logger.debug(f"[PARSER-SERVICE-DETECT] '{file_name}' matched lifecycle pattern -> '{svc}'")
                return svc
            
            # 2. Look for ComponentService or ServiceName in namespace
            m2 = re.search(r'([A-Za-z0-9_]+Service)\b', sample_text)
            if m2:
                svc = m2.group(1).strip()
                logger.debug(f"[PARSER-SERVICE-DETECT] '{file_name}' matched namespace pattern -> '{svc}'")
                return svc

        # 3. Derive dynamically from filename (strip date prefixes, log- prefix, and extension)
        clean_stem = re.sub(r'^log[-_]?\d{4}[-_]\d{2}[-_]\d{2}[-_]?', '', file_name, flags=re.I)
        clean_stem = re.sub(r'\.log$', '', clean_stem, flags=re.I)
        clean_stem = re.sub(r'[-_]', ' ', clean_stem).strip()
        
        # CamelCase / PascalCase or title
        if clean_stem:
            words = clean_stem.split()
            svc = "".join([w.capitalize() for w in words]) if len(words) > 1 else clean_stem
            logger.debug(f"[PARSER-SERVICE-DETECT] '{file_name}' derived from filename -> '{svc}'")
            return svc
        
        fallback_svc = Path(file_name).stem
        logger.debug(f"[PARSER-SERVICE-DETECT] '{file_name}' using fallback stem -> '{fallback_svc}'")
        return fallback_svc

    def parse_all(self, force: bool = False) -> List[LogEntry]:
        if not force and not self.needs_reparse() and self.cached_entries:
            logger.debug(f"[PARSER-CACHE-HIT] Serving {len(self.cached_entries)} parsed entries from cache.")
            return self.cached_entries

        start_time = time.time()
        log_files = self.get_log_files()
        logger.info(f"[PARSER-START] Beginning log ingestion across {len(log_files)} file(s) (force={force})")

        all_entries: List[LogEntry] = []
        entry_id = 1
        new_mtimes: Dict[str, float] = {}

        # Generic pattern for timestamp || LEVEL | Component | Message | url: ... | action: ...
        pattern_pipe = re.compile(
            r"^\[?(\d{4}[-/]\d{2}[-/]\d{2})\s+(\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]?\s*\|\|([A-Za-z]+)\|([^|]*)\|(.*)"
        )
        # Generic pattern for standard timestamp [LEVEL] Component: Message
        pattern_std = re.compile(
            r"^\[?(\d{4}[-/]\d{2}[-/]\d{2})[T ](\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]?\s*(?:\[([A-Za-z]+)\]|([A-Za-z]+))\s*[:-]?\s*(?:\[([^\]]+)\])?\s*[-:]?\s*(.*)"
        )

        for file_path in log_files:
            file_start = time.time()
            file_mtime = file_path.stat().st_mtime
            file_size_kb = file_path.stat().st_size / 1024.0
            new_mtimes[file_path.name] = file_mtime
            
            # Sample first 200 lines to detect service name without loading entire multi-GB file into RAM
            sample_lines = []
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f_sample:
                for _ in range(200):
                    l = f_sample.readline()
                    if not l:
                        break
                    sample_lines.append(l)
            sample_text = "".join(sample_lines)
            service = self.detect_service_name(file_path.name, sample_text)
            current_entry: Optional[Dict[str, Any]] = None
            file_entries_count = 0

            # Stream line-by-line in O(1) memory to safely handle files in GBs
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_idx, line in enumerate(f):
                    # Try pipe format first
                    m = pattern_pipe.match(line)
                    if m:
                        if current_entry:
                            all_entries.append(LogEntry(**current_entry))
                            entry_id += 1
                            file_entries_count += 1

                        date_str, time_str, level, comp, rest = m.groups()
                        timestamp = f"{date_str} {time_str}"
                        
                        url = ""
                        action = ""
                        msg = rest
                        
                        if "|url:" in rest:
                            parts = rest.split("|url:")
                            msg = parts[0].strip()
                            url_action = parts[1] if len(parts) > 1 else ""
                            if "|action:" in url_action:
                                u_parts = url_action.split("|action:")
                                url = u_parts[0].strip()
                                action = u_parts[1].strip() if len(u_parts) > 1 else ""
                            else:
                                url = url_action.strip()

                        current_entry = {
                            "id": entry_id,
                            "file_name": file_path.name,
                            "timestamp": timestamp,
                            "date": date_str,
                            "time": time_str,
                            "level": level.strip(),
                            "component": comp.strip() or "Program",
                            "message": msg.strip(),
                            "service": service,
                            "url": url,
                            "action": action,
                            "stack_trace": None,
                            "line_number": line_idx + 1
                        }
                    else:
                        # Try standard format
                        m2 = pattern_std.match(line)
                        if m2:
                            if current_entry:
                                all_entries.append(LogEntry(**current_entry))
                                entry_id += 1
                                file_entries_count += 1

                            date_str, time_str, lvl1, lvl2, comp, rest = m2.groups()
                            level = (lvl1 or lvl2 or "INFO").strip()
                            current_entry = {
                                "id": entry_id,
                                "file_name": file_path.name,
                                "timestamp": f"{date_str} {time_str}",
                                "date": date_str,
                                "time": time_str,
                                "level": level,
                                "component": (comp or "App").strip(),
                                "message": (rest or "").strip(),
                                "service": service,
                                "url": "",
                                "action": "",
                                "stack_trace": None,
                                "line_number": line_idx + 1
                            }
                        else:
                            # Continuation line (stack trace or multiline text)
                            if current_entry:
                                stripped_line = line.strip()
                                if stripped_line:
                                    if current_entry["stack_trace"] is None:
                                        current_entry["stack_trace"] = stripped_line
                                    else:
                                        current_entry["stack_trace"] += "\n" + stripped_line
                                    current_entry["message"] += "\n" + stripped_line

            if current_entry:
                all_entries.append(LogEntry(**current_entry))
                entry_id += 1
                file_entries_count += 1

            total_file_lines = line_idx + 1 if 'line_idx' in locals() else file_entries_count
            file_dur_ms = (time.time() - file_start) * 1000.0
            logger.info(
                f"[PARSER-FILE-DONE] '{file_path.name}': {file_entries_count} entries from {total_file_lines} lines "
                f"({file_size_kb:.1f} KB) in {file_dur_ms:.1f}ms | Service='{service}'"
            )

        total_dur_ms = (time.time() - start_time) * 1000.0
        error_count = sum(1 for e in all_entries if e.level == "ERROR")
        logger.info(
            f"[PARSER-COMPLETE] Total parsed: {len(all_entries)} entries ({error_count} errors) "
            f"across {len(log_files)} file(s) in {total_dur_ms:.1f}ms"
        )

        self.cached_entries = all_entries
        self._last_modified_times = new_mtimes
        return self.cached_entries

parser = LogParser()
