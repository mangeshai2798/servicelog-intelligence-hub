"""
Drain3 Template Mining Engine
Neuro-Symbolic Log Normalization & Online Pattern Discovery
Automatically extracts structural templates, masks variable noise (IPs, UUIDs, IDs),
and clusters log entries without requiring hardcoded regex rules.
"""

import threading
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.masking import MaskingInstruction

from app.logger import logger
from app.config import DATA_DIR


class LogTemplateMiner:
    _instance: Optional["LogTemplateMiner"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "LogTemplateMiner":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self.config = TemplateMinerConfig()
        self.config.drain_sim_th = 0.5
        self.config.drain_depth = 4
        self.config.drain_max_children = 100
        self.config.drain_max_clusters = 1000

        # Masking instructions to strip high-cardinality noise
        self.config.masking_instructions = [
            MaskingInstruction(r'((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)', '<IP>'),
            MaskingInstruction(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', '<UUID>'),
            MaskingInstruction(r'\b0x[a-fA-F0-9]+\b', '<HEX>'),
            MaskingInstruction(r'\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b', '<TIMESTAMP>'),
            MaskingInstruction(r'(?:/[a-zA-Z0-9_\-\.]+)+|(?:[a-zA-Z]:\\[a-zA-Z0-9_\-\.\\]+)', '<PATH>'),
            MaskingInstruction(r'\b(?:TX|tx|ORDER|order|REQ|req|JOB|job|BATCH|batch)[-_]?[0-9a-zA-Z]+\b', '<ENTITY_ID>'),
            MaskingInstruction(r'\b\d+\b', '<NUM>'),
        ]

        self.miner = TemplateMiner(config=self.config)
        self.state_file = DATA_DIR / "drain3_state.json"
        self._mutex = threading.Lock()
        logger.info("[DRAIN3-INIT] Initialized Drain3 Online Template Mining Engine.")

    def mine(self, log_message: str) -> Tuple[int, str]:
        """
        Processes a raw or cleaned log message, extracts its structural template,
        and assigns a cluster ID.
        Returns:
            Tuple[int, str]: (cluster_id, template_mined)
        """
        if not log_message:
            return 0, ""

        with self._mutex:
            try:
                # Strip multi-line stack traces to top exception for template mining
                first_line = log_message.strip().splitlines()[0][:500]
                result = self.miner.add_log_message(first_line)
                cluster_id = result.get("cluster_id", 0)
                template_mined = result.get("template_mined", first_line)
                return cluster_id, template_mined
            except Exception as e:
                logger.debug(f"[DRAIN3-WARN] Failed to mine template for message: {e}")
                return 0, log_message[:120]

    def get_clusters_summary(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns structured summaries of all mined template clusters."""
        with self._mutex:
            clusters = []
            for cluster in self.miner.drain.clusters:
                clusters.append({
                    "cluster_id": cluster.cluster_id,
                    "template": cluster.get_template(),
                    "size": cluster.size,
                    "sample_message": cluster.sample_log
                })
            # Sort by frequency descending
            clusters.sort(key=lambda c: c["size"], reverse=True)
            return clusters[:limit]

    def get_cluster_by_id(self, cluster_id: int) -> Optional[Dict[str, Any]]:
        """Looks up a specific template cluster by ID."""
        with self._mutex:
            for cluster in self.miner.drain.clusters:
                if cluster.cluster_id == cluster_id:
                    return {
                        "cluster_id": cluster.cluster_id,
                        "template": cluster.get_template(),
                        "size": cluster.size,
                        "sample_message": cluster.sample_log
                    }
            return None


# Global singleton instance
template_miner = LogTemplateMiner.get_instance()

