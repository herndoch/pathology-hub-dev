"""Smoke tests for Pathology Hub Chat MVP backend client (no live API key)."""

from __future__ import annotations

import json
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
    card_root_token,
    collapse_video_cards_for_citations,
    dedupe_cards,
    dedupe_video_cards,
    diversify_by_source_id,
    extract_evidence_cards,
    extract_figures,
    filter_cards_by_page_root,
    filter_figures_by_page_root,
    is_cyto_root_token,
    merge_outcomes,
    normalize_root_token,
    page_root_from_tag,
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

    def test_cap_cards_diverse_min_per_source_default_zero_is_unchanged(self):
        # Default behavior (min_per_source=0) must be byte-identical to the
        # pre-existing plain round-robin — no surprise behavior change for
        # any existing caller that doesn't pass the new parameter.
        cards = [{"source": "textbooks", "rank": i} for i in range(5)] + [
            {"source": "who", "rank": i} for i in range(5)
        ]
        self.assertEqual(cap_cards_diverse(cards, 4), cap_cards_diverse(cards, 4, min_per_source=0))

    def test_cap_cards_diverse_min_per_source_protects_thin_family(self):
        # Adversarial imbalance: one dominant family (100 cards) sorted
        # entirely before a thin family (2 cards) in the input list. A cap
        # small enough to be reached during the dominant family's initial
        # min_per_source pass, combined with the thin family sitting late in
        # `order`, is the scenario `min_per_source` exists to protect against.
        cards = [{"source": "pathout", "rank": i} for i in range(100)] + [
            {"source": "videos", "rank": i} for i in range(2)
        ]
        capped = cap_cards_diverse(cards, 10, min_per_source=3)
        sources = [c["source"] for c in capped]
        # Both of the thin family's cards must survive the cap.
        self.assertEqual(sources.count("videos"), 2)
        self.assertEqual(len(capped), 10)

    def test_cap_cards_diverse_min_per_source_never_exceeds_max_cards(self):
        cards = [{"source": s, "rank": i} for s in ("a", "b", "c", "d") for i in range(20)]
        capped = cap_cards_diverse(cards, 5, min_per_source=6)
        self.assertEqual(len(capped), 5)

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

    def test_topic_page_sources_excludes_curriculum_and_retired_journal_corpus(self):
        from app import TOPIC_PAGE_SOURCES  # noqa: E402

        self.assertNotIn("curriculum", TOPIC_PAGE_SOURCES)
        # `journals` (local journal FAISS corpus) was retired and replaced by
        # live Elsevier Scopus + PubMed + OncoKB via literature_apis.py —
        # see TOPIC_PAGE_SOURCES comment in app.py.
        self.assertNotIn("journals", TOPIC_PAGE_SOURCES)
        self.assertIn("textbooks", TOPIC_PAGE_SOURCES)
        self.assertIn("videos", TOPIC_PAGE_SOURCES)
        # `lectures` deliberately excluded: live-probed this session and
        # confirmed the backend returns byte-identical lecture_results/
        # video_results content (same chunk_ids) regardless of which of the
        # two source names is requested — same underlying corpus, not two
        # distinct families. Requesting both wastes a redundant backend call
        # and duplicate cards per query variant for zero additional coverage.
        self.assertNotIn("lectures", TOPIC_PAGE_SOURCES)

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

    def test_api_search_dedupes_lecture_video_duplicate_corpus(self):
        # Live-confirmed this session: requesting "lectures" or "videos" both
        # return byte-identical lecture_results/video_results (same
        # chunk_ids). Any non-topic-page mode that ends up with both result
        # keys populated (e.g. a sidebar user checking both boxes) must not
        # surface the same underlying chunk twice.
        from fastapi.testclient import TestClient

        from app import app  # noqa: E402

        duplicate_response = {
            "schema_version": "evidence_search_response.v1.5.10",
            "query": "q",
            "source_status": {"lectures": "ok", "videos": "ok"},
            "warnings": [],
            "lecture_results": [
                {"chunk_id": "lecture::x::1", "source": "videos", "title": "Case 01"},
            ],
            "video_results": [
                {"chunk_id": "lecture::x::1", "source": "videos", "title": "Case 01"},
            ],
        }
        mock_outcome = SearchOutcome(
            request_payload={"query": "q", "sources": ["lectures", "videos"]},
            url="http://mock/evidence/search",
            status_code=200,
            ok=True,
            elapsed_ms=5.0,
            response_json=duplicate_response,
            api_key_present=True,
        )

        with patch("app.staged_retrieve", return_value=[mock_outcome]):
            client = TestClient(app)
            resp = client.post(
                "/api/search",
                json={"query": "q", "sources": ["lectures", "videos"], "max_results": 5},
            )
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["cards"]), 1)


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


