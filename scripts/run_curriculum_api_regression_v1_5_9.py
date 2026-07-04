#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
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


def request_json(method, path, payload=None):
    if not BASE_URL:
        raise RuntimeError("BASE_URL is required")
    data = None
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{method} {path} returned {e.code}: {raw[:1000]}") from e


def assert_no_forbidden_curriculum_tags(resp):
    for result in resp.get("curriculum_results") or []:
        tag = str(result.get("tag") or "")
        hits = [p for p in FORBIDDEN if p in tag]
        assert not hits, f"Forbidden pattern(s) {hits} in curriculum tag {tag}"


def assert_curriculum_health():
    status, health = request_json("GET", "/health")
    assert status == 200
    expected = {
        "curriculum_map_enabled": True,
        "curriculum_map_version": "v0.2",
        "curriculum_map_build_status": "passed_local_visibility_gate",
        "curriculum_map_forbidden_visible_tag_count": 0,
        "curriculum_map_records_visible": 137293,
        "curriculum_map_review_queue_count": 4245,
    }
    for key, value in expected.items():
        assert health.get(key) == value, f"health[{key!r}]={health.get(key)!r}, expected {value!r}"
    return health


def post_search(payload):
    status, resp = request_json("POST", "/evidence/search", payload)
    assert status == 200
    assert isinstance(resp, dict)
    return resp


def assert_curriculum_smoke():
    for payload in [
        {"query": "GYN::Ovary", "sources": ["curriculum"], "max_results": 5, "compact": True},
        {"query": "ovary granulosa", "sources": ["curriculum"], "max_results": 5, "compact": True},
    ]:
        resp = post_search(payload)
        assert resp.get("source_status", {}).get("curriculum") == "ok", resp
        assert resp.get("curriculum_status", {}).get("build_status") == "passed_local_visibility_gate"
        assert resp.get("curriculum_results"), f"No curriculum results for {payload}"
        assert_no_forbidden_curriculum_tags(resp)


def assert_existing_source_smoke():
    probes = [
        {"query": "ovarian high grade serous carcinoma", "sources": ["who"], "max_results": 1, "compact": True},
        {"query": "prostate adenocarcinoma cribriform pattern", "sources": ["textbooks"], "max_results": 1, "compact": True},
        {"query": "prostate adenocarcinoma cribriform pattern", "sources": ["pathout"], "max_results": 1, "compact": True},
        {"query": "melanoma invasive overview", "sources": ["lectures"], "max_results": 1, "compact": True},
    ]
    for payload in probes:
        source = payload["sources"][0]
        resp = post_search(payload)
        status = resp.get("source_status", {}).get(source)
        if source == "lectures":
            status = resp.get("source_status", {}).get("lectures") or resp.get("source_status", {}).get("videos")
        assert status not in {None, "not_requested", "error", "vector_error", "upstream_error", "error_no_upstream"}, (
            source,
            status,
            resp.get("warnings"),
        )


def main():
    health = assert_curriculum_health()
    assert_curriculum_smoke()
    assert_existing_source_smoke()
    print(json.dumps({
        "passed": True,
        "base_url": BASE_URL,
        "version": health.get("version"),
        "curriculum_map_build_status": health.get("curriculum_map_build_status"),
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)
