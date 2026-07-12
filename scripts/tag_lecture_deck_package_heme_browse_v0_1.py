#!/usr/bin/env python3
"""Tag lecture deck segments with best-matching canonical Heme::* browse leaves.

Uses the Chat MVP browse_tag_index Heme root (354 leaves). Does not invent tags
outside that set. Heuristic keyword + sticky context — not discourse parsing.

Policy:
- primary_tag must start with Heme:: and exist in the browse leaf set
- intro/agenda/thanks/filler → indexable=False
- Prefer more specific (deeper / longer label) matches; lecture-stem priors break ties
- ASR crumbs stay in segments*.jsonl; consolidation is a separate step
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote


STOPWORDS = {
    "with",
    "and",
    "the",
    "of",
    "or",
    "in",
    "to",
    "a",
    "an",
    "for",
    "from",
    "by",
    "on",
    "nos",
    "type",
    "cell",
    "cells",
    "positive",
    "negative",
    "associated",
    "related",
    "defined",
    "other",
    "rare",
    "general",
    "tumor",
    "tumors",
    "neoplasm",
    "neoplasms",
    "disorder",
    "disorders",
    "disease",
    "syndrome",
    "syndromes",
    "lesion",
    "lesions",
    "primary",
    "secondary",
}

DO_NOT_INDEX_PATTERNS = [
    r"^\s*thank you",
    r"\bi thank you\b",
    r"\bthanks?\b.{0,40}(attention|listening|time)\b",
    r"\backnowledg",
    r"\bdisclosures?\b",
    r"\bconflict of interest\b",
    r"\bno disclosures\b",
    r"hello,?\s+my name is",
    r"delighted to participate",
    r"society for hematopathology",
    r"virtual curriculum",
    r"listed on this slide are the entities",
    r"we will be discussing during this lecture",
    r"we'll be discussing in this lecture",
    r"any questions",
    r"questions\??\s*$",
]

# Extra aliases that ASR / clinicians use → browse leaf tokens
ALIAS_TO_TOKEN = [
    (r"\bdlbcl\b", "diffuse large b cell lymphoma"),
    (r"\bpmbl\b", "primary mediastinal large b cell lymphoma"),
    (r"\bthrlbcl\b", "t cell histiocyte rich large b cell lymphoma"),
    (r"\bcll\b", "chronic lymphocytic leukemia"),
    (r"\bsll\b", "small lymphocytic lymphoma"),
    (r"\bmcl\b", "mantle cell lymphoma"),
    (r"\bfl\b", "follicular lymphoma"),
    (r"\bmzl\b", "marginal zone lymphoma"),
    (r"\bmalt\b", "extranodal marginal zone lymphoma of malt"),
    (r"\bhcl\b", "hairy cell leukemia"),
    (r"\blpl\b", "lymphoplasmacytic lymphoma"),
    (r"\bwm\b", "waldenstrom"),
    (r"\baml\b", "acute myeloid leukemia"),
    (r"\bmds\b", "myelodysplastic"),
    (r"\bmpn\b", "myeloproliferative"),
    (r"\bcmml\b", "chronic myelomonocytic leukemia"),
    (r"\bcml\b", "chronic myeloid leukemia"),
    (r"\bpmf\b", "primary myelofibrosis"),
    (r"\bapl\b", "acute promyelocytic leukemia"),
    (r"\bnlphl\b", "nodular lymphocyte predominant hodgkin lymphoma"),
    (r"\bchl\b", "classic hodgkin lymphoma"),
    (r"\balcl\b", "anaplastic large cell lymphoma"),
    (r"\bptcl\b", "peripheral t cell lymphoma"),
    (r"\baetl\b", "enteropathy associated t cell lymphoma"),
    (r"\bhstl\b", "hepatosplenic t cell lymphoma"),
    (r"\benktl\b", "extranodal nk t cell lymphoma"),
    (r"\bmgus\b", "monoclonal gammopathy"),
    (r"\bpel\b", "primary effusion lymphoma"),
    (r"\bhgbl\b", "high grade b cell lymphoma"),
    (r"double[\s-]?hit", "dlbcl high grade with myc and bcl2 rearrangements"),
    (r"triple[\s-]?hit", "dlbcl high grade with myc and bcl2 rearrangements"),
    (r"\b11q\b", "high grade b cell lymphoma with 11q aberration"),
    (r"burkett", "burkitt"),
    (r"\bmyc\b", "myc"),
]

# Lecture package stem → preferred Heme:: branch prefixes (soft prior)
LECTURE_PRIORS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"aggressive_b", re.I), ["Heme::Mature_B_Cell::Large_B_Cell", "Heme::Mature_B_Cell::Burkitt"]),
    (re.compile(r"small_b_cell", re.I), ["Heme::Mature_B_Cell"]),
    (re.compile(r"hodgkin", re.I), ["Heme::Hodgkin_Lymphoma", "Heme::Mature_B_Cell"]),
    (re.compile(r"t_nk", re.I), ["Heme::Mature_T_NK_Cell", "Heme::T_NK_Cell"]),
    (re.compile(r"^heme_sh_aml", re.I), ["Heme::Acute_Myeloid_Leukemia", "Heme::Acute_Leukemia"]),
    (re.compile(r"mds_mpn", re.I), ["Heme::Myelodysplastic", "Heme::Myeloproliferative", "Heme::Myelodysplastic_Myeloproliferative", "Heme::Myeloid_Neoplasms"]),
    (re.compile(r"plasma_cell", re.I), ["Heme::Plasma_Cell_Neoplasm"]),
    (re.compile(r"histiocytic", re.I), ["Heme::Histiocytic_Dendritic_Cell", "Heme::Histiocytic_Dendritic"]),
    (re.compile(r"spleen", re.I), ["Heme::Mature_B_Cell::Splenic", "Heme::Non_Neoplastic", "Heme::Mature_T_NK_Cell"]),
    (re.compile(r"reactive", re.I), ["Heme::Non_Neoplastic", "Heme::Tumor_Like", "Heme::Infection"]),
    (re.compile(r"bm_failure|bm_intro|bm_systemic", re.I), ["Heme::Non_Neoplastic", "Heme::Myelodysplastic", "Heme::Stroma_Derived"]),
    (re.compile(r"ia_lpd|immune", re.I), ["Heme::Immune_Deficiency_Associated"]),
    (re.compile(r"pt_lpd|post.?transplant", re.I), ["Heme::Immune_Deficiency_Associated"]),
    (re.compile(r"ihc", re.I), ["Heme::Mature_B_Cell", "Heme::Mature_T_NK_Cell", "Heme::Hodgkin"]),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gcs_to_https(gcs_uri: str) -> str:
    without = gcs_uri[len("gs://") :]
    bucket, _, key = without.partition("/")
    return f"https://storage.googleapis.com/{bucket}/{quote(key, safe='/')}"


def make_video_time_url(video_url: Optional[str], start: Any, end: Any) -> Optional[str]:
    if not video_url:
        return None
    try:
        s = float(start)
    except (TypeError, ValueError):
        return None
    try:
        e = float(end) if end is not None else None
    except (TypeError, ValueError):
        e = None
    if e is not None:
        return f"{video_url}#t={s:g},{e:g}"
    return f"{video_url}#t={s:g}"


def tokenize_label(text: str) -> list[str]:
    parts = re.split(r"[^a-z0-9]+", text.lower())
    return [p for p in parts if p and p not in STOPWORDS and len(p) > 1]


def load_heme_leaves(path: Path) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    leaves = doc.get("leaves") or []
    out = []
    for leaf in leaves:
        tag = leaf.get("tag") or ""
        if not tag.startswith("Heme::"):
            continue
        label = leaf.get("label") or tag.split("::")[-1]
        query = leaf.get("query") or label.replace("_", " ")
        # IMPORTANT: use leaf label/query tokens only — parent path tokens like
        # Non_Neoplastic → "neoplastic" cause catastrophic false positives.
        label_tokens = set(tokenize_label(label))
        query_tokens = set(tokenize_label(query))
        tokens = label_tokens | query_tokens
        phrases = {
            re.sub(r"\s+", " ", query.lower()).strip(),
            re.sub(r"_+", " ", label.lower()).strip(),
            re.sub(r"_+", " ", tag.split("::")[-1].lower()).strip(),
        }
        phrases = {p for p in phrases if len(p) >= 5}
        out.append(
            {
                "tag": tag,
                "label": label,
                "query": query,
                "tokens": tokens,
                "label_tokens": label_tokens,
                "phrases": phrases,
                "depth": tag.count("::"),
                "leaf_token_count": len(label_tokens),
            }
        )
    return out


def normalize_asr(text: str) -> str:
    t = text.lower()
    for pat, rep in ALIAS_TO_TOKEN:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\s+", " ", t)
    return t


def lecture_priors(package_id: str) -> list[str]:
    priors: list[str] = []
    for pat, prefs in LECTURE_PRIORS:
        if pat.search(package_id):
            priors.extend(prefs)
    return priors


def score_leaf(norm_text: str, text_tokens: set[str], leaf: dict[str, Any], priors: list[str]) -> float:
    score = 0.0
    phrase_hit = False
    for ph in leaf["phrases"]:
        if len(ph) >= 10 and ph in norm_text:
            score += 10.0 + min(len(ph) / 8.0, 5.0)
            phrase_hit = True
        elif len(ph) >= 6 and ph in norm_text:
            score += 4.5
            phrase_hit = True
    label_overlap = leaf.get("label_tokens", leaf["tokens"]) & text_tokens
    token_overlap = leaf["tokens"] & text_tokens
    if not phrase_hit and not label_overlap:
        return 0.0
    for tok in label_overlap:
        score += 1.6 + min(len(tok) / 5.0, 2.5)
    # light credit for query-only tokens if we already have a label/phrase anchor
    extra = token_overlap - label_overlap
    if phrase_hit or label_overlap:
        for tok in extra:
            if len(tok) >= 5:
                score += 0.6
    if score <= 0:
        return 0.0
    # Guardrails for generic leaf labels that otherwise fire on common speech
    leaf_l = leaf["label"].lower()
    if "metastatic" in leaf_l and "metasta" not in norm_text:
        return 0.0
    if "lymphoblastic" in leaf_l and not re.search(r"lymphoblastic|\ball\b|bcr.?abl|etv6|kmt2a", norm_text):
        return 0.0
    if leaf_l.endswith("_features") and "features" in label_overlap and len(label_overlap) <= 2 and not phrase_hit:
        return 0.0
    # Require either a phrase hit or >=2 distinctive label tokens
    if not phrase_hit and len(label_overlap) < 2 and max((len(t) for t in label_overlap), default=0) < 8:
        return 0.0
    score += 0.12 * leaf["depth"]
    score += 0.08 * leaf["leaf_token_count"]
    for i, pref in enumerate(priors):
        if leaf["tag"].startswith(pref):
            score += 2.0 - 0.15 * i
            break
    return score


def is_do_not_index(text: str, start_sec: float, duration: Optional[float]) -> tuple[bool, str]:
    t = normalize_asr(text)
    open_cut = 120.0
    if duration and duration > 0:
        open_cut = min(180.0, max(90.0, duration * 0.03))
    if start_sec < open_cut and re.search(
        r"hello|my name is|delighted|society for hematopathology|virtual curriculum|"
        r"listed on this slide|entities that we will|overview|agenda|outline|"
        r"disclosures|conflict of interest",
        t,
    ):
        return True, "agenda_or_overview"
    if start_sec < open_cut * 0.75:
        if len(re.findall(r"[a-z0-9]+", t)) < 12 and not re.search(
            r"lymphoma|leukemia|myeloma|mds|hodgkin|aml", t
        ):
            return True, "agenda_or_overview"
    close_cut = None
    if duration and duration > 0:
        close_cut = duration - 90.0
    if close_cut is not None and start_sec > close_cut and re.search(
        r"thank|attention|questions|wrap|summary|in this talk", t
    ):
        return True, "closing_summary"
    for pat in DO_NOT_INDEX_PATTERNS:
        if re.search(pat, t):
            return True, "thanks_or_housekeeping"
    words = re.findall(r"[a-z0-9]+", t)
    if len(words) < 4:
        return True, "too_short"
    return False, ""


def pick_best(
    text: str,
    leaves: list[dict[str, Any]],
    priors: list[str],
    sticky_tag: Optional[str],
) -> tuple[Optional[str], str, float]:
    norm = normalize_asr(text)
    text_tokens = set(tokenize_label(norm))
    scored: list[tuple[float, str]] = []
    for leaf in leaves:
        s = score_leaf(norm, text_tokens, leaf, priors)
        if s > 0:
            scored.append((s, leaf["tag"]))
    if not scored:
        if sticky_tag:
            return sticky_tag, "sticky_context", 0.0
        return None, "no_match", 0.0
    scored.sort(key=lambda x: (-x[0], -x[1].count("::"), x[1]))
    best_score, best_tag = scored[0]
    min_accept = 5.0
    if best_score < min_accept:
        if sticky_tag:
            sticky_score = next((s for s, t in scored if t == sticky_tag), 0.0)
            if sticky_score >= 4.0 or best_score < 4.0:
                return sticky_tag, "sticky_context", sticky_score
        return None, "weak_no_match", best_score
    if sticky_tag:
        sticky_score = next((s for s, t in scored if t == sticky_tag), 0.0)
        if sticky_score and best_tag != sticky_tag and sticky_score >= best_score * 0.9:
            return sticky_tag, "sticky_hold", sticky_score
    return best_tag, "keyword_best_of_heme", best_score


def tag_package(
    package_dir: Path,
    leaves: list[dict[str, Any]],
    *,
    out_dir: Optional[Path] = None,
) -> dict[str, Any]:
    out_dir = out_dir or package_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    package_id = manifest.get("package_id") or package_dir.name
    priors = lecture_priors(package_id)
    duration = manifest.get("duration_seconds")
    try:
        duration_f = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_f = None

    seg_path = package_dir / "segments.jsonl"
    rows = [json.loads(ln) for ln in seg_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    sticky: Optional[str] = None
    by_tag: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    indexable_rows: list[dict[str, Any]] = []

    for row in rows:
        text = row.get("text") or ""
        start = float(row.get("start_sec") or 0.0)
        dni, reason = is_do_not_index(text, start, duration_f)
        if dni:
            row["indexable"] = False
            row["primary_tag"] = None
            row["entity_name"] = None
            row["tag_status"] = "do_not_index"
            row["tag_basis"] = reason
            row["tag_score"] = None
            reasons[reason] += 1
            # reset sticky on clear agenda/thanks blocks
            if reason in {"agenda_or_overview", "thanks_or_housekeeping", "closing_summary"}:
                sticky = None
            continue

        tag, basis, score = pick_best(text, leaves, priors, sticky)
        if not tag:
            row["indexable"] = False
            row["primary_tag"] = None
            row["entity_name"] = None
            row["tag_status"] = "do_not_index"
            row["tag_basis"] = basis
            row["tag_score"] = score
            reasons[basis] += 1
            continue

        assert tag.startswith("Heme::")
        row["indexable"] = True
        row["primary_tag"] = tag
        row["entity_name"] = tag.split("::")[-1]
        row["tag_status"] = "heuristic_heme_browse_v0_1"
        row["tag_basis"] = basis
        row["tag_score"] = round(score, 3)
        sticky = tag
        by_tag[tag] += 1
        indexable_rows.append(row)

    # frames: inherit nearest sticky not required; keep non-indexable unless transcript_context matches
    frames_path = package_dir / "frames.jsonl"
    frames = []
    if frames_path.is_file():
        frames = [json.loads(ln) for ln in frames_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for fr in frames:
            ctx = fr.get("transcript_context") or ""
            tag, basis, score = pick_best(ctx, leaves, priors, None)
            if tag and score >= 4.0:
                fr["primary_tag"] = tag
                fr["indexable"] = True
                fr["tag_status"] = "heuristic_heme_browse_v0_1"
                fr["tag_basis"] = basis
                fr["tag_score"] = round(score, 3)
            else:
                fr["primary_tag"] = None
                fr["indexable"] = False
                fr["tag_status"] = "untagged_or_weak"
                fr["tag_basis"] = basis
                fr["tag_score"] = round(score, 3) if score else None

    counts = dict(manifest.get("counts") or {})
    counts.update(
        {
            "segments_total": len(rows),
            "segments_indexable": len(indexable_rows),
            "segments_do_not_index": len(rows) - len(indexable_rows),
            "frames_total": len(frames),
            "frames_indexable": sum(1 for f in frames if f.get("indexable")),
            "by_tag": dict(by_tag.most_common()),
            "do_not_index_reasons": dict(reasons),
            "heme_leaf_universe": len(leaves),
        }
    )
    manifest["counts"] = counts
    manifest["tagging"] = {
        "method": "best_of_canonical_Heme_browse_leaves_v0_1",
        "heme_leaf_count": len(leaves),
        "lecture_priors": priors,
        "created_at_utc": utc_now(),
    }
    limitations = list(manifest.get("known_limitations") or [])
    note = (
        "primary_tag chosen as best-matching canonical Heme::* browse leaf "
        f"({len(leaves)} leaves); heuristic keywords + sticky context, not human gold."
    )
    if note not in limitations:
        limitations.insert(0, note)
    manifest["known_limitations"] = limitations

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with (out_dir / "segments.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out_dir / "segments_indexable.jsonl").open("w", encoding="utf-8") as f:
        for row in indexable_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if frames:
        with (out_dir / "frames.jsonl").open("w", encoding="utf-8") as f:
            for fr in frames:
                f.write(json.dumps(fr, ensure_ascii=False) + "\n")

    audit = {
        "schema_version": "lecture_deck_heme_browse_tag_audit.v0_1",
        "created_at_utc": utc_now(),
        "package_id": package_id,
        "input_paths": [str(seg_path), str(package_dir / "manifest.json")],
        "output_paths": [
            str(out_dir / "manifest.json"),
            str(out_dir / "segments.jsonl"),
            str(out_dir / "segments_indexable.jsonl"),
        ],
        "counts": counts,
        "lecture_priors": priors,
        "known_limitations": [
            "Tags restricted to canonical Heme::* browse leaves only.",
            "Best-of scoring is heuristic; not semantic embedding retrieval.",
            "Do not vectorize segments_*.jsonl; consolidate to chunks_indexable.jsonl first.",
        ],
    }
    (out_dir / "tag_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return audit


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument(
        "--heme-leaves",
        type=Path,
        default=Path("outputs/heme_browse_leaves_v0_1.json"),
    )
    p.add_argument(
        "--browse-index",
        type=Path,
        default=Path("frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json"),
    )
    args = p.parse_args()

    if not args.heme_leaves.is_file():
        # build from browse index
        idx = json.loads(args.browse_index.read_text(encoding="utf-8"))
        heme = next(r for r in idx["roots"] if r.get("label") == "Heme")
        tags: list[dict[str, Any]] = []

        def walk(n: Any) -> None:
            if isinstance(n, dict):
                tag = n.get("tag")
                if isinstance(tag, str) and tag.startswith("Heme::"):
                    tags.append(
                        {
                            "tag": tag,
                            "label": n.get("label"),
                            "query": n.get("query"),
                            "provenance": n.get("provenance"),
                        }
                    )
                for v in n.values():
                    if isinstance(v, (list, dict)):
                        walk(v)
            elif isinstance(n, list):
                for x in n:
                    walk(x)

        walk(heme)
        uniq = {t["tag"]: t for t in tags}
        args.heme_leaves.parent.mkdir(parents=True, exist_ok=True)
        args.heme_leaves.write_text(
            json.dumps(
                {
                    "schema_version": "heme_browse_leaves.v0_1",
                    "count": len(uniq),
                    "leaves": sorted(uniq.values(), key=lambda x: x["tag"]),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    leaves = load_heme_leaves(args.heme_leaves)
    audit = tag_package(args.package_dir, leaves, out_dir=args.out_dir)
    print(
        json.dumps(
            {
                "ok": True,
                "package_id": audit["package_id"],
                "segments_indexable": audit["counts"]["segments_indexable"],
                "top_tags": list(audit["counts"]["by_tag"].items())[:8],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
