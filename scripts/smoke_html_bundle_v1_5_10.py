#!/usr/bin/env python3
"""Smoke test v1.5.10 HTML bundle mode against one Pathology Hub base URL."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("API_KEY", "")
FORBIDDEN = [
    "::Lectures::",
    "::Textbooks::",
    "::Error",
    "Slide_",
    "Page_",
    "Digital_Pathology_Slide",
    "Pathology_Slide",
    "rejected_generated",
]


def request_json(method: str, path: str, payload: dict | None = None, timeout: int = 320):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, body, json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read()
        print(body[:1000].decode("utf-8", errors="replace"), file=sys.stderr)
        raise


def fetch_url(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def gs_to_public_url(uri: str) -> str:
    if not uri.startswith("gs://"):
        return uri
    rest = uri.removeprefix("gs://")
    bucket, _, path = rest.partition("/")
    return f"https://storage.googleapis.com/{bucket}/{urllib.parse.quote(path)}"


def collect_primary_tags(value):
    tags = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_results") and isinstance(item, list):
                tags.extend(x.get("primary_tag") for x in item if isinstance(x, dict) and x.get("primary_tag"))
            else:
                tags.extend(collect_primary_tags(item))
    elif isinstance(value, list):
        for item in value:
            tags.extend(collect_primary_tags(item))
    return tags


def assert_no_forbidden(label: str, text: str):
    hits = [pattern for pattern in FORBIDDEN if pattern in text]
    if hits:
        raise AssertionError(f"{label}: forbidden patterns found: {hits}")


def assert_small_json(label: str, body: bytes):
    text = body.decode("utf-8", errors="replace")
    if "<html" in text.lower() or "</html>" in text.lower():
        raise AssertionError(f"{label}: response appears to contain inline HTML")
    if len(body) > 250_000:
        raise AssertionError(f"{label}: response too large: {len(body)} bytes")


def smoke_post(label: str, payload: dict):
    print(f"{label}: request", flush=True)
    status, body, data = request_json("POST", "/evidence/search", payload)
    if status != 200:
        raise AssertionError(f"{label}: HTTP {status}")
    assert_small_json(label, body)
    assert_no_forbidden(f"{label} JSON", body.decode("utf-8", errors="replace"))
    tags = collect_primary_tags(data)
    bad_tags = [tag for tag in tags if any(pattern in str(tag) for pattern in FORBIDDEN)]
    if bad_tags:
        raise AssertionError(f"{label}: forbidden primary tags: {bad_tags[:10]}")
    print(f"{label}: ok status=200 bytes={len(body)} primary_tags={len(tags)}", flush=True)
    return body, data


def smoke_html(label: str, payload: dict):
    body, data = smoke_post(label, payload)
    result = data.get("html_result") or {}
    if result.get("status") not in {"ok", "partial"}:
        raise AssertionError(f"{label}: bad html_result.status={result.get('status')!r}")
    html_url = result.get("html_url")
    audit_uri = result.get("audit_gcs_uri")
    if not html_url or not audit_uri:
        raise AssertionError(f"{label}: missing html_url or audit_gcs_uri")
    html = fetch_url(html_url)
    audit = fetch_url(gs_to_public_url(audit_uri))
    assert_no_forbidden(f"{label} HTML", html.decode("utf-8", errors="replace"))
    audit_json = json.loads(audit.decode("utf-8"))
    if not audit_json.get("schema_version"):
        raise AssertionError(f"{label}: audit missing schema_version")
    if not audit_json.get("input_paths") and not audit_json.get("inputs"):
        raise AssertionError(f"{label}: audit missing input paths")
    if not audit_json.get("output_paths") and not audit_json.get("outputs"):
        raise AssertionError(f"{label}: audit missing output paths")
    print(
        f"{label}: html={html_url} audit={audit_uri} "
        f"figures={result.get('figure_count')} evidence={result.get('evidence_count')}",
        flush=True,
    )
    return body, data


def main() -> int:
    if not BASE_URL:
        raise SystemExit("Set BASE_URL")
    if not API_KEY:
        raise SystemExit("Set API_KEY")

    status, body, health = request_json("GET", "/health")
    if status != 200:
        raise AssertionError(f"health: HTTP {status}")
    assert_no_forbidden("health JSON", body.decode("utf-8", errors="replace"))
    if health.get("html_bundle_enabled") is not True:
        raise AssertionError("health: html_bundle_enabled is not true")
    if health.get("html_bundle_version") != "v1.5.10":
        raise AssertionError(f"health: html_bundle_version={health.get('html_bundle_version')!r}")
    if health.get("curriculum_map_forbidden_visible_tag_count") not in (0, None):
        raise AssertionError("health: curriculum forbidden visible tag count is nonzero")
    print(f"health: ok bytes={len(body)} html_bundle_version={health.get('html_bundle_version')}", flush=True)

    smoke_post(
        "normal curriculum",
        {"query": "ovary granulosa", "sources": ["curriculum"], "max_results": 5, "compact": True},
    )
    smoke_post(
        "normal evidence",
        {
            "query": "prostate adenocarcinoma cribriform pattern",
            "sources": ["textbooks"],
            "max_results": 1,
            "compact": True,
        },
    )
    smoke_html(
        "HTML teaching_page",
        {
            "query": "ovarian granulosa cell tumor",
            "sources": ["who", "textbooks", "pathout"],
            "max_results": 3,
            "compact": True,
            "include_figures": True,
            "max_figures": 5,
            "render_html": True,
            "html_profile": "teaching_page",
            "html_title": "Ovarian granulosa cell tumor teaching page",
        },
    )
    smoke_html(
        "HTML gallery",
        {
            "query": "tubular adenoma",
            "sources": ["textbooks"],
            "max_results": 5,
            "compact": True,
            "include_figures": True,
            "max_figures": 10,
            "render_html": True,
            "html_profile": "gallery",
            "html_title": "Tubular adenoma gallery",
            "target_figure_count": 50,
        },
    )
    print("SMOKE PASSED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
