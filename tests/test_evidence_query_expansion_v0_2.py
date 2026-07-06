#!/usr/bin/env python3
"""Unit tests for evidence query expansion v0_2."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.evidence_search_reliability_v0_2.config import load_config
from backend.evidence_search_reliability_v0_2.query_expansion import expand_query


class QueryExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(enabled=True, debug=False)

    def _expand(self, query: str, **kwargs):
        return expand_query(query, config=self.config, **kwargs)

    def test_lcis_breast_expands(self):
        r = self._expand("LCIS breast", entity_metadata={"root": "Breast", "organ_context": "breast"})
        self.assertIn("lobular carcinoma in situ", r.effective_query.lower())
        self.assertEqual(r.original_query, "LCIS breast")

    def test_ssl_colon_expands(self):
        r = self._expand("SSL colon", entity_metadata={"root": "GI", "organ_context": "colon"})
        self.assertIn("sessile serrated", r.effective_query.lower())

    def test_ais_cervix_expands(self):
        r = self._expand("AIS cervix", entity_metadata={"root": "GYN", "organ_context": "cervix"})
        self.assertIn("adenocarcinoma in situ", r.effective_query.lower())

    def test_ais_without_context_conservative(self):
        r = self._expand("AIS")
        self.assertEqual(r.effective_query, "AIS")
        self.assertFalse(any(x["abbreviation"] == "AIS" for x in r.expansions_applied))

    def test_cis_bladder_expands(self):
        r = self._expand("CIS bladder", entity_metadata={"root": "GU", "organ_context": "bladder"})
        self.assertIn("carcinoma in situ", r.effective_query.lower())

    def test_cis_without_context_conservative(self):
        r = self._expand("CIS")
        self.assertEqual(r.effective_query, "CIS")

    def test_ipmn_pancreas_expands(self):
        r = self._expand("IPMN pancreas", entity_metadata={"root": "GI", "organ_context": "pancreas"})
        self.assertIn("intraductal papillary mucinous", r.effective_query.lower())

    def test_cmf_bone_not_fibroma(self):
        r = self._expand("CMF bone", entity_metadata={"root": "BST", "organ_context": "bone"})
        self.assertIn("chondromyxoid fibroma", r.effective_query.lower())
        self.assertNotRegex(r.effective_query.lower(), r"\bbone fibroma\b")

    def test_sccis_skin_expands(self):
        r = self._expand("SCCIS skin", entity_metadata={"root": "Skin", "organ_context": "skin"})
        self.assertIn("squamous cell carcinoma in situ", r.effective_query.lower())

    def test_ptc_thyroid_expands(self):
        r = self._expand("PTC thyroid", entity_metadata={"root": "HN", "organ_context": "thyroid"})
        self.assertIn("papillary thyroid carcinoma", r.effective_query.lower())

    def test_mtc_thyroid_expands(self):
        r = self._expand("MTC thyroid", entity_metadata={"root": "HN", "organ_context": "thyroid"})
        self.assertIn("medullary thyroid carcinoma", r.effective_query.lower())

    def test_dsrcct_bst_expands(self):
        r = self._expand("DSRCT soft tissue", entity_metadata={"root": "BST", "organ_context": "soft tissue"})
        self.assertIn("desmoplastic small round cell", r.effective_query.lower())

    def test_dfsp_skin_expands(self):
        r = self._expand("DFSP skin", entity_metadata={"root": "Skin", "organ_context": "skin"})
        self.assertIn("dermatofibrosarcoma protuberans", r.effective_query.lower())

    def test_preserves_original_query(self):
        r = self._expand("LCIS breast")
        self.assertTrue(r.effective_query.startswith("LCIS"))

    def test_disabled_returns_original(self):
        cfg = load_config(enabled=False)
        r = expand_query("LCIS breast", config=cfg)
        self.assertEqual(r.effective_query, "LCIS breast")

    def test_no_car_f_map_status_in_rules(self):
        for rule in self.config.rules:
            for key, val in rule.items():
                self.assertNotIn("map_status", key.lower())
                if isinstance(val, str):
                    self.assertNotIn("map_status", val.lower())
                if key.lower() in {"c", "ar", "f", "map_status"}:
                    self.fail("C/AR/F must not be used as rule fields or map_status")


if __name__ == "__main__":
    unittest.main()
