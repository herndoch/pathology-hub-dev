#!/usr/bin/env python3
"""Advisory 'fake pathologist' review of prebuilt topic pages (v0_1).

Reads existing prebuild page JSON sidecars (does NOT rewrite them) and writes
a sibling critique:

    outputs/chat_mvp_topic_prepop_v0_1/pages/<tag_slug>.review.json

Plus a batch audit JSON. Intended to run AFTER
`prebuild_topic_pages_pilot_v0_1.py` once the retrieval/synthesis workflow is
stable — human reviewers still own publish decisions.

Requires OPENAI_API_KEY (env or Secret Manager) via secrets_helper.

Examples:
    # Review every *.json page that has answer_markdown (skip *.review.json)
    python3 scripts/pathologist_review_topic_pages_v0_1.py

    # One tag
    python3 scripts/pathologist_review_topic_pages_v0_1.py \\
        --tags "Heme::Mature_B_Cell::Large_B_Cell::Diffuse_Large_B_Cell_Lymphoma_NOS"

    # Limit for smoke
    python3 scripts/pathologist_review_topic_pages_v0_1.py --limit 3
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
MVP_DIR = SCRIPT_DIR.parent
REPO_ROOT = MVP_DIR.parents[1]
if str(MVP_DIR) not in sys.path:
    sys.path.insert(0, str(MVP_DIR))

import prompts  # noqa: E402
from openai_synthesizer import get_topic_page_model, synthesize  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
PAGES_DIR = OUTPUT_DIR / "pages"
DEFAULT_AUDIT_PATH = OUTPUT_DIR / "pathologist_review_audit_v0_1.json"
REVIEW_SCHEMA_VERSION = "topic_page_pathologist_review_v0_1"
AUDIT_SCHEMA_VERSION = "topic_page_pathologist_review_batch_audit_v0_1"


def _slugify_tag(tag: str) -> str:
    slug = tag.replace("::", "__")
    return re.sub(r"[^a-zA-Z0-9_]+", "_", slug)


def _slim_evidence_for_review(page: dict) -> dict[str, Any]:
    """Compact evidence so the critique call fits context without inventing."""
    cards = []
    for card in (page.get("cards") or [])[:40]:
        if not isinstance(card, dict):
            continue
        cards.append(
            {
                "source": card.get("source"),
                "source_id": card.get("source_id"),
                "title": card.get("title") or card.get("name") or card.get("heading"),
                "section": card.get("section"),
                "source_url": card.get("source_url") or card.get("source_page_url"),
                "doi": card.get("doi"),
                "excerpt": (card.get("excerpt") or card.get("text") or "")[:400],
            }
        )
    figures = []
    for fig in (page.get("figures") or [])[:24]:
        if not isinstance(fig, dict):
            continue
        figures.append(
            {
                "caption": fig.get("caption") or fig.get("title") or fig.get("alt"),
                "source": fig.get("source"),
                "source_id": fig.get("source_id"),
                "figure_url": fig.get("figure_url") or fig.get("image_url") or fig.get("url"),
            }
        )
    return {
        "tag": page.get("tag"),
        "label": page.get("label"),
        "provenance": page.get("provenance"),
        "draft_answer_markdown": page.get("answer_markdown") or "",
        "cards": cards,
        "figures": figures,
        "card_count": len(page.get("cards") or []),
        "figure_count": len(page.get("figures") or []),
        "known_limitations": page.get("known_limitations") or [],
    }


def _parse_score(text: str) -> int | None:
    m = re.search(r"##\s*Score\b(.*?)(?:\n##\s|\Z)", text or "", flags=re.I | re.S)
    scope = m.group(1) if m else (text or "")
    m2 = re.search(r"\b(\d{1,3})\b", scope)
    if not m2:
        return None
    n = int(m2.group(1))
    return n if 0 <= n <= 100 else None


def _parse_verdict(text: str) -> str:
    """Prefer the ## Verdict section; calibrate with ## Score when present.

    Models often emit needs_fixes even at score 80+. When a numeric Score is
    present, enforce the rubric: >=75 → ready, <=35 → blocked (unless already
    blocked), else keep the model label.
    """
    text = text or ""
    section = re.search(
        r"##\s*Verdict\b(.*?)(?:\n##\s|\Z)",
        text,
        flags=re.I | re.S,
    )
    scope = section.group(1) if section else text
    low = scope.lower()
    raw = None
    for key in ("ready_for_human_review", "blocked_thin_evidence", "needs_fixes"):
        if key in low:
            raw = key
            break
    if raw is None:
        low_all = text.lower()
        for key in ("ready_for_human_review", "blocked_thin_evidence", "needs_fixes"):
            if key in low_all:
                raw = key
                break
    if raw is None:
        raw = "needs_fixes"

    score = _parse_score(text)
    if score is None:
        return raw
    if raw == "blocked_thin_evidence" and score <= 45:
        return "blocked_thin_evidence"
    if score <= 35:
        return "blocked_thin_evidence"
    if score >= 75:
        return "ready_for_human_review"
    return raw if raw != "ready_for_human_review" or score >= 75 else "needs_fixes"


def _review_one(page_path: Path, model: Optional[str]) -> dict[str, Any]:
    page = json.loads(page_path.read_text(encoding="utf-8"))
    tag = page.get("tag") or page_path.stem
    label = page.get("label") or tag
    if not page.get("answer_markdown"):
        return {
            "ok": False,
            "tag": tag,
            "label": label,
            "page_path": str(page_path.relative_to(REPO_ROOT)),
            "error": "no_answer_markdown",
        }

    bundle = _slim_evidence_for_review(page)
    result = synthesize(
        prompts.pathologist_page_review_system_prompt(),
        f"Review the draft topic page for: {label}",
        bundle,
        model=model or get_topic_page_model(),
    )
    score = _parse_score(result.text) if result.ok else None
    review = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "tag": tag,
        "label": label,
        "page_json": str(page_path.relative_to(REPO_ROOT)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": bool(result.ok),
        "model": result.model,
        "score": score,
        "verdict": _parse_verdict(result.text) if result.ok else None,
        "review_markdown": result.text if result.ok else "",
        "error": result.error,
        "known_limitations": [
            "Advisory LLM critique only — not a human pathologist sign-off.",
            "Does not mutate the prebuild page JSON/markdown.",
            "Publish decisions remain with a human reviewer.",
            "Verdict is score-calibrated when ## Score is present (>=75 ready, <=35 blocked).",
        ],
    }
    out_path = page_path.parent / f"{page_path.stem}.review.json"
    out_path.write_text(json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "ok": review["ok"],
        "tag": tag,
        "label": label,
        "verdict": review.get("verdict"),
        "page_path": str(page_path.relative_to(REPO_ROOT)),
        "review_path": str(out_path.relative_to(REPO_ROOT)),
        "model": review.get("model"),
        "error": review.get("error"),
    }


def _iter_page_jsons(pages_dir: Path, tags: Optional[list[str]], limit: Optional[int]) -> list[Path]:
    if tags:
        paths = []
        for tag in tags:
            p = pages_dir / f"{_slugify_tag(tag)}.json"
            if not p.exists():
                raise SystemExit(f"Missing prebuild page for tag: {tag} ({p})")
            paths.append(p)
        return paths[: limit or None]

    paths = sorted(
        p
        for p in pages_dir.glob("*.json")
        if not p.name.endswith(".review.json") and p.name != "index.json"
    )
    if limit is not None:
        paths = paths[:limit]
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages-dir", type=Path, default=PAGES_DIR)
    parser.add_argument("--tags", nargs="+", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--model", default=None, help="Override OPENAI_TOPIC_PAGE_MODEL")
    parser.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT_PATH)
    args = parser.parse_args()

    pages_dir = args.pages_dir
    if not pages_dir.is_dir():
        raise SystemExit(f"Pages directory not found: {pages_dir}")

    paths = _iter_page_jsons(pages_dir, args.tags, args.limit)
    if not paths:
        raise SystemExit(f"No page JSON files found under {pages_dir}")

    results: list[dict] = []
    # Cap raised for quality-burn throughput (OpenAI can absorb more than 4;
    # still bounded so a runaway CLI flag cannot open hundreds of sockets).
    workers = max(1, min(args.parallel, 24))
    if workers == 1:
        for path in paths:
            results.append(_review_one(path, args.model))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_review_one, path, args.model): path for path in paths}
            for fut in as_completed(futs):
                results.append(fut.result())

    results.sort(key=lambda r: str(r.get("tag") or ""))
    ok_n = sum(1 for r in results if r.get("ok"))
    verdicts: dict[str, int] = {}
    for r in results:
        v = r.get("verdict") or ("error" if not r.get("ok") else "unknown")
        verdicts[v] = verdicts.get(v, 0) + 1

    audit = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_paths": [str(pages_dir.relative_to(REPO_ROOT))],
        "output_paths": [str(args.audit_out.relative_to(REPO_ROOT))],
        "counts": {
            "pages_reviewed": len(results),
            "ok": ok_n,
            "failed": len(results) - ok_n,
            "verdicts": verdicts,
        },
        "results": results,
        "known_limitations": [
            "LLM advisory only — not human pathologist sign-off.",
            "Requires prebuilt page JSON with answer_markdown.",
            "Does not overwrite page content; writes *.review.json sidecars only.",
        ],
    }
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)
    args.audit_out.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(audit["counts"], indent=2))
    print(f"Audit: {args.audit_out}")


if __name__ == "__main__":
    main()
