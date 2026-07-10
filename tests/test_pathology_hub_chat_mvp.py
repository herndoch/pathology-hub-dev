"""Smoke tests for Pathology Hub Chat MVP backend client (no live API key)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

MVP_DIR = Path(__file__).resolve().parents[1] / "frontend" / "pathology_hub_chat_mvp"
if str(MVP_DIR) not in sys.path:
    sys.path.insert(0, str(MVP_DIR))

from pathology_backend import (  # noqa: E402
    PathologyHubClient,
    SearchOutcome,
    extract_evidence_cards,
    extract_figures,
    merge_outcomes,
    staged_retrieve,
)


SAMPLE_RESPONSE = {
    "schema_version": "evidence_search_response.v1.5.10",
    "query": "LCIS breast",
    "source_status": {"textbooks": "ok", "who": "ok"},
    "warnings": [],
    "textbook_results": [
        {
            "title": "Lobular carcinoma in situ",
            "source_url": "https://example.com/tb",
            "text_excerpt": "LCIS is a clonal proliferation…",
        }
    ],
    "who_results": [
        {
            "title": "LCIS (WHO)",
            "source_url": "https://example.com/who",
        }
    ],
    "figures": [{"figure_url": "https://example.com/fig.jpg", "caption": "Fig 1"}],
}


class TestEvidenceParsing(unittest.TestCase):
    def test_extract_evidence_cards_adds_source_labels(self):
        cards = extract_evidence_cards(SAMPLE_RESPONSE)
        self.assertEqual(len(cards), 2)
        sources = {c["source"] for c in cards}
        self.assertEqual(sources, {"textbooks", "who"})
        self.assertTrue(all(c.get("_result_key") for c in cards))

    def test_extract_figures_returns_list(self):
        figures = extract_figures(SAMPLE_RESPONSE)
        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0]["caption"], "Fig 1")

    def test_merge_outcomes_combines_staged_calls(self):
        ok = SearchOutcome(
            request_payload={"query": "q", "sources": ["textbooks"]},
            url="http://example/evidence/search",
            status_code=200,
            ok=True,
            elapsed_ms=120.0,
            response_json=dict(SAMPLE_RESPONSE),
            api_key_present=True,
        )
        err = SearchOutcome(
            request_payload={"query": "q", "sources": ["pathout"]},
            url="http://example/evidence/search",
            status_code=500,
            ok=False,
            elapsed_ms=40.0,
            response_json=None,
            error="HTTP 500: boom",
            api_key_present=True,
        )
        merged = merge_outcomes([ok, err])
        self.assertEqual(merged["schema_version"], "evidence_search_response.v1.5.10")
        self.assertIn("textbook_results", merged)
        self.assertIn("who_results", merged)
        self.assertTrue(any("request_error" in w for w in merged["warnings"]))


class TestStagedRetrieve(unittest.TestCase):
    def test_single_call_when_one_source(self):
        client = MagicMock(spec=PathologyHubClient)
        client.search.return_value = SearchOutcome(
            request_payload={},
            url="u",
            status_code=200,
            ok=True,
            elapsed_ms=1.0,
            response_json=SAMPLE_RESPONSE,
        )
        outcomes = staged_retrieve(client, "LCIS", ["textbooks"])
        self.assertEqual(len(outcomes), 1)
        client.search.assert_called_once()

    def test_per_source_calls_when_multiple_sources(self):
        client = MagicMock(spec=PathologyHubClient)
        client.search.return_value = SearchOutcome(
            request_payload={},
            url="u",
            status_code=200,
            ok=True,
            elapsed_ms=1.0,
            response_json={"textbook_results": []},
        )
        outcomes = staged_retrieve(client, "LCIS", ["textbooks", "who"])
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(client.search.call_count, 2)


class TestSearchOutcomeDebug(unittest.TestCase):
    def test_to_debug_dict_never_includes_api_key(self):
        outcome = SearchOutcome(
            request_payload={"query": "q"},
            url="http://x/evidence/search",
            status_code=200,
            ok=True,
            elapsed_ms=10.5,
            response_json=SAMPLE_RESPONSE,
            api_key_present=True,
        )
        debug = outcome.to_debug_dict()
        self.assertIn("source_status", debug)
        self.assertNotIn("api_key", debug)
        self.assertTrue(debug["api_key_present"])


class TestAppContract(unittest.TestCase):
    def test_validate_sources_rejects_unknown(self):
        from app import _validate_sources  # noqa: E402

        with self.assertRaises(ValueError):
            _validate_sources(["not_a_real_source"])

    def test_topic_page_is_a_valid_mode(self):
        from app import VALID_MODES  # noqa: E402

        self.assertIn("topic_page", VALID_MODES)

    def test_topic_page_figure_defaults_force_figures_on(self):
        from app import ChatRequest, _apply_figure_defaults  # noqa: E402

        req = ChatRequest(query="BAP1-inactivated melanocytoma", mode="topic_page")
        self.assertFalse(req.include_figures)
        _apply_figure_defaults(req, "topic_page")
        self.assertTrue(req.include_figures)
        self.assertEqual(req.max_figures, 8)

    def test_api_search_shape(self):
        from fastapi.testclient import TestClient

        from app import app  # noqa: E402

        mock_outcome = SearchOutcome(
            request_payload={"query": "LCIS", "sources": ["textbooks"]},
            url="http://mock/evidence/search",
            status_code=200,
            ok=True,
            elapsed_ms=5.0,
            response_json=SAMPLE_RESPONSE,
            api_key_present=True,
        )

        with patch("app.staged_retrieve", return_value=[mock_outcome]):
            client = TestClient(app)
            resp = client.post(
                "/api/search",
                json={"query": "LCIS breast", "sources": ["textbooks"], "max_results": 5},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["mode"], "search_only")
        self.assertIn("cards", body)
        self.assertIn("debug", body)
        self.assertGreaterEqual(len(body["cards"]), 1)


class TestTopicPagePrompt(unittest.TestCase):
    def test_topic_page_system_prompt_has_all_fixed_headers_in_order(self):
        import prompts  # noqa: E402

        text = prompts.topic_page_system_prompt()
        last_index = -1
        for section in prompts.TOPIC_PAGE_SECTIONS:
            header = f"## {section}"
            index = text.find(header)
            self.assertGreater(index, last_index, f"missing or out-of-order header: {header!r}")
            last_index = index

    def test_topic_page_system_prompt_inherits_base_grounding_rules(self):
        import prompts  # noqa: E402

        text = prompts.topic_page_system_prompt()
        self.assertIn("NEVER invent, guess, autocomplete, or reconstruct a URL", text)


if __name__ == "__main__":
    unittest.main()
