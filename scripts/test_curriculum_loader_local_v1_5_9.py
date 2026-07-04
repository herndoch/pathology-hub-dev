#!/usr/bin/env python3
import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_APP = ROOT / "backend" / "pathology_hub_v04_curriculum" / "app.py"
OUTPUT_DIR = ROOT / "outputs" / "curriculum_map_v0_2"

os.environ.setdefault("PATHOLOGY_HUB_API_KEY", "test-key")
os.environ["CURRICULUM_SQLITE_GCS"] = str(OUTPUT_DIR / "curriculum_tag_index_v0_2.sqlite")
os.environ["CURRICULUM_NODES_GCS"] = str(OUTPUT_DIR / "curriculum_nodes_v0_2.csv")
os.environ["CURRICULUM_REVIEW_QUEUE_GCS"] = str(OUTPUT_DIR / "review_queue_v0_2.csv")
os.environ["CURRICULUM_REJECTED_TAGS_GCS"] = str(OUTPUT_DIR / "rejected_tags_v0_2.csv")
os.environ["CURRICULUM_ACCEPTANCE_GCS"] = str(OUTPUT_DIR / "acceptance_summary_v0_2.json")

FORBIDDEN = [
    "::Lectures::",
    "::Textbooks::",
    "::Error",
    "Slide_",
    "Page_",
    "Digital_Pathology_Slide",
    "Pathology_Slide",
    "rejected_generated",
]


def load_app_module():
    spec = importlib.util.spec_from_file_location("curriculum_backend_app", BACKEND_APP)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def assert_no_forbidden(resp):
    for row in resp.get("curriculum_results") or []:
        tag = row.get("tag") or ""
        hits = [p for p in FORBIDDEN if p in tag]
        assert not hits, f"Forbidden patterns {hits} in {tag}"


def main():
    from fastapi.testclient import TestClient

    mod = load_app_module()

    # Keep the local test focused on the v1.5.9 wrapper. The previous endpoint
    # would otherwise download legacy FAISS/JSONL assets and call embeddings.
    mod._OLD_HEALTH_ENDPOINT_V159 = lambda: {
        "schema_version": "pathology_hub_health.v1.5.8",
        "version": "1.5.8-pathout-lecture-tags-v04",
        "search_mode": {},
    }
    mod._OLD_SEARCH_ENDPOINT_V159 = lambda req, request, x_api_key=None: {
        "schema_version": "evidence_search_response.v1.5.8",
        "query": req.query,
        "source_status": {s: "ok" for s in req.sources},
        "warnings": [],
        "search_mode": {},
        "figures": [],
    }

    client = TestClient(mod.app)
    headers = {"X-API-Key": "test-key"}

    health = client.get("/health", headers=headers)
    assert health.status_code == 200, health.text
    h = health.json()
    assert h["curriculum_map_enabled"] is True
    assert h["curriculum_map_version"] == "v0.2"
    assert h["curriculum_map_build_status"] == "passed_local_visibility_gate"
    assert h["curriculum_map_forbidden_visible_tag_count"] == 0
    assert h["curriculum_map_records_visible"] == 137293
    assert h["curriculum_map_review_queue_count"] == 4245

    for payload in [
        {"query": "GYN::Ovary", "sources": ["curriculum"], "max_results": 5, "compact": True},
        {"query": "ovary granulosa", "sources": ["curriculum"], "max_results": 5, "compact": True},
    ]:
        resp = client.post("/evidence/search", headers=headers, json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["source_status"]["curriculum"] == "ok"
        assert data["curriculum_status"]["build_status"] == "passed_local_visibility_gate"
        assert data["curriculum_results"], payload
        assert_no_forbidden(data)

    print("local curriculum tests passed")


if __name__ == "__main__":
    main()
