"""Shared helpers for evidence retrieval benchmark v0_1."""

from __future__ import annotations

import csv
import json
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "evidence_retrieval_benchmark.v0_1"
DEFAULT_BASE_URL = "https://pathology-hub-v04-vorn5q2kga-uc.a.run.app"
DEFAULT_SOURCES = ("who", "pathout", "textbooks", "journals")

FAILURE_MODES = (
    "expected_hit_found",
    "expected_source_present_but_not_retrieved",
    "wrong_entity_preferred",
    "wrong_root_preferred",
    "abbreviation_expansion_missing",
    "figure_urls_missing_without_include_figures",
    "figure_urls_present_with_include_figures",
    "curriculum_node_missing",
    "source_unavailable",
    "api_not_run_missing_key",
    "local_source_missing",
    "parse_error",
)

ROOT_ALIASES = {
    "Breast": ("breast",),
    "GI": ("gi", "colon", "gastrointestinal", "digestive", "pancreas", "esophagus"),
    "GU": ("gu", "kidney", "renal", "bladder", "prostate", "urinary"),
    "GYN": ("gyn", "endometrium", "cervix", "ovary", "vulva", "uterus"),
    "Skin": ("skin", "derm", "dermatology"),
    "BST": ("bst", "bone", "soft tissue", "sarcoma"),
    "HN": ("hn", "head neck", "salivary", "thyroid"),
    "Endo": ("endo", "endocrine", "thyroid", "adrenal"),
    "Thorax_Mediastinum": ("thorax", "lung", "mediastinum"),
}

RESULT_KEY_FIELDS = (
    "who_results",
    "pathout_results",
    "textbook_results",
    "journal_results",
    "lecture_results",
    "video_results",
    "curriculum_results",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_text(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def token_set(value: str) -> set[str]:
    return {t for t in normalize_text(value).split() if len(t) > 2}


def load_entities_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_expected_hits(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_queries_for_entity(entity: dict[str, str]) -> list[dict[str, str]]:
    name = entity["entity_name"].strip()
    root = entity.get("root", "").strip()
    abbr = (entity.get("abbreviation") or "").strip()
    organ = (entity.get("organ_context") or root).strip()
    morph = (entity.get("morphology_molecular_term") or "").strip()
    queries = [
        {"query_type": "exact_name", "query": name},
    ]
    if abbr:
        queries.append({"query_type": "abbreviation", "query": abbr})
    if organ:
        queries.append({"query_type": "entity_plus_organ", "query": f"{name} {organ}"})
    if morph:
        queries.append({"query_type": "entity_plus_morphology", "query": f"{name} {morph}"})
    return queries


def request_json(
    base_url: str,
    api_key: str,
    method: str,
    path: str,
    payload: dict | None = None,
    timeout: int = 120,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body)


def extract_figure_urls(response: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for fig in response.get("figures") or []:
        if isinstance(fig, dict):
            for key in ("figure_url", "image_url", "page_image_url", "url"):
                val = fig.get(key)
                if isinstance(val, str) and val.startswith("http"):
                    urls.append(val)
    for group in RESULT_KEY_FIELDS:
        for hit in response.get(group) or []:
            if not isinstance(hit, dict):
                continue
            for key in ("figure_url", "image_url", "page_image_url", "url", "source_url"):
                val = hit.get(key)
                if isinstance(val, str) and val.startswith("http") and (
                    "imgau" in val or "figure" in val or "storage.googleapis.com" in val
                ):
                    urls.append(val)
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def flatten_hit(hit: dict[str, Any], source: str, rank: int) -> dict[str, Any]:
    return {
        "rank": hit.get("rank", rank),
        "title": hit.get("title") or hit.get("tag") or hit.get("source_name") or "",
        "score": hit.get("score") or hit.get("vector_score") or hit.get("fts_score"),
        "source_id": hit.get("source_id") or hit.get("document_id") or hit.get("doc_id"),
        "chunk_id": hit.get("chunk_id") or hit.get("record_id"),
        "page_id": hit.get("page") or hit.get("page_id"),
        "excerpt": (hit.get("excerpt") or hit.get("text") or "")[:500],
        "retrieval_mode": hit.get("retrieval_mode"),
        "primary_tag": hit.get("primary_tag") or hit.get("tag"),
        "source": source,
    }


def hit_matches_expected(hit: dict[str, Any], expected: dict[str, Any], entity: dict[str, str]) -> bool:
    title = normalize_text(str(hit.get("title") or ""))
    excerpt = normalize_text(str(hit.get("excerpt") or hit.get("text") or ""))
    tag = normalize_text(str(hit.get("primary_tag") or hit.get("tag") or ""))
    blob = f"{title} {excerpt} {tag}"
    entity_norm = normalize_text(entity["entity_name"])
    if entity_norm and entity_norm in blob:
        return True
    for phrase in expected.get("title_substrings") or []:
        if normalize_text(phrase) in blob:
            return True
    for phrase in expected.get("tag_substrings") or []:
        if normalize_text(phrase) in tag:
            return True
    for token in expected.get("required_tokens") or []:
        if normalize_text(token) not in blob:
            return False
        return True
    return False


def classify_failure(
    *,
    source: str,
    include_figures: bool,
    source_status: str,
    hits: list[dict[str, Any]],
    expected: dict[str, Any],
    entity: dict[str, str],
    local_corpus_present: bool,
    api_ran: bool,
    figure_urls: list[str],
) -> str:
    if not api_ran:
        return "api_not_run_missing_key"
    if source_status in {"error", "upstream_error", "vector_error", "error_no_upstream", "not_requested"}:
        return "source_unavailable"
    if not local_corpus_present and source in {"who", "pathout", "textbooks", "curriculum"}:
        return "local_source_missing"
    if any(hit_matches_expected(h, expected, entity) for h in hits):
        if include_figures and (expected.get("figure_expected") is True) and not figure_urls:
            return "figure_urls_present_with_include_figures" if False else "expected_hit_found"
        return "expected_hit_found"
    if source == "curriculum" and expected.get("curriculum_tag_expected"):
        return "curriculum_node_missing"
    if include_figures and expected.get("figure_expected") is True and not figure_urls:
        return "figure_urls_missing_without_include_figures" if not include_figures else "figure_urls_present_with_include_figures"
    if not include_figures and expected.get("figure_expected") is True and figure_urls:
        return "figure_urls_present_with_include_figures"
    wrong_root = expected.get("wrong_root_markers") or []
    for hit in hits[:3]:
        blob = normalize_text(
            f"{hit.get('title')} {hit.get('excerpt')} {hit.get('primary_tag')}"
        )
        for marker in wrong_root:
            if normalize_text(marker) in blob:
                return "wrong_root_preferred"
    wrong_entity = expected.get("wrong_entity_markers") or []
    for hit in hits[:3]:
        blob = normalize_text(f"{hit.get('title')} {hit.get('excerpt')}")
        for marker in wrong_entity:
            if normalize_text(marker) in blob and normalize_text(entity["entity_name"]) not in blob:
                return "wrong_entity_preferred"
    if expected.get("abbreviation") and any(
        q.get("query_type") == "abbreviation" for q in expected.get("queries", [])
    ):
        pass
    return "expected_source_present_but_not_retrieved"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize_failure_modes(rows: list[dict[str, Any]]) -> Counter:
    return Counter(row.get("failure_mode") or "unknown" for row in rows)
