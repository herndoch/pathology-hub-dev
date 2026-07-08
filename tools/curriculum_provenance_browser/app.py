#!/usr/bin/env python3
"""Local read-only browser for curriculum source locator provenance index."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE = REPO_ROOT / "outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_1.sqlite"
DEFAULT_INDEX_AUDIT = REPO_ROOT / "06_audits/curriculum_provenance_links/v0_1/source_locator_index_audit_v0_1.json"
DEFAULT_REPAIR_AUDIT = REPO_ROOT / "06_audits/curriculum_provenance_links/v0_1/source_locator_repair_audit_v0_1.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"

SQLITE_PATH = Path(os.environ.get("CURRICULUM_LOCATOR_SQLITE", str(DEFAULT_SQLITE)))
INDEX_AUDIT_PATH = Path(os.environ.get("CURRICULUM_LOCATOR_INDEX_AUDIT", str(DEFAULT_INDEX_AUDIT)))
REPAIR_AUDIT_PATH = Path(os.environ.get("CURRICULUM_LOCATOR_REPAIR_AUDIT", str(DEFAULT_REPAIR_AUDIT)))

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
    return data


def _load_audit(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "sqlite_path": str(SQLITE_PATH),
        "sqlite_exists": SQLITE_PATH.exists(),
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
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> SearchResponse:
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
    return {
        "record_id": record_id,
        "fields": {col: data.get(col.replace("_json", "")) for col in PROVENANCE_COLUMNS if col in data or col.replace("_json", "") in data},
        "locator_summary": data["locator_summary"],
    }
