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
    cap_cards_diverse,
    card_identity_key,
    dedupe_cards,
    diversify_by_source_id,
    extract_evidence_cards,
    extract_figures,
    merge_outcomes,
    slim_merged_from_cards,
    staged_retrieve,
    topic_page_query_variants,
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

    def test_multi_source_calls_run_concurrently_and_preserve_order(self):
        # Each source's mocked call sleeps briefly; if calls were still
        # sequential this would take >= 4x the per-call sleep instead of
        # ~1x, so this catches an accidental revert to the old for-loop.
        import time as _time

        sources = ["textbooks", "who", "pathout", "lectures"]
        per_call_sleep = 0.2

        def _slow_search(query, sources, **kwargs):
            _time.sleep(per_call_sleep)
            return SearchOutcome(
                request_payload={"sources": sources},
                url="u",
                status_code=200,
                ok=True,
                elapsed_ms=1.0,
                response_json={"query": query, "requested": sources},
            )

        client = MagicMock(spec=PathologyHubClient)
        client.search.side_effect = _slow_search

        start = _time.monotonic()
        outcomes = staged_retrieve(client, "LCIS", sources)
        elapsed = _time.monotonic() - start

        self.assertEqual(len(outcomes), 4)
        self.assertEqual(client.search.call_count, 4)
        self.assertLess(elapsed, per_call_sleep * len(sources))
        # Order of returned outcomes matches order of requested sources.
        requested_order = [o.response_json["requested"][0] for o in outcomes]
        self.assertEqual(requested_order, sources)


class TestDiversifyBySourceId(unittest.TestCase):
    def test_noop_with_single_distinct_source_id(self):
        items = [{"source_id": "a", "rank": 1}, {"source_id": "a", "rank": 2}]
        self.assertEqual(diversify_by_source_id(items), items)

    def test_noop_with_empty_or_non_list(self):
        self.assertEqual(diversify_by_source_id([]), [])
        self.assertEqual(diversify_by_source_id(None), None)

    def test_round_robin_interleaves_distinct_sources_without_dropping_data(self):
        items = [
            {"source_id": "textbook_a", "rank": 1},
            {"source_id": "textbook_a", "rank": 2},
            {"source_id": "textbook_a", "rank": 3},
            {"source_id": "textbook_b", "rank": 1},
        ]
        result = diversify_by_source_id(items)
        self.assertEqual(len(result), len(items))
        # No data lost — same set of items, just reordered.
        self.assertEqual(
            sorted((i["source_id"], i["rank"]) for i in result),
            sorted((i["source_id"], i["rank"]) for i in items),
        )
        # textbook_b's single item should surface right after textbook_a's
        # first item, not get buried after all 3 textbook_a entries.
        source_order = [i["source_id"] for i in result]
        self.assertEqual(source_order, ["textbook_a", "textbook_b", "textbook_a", "textbook_a"])

    def test_missing_key_treated_as_its_own_group(self):
        items = [{"rank": 1}, {"source_id": "a", "rank": 2}, {"rank": 3}]
        result = diversify_by_source_id(items)
        self.assertEqual(len(result), 3)


class TestTopicPageQueryVariants(unittest.TestCase):
    def test_builds_four_programmatic_variants(self):
        variants = topic_page_query_variants("High-grade serous carcinoma ovary")
        self.assertEqual(len(variants), 4)
        self.assertEqual(variants[0], "High-grade serous carcinoma ovary")
        self.assertIn("histology", variants[1].lower())
        self.assertIn("ihc", variants[2].lower())
        self.assertIn("differential", variants[3].lower())

    def test_category_context_enriches_short_entity_names(self):
        variants = topic_page_query_variants(
            "HGSC",
            category_context="GYN — Ovary > Carcinomas",
        )
        self.assertTrue(variants[0].startswith("HGSC GYN — Ovary > Carcinomas"))

    def test_category_context_skipped_for_descriptive_entity_names(self):
        variants = topic_page_query_variants(
            "ovarian high-grade serous carcinoma",
            category_context="GYN — Ovary > Carcinomas",
        )
        self.assertEqual(variants[0], "ovarian high-grade serous carcinoma")

    def test_deduplicates_identical_variants(self):
        variants = topic_page_query_variants("  LCIS  ")
        self.assertEqual(variants[0], "LCIS")