class TestWhoSectionMentions(unittest.TestCase):
    """Fixture text below is real WHO `differential_diagnosis`-section excerpt
    text captured live this session via `/api/search` (sources=["who"],
    excerpt_char_limit=4000) for "myoepithelial carcinoma differential
    diagnosis" and "traditional serrated adenoma" probes — not invented."""

    @classmethod
    def setUpClass(cls):
        from who_section_mentions import load_taxonomy_leaf_names  # noqa: E402

        cls.leaves = load_taxonomy_leaf_names()

    def test_finds_real_cross_mention_in_live_captured_excerpt(self):
        from who_section_mentions import who_section_mentions  # noqa: E402

        card = {
            "entity_name": "Epithelial-myoepithelial carcinoma",
            "section": "differential_diagnosis",
            "source_url": (
                "https://storage.googleapis.com/pathology-hub-0/WHO/WHO_HTML/HN/"
                "Epithelial_Myoepithelial_Carcinoma.html"
            ),
            "excerpt": (
                "Entity: Epithelial-myoepithelial carcinoma Section: differential_diagnosis "
                "The differential diagnosis includes other salivary gland tumours with biphasic "
                "and/or clear cell morphology, such as adenoid cystic carcinoma, basal cell "
                "adenocarcinoma, pleomorphic adenoma, myoepithelial carcinoma, and clear cell "
                "carcinoma."
            ),
        }
        matches = who_section_mentions(card, self.leaves)
        matched_leaves = {m["matched_leaf"] for m in matches}
        self.assertIn("Adenoid cystic carcinoma", matched_leaves)
        self.assertIn("Pleomorphic adenoma", matched_leaves)
        for m in matches:
            self.assertEqual(m["source_url"], card["source_url"])
            self.assertIn(m["candidate_phrase"].lower(), card["excerpt"].lower())
            self.assertEqual(m["snippet"], card["excerpt"])

    def test_does_not_hallucinate_generic_word_only_overlap(self):
        # "myoepithelial carcinoma" and "clear cell carcinoma" are literal
        # substrings of the same excerpt above, but must NOT fuzzy-match to
        # unrelated leaves ("Endometrioid carcinoma", "Clear cell renal cell
        # carcinoma") purely because they share the generic word "carcinoma"
        # / "clear cell" — regression test for a real false-positive found
        # live this session before the generic-token exclusion was added.
        from who_section_mentions import who_section_mentions  # noqa: E402

        card = {
            "entity_name": "Epithelial-myoepithelial carcinoma",
            "section": "differential_diagnosis",
            "source_url": "https://example.com/emca.html",
            "excerpt": (
                "Entity: Epithelial-myoepithelial carcinoma Section: differential_diagnosis "
                "such as adenoid cystic carcinoma, myoepithelial carcinoma, and clear cell carcinoma."
            ),
        }
        matches = who_section_mentions(card, self.leaves)
        matched_leaves = {m["matched_leaf"] for m in matches}
        self.assertNotIn("Endometrioid carcinoma", matched_leaves)
        self.assertNotIn("Clear cell renal cell carcinoma", matched_leaves)

    def test_ignores_non_target_sections(self):
        from who_section_mentions import who_section_mentions  # noqa: E402

        card = {
            "entity_name": "Myoepithelial carcinoma",
            "section": "epidemiology",
            "source_url": "https://example.com/x.html",
            "excerpt": "such as adenoid cystic carcinoma and pleomorphic adenoma.",
        }
        self.assertEqual(who_section_mentions(card, self.leaves), [])

    def test_never_links_entitys_own_page_to_itself(self):
        from who_section_mentions import who_section_mentions  # noqa: E402

        card = {
            "entity_name": "Chordoma",
            "section": "differential_diagnosis",
            "source_url": "https://example.com/chordoma.html",
            "excerpt": (
                "Entity: Chordoma Section: differential_diagnosis Tumours are distinguished from "
                "chondrosarcoma, carcinoma, meningioma, and myoepithelial tumours."
            ),
        }
        matches = who_section_mentions(card, self.leaves)
        matched_leaves = {m["matched_leaf"] for m in matches}
        self.assertIn("Chondrosarcoma", matched_leaves)
        self.assertIn("Meningioma", matched_leaves)
        self.assertNotIn("Chordoma", matched_leaves)

    def test_empty_for_missing_or_malformed_card(self):
        from who_section_mentions import who_section_mentions  # noqa: E402

        self.assertEqual(who_section_mentions(None), [])
        self.assertEqual(who_section_mentions({}), [])
        self.assertEqual(who_section_mentions({"section": "microscopic"}), [])


