#!/usr/bin/env python3
"""Crawl ARUP education video lectures into a local catalog JSON.

Source index: https://arup.utah.edu/education/videoIndex

For each /education/{slug} page, extracts:
  - title, embed player URL, slides PDF(s)
For each embed player (/media/{slug}/videoLecture), resolves:
  - direct MP4 URL(s), VTT subtitle track(s)

Does not download media. Does not upload to GCS.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path
from typing import Any


BASE = "https://arup.utah.edu"
UA = "PathologyHubCatalogBot/0.1"
SKIP_SLUGS = {
    "/education/videoIndex",
    "/education/confIndex",
    "/education/cytoIndex",
    "/education/shortTopics",
    "/education/publications",
}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def fetch(url: str, *, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def discover_slugs() -> list[str]:
    html = fetch(f"{BASE}/education/videoIndex")
    slugs = sorted(set(re.findall(r'href="(/education/[a-z0-9_-]+)"', html)))
    return [s for s in slugs if s not in SKIP_SLUGS and not s.endswith("Index")]


def parse_education_page(slug: str) -> dict[str, Any]:
    url = BASE + slug
    try:
        html = fetch(url)
    except Exception as exc:
        return {"slug": slug.rsplit("/", 1)[-1], "education_url": url, "error": str(exc)}

    video_object: dict[str, Any] = {}
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
            graph = data.get("@graph", [data])
            for node in graph:
                if isinstance(node, dict) and node.get("@type") == "VideoObject":
                    video_object = node
                    break
        except json.JSONDecodeError:
            pass

    title = None
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if h1:
        title = unescape(re.sub(r"<[^>]+>", "", h1.group(1)))
        title = re.sub(r"\s+", " ", title).strip()
    title = title or video_object.get("name")

    pdfs = sorted(set(re.findall(r'(/sites/default/files/Edu_Media/pdfs/[^"\']+\.pdf)', html)))
    slug_name = slug.rsplit("/", 1)[-1]
    series_hint = next(
        (tag for tag in ("pcap24", "pcap25", "pcap22", "pbm25", "heme", "hemepath", "cyto", "gi", "breast", "molec", "flow") if tag in slug_name),
        None,
    )
    video_len = None
    vm = re.search(r"Video Length:</span><span class=\"field-content\">\s*([^<]+)", html)
    if vm:
        video_len = unescape(vm.group(1)).strip()

    return {
        "slug": slug_name,
        "title": title,
        "education_url": url,
        "embed_url": video_object.get("embedUrl"),
        "content_url_declared": video_object.get("contentUrl"),
        "thumbnail_url": video_object.get("thumbnailUrl"),
        "duration_iso": video_object.get("duration"),
        "video_length_label": video_len,
        "slides_pdfs": [BASE + p for p in pdfs],
        "series_hint": series_hint,
        "has_pdf": bool(pdfs),
        "has_embed": bool(video_object.get("embedUrl")),
    }


def parse_embed_page(rec: dict[str, Any]) -> dict[str, Any]:
    embed = rec.get("embed_url")
    if not embed:
        return rec
    try:
        html = fetch(embed)
    except Exception as exc:
        rec["embed_error"] = str(exc)
        return rec
    mp4s = sorted(set(re.findall(r'(/sites/default/files/Edu_Media/videos/[^"\']+\.mp4)', html)))
    vtts = sorted(set(re.findall(r'(/sites/default/files/Edu_Media/[^"\']+\.vtt)', html)))
    rec["video_mp4s"] = [BASE + u for u in mp4s]
    rec["vtt_tracks"] = [BASE + u for u in vtts]
    rec["has_mp4"] = bool(mp4s)
    rec["has_vtt"] = bool(vtts)
    if mp4s:
        rec["video_mp4_primary"] = BASE + mp4s[0]
    if rec.get("slides_pdfs"):
        rec["slides_pdf_primary"] = rec["slides_pdfs"][0]
    if vtts:
        rec["vtt_primary"] = BASE + vtts[0]
    return rec


def build_catalog(*, workers: int = 8) -> dict[str, Any]:
    slugs = discover_slugs()
    lectures: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(parse_education_page, slug): slug for slug in slugs}
        for i, fut in enumerate(as_completed(futures), 1):
            lectures.append(fut.result())
            if i % 25 == 0:
                print(f"crawled education pages {i}/{len(slugs)}", flush=True)
    lectures.sort(key=lambda r: r.get("slug") or "")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        lectures = list(pool.map(parse_embed_page, lectures))
    return {
        "schema_version": "arup_education_catalog.v0_1",
        "source": f"{BASE}/education",
        "crawled_at_utc": utc_now(),
        "url_patterns": {
            "education_page": f"{BASE}/education/{{slug}}",
            "embed_player": f"{BASE}/media/{{slug}}/videoLecture",
            "video_mp4": f"{BASE}/sites/default/files/Edu_Media/videos/{{file}}.mp4",
            "slides_pdf": f"{BASE}/sites/default/files/Edu_Media/pdfs/{{base}}_lecture-slides.pdf",
            "vtt": f"{BASE}/sites/default/files/Edu_Media/cc/{{file}}.vtt",
        },
        "counts": {
            "total": len(lectures),
            "with_title": sum(1 for r in lectures if r.get("title")),
            "with_embed": sum(1 for r in lectures if r.get("has_embed")),
            "with_mp4": sum(1 for r in lectures if r.get("has_mp4")),
            "with_pdf": sum(1 for r in lectures if r.get("has_pdf")),
            "with_vtt": sum(1 for r in lectures if r.get("has_vtt")),
            "errors": sum(1 for r in lectures if r.get("error") or r.get("embed_error")),
        },
        "series_counts": dict(Counter(r.get("series_hint") or "other" for r in lectures)),
        "lectures": lectures,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("audits/arup_education_catalog_v0_1.json"),
        help="Output catalog JSON path",
    )
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args()
    catalog = build_catalog(workers=args.workers)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(json.dumps(catalog["counts"], indent=2), flush=True)
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
