#!/usr/bin/env python3
"""Publish Heme SH Anki builder shared inputs + docs to GCS (v0_1).

Canonical prefix:
  gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/

Writes:
  - shared SOP PDF (from local path)
  - handoff docs from repo
  - series_index.json (pointers to existing lecture ZIPs + sidecars; no re-copy)
  - audit.json
  - DROPBOX_FOR_LOCAL_UPLOADS.md (where to put TNK zip + WHO JSON)

Does NOT overwrite lecture source ZIPs or deck sidecars.
Does NOT invent TNK/WHO files — those must be uploaded from local/Drive.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import storage

PROJECT = "pathology-annotation-project"
BUCKET = "pathology_hub"
PREFIX = "02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1"

SERIES = [
    ("aggressive_b_cell", "HANDOFF_AGGRESSIVE_B_CELL_ANKI_BUILDER_v0_1.md", ["heme_sh_aggressive_b_cell_v0_1"]),
    ("aml", "HANDOFF_AML_ANKI_BUILDER_v0_1.md", ["heme_sh_aml_v0_1"]),
    ("bm_failure_syndromes", "HANDOFF_BM_FAILURE_SYNDROMES_ANKI_BUILDER_v0_1.md", ["heme_sh_bm_failure_syndromes_v0_1"]),
    ("bm_intro", "HANDOFF_BM_INTRO_ANKI_BUILDER_v0_1.md", ["heme_sh_bm_intro_v0_1"]),
    ("bm_systemic_manifestations", "HANDOFF_BM_SYSTEMIC_MANIFESTATIONS_ANKI_BUILDER_v0_1.md", ["heme_sh_bm_systemic_manifestations_v0_1"]),
    ("histiocytic", "HANDOFF_HISTIOCYTIC_ANKI_BUILDER_v0_1.md", ["heme_sh_histiocytic_v0_1"]),
    ("hodgkin_nlp", "HANDOFF_HODGKIN_NLP_ANKI_BUILDER_v0_1.md", ["heme_sh_hodgkin_nlp_v0_1"]),
    ("hodgkin_overview", "HANDOFF_HODGKIN_OVERVIEW_ANKI_BUILDER_v0_1.md", ["heme_sh_hodgkin_overview_v0_1"]),
    ("hodgkin_t_nk_cell", "HANDOFF_HODGKIN_T_NK_CELL_ANKI_BUILDER_v0_1.md", ["heme_sh_hodgkin_t_nk_cell_1_v0_1", "heme_sh_hodgkin_t_nk_cell_2_v0_1"]),
    ("ia_lpd", "HANDOFF_IA_LPD_ANKI_BUILDER_v0_1.md", ["heme_sh_ia_lpd_v0_1"]),
    ("ihc_for_lpd", "HANDOFF_IHC_FOR_LPD_ANKI_BUILDER_v0_1.md", ["heme_sh_ihc_for_lpd_v0_1"]),
    ("mds_mpn", "HANDOFF_MDS_MPN_ANKI_BUILDER_v0_1.md", ["heme_sh_mds_mpn_1_v0_1", "heme_sh_mds_mpn_2_v0_1", "heme_sh_mds_mpn_3_v0_1"]),
    ("plasma_cell", "HANDOFF_PLASMA_CELL_ANKI_BUILDER_v0_1.md", ["heme_sh_plasma_cell_v0_1"]),
    ("pt_lpd", "HANDOFF_PT_LPD_ANKI_BUILDER_v0_1.md", ["heme_sh_pt_lpd_v0_1"]),
    ("reactive_lymphoid_hyperplasia", "HANDOFF_REACTIVE_LYMPHOID_HYPERPLASIA_ANKI_BUILDER_v0_1.md", ["heme_sh_reactive_lymphoid_hyperplasia_v0_1"]),
    ("small_b_cell", "HANDOFF_SMALL_B_CELL_ANKI_BUILDER_v0_1.md", ["heme_sh_small_b_cell_1_of_2_v0_1", "heme_sh_small_b_cell_2_of_2_v0_1"]),
    ("spleen", "HANDOFF_SPLEEN_ANKI_BUILDER_v0_1.md", ["heme_sh_spleen_v0_1"]),
]

DOC_NAMES = [
    "HANDOFF_HEME_SH_ANKI_BUILDER_COMMON_v0_1.md",
    "HANDOFF_HEME_SH_ANKI_BUILDER_INDEX_v0_1.md",
    "HANDOFF_CHATGPT_HEME_ANKI_PROMPTS_v0_1.md",
] + [h for _, h, _ in SERIES]

SHARED_PENDING = [
    "Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip",
    "WHO_WHO_JSON_PROCESSED_HEME.json",
    "accepted_tags.json",
]


def upload_bytes(bucket, rel: str, data: bytes, content_type: str) -> str:
    blob = bucket.blob(f"{PREFIX}/{rel}")
    blob.upload_from_string(data, content_type=content_type)
    return f"gs://{BUCKET}/{PREFIX}/{rel}"


def upload_file(bucket, rel: str, path: Path, content_type: str) -> str:
    blob = bucket.blob(f"{PREFIX}/{rel}")
    blob.upload_from_filename(str(path), content_type=content_type)
    return f"gs://{BUCKET}/{PREFIX}/{rel}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs-dir", type=Path, default=Path("/workspace/docs"))
    ap.add_argument(
        "--sop-pdf",
        type=Path,
        default=Path(
            "/home/ubuntu/.cursor/projects/workspace/uploads/Pathology_Anki_Contextual_Cloze_SOP_2__5980.pdf"
        ),
    )
    ap.add_argument(
        "--tnk-zip",
        type=Path,
        default=None,
        help="Optional local path to TNK exemplar zip to upload into shared/",
    )
    ap.add_argument(
        "--who-json",
        type=Path,
        default=None,
        help="Optional local path to WHO_WHO_JSON_PROCESSED_HEME.json",
    )
    ap.add_argument(
        "--accepted-tags",
        type=Path,
        default=None,
        help="Optional local accepted_tags.json (else leave pending inside TNK zip)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = storage.Client(project=PROJECT)
    bucket = client.bucket(BUCKET)
    deck_prefix = "02_normalized/lectures/deck_packages"
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    outputs: list[str] = []
    missing_shared: list[str] = []

    # Series index from live manifests
    series_rows = []
    for slug, handoff, pkg_ids in SERIES:
        lectures = []
        for pid in pkg_ids:
            mblob = bucket.blob(f"{deck_prefix}/{pid}/manifest.json")
            if not mblob.exists():
                lectures.append({"package_id": pid, "error": "manifest_missing"})
                continue
            m = json.loads(mblob.download_as_text())
            video = m.get("video_file_declared") or ""
            stem = video.replace(".mp4", "") if video.endswith(".mp4") else pid
            # Prefer known zip naming
            zip_candidates = [
                f"{stem}_package.zip",
                f"{stem}_chatgpt_readable_package.zip",
            ]
            zip_uri = None
            for zname in zip_candidates:
                if bucket.blob(zname).exists():
                    zip_uri = f"gs://{BUCKET}/{zname}"
                    break
            counts = m.get("counts") or {}
            lectures.append(
                {
                    "package_id": pid,
                    "title": m.get("title"),
                    "lecture_zip_gcs_uri": zip_uri,
                    "sidecar_prefix": f"gs://{BUCKET}/{deck_prefix}/{pid}/",
                    "sidecar_files": {
                        "manifest": f"gs://{BUCKET}/{deck_prefix}/{pid}/manifest.json",
                        "frames": f"gs://{BUCKET}/{deck_prefix}/{pid}/frames.jsonl",
                        "segments": f"gs://{BUCKET}/{deck_prefix}/{pid}/segments.jsonl",
                        "chunks_indexable": f"gs://{BUCKET}/{deck_prefix}/{pid}/chunks_indexable.jsonl",
                    },
                    "do_not_use_for_builder": [
                        f"gs://{BUCKET}/{deck_prefix}/{pid}/tag_audit.json",
                        f"gs://{BUCKET}/{deck_prefix}/{pid}/chunk_audit.json",
                        f"gs://{BUCKET}/{deck_prefix}/{pid}/audit.json",
                    ],
                    "counts": {
                        "segments": counts.get("segments") or counts.get("segments_total"),
                        "frames": counts.get("frames") or counts.get("frames_total"),
                        "chunks_indexable": counts.get("chunks_indexable"),
                    },
                }
            )
        series_rows.append(
            {
                "slug": slug,
                "handoff_md": f"gs://{BUCKET}/{PREFIX}/docs/{handoff}",
                "lectures": lectures,
            }
        )

    series_index = {
        "schema_version": "heme_anki_builder_series_index.v0_1",
        "created_at_utc": created_at,
        "builder_prefix": f"gs://{BUCKET}/{PREFIX}/",
        "shared": {
            "sop_pdf": f"gs://{BUCKET}/{PREFIX}/shared/Pathology_Anki_Contextual_Cloze_SOP_v1_1.pdf",
            "tnk_exemplar_zip": f"gs://{BUCKET}/{PREFIX}/shared/Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip",
            "who_heme_json": f"gs://{BUCKET}/{PREFIX}/shared/WHO_WHO_JSON_PROCESSED_HEME.json",
            "accepted_tags_json": f"gs://{BUCKET}/{PREFIX}/shared/accepted_tags.json",
        },
        "series": series_rows,
        "known_limitations": [
            "Lecture ZIP + sidecar objects remain at their existing GCS URIs; this index points to them and does not duplicate payloads.",
            "TNK exemplar zip / WHO heme JSON / extracted accepted_tags.json may be pending until local upload.",
            "chunks_indexable is navigation only; survey lectures (e.g. BM Intro) may have zero gated chunks and remain high-yield.",
        ],
    }

    dropbox = """# Drop local Anki builder authority files here