class TestFigureQualityFilter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        import tempfile
        from pathlib import Path

        cls.flags_file = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        rows = [
            {
                "chunk_id": "tbchunk:cyto_comprehensive_part_two:cyto_comprehensive_part_two_p0479_c001",
                "record_id": "textbooks:tbchunk:cyto_comprehensive_part_two:cyto_comprehensive_part_two_p0479_c001",
                "source_id": "cyto_comprehensive_part_two",
                "fig_slot": "fig01",
                "tier": "suppress_render",
            },
            {
                "chunk_id": "tbchunk:gyn_essentials:gyn_essentials_p0530_fig001_caption",
                "record_id": "textbooks:tbchunk:gyn_essentials:gyn_essentials_p0530_fig001_caption",
                "source_id": "gyn_essentials",
                "fig_slot": "fig01",
                "tier": "warn_render",
            },
        ]
        for row in rows:
            cls.flags_file.write(json.dumps(row) + "\n")
        cls.flags_file.close()
        cls.flags_path = cls.flags_file.name

        from figure_quality_filter import _load_index  # noqa: E402

        _load_index.cache_clear()

    @classmethod
    def tearDownClass(cls):
        from figure_quality_filter import _load_index  # noqa: E402
        import os

        _load_index.cache_clear()
        os.unlink(cls.flags_path)

    def test_matches_live_chunk_id_join_key(self):
        from figure_quality_filter import is_suppress_render  # noqa: E402

        card = {
            "chunk_id": "tbchunk:cyto_comprehensive_part_two:cyto_comprehensive_part_two_p0479_c001",
            "source_id": "cyto_comprehensive_part_two",
            "figure_url": "https://example.com/bad.png",
        }
        self.assertTrue(is_suppress_render(card, flags_path=self.flags_path))

    def test_warn_render_tier_is_not_suppressed(self):
        from figure_quality_filter import is_suppress_render  # noqa: E402

        card = {
            "chunk_id": "tbchunk:gyn_essentials:gyn_essentials_p0530_fig001_caption",
            "source_id": "gyn_essentials",
        }
        self.assertFalse(is_suppress_render(card, flags_path=self.flags_path))

    def test_figure_join_via_source_id_and_fig_slot(self):
        from figure_quality_filter import filter_suppress_render_figures  # noqa: E402

        figures = [
            {
                "source_id": "cyto_comprehensive_part_two",
                "image_path": "gs://pathology_hub/01_staged/textbooks/assets/figure_images/cyto_comprehensive_part_two/cyto_comprehensive_part_two_p0473_fig01_figure_35_16.png",
                "figure_url": "https://example.com/bad.png",
            },
            {
                "source_id": "gyn_essentials",
                "image_path": "gs://pathology_hub/01_staged/textbooks/assets/figure_images/gyn_essentials/gyn_essentials_p0100_fig02_figure.png",
                "figure_url": "https://example.com/ok.png",
            },
        ]
        filtered = filter_suppress_render_figures(figures, flags_path=self.flags_path)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["source_id"], "gyn_essentials")

    def test_strip_suppress_render_urls_keeps_card_text(self):
        from figure_quality_filter import strip_suppress_render_image_urls  # noqa: E402

        cards = [
            {
                "chunk_id": "tbchunk:cyto_comprehensive_part_two:cyto_comprehensive_part_two_p0479_c001",
                "source_id": "cyto_comprehensive_part_two",
                "figure_url": "https://example.com/bad.png",
                "page_image_url": "https://example.com/page.png",
                "excerpt": "real evidence text",
            }
        ]
        cleaned = strip_suppress_render_image_urls(cards, flags_path=self.flags_path)
        self.assertEqual(len(cleaned), 1)
        self.assertNotIn("figure_url", cleaned[0])
        self.assertEqual(cleaned[0]["page_image_url"], "https://example.com/page.png")
        self.assertEqual(cleaned[0]["excerpt"], "real evidence text")

    def test_tiny_decoded_image_matches_audit_threshold(self):
        from figure_quality_filter import is_tiny_decoded_image  # noqa: E402

        # Live cyto_thyroid_bethesda unidentified stubs are 90x90.
        self.assertTrue(is_tiny_decoded_image(90, 90))
        self.assertTrue(is_tiny_decoded_image(119, 800))
        self.assertFalse(is_tiny_decoded_image(120, 120))
        self.assertFalse(is_tiny_decoded_image(460, 306))

    def test_near_black_sample_classifies_bethesda_stub_stats(self):
        from figure_quality_filter import is_near_black_sample  # noqa: E402

        # Measured on live 90x90 stub: mean_l≈25.4, near_black≈0.368
        self.assertTrue(is_near_black_sample(25.4, 0.368))
        # Mostly solid black frame
        self.assertTrue(is_near_black_sample(5.0, 0.92))
        # Normal cytology-ish dark field should not trip loose threshold alone
        self.assertFalse(is_near_black_sample(45.0, 0.27))
        self.assertFalse(is_near_black_sample(120.0, 0.05))


