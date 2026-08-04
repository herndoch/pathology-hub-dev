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


def smoke_unpaywall() -> None:
    """Structural-only checks (no network) so a rename/removal is caught even
    when Elsevier/NCBI keys aren't available locally."""
    import literature_apis as lit

    if lit.unpaywall_email() != "herndon.charlie@gmail.com" and not __import__("os").environ.get(
        "UNPAYWALL_EMAIL"
    ):
        _fail("unpaywall default email", lit.unpaywall_email())
    for needle in ("unpaywall_enabled", "enrich_cards_with_open_access", "_unpaywall_lookup"):
        if not hasattr(lit, needle):
            _fail("unpaywall function missing", needle)
    card = lit._card(
        title="t", journal="j", doi="10.1/x", abstract="a", year="2020",
        retrieval_mode="test", source_name="Test",
    )
    for key in ("is_open_access", "open_access_url", "open_access_status"):
        if key not in card:
            _fail("literature card missing open-access field", key)
    # No-DOI card must pass through unchanged with unpaywall disabled or on.
    nodoi = lit._card(
        title="t2", journal="j2", doi=None, abstract="", year=None,
        retrieval_mode="test", source_name="Test",
    )
    if lit._enrich_card_open_access(dict(nodoi)) != nodoi:
        _fail("no-doi card should pass through unpaywall enrichment unchanged", None)
    _ok("unpaywall integration (structural, offline)")


def smoke_model_selector() -> None:
    """Structural (offline) checks for the per-request synthesis model
    override (2026-08-02: "would like option to be able to select model" —
    luna default, terra/sol selectable)."""
    import openai_synthesizer as synth

    if synth.get_topic_page_model() not in synth.SUPPORTED_SYNTHESIS_MODELS:
        _fail("default topic-page model not in its own allowlist", synth.get_topic_page_model())
    if synth.resolve_synthesis_model("gpt-5.6-terra") != "gpt-5.6-terra":
        _fail("resolve_synthesis_model should honor an allowlisted override", None)
    if synth.resolve_synthesis_model("not-a-real-model") != synth.get_topic_page_model():
        _fail("resolve_synthesis_model should ignore an unrecognized model", None)
    if synth.resolve_synthesis_model(None) != synth.get_topic_page_model():
        _fail("resolve_synthesis_model should default when no override given", None)
    _ok("model selector allowlist/fallback (structural, offline)")


def smoke_cyto_root_narrow() -> None:
    """Structural (offline) checks for the B9 cyto-strictness fix (2026-08-01):
    a bare "cyto" root target (content-spec `ABPathSpec::cyto::…` pages have
    no resolvable organ) must fall back to non-strict matching instead of
    silently dropping every WHO/textbook/pathout/video card — see
    is_cyto_root_token / _root_matches_page in pathology_backend.py."""
    import pathology_backend as backend

    if backend.is_cyto_root_token("cyto"):
        _fail("bare 'cyto' token should not be strict-cyto", "is_cyto_root_token('cyto') is True")
    if not backend.is_cyto_root_token("cytogyn"):
        _fail("organ-specific cyto token should still be strict-cyto", "is_cyto_root_token('cytogyn') is False")
    if backend.is_cyto_root_token("breast"):
        _fail("non-cyto token misclassified as cyto", "is_cyto_root_token('breast') is True")

    # Bare-cyto target: an organ-specific card root must still be kept (cyto
    # family match), not dropped for failing to equal the bare target exactly.
    if not backend._root_matches_page("cytogyn", "cyto", False):
        _fail("organ-specific card should match bare 'cyto' target", None)
    if backend._root_matches_page("breast", "cyto", False):
        _fail("non-cyto card should not match bare 'cyto' target", None)

    cards = [
        {"source": "textbooks", "primary_tag": "Cyto_GYN::Squamous::LSIL"},
        {"source": "textbooks", "primary_tag": "Breast::Neoplastic::Invasive_Ductal_Carcinoma"},
        {"source": "who", "primary_tag": None},
    ]
    kept = backend.filter_cards_by_page_root(cards, "cyto")
    kept_sources = [(c.get("source"), c.get("primary_tag")) for c in kept]
    if ("textbooks", "Cyto_GYN::Squamous::LSIL") not in kept_sources:
        _fail("cyto-family textbook card wrongly dropped for bare 'cyto' target", kept_sources)
    if ("textbooks", "Breast::Neoplastic::Invasive_Ductal_Carcinoma") in kept_sources:
        _fail("non-cyto textbook card wrongly kept for bare 'cyto' target", kept_sources)
    if ("who", None) not in kept_sources:
        _fail("WHO card wrongly dropped for bare 'cyto' target (non-strict policy)", kept_sources)
    _ok("cyto root-narrow bare-token fallback (structural, offline)")


