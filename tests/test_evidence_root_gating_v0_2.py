#!/usr/bin/env python3
"""Root-gating and ambiguity safeguard tests for evidence search v0_2."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.evidence_search_reliability_v0_2.config import load_config
from backend.evidence_search_reliability_v0_2.query_expansion import expand_query
from backend.evidence_search_reliability_v0_2.root_inference import infer_roots_from_context


class RootGatingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(enabled=True)

    def test_infer_breast_from_query(self):
        roots = infer_roots_from_context("DCIS breast mammary", config=self.config)
        self.assertIn("Breast", roots)

    def test_crc_stays_gi_with_colon(self):
        r = expand_query("CRC colon", config=self.config, entity_metadata={"root": "GI"})
        self.assertIn("colorectal", r.effective_query.lower())
        self.assertIn("GI", r.inferred_roots)

    def test_crc_no_renal_expansion(self):
        r = expand_query("CRC", config=self.config)
        self.assertEqual(r.effective_query, "CRC")

    def test_ssl_blocks_without_gi_context(self):
        r = expand_query("SSL", config=self.config)
        self.assertEqual(r.effective_query, "SSL")

    def test_cis_blocked_without_urinary_or_gyn_context(self):
        r = expand_query("CIS", config=self.config)
        self.assertFalse(any(x["abbreviation"] == "CIS" for x in r.expansions_applied))

    def test_cmf_requires_bone_context(self):
        r = expand_query("CMF", config=self.config)
        self.assertEqual(r.effective_query, "CMF")

    def test_idc_nos_breast_context(self):
        r = expand_query(
            "IDC NOS breast",
            config=self.config,
            entity_metadata={"root": "Breast", "organ_context": "breast"},
        )
        self.assertIn("invasive ductal carcinoma", r.effective_query.lower())

    def test_hgsc_ovary_context(self):
        r = expand_query("HGSC ovary", config=self.config, entity_metadata={"root": "GYN"})
        self.assertIn("high-grade serous carcinoma", r.effective_query.lower())


class WhoRankingTests(unittest.TestCase):
    def test_who_title_boost_prefers_exact_entity(self):
        from backend.evidence_search_reliability_v0_2.query_expansion import ExpansionResult
        from backend.evidence_search_reliability_v0_2.who_ranking import apply_who_title_boost

        expansion = ExpansionResult(
            original_query="bullous pemphigoid",
            effective_query="bullous pemphigoid",
        )
        hits = [
            {"title": "Pilomatricoma", "score": -5.0, "excerpt": "bullous skin"},
            {"title": "Bullous pemphigoid", "score": -6.0, "excerpt": "autoimmune blistering"},
        ]
        ranked = apply_who_title_boost(hits, query="bullous pemphigoid", expansion=expansion)
        self.assertEqual(ranked[0]["title"], "Bullous pemphigoid")


if __name__ == "__main__":
    unittest.main()
