#!/usr/bin/env python3
"""Regression tests: v0_2 module must not break v0_1 artifact validation."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "06_audits/evidence_retrieval_writable/benchmark_v0_1"


class V02RegressionGateTests(unittest.TestCase):
    def test_v0_1_benchmark_regression_still_passes(self):
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "06_audits.evidence_retrieval_writable.benchmark_v0_1.benchmark_regression_tests", "-q"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_v0_2_unit_tests_pass(self):
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_evidence_query_expansion_v0_2", "tests.test_evidence_root_gating_v0_2", "-q"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