class TestRootNarrowFilter(unittest.TestCase):
    def test_page_root_from_tag(self):
        self.assertEqual(page_root_from_tag("HN::Salivary_Gland::Benign::Pleomorphic_Adenoma"), "hn")
        self.assertEqual(page_root_from_tag("Breast::Neoplastic::DCIS"), "breast")
        self.assertIsNone(page_root_from_tag(None))

    def test_filter_cards_keeps_who_journals_drops_off_root_textbooks(self):
        cards = [
            {"source": "who", "title": "WHO entity"},
            {"source": "journals", "journal": "Modern Pathology", "title": "Journal hit"},
            {"source": "textbooks", "source_id": "hn_gnepp", "primary_tag": "HN::Salivary::X"},
            {"source": "textbooks", "source_id": "cyto_milan", "primary_tag": "Cyto_Breast::X"},
            {"source": "videos", "source_id": "breast_lecture", "title": "Off root video"},
            {"source": "videos", "source_id": "hn_lecture", "title": "On root video"},
        ]
        filtered = filter_cards_by_page_root(cards, "hn")
        sources = {c["source"] for c in filtered}
        self.assertEqual(sources, {"who", "journals", "textbooks", "videos"})
        self.assertEqual(len([c for c in filtered if c.get("source_id") == "hn_gnepp"]), 1)
        self.assertEqual(len([c for c in filtered if c.get("source_id") == "cyto_milan"]), 0)
        self.assertEqual(len([c for c in filtered if c.get("source_id") == "hn_lecture"]), 1)
        self.assertEqual(len([c for c in filtered if c.get("source_id") == "breast_lecture"]), 0)

    def test_is_cyto_root_token(self):
        self.assertTrue(is_cyto_root_token(page_root_from_tag("Cyto_Thyroid::Malignant::X")))
        self.assertTrue(is_cyto_root_token("cytobreast"))
        self.assertFalse(is_cyto_root_token(page_root_from_tag("Thyroid::Malignant::X")))
        self.assertFalse(is_cyto_root_token(None))
        self.assertFalse(is_cyto_root_token(""))

    def test_cyto_page_drops_generic_who_card_for_same_diagnosis(self):
        """Regression for user report (2026-07-26): a Cyto_* topic page must not
        show the generic/histologic WHO write-up just because it shares a
        diagnosis label with the underlying entity — WHO cards never carry a
        primary_tag, so they must be dropped (not kept-by-default) on cyto
        pages, unlike on ordinary (non-cyto) pages where WHO is always kept."""
        cards = [
            {"source": "who", "title": "Papillary thyroid carcinoma (WHO)"},
            {
                "source": "textbooks",
                "source_id": "thyroid_rosai",
                "primary_tag": "Thyroid::Malignant::Papillary_Thyroid_Carcinoma",
                "title": "Surgical pathology of PTC",
            },
            {
                "source": "textbooks",
                "source_id": "cyto_cibas",
                "primary_tag": "Cyto_Thyroid::Malignant::Papillary::Papillary_Thyroid_Carcinoma_Classic",
                "title": "Cytology of PTC",
            },
            {
                "source": "pathout",
                "source_id": "cyto_pattern",
                "primary_tag": "Cyto_Thyroid::Pattern::Papillary_Fragments",
                "title": "Cyto pattern reference",
            },
            {"source": "journals", "title": "PubMed: PTC review"},
        ]
        filtered = filter_cards_by_page_root(cards, page_root_from_tag(
            "Cyto_Thyroid::Malignant::Papillary::Papillary_Thyroid_Carcinoma_Classic"
        ))
        titles = {c["title"] for c in filtered}
        self.assertNotIn("Papillary thyroid carcinoma (WHO)", titles)
        self.assertNotIn("Surgical pathology of PTC", titles)
        self.assertIn("Cytology of PTC", titles)
        self.assertIn("Cyto pattern reference", titles)
        # Live literature is fetched/scoped separately — untouched by this filter.
        self.assertIn("PubMed: PTC review", titles)

    def test_non_cyto_page_still_keeps_who_regardless_of_root(self):
        """Non-cyto pages must see zero behavior change from the B9 fix."""
        cards = [
            {"source": "who", "title": "Generic WHO entity"},
            {
                "source": "textbooks",
                "source_id": "breast_wolf",
                "primary_tag": "Breast::Neoplastic::DCIS",
                "title": "On-root textbook",
            },
        ]
        filtered = filter_cards_by_page_root(cards, page_root_from_tag("Breast::Neoplastic::DCIS"))
        self.assertEqual({c["title"] for c in filtered}, {"Generic WHO entity", "On-root textbook"})

    def test_cyto_page_drops_unresolvable_root_textbook_pathout_cards(self):
        """B9: on cyto pages, even textbooks/pathout with no resolvable tag/source_id
        prefix are dropped (stricter than the B8 'keep unless proven off-root')."""
        cards = [
            {"source": "textbooks", "title": "No tag at all"},
            {
                "source": "textbooks",
                "source_id": "cyto_milan",
                "primary_tag": "Cyto_Salivary::Category::Milan_III",
                "title": "On-root cyto textbook",
            },
        ]
        filtered = filter_cards_by_page_root(cards, page_root_from_tag("Cyto_Salivary::Category::Milan_III"))
        self.assertEqual({c["title"] for c in filtered}, {"On-root cyto textbook"})

    def test_cyto_page_keeps_generic_cyto_sourced_card_missing_primary_tag(self):
        """Cyto textbooks/atlases (e.g. 'cyto_cibas') span every cyto organ in
        one source_id-named book — only the per-chunk primary_tag carries the
        specific Cyto_<Organ> root. A card that (unusually) has a cyto-book
        source_id but no primary_tag should still be kept on any Cyto_* page
        rather than dropped for not matching the specific organ exactly."""
        cards = [
            {"source": "textbooks", "source_id": "cyto_cibas", "title": "Generic cyto book, no primary_tag"},
            {"source": "textbooks", "source_id": "thyroid_rosai", "title": "Generic surgical book, no primary_tag"},
        ]
        filtered = filter_cards_by_page_root(cards, page_root_from_tag("Cyto_Thyroid::Malignant::X"))
        self.assertEqual({c["title"] for c in filtered}, {"Generic cyto book, no primary_tag"})

    def test_filter_figures_by_page_root_drops_off_root_keeps_generic_cyto_on_cyto_pages(self):
        """Figures never carry primary_tag (confirmed live — see README B9 note),
        only source_id. Real cyto book source_ids (e.g. 'cyto_cibas_fig12') are
        organ-agnostic, so any Cyto_* page must keep them; a non-cyto figure
        (e.g. 'thyroid_rosai_fig3') and one with no source_id at all must not."""
        figures = [
            {"source_id": "cyto_cibas_fig12", "caption": "Cyto figure"},
            {"source_id": "thyroid_rosai_fig3", "caption": "Off-root surgical figure"},
            {"caption": "No source_id at all"},
        ]
        filtered = filter_figures_by_page_root(figures, page_root_from_tag("Cyto_Thyroid::Malignant::X"))
        captions = {f["caption"] for f in filtered}
        self.assertEqual(captions, {"Cyto figure"})

    def test_filter_figures_by_page_root_keeps_unresolvable_on_non_cyto_pages(self):
        """Non-cyto pages must see zero behavior change from the B9 fix."""
        figures = [
            {"source_id": "breast_wolf_fig1", "caption": "On-root figure"},
            {"caption": "No source_id at all"},
        ]
        filtered = filter_figures_by_page_root(figures, page_root_from_tag("Breast::Neoplastic::DCIS"))
        captions = {f["caption"] for f in filtered}
        self.assertEqual(captions, {"On-root figure", "No source_id at all"})


