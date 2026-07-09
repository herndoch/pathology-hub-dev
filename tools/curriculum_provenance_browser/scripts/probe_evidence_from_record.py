#!/usr/bin/env python3
"""Probe live /evidence/search using a curriculum provenance record_id.

Reads the record from the local SQLite index (read-only), builds the suggested
POST /evidence/search body, optionally calls the live API when
PATHOLOGY_HUB_API_KEY or HUB_API is set, and writes an audit JSON under
06_audits/. Never prints secret values.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from evidence_bridge import (  # noqa: E402
    DEFAULT_EVIDENCE_API_URL,
    build_suggested_evidence_query,
    video_time_url_for_record,
)

DEFAULT_SQLITE = REPO_ROOT / "outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_1.sqlite"
AUDIT_DIR = REPO_ROOT / "06_audits/curriculum_provenance_links/v0_1"
SCHEMA_VERSION = "provenance_evidence_probe_v0_1"


def _load_api_key() -> tuple[str | None, str | None]:
    for env_name in ("PATHOLOGY_HUB_API_KEY", "HUB_API"):
        value = os.environ.get(env_name)
        if value:
            return value, env_name
    return None, None


def _fetch_record(conn: sqlite3.Connection, record_id: str) -> dict[str, Any]:
    row = conn.execute(
        "select * from provenance_records where record_id = ?",
        (record_id,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"record_id not found: {record_id}")
    return dict(row)


def _result_counts(response: dict[str, Any]) -> dict[str, int]:
    keys = (
        "textbook_results",
        "pathout_results",
        "who_results",
        "lecture_results",
        "video_results",
        "journal_results",
        "curriculum_results",
    )
    return {k: len(response.get(k) or []) for k in keys if response.get(k)}


def _post_evidence_search(url: str, api_key: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:500]
    except urllib.error.URLError as exc:
        return 0, str(exc.reason)[:500]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-id", required=True, help="Curriculum provenance record_id")
    parser.add_argument(
        "--sqlite",
        default=os.environ.get("CURRICULUM_LOCATOR_SQLITE", str(DEFAULT_SQLITE)),
        help="Path to curriculum_source_locator_index_v0_1.sqlite (read-only)",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("PATHOLOGY_HUB_API_URL", DEFAULT_EVIDENCE_API_URL),
        help="Live evidence API base URL",
    )
    parser.add_argument(
        "--skip-live-call",
        action="store_true",
        help="Build the suggested query and audit only; do not POST /evidence/search",
    )
    parser.add_argument(
        "--run-tag",
        default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        help="Suffix for the audit JSON filename",
    )
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite index not found: {sqlite_path}")

    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        record = _fetch_record(conn, args.record_id)
    finally:
        conn.close()

    suggested = build_suggested_evidence_query(record)
    api_key, api_key_env = _load_api_key()
    live_call: dict[str, Any] = {
        "attempted": False,
        "api_key_env": api_key_env,
        "api_key_present": bool(api_key),
    }

    if not args.skip_live_call and api_key:
        url = args.api_url.rstrip("/") + "/evidence/search"
        live_call["attempted"] = True
        live_call["url"] = url
        try:
            status_code, body = _post_evidence_search(url, api_key, suggested["request_body"])
            live_call["status_code"] = status_code
            live_call["ok"] = 200 <= status_code < 300
            if live_call["ok"] and isinstance(body, dict):
                live_call["source_status"] = body.get("source_status")
                live_call["result_counts"] = _result_counts(body)
            else:
                live_call["error"] = body if isinstance(body, str) else json.dumps(body)[:500]
        except Exception as exc:
            live_call["ok"] = False
            live_call["error"] = str(exc)[:500]
    elif not args.skip_live_call:
        live_call["skipped_reason"] = "No PATHOLOGY_HUB_API_KEY or HUB_API in environment"

    audit = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_paths": {
            "sqlite": str(sqlite_path),
            "record_id": args.record_id,
        },
        "output_paths": {},
        "counts": {
            "live_call_attempted": int(live_call.get("attempted", False)),
            "live_call_ok": int(live_call.get("ok", False)),
        },
        "record_summary": {
            "source_family": record.get("source_family"),
            "approved_tag": record.get("approved_tag"),
            "locator_status": record.get("locator_status"),
            "video_time_url": video_time_url_for_record(record),
        },
        "suggested_evidence_query": suggested,
        "live_evidence_search": live_call,
        "known_limitations": [
            "Query text is derived heuristically from approved_tag; manual refinement may be needed.",
            "ABPath records have no default evidence source mapping.",
            "API key values are never written to this audit.",
            "Live call is skipped when --skip-live-call is set or no API key env var is present.",
        ],
    }

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    safe_tag = args.run_tag.replace("/", "_")
    audit_path = AUDIT_DIR / f"provenance_evidence_probe_{safe_tag}.json"
    audit["output_paths"]["audit_json"] = str(audit_path)
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "audit_path": str(audit_path),
        "record_id": args.record_id,
        "suggested_query": suggested["request_body"],
        "live_call_attempted": live_call.get("attempted"),
        "live_call_ok": live_call.get("ok"),
        "api_key_present": live_call.get("api_key_present"),
    }, indent=2))


if __name__ == "__main__":
    main()