Canonical shared prefix:
`gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/shared/`

## Upload from your machine

```bash
# Style authority (required)
gsutil cp /path/to/Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip \\
  gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/shared/

# WHO entity canon (required)
gsutil cp /path/to/WHO_WHO_JSON_PROCESSED_HEME.json \\
  gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/shared/

# Optional: extract accepted_tags.json from the TNK zip and place beside it
gsutil cp /path/to/accepted_tags.json \\
  gs://pathology_hub/02_normalized/anki/heme_sh_contextual_cloze_builder_v0_1/shared/
```

Or re-run:

```bash
python3 scripts/publish_heme_anki_builder_gcs_bundle_v0_1.py \\
  --tnk-zip /path/to/Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip \\
  --who-json /path/to/WHO_WHO_JSON_PROCESSED_HEME.json \\
  --accepted-tags /path/to/accepted_tags.json
```

Do **not** upload `tag_audit.json` / `chunk_audit.json` / lecture `audit.json` into this shared folder.
"""

    readme = f"""# Heme SH Contextual Cloze Anki — builder inputs (v0_1)

Published: {created_at}

## Layout

- `shared/` — TNK exemplar, SOP PDF, WHO heme JSON, accepted tags
- `docs/` — handoff markdown (COMMON, INDEX, ChatGPT prompts, per-series)
- `series_index.json` — pointers to existing lecture ZIPs + sidecars
- `audit.json` — publish audit
- `DROPBOX_FOR_LOCAL_UPLOADS.md` — how to land TNK/WHO from your laptop

