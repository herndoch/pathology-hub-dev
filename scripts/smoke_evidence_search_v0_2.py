#!/usr/bin/env python3
"""Smoke tests for Evidence Search Reliability v0_2 (requires BASE_URL + PATHOLOGY_HUB_API_KEY env)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "https://pathology-hub-v04-vorn5q2kga-uc.a.run.app").rstrip("/")
API_KEY = os.environ.get("PATHOLOGY_HUB_API_KEY", "")

CASES = [
    ("health", "GET", "/health", None),
    ("lcis_breast", "POST", "/evidence/search", {"query": "LCIS breast", "sources": ["who", "pathout"], "max_results": 5, "compact": True}),
    ("ssl_colon", "POST", "/evidence/search", {"query": "SSL colon", "sources": ["who", "textbooks"], "max_results": 5, "compact": True}),
    ("ais_cervix", "POST", "/evidence/search", {"query": "AIS cervix", "sources": ["pathout"], "max_results": 5, "compact": True}),
    ("cis_bladder", "POST", "/evidence/search", {"query": "CIS bladder", "sources": ["who"], "max_results": 5, "compact": True}),
    ("ipmn_figures", "POST", "/evidence/search", {"query": "IPMN pancreas", "sources": ["textbooks"], "max_results": 5, "include_figures": True, "max_figures": 5, "compact": True}),
    ("bullous_pemphigoid_who", "POST", "/evidence/search", {"query": "bullous pemphigoid", "sources": ["who"], "max_results": 5, "compact": True}),
    ("cmf_bone", "POST", "/evidence/search", {"query": "chondromyxoid fibroma bone", "sources": ["who", "textbooks"], "max_results": 5, "compact": True}),
    ("pathout_figures", "POST", "/evidence/search", {"query": "basal cell carcinoma", "sources": ["pathout"], "max_results": 5, "include_figures": True, "max_figures": 5, "compact": True}),
    ("textbook_figures", "POST", "/evidence/search", {"query": "melanoma", "sources": ["textbooks"], "max_results": 5, "include_figures": True, "max_figures": 5, "compact": True}),
]


def request(method: str, path: str, payload: dict | None) -> tuple[int, dict]:
    headers = {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main() -> int:
    if not API_KEY and any(c[0] != "health" for c in CASES):
        print("PATHOLOGY_HUB_API_KEY not set; health-only mode")
    failed = 0
    for name, method, path, payload in CASES:
        if name != "health" and not API_KEY:
            continue
        try:
            status, body = request(method, path, payload)
            ok = status == 200
            if name == "health":
                ok = ok and body.get("loaded") is True
            print(f"{name}: {'PASS' if ok else 'FAIL'} status={status}")
            if not ok:
                failed += 1
        except urllib.error.HTTPError as exc:
            print(f"{name}: FAIL http_{exc.code}")
            failed += 1
        except Exception as exc:
            print(f"{name}: FAIL {type(exc).__name__}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
