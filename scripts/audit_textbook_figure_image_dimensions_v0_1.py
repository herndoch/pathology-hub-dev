#!/usr/bin/env python3
"""Audit textbook figure/page image dimensions for header/footer-crop suspects.

This script is intentionally sidecar-only and read-only against public GCS
HTTP URLs. It reads unique textbook image locators from the derived curriculum
source locator SQLite index, fetches minimal byte ranges to parse JPEG/PNG
dimensions (no full-image download required beyond header bytes), and flags
suspicious aspect ratios / strip shapes that are consistent with captured
headers or footers rather than real figure panels.

It does not modify the SQLite index, vector docstores, normalized records, or
any GCS objects. It only reads public image bytes over HTTP and writes local
audit JSON/CSV sidecars.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import re
import sqlite3
import struct
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "textbook_figure_image_dimension_audit.v0_1"

DEFAULT_SQLITE = "outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_1.sqlite"
DEFAULT_OUTPUT_DIR = "06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1"

EXTREME_ASPECT_HIGH = 2.2
EXTREME_ASPECT_LOW = 0.45
WIDE_STRIP_MAX_HEIGHT = 150
WIDE_STRIP_MIN_WIDTH = 400
TALL_STRIP_MAX_WIDTH = 150
TALL_STRIP_MIN_HEIGHT = 400
TINY_DIM = 120

FIG_SLOT_RE = re.compile(r"_fig(\d+)_", re.IGNORECASE)


def gs_to_https(uri: str) -> str:
    if uri.startswith("gs://"):
        return "https://storage.googleapis.com/" + uri[len("gs://") :]
    return uri


def jpeg_size(data: bytes) -> Optional[Tuple[int, int]]:
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    n = len(data)
    while i < n - 1:
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        i += 2
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if i + 2 > n:
            return None
        seglen = struct.unpack(">H", data[i : i + 2])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 7 > n:
                return None
            height, width = struct.unpack(">HH", data[i + 3 : i + 7])
            return width, height
        i += seglen
    return None


def png_size(data: bytes) -> Optional[Tuple[int, int]]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if len(data) < 24:
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def jp2_size(data: bytes) -> Optional[Tuple[int, int]]:
    """Parse dimensions from a JP2 (JPEG2000 container) 'ihdr' box.

    JP2 signature box is `\\x00\\x00\\x00\\x0cjP  \\r\\n\\x87\\n`. The image header
    box (`ihdr`) stores height then width as big-endian uint32 immediately
    after the 4-byte box type. This is a targeted scan rather than a full
    ISO/IEC 15444-1 box-tree parser, but is reliable for the well-formed
    JP2 files produced by standard PDF/image extraction pipelines.
    """
    if data[4:12] != b"jP  \r\n\x87\n":
        return None
    idx = data.find(b"ihdr")
    if idx < 0 or idx + 12 > len(data):
        return None
    height, width = struct.unpack(">II", data[idx + 4 : idx + 12])
    return width, height


def fetch_image_size(url: str, timeout: float = 20.0, max_bytes: int = 262144) -> Optional[Tuple[int, int]]:
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8", "Range": f"bytes=0-{max_bytes - 1}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(max_bytes)
    lowered = url.lower()
    if lowered.endswith(".png") or data[:4] == b"\x89PNG":
        return png_size(data)
    if lowered.endswith((".jpx", ".jp2")) or data[4:8] == b"jP  ":
        return jp2_size(data)
    return jpeg_size(data)


def classify(width: int, height: int) -> List[str]:
    flags: List[str] = []
    if height <= 0 or width <= 0:
        return ["invalid_dimensions"]
    ratio = width / height
    if ratio > EXTREME_ASPECT_HIGH or ratio < EXTREME_ASPECT_LOW:
        flags.append("extreme_aspect_ratio")
    if height < WIDE_STRIP_MAX_HEIGHT and width > WIDE_STRIP_MIN_WIDTH:
        flags.append("wide_strip_header_footer_suspect")
    if width < TALL_STRIP_MAX_WIDTH and height > TALL_STRIP_MIN_HEIGHT:
        flags.append("tall_strip_suspect")
    if width < TINY_DIM or height < TINY_DIM:
        flags.append("tiny_image")
    return flags


def chunk_kind(chunk_id: str) -> str:
    if "_caption" in chunk_id:
        return "caption_chunk"
    if re.search(r"_p\d+_c\d+", chunk_id):
        return "page_text_chunk"
    return "other_chunk"


def fig_slot(image_path: str) -> str:
    match = FIG_SLOT_RE.search(image_path)
    return f"fig{match.group(1).zfill(2)}" if match else "unknown"


def load_candidate_rows(
    sqlite_path: Path, sample_size: int, seed: int, source_family: str
) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = cur.execute(
        """
        select record_id, chunk_id, source_id, pdf_page, approved_tag,
               coalesce(nullif(image_url, ''), image_path) as image_locator,
               locator_status
        from provenance_records
        where source_family = ?
          and (image_url is not null and image_url != '' or image_path is not null and image_path != '')
        """,
        (source_family,),
    ).fetchall()
    conn.close()

    by_image: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        loc = row["image_locator"]
        if not loc:
            continue
        by_image.setdefault(
            loc,
            {
                "image_locator": loc,
                "record_id": row["record_id"],
                "chunk_id": row["chunk_id"] or "",
                "source_id": row["source_id"],
                "pdf_page": row["pdf_page"],
                "approved_tag": row["approved_tag"],
                "locator_status": row["locator_status"],
            },
        )

    unique_rows = list(by_image.values())
    if sample_size and sample_size < len(unique_rows):
        rng = random.Random(seed)
        unique_rows = rng.sample(unique_rows, sample_size)
    return unique_rows


def probe_one(row: Dict[str, Any]) -> Dict[str, Any]:
    url = gs_to_https(row["image_locator"])
    result = dict(row)
    result["url"] = url
    result["chunk_kind"] = chunk_kind(row["chunk_id"])
    result["fig_slot"] = fig_slot(row["image_locator"])
    try:
        size = fetch_image_size(url)
        if size is None:
            result["fetch_status"] = "unparsed_header"
            result["flags"] = ["unparsed_header"]
            return result
        width, height = size
        result["width"] = width
        result["height"] = height
        result["aspect_ratio"] = round(width / height, 3) if height else None
        result["fetch_status"] = "ok"
        result["flags"] = classify(width, height)
        return result
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError) as exc:
        result["fetch_status"] = "fetch_error"
        result["flags"] = ["fetch_error"]
        result["error"] = str(exc)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-path", type=Path, default=Path(DEFAULT_SQLITE))
    parser.add_argument("--source-family", default="textbooks")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=300,
        help="Number of unique images to probe. Use 0 to probe every unique image (slow).",
    )
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--output-dir", type=Path, default=Path(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--run-tag", default="sample", help="Suffix for output filenames, e.g. sample or full.")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = args.output_dir / f"figure_image_dimension_audit_{args.run_tag}_v0_1.json"
    flagged_csv_path = args.output_dir / f"flagged_figure_images_{args.run_tag}_v0_1.csv"

    candidates = load_candidate_rows(args.sqlite_path, args.sample_size, args.seed, args.source_family)

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(probe_one, row): row for row in candidates}
        for future in as_completed(futures):
            results.append(future.result())

    total = len(results)
    fetch_ok = sum(1 for r in results if r["fetch_status"] == "ok")
    fetch_error = sum(1 for r in results if r["fetch_status"] == "fetch_error")
    unparsed = sum(1 for r in results if r["fetch_status"] == "unparsed_header")

    flag_counts: Counter[str] = Counter()
    by_chunk_kind: Dict[str, Counter[str]] = defaultdict(Counter)
    by_fig_slot: Dict[str, Counter[str]] = defaultdict(Counter)
    for r in results:
        for flag in r.get("flags", []):
            flag_counts[flag] += 1
            by_chunk_kind[r["chunk_kind"]][flag] += 1
            by_fig_slot[r["fig_slot"]][flag] += 1
        by_chunk_kind[r["chunk_kind"]]["_total"] += 1
        by_fig_slot[r["fig_slot"]]["_total"] += 1

    any_flag = [r for r in results if r.get("flags") and r["fetch_status"] == "ok"]

    audit = {
        "schema_version": SCHEMA_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "input_paths": {"sqlite_index": str(args.sqlite_path)},
        "output_paths": {"audit_json": str(audit_path), "flagged_csv": str(flagged_csv_path)},
        "run_params": {
            "source_family": args.source_family,
            "sample_size_requested": args.sample_size,
            "seed": args.seed,
            "concurrency": args.concurrency,
        },
        "counts": {
            "unique_images_probed": total,
            "fetch_ok": fetch_ok,
            "fetch_error": fetch_error,
            "unparsed_header": unparsed,
            "flag_counts": dict(flag_counts),
            "any_flag_among_fetch_ok": len(any_flag),
            "any_flag_rate_pct": round(100 * len(any_flag) / fetch_ok, 2) if fetch_ok else None,
            "by_chunk_kind": {k: dict(v) for k, v in by_chunk_kind.items()},
            "by_fig_slot": {k: dict(v) for k, v in by_fig_slot.items()},
        },
        "known_limitations": [
            "This audit reads only the first ~256KB of each image over HTTP to parse header dimensions; it does not download or inspect full pixel content.",
            "Aspect-ratio/strip heuristics are approximations for header/footer-crop suspicion, not confirmed visual classification.",
            "Sample-based runs (sample_size > 0) are a statistical estimate, not a full-corpus count, unless run with --sample-size 0.",
            "Does not modify curriculum_source_locator_index_v0_1.sqlite, vector docstores, or normalized records.",
        ],
    }
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    fieldnames = [
        "record_id", "chunk_id", "chunk_kind", "source_id", "pdf_page", "approved_tag",
        "fig_slot", "url", "width", "height", "aspect_ratio", "fetch_status", "flags",
    ]
    with flagged_csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            if not r.get("flags"):
                continue
            writer.writerow(
                {
                    "record_id": r.get("record_id"),
                    "chunk_id": r.get("chunk_id"),
                    "chunk_kind": r.get("chunk_kind"),
                    "source_id": r.get("source_id"),
                    "pdf_page": r.get("pdf_page"),
                    "approved_tag": r.get("approved_tag"),
                    "fig_slot": r.get("fig_slot"),
                    "url": r.get("url"),
                    "width": r.get("width"),
                    "height": r.get("height"),
                    "aspect_ratio": r.get("aspect_ratio"),
                    "fetch_status": r.get("fetch_status"),
                    "flags": ";".join(r.get("flags", [])),
                }
            )

    print(json.dumps({"outputs": audit["output_paths"], "counts": audit["counts"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