## ChatGPT usage

1. `@github herndoch/pathology-hub-dev` → open `docs/HANDOFF_CHATGPT_HEME_ANKI_PROMPTS_v0_1.md`
2. Or download shared + one series zip/sidecars using `series_index.json`
3. Never use sidecar tag/chunk audits as tag authority
"""

    if args.dry_run:
        print(json.dumps(series_index, indent=2)[:4000])
        print("dry-run: would upload SOP, docs, series_index, audit")
        return

    # SOP
    if args.sop_pdf.exists():
        outputs.append(
            upload_file(
                bucket,
                "shared/Pathology_Anki_Contextual_Cloze_SOP_v1_1.pdf",
                args.sop_pdf,
                "application/pdf",
            )
        )
    else:
        missing_shared.append("Pathology_Anki_Contextual_Cloze_SOP_v1_1.pdf")

    # Optional authority files
    if args.tnk_zip and args.tnk_zip.exists():
        outputs.append(
            upload_file(
                bucket,
                "shared/Heme_SH_TNK_Lymphomas_Contextual_Cloze_Final_Package.zip",
                args.tnk_zip,
                "application/zip",
            )
        )
    else:
        missing_shared.append(SHARED_PENDING[0])

    if args.who_json and args.who_json.exists():
        outputs.append(
            upload_file(
                bucket,
                "shared/WHO_WHO_JSON_PROCESSED_HEME.json",
                args.who_json,
                "application/json",
            )
        )
    else:
        missing_shared.append(SHARED_PENDING[1])

    if args.accepted_tags and args.accepted_tags.exists():
        outputs.append(
            upload_file(
                bucket,
                "shared/accepted_tags.json",
                args.accepted_tags,
                "application/json",
            )
        )
    else:
        missing_shared.append(SHARED_PENDING[2])

    # Docs
    for name in DOC_NAMES:
        path = args.docs_dir / name
        if not path.exists():
            raise SystemExit(f"missing doc: {path}")
        outputs.append(upload_file(bucket, f"docs/{name}", path, "text/markdown; charset=utf-8"))

    outputs.append(
        upload_bytes(
            bucket,
            "series_index.json",
            json.dumps(series_index, indent=2).encode("utf-8"),
            "application/json",
        )
    )
    outputs.append(upload_bytes(bucket, "README.md", readme.encode("utf-8"), "text/markdown; charset=utf-8"))
    outputs.append(
        upload_bytes(
            bucket,
            "DROPBOX_FOR_LOCAL_UPLOADS.md",
            dropbox.encode("utf-8"),
            "text/markdown; charset=utf-8",
        )
    )

    audit = {
        "schema_version": "heme_anki_builder_gcs_publish_audit.v0_1",
        "created_at_utc": created_at,
        "gcp_project": PROJECT,
        "input_paths": [
            str(args.docs_dir),
            str(args.sop_pdf) if args.sop_pdf else None,
            str(args.tnk_zip) if args.tnk_zip else None,
            str(args.who_json) if args.who_json else None,
            f"gs://{BUCKET}/{deck_prefix}/heme_sh_*_v0_1/",
        ],
        "output_paths": [f"gs://{BUCKET}/{PREFIX}/"],
        "counts": {
            "docs_uploaded": len(DOC_NAMES),
            "series": len(SERIES),
            "objects_written": len(outputs),
            "shared_pending": len(missing_shared),
        },
        "uploaded_objects": outputs,
        "shared_pending": missing_shared,
        "known_limitations": series_index["known_limitations"]
        + [
            "Until TNK zip + WHO JSON are uploaded, ChatGPT still needs those files from Drive/local.",
            "Public-read ACLs are NOT set by this script; use signed URLs or project IAM as needed.",
        ],
    }
    outputs.append(
        upload_bytes(
            bucket,
            "audit.json",
            json.dumps(audit, indent=2).encode("utf-8"),
            "application/json",
        )
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mirror = bucket.blob(f"06_audits/anki/heme_sh_contextual_cloze_builder_v0_1/audit_{ts}.json")
    mirror.upload_from_string(json.dumps(audit, indent=2), content_type="application/json")
    print(json.dumps(audit, indent=2))
    print(f"\nMIRROR: gs://{BUCKET}/{mirror.name}")


if __name__ == "__main__":
    main()