class TestVideoDedupe(unittest.TestCase):
    def test_dedupe_video_cards_by_video_id(self):
        cards = [
            {"source": "videos", "video_id": "vid-a", "title": "Case 01", "chunk_id": "c1"},
            {"source": "videos", "video_id": "vid-a", "title": "Case 01", "chunk_id": "c2"},
            {"source": "videos", "video_id": "vid-b", "title": "Case 02", "chunk_id": "c3"},
            {"source": "who", "title": "WHO entity"},
        ]
        deduped = dedupe_video_cards(cards)
        self.assertEqual(len(deduped), 2)
        self.assertEqual({c["video_id"] for c in deduped}, {"vid-a", "vid-b"})

    def test_collapse_video_cards_for_citations_keeps_non_video(self):
        cards = [
            {"source": "videos", "video_id": "vid-a", "title": "Lecture", "chunk_id": "c1"},
            {"source": "videos", "video_id": "vid-a", "title": "Lecture", "chunk_id": "c2"},
            {"source": "textbooks", "title": "Textbook hit"},
        ]
        collapsed = collapse_video_cards_for_citations(cards)
        self.assertEqual(len(collapsed), 2)
        self.assertEqual(collapsed[0]["source"], "videos")
        self.assertEqual(collapsed[1]["source"], "textbooks")

    def test_path_blob_video_id_dedupes_by_title(self):
        cards = [
            {
                "source": "videos",
                "video_id": "gcs_gs_pathology_hub_02_normalized_lectures_lecture_chunks",
                "title": "Benign Cystic Neck Mass (Case 01)",
                "chunk_id": "c1",
            },
            {
                "source": "videos",
                "video_id": "gcs_gs_pathology_hub_02_normalized_lectures_lecture_chunks",
                "title": "Benign Cystic Neck Mass (Case 01)",
                "chunk_id": "c2",
            },
            {
                "source": "videos",
                "video_id": "gcs_gs_pathology_hub_02_normalized_lectures_lecture_chunks",
                "title": "Other Lecture Title",
                "chunk_id": "c3",
            },
        ]
        deduped = dedupe_video_cards(cards)
        self.assertEqual(len(deduped), 2)
        self.assertEqual({c["title"] for c in deduped}, {
            "Benign Cystic Neck Mass (Case 01)",
            "Other Lecture Title",
        })


