#!/usr/bin/env python3
"""Tag lecture_deck_package segments for Heme aggressive B-cell lecture PoC.

Rules:
- Assign primary_tag only when the segment meaningfully contributes to an entity.
- Mark intro / thanks / pure agenda / housekeeping as indexable=False (do_not_index).
- Prefer canonical video name Heme_SH_Aggressive_B_Cell.mp4 (pending upload).
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote


CANONICAL_VIDEO_GCS = "gs://pathology-hub-0/source_videos/Heme_SH_Aggressive_B_Cell.mp4"
LEGACY_VIDEO_GCS = (
    "gs://pathology-hub-0/source_videos/Other_Heme_Lecture_aggressive b cell lymphomas.mp4"
)

# Lecture TOC entities (Sohani SH aggressive B-cell) → browse index tags
ENTITY_RULES: list[dict[str, Any]] = [
    {
        "name": "burkitt",
        "tag": "Heme::Mature_B_Cell::Burkitt::Burkitt_Lymphoma",
        "patterns": [
            r"\bburkitt\b",
            r"\bburkett\b",
            r"\bstarry[\s-]?sky\b",
            r"\bendemic\b.*\bburkitt\b",
            r"\bmyc\b.*\bburkitt\b",
        ],
        "strong": [r"\bburkitt lymphoma\b", r"\bburkett lymphoma\b"],
    },
    {
        "name": "burkitt_like_11q",
        "tag": "Heme::Mature_B_Cell::Large_B_Cell::High_Grade_B_Cell_Lymphoma_With_11q_Aberration",
        "patterns": [
            r"\b11q\b",
            r"burkitt[\s-]?like.*11q",
            r"burkett[\s-]?like.*11q",
            r"11q aberration",
        ],
        "strong": [r"\b11q\b"],
    },
    {
        "name": "hgbl_rearrangements",
        "tag": "Heme::Mature_B_Cell::Large_B_Cell::DLBCL_High_Grade_With_MYC_And_BCL2_Rearrangements",
        "patterns": [
            r"double[\s-]?hit",
            r"triple[\s-]?hit",
            r"high[\s-]?grade b[\s-]?cell lymphoma with.*(myc|bcl)",
            r"myc.*(bcl2|bcl-2|bcl6|bcl-6)",
            r"(bcl2|bcl-2|bcl6|bcl-6).*myc",
            r"mcl-2|b-cl-6|bcl.?2 and or bcl.?6",
        ],
        "strong": [r"double[\s-]?hit", r"triple[\s-]?hit"],
    },
    {
        "name": "hgbl_nos",
        "tag": "Heme::Mature_B_Cell::Large_B_Cell::High_Grade_B_Cell_Lymphoma_NOS",
        "patterns": [
            r"high[\s-]?grade b[\s-]?cell lymphoma.{0,40}nos",
            r"high[\s-]?grade b[\s-]?cell lymphoma is not otherwise",
            r"high[\s-]?grade.{0,20}not otherwise specified",
        ],
        "strong": [r"high[\s-]?grade b[\s-]?cell lymphoma.{0,40}nos"],
    },
    {
        "name": "dlbcl_nos",
        "tag": "Heme::Mature_B_Cell::Large_B_Cell::Diffuse_Large_B_Cell_Lymphoma_NOS",
        "patterns": [
            r"\bdlbcl\b",
            r"diffuse large b[\s-]?cell",
            r"cell of origin",
            r"germinal center.*(dlbcl|type)",
            r"activated b[\s-]?cell",
            r"\bgcb\b",
            r"\babc\b.*(dlbcl|type|subtype)",
            r"hans algorithm",
            r"\bcd10\b.*dlbcl",
            r"ipi\b",
        ],
        "strong": [r"\bdlbcl\b", r"diffuse large b[\s-]?cell lymphoma"],
    },
    {
        "name": "pmbl",
        "tag": "Heme::Mature_B_Cell::Large_B_Cell::Primary_Mediastinal_Large_B_Cell_Lymphoma",
        "patterns": [
            r"primary media",
            r"primary mediastinal",
            r"\bpmbl\b",
            r"mediastinal large b",
            r"grey zone|gray zone",
        ],
        "strong": [r"primary mediastinal", r"primary media", r"\bpmbl\b"],
    },
    {
        "name": "alk_lbcl",
        "tag": "Heme::Mature_B_Cell::Large_B_Cell::ALK_Positive_Large_B_Cell_Lymphoma",
        "patterns": [
            r"alk[\s-]?positive large",
            r"alk positive large",
            r"alc positive large",  # ASR mangling
            r"\balk\b.{0,30}large b",
        ],
        "strong": [r"alk[\s-]?positive large", r"alc positive large"],
    },
    {
        "name": "thrlbcl",
        "tag": "Heme::Mature_B_Cell::Large_B_Cell::T_Cell_Histiocyte_Rich_Large_B_Cell_Lymphoma",
        "patterns": [
            r"histiocyte[\s-]?rich",
            r"histocyte[\s-]?rich",
            r"t[\s-]?cell.?histiocyte",
            r"\bthrlbcl\b",
        ],
        "strong": [r"histiocyte[\s-]?rich", r"histocyte[\s-]?rich"],
    },
]

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
    r"society for hematopathology virtual curriculum",
    r"listed on this slide are the entities",
    r"we will be discussing during this lecture",
    r"we'll be discussing in this lecture the entities",
    r"questions\??\s*$",
    r"any questions",
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


def normalize_asr(text: str) -> str:
    t = text.lower()
    # Common ASR mangling in this lecture
    replacements = [
        (r"\bburkett\b", "burkitt"),
        (r"\bburket\b", "burkitt"),
        (r"\bburqat\b", "burkitt"),
        (r"\bburqa\b", "burkitt"),
        (r"\bspiratic\b", "sporadic"),
        (r"\bmick\b", "myc"),
        (r"\bmcl-2\b", "bcl2"),
        (r"\bb-cl-6\b", "bcl6"),
        (r"\bmedia style\b", "mediastinal"),
        (r"\bmediacinell\b", "mediastinal"),
        (r"\balc positive\b", "alk positive"),
        (r"\bextranotal\b", "extranodal"),
        (r"\bextranodontal\b", "extranodal"),
        (r"\biliococcal\b", "ileocecal"),
        (r"\brutoxymab\b", "rituximab"),
        (r"\bhistocyte\b", "histiocyte"),
        (r"\belk\b", "alk"),
    ]
    for pat, rep in replacements:
        t = re.sub(pat, rep, t)
    return t


def match_entities(text: str) -> list[tuple[str, str, bool]]:
    """Return list of (name, tag, is_strong)."""
    t = normalize_asr(text)
    hits: list[tuple[str, str, bool]] = []
    for rule in ENTITY_RULES:
        strong = any(re.search(p, t) for p in rule["strong"])
        weak = any(re.search(p, t) for p in rule["patterns"])
        if strong or weak:
            hits.append((rule["name"], rule["tag"], strong))
    return hits


def is_do_not_index(text: str, start_sec: float, sticky: Optional[str]) -> tuple[bool, str]:
    t = normalize_asr(text)
    # Opening agenda / speaker bio — entity names here are TOC only.
    if start_sec < 150:
        return True, "agenda_or_overview"
    if start_sec < 200 and re.search(
        r"hello,?\s+my name is|delighted to participate|society for hematopathology|"
        r"listed on this slide|entities that we will|we'll be discussing|"
        r"of course, talk about|spend a little bit of time discussing|"
        r"this table is one that i will come back|nice overview|"
        r"fourth edition update|who classification|provisional entit",
        t,
    ):
        return True, "agenda_or_overview"
    # Closing multi-entity recap / thanks
    if start_sec > 6050 and (len(match_entities(text)) >= 2 or re.search(r"thank|attention|in this talk", t)):
        return True, "closing_summary"
    for pat in DO_NOT_INDEX_PATTERNS:
        if re.search(pat, t):
            if re.search(r"listed on this slide|entities that we will|we'll be discussing in this lecture the entities", t):
                return True, "agenda_toc"
            if re.search(r"hello,?\s+my name is|delighted to participate|society for hematopathology", t):
                return True, "speaker_intro"
            if re.search(r"thank|acknowledg|disclosure|conflict of interest", t):
                return True, "thanks_or_disclosure"
            if re.search(r"any questions|questions\??\s*$", t) and not sticky:
                return True, "qa_housekeeping"
    # Very short filler
    words = re.findall(r"[a-z0-9]+", t)
    if len(words) < 4 and not match_entities(text):
        return True, "too_short_no_entity"
    # Closing thanks near end
    if start_sec > 6000 and re.search(r"thank|attention|wrap", t):
        return True, "closing"
    return False, ""


def choose_primary(
    hits: list[tuple[str, str, bool]],
    sticky_name: Optional[str],
) -> tuple[Optional[str], Optional[str], str]:
    if not hits and sticky_name:
        for rule in ENTITY_RULES:
            if rule["name"] == sticky_name:
                return sticky_name, rule["tag"], "sticky_context"
        return None, None, "no_match"
    if not hits:
        return None, None, "no_match"
    strong = [h for h in hits if h[2]]
    pool = strong or hits
    # Prefer more specific entities over DLBCL when both fire
    priority = [
        "burkitt_like_11q",
        "hgbl_rearrangements",
        "hgbl_nos",
        "alk_lbcl",
        "thrlbcl",
        "pmbl",
        "burkitt",
        "dlbcl_nos",
    ]
    pool_sorted = sorted(pool, key=lambda h: priority.index(h[0]) if h[0] in priority else 99)
    name, tag, _ = pool_sorted[0]
    basis = "strong_keyword" if pool_sorted[0][2] else "keyword"
    return name, tag, basis


def tag_segments(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sticky: Optional[str] = None
    sticky_until_gap = 0
    counts = {
        "input": len(rows),
        "indexable": 0,
        "do_not_index": 0,
        "tagged": 0,
        "sticky_tagged": 0,
        "by_tag": {},
        "do_not_index_reasons": {},
    }
    out: list[dict[str, Any]] = []

    for row in rows:
        text = row.get("text") or ""
        start = float(row.get("start_sec") or 0)
        skip, reason = is_do_not_index(text, start, sticky)
        hits = match_entities(text)
        # TOC/agenda with many entity names but no sticky yet → do not index
        if not sticky and len(hits) >= 2 and start < 120:
            skip, reason = True, "agenda_multi_entity"

        name, tag, basis = choose_primary(hits, None if skip else sticky)

        if skip:
            row = dict(row)
            row["indexable"] = False
            row["do_not_index_reason"] = reason
            row["primary_tag"] = None
            row["tag_status"] = "do_not_index"
            row["tag_basis"] = reason
            row["entity_name"] = None
            counts["do_not_index"] += 1
            counts["do_not_index_reasons"][reason] = counts["do_not_index_reasons"].get(reason, 0) + 1
            out.append(row)
            continue

        if name and basis != "sticky_context":
            sticky = name
            sticky_until_gap = 0
        elif name and basis == "sticky_context":
            sticky_until_gap += 1
            # Allow longer sticky through morphology paragraphs without entity names.
            if sticky_until_gap > 24:
                name, tag, basis = None, None, "sticky_expired"
                sticky = None
        else:
            sticky_until_gap += 1
            if sticky_until_gap > 24:
                sticky = None

        row = dict(row)
        if tag:
            row["indexable"] = True
            row["primary_tag"] = tag
            row["entity_name"] = name
            row["tag_status"] = "heuristic_v0_1"
            row["tag_basis"] = basis
            counts["indexable"] += 1
            counts["tagged"] += 1
            if basis == "sticky_context":
                counts["sticky_tagged"] += 1
            counts["by_tag"][tag] = counts["by_tag"].get(tag, 0) + 1
        else:
            # Content-ish but no entity → do not index (avoid orphan junk in vector)
            row["indexable"] = False
            row["do_not_index_reason"] = "no_meaningful_entity_tag"
            row["primary_tag"] = None
            row["entity_name"] = None
            row["tag_status"] = "do_not_index"
            row["tag_basis"] = "no_meaningful_entity_tag"
            counts["do_not_index"] += 1
            counts["do_not_index_reasons"]["no_meaningful_entity_tag"] = (
                counts["do_not_index_reasons"].get("no_meaningful_entity_tag", 0) + 1
            )
        out.append(row)

    return {"rows": out, "counts": counts}


def apply_canonical_video(row: dict[str, Any], video_url: str, gcs_uri: str, join_basis: str) -> dict[str, Any]:
    row = dict(row)
    row["raw_source_gcs_uri"] = gcs_uri
    row["video_url"] = video_url
    row["video_time_url"] = make_video_time_url(video_url, row.get("start_sec"), row.get("end_sec"))
    row["raw_source_join_basis"] = join_basis
    row["legacy_raw_source_gcs_uri"] = LEGACY_VIDEO_GCS
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    pkg = args.package_dir
    segments = [
        json.loads(ln)
        for ln in (pkg / "segments.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    frames = [
        json.loads(ln)
        for ln in (pkg / "frames.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))

    tagged = tag_segments(segments)
    video_url = gcs_to_https(CANONICAL_VIDEO_GCS)
    join_basis = "canonical_name_pending_upload"

    out_rows = [
        apply_canonical_video(r, video_url, CANONICAL_VIDEO_GCS, join_basis) for r in tagged["rows"]
    ]
    out_frames = []
    for fr in frames:
        fr2 = apply_canonical_video(fr, video_url, CANONICAL_VIDEO_GCS, join_basis)
        # Frame inherits nearest prior indexable segment tag when possible
        t = float(fr2.get("start_sec") or 0)
        prior = None
        for seg in out_rows:
            if seg.get("indexable") and float(seg.get("start_sec") or 0) <= t:
                prior = seg
            if float(seg.get("start_sec") or 0) > t:
                break
        if prior:
            fr2["primary_tag"] = prior.get("primary_tag")
            fr2["indexable"] = True
            fr2["tag_status"] = "inherited_from_segment"
        else:
            fr2["primary_tag"] = None
            fr2["indexable"] = False
            fr2["tag_status"] = "do_not_index"
        out_frames.append(fr2)

    indexable_segs = [r for r in out_rows if r.get("indexable")]
    indexable_frames = [f for f in out_frames if f.get("indexable")]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "segments.jsonl").open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (args.out_dir / "segments_indexable.jsonl").open("w", encoding="utf-8") as f:
        for r in indexable_segs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (args.out_dir / "frames.jsonl").open("w", encoding="utf-8") as f:
        for r in out_frames:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    new_manifest = dict(manifest)
    new_manifest.update(
        {
            "schema_version": "lecture_deck_package.v0_1",
            "tagging_version": "heme_aggressive_b_heuristic_v0_1",
            "raw_source_gcs_uri": CANONICAL_VIDEO_GCS,
            "video_url": video_url,
            "raw_source_join_basis": join_basis,
            "legacy_raw_source_gcs_uri": LEGACY_VIDEO_GCS,
            "video_file_declared": "Heme_SH_Aggressive_B_Cell.mp4",
            "counts": {
                "segments_total": len(out_rows),
                "segments_indexable": len(indexable_segs),
                "segments_do_not_index": tagged["counts"]["do_not_index"],
                "frames_total": len(out_frames),
                "frames_indexable": len(indexable_frames),
                "by_tag": tagged["counts"]["by_tag"],
                "do_not_index_reasons": tagged["counts"]["do_not_index_reasons"],
                "segments_with_video_time_url": sum(1 for r in out_rows if r.get("video_time_url")),
            },
            "created_at_utc": utc_now(),
            "known_limitations": [
                "Canonical MP4 path set to Heme_SH_Aggressive_B_Cell.mp4 — pending user upload (legacy Other_Heme_* kept as fallback pointer).",
                "Tags are heuristic keyword + sticky-section; not human-reviewed.",
                "do_not_index segments excluded from segments_indexable.jsonl — do not vectorize them.",
                "Not written into live lecture FAISS/docstore; not API-exposed yet.",
            ],
        }
    )
    (args.out_dir / "manifest.json").write_text(json.dumps(new_manifest, indent=2) + "\n", encoding="utf-8")

    audit = {
        "schema_version": "lecture_deck_package_tag_audit.v0_1",
        "created_at_utc": utc_now(),
        "package_id": new_manifest.get("package_id"),
        "input_paths": [
            str(pkg / "segments.jsonl"),
            str(pkg / "frames.jsonl"),
            str(pkg / "manifest.json"),
        ],
        "output_paths": [
            str(args.out_dir / "manifest.json"),
            str(args.out_dir / "segments.jsonl"),
            str(args.out_dir / "segments_indexable.jsonl"),
            str(args.out_dir / "frames.jsonl"),
            str(args.out_dir / "audit.json"),
        ],
        "counts": new_manifest["counts"],
        "canonical_video": {
            "raw_source_gcs_uri": CANONICAL_VIDEO_GCS,
            "join_basis": join_basis,
            "legacy_fallback": LEGACY_VIDEO_GCS,
        },
        "known_limitations": new_manifest["known_limitations"],
        "index_policy": "Only segments_indexable.jsonl rows should enter vector index.",
    }
    (args.out_dir / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "counts": new_manifest["counts"]}, indent=2))


if __name__ == "__main__":
    main()
