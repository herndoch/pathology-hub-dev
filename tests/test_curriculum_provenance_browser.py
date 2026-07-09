"""Smoke tests for the local curriculum provenance browser."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "tools" / "curriculum_provenance_browser"
APP_PATH = APP_DIR / "app.py"

# Two real textbook record_ids sharing a rare approved_tag (used so a narrow
# search filter can exercise both fixture rows without scanning the full
# 98k-row textbooks family). These are used purely as join keys for the
# quality-flags fixture below; the fixture's tier/flags values are synthetic.
FIXTURE_TIER_A_RECORD_ID = (
    "gapfill_v0_4:textbooks:tbchunk:bone_pattern:bone_pattern_p0299_c003:"
    "BST::Soft_Tissue::Skeletal_Muscle::Malignant::Ectomesenchymoma"
)
FIXTURE_TIER_B_RECORD_ID = (
    "gapfill_v0_4:textbooks:tbchunk:hn_biopsy_interpretation:"
    "hn_biopsy_interpretation_p0283_c001:"
    "BST::Soft_Tissue::Skeletal_Muscle::Malignant::Ectomesenchymoma"
)
FIXTURE_SHARED_APPROVED_TAG = "BST::Soft_Tissue::Skeletal_Muscle::Malignant::Ectomesenchymoma"


def load_app_module():
    spec = importlib.util.spec_from_file_location("curriculum_provenance_browser_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CurriculumProvenanceBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_app_module()
        src = REPO_ROOT / "outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_1.sqlite"
        if not src.exists():
            raise unittest.SkipTest(f"missing sqlite index: {src}")
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_copy = Path(cls.temp_dir.name) / "index.sqlite"
        cls.db_copy.write_bytes(src.read_bytes())
        cls.module.SQLITE_PATH = cls.db_copy

        # Small fixture quality-flags JSONL: one Tier A (suppress_render) row
        # and one Tier B (warn_render) row, keyed by real record_ids from the
        # copied sqlite index so both /api/search and /api/records/{id} can
        # be exercised against them.
        cls.quality_flags_fixture = Path(cls.temp_dir.name) / "quality_flags_fixture.jsonl"
        fixture_rows = [
            {
                "record_id": FIXTURE_TIER_A_RECORD_ID,
                "chunk_id": "tbchunk:bone_pattern:bone_pattern_p0299_c003",
                "source_id": "bone_pattern",
                "fig_slot": "fig01",
                "width": 7,
                "height": 7,
                "aspect_ratio": 1.0,
                "flags": ["tiny_image"],
                "tier": "suppress_render",
            },
            {
                "record_id": FIXTURE_TIER_B_RECORD_ID,
                "chunk_id": "tbchunk:hn_biopsy_interpretation:hn_biopsy_interpretation_p0283_c001",
                "source_id": "hn_biopsy_interpretation",
                "fig_slot": "fig01",
                "width": 1200,
                "height": 90,
                "aspect_ratio": 13.33,
                "flags": ["extreme_aspect_ratio", "wide_strip_header_footer_suspect"],
                "tier": "warn_render",
            },
        ]
        with cls.quality_flags_fixture.open("w", encoding="utf-8") as fh:
            for row in fixture_rows:
                fh.write(json.dumps(row) + "\n")
        cls.module.QUALITY_FLAGS_JSONL_PATH = cls.quality_flags_fixture
        cls.module._quality_flags_cache = None
        cls.module._quality_flags_cache_path = None

        cls.client = TestClient(cls.module.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_health(self) -> None:
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["sqlite_exists"])

    def test_summary(self) -> None:
        res = self.client.get("/api/summary")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("rows", body)
        self.assertGreater(len(body["rows"]), 0)

    def test_search_partial_textbooks(self) -> None:
        res = self.client.get(
            "/api/search",
            params={"source_family": "textbooks", "completeness": "partial", "limit": 5},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertGreater(body["total"], 0)
        self.assertTrue(all(r["locator_status"] == "partial" for r in body["rows"]))

    def test_record_detail(self) -> None:
        conn = sqlite3.connect(str(self.db_copy))
        record_id = conn.execute("select record_id from provenance_records limit 1").fetchone()[0]
        conn.close()
        res = self.client.get(f"/api/records/{record_id}")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["record_id"], record_id)
        self.assertIn("locator_summary", body)
        self.assertIn("fields", body)

    def test_quality_flag_join_tier_a_and_tier_b(self) -> None:
        tier_a_res = self.client.get(f"/api/records/{FIXTURE_TIER_A_RECORD_ID}")
        self.assertEqual(tier_a_res.status_code, 200)
        tier_a_body = tier_a_res.json()
        self.assertIsNotNone(tier_a_body["quality_flag"])
        self.assertEqual(tier_a_body["quality_flag"]["tier"], "suppress_render")
        self.assertEqual(tier_a_body["quality_flag"]["width"], 7)
        self.assertEqual(tier_a_body["quality_flag"]["height"], 7)
        self.assertIn("tiny_image", tier_a_body["quality_flag"]["flags"])

        tier_b_res = self.client.get(f"/api/records/{FIXTURE_TIER_B_RECORD_ID}")
        self.assertEqual(tier_b_res.status_code, 200)
        tier_b_body = tier_b_res.json()
        self.assertIsNotNone(tier_b_body["quality_flag"])
        self.assertEqual(tier_b_body["quality_flag"]["tier"], "warn_render")
        self.assertIn("extreme_aspect_ratio", tier_b_body["quality_flag"]["flags"])

        # A record with no sidecar entry should come back with quality_flag: null.
        conn = sqlite3.connect(str(self.db_copy))
        other_record_id = conn.execute(
            "select record_id from provenance_records where record_id != ? and record_id != ? limit 1",
            (FIXTURE_TIER_A_RECORD_ID, FIXTURE_TIER_B_RECORD_ID),
        ).fetchone()[0]
        conn.close()
        clean_res = self.client.get(f"/api/records/{other_record_id}")
        self.assertEqual(clean_res.status_code, 200)
        self.assertIsNone(clean_res.json()["quality_flag"])

    def test_search_quality_filter(self) -> None:
        # Narrow to the two fixture rows' shared (rare) approved_tag so this
        # exercises the in-memory quality filter without scanning the whole
        # textbooks family.
        base_params = {"approved_tag": FIXTURE_SHARED_APPROVED_TAG, "limit": 50}

        all_res = self.client.get("/api/search", params={**base_params, "quality": "all"})
        self.assertEqual(all_res.status_code, 200)
        all_ids = {r["record_id"] for r in all_res.json()["rows"]}
        self.assertIn(FIXTURE_TIER_A_RECORD_ID, all_ids)
        self.assertIn(FIXTURE_TIER_B_RECORD_ID, all_ids)

        suppressed_res = self.client.get("/api/search", params={**base_params, "quality": "suppressed"})
        self.assertEqual(suppressed_res.status_code, 200)
        suppressed_body = suppressed_res.json()
        suppressed_ids = {r["record_id"] for r in suppressed_body["rows"]}
        self.assertIn(FIXTURE_TIER_A_RECORD_ID, suppressed_ids)
        self.assertNotIn(FIXTURE_TIER_B_RECORD_ID, suppressed_ids)
        self.assertEqual(suppressed_body["total"], len(suppressed_ids))
        for row in suppressed_body["rows"]:
            self.assertEqual(row["quality_flag"]["tier"], "suppress_render")

        flagged_res = self.client.get("/api/search", params={**base_params, "quality": "flagged"})
        self.assertEqual(flagged_res.status_code, 200)
        flagged_ids = {r["record_id"] for r in flagged_res.json()["rows"]}
        self.assertIn(FIXTURE_TIER_A_RECORD_ID, flagged_ids)
        self.assertIn(FIXTURE_TIER_B_RECORD_ID, flagged_ids)

        clean_res = self.client.get("/api/search", params={**base_params, "quality": "clean"})
        self.assertEqual(clean_res.status_code, 200)
        clean_ids = {r["record_id"] for r in clean_res.json()["rows"]}
        self.assertNotIn(FIXTURE_TIER_A_RECORD_ID, clean_ids)
        self.assertNotIn(FIXTURE_TIER_B_RECORD_ID, clean_ids)

        invalid_res = self.client.get("/api/search", params={**base_params, "quality": "not-a-real-value"})
        self.assertEqual(invalid_res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