class TestBestVideoCardPerLecture(unittest.TestCase):
    """Parity check for `videoLectureKey` / `bestVideoCardPerLecture` in app.js.

    Those two helpers collapse the "LECTURE SEGMENTS" gallery and "VIDEOS"
    list down to one best segment per distinct lecture (e.g. the screenshot
    bug: 5 timestamped chunks of one "BST Lecture 3 SoftTissue2" video all
    rendered as if they were 5 separate lectures). This file's tests hit
    app.js mostly via string assertions rather than a JS runtime, so this
    reimplements the same identity/tiebreak logic in Python and exercises it
    directly against the exact multi-segment-one-lecture shape from the bug
    report, plus a genuinely-multi-lecture case that must NOT collapse.
    """

    @staticmethod
    def _video_lecture_key(card):
        video_id = str(card.get("video_id") or "").strip()
        looks_like_path_blob = (
            not video_id
            or video_id.lower().startswith("gcs_gs_")
            or video_id.lower().endswith("lecture_chunks")
            or "/" in video_id
        )
        if not looks_like_path_blob:
            return video_id
        title = str(card.get("title") or "").strip()
        if title:
            return f"title:{title}"
        return video_id or str(card.get("chunk_id") or "").strip() or None

    @classmethod
    def _duration(cls, card):
        start = card.get("start_sec", card.get("start_time_sec"))
        end = card.get("end_sec", card.get("end_time_sec"))
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
            return end - start
        return 0

    @classmethod
    def _best_per_lecture(cls, rows):
        """rows: list of (card, score), already sorted by score descending."""
        winners = {}
        order = []
        for card, score in rows:
            key = cls._video_lecture_key(card) or f"chunk:{card.get('chunk_id')}"
            current = winners.get(key)
            if current is None:
                winners[key] = (card, score)
                order.append(key)
                continue
            current_card, current_score = current
            if score > current_score or (
                score == current_score and cls._duration(card) > cls._duration(current_card)
            ):
                winners[key] = (card, score)
        return [winners[key][0] for key in order]

    def test_five_segments_of_one_lecture_collapse_to_single_best(self):
        # Mirrors the screenshot: 5 timestamped segments, same lecture title,
        # path-blob-style video_id (so identity must fall back to title).
        rows = [
            ({"title": "BST Lecture 3 SoftTissue2", "video_id": "gcs_gs_pathology_hub_lecture_chunks",
              "chunk_id": "c1", "start_sec": 1846, "end_sec": 1959}, 1.0),
            ({"title": "BST Lecture 3 SoftTissue2", "video_id": "gcs_gs_pathology_hub_lecture_chunks",
              "chunk_id": "c2", "start_sec": 1382, "end_sec": 1492}, 1.0),
            ({"title": "BST Lecture 3 SoftTissue2", "video_id": "gcs_gs_pathology_hub_lecture_chunks",
              "chunk_id": "c3", "start_sec": 1624, "end_sec": 1717}, 1.0),
            ({"title": "BST Lecture 3 SoftTissue2", "video_id": "gcs_gs_pathology_hub_lecture_chunks",
              "chunk_id": "c4", "start_sec": 1718, "end_sec": 1846}, 1.0),
            ({"title": "BST Lecture 3 SoftTissue2", "video_id": "gcs_gs_pathology_hub_lecture_chunks",
              "chunk_id": "c5", "start_sec": 2202, "end_sec": 2311}, 1.0),
        ]
        best = self._best_per_lecture(rows)
        self.assertEqual(len(best), 1)
        # Equal scores -> longest segment wins (c4: 128s is the longest here).
        self.assertEqual(best[0]["chunk_id"], "c4")

    def test_higher_score_wins_over_longer_duration(self):
        rows = [
            ({"title": "Same Lecture", "video_id": "vid-x", "chunk_id": "short", "start_sec": 0, "end_sec": 10}, 1.0),
            ({"title": "Same Lecture", "video_id": "vid-x", "chunk_id": "long", "start_sec": 0, "end_sec": 500}, 0.5),
        ]
        best = self._best_per_lecture(rows)
        self.assertEqual(len(best), 1)
        self.assertEqual(best[0]["chunk_id"], "short")

    def test_genuinely_distinct_lectures_are_not_collapsed(self):
        rows = [
            ({"title": "Lecture A", "video_id": "vid-a", "chunk_id": "a1"}, 1.0),
            ({"title": "Lecture A", "video_id": "vid-a", "chunk_id": "a2"}, 0.8),
            ({"title": "Lecture B", "video_id": "vid-b", "chunk_id": "b1"}, 0.9),
        ]
        best = self._best_per_lecture(rows)
        self.assertEqual(len(best), 2)
        self.assertEqual({c["chunk_id"] for c in best}, {"a1", "b1"})

    def test_app_js_has_lecture_collapse_helpers(self):
        js = (MVP_DIR / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function videoLectureKey", js)
        self.assertIn("function bestVideoCardPerLecture", js)
        self.assertIn("function videoSegmentDurationSec", js)


class TestDdxRootPreference(unittest.TestCase):
    """DDx nav must prefer same organ root over first index hit (cyto-first)."""

    @classmethod
    def setUpClass(cls):
        idx_path = MVP_DIR / "static" / "browse_tag_index_v0_1.json"
        cls.index = json.loads(idx_path.read_text(encoding="utf-8"))
        cls.leaves = []
        for root in cls.index["roots"]:
            for sub in root["subcategories"]:
                for leaf in sub["leaves"]:
                    label = str(leaf.get("label") or "").replace("_", " ")
                    cls.leaves.append(
                        {
                            "categoryId": root["id"],
                            "subcategoryId": sub["id"],
                            "tag": leaf.get("tag"),
                            "label": leaf.get("label"),
                            "normalized": label.lower(),
                        }
                    )

    def _exact(self, name: str):
        norm = name.lower().replace("_", " ")
        return [leaf for leaf in self.leaves if leaf["normalized"] == norm]

    def _score(self, leaf, page_cat, page_sub, page_tag):
        score = 0
        page_root = (page_tag or "").split("::", 1)[0].lower() if page_tag else (page_cat or "")
        leaf_root = (leaf["tag"] or "").split("::", 1)[0].lower() if leaf.get("tag") else leaf["categoryId"]
        if page_cat and leaf["categoryId"] == page_cat:
            score += 100
        if page_root and leaf_root == page_root:
            score += 80
        if page_sub and leaf["subcategoryId"]:
            a = leaf["subcategoryId"].lower().replace("_", "")
            b = page_sub.lower().replace("_", "")
            if a == b:
                score += 75
            elif a in b or b in a:
                score += 50
            elif "salivary" in a and "salivary" in b:
                score += 25
        if page_cat and page_cat != "cyto" and leaf["categoryId"] == "cyto":
            score -= 40
        return score

    def _pick(self, candidates, page_cat, page_sub, page_tag):
        return max(candidates, key=lambda leaf: self._score(leaf, page_cat, page_sub, page_tag))

    def test_adenoid_cystic_from_hn_salivary_prefers_hn_not_cyto_breast(self):
        candidates = self._exact("Adenoid Cystic Carcinoma")
        self.assertGreaterEqual(len(candidates), 3)
        # First-in-index without preference is cyto (historical bug).
        self.assertEqual(candidates[0]["categoryId"], "cyto")
        best = self._pick(
            candidates,
            page_cat="hn",
            page_sub="Salivary_Gland",
            page_tag="HN::Salivary_Gland::Benign_Tumor::Pleomorphic_Adenoma",
        )
        self.assertEqual(best["categoryId"], "hn")
        self.assertIn("Salivary", best["tag"] or "")

    def test_app_js_has_page_context_ddx_helpers(self):
        js = (MVP_DIR / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function scoreLeafForPageContext", js)
        self.assertIn("function pickBestLeaf", js)
        self.assertIn("pageContextFromBrowseState", js)
        self.assertIn("findTaxonomyMatch(entityName, ctx)", js)


class TestMarkdownFenceHelpers(unittest.TestCase):
    def test_app_js_has_fence_unwrapper_and_link_normalizer(self):
        js_path = MVP_DIR / "static" / "app.js"
        js = js_path.read_text(encoding="utf-8")
        self.assertIn("function unwrapFencedMarkdownBlocks", js)
        self.assertIn("function normalizeInlineLinkLabel", js)
        self.assertIn("function renderTopicVideos", js)
        self.assertIn("function renderTopicLectureGallery", js)
        self.assertIn("function sectionHasContent", js)
        self.assertIn("function compactBrowseRoots", js)
        self.assertIn("compare-gallery-grid", js)
        self.assertIn("function findTaxonomyMatch", js)

    def test_fenced_markdown_table_unwraps_for_parsing(self):
        fenced = """```markdown
| Feature | A | B |
|---|---|---|
| Row | 1 | 2 |
```"""
        # Parity with unwrapFencedMarkdownBlocks in app.js
        import re

        def is_table(block: str) -> bool:
            lines = [ln for ln in block.split("\n") if ln.strip()]
            return len(lines) >= 2 and all("|" in ln for ln in lines)

        def unwrap(text: str) -> str:
            def repl(match: re.Match) -> str:
                lang = match.group(1) or ""
                body = match.group(2).strip()
                if not body:
                    return ""
                if is_table(body):
                    return body
                if not lang or lang.lower() in ("markdown", "md", "text"):
                    return body
                return match.group(0)

            return re.sub(r"```([a-zA-Z0-9_-]*)\s*\n([\s\S]*?)```", repl, text)

        unwrapped = unwrap(fenced)
        self.assertTrue(unwrapped.startswith("| Feature"))
        self.assertNotIn("```", unwrapped)


if __name__ == "__main__":
    unittest.main()
