#!/usr/bin/env python3
"""Local read-only browser for curriculum source locator provenance index."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from evidence_bridge import (
    build_suggested_evidence_query,
    link_href_for_field,
    video_time_url_for_record,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE = REPO_ROOT / "outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_1.sqlite"
DEFAULT_INDEX_AUDIT = REPO_ROOT / "06_audits/curriculum_provenance_links/v0_1/source_locator_index_audit_v0_1.json"
DEFAULT_REPAIR_AUDIT = REPO_ROOT / "06_audits/curriculum_provenance_links/v0_1/source_locator_repair_audit_v0_1.json"
DEFAULT_QUALITY_FLAGS_JSONL = (
    REPO_ROOT / "outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl"
)
STATIC_DIR = Path(__file__).resolve().parent / "static"

SQLITE_PATH = Path(os.environ.get("CURRICULUM_LOCATOR_SQLITE", str(DEFAULT_SQLITE)))
INDEX_AUDIT_PATH = Path(os.environ.get("CURRICULUM_LOCATOR_INDEX_AUDIT", str(DEFAULT_INDEX_AUDIT)))
REPAIR_AUDIT_PATH = Path(os.environ.get("CURRICULUM_LOCATOR_REPAIR_AUDIT", str(DEFAULT_REPAIR_AUDIT)))
QUALITY_FLAGS_JSONL_PATH = Path(
    os.environ.get("CURRICULUM_QUALITY_FLAGS_JSONL", str(DEFAULT_QUALITY_FLAGS_JSONL))
)

QUALITY_FILTER_VALUES = {"all", "suppressed", "flagged", "clean"}

SOURCE_FAMILY_LABELS = {
    "abpath": "ABPath",
    "pathout": "PathOut",
    "who": "WHO",
    "lectures": "Lectures",
    "textbooks": "Textbooks",
}

LOCATOR_TYPE_HELP = {
    "ontology_tag": "ABPath ontology tag origin — curriculum taxonomy, not source evidence.",
    "web_page": "PathOut web page URL plus figure URLs when present.",
    "who_html_or_entity": "Local WHO HTML GCS path / entity locator.",
    "video_time_or_chunk": "Lecture source video GCS URI plus timestamp when available.",
    "pdf_page_or_page_image": "Textbook source PDF GCS URI plus page and page/figure image when available.",
}

PROVENANCE_COLUMNS = [
    "provenance_row_key",
    "record_id",
    "source_family",
    "approved_tag",
    "root",
    "map_status",
    "visible",
    "locator_type",
    "locator_status",
    "locator",
    "source_id",
    "chunk_id",
    "raw_source_gcs_uri",
    "normalized_artifact_gcs_uri",
    "source_url",
    "source_video_gcs_uri",
    "time_start_sec",
    "time_end_sec",
    "source_pdf_gcs_uri",
    "pdf_page",
    "image_path",
    "image_url",
    "figure_id",
    "figure_record_id",
    "who_entity_name",
    "who_html_gcs_path",
    "input_path",
    "missing_locator_parts_json",
    "direct_http_urls_json",
    "gcs_uris_json",
    "text_excerpt",
]

app = FastAPI(
    title="Curriculum Provenance Browser",
    version="0.1.0",
    description="Local read-only UI for repaired curriculum source locator index.",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class SearchResponse(BaseModel):
    total: int
    limit: int
    offset: int
    rows: list[dict[str, Any]]


def _connect() -> sqlite3.Connection:
    if not SQLITE_PATH.exists():
        raise HTTPException(status_code=503, detail=f"SQLite index not found: {SQLITE_PATH}")
    conn = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_json_field(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for key in ("missing_locator_parts_json", "direct_http_urls_json", "gcs_uris_json"):
        data[key.replace("_json", "")] = _parse_json_field(data.pop(key))
    data["source_family_label"] = SOURCE_FAMILY_LABELS.get(data.get("source_family") or "", data.get("source_family"))
    data["locator_type_help"] = LOCATOR_TYPE_HELP.get(data.get("locator_type") or "", "")
    return data


def _build_locator_summary(row: dict[str, Any]) -> dict[str, Any]:
    family = row.get("source_family") or ""
    summary: dict[str, Any] = {
        "family": family,
        "family_label": row.get("source_family_label"),
        "locator_type": row.get("locator_type"),
        "locator_status": row.get("locator_status"),
        "help": row.get("locator_type_help"),
        "primary": None,
        "secondary": [],
        "missing_parts": row.get("missing_locator_parts") or [],
    }

    if family == "abpath":
        summary["primary"] = {
            "kind": "ontology_tag",
            "label": "Approved tag (ontology origin)",
            "value": row.get("approved_tag") or row.get("locator"),
        }
        summary["note"] = "Not source evidence — ABPath curriculum taxonomy only."
    elif family == "pathout":
        summary["primary"] = {"kind": "url", "label": "Page URL", "value": row.get("source_url") or row.get("locator")}
        figure_urls = row.get("direct_http_urls") or []
        if figure_urls:
            summary["secondary"].append({"kind": "figure_urls", "label": "Figure URLs", "values": figure_urls})
    elif family == "who":
        summary["primary"] = {
            "kind": "gcs",
            "label": "WHO HTML path",
            "value": row.get("who_html_gcs_path") or row.get("locator"),
        }
        if row.get("who_entity_name"):
            summary["secondary"].append(
                {"kind": "text", "label": "Entity", "value": row.get("who_entity_name")}
            )
    elif family == "lectures":
        video = row.get("source_video_gcs_uri") or row.get("raw_source_gcs_uri")
        start = row.get("time_start_sec")
        end = row.get("time_end_sec")
        summary["primary"] = {"kind": "gcs", "label": "Source video", "value": video}
        if start is not None:
            time_label = f"{start:g}s" if end is None else f"{start:g}–{end:g}s"
            summary["secondary"].append({"kind": "time", "label": "Timestamp", "value": time_label})
        elif row.get("locator"):
            summary["secondary"].append({"kind": "text", "label": "Chunk locator", "value": row.get("locator")})
    elif family == "textbooks":
        summary["primary"] = {
            "kind": "gcs",
            "label": "Source PDF",
            "value": row.get("source_pdf_gcs_uri") or row.get("raw_source_gcs_uri"),
        }
        if row.get("pdf_page") is not None:
            summary["secondary"].append({"kind": "page", "label": "PDF page", "value": row.get("pdf_page")})
        if row.get("image_url"):
            summary["secondary"].append({"kind": "url", "label": "Figure/page image", "value": row.get("image_url")})
        elif row.get("image_path"):
            summary["secondary"].append({"kind": "gcs", "label": "Figure/page image path", "value": row.get("image_path")})
        if row.get("figure_id"):
            summary["secondary"].append({"kind": "text", "label": "Figure ID", "value": row.get("figure_id")})

    return summary


def _enrich_row(row: sqlite3.Row) -> dict[str, Any]:
    data = _row_to_dict(row)
    data["locator_summary"] = _build_locator_summary(data)
    data["quality_flag"] = _quality_flag_for(data.get("record_id"))
    return data


def _load_audit(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# In-memory quality-flag join (read-only JSONL, no DB connection). Cached by
# source path so tests can point QUALITY_FLAGS_JSONL_PATH at a fixture and
# get a fresh load without restarting the process.
_quality_flags_cache: dict[str, dict[str, Any]] | None = None
_quality_flags_cache_path: Path | None = None


def _load_quality_flags(path: Path) -> dict[str, dict[str, Any]]:
    """Load the textbook figure image quality-flag sidecar JSONL, keyed by record_id.

    Read-only: this never opens curriculum_source_locator_index_v0_1.sqlite or
    curriculum_record_provenance_sidecar_repaired_v0_1.jsonl, and never mutates
    the sidecar file itself.
    """
    if not path.exists():
        return {}
    flags_by_record: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            record_id = row.get("record_id")
            if not record_id:
                continue
            flags_by_record[record_id] = {
                "tier": row.get("tier"),
                "flags": row.get("flags") or [],
                "width": row.get("width"),
                "height": row.get("height"),
            }
    return flags_by_record


def _quality_flags() -> dict[str, dict[str, Any]]:
    global _quality_flags_cache, _quality_flags_cache_path
    if _quality_flags_cache is None or _quality_flags_cache_path != QUALITY_FLAGS_JSONL_PATH:
        _quality_flags_cache = _load_quality_flags(QUALITY_FLAGS_JSONL_PATH)
        _quality_flags_cache_path = QUALITY_FLAGS_JSONL_PATH
    return _quality_flags_cache


def _quality_flag_for(record_id: str | None) -> dict[str, Any] | None:
    if not record_id:
        return None
    return _quality_flags().get(record_id)


def _matches_quality(quality_flag: dict[str, Any] | None, quality: str) -> bool:
    if quality == "suppressed":
        return bool(quality_flag) and quality_flag.get("tier") == "suppress_render"
    if quality == "flagged":
        return bool(quality_flag)
    if quality == "clean":
        return quality_flag is None
    return True


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "sqlite_path": str(SQLITE_PATH),
        "sqlite_exists": SQLITE_PATH.exists(),
        "quality_flags_jsonl_path": str(QUALITY_FLAGS_JSONL_PATH),
        "quality_flags_jsonl_exists": QUALITY_FLAGS_JSONL_PATH.exists(),
        "read_only": True,
    }


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    index_audit = _load_audit(INDEX_AUDIT_PATH)
    repair_audit = _load_audit(REPAIR_AUDIT_PATH)
    with _connect() as conn:
        total = conn.execute("select count(*) from provenance_records").fetchone()[0]
        families = [
            row[0]
            for row in conn.execute(
                "select distinct source_family from provenance_records order by source_family"
            ).fetchall()
        ]
        roots = [
            row[0]
            for row in conn.execute(
                "select distinct root from provenance_records where root is not null and root != '' order by root limit 200"
            ).fetchall()
        ]
    return {
        "sqlite_path": str(SQLITE_PATH),
        "total_records": total,
        "source_families": families,
        "sample_roots": roots,
        "index_audit": index_audit,
        "repair_audit": repair_audit,
        "locator_type_help": LOCATOR_TYPE_HELP,
        "source_family_labels": SOURCE_FAMILY_LABELS,
    }


@app.get("/api/summary")
def summary() -> dict[str, Any]:
    with _connect() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                """
                select source_family, locator_type, locator_status, row_count
                from source_family_summary
                order by source_family, locator_status, locator_type
                """
            ).fetchall()
        ]
        totals = conn.execute(
            """
            select locator_status, sum(row_count) as total
            from source_family_summary
            group by locator_status
            order by locator_status
            """
        ).fetchall()
    for row in rows:
        row["source_family_label"] = SOURCE_FAMILY_LABELS.get(row["source_family"], row["source_family"])
        row["locator_type_help"] = LOCATOR_TYPE_HELP.get(row["locator_type"], "")
    return {
        "rows": rows,
        "totals_by_status": {row["locator_status"]: row["total"] for row in totals},
    }


@app.get("/api/search", response_model=SearchResponse)
def search(
    approved_tag: str | None = Query(None, description="Substring match on approved_tag"),
    root: str | None = Query(None, description="Exact or substring match on root"),
    source_family: str | None = Query(None),
    text: str | None = Query(None, description="Substring match on text_excerpt, approved_tag, locator"),
    locator_status: str | None = Query(None, description="complete, partial, or omit for all"),
    completeness: str | None = Query(
        None,
        description="Alias filter: complete | partial | all. Overrides locator_status when set.",
    ),
    quality: str | None = Query(
        None,
        description=(
            "Optional textbook figure image quality-flag filter, applied in-memory after the "
            "SQL query: all (default) | suppressed | flagged | clean."
        ),
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> SearchResponse:
    if quality is not None and quality not in QUALITY_FILTER_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"quality must be one of {sorted(QUALITY_FILTER_VALUES)}, got: {quality}",
        )
    quality = quality or "all"

    where: list[str] = []
    params: list[Any] = []

    if completeness in {"complete", "partial"}:
        locator_status = completeness
    elif completeness == "all":
        locator_status = None

    if approved_tag:
        where.append("approved_tag like ?")
        params.append(f"%{approved_tag}%")
    if root:
        where.append("root like ?")
        params.append(f"%{root}%")
    if source_family:
        where.append("source_family = ?")
        params.append(source_family.lower())
    if text:
        where.append("(text_excerpt like ? or approved_tag like ? or locator like ?)")
        params.extend([f"%{text}%", f"%{text}%", f"%{text}%"])
    if locator_status:
        where.append("locator_status = ?")
        params.append(locator_status)

    clause = f"where {' and '.join(where)}" if where else ""

    if quality == "all":
        # Unchanged SQL-side pagination path (existing behavior).
        count_sql = f"select count(*) from provenance_records {clause}"
        data_sql = f"""
            select * from provenance_records
            {clause}
            order by source_family, locator_status, approved_tag, record_id
            limit ? offset ?
        """
        with _connect() as conn:
            total = conn.execute(count_sql, params).fetchone()[0]
            rows = [_enrich_row(row) for row in conn.execute(data_sql, [*params, limit, offset]).fetchall()]
        return SearchResponse(total=total, limit=limit, offset=offset, rows=rows)

    # quality filter is applied in-memory after the existing SQL query (same
    # WHERE clause, unchanged). SQL-side limit/offset is dropped here so the
    # reported total and page reflect the post-filter set rather than a
    # partially-filtered single page of the unfiltered SQL result.
    all_sql = f"""
        select * from provenance_records
        {clause}
        order by source_family, locator_status, approved_tag, record_id
    """
    with _connect() as conn:
        matched_rows = [_enrich_row(row) for row in conn.execute(all_sql, params).fetchall()]

    filtered_rows = [r for r in matched_rows if _matches_quality(r.get("quality_flag"), quality)]
    total = len(filtered_rows)
    page_rows = filtered_rows[offset : offset + limit]

    return SearchResponse(total=total, limit=limit, offset=offset, rows=page_rows)


@app.get("/api/records/{record_id:path}")
def record_detail(record_id: str) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            "select * from provenance_records where record_id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"record_id not found: {record_id}")
        data = _enrich_row(row)
    fields = {
        col: data.get(col.replace("_json", ""))
        for col in PROVENANCE_COLUMNS
        if col in data or col.replace("_json", "") in data
    }
    suppress_image = bool(data.get("quality_flag") and data["quality_flag"].get("tier") == "suppress_render")
    video_time_url = video_time_url_for_record(data)
    linkable_fields = {
        key: link_href_for_field(key, val, suppress_image=suppress_image)
        for key, val in {
            **fields,
            "video_time_url": video_time_url,
        }.items()
        if link_href_for_field(key, val, suppress_image=suppress_image)
    }
    return {
        "record_id": record_id,
        "fields": fields,
        "locator_summary": data["locator_summary"],
        "quality_flag": data["quality_flag"],
        "video_time_url": video_time_url,
        "linkable_fields": linkable_fields,
        "suggested_evidence_query": build_suggested_evidence_query(data),
    }
