"""Offline unit tests for iterative topic-page retrieval + SSE stream."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
MVP = ROOT / "frontend" / "pathology_hub_chat_mvp"
sys.path.insert(0, str(MVP))

from pathology_backend import SearchOutcome  # noqa: E402

SAMPLE_RESPONSE = {
    "ok": True,
    "query": "secretory carcinoma",
    "source_status": {"textbooks": "ok", "who": "ok", "pathout": "ok", "videos": "ok"},
    "textbook_results": [
        {
            "source": "textbooks",
            "source_id": "breast_atlas",
            "title": "Secretory carcinoma",
            "text_excerpt": "ETV6-NTRK3 fusion. Gross: firm white mass. Imaging: US hypoechoic.",
            "rank": 1,
        }
    ],
    "who_results": [
        {
            "source": "who",
            "title": "Secretory carcinoma of the breast",
            "text_excerpt": "Rare carcinoma with ETV6::NTRK3. Differential includes acinic.",
            "rank": 1,
        }
    ],
    "pathout_results": [],
    "video_results": [],
    "figures": [],
}


def _fake_outcomes(query, sources):
    return [
        SearchOutcome(
            request_payload={"query": query, "sources": [s]},
            url="http://mock/evidence/search",
            status_code=200,
            ok=True,
            elapsed_ms=1.0,
            response_json=SAMPLE_RESPONSE,
            api_key_present=True,
        )
        for s in sources
    ]


class IterativeRetrievalTests(unittest.TestCase):
    def test_flags_default_on(self):
        import iterative_topic_retrieval as itr

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TOPIC_PAGE_ITERATIVE", None)
            os.environ.pop("TOPIC_PAGE_ITERATIVE_ROUNDS", None)
            self.assertTrue(itr.iterative_enabled())
            self.assertEqual(itr.max_rounds(), 3)

    def test_rounds_clamped(self):
        import iterative_topic_retrieval as itr

        with patch.dict(os.environ, {"TOPIC_PAGE_ITERATIVE_ROUNDS": "99"}):
            self.assertEqual(itr.max_rounds(), 3)
        with patch.dict(os.environ, {"TOPIC_PAGE_ITERATIVE_ROUNDS": "0"}):
            self.assertEqual(itr.max_rounds(), 1)

    def test_generator_emits_progress_and_returns_bundle(self):
        import iterative_topic_retrieval as itr

        lit_bundle = {
            "cards": [
                {
                    "source": "literature",
                    "title": "Secretory carcinoma review",
                    "doi": "10.1000/test",
                    "excerpt": "ETV6 NTRK3 clinicopathologic",
                }
            ],
            "providers": {"scopus": {"ok": True, "returned": 1, "total": 10}},
            "warnings": [],
        }

        with patch.dict(
            os.environ,
            {"TOPIC_PAGE_ITERATIVE": "1", "TOPIC_PAGE_ITERATIVE_ROUNDS": "3", "TOPIC_PAGE_LIVE_LITERATURE": "1"},
        ), patch(
            "iterative_topic_retrieval.staged_retrieve",
            side_effect=lambda client, query, sources, **kw: _fake_outcomes(query, sources),
        ), patch(
            "iterative_topic_retrieval.fetch_live_literature",
            return_value=lit_bundle,
        ), patch(
            "iterative_topic_retrieval.live_literature_enabled",
            return_value=True,
        ):
            gen = itr.run_iterative_topic_retrieval(
                MagicMock(),
                query="secretory carcinoma breast",
                sources=["textbooks", "who", "pathout", "videos"],
                max_results=3,
                include_figures=True,
                max_figures=4,
            )
            events = []
            try:
                while True:
                    events.append(next(gen))
            except StopIteration as stop:
                final = stop.value

        phases = [e.get("phase") for e in events]
        self.assertIn("plan", phases)
        self.assertIn("round", phases)
        self.assertIn("literature", phases)
        self.assertIn("assemble", phases)
        self.assertTrue(any(e.get("status") == "running" for e in events))
        self.assertTrue(any(e.get("status") == "done" for e in events))
        self.assertIsInstance(final, dict)
        self.assertTrue(final["retrieval_meta"]["iterative"])
        self.assertGreaterEqual(len(final["retrieval_meta"]["round_summaries"]), 2)
        self.assertTrue(any((c.get("source") == "literature") for c in final["cards"]))


class ChatStreamEndpointTests(unittest.TestCase):
    def test_health_exposes_iterative_and_ui_sources(self):
        from fastapi.testclient import TestClient

        import app as app_mod
        from app import UI_SOURCES

        with patch.object(app_mod._backend_client, "health", return_value={"ok": True}), patch(
            "app.secrets_helper.all_secret_status", return_value={}
        ):
            client = TestClient(app_mod.app)
            resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("ui_sources", body)
        self.assertNotIn("journals", body["ui_sources"])
        self.assertEqual(body["ui_sources"], UI_SOURCES)
        self.assertIn("topic_page_iterative", body)
        self.assertIn("topic_page_live_literature", body)
        self.assertTrue(body.get("scopus_paren_sanitize"))
        self.assertEqual(body.get("build_marker"), "topic-iterative-sse-layout-9231")

    def test_sse_stream_topic_page_emits_progress_then_result(self):
        from fastapi.testclient import TestClient

        import app as app_mod

        lit_bundle = {"cards": [], "providers": {}, "warnings": []}

        with patch.dict(
            os.environ,
            {
                "TOPIC_PAGE_ITERATIVE": "1",
                "TOPIC_PAGE_ITERATIVE_ROUNDS": "2",
                "TOPIC_PAGE_LIVE_LITERATURE": "1",
            },
        ), patch(
            "iterative_topic_retrieval.staged_retrieve",
            side_effect=lambda client, query, sources, **kw: _fake_outcomes(query, sources),
        ), patch(
            "iterative_topic_retrieval.fetch_live_literature",
            return_value=lit_bundle,
        ), patch(
            "iterative_topic_retrieval.live_literature_enabled",
            return_value=True,
        ), patch(
            "app.synthesize"
        ) as mock_synthesize:
            mock_synthesize.return_value = MagicMock(
                ok=True,
                text="## Key Facts\n- test",
                model="test-model",
                evidence_truncated=False,
                evidence_char_len=100,
            )
            client = TestClient(app_mod.app)
            with client.stream(
                "POST",
                "/api/chat/stream",
                json={"query": "secretory carcinoma", "mode": "topic_page", "sources": ["textbooks"]},
            ) as resp:
                self.assertEqual(resp.status_code, 200)
                self.assertIn("text/event-stream", resp.headers.get("content-type", ""))
                raw = "".join(resp.iter_text())

        self.assertIn("event: progress", raw)
        self.assertIn("event: result", raw)
        # Parse last result event
        blocks = [b for b in raw.split("\n\n") if b.strip()]
        result = None
        progress_count = 0
        for block in blocks:
            lines = block.split("\n")
            event = "message"
            data_lines = []
            for line in lines:
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
            if not data_lines:
                continue
            data = json.loads("\n".join(data_lines))
            if event == "progress":
                progress_count += 1
            if event == "result":
                result = data
        self.assertGreaterEqual(progress_count, 3)
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "topic_page")
        self.assertTrue(result["debug"].get("iterative"))


if __name__ == "__main__":
    unittest.main()
