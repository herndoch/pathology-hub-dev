#!/usr/bin/env python3
"""Smoke-test Chat MVP browse UX features (API + static assets).

Offline checks use FastAPI TestClient (no live keys). Live checks optional via
--base-url when the app is already running (./scripts/run_local.sh).

Usage:
    python3 scripts/smoke_test_chat_mvp_v0_1.py
    python3 scripts/smoke_test_chat_mvp_v0_1.py --base-url http://127.0.0.1:8000 --live
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

MVP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = MVP_DIR.parents[1]
if str(MVP_DIR) not in sys.path:
    sys.path.insert(0, str(MVP_DIR))

import requests  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


def _ok(name: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  OK  {name}{suffix}")


def _fail(name: str, detail: str) -> None:
    print(f"  FAIL {name}: {detail}")
    raise SystemExit(1)


def smoke_offline() -> None:
    print("Offline smoke (TestClient)")
    client = TestClient(app)

    idx = client.get("/static/browse_tag_index_v0_1.json")
    if idx.status_code != 200:
        _fail("browse index", f"HTTP {idx.status_code}")
    data = idx.json()
    if data.get("schema_version") != "browse_tag_index_v0_2":
        _fail("browse index schema", data.get("schema_version"))
    counts = data.get("counts") or {}
    if counts.get("roots_total", 0) < 10:
        _fail("browse roots", str(counts))
    _ok("browse index", f"{counts.get('leaves_total')} leaves, {counts.get('roots_total')} roots")

    js = client.get("/static/app.js").text
    for needle in (
        'pathout: "Pathoutlines"',
        "formatSubcategoryLabel",
        "compare-tray",
        'event.key === "ArrowLeft"',
        "media-modal-prev",
        "/api/flag",
        "/api/compare",
    ):
        if needle not in js:
            _fail("app.js feature", f"missing {needle!r}")
    _ok("app.js UX features")

    css = client.get("/static/style.css").text
    for needle in (".compare-tray", ".compare-column", ".vs-btn"):
        if needle not in css:
            _fail("style.css", f"missing {needle!r}")
    _ok("style.css compare/VS styles")

    health = client.get("/api/health").json()
    if "topic_page_root_narrow" not in health:
        _fail("health", "missing topic_page_root_narrow")
    _ok("health", f"root_narrow={health.get('topic_page_root_narrow')}")

    flag_resp = client.post("/api/flag", json={"tag": "smoke::test", "label": "Smoke", "comment": ""})
    if flag_resp.status_code != 200 or flag_resp.json().get("ok") is not False:
        _fail("flag empty comment", flag_resp.text)
    _ok("flag rejects empty comment")

    with tempfile.TemporaryDirectory() as tmp:
        flags_path = Path(tmp) / "flags.jsonl"
        import app as app_module

        old_path = app_module.PAGE_FLAGS_PATH
        old_dir = app_module.PAGE_FLAGS_DIR
        try:
            app_module.PAGE_FLAGS_DIR = str(tmp)
            app_module.PAGE_FLAGS_PATH = str(flags_path)
            good = client.post(
                "/api/flag",
                json={
                    "tag": "HN::Salivary_Gland::Benign_Tumor::Pleomorphic_Adenoma",
                    "label": "Pleomorphic Adenoma",
                    "query": "pleomorphic adenoma",
                    "comment": "smoke test flag",
                },
            )
            if good.status_code != 200 or not good.json().get("ok"):
                _fail("flag append", good.text)
            lines = flags_path.read_text(encoding="utf-8").strip().splitlines()
            if len(lines) != 1:
                _fail("flag jsonl", f"expected 1 line, got {len(lines)}")
            rec = json.loads(lines[0])
            if rec.get("schema_version") != "page_flags_v0_1":
                _fail("flag schema", rec.get("schema_version"))
        finally:
            app_module.PAGE_FLAGS_PATH = old_path
            app_module.PAGE_FLAGS_DIR = old_dir
    _ok("flag append JSONL")

    cmp_resp = client.post("/api/compare", json={"entities": [{"tag": "a", "label": "A", "query": "a"}]})
    if cmp_resp.status_code != 422:
        _fail("compare min entities", f"HTTP {cmp_resp.status_code}")
    _ok("compare validates min 2 entities")


def smoke_live(base_url: str) -> None:
    print(f"\nLive smoke ({base_url})")
    health = requests.get(f"{base_url}/api/health", timeout=15).json()
    secrets = health.get("secrets") or {}
    openai_ok = bool((secrets.get("openai") or {}).get("present"))
    hub_ok = bool((secrets.get("pathology_hub") or {}).get("present"))
    if not hub_ok:
        _fail("live secrets", "pathology_hub key missing")
    _ok("live health", f"openai={openai_ok} hub={hub_ok} model={health.get('openai_model')}")

    static_js = requests.get(f"{base_url}/static/app.js", timeout=15).text
    if "Pathoutlines" not in static_js:
        _fail("live static", "Pathoutlines label missing")
    _ok("live static served")

    if not openai_ok:
        print("  SKIP live topic_page (OPENAI_API_KEY not present)")
        return

    payload = {
        "query": "pleomorphic adenoma salivary gland",
        "mode": "topic_page",
        "category_context": "Head & Neck > Salivary Gland",
        "page_tag": "HN::Salivary_Gland::Benign_Tumor::Pleomorphic_Adenoma",
        "include_figures": True,
        "max_figures": 4,
    }
    resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=180)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("ok"):
        _fail("live topic_page", body.get("error") or body.get("answer_error") or "not ok")
    answer = body.get("answer") or ""
    if not re.search(r"##\s*Key Facts", answer, re.I):
        _fail("live topic_page", "missing Key Facts section")
    _ok("live topic_page", f"cards={len(body.get('cards') or [])} chars={len(answer)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--live", action="store_true", help="Also run live API checks against base-url")
    args = parser.parse_args()

    smoke_offline()
    if args.live:
        try:
            smoke_live(args.base_url.rstrip("/"))
        except requests.RequestException as exc:
            _fail("live connection", str(exc))
    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    main()
