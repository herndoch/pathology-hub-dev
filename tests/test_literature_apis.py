"""Unit tests for live literature helpers (no network)."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "pathology_hub_chat_mvp"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import literature_apis  # noqa: E402


class TestLiteratureHelpers(unittest.TestCase):
    def test_extract_genes_finds_common_symbols(self):
        genes = literature_apis._extract_genes("Salivary secretory carcinoma ETV6-NTRK3 fusion BRAF wild-type")
        self.assertIn("ETV6", genes)
        self.assertIn("NTRK3", genes)
        self.assertIn("BRAF", genes)

    def test_doi_url(self):
        self.assertEqual(literature_apis._doi_url("10.1/abc"), "https://doi.org/10.1/abc")
        self.assertIsNone(literature_apis._doi_url(""))

    def test_live_literature_disabled(self):
        with patch.dict(os.environ, {"TOPIC_PAGE_LIVE_LITERATURE": "0"}):
            out = literature_apis.fetch_live_literature("fibroadenoma")
        self.assertFalse(out["enabled"])
        self.assertEqual(out["cards"], [])

    def test_card_shape(self):
        card = literature_apis._card(
            title="Test",
            journal="AJSP",
            doi="10.1097/PAS.0000000000000000",
            abstract="Hello",
            year="2024",
            retrieval_mode="elsevier_scopus",
            source_name="Elsevier Scopus",
        )
        self.assertEqual(card["source"], "literature")
        self.assertTrue(card["source_url"].startswith("https://doi.org/"))


if __name__ == "__main__":
    unittest.main()
