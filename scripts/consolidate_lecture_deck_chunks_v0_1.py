#!/usr/bin/env python3
"""Collapse whisper crumbs into indexable lecture chunks.

Input: tagged segments_indexable.jsonl (fine ASR utterances).
Output: chunks_indexable.jsonl — same-tag merges capped by duration/chars.

Policy:
- Never merge across primary_tag changes.
- Target ~45–90s teaching units (defaults), not 5s ASR crumbs.
- Drop leftover crumbs under min_chars unless they are the only piece in a run.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gcs_to_https(gcs_uri: str) -> str:
    without = gcs_uri[len("gs://") :]
    bucket, _, key = without.partition("/")
    return f"https://storage.googleapis.com/{bucket}/{quote(key, safe='/')}"


def make_video_time_url(video_url: str | None, start: Any, end: Any) -> str | None:
    if not video_url:
        return None
    try:
        s = float(start)
        e = float(end) if end is not None else None
    except (TypeError, ValueError):
        return None
    if e is not None:
        return f"{video_url}#t={s:g},{e:g}"
    return f"{video_url}#t={s:g}"


def smooth_tag_islands(
    rows: list[dict[str, Any]],
    *,
    min_run_utterances: int = 6,
    min_run_sec: float = 40.0,
) -> list[dict[str, Any]]:
    """Repaint brief tag flickers so consolidation isn't shredded by ASR keyword noise."""
    if not rows:
        return rows
    out = [dict(r) for r in rows]
    # Find runs of identical primary_tag
    runs: list[tuple[int, int, str]] = []  # start_idx, end_idx exclusive, tag
    i = 0
    while i < len(out):
        j = i + 1
        tag = out[i].get("primary_tag")
        while j < len(out) and out[j].get("primary_tag") == tag:
            j += 1
        runs.append((i, j, tag or ""))
        i = j

    for ri, (a, b, tag) in enumerate(runs):
        dur = float(out[b - 1]["end_sec"]) - float(out[a]["start_sec"])
        n = b - a
        if n >= min_run_utterances and dur >= min_run_sec:
            continue
        # Prefer surrounding tag if both neighbors agree; else previous; else next.
        prev_tag = runs[ri - 1][2] if ri > 0 else None
        next_tag = runs[ri + 1][2] if ri + 1 < len(runs) else None
        repaint = None
        if prev_tag and next_tag and prev_tag == next_tag:
            repaint = prev_tag
        elif prev_tag:
            repaint = prev_tag
        elif next_tag:
            repaint = next_tag
        if not repaint or repaint == tag:
            continue
        # map entity_name from ENTITY-ish suffix
        entity = None
        for r in out:
            if r.get("primary_tag") == repaint and r.get("entity_name"):
                entity = r["entity_name"]
                break
        for k in range(a, b):
            out[k]["primary_tag"] = repaint
            if entity:
                out[k]["entity_name"] = entity
            out[k]["tag_basis"] = "smoothed_short_island"
    return out


