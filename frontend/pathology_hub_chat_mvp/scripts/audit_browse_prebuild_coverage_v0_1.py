#!/usr/bin/env python3
"""Audit Browse leaf coverage by local/GCS topic-page prebuild sidecars (v0_1).

Reads the static Browse tag index and reports, per root and overall, how many
leaf topics have local ok prebuild pages and textbook/thoracic textbook cards.
GCS reads are opt-in because a full index check performs thousands of blob
lookups.

Examples:
    python3 scripts/audit_browse_prebuild_coverage_v0_1.py
    python3 scripts/audit_browse_prebuild_coverage_v0_1.py --check-gcs
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
MVP_DIR = SCRIPT_DIR.parent
REPO_ROOT = MVP_DIR.parents[1]
STATIC_INDEX_PATH = MVP_DIR / "static/browse_tag_index_v0_1.json"
OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
PAGES_DIR = OUTPUT_DIR / "pages"
DEFAULT_AUDIT_PATH = OUTPUT_DIR / "browse_prebuild_coverage_audit_v0_1.json"

AUDIT_SCHEMA_VERSION = "browse_prebuild_coverage_audit_v0_1"
PAGE_SCHEMA_VERSION = "topic_page_prebuild_v0_1"


def _slugify_tag(tag: str) -> str:
    slug = tag.replace("::", "__")
    return re.sub(r"[^a-zA-Z0-9_]+", "_", slug)


def _repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _iter_leaves(index: dict[str, Any]) -> list[dict[str, Any]]:
    leaves: list[dict[str, Any]] = []
    for root in index.get("roots") or []:
        if not isinstance(root, dict):
            continue
        root_id = str(root.get("id") or "unknown")
        root_label = str(root.get("label") or root_id)
        for sub in root.get("subcategories") or []:
            if not isinstance(sub, dict):
                continue
            sub_id = str(sub.get("id") or "unknown")
            sub_label = str(sub.get("label") or sub_id)
            for leaf in sub.get("leaves") or []:
                if not isinstance(leaf, dict) or not leaf.get("tag"):
                    continue
                leaves.append(
                    {
                        "tag": str(leaf["tag"]),
                        "label": str(leaf.get("label") or leaf["tag"]),
                        "provenance": str(leaf.get("provenance") or "unknown"),
                        "query": str(leaf.get("query") or leaf.get("label") or leaf["tag"]),
                        "root_id": root_id,
                        "root_label": root_label,
                        "subcategory_id": sub_id,
                        "subcategory_label": sub_label,
                    }
                )
    return leaves


def _empty_counts(root_label: Optional[str] = None) -> dict[str, Any]:
    counts: dict[str, Any] = {
        "leaves_total": 0,
        "leaves_by_provenance": {},
        "local_pages_found": 0,
        "local_pages_unreadable": 0,
        "local_ok_prebuild": 0,
        "available_ok_prebuild": 0,
        "gcs_checked_missing_local": 0,
        "gcs_ok_prebuild_missing_local": 0,
        "gcs_miss_or_error_missing_local": 0,
        "pages_with_textbook_cards": 0,
        "pages_with_thoracic_textbook_cards": 0,
        "textbook_cards_total": 0,
        "thoracic_textbook_cards_total": 0,
    }
    if root_label is not None:
        counts["root_label"] = root_label
    return counts


def _is_ok_prebuild(page: Optional[dict[str, Any]]) -> bool:
    if not isinstance(page, dict):
        return False
    return bool(page.get("ok")) and bool(page.get("answer_markdown"))


def _is_textbook_card(card: dict[str, Any]) -> bool:
    source = str(card.get("source") or "").lower()
    source_type = str(card.get("source_type") or "").lower()
    result_key = str(card.get("_result_key") or "").lower()
    source_name = str(card.get("source_name") or "").lower()
    return (
        source == "textbooks"
        or "textbook" in source_type
        or result_key == "textbook_results"
        or source_name == "textbooks"
    )


def _is_thoracic_textbook_card(card: dict[str, Any]) -> bool:
    source_id = str(card.get("source_id") or "").lower()
    return _is_textbook_card(card) and source_id.startswith("thoracic_")


def _card_counts(page: Optional[dict[str, Any]]) -> tuple[int, int]:
    if not _is_ok_prebuild(page):
        return 0, 0
    textbook_cards = 0
    thoracic_textbook_cards = 0
    for card in page.get("cards") or []:
        if not isinstance(card, dict):
            continue
        if _is_textbook_card(card):
            textbook_cards += 1
        if _is_thoracic_textbook_card(card):
            thoracic_textbook_cards += 1
    return textbook_cards, thoracic_textbook_cards


def _add_leaf_counts(counts: dict[str, Any], leaf: dict[str, Any]) -> None:
    counts["leaves_total"] += 1
    prov_counter = Counter(counts["leaves_by_provenance"])
    prov_counter[leaf["provenance"]] += 1
    counts["leaves_by_provenance"] = dict(sorted(prov_counter.items()))


def _bump(counts: dict[str, Any], key: str, amount: int = 1) -> None:
    counts[key] += amount


def _import_gcs_cache():
    if str(MVP_DIR) not in sys.path:
        sys.path.insert(0, str(MVP_DIR))
    import gcs_topic_cache  # noqa: PLC0415

    return gcs_topic_cache


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    index = _load_json(args.index_path)
    if index is None:
        raise SystemExit(f"Could not read Browse tag index JSON: {args.index_path}")

    leaves = _iter_leaves(index)
    counts = {
        "overall": _empty_counts(),
        "per_root": {},
        "index_schema_version": index.get("schema_version"),
    }
    for leaf in leaves:
        root_id = leaf["root_id"]
        counts["per_root"].setdefault(root_id, _empty_counts(leaf["root_label"]))
        _add_leaf_counts(counts["overall"], leaf)
        _add_leaf_counts(counts["per_root"][root_id], leaf)

    gcs_cache = None
    gcs_configured = False
    gcs_status = "not_checked"
    if args.check_gcs:
        try:
            gcs_cache = _import_gcs_cache()
            gcs_configured = bool(gcs_cache.is_configured())
            gcs_status = "configured" if gcs_configured else "not_configured"
        except Exception as exc:  # noqa: BLE001 - audit should still report local coverage
            gcs_status = f"import_failed: {exc}"

    local_pages_dir_exists = args.pages_dir.is_dir()
    local_json_files = 0
    if local_pages_dir_exists:
        local_json_files = sum(1 for _ in args.pages_dir.glob("*.json"))

    for leaf in leaves:
        root_counts = counts["per_root"][leaf["root_id"]]
        destinations = (counts["overall"], root_counts)
        slug = _slugify_tag(leaf["tag"])
        local_path = args.pages_dir / f"{slug}.json"

        local_page = None
        if not args.no_local:
            if local_path.exists():
                for dest in destinations:
                    _bump(dest, "local_pages_found")
                local_page = _load_json(local_path)
                if local_page is None:
                    for dest in destinations:
                        _bump(dest, "local_pages_unreadable")
            elif local_pages_dir_exists:
                local_page = None

        local_ok = _is_ok_prebuild(local_page)
        if local_ok:
            for dest in destinations:
                _bump(dest, "local_ok_prebuild")

        selected_page = local_page if local_ok else None
        if not local_ok and args.check_gcs and gcs_configured and gcs_cache is not None:
            for dest in destinations:
                _bump(dest, "gcs_checked_missing_local")
            gcs_page = gcs_cache.read_page(slug)
            if _is_ok_prebuild(gcs_page):
                selected_page = gcs_page
                for dest in destinations:
                    _bump(dest, "gcs_ok_prebuild_missing_local")
            else:
                for dest in destinations:
                    _bump(dest, "gcs_miss_or_error_missing_local")

        if _is_ok_prebuild(selected_page):
            for dest in destinations:
                _bump(dest, "available_ok_prebuild")

        textbook_cards, thoracic_textbook_cards = _card_counts(selected_page)
        if textbook_cards:
            for dest in destinations:
                _bump(dest, "pages_with_textbook_cards")
                _bump(dest, "textbook_cards_total", textbook_cards)
        if thoracic_textbook_cards:
            for dest in destinations:
                _bump(dest, "pages_with_thoracic_textbook_cards")
                _bump(dest, "thoracic_textbook_cards_total", thoracic_textbook_cards)

    audit = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input_paths": {
            "browse_tag_index": _repo_rel(args.index_path),
            "local_pages_glob": _repo_rel(args.pages_dir / "*.json"),
            "gcs_topic_cache": "frontend/pathology_hub_chat_mvp/gcs_topic_cache.py",
        },
        "output_paths": {
            "audit_json": _repo_rel(args.audit_out),
        },
        "options": {
            "scan_local": not args.no_local,
            "check_gcs": bool(args.check_gcs),
            "gcs_status": gcs_status,
            "gcs_checked_only_for_missing_local_ok_pages": True,
        },
        "counts": counts,
        "diagnostics": {
            "browse_leaf_records": len(leaves),
            "local_pages_dir_exists": local_pages_dir_exists,
            "local_json_files_scanned_by_name": local_json_files,
            "expected_page_schema_version": PAGE_SCHEMA_VERSION,
        },
        "known_limitations": [
            "Local prebuild coverage is based on slug-matched JSON sidecars only; gitignored outputs may differ by machine.",
            "Textbook-card coverage counts cards embedded in ok prebuild pages and does not independently query the backend.",
            "GCS coverage is checked only when --check-gcs is passed and gcs_topic_cache is configured.",
            "When --check-gcs is used, GCS is read only for leaves without a local ok prebuild to keep the audit bounded.",
        ],
    }
    return audit


def _format_root_summary(root_id: str, counts: dict[str, Any]) -> str:
    return (
        f"{root_id}: leaves={counts['leaves_total']} "
        f"provenance={counts['leaves_by_provenance']} "
        f"local_ok={counts['local_ok_prebuild']} "
        f"textbook_pages={counts['pages_with_textbook_cards']} "
        f"thoracic_textbook_pages={counts['pages_with_thoracic_textbook_cards']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--index-path", type=Path, default=STATIC_INDEX_PATH)
    parser.add_argument("--pages-dir", type=Path, default=PAGES_DIR)
    parser.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--no-local", action="store_true", help="Skip local outputs/.../pages JSON scan.")
    parser.add_argument("--check-gcs", action="store_true", help="Use gcs_topic_cache.read_page for missing local ok pages.")
    args = parser.parse_args()

    audit = build_audit(args)
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)
    args.audit_out.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    overall = audit["counts"]["overall"]
    thorax = audit["counts"]["per_root"].get("thorax_mediastinum")
    print(f"wrote {_repo_rel(args.audit_out)}")
    print(_format_root_summary("overall", overall))
    if thorax:
        print(_format_root_summary("thorax_mediastinum", thorax))
    else:
        print("thorax_mediastinum: not found in Browse index")


if __name__ == "__main__":
    main()
