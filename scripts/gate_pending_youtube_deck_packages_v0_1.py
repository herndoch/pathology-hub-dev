#!/usr/bin/env python3
"""Scan GCS for live YouTube deck packages with empty/missing chunks_indexable and gate them.

Skips remastered family prefixes (yt_skin_, yt_gi_, yt_cyto_) which were batch-gated
from content_library. Intended for Colab-uploaded live YouTube packages (Cipriani /
Gardner / Damron pattern).

Example:
  python scripts/gate_pending_youtube_deck_packages_v0_1.py \\
    --leaf-dir-map BST=outputs/bst_browse_leaf_embeddings_v0_1 \\
    --leaf-dir-map Breast=outputs/breast_browse_leaf_embeddings_v0_1
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.cloud.storage import Client


SKIP_PREFIXES = ("yt_skin_", "yt_gi_", "yt_cyto_")
DECK_PREFIX = "02_normalized/lectures/deck_packages/"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_leaf_maps(items: list[str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--leaf-dir-map must be Root=path, got {item!r}")
        root, path = item.split("=", 1)
        out[root.strip()] = Path(path.strip())
    return out


def list_live_yt_package_ids(client: Client, bucket: str) -> list[str]:
    hub = client.bucket(bucket)
    ids: set[str] = set()
    for blob in hub.list_blobs(prefix=DECK_PREFIX):
        parts = blob.name.split("/")
        if len(parts) < 4:
            continue
        pid = parts[3]
        if not pid.startswith("yt_"):
            continue
        if pid.startswith(SKIP_PREFIXES):
            continue
        ids.add(pid)
    return sorted(ids)


def chunk_count(client: Client, bucket: str, package_id: str) -> int:
    blob = client.bucket(bucket).blob(f"{DECK_PREFIX}{package_id}/chunks_indexable.jsonl")
    if not blob.exists():
        return 0
    text = blob.download_as_text()
    return sum(1 for ln in text.splitlines() if ln.strip())


def read_root(client: Client, bucket: str, package_id: str) -> str | None:
    blob = client.bucket(bucket).blob(f"{DECK_PREFIX}{package_id}/manifest.json")
    if not blob.exists():
        return None
    man = json.loads(blob.download_as_text())
    root = man.get("root")
    return str(root) if root else None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hub-bucket", default="pathology_hub")
    p.add_argument(
        "--leaf-dir-map",
        action="append",
        default=[],
        help="Root=path (repeatable). Default BST→outputs/bst_browse_leaf_embeddings_v0_1",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--audit-dir", type=Path, default=Path("audits/youtube_pending_gate_v0_1"))
    args = p.parse_args()

    leaf_map = parse_leaf_maps(args.leaf_dir_map) or {
        "BST": Path("outputs/bst_browse_leaf_embeddings_v0_1"),
    }

    client = Client()
    package_ids = list_live_yt_package_ids(client, args.hub_bucket)
    pending = []
    for pid in package_ids:
        n = chunk_count(client, args.hub_bucket, pid)
        root = read_root(client, args.hub_bucket, pid) or "BST"
        if n == 0:
            pending.append({"package_id": pid, "root": root, "chunks": n})

    if args.limit:
        pending = pending[: args.limit]

    print(json.dumps({"scanned": len(package_ids), "pending": pending}, indent=2), flush=True)

    results = []
    gate_script = Path(__file__).resolve().parent / "gate_youtube_deck_package_from_gcs_v0_1.py"
    for item in pending:
        pid = item["package_id"]
        root = item["root"]
        leaf_dir = leaf_map.get(root)
        if leaf_dir is None:
            results.append({"package_id": pid, "ok": False, "error": f"no leaf-dir for root {root}"})
            continue
        if args.dry_run:
            results.append({"package_id": pid, "ok": True, "dry_run": True, "root": root, "leaf_dir": str(leaf_dir)})
            continue
        cmd = [
            sys.executable,
            str(gate_script),
            "--package-id",
            pid,
            "--root",
            root,
            "--leaf-dir",
            str(leaf_dir),
        ]
        print("+", " ".join(cmd), flush=True)
        try:
            subprocess.check_call(cmd)
            results.append({"package_id": pid, "ok": True, "root": root})
        except subprocess.CalledProcessError as exc:
            results.append({"package_id": pid, "ok": False, "root": root, "error": str(exc)})

    args.audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = args.audit_dir / f"audit_{utc_stamp()}.json"
    audit = {
        "schema_version": "youtube_pending_gate_audit.v0_1",
        "created_at_utc": utc_now(),
        "input_paths": [f"gs://{args.hub_bucket}/{DECK_PREFIX}"],
        "output_paths": [str(audit_path)],
        "counts": {
            "packages_scanned": len(package_ids),
            "pending": len(pending),
            "gated_ok": sum(1 for r in results if r.get("ok") and not r.get("dry_run")),
            "failed": sum(1 for r in results if not r.get("ok")),
        },
        "results": results,
        "known_limitations": [
            "Does not rebuild FAISS or refresh Cloud Run.",
            "Skips yt_skin_/yt_gi_/yt_cyto_ remaster prefixes.",
            "Requires matching browse leaf embeddings per root.",
        ],
    }
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