def consolidate(
    rows: list[dict[str, Any]],
    *,
    max_duration_sec: float = 150.0,
    max_chars: int = 2800,
    min_chars: int = 200,
    gap_flush_sec: float = 25.0,
) -> list[dict[str, Any]]:
    indexable = [r for r in rows if r.get("indexable") and r.get("primary_tag") and (r.get("text") or "").strip()]
    if not indexable:
        return []
    indexable = smooth_tag_islands(indexable)

    chunks: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        text = " ".join((r.get("text") or "").strip() for r in buf).strip()
        text = " ".join(text.split())
        if len(text) < min_chars and chunks and chunks[-1]["primary_tag"] == buf[0]["primary_tag"]:
            prev = chunks[-1]
            prev["text"] = (prev["text"] + " " + text).strip()
            prev["end_sec"] = float(buf[-1]["end_sec"])
            prev["source_segment_ids"] = list(prev.get("source_segment_ids") or []) + [
                r.get("segment_id") for r in buf
            ]
            prev["source_segment_count"] = len(prev["source_segment_ids"])
            prev["video_time_url"] = make_video_time_url(
                prev.get("video_url"), prev.get("start_sec"), prev.get("end_sec")
            )
            prev["char_count"] = len(prev["text"])
            prev["duration_sec"] = round(float(prev["end_sec"]) - float(prev["start_sec"]), 3)
            buf = []
            return

        first, last = buf[0], buf[-1]
        start = float(first["start_sec"])
        end = float(last["end_sec"])
        video_url = first.get("video_url")
        chunk = {
            "schema_version": "lecture_deck_chunk.v0_1",
            "package_id": first.get("package_id"),
            "chunk_id": f"{first.get('package_id')}::chunk_{len(chunks):04d}",
            "start_sec": start,
            "end_sec": end,
            "duration_sec": round(end - start, 3),
            "text": text,
            "char_count": len(text),
            "primary_tag": first.get("primary_tag"),
            "entity_name": first.get("entity_name"),
            "tag_status": "heuristic_v0_1_consolidated",
            "tag_basis": "merged_same_tag_window",
            "indexable": True,
            "root": first.get("root") or "Heme",
            "video_id": first.get("video_id"),
            "video_url": video_url,
            "video_time_url": make_video_time_url(video_url, start, end),
            "raw_source_gcs_uri": first.get("raw_source_gcs_uri"),
            "raw_source_join_basis": first.get("raw_source_join_basis"),
            "legacy_raw_source_gcs_uri": first.get("legacy_raw_source_gcs_uri"),
            "source_segment_ids": [r.get("segment_id") for r in buf],
            "source_segment_count": len(buf),
        }
        chunks.append(chunk)
        buf = []

    for row in indexable:
        if not buf:
            buf = [row]
            continue
        same_tag = row.get("primary_tag") == buf[0].get("primary_tag")
        gap = float(row["start_sec"]) - float(buf[-1]["end_sec"])
        trial_text = " ".join((r.get("text") or "").strip() for r in buf + [row])
        trial_text = " ".join(trial_text.split())
        trial_dur = float(row["end_sec"]) - float(buf[0]["start_sec"])
        if (not same_tag) or gap > gap_flush_sec or trial_dur > max_duration_sec or len(trial_text) > max_chars:
            flush()
            buf = [row]
        else:
            buf.append(row)
    flush()

    # Second pass: absorb remaining tiny chunks into previous same-tag neighbor.
    merged: list[dict[str, Any]] = []
    for c in chunks:
        if (
            merged
            and c["duration_sec"] < 55
            and c["primary_tag"] == merged[-1]["primary_tag"]
            and (float(c["end_sec"]) - float(merged[-1]["start_sec"])) <= max_duration_sec * 1.35
            and (merged[-1]["char_count"] + c["char_count"]) <= int(max_chars * 1.35)
        ):
            prev = merged[-1]
            prev["text"] = (prev["text"] + " " + c["text"]).strip()
            prev["end_sec"] = c["end_sec"]
            prev["duration_sec"] = round(float(prev["end_sec"]) - float(prev["start_sec"]), 3)
            prev["char_count"] = len(prev["text"])
            prev["source_segment_ids"] = list(prev.get("source_segment_ids") or []) + list(
                c.get("source_segment_ids") or []
            )
            prev["source_segment_count"] = len(prev["source_segment_ids"])
            prev["video_time_url"] = make_video_time_url(
                prev.get("video_url"), prev.get("start_sec"), prev.get("end_sec")
            )
        elif merged and c["duration_sec"] < 25:
            # Ultra-short island after a tag flip: fold into previous chunk (keep previous tag).
            prev = merged[-1]
            if (float(c["end_sec"]) - float(prev["start_sec"])) <= max_duration_sec * 1.35 and (
                prev["char_count"] + c["char_count"]
            ) <= int(max_chars * 1.35):
                prev["text"] = (prev["text"] + " " + c["text"]).strip()
                prev["end_sec"] = c["end_sec"]
                prev["duration_sec"] = round(float(prev["end_sec"]) - float(prev["start_sec"]), 3)
                prev["char_count"] = len(prev["text"])
                prev["source_segment_ids"] = list(prev.get("source_segment_ids") or []) + list(
                    c.get("source_segment_ids") or []
                )
                prev["source_segment_count"] = len(prev["source_segment_ids"])
                prev["video_time_url"] = make_video_time_url(
                    prev.get("video_url"), prev.get("start_sec"), prev.get("end_sec")
                )
            else:
                merged.append(c)
        else:
            merged.append(c)

    for i, c in enumerate(merged):
        c["chunk_id"] = f"{c.get('package_id')}::chunk_{i:04d}"
    return merged


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--package-dir", type=Path, required=True)
    p.add_argument("--max-duration-sec", type=float, default=150.0)
    p.add_argument("--max-chars", type=int, default=2800)
    p.add_argument("--min-chars", type=int, default=200)
    p.add_argument("--gap-flush-sec", type=float, default=25.0)
    args = p.parse_args()

    pkg = args.package_dir
    # Prefer full tagged segments.jsonl so we can also report exclusions; fall back to indexable.
    seg_path = pkg / "segments.jsonl"
    if not seg_path.is_file():
        seg_path = pkg / "segments_indexable.jsonl"
    rows = [json.loads(ln) for ln in seg_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    chunks = consolidate(
        rows,
        max_duration_sec=args.max_duration_sec,
        max_chars=args.max_chars,
        min_chars=args.min_chars,
        gap_flush_sec=args.gap_flush_sec,
    )

    out_chunks = pkg / "chunks_indexable.jsonl"
    with out_chunks.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    manifest_path = pkg / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    by_tag: dict[str, int] = {}
    for c in chunks:
        t = c["primary_tag"]
        by_tag[t] = by_tag.get(t, 0) + 1
    durs = [c["duration_sec"] for c in chunks]
    chars = [c["char_count"] for c in chunks]

    counts = dict(manifest.get("counts") or {})
    counts.update(
        {
            "chunks_indexable": len(chunks),
            "chunks_by_tag": by_tag,
            "chunk_duration_sec_mean": round(sum(durs) / len(durs), 2) if durs else 0,
            "chunk_duration_sec_median": sorted(durs)[len(durs) // 2] if durs else 0,
            "chunk_chars_mean": round(sum(chars) / len(chars), 1) if chars else 0,
            "chunk_max_duration_sec": args.max_duration_sec,
            "chunk_max_chars": args.max_chars,
        }
    )
    manifest["counts"] = counts
    manifest["index_artifact"] = "chunks_indexable.jsonl"
    manifest["index_policy"] = (
        "Vectorize ONLY chunks_indexable.jsonl. "
        "segments_indexable.jsonl is an intermediate ASR crumb file — do not index."
    )
    manifest["consolidation"] = {
        "max_duration_sec": args.max_duration_sec,
        "max_chars": args.max_chars,
        "min_chars": args.min_chars,
        "created_at_utc": utc_now(),
    }
    limitations = list(manifest.get("known_limitations") or [])
    note = "Index grain is chunks_indexable.jsonl (~75s/1.6k char merges), not raw whisper segments."
    if note not in limitations:
        limitations.insert(0, note)
    manifest["known_limitations"] = limitations
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    audit = {
        "schema_version": "lecture_deck_chunk_consolidate_audit.v0_1",
        "created_at_utc": utc_now(),
        "package_id": manifest.get("package_id"),
        "input_paths": [str(seg_path)],
        "output_paths": [str(out_chunks), str(manifest_path)],
        "counts": {
            "input_rows": len(rows),
            "input_indexable_utterances": sum(1 for r in rows if r.get("indexable")),
            "output_chunks": len(chunks),
            "by_tag": by_tag,
            "duration_sec_mean": counts.get("chunk_duration_sec_mean"),
            "duration_sec_median": counts.get("chunk_duration_sec_median"),
            "chars_mean": counts.get("chunk_chars_mean"),
        },
        "params": {
            "max_duration_sec": args.max_duration_sec,
            "max_chars": args.max_chars,
            "min_chars": args.min_chars,
        },
        "known_limitations": [
            "Consolidation is deterministic merge by tag/time/size — not discourse parsing.",
            "Do not vectorize segments_*.jsonl; only chunks_indexable.jsonl.",
        ],
    }
    (pkg / "chunk_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "chunks": len(chunks), "by_tag": by_tag, "duration_sec_median": counts.get("chunk_duration_sec_median")}, indent=2))


if __name__ == "__main__":
    main()
