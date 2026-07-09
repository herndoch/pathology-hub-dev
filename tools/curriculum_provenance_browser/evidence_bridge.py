"""Bridge helpers: curriculum provenance records → /evidence/search payloads and link URLs."""

from __future__ import annotations

import os
import re
from typing import Any

DEFAULT_EVIDENCE_API_URL = os.environ.get(
    "PATHOLOGY_HUB_API_URL",
    os.environ.get("HUB_API_URL", "https://pathology-hub-v04-vorn5q2kga-uc.a.run.app"),
)

# Map curriculum source_family to live /evidence/search `sources` values.
SOURCE_FAMILY_TO_EVIDENCE_SOURCES: dict[str, list[str]] = {
    "textbooks": ["textbooks"],
    "pathout": ["pathout"],
    "who": ["who"],
    "lectures": ["lectures"],
    "abpath": [],
}

ROOT_CODE_RE = re.compile(r"^[A-Z]{2,5}$")


def gs_to_https(uri: str | None) -> str | None:
    if not uri or not isinstance(uri, str):
        return None
    uri = uri.strip()
    if uri.startswith("gs://"):
        return "https://storage.googleapis.com/" + uri[len("gs://") :]
    return uri


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def make_video_time_url(
    video_url: str | None,
    start_sec: Any = None,
    end_sec: Any = None,
) -> str | None:
    """Build a browser-openable timestamp URL from a video URL and start/end seconds."""
    if not video_url:
        return None
    start = _safe_float(start_sec)
    end = _safe_float(end_sec)
    if start is None:
        return gs_to_https(video_url) or video_url
    base = str(video_url).split("#", 1)[0]
    https_base = gs_to_https(base) or base
    if end is not None and end > start:
        return f"{https_base}#t={start:g},{end:g}"
    return f"{https_base}#t={start:g}"


def approved_tag_to_query(approved_tag: str | None) -> str:
    """Derive a short keyword-style evidence query from a curriculum approved_tag."""
    if not approved_tag:
        return ""
    parts = [p.replace("_", " ").strip() for p in approved_tag.split("::") if p.strip()]
    if not parts:
        return ""
    if len(parts) > 1 and ROOT_CODE_RE.match(parts[0]):
        parts = parts[1:]
    if not parts:
        return approved_tag.replace("_", " ").replace("::", " ").strip()
    # Prefer the most specific leaf terms (last two segments).
    query_parts = parts[-2:] if len(parts) >= 2 else parts
    return " ".join(query_parts).strip()


def evidence_sources_for_family(source_family: str | None) -> list[str]:
    return list(SOURCE_FAMILY_TO_EVIDENCE_SOURCES.get((source_family or "").lower(), []))


def build_suggested_evidence_query(row: dict[str, Any]) -> dict[str, Any]:
    """Build a POST /evidence/search JSON body from a provenance record row."""
    family = (row.get("source_family") or "").lower()
    sources = evidence_sources_for_family(family)
    query = approved_tag_to_query(row.get("approved_tag"))
    if not query:
        excerpt = (row.get("text_excerpt") or "").strip()
        if excerpt:
            query = " ".join(excerpt.split()[:8])

    request_body: dict[str, Any] = {
        "query": query,
        "sources": sources,
        "max_results": 5,
    }

    note: str | None = None
    if family == "abpath":
        note = "ABPath is ontology-only — no evidence source mapping. Adjust query/sources manually."
    elif not sources:
        note = f"No default evidence source mapping for source_family={family!r}."
    elif not query:
        note = "Could not derive a query from approved_tag or text_excerpt — fill in query manually."

    return {
        "endpoint": "POST /evidence/search",
        "api_url": DEFAULT_EVIDENCE_API_URL.rstrip("/"),
        "request_body": request_body,
        "note": note,
    }


def video_time_url_for_record(row: dict[str, Any]) -> str | None:
    """Compute video_time_url from provenance locator fields (not stored in SQLite)."""
    if (row.get("source_family") or "").lower() != "lectures" and not row.get("source_video_gcs_uri"):
        return None
    video = row.get("source_video_gcs_uri") or row.get("raw_source_gcs_uri")
    return make_video_time_url(video, row.get("time_start_sec"), row.get("time_end_sec"))


def link_href_for_field(field: str, value: Any, *, suppress_image: bool = False) -> str | None:
    """Return an https href for known linkable provenance fields, or None."""
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text:
        return None

    if field == "image_url" and suppress_image:
        return None
    if field in {"source_url", "image_url"} and (
        text.startswith("http://") or text.startswith("https://")
    ):
        return text
    if field in {
        "who_html_gcs_path",
        "source_pdf_gcs_uri",
        "source_video_gcs_uri",
        "raw_source_gcs_uri",
        "normalized_artifact_gcs_uri",
        "image_path",
    }:
        return gs_to_https(text) if text.startswith("gs://") else None
    if field == "video_time_url":
        return text if text.startswith("http://") or text.startswith("https://") else gs_to_https(text)
    return None
