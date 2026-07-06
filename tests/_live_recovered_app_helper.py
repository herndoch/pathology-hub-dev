"""Shared test helper for backend/pathology_hub_v04_live_recovered/app.py.

Loading the real recovered app.py triggers module-level env-var reads for the
v0_2 feature flags, so each test that needs a different flag combination must
import a FRESH copy of the module with the desired environment already set.

These tests never touch GCS, OpenAI, or FAISS: `ensure_artifacts()` and friends
are only invoked from FastAPI `@app.on_event("startup")` handlers, which do NOT
run on a plain module import (only when an ASGI server / TestClient boots the
app). The wrapper endpoints (`health_v02`, `search_evidence_v02`) are called
here as plain Python functions with the baseline endpoints monkeypatched to
deterministic stubs, so tests are fast, offline, and hermetic.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[1] / "backend" / "pathology_hub_v04_live_recovered"

_ENV_KEYS = (
    "EVIDENCE_V0_2_ENABLED",
    "EVIDENCE_QUERY_EXPANSION_ENABLED",
    "EVIDENCE_ROOT_GATING_ENABLED",
    "EVIDENCE_WHO_RERANK_ENABLED",
    "EVIDENCE_V0_2_DEBUG",
    "EVIDENCE_HUB_APP_VERSION_OVERRIDE",
    "PATHOLOGY_HUB_API_KEY",
)


def _reset_env(overrides: dict[str, str]) -> dict[str, str | None]:
    previous: dict[str, str | None] = {}
    for key in _ENV_KEYS:
        previous[key] = os.environ.get(key)
        os.environ.pop(key, None)
    for key, value in overrides.items():
        os.environ[key] = value
    return previous


def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def load_app_module(env_overrides: dict[str, str] | None = None):
    """Import a fresh copy of the recovered app with the given env flags set.

    NOTE: the env vars are deliberately left set (not restored) after this
    returns, because some flags (e.g. EVIDENCE_WHO_RERANK_ENABLED,
    EVIDENCE_V0_2_DEBUG, EVIDENCE_ROOT_GATING_ENABLED) are re-read from
    os.environ at REQUEST time inside search_evidence_v02/health_v02, not
    only at import time. Each call to load_app_module() resets all known
    keys first, so tests remain isolated from each other as long as they
    call load_app_module() before making assertions.
    """
    _reset_env(env_overrides or {})
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    for mod_name in list(sys.modules):
        if mod_name == "app" or mod_name.startswith("evidence_search_reliability_v0_2"):
            del sys.modules[mod_name]
    module = importlib.import_module("app")
    return module


def make_search_request(module, **overrides: Any):
    payload = {
        "query": "LCIS",
        "sources": ["who"],
        "max_results": 5,
        "compact": True,
    }
    payload.update(overrides)
    return module.EvidenceSearchRequest(**payload)


def baseline_response_stub(**overrides: Any) -> dict[str, Any]:
    base = {
        "schema_version": "evidence_search_response.v1.5.10",
        "query": "LCIS",
        "source_status": {"who": "ok", "journals": "not_requested", "pathout": "not_requested", "textbooks": "not_requested", "curriculum": "not_requested"},
        "who_results": [
            {"title": "Lobular carcinoma in situ", "source": "who", "score": -5.0, "rank": 1, "url": "https://storage.googleapis.com/pathology-hub-0/WHO/example.html"},
            {"title": "Unrelated entity", "source": "who", "score": -6.0, "rank": 2, "url": "https://storage.googleapis.com/pathology-hub-0/WHO/other.html"},
        ],
        "journal_results": [],
        "pathout_results": [],
        "textbook_results": [],
        "curriculum_results": [],
        "figures": [],
        "warnings": [],
    }
    base.update(overrides)
    return base
