#!/usr/bin/env python3
"""Free (no-LLM) structural quality score for topic-page prebuild JSON (v0_1).

Reads page sidecars under outputs/chat_mvp_topic_prepop_v0_1/pages/ and writes:
  - per-page *.quality.json sidecars (same dir)
  - batch audit JSON (default under outputs/... and optional audits/ copy)

Signals (creative but deterministic):
  - synthesis ok + answer length
  - required-section compliance vs evidence cards (lit → Key Literature, etc.)
  - hub citation presence when textbook/WHO/PathOut cards exist
  - hallucinated URL smell (markdown URLs absent from card URLs)
  - figure modality placement heuristics
  - banned filler / double-paren book chips
  - section-order drift vs TOPIC_PAGE_SECTIONS

Does NOT call OpenAI. Pair with pathologist_review / quality burn for LLM critique.
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
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
MVP_DIR = SCRIPT_DIR.parent
REPO_ROOT = MVP_DIR.parents[1]
if str(MVP_DIR) not in sys.path:
    sys.path.insert(0, str(MVP_DIR))

from prompts import TOPIC_PAGE_SECTIONS  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "outputs/chat_mvp_topic_prepop_v0_1"
PAGES_DIR = OUTPUT_DIR / "pages"
DEFAULT_AUDIT = OUTPUT_DIR / "topic_page_structural_quality_audit_v0_1.json"
AUDITS_COPY = REPO_ROOT / "audits/topic_page_quality_burn_v0_1/structural_quality_audit_v0_1.json"

PAGE_SCHEMA = "topic_page_prebuild_v0_1"
QUALITY_SCHEMA = "topic_page_structural_quality_v0_1"
AUDIT_SCHEMA = "topic_page_structural_quality_batch_audit_v0_1"

_MD_URL_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
_IMG_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
_FILLER_RE = re.compile(r"Abstract not provided in the retrieved record", re.I)
_DOUBLE_PAREN_RE = re.compile(r"\(\([A-Za-z][^)]{0,40}\)\)")

_IMAGING_HINT = re.compile(
    r"\b(mammogram|mammograph|ultrasound|sonograph|\bmri\b|\bct\b|radiograph|pet[- ]?ct|"
    r"imaging|radiolog)",
    re.I,
)
_GROSS_HINT = re.compile(r"\b(gross|cut surface|specimen|macroscopic|ex vivo)\b", re.I)
_CYTO_HINT = re.compile(r"\b(cytolog|fna|smear|pap smear|liquid[- ]based)\b", re.I)
_IHC_HINT = re.compile(r"\b(ihc|immunohistochem|special stain|cd\d{1,3}|ki[- ]?67)\b", re.I)


def _load(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _card_urls(cards: list[dict]) -> set[str]:
    urls: set[str] = set()
    for c in cards:
        for k in ("source_url", "source_page_url", "doi", "open_access_url", "url", "figure_url", "image_url"):
            v = c.get(k)
            if isinstance(v, str) and v.startswith("http"):
                urls.add(v.rstrip("/"))
            if isinstance(v, str) and v.startswith("10.") and "doi.org" not in v:
                urls.add(f"https://doi.org/{v}".rstrip("/"))
    return urls


def _figure_urls(figures: list[dict]) -> set[str]:
    urls: set[str] = set()
    for f in figures:
        for k in ("figure_url", "image_url", "url"):
            v = f.get(k)
            if isinstance(v, str) and v.startswith("http"):
                urls.add(v.rstrip("/"))
    return urls


def _source_buckets(cards: list[dict]) -> dict[str, int]:
    buckets: Counter[str] = Counter()
    for c in cards:
        src = str(c.get("source") or c.get("source_name") or c.get("_result_key") or "").lower()
        sid = str(c.get("source_id") or "").lower()
        if "who" in src or sid.startswith("who"):
            buckets["who"] += 1
        elif "pathout" in src or "pathologyoutlines" in src:
            buckets["pathout"] += 1
        elif "textbook" in src or "textbook" in str(c.get("source_type") or "").lower():
            buckets["textbook"] += 1
        elif "literature" in src or src in {"pubmed", "scopus", "oncokb"}:
            buckets["literature"] += 1
        elif "lecture" in src or "video" in src:
            buckets["lecture"] += 1
        else:
            buckets["other"] += 1
    return dict(buckets)


def _present_sections(md: str) -> list[str]:
    found = []
    for m in _HEADING_RE.finditer(md or ""):
        title = m.group(1).strip()
        # normalize slight variants
        for canon in TOPIC_PAGE_SECTIONS:
            if title.lower() == canon.lower():
                found.append(canon)
                break
        else:
            found.append(title)
    return found


def _section_order_ok(sections: list[str]) -> bool:
    order = {s: i for i, s in enumerate(TOPIC_PAGE_SECTIONS)}
    idxs = [order[s] for s in sections if s in order]
    return idxs == sorted(idxs)


def _url_host(u: str) -> str:
    try:
        return urlparse(u).netloc.lower()
    except Exception:
        return ""


def score_page(page: dict[str, Any]) -> dict[str, Any]:
    md = page.get("answer_markdown") or ""
    cards = [c for c in (page.get("cards") or []) if isinstance(c, dict)]
    figures = [f for f in (page.get("figures") or []) if isinstance(f, dict)]
    buckets = _source_buckets(cards)
    sections = _present_sections(md)
    section_set = set(sections)

    known_urls = _card_urls(cards) | _figure_urls(figures)
    md_urls = [u.rstrip("/") for u in _MD_URL_RE.findall(md)]
    img_urls = [u.rstrip("/") for u in _IMG_RE.findall(md)]
    # allow common DOI host variants + figure proxy hosts already on cards
    hallucinated = []
    for u in md_urls + img_urls:
        if u in known_urls:
            continue
        # soften: same path under doi.org vs dx.doi.org
        if any(u.replace("dx.doi.org", "doi.org") == k.replace("dx.doi.org", "doi.org") for k in known_urls):
            continue
        # soften: figure proxy signed URLs often rewrite query — compare host+path prefix
        host = _url_host(u)
        if host and any(_url_host(k) == host and u.split("?")[0][:80] in k for k in known_urls):
            continue
        hallucinated.append(u)

    flags: list[str] = []
    deductions = 0

    ok = bool(page.get("ok")) and bool(md.strip())
    if not ok:
        flags.append("not_ok_or_empty_answer")
        deductions += 40

    ans_len = len(md)
    if ans_len < 600:
        flags.append("very_short_answer")
        deductions += 20
    elif ans_len < 1200:
        flags.append("short_answer")
        deductions += 8

    if len(cards) < 5:
        flags.append("few_cards")
        deductions += 15
    elif len(cards) < 10:
        flags.append("modest_cards")
        deductions += 5

    if buckets.get("literature", 0) > 0 and "Key Literature" not in section_set:
        flags.append("missing_key_literature_despite_lit_cards")
        deductions += 18

    if buckets.get("textbook", 0) > 0:
        # hub book cites should appear as markdown links somewhere
        if not re.search(r"\[[^\]]+\]\(https?://", md):
            flags.append("textbook_cards_but_no_markdown_cites")
            deductions += 12
        if "Textbooks" in md and not re.search(r"\[[A-Za-z][^\]]{0,40}\]\(https?://", md):
            flags.append("generic_textbooks_label_smell")
            deductions += 4

    if buckets.get("who", 0) > 0 and "[WHO]" not in md and "WHO" not in md:
        flags.append("who_cards_but_no_who_mention")
        deductions += 8

    if _FILLER_RE.search(md):
        flags.append("abstract_filler_phrase")
        deductions += 10

    if _DOUBLE_PAREN_RE.search(md):
        flags.append("double_paren_book_chip")
        deductions += 8

    if not _section_order_ok(sections):
        flags.append("section_order_drift")
        deductions += 6

    if len(sections) < 3 and ok:
        flags.append("few_sections")
        deductions += 10

    # figure modality placement: if captions scream imaging/gross/cyto but section missing
    fig_blob = " ".join(
        str(f.get("caption") or f.get("title") or f.get("alt") or "") for f in figures
    )
    if _IMAGING_HINT.search(fig_blob) and "Imaging Features" not in section_set:
        flags.append("imaging_figures_without_imaging_section")
        deductions += 10
    if _GROSS_HINT.search(fig_blob) and "Gross Features" not in section_set:
        flags.append("gross_figures_without_gross_section")
        deductions += 8
    if _CYTO_HINT.search(fig_blob) and "Cytology" not in section_set:
        flags.append("cyto_figures_without_cytology_section")
        deductions += 8
    if _IHC_HINT.search(fig_blob) and "Ancillary Tests" not in section_set:
        flags.append("ihc_figures_without_ancillary_section")
        deductions += 6

    # embedded images should mostly come from known figure urls
    orphan_imgs = [u for u in img_urls if u not in known_urls]
    if len(orphan_imgs) >= 2:
        flags.append("orphan_embedded_images")
        deductions += 8

    if len(hallucinated) >= 3:
        flags.append("many_unmatched_urls")
        deductions += 12
    elif hallucinated:
        flags.append("some_unmatched_urls")
        deductions += 4

    if "Differential Diagnosis" not in section_set and len(cards) >= 12:
        flags.append("no_ddx_despite_rich_evidence")
        deductions += 6

    score = max(0, min(100, 100 - deductions))
    if score >= 85 and not flags:
        band = "excellent"
    elif score >= 75:
        band = "good"
    elif score >= 55:
        band = "fair"
    else:
        band = "poor"

    return {
        "schema_version": QUALITY_SCHEMA,
        "tag": page.get("tag"),
        "label": page.get("label"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok_prebuild": ok,
        "score": score,
        "band": band,
        "answer_chars": ans_len,
        "card_count": len(cards),
        "figure_count": len(figures),
        "source_buckets": buckets,
        "sections_present": sections,
        "flags": flags,
        "hallucinated_url_sample": hallucinated[:8],
        "priority_for_llm_review": (
            "high"
            if band in {"poor", "fair"} or any(
                f.startswith("missing_") or f.startswith("not_ok") for f in flags
            )
            else "normal"
        ),
        "known_limitations": [
            "Deterministic structural heuristics only — not medical correctness.",
            "URL matching is best-effort; signed figure proxies may false-positive.",
        ],
    }


def _iter_pages(pages_dir: Path, limit: Optional[int], only_missing: bool) -> list[Path]:
    paths = sorted(
        p
        for p in pages_dir.glob("*.json")
        if not p.name.endswith(".review.json")
        and not p.name.endswith(".quality.json")
        and p.name != "index.json"
    )
    if only_missing:
        paths = [p for p in paths if not (p.parent / f"{p.stem}.quality.json").exists()]
    if limit is not None:
        paths = paths[:limit]
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages-dir", type=Path, default=PAGES_DIR)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--also-copy-audit", type=Path, default=AUDITS_COPY)
    ap.add_argument("--write-sidecars", action="store_true", default=True)
    ap.add_argument("--no-sidecars", action="store_true")
    args = ap.parse_args()

    paths = _iter_pages(args.pages_dir, args.limit, args.only_missing)
    if not paths:
        raise SystemExit(f"No pages under {args.pages_dir}")

    results: list[dict[str, Any]] = []
    bands: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    write_sidecars = args.write_sidecars and not args.no_sidecars

    for path in paths:
        page = _load(path)
        if page is None:
            results.append({"ok": False, "path": str(path), "error": "unreadable"})
            continue
        q = score_page(page)
        q["page_json"] = str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)
        if write_sidecars:
            side = path.parent / f"{path.stem}.quality.json"
            side.write_text(json.dumps(q, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            q["quality_path"] = str(side.relative_to(REPO_ROOT)) if side.is_relative_to(REPO_ROOT) else str(side)
        bands[q["band"]] += 1
        for f in q["flags"]:
            flag_counts[f] += 1
        results.append(
            {
                "tag": q.get("tag"),
                "label": q.get("label"),
                "score": q["score"],
                "band": q["band"],
                "flags": q["flags"],
                "priority_for_llm_review": q["priority_for_llm_review"],
                "card_count": q["card_count"],
                "answer_chars": q["answer_chars"],
            }
        )

    # worst first for human triage
    scored = [r for r in results if "score" in r]
    scored.sort(key=lambda r: (r["score"], -(r.get("card_count") or 0)))

    audit = {
        "schema_version": AUDIT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_paths": [str(args.pages_dir)],
        "output_paths": [str(args.audit_out)],
        "counts": {
            "pages_scored": len(scored),
            "unreadable": sum(1 for r in results if r.get("error")),
            "bands": dict(bands),
            "mean_score": round(sum(r["score"] for r in scored) / max(1, len(scored)), 2),
            "flag_counts": dict(flag_counts.most_common()),
            "high_priority_for_llm": sum(1 for r in scored if r.get("priority_for_llm_review") == "high"),
        },
        "worst_50": scored[:50],
        "known_limitations": [
            "Structural heuristics only.",
            "Does not prove medical correctness or citation faithfulness beyond URL presence.",
        ],
    }
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)
    args.audit_out.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.also_copy_audit:
        args.also_copy_audit.parent.mkdir(parents=True, exist_ok=True)
        args.also_copy_audit.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(audit["counts"], indent=2))
    print(f"Audit: {args.audit_out}")


if __name__ == "__main__":
    main()
