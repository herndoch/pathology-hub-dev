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
    schema = data.get("schema_version")
    if schema not in {"browse_tag_index_v0_2", "browse_tag_index_v0_3", "browse_tag_index_v0_4"}:
        _fail("browse index schema", schema)
    counts = data.get("counts") or {}
    if counts.get("roots_total", 0) < 10:
        _fail("browse roots", str(counts))
    rules = data.get("dedupe_rules") or {}
    nav_sources = rules.get("nav_sources") or []
    allowed_nav = (
        nav_sources == ["abpath_content_spec", "who"]
        or nav_sources == ["abpath", "who"]
    )
    if not allowed_nav or rules.get("pathout_nav") is not False:
        _fail("browse nav sources", nav_sources)
    prov_vals = rules.get("provenance_values") or []
    if not set(["abpath", "who", "both"]).issubset(set(prov_vals)):
        _fail("browse provenance values", prov_vals)
    if schema in {"browse_tag_index_v0_3", "browse_tag_index_v0_4"}:
        if rules.get("bloated_abpath_ontology_excluded") is not True:
            _fail("bloated ontology exclusion", rules.get("bloated_abpath_ontology_excluded"))
        if not counts.get("abpath_content_spec_terminal_rows"):
            _fail("content-spec terminal rows", str(counts))
        # Guardrail: must not silently reintroduce the ~6k ontology expansion.
        if (counts.get("leaves_abpath_only") or 0) > 4500:
            _fail("abpath-only leaf count looks like bloated ontology", str(counts))
        if rules.get("abpath_topic_filter") != "diagnosis_entities_only":
            _fail("abpath topic filter", rules.get("abpath_topic_filter"))
        if (counts.get("content_spec_rows_dropped_non_diagnosis") or 0) < 50:
            _fail(
                "expected non-diagnosis content-spec drops",
                str(counts.get("content_spec_rows_dropped_non_diagnosis")),
            )
    if schema == "browse_tag_index_v0_4":
        variants = data.get("nav_variants") or {}
        if "who" not in variants or "who_pathout" not in variants:
            _fail("nav variants missing", sorted(variants))
        who_total = (variants.get("who") or {}).get("counts", {}).get("leaves_total") or 0
        who_po_total = (variants.get("who_pathout") or {}).get("counts", {}).get("leaves_total") or 0
        if who_total < 500:
            _fail("who variant too small", str(who_total))
        if who_po_total <= who_total:
            _fail("who_pathout should exceed who-only", f"{who_po_total} vs {who_total}")
        if rules.get("pathout_nav") is not False:
            _fail("default pathout_nav should stay false", rules.get("pathout_nav"))
        # Architecture hygiene: Bone/Bones must be collapsed; no Soft_TissueAdipocytic.
        bst = next((r for r in data.get("roots") or [] if r.get("id") == "bst"), None)
        if not bst:
            _fail("missing bst root", None)
        else:
            sub_ids = {s.get("id") for s in bst.get("subcategories") or []}
            if "bones" in sub_ids and "bone" in sub_ids:
                _fail("bst still has Bone + Bones split", sorted(sub_ids))
            if "soft_tissueadipocytic" in sub_ids:
                _fail("bst still has Soft_TissueAdipocytic", sorted(sub_ids))
        # Ancillary/QA buckets should not remain as Browse subcategories.
        bad_subs = []
        for root in data.get("roots") or []:
            for sub in root.get("subcategories") or []:
                label = str(sub.get("label") or "")
                if re.search(r"(?i)ancillary|qc/?qa|indications\s*/\s*techniques", label):
                    bad_subs.append(f"{root.get('id')}:{label}")
        if bad_subs:
            _fail("methodology subcategory buckets remain", bad_subs[:8])
        # No leaf may be a residual "Other ..." catch-all or a bare generic
        # word with zero organ/entity-specific qualifier — not prebuild-worthy.
        generic_bare = {
            "benign", "malignant", "premalignant", "borderline", "carcinoma",
            "sarcoma", "lymphoma", "leukemia", "adenoma", "tumor", "tumour",
            "tumors", "tumours", "neoplasm", "neoplasms", "lesion", "lesions",
            "disorder", "disorders", "disease", "diseases", "syndrome",
            "infection", "infections", "infectious", "inflammatory", "other",
            "others", "general", "normal", "miscellaneous", "cyst", "cysts",
            "polyp", "polyps", "hyperplasia", "metaplasia", "dysplasia",
            "atypia", "metastasis", "metastases", "condition", "conditions",
            "change", "changes", "process", "processes", "topic", "topics",
            "type", "types",
        }
        bad_leaves = []
        for root in data.get("roots") or []:
            for sub in root.get("subcategories") or []:
                for leaf in sub.get("leaves") or []:
                    label = str(leaf.get("label") or "").replace("_", " ")
                    if re.match(r"(?i)^other\b", label):
                        bad_leaves.append(f"{root.get('id')}:{label}")
                        continue
                    toks = re.sub(r"[^a-z0-9]+", " ", label.lower()).split()
                    if toks and all(t in generic_bare for t in toks):
                        bad_leaves.append(f"{root.get('id')}:{label}")
        if bad_leaves:
            _fail("non-prebuildable leaf topics remain", bad_leaves[:10])
        # No "The X" / "X" or "X Gland(s)" / "X" near-duplicate subcategories.
        stop = {"the", "of", "gland"}

        def _sing(t: str) -> str:
            if len(t) > 4 and t.endswith("ies"):
                return t[:-3] + "y"
            if len(t) > 4 and t.endswith("ses"):
                return t[:-2]
            if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
                return t[:-1]
            return t

        def _sub_key(label: str) -> str:
            toks = [_sing(t) for t in re.sub(r"[^a-z0-9]+", " ", label.lower()).split() if t]
            toks = [t for t in toks if t not in stop]
            return " ".join(sorted(toks))

        for root in data.get("roots") or []:
            seen: dict[str, str] = {}
            for sub in root.get("subcategories") or []:
                k = _sub_key(str(sub.get("label") or ""))
                if k in seen:
                    _fail(
                        "near-duplicate subcategories",
                        f"{root.get('id')}: {seen[k]!r} vs {sub.get('label')!r}",
                    )
                seen[k] = sub.get("label")
        # Heme must always read as Hematolymphoid, never the old label.
        heme_root = next((r for r in data.get("roots") or [] if r.get("id") == "heme"), None)
        if not heme_root or heme_root.get("label") != "Hematolymphoid":
            _fail("heme root label", heme_root.get("label") if heme_root else None)
        js = client.get("/static/app.js").text
        if 'data-browse-mode=' in js:
            _fail("browse mode toggle should be removed", "found data-browse-mode in app.js")
        for needle in ('"Hematolymphoid"', "browse-tile-glyph"):
            if needle not in js:
                _fail("browse UI missing", needle)
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
        "ACCEPTED_NAV_PROVENANCES",
        "PathologyOutlines",
        "formatNavProvenanceLabel",
        "unwrapFencedMarkdownBlocks",
        "renderTopicVideos",
        "compare-gallery-grid",
        "normalizeInlineLinkLabel",
        "scoreLeafForPageContext",
        "pickBestLeaf",
    ):
        if needle not in js:
            _fail("app.js feature", f"missing {needle!r}")
    _ok("app.js UX features")

    css = client.get("/static/style.css").text
    for needle in (".compare-tray", ".compare-column", ".vs-btn", ".topic-videos"):
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
