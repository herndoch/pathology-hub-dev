"""Best-effort GCS read-through/write-through cache for topic_page sidecars.

Keeps prebuilt/cached topic pages (see TOPIC_PREBUILD_PAGES_DIR in app.py and
scripts/prebuild_topic_pages_pilot_v0_1.py) available across Cloud Run
instances and redeploys, where local disk is ephemeral. Per AGENTS.md this is
an "API-exposed capability" derived output, kept separate from source /
staged / vectorized data:

    gs://pathology_hub/api_exposed/chat_mvp_topic_prebuilds_v0_1/pages/<slug>.json
    gs://pathology_hub/api_exposed/chat_mvp_topic_prebuilds_v0_1/manifests/<batch>.json

Every function here is best-effort: on any failure (library missing,
credentials missing, network error, bad bucket) it returns None/False and
never raises, so a broken/unset GCS config degrades to "local cache only"
rather than breaking the live chat path.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("chat_mvp.gcs_topic_cache")

GCS_BUCKET = os.environ.get("TOPIC_PREBUILD_GCS_BUCKET", "pathology_hub").strip()
GCS_PREFIX = os.environ.get(
    "TOPIC_PREBUILD_GCS_PREFIX", "api_exposed/chat_mvp_topic_prebuilds_v0_1/pages"
).strip().strip("/")
GCS_ENABLED = os.environ.get("TOPIC_PREBUILD_GCS_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

_client = None
_client_lock = threading.Lock()
_client_init_failed = False


def _get_client():
    """Lazily construct a storage.Client(); memoize failure so we don't retry
    (and log) on every single request once it's clear GCS isn't reachable."""
    global _client, _client_init_failed
    if _client is not None:
        return _client
    if _client_init_failed or not GCS_ENABLED or not GCS_BUCKET:
        return None
    with _client_lock:
        if _client is not None or _client_init_failed:
            return _client
        try:
            from google.cloud import storage  # type: ignore

            _client = storage.Client()
        except Exception as exc:  # noqa: BLE001 - best effort, any failure disables GCS cache
            logger.warning("gcs_topic_cache: disabled (client init failed: %s)", exc)
            _client_init_failed = True
            _client = None
    return _client


def _blob_path(slug: str) -> str:
    return f"{GCS_PREFIX}/{slug}.json"


def is_configured() -> bool:
    return bool(GCS_ENABLED and GCS_BUCKET) and not _client_init_failed


def read_page(slug: str) -> Optional[dict]:
    """Read+parse one cached topic page JSON blob, or None on any miss/error."""
    client = _get_client()
    if client is None:
        return None
    try:
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(_blob_path(slug))
        raw = blob.download_as_bytes(timeout=10)
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.info("gcs_topic_cache: read miss for %s (%s)", slug, exc)
        return None


def write_page_sync(slug: str, page: dict) -> bool:
    """Blocking upload of one page JSON. Prefer write_page_async for request paths."""
    client = _get_client()
    if client is None:
        return False
    try:
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(_blob_path(slug))
        blob.upload_from_string(
            json.dumps(page, indent=2, ensure_ascii=False),
            content_type="application/json",
            timeout=15,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("gcs_topic_cache: write failed for %s (%s)", slug, exc)
        return False


def write_page_async(slug: str, page: dict) -> None:
    """Fire-and-forget upload — never adds latency to the caller's response."""
    if not is_configured():
        return

    def _run():
        write_page_sync(slug, page)

    threading.Thread(target=_run, name=f"gcs-cache-write-{slug[:40]}", daemon=True).start()
