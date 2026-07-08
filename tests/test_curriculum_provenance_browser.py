"""Smoke tests for the local curriculum provenance browser."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "tools" / "curriculum_provenance_browser"
APP_PATH = APP_DIR / "app.py"


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


if __name__ == "__main__":
    unittest.main()
