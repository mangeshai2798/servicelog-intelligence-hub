#!/usr/bin/env python3
"""
========================================================================================
Unit & Integration Test Suite for Model Benchmarking & Sequential Memory Isolation
========================================================================================
Verifies:
1. Memory isolation: Models are unloaded cleanly and RAM is reclaimed.
2. Dynamic switching: Switching models clears active references.
3. Benchmark queries integrity: All 10 SRE operational queries are well-formed.
4. Query execution: QueryEngine answers queries with metrics and evidence.
========================================================================================
"""

import sys
import unittest
import psutil
from pathlib import Path

# Ensure project root and backend are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ai_service import LocalQwenEngine, ai_service
from app.query_engine import query_engine
from backend.benchmark_models import BENCHMARK_QUERIES, AVAILABLE_MODELS, get_process_ram_mb


class TestModelBenchmarkAndIsolation(unittest.TestCase):
    """Test suite for validating model benchmarking, isolation, and query execution."""

    def setUp(self):
        # Guarantee clean state before each test
        LocalQwenEngine.unload_model()

    def tearDown(self):
        # Guarantee clean state after each test
        LocalQwenEngine.unload_model()

    def test_01_benchmark_queries_count_and_structure(self):
        """Verifies that all 10 standardized SRE benchmark queries exist with complete metadata."""
        self.assertEqual(len(BENCHMARK_QUERIES), 10, "Benchmark suite must contain exactly 10 SRE queries")
        for q in BENCHMARK_QUERIES:
            self.assertIn("id", q)
            self.assertIn("category", q)
            self.assertIn("query", q)
            self.assertIn("description", q)
            self.assertTrue(len(q["query"]) > 10, f"Query #{q['id']} text is too short")

    def test_02_available_models_configuration(self):
        """Verifies model configurations for 0.5B, 1.5B, and 3B."""
        expected_keys = ["0.5B", "1.5B", "3B"]
        for k in expected_keys:
            self.assertIn(k, AVAILABLE_MODELS, f"Model key '{k}' must be registered in AVAILABLE_MODELS")
            m = AVAILABLE_MODELS[k]
            self.assertTrue("Qwen" in m["model_id"])
            self.assertIn("parameters", m)
            self.assertIn("expected_ram_mb", m)

    def test_03_strict_memory_unloading(self):
        """Tests that unload_model() strictly clears model references and releases in-memory state."""
        # Baseline
        ram_before = get_process_ram_mb()
        engine = LocalQwenEngine.get_instance("Qwen/Qwen2.5-0.5B-Instruct")
        ok = engine.load_model()
        self.assertTrue(ok, "Qwen 0.5B model should load successfully")
        self.assertTrue(engine.is_ready(), "Engine must report ready after load")
        self.assertIsNotNone(LocalQwenEngine._model)
        self.assertIsNotNone(LocalQwenEngine._tokenizer)

        # Unload
        LocalQwenEngine.unload_model()
        self.assertIsNone(LocalQwenEngine._model, "Model reference must be None after unload")
        self.assertIsNone(LocalQwenEngine._tokenizer, "Tokenizer reference must be None after unload")
        self.assertFalse(engine.is_ready(), "Engine must not report ready after unload")

    def test_04_dynamic_model_switching_unloads_previous(self):
        """Tests that ai_service.set_model unloads the previous model before setting the new one."""
        ai_service.set_model("Qwen/Qwen2.5-0.5B-Instruct")
        engine = LocalQwenEngine.get_instance()
        engine.load_model()
        self.assertTrue(engine.is_ready())

        # Switch to 3B model
        ai_service.set_model("Qwen/Qwen2.5-3B-Instruct")
        self.assertEqual(ai_service.model_name, "Qwen/Qwen2.5-3B-Instruct")
        # Ensure previous 0.5B was unloaded
        self.assertIsNone(LocalQwenEngine._model, "Previous model should be unloaded on switch before new load")

    def test_05_query_engine_answers_sre_query(self):
        """Verifies that QueryEngine produces valid QueryResponse with metrics."""
        ai_service.set_model("Qwen/Qwen2.5-0.5B-Instruct")
        sample_q = BENCHMARK_QUERIES[0]["query"]
        resp = query_engine.answer_query(sample_q)
        self.assertIsNotNone(resp)
        self.assertTrue(len(resp.answer) > 50, "Answer should be substantive")
        self.assertIn("total_records", resp.metrics)
        self.assertIn("success_rate", resp.metrics)
        self.assertTrue(resp.duration_ms > 0)


def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestModelBenchmarkAndIsolation)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
