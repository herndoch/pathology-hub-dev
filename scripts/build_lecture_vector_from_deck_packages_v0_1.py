#!/usr/bin/env python3
"""Build lecture FAISS/docstore from gated deck_packages chunks_indexable.jsonl.

Policy:
  - Index ONLY chunks_indexable.jsonl rows with non-null video_time_url
  - Never vectorize segments*.jsonl
  - Write versioned outputs under 03_indexes/lectures/vector_deck_packages_v0_1/
  - Optionally promote into live STRICT_CYTO_v9 paths (after backup)
  - Produce audit JSON before/with upload

Does not itself restart Cloud Run — pods cache downloaded artifacts until
a new revision / cold start.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

import faiss
import numpy as np
from google.cloud.storage import Client
from openai import OpenAI


EMBEDDING_MODEL = "text-embedding-3-small"
SCHEMA_VERSION = "lecture_timecoded_vector_manifest.deck_packages_v0_1"
DECK_PREFIX = "02_normalized/lectures/deck_packages/"
VERSIONED_PREFIX = "03_indexes/lectures/vector_deck_packages_v0_1/"
LIVE_PREFIX = "03_indexes/lectures/vector_STRICT_CYTO_v9/"
LIVE_NAMES = {
    "docstore": "lecture_timecoded_vector_docstore_STRICT_CYTO_v9.jsonl",
    "embeddings": "lecture_timecoded_embeddings_STRICT_CYTO_v9.npy",
    "faiss_index": "lecture_timecoded_faiss_STRICT_CYTO_v9.index",
    "manifest": "lecture_timecoded_vector_manifest_STRICT_CYTO_v9.json",
}
VERSIONED_NAMES = {
    "docstore": "lecture_deck_packages_vector_docstore_v0_1.jsonl",
    "embeddings": "lecture_deck_packages_embeddings_v0_1.npy",
    "faiss_index": "lecture_deck_packages_faiss_v0_1.index",
    "manifest": "lecture_deck_packages_vector_manifest_v0_1.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug_video_id(package_id: str, video_file: Optional[str], raw_uri: Optional[str]) -> str:
    if video_file:
        stem = Path(video_file).stem
        if stem:
            return stem
    if raw_uri and raw_uri.startswith("gs://"):
        return Path(unquote(raw_uri.rstrip("/").split("/")[-1])).stem
    # package_id often ends with _v0_1
    return re.sub(r"_v0_1$", "", package_id)


def embed_text_for_row(title: str, video_id: str, primary_tag: Optional[str], transcript: str) -> str:
    """Match legacy retrieval flavor: title/tag metadata + transcript."""
    tag = primary_tag or "_UNMAPPED_"
    body = " ".join((transcript or "").split())
    return (
        f"Title: {title} Video ID: {video_id} Primary tag: {tag} "
        f"Tag status: semantic_gated_v0_2 Transcript: {body}"
    )


def embed_texts(client: OpenAI, texts: list[str], *, batch_size: int = 64) -> np.ndarray:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch, encoding_format="float")
        by_idx = sorted(resp.data, key=lambda d: d.index)
        vectors.extend([d.embedding for d in by_idx])
        print(f"  embedded {min(i + batch_size, len(texts))}/{len(texts)}", flush=True)
    arr = np.asarray(vectors, dtype=np.float32)
    norms = np.maximum(np.linalg.norm(arr, axis=1, keepdims=True), 1e-12)
    return arr / norms


def list_package_ids(client: Client, hub_bucket: str) -> list[str]:
    hub = client.bucket(hub_bucket)
    pkgs: set[str] = set()
    for b in hub.list_blobs(prefix=DECK_PREFIX):
        # .../deck_packages/<package_id>/chunks_indexable.jsonl
        rest = b.name[len(DECK_PREFIX) :]
        parts = rest.split("/")
        if len(parts) == 2 and parts[1] == "chunks_indexable.jsonl":
            pkgs.add(parts[0])
    return sorted(pkgs)


def load_package_chunks(
    client: Client,
    hub_bucket: str,
    package_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    hub = client.bucket(hub_bucket)
    inputs: list[str] = []
    man_blob = hub.blob(f"{DECK_PREFIX}{package_id}/manifest.json")
    chunk_blob = hub.blob(f"{DECK_PREFIX}{package_id}/chunks_indexable.jsonl")
    if not chunk_blob.exists():
        return [], {}, inputs
    inputs.append(f"gs://{hub_bucket}/{chunk_blob.name}")
    manifest: dict[str, Any] = {}
    if man_blob.exists():
        inputs.append(f"gs://{hub_bucket}/{man_blob.name}")
        manifest = json.loads(man_blob.download_as_text())
    rows = []
    for line in chunk_blob.download_as_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows, manifest, inputs


def adapt_row(
    chunk: dict[str, Any],
    *,
    manifest: dict[str, Any],
    vector_id: int,
) -> Optional[dict[str, Any]]:
    video_time_url = chunk.get("video_time_url")
    video_url = chunk.get("video_url") or manifest.get("video_url")
    if not video_time_url or not video_url:
        return None
    if chunk.get("raw_source_join_basis") in {"no_match", None} and not manifest.get("raw_source_gcs_uri"):
        # still allow if URLs present
        pass
    package_id = chunk.get("package_id") or manifest.get("package_id") or "unknown"
    title = (
        manifest.get("title")
        or package_id.replace("_", " ")
    )
    video_file = manifest.get("video_file_declared")
    raw_uri = chunk.get("raw_source_gcs_uri") or manifest.get("raw_source_gcs_uri")
    video_id = slug_video_id(package_id, video_file, raw_uri)
    primary_tag = chunk.get("primary_tag")
    transcript = chunk.get("text") or ""
    if len(transcript.strip()) < 40:
        return None

    embed_src = embed_text_for_row(title, video_id, primary_tag, transcript)
    start_sec = chunk.get("start_sec")
    end_sec = chunk.get("end_sec")
    try:
        start_f = float(start_sec) if start_sec is not None else None
        end_f = float(end_sec) if end_sec is not None else None
    except (TypeError, ValueError):
        start_f = end_f = None

    chunk_id = chunk.get("chunk_id") or f"lecture::{video_id}::{vector_id:06d}"
    # Prefer lecture:: namespace for API familiarity while keeping unique ids
    if not str(chunk_id).startswith("lecture::"):
        api_chunk_id = f"lecture::{video_id}::{chunk_id.split('::')[-1]}"
    else:
        api_chunk_id = chunk_id

    return {
        "chunk_id": api_chunk_id,
        "deck_chunk_id": chunk.get("chunk_id"),
        "package_id": package_id,
        "vector_id": vector_id,
        "source_family": "lectures",
        "source_type": "lecture_timecoded_chunk",
        "title": title,
        "video_id": video_id,
        "video_url": video_url,
        "video_time_url": video_time_url,
        "raw_source_gcs_uri": raw_uri,
        "raw_source_join_basis": chunk.get("raw_source_join_basis")
        or manifest.get("raw_source_join_basis"),
        "start_sec": start_f,
        "end_sec": end_f,
        "duration_sec": chunk.get("duration_sec"),
        "primary_tag": primary_tag,
        "entity_name": chunk.get("entity_name"),
        "tag_status": chunk.get("tag_status") or "semantic_gated_v0_2",
        "tag_basis": chunk.get("tag_basis") or "semantic_gated_best_of_browse",
        "tag_score": chunk.get("tag_score"),
        "tag_margin": chunk.get("tag_margin"),
        "tag_runner_up": chunk.get("tag_runner_up"),
        "tagging_scope": "deck_packages_gated_v0_1",
        "tag_governance_status": "semantic_gated_v0_2",
        "root": chunk.get("root") or manifest.get("root"),
        "text": embed_src,
        "transcript_text": transcript,
        "text_char_count": len(embed_src),
        "index_grain": "chunks_indexable.jsonl",
        "schema_version": "lecture_deck_vector_row.v0_1",
    }


def build_faiss(matrix: np.ndarray) -> faiss.Index:
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    return index


def write_outputs(
    out_dir: Path,
    rows: list[dict[str, Any]],
    matrix: np.ndarray,
    index: faiss.Index,
    *,
    input_paths: list[str],
    promote_live: bool,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_path = out_dir / VERSIONED_NAMES["docstore"]
    npy_path = out_dir / VERSIONED_NAMES["embeddings"]
    faiss_path = out_dir / VERSIONED_NAMES["faiss_index"]
    man_path = out_dir / VERSIONED_NAMES["manifest"]

    with doc_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    np.save(npy_path, matrix)
    faiss.write_index(index, str(faiss_path))

    by_tag = Counter(r.get("primary_tag") or "_UNMAPPED_" for r in rows)
    by_video = Counter(r.get("video_id") for r in rows)
    by_root = Counter(r.get("root") or "Unknown" for r in rows)
    with_url = sum(1 for r in rows if r.get("video_time_url"))

    gcs_versioned = {
        k: f"gs://pathology_hub/{VERSIONED_PREFIX}{v}" for k, v in VERSIONED_NAMES.items()
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": utc_now(),
        "source_family": "lectures",
        "dataset_scope": "deck_packages_gated_chunks_v0_1",
        "input_paths": input_paths,
        "input_gcs_glob": f"gs://pathology_hub/{DECK_PREFIX}*/chunks_indexable.jsonl",
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": int(matrix.shape[1]),
        "record_count": len(rows),
        "bad_or_empty_rows_skipped": 0,
        "faiss_index_type": "IndexFlatIP_cosine_normalized",
        "vectorized": True,
        "api_exposed": False,  # true only after Cloud Run picks up artifacts
        "promote_live_requested": promote_live,
        "gcs_outputs": gcs_versioned,
        "live_gcs_outputs_if_promoted": {
            k: f"gs://pathology_hub/{LIVE_PREFIX}{v}" for k, v in LIVE_NAMES.items()
        },
        "counts": {
            "distinct_video_ids": len(by_video),
            "rows_with_video_time_url": with_url,
            "by_root": dict(by_root.most_common()),
            "top_primary_tags": by_tag.most_common(20),
            "top_video_ids": by_video.most_common(20),
            "tag_status_counts": dict(Counter(r.get("tag_status") for r in rows)),
        },
        "known_limitations": [
            "Deck-package gated chunks only — legacy STRICT_CYTO 42k corpus not merged in this build.",
            "Packages with zero gated chunks or missing video_time_url are omitted.",
            "Cloud Run must cold-start / new revision to download replaced artifacts (local pod cache).",
            "Semantic tags are gated embeddings, not human gold.",
        ],
    }
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "paths": {
            "docstore": str(doc_path),
            "embeddings": str(npy_path),
            "faiss_index": str(faiss_path),
            "manifest": str(man_path),
        },
        "manifest": manifest,
    }


def upload_file(client: Client, local: Path, gcs_uri: str) -> str:
    assert gcs_uri.startswith("gs://")
    without = gcs_uri[len("gs://") :]
    bucket_name, _, key = without.partition("/")
    client.bucket(bucket_name).blob(key).upload_from_filename(str(local))
    return gcs_uri


def backup_live(client: Client, stamp: str) -> list[str]:
    hub = client.bucket("pathology_hub")
    backup_prefix = f"03_indexes/lectures/vector_STRICT_CYTO_v9_backup_before_deck_v0_1_{stamp}/"
    copied = []
    for name in LIVE_NAMES.values():
        src = hub.blob(f"{LIVE_PREFIX}{name}")
        if not src.exists():
            continue
        dest_name = f"{backup_prefix}{name}"
        hub.copy_blob(src, hub, dest_name)
        copied.append(f"gs://pathology_hub/{dest_name}")
    return copied


def promote_to_live(client: Client, out_dir: Path) -> list[str]:
    uploaded = []
    mapping = [
        (VERSIONED_NAMES["docstore"], LIVE_NAMES["docstore"]),
        (VERSIONED_NAMES["embeddings"], LIVE_NAMES["embeddings"]),
        (VERSIONED_NAMES["faiss_index"], LIVE_NAMES["faiss_index"]),
        (VERSIONED_NAMES["manifest"], LIVE_NAMES["manifest"]),
    ]
    for local_name, live_name in mapping:
        local = out_dir / local_name
        uri = f"gs://pathology_hub/{LIVE_PREFIX}{live_name}"
        upload_file(client, local, uri)
        uploaded.append(uri)
    return uploaded


def local_smoke(index: faiss.Index, matrix: np.ndarray, rows: list[dict[str, Any]], client: OpenAI) -> dict[str, Any]:
    queries = [
        "peripheral T-cell lymphoma angioimmunoblastic",
        "breast implant associated anaplastic large cell lymphoma",
        "invasive lobular carcinoma LCIS",
        "Barrett esophagus dysplasia",
        "nodular fasciitis soft tissue",
    ]
    results = []
    q_emb = embed_texts(client, queries)
    scores, idxs = index.search(q_emb, 5)
    for qi, q in enumerate(queries):
        hits = []
        for score, idx in zip(scores[qi], idxs[qi]):
            if idx < 0:
                continue
            r = rows[int(idx)]
            hits.append(
                {
                    "score": round(float(score), 4),
                    "title": r.get("title"),
                    "primary_tag": r.get("primary_tag"),
                    "video_id": r.get("video_id"),
                    "video_time_url": r.get("video_time_url"),
                    "start_sec": r.get("start_sec"),
                }
            )
        results.append({"query": q, "hits": hits})
    return {"ok": True, "queries": results}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hub-bucket", default="pathology_hub")
    p.add_argument("--out-dir", type=Path, default=Path("outputs/lecture_vector_deck_packages_v0_1"))
    p.add_argument("--audit-dir", type=Path, default=Path("audits/lecture_vector_deck_packages_v0_1"))
    p.add_argument("--upload", action="store_true")
    p.add_argument("--promote-live", action="store_true", help="Backup then overwrite STRICT_CYTO_v9 paths")
    p.add_argument("--limit-packages", type=int, default=0)
    p.add_argument("--skip-smoke", action="store_true")
    args = p.parse_args()

    gcs = Client()
    oai = OpenAI()
    package_ids = list_package_ids(gcs, args.hub_bucket)
    if args.limit_packages:
        package_ids = package_ids[: args.limit_packages]

    print(f"Found {len(package_ids)} deck packages with chunks_indexable.jsonl", flush=True)

    rows: list[dict[str, Any]] = []
    input_paths: list[str] = []
    skipped = Counter()
    packages_used = []

    for pid in package_ids:
        chunks, manifest, inputs = load_package_chunks(gcs, args.hub_bucket, pid)
        input_paths.extend(inputs)
        if not chunks:
            skipped["empty_chunks_file"] += 1
            continue
        kept_here = 0
        for ch in chunks:
            adapted = adapt_row(ch, manifest=manifest, vector_id=len(rows))
            if not adapted:
                skipped["missing_url_or_short_text"] += 1
                continue
            rows.append(adapted)
            kept_here += 1
        if kept_here:
            packages_used.append({"package_id": pid, "chunks": kept_here})
            print(f"  {pid}: +{kept_here}", flush=True)
        else:
            skipped["package_zero_kept"] += 1

    if not rows:
        raise SystemExit("No indexable deck chunks found")

    print(f"Embedding {len(rows)} rows…", flush=True)
    matrix = embed_texts(oai, [r["text"] for r in rows])
    index = build_faiss(matrix)
    built = write_outputs(
        args.out_dir,
        rows,
        matrix,
        index,
        input_paths=sorted(set(input_paths)),
        promote_live=args.promote_live,
    )
    manifest = built["manifest"]
    manifest["counts"]["packages_used"] = len(packages_used)
    manifest["counts"]["skipped"] = dict(skipped)
    manifest["packages"] = packages_used
    (args.out_dir / VERSIONED_NAMES["manifest"]).write_text(json.dumps(manifest, indent=2) + "\n")

    smoke = None
    if not args.skip_smoke:
        print("Local retrieval smoke…", flush=True)
        smoke = local_smoke(index, matrix, rows, oai)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.audit_dir.mkdir(parents=True, exist_ok=True)
    audit = {
        "schema_version": "lecture_vector_deck_packages_build_audit.v0_1",
        "created_at_utc": utc_now(),
        "input_paths": manifest["input_paths"][:50],
        "input_path_count": len(manifest["input_paths"]),
        "output_paths": list(built["paths"].values()),
        "counts": {
            "packages_scanned": len(package_ids),
            "packages_used": len(packages_used),
            "rows_indexed": len(rows),
            "skipped": dict(skipped),
            "distinct_video_ids": manifest["counts"]["distinct_video_ids"],
            "rows_with_video_time_url": manifest["counts"]["rows_with_video_time_url"],
        },
        "gcs_outputs": manifest["gcs_outputs"],
        "promote_live": args.promote_live,
        "local_smoke": smoke,
        "known_limitations": manifest["known_limitations"],
    }

    uploaded = []
    backups = []
    if args.upload:
        print("Uploading versioned artifacts…", flush=True)
        for key, fname in VERSIONED_NAMES.items():
            uri = f"gs://pathology_hub/{VERSIONED_PREFIX}{fname}"
            upload_file(gcs, args.out_dir / fname, uri)
            uploaded.append(uri)
            print("  ", uri, flush=True)
        if args.promote_live:
            print("Backing up live STRICT_CYTO_v9…", flush=True)
            backups = backup_live(gcs, stamp)
            print("Promoting to live STRICT_CYTO_v9 paths…", flush=True)
            uploaded.extend(promote_to_live(gcs, args.out_dir))
            # rewrite manifest api_exposed note
            live_man_path = args.out_dir / VERSIONED_NAMES["manifest"]
            man = json.loads(live_man_path.read_text())
            man["api_exposed"] = False
            man["api_expose_note"] = (
                "Artifacts promoted to STRICT_CYTO_v9 GCS paths; Cloud Run must "
                "cold-start or new revision to download (pod local cache)."
            )
            man["backup_gcs"] = backups
            live_man_path.write_text(json.dumps(man, indent=2) + "\n")
            # re-upload updated manifests
            upload_file(gcs, live_man_path, f"gs://pathology_hub/{VERSIONED_PREFIX}{VERSIONED_NAMES['manifest']}")
            upload_file(gcs, live_man_path, f"gs://pathology_hub/{LIVE_PREFIX}{LIVE_NAMES['manifest']}")

        audit_gcs = f"gs://pathology_hub/06_audits/lectures/vector_deck_packages_v0_1/{stamp}/audit.json"
        audit["output_paths"].append(audit_gcs)
        audit["uploaded"] = uploaded
        audit["backups"] = backups
        audit_path = args.audit_dir / f"audit_{stamp}.json"
        audit_path.write_text(json.dumps(audit, indent=2) + "\n")
        upload_file(gcs, audit_path, audit_gcs)
        audit["audit_gcs"] = audit_gcs
        print("AUDIT", audit_gcs, flush=True)
    else:
        audit_path = args.audit_dir / f"audit_{stamp}.json"
        audit_path.write_text(json.dumps(audit, indent=2) + "\n")

    print(
        json.dumps(
            {
                "ok": True,
                "rows": len(rows),
                "packages": len(packages_used),
                "out_dir": str(args.out_dir),
                "audit": str(audit_path),
                "uploaded": len(uploaded),
                "promote_live": args.promote_live,
                "smoke_top": (smoke or {}).get("queries", [{}])[0] if smoke else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