class TestCardDedupeAndCap(unittest.TestCase):
    def test_card_identity_key_prefers_chunk_id(self):
        self.assertEqual(
            card_identity_key({"chunk_id": "abc123", "title": "X"}),
            "id:abc123",
        )

    def test_dedupe_cards_drops_duplicates_preserving_order(self):
        cards = [
            {"chunk_id": "a", "source": "textbooks", "title": "One"},
            {"chunk_id": "a", "source": "textbooks", "title": "One dup"},
            {"source_url": "https://example.com/x", "source": "who", "title": "Two"},
            {"source_url": "https://example.com/x", "source": "who", "title": "Two dup"},
        ]
        result = dedupe_cards(cards)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["chunk_id"], "a")
        self.assertEqual(result[1]["source_url"], "https://example.com/x")

    def test_cap_cards_diverse_round_robins_across_sources(self):
        cards = [
            {"source": "textbooks", "rank": 1},
            {"source": "textbooks", "rank": 2},
            {"source": "textbooks", "rank": 3},
            {"source": "videos", "rank": 1},
            {"source": "journals", "rank": 1},
        ]
        capped = cap_cards_diverse(cards, 3)
        self.assertEqual(len(capped), 3)
        sources = [c["source"] for c in capped]
        self.assertEqual(sources, ["textbooks", "videos", "journals"])

    def test_slim_merged_from_cards_rebuilds_result_lists(self):
        cards = extract_evidence_cards(SAMPLE_RESPONSE)
        slim = slim_merged_from_cards(SAMPLE_RESPONSE, cards)
        self.assertEqual(len(slim["textbook_results"]), 1)
        self.assertEqual(len(slim["who_results"]), 1)


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

    def test_topic_page_sources_excludes_curriculum_includes_journals(self):
        from app import TOPIC_PAGE_SOURCES  # noqa: E402

        self.assertNotIn("curriculum", TOPIC_PAGE_SOURCES)
        self.assertIn("journals", TOPIC_PAGE_SOURCES)
        self.assertIn("textbooks", TOPIC_PAGE_SOURCES)
        self.assertIn("videos", TOPIC_PAGE_SOURCES)
        self.assertIn("lectures", TOPIC_PAGE_SOURCES)

    def test_topic_page_mode_overrides_sidebar_sources_server_side(self):
        from fastapi.testclient import TestClient

        from app import TOPIC_PAGE_SOURCES, app  # noqa: E402

        captured_calls: list[list[str]] = []

        def _fake_staged_retrieve(client, query, sources, **kwargs):
            captured_calls.append(list(sources))
            return [
                SearchOutcome(
                    request_payload={"query": query, "sources": sources},
                    url="http://mock/evidence/search",
                    status_code=200,
                    ok=True,
                    elapsed_ms=1.0,
                    response_json=SAMPLE_RESPONSE,
                    api_key_present=True,
                )
                for _ in sources
            ]

        with patch("app.staged_retrieve", side_effect=_fake_staged_retrieve), patch(
            "app.synthesize"
        ) as mock_synthesize:
            mock_synthesize.return_value = MagicMock(ok=True, text="- fake answer", model="test-model")
            client = TestClient(app)
            resp = client.post(
                "/api/chat",
                json={
                    "query": "ovarian high-grade serous carcinoma",
                    "mode": "topic_page",
                    # Deliberately narrow, sidebar-style default — server must
                    # override this to the full TOPIC_PAGE_SOURCES set.
                    "sources": ["textbooks", "pathout", "who"],
                },
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["debug"]["multi_query"])
        self.assertGreaterEqual(len(body["debug"]["query_variants"]), 3)
        self.assertGreater(body["debug"]["call_count"], 6)
        self.assertTrue(all(sorted(s) == sorted(TOPIC_PAGE_SOURCES) for s in captured_calls))

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