def smoke_offline() -> None:
    print("Offline smoke (TestClient)")
    smoke_unpaywall()
    smoke_model_selector()
    smoke_cyto_root_narrow()
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
        # No leftover "a)"/"iii)"/"1)" list markers in leaf labels (2026-08-02
        # — parser only recognized "a."/"iii." period-style markers, not the
        # parenthesis style some ABPath sections use).
        list_marker_re = re.compile(r"^(?:[a-zA-Z]|[ivxlcIVXLC]+|\d+)\)\s+")
        marker_leaves = []
        for root in data.get("roots") or []:
            for sub in root.get("subcategories") or []:
                for leaf in sub.get("leaves") or []:
                    if list_marker_re.match(str(leaf.get("label") or "")):
                        marker_leaves.append(f"{root.get('id')}:{leaf.get('label')}")
        if marker_leaves:
            _fail("leftover list-marker prefixes in leaf labels", marker_leaves[:10])
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
        # Known WHO source typo (doubled letter) must be self-healed.
        for root in data.get("roots") or []:
            for sub in root.get("subcategories") or []:
                if re.match(r"(?i)^v+agina$", str(sub.get("label") or "")) and sub.get("label") != "Vagina":
                    _fail("VVagina typo not repaired", f"{root.get('id')}:{sub.get('label')}")
        # Heme must always read as Hematolymphoid, never the old label.
        heme_root = next((r for r in data.get("roots") or [] if r.get("id") == "heme"), None)
        if not heme_root or heme_root.get("label") != "Hematolymphoid":
            _fail("heme root label", heme_root.get("label") if heme_root else None)
        # Cytopathology must branch by organ system first (Cyto_Heme ->
        # "Hematolymphoid Cytopathology", not the raw "Cyto Heme"/"SIL"/
        # "Adenocarcinomas" generic-header buckets from before).
        cyto_root = next((r for r in data.get("roots") or [] if r.get("id") == "cyto"), None)
        if not cyto_root:
            _fail("missing cyto root", None)
        else:
            cyto_sub_labels = {s.get("label") for s in cyto_root.get("subcategories") or []}
            for expected in ("Hematolymphoid Cytopathology", "Gynecologic Cytopathology", "Thyroid / Parathyroid Cytopathology"):
                if expected not in cyto_sub_labels:
                    _fail("cyto organ-system subcategory missing", f"{expected!r} not in {sorted(cyto_sub_labels)}")
            for bad in ("Cyto Heme", "Cyto Gyn", "SIL", "Adenocarcinomas", "Malignant Neoplasms"):
                if bad in cyto_sub_labels:
                    _fail("cyto still has a non-organ-system subcategory", bad)
            if len(cyto_sub_labels) > 25:
                _fail("cyto subcategories still fragmented (expected ~16 organ systems)", len(cyto_sub_labels))
            cyto_tags = [
                l.get("tag", "")
                for s in cyto_root.get("subcategories") or []
                for l in s.get("leaves") or []
            ]
            if any(t.startswith("ABPathSpec::cyto::") for t in cyto_tags):
                _fail("cyto still has synthetic ABPathSpec:: tags (expected native Cyto_<System>::…)", None)
            if "Cyto_Adrenal::Malignant::Adrenal_Cortical_Carcinoma" not in cyto_tags:
                _fail("expected native Cyto_Adrenal tag not found", None)
            category_tags = [t for t in cyto_tags if "::Category::" in t]
            if len(category_tags) < 5 * 10:
                _fail("expected >=5 Bethesda-tier Category leaves per cyto system", len(category_tags))
        # Cardio (2026-08-02): merged into Thorax_Mediastinum::Heart /
        # ::Blood_Vessels per WHO's own Thoracic Tumours volume — no
        # standalone "cardio" root, no synthetic ABPathSpec:: tags for it.
        if any(r.get("id") == "cardio" for r in data.get("roots") or []):
            _fail("cardio root should no longer exist (merged into thorax_mediastinum)", None)
        thorax_root = next((r for r in data.get("roots") or [] if r.get("id") == "thorax_mediastinum"), None)
        if not thorax_root:
            _fail("missing thorax_mediastinum root", None)
        else:
            thorax_subs = {s.get("id") for s in thorax_root.get("subcategories") or []}
            for expected in ("heart", "blood_vessels"):
                if expected not in thorax_subs:
                    _fail(f"thorax_mediastinum missing '{expected}' subcategory", sorted(thorax_subs))
            heart_leaves = next(
                (s.get("leaves") or [] for s in thorax_root.get("subcategories") or [] if s.get("id") == "heart"),
                [],
            )
            myxoma = next((l for l in heart_leaves if "Myxoma" in l.get("tag", "")), None)
            if not myxoma:
                _fail("Cardiac Myxoma not found under thorax_mediastinum::heart", None)
            elif myxoma.get("tag") != "Thorax_Mediastinum::Heart::Benign::Cardiac_Myxoma":
                _fail("Cardiac Myxoma has unexpected tag shape", myxoma.get("tag"))
            elif myxoma.get("provenance") != "abpath":
                _fail("Cardiac Myxoma provenance should be 'abpath', not sanitized to 'who'", myxoma.get("provenance"))
        # Roots with huge subcategory fan-out (Peds/Neuro/Skin/Heme/Forensic)
        # must actually exceed the frontend's grouping threshold — otherwise
        # a future data change could silently regress back to a flat wall.
        for rid, min_subs in (("peds", 100), ("neuro", 100), ("skin", 100), ("heme", 30), ("forensic", 30)):
            root = next((r for r in data.get("roots") or [] if r.get("id") == rid), None)
            if not root or len(root.get("subcategories") or []) < min_subs:
                _fail(
                    f"{rid} root subcategory fan-out unexpectedly small",
                    len(root.get("subcategories") or []) if root else None,
                )
        js = client.get("/static/app.js").text
        if 'data-browse-mode=' in js:
            _fail("browse mode toggle should be removed", "found data-browse-mode in app.js")
        for needle in ('"Hematolymphoid"', "browse-tile-glyph"):
            if needle not in js:
                _fail("browse UI missing", needle)
        for needle in (
            "ONCOTREE_SUBCATEGORY_GROUP_THRESHOLD",
            "subcategoryProcessCategory",
            "buildOncotreeSubcategoryGroups",
            "oncotree-supergroup",
        ):
            if needle not in js:
                _fail("subcategory disease-process grouping missing", needle)
        for needle in ("model-select", "selectedSynthesisModel"):
            if needle not in js:
                _fail("model selector UI missing", needle)
        for needle in ("SUBCATEGORY_TRUNK_MAP", "applyTrunkGrouping", "oncotree-trunk"):
            if needle not in js:
                _fail("subcategory trunk-grouping feature missing", needle)
        for needle in (
            "buildCiteHoverIndex",
            "citeHoverPayload",
            "showCiteHoverCard",
            "bindCiteHoverHandlers",
            "data-cite-hover",
            "lectureCardPresentation(card)",
        ):
            if needle not in js:
                _fail("rich citation hover-card feature missing", needle)
        for needle in ("ONCOTREE_TALL_LABEL_CHARS", "oncotree-node-wrap-tall", "isTall"):
            if needle not in js:
                _fail("tall-label tree wrap feature missing", needle)
        if "Backend unreachable" in js and "This chat app is fine" not in js:
            _fail("Backend-unreachable status missing its explanatory tooltip", None)
        for needle in ("export-info-btn", "export-info-modal"):
            if needle not in js:
                _fail("export info button wiring missing from app.js", needle)
        index_html = client.get("/").text
        for needle in ("model-select", "gpt-5.6-terra", "gpt-5.6-luna"):
            if needle not in index_html:
                _fail("model selector markup missing from index.html", needle)
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
    for needle in (".compare-tray", ".compare-column", ".vs-btn", ".topic-videos", ".cite-hover-card"):
        if needle not in css:
            _fail("style.css", f"missing {needle!r}")
    _ok("style.css compare/VS styles")

    index_html2 = client.get("/").text
    if "cite-hover-card" not in index_html2:
        _fail("cite hover card markup missing from index.html", None)
    for needle in ("export-info-btn", "export-info-modal", "What can I do with this JSON"):
        if needle not in index_html2:
            _fail("export info modal markup missing from index.html", needle)

    health = client.get("/api/health").json()
    if "topic_page_root_narrow" not in health:
        _fail("health", "missing topic_page_root_narrow")
    if "topic_page_cache_gcs_configured" not in health:
        _fail("health", "missing topic_page_cache_gcs_configured")
    _ok("health", f"root_narrow={health.get('topic_page_root_narrow')}")

    # 2026-08-02 prebuild-serving fix: a cached/prebuilt page must load
    # instantly even when the server is iterative/SSE-capable — the whole
    # point of prebuilding is defeated if the client only ever trusts the
    # cache on "older, non-iterative" servers.
    if "!healthFlags.iterative && Boolean(leafRef.tag)" in js:
        _fail("cache gating still skips prebuilt pages when iterative is on", None)
    if "const allowCache = !rebuild && Boolean(leafRef.tag);" not in js:
        _fail("expected cache-first allowCache gating not found", None)
    _ok("prebuilt-cache-first gating (structural, offline)")

    # 2026-08-03: inline citation labels must defer to the deterministic
    # source_id->book URL mapping, not the model's freeform label text — the
    # model sometimes writes a hallucinated-but-plausible book chip (e.g.
    # "Gnepp" for a Bone/Soft Tissue citation that is actually
    # softtissue_enzinger). See citeDisplayLabel in app.js.
    for needle in (
        "if (/^(Gnepp|Atlas|Cardesa|Vasef|Biopsy|FAQ|Dorfman|Horvai|Enzinger|Pattern)$/i.test(normalized)) {",
        "return textbookLabelFromUrl(url) || normalized;",
    ):
        if needle not in js:
            _fail("citeDisplayLabel book-chip URL cross-check missing", needle)
    _ok("citation label URL cross-check (structural, offline)")

    # WHO citations for entities covered by who_genetic_syndromes_links_v0_1.json
    # should link to the real tumourclassification.iarc.who.int page, not only
    # the Pathology Hub WHO_HTML mirror. See whoSyndromeUrlForEntity in app.js.
    who_links_resp = client.get("/static/who_genetic_syndromes_links_v0_1.json")
    if who_links_resp.status_code != 200:
        _fail("who_genetic_syndromes_links_v0_1.json not served", who_links_resp.status_code)
    who_links_data = who_links_resp.json()
    who_entries = who_links_data.get("entries") or {}
    if len(who_entries) < 1000:
        _fail("WHO chapter-link index looks too small", len(who_entries))
    if "neurofibromatosis type 1" not in who_entries:
        _fail("WHO chapter-link index missing expected entry", "neurofibromatosis type 1")
    for needle in (
        "whoSyndromeUrlForEntity",
        "WHO_VOLUME_BY_ROOT",
        "loadWhoSyndromeLinks",
        "function resolveWhoOverrideUrl",
        "activeWhoOverrideUrl",
    ):
        if needle not in js:
            _fail("WHO real-link wiring missing from app.js", needle)
    _ok("WHO real-link lookup + root disambiguation (structural, offline)")

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
