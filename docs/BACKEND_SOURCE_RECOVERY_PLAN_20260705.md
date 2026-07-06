# Backend Source Recovery Plan

**Date:** 2026-07-05  
**Workstream:** Backend API  
**Status:** Recovery **incomplete** — partial local copy exists; not verified against live production

---

## Problem statement

Pathology Hub's live Cloud Run service `pathology-hub-v04` runs version **1.5.10-html-bundle** (per v0_1 live benchmark health output). The repo contains a **partial, stale** backend at `backend/pathology_hub_v04_curriculum/app.py` labeled **1.5.7-page-images-v04** (~3,200 lines, FastAPI).

Without an **authoritative match** to the running container image:

- Evidence Search Reliability v0_2 cannot be safely integrated and deployed
- Tag-aware runtime (SQLite tag index, browse modes) cannot be implemented against known dispatch code
- Journal RRF/fusion debugging (Virchows FTS-only issue) cannot proceed
- Dockerfile in repo copies only `app.py` — production image may differ

Handoff docs explicitly list step 1 as: *"Pull/recover current backend source for pathology-hub-v04"* (`docs/00_MASTER_HANDOFF_FOR_CODEX.md`).

---

## Known live services

| Service | Region | URL | Role |
|---------|--------|-----|------|
| `pathology-hub-v04` | `us-central1` | `https://pathology-hub-v04-vorn5q2kga-uc.a.run.app` | **Production** Evidence RAG API |
| `pathology-hub-v04-curriculum-staging` | `us-central1` (assumed) | `https://pathology-hub-v04-curriculum-staging-vorn5q2kga-uc.a.run.app` | Staging for curriculum-map experiments (OpenAPI v1.5.9 draft) |

### Live service facts (from handoffs + benchmark — refresh with read-only script)

| Field | Documented value |
|-------|------------------|
| Revision (2026-06-29 handoff) | `pathology-hub-v04-00014-mbj` |
| Version (2026-06-29) | `1.5.8-pathout-lecture-tags-v04` |
| Version (2026-07-05 benchmark) | `1.5.10-html-bundle` |
| Endpoint | `POST /evidence/search`, `GET /health` |
| Auth | `X-API-Key` header |
| GCP project | `pathology-annotation-project` |

---

## Known staging services

- **`pathology-hub-v04-curriculum-staging`** — referenced in `openapi_pathology_hub_unified_searchEvidence_v1_5_9_curriculum.yaml` for Curriculum Map v0.2 extension draft.
- v0_2 executive summary states: **no evidence-search staging service with v0_2 deployed** — staging exists for curriculum work, not validated for reliability patch.

Do **not** assume staging mirrors production artifact versions without health/manifest comparison.

---

## What GCS search proved

Read-only GCS inventory (`audits/gcs_inventory/20260704T175703Z/`) confirmed:

| Finding | Implication |
|---------|-------------|
| `gs://pathology_hub/06_audits/backend_api/` exists | Backend deployment audits may contain image/build metadata |
| `gs://pathology_hub/99_backups/backend_api/` exists | Prior backend snapshots may exist as tarballs or manifests |
| `gs://pathology_hub/04_api_artifacts/` has OpenAPI v1.5.1–v1.5.4 YAML | API contract history; not application source |
| `gs://pathology_hub/gcloud/` prefix exists | May contain build tmp artifacts — inspect read-only |
| No `backend/` or `app.py` at bucket root | **Application source is not stored as plain GCS objects at top level** |
| Vector/docstore/manifest paths confirmed | Data plane artifacts exist; code plane does not |

GCS inventory is **prefix listing only** (level 1–2); it does not recursively enumerate `06_audits/backend_api/` contents. Deep listing required.

### What GCS did **not** prove

- Complete recoverable Python source tree for 1.5.10
- That local `backend/pathology_hub_v04_curriculum/app.py` matches any deployed revision
- Cloud Build trigger configuration or CI pipeline location

---

## Why backend source is still the blocker

1. **Version skew:** Local 1.5.7 vs live 1.5.10-html-bundle — at least three minor releases of unknown diffs (html bundle, journal union, figure proxy changes).
2. **Deploy dependency:** v0_2 patch must hook into `/evidence/search` **before** per-source dispatch; integration point unknown without current handler code.
3. **Debug dependency:** Journal Virchows retrieval issue requires inspecting live RRF/fusion — cannot trust 1.5.7 code path.
4. **Dockerfile minimalism:** Repo Dockerfile copies single `app.py`; production may use multi-file layout or different entrypoint.
5. **No recovery audit on record:** No manifest in repo proving image digest ↔ source tree SHA256 match.

---

## Recovery paths (in priority order)

### Path A — Cloud Run revision image extract (recommended first)

Extract filesystem from the **currently serving** revision image without deploying anything.

### Path B — Artifact Registry image history

List images tagged for `pathology-hub-v04`; pull digest matching live revision.

### Path C — Cloud Build history

Find build that produced the live image; recover source from build logs / stored source tarball.

### Path D — GCS backend_api backups

List and inspect `gs://pathology_hub/99_backups/backend_api/` and `gs://pathology_hub/06_audits/backend_api/`.

### Path E — Reconstruct from handoff reference patch

Use `codex_local/tag_search_backend_patch_v1_6_1_REFERENCE.py` and partial `app.py` as scaffold — **last resort**; requires full regression proof.

---

## Exact commands to run (read-only unless noted)

Set context once:

```bash
export PROJECT=pathology-annotation-project
export REGION=us-central1
export SERVICE=pathology-hub-v04
export AUDIT_DIR="audits/backend_source_recovery/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$AUDIT_DIR"
```

Or run the bundled script: `bash commands/read_only_cloudrun_source_recovery.sh`

### 1. Cloud Run service and revision metadata

```bash
gcloud run services describe "$SERVICE" \
  --project="$PROJECT" --region="$REGION" \
  --format=json > "$AUDIT_DIR/service.describe.json"

gcloud run revisions list \
  --service="$SERVICE" --project="$PROJECT" --region="$REGION" \
  --format='table(name,active,creationTimestamp,imageDigest)' \
  > "$AUDIT_DIR/revisions.list.txt"

# Replace REVISION with active revision name from above
gcloud run revisions describe REVISION \
  --project="$PROJECT" --region="$REGION" \
  --format=json > "$AUDIT_DIR/revision.active.describe.json"
```

### 2. Extract image reference

```bash
IMAGE=$(gcloud run revisions describe REVISION \
  --project="$PROJECT" --region="$REGION" \
  --format='value(spec.containers[0].image)')

echo "$IMAGE" > "$AUDIT_DIR/image.uri.txt"
```

### 3. Artifact Registry metadata (read-only)

```bash
gcloud artifacts docker images list us-central1-docker.pkg.dev/$PROJECT/pathology-hub \
  --include-tags \
  --format='table(IMAGE,TAGS,CREATE_TIME,UPDATE_TIME)' \
  > "$AUDIT_DIR/artifact_registry.images.txt" 2>&1

gcloud artifacts docker images describe "$IMAGE" \
  --format=json > "$AUDIT_DIR/image.describe.json" 2>&1
```

### 4. Cloud Build history (read-only)

```bash
gcloud builds list --project="$PROJECT" --limit=50 \
  --format='table(id,status,createTime,source.storageSource.bucket,images)' \
  > "$AUDIT_DIR/cloudbuild.list.txt"

# If build ID found for pathology-hub-v04 image:
gcloud builds describe BUILD_ID --project="$PROJECT" \
  --format=json > "$AUDIT_DIR/cloudbuild.describe.json"
```

### 5. GCS backend_api audit paths (read-only)

```bash
gcloud storage ls -l "gs://pathology_hub/06_audits/backend_api/**" \
  > "$AUDIT_DIR/gcs.backend_api_audits.ls.txt" 2>&1

gcloud storage ls -l "gs://pathology_hub/99_backups/backend_api/**" \
  > "$AUDIT_DIR/gcs.backend_api_backups.ls.txt" 2>&1
```

### 6. Image filesystem extract (local disk only — not a deploy)

Requires Docker and permission to pull from Artifact Registry:

```bash
docker pull "$IMAGE"
CID=$(docker create "$IMAGE")
docker export "$CID" | tar -t > "$AUDIT_DIR/image.filelist.txt"
docker cp "$CID:/app" "$AUDIT_DIR/extracted_app/" 2>/dev/null || true
docker rm "$CID"
```

**Do not** push images or update Cloud Run from this step.

### 7. Staging service compare (read-only)

```bash
gcloud run services describe pathology-hub-v04-curriculum-staging \
  --project="$PROJECT" --region="$REGION" \
  --format=json > "$AUDIT_DIR/staging.service.describe.json" 2>&1
```

### 8. Optional: Cloud Run logs sample (read-only, no secrets)

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="'$SERVICE'"' \
  --project="$PROJECT" --limit=20 --format=json \
  > "$AUDIT_DIR/logs.sample.json" 2>&1
```

Filter logs before sharing — exclude lines containing API keys or tokens.

---

## What evidence counts as "source recovered"

Recovery is **complete** when all of the following are true and recorded in an audit JSON:

| Criterion | Evidence artifact |
|-----------|-------------------|
| Live revision identified | `revision.active.describe.json` with active traffic |
| Image digest captured | `image.uri.txt` + `image.describe.json` |
| Application tree extracted | `extracted_app/` or equivalent with `app.py` (or main module) |
| Version string matches live | Extracted `APP_VERSION` or health `service_version` equals **1.5.10-html-bundle** (or documented live value) |
| SHA256 manifest of source files | `source.sha256manifest.json` in audit dir |
| Diff against repo copy documented | `diff.repo_vs_extracted.txt` — explain every intentional delta |
| Requirements lockfile present | `requirements.txt` matching image pip freeze or container metadata |
| Dockerfile/build recipe recovered | From Cloud Build describe or image labels |
| Smoke test passes locally | `codex_local/api_smoke_test.py` against **local uvicorn** of recovered source (optional but strong) |

Recovery is **partial** if:

- Only older `app.py` (1.5.7) available — **current repo state**
- Image pulled but version mismatch with production health
- Single-file extract without provenance chain

Recovery is **failed** if:

- No image pull access and no GCS backup contains source
- Extracted code cannot start or fails smoke tests against same GCS artifact paths as production

---

## Current repo state (honest assessment)

| Item | Path | Status |
|------|------|--------|
| Partial app | `backend/pathology_hub_v04_curriculum/app.py` | Present — **1.5.7**, not verified |
| Dockerfile | `backend/pathology_hub_v04_curriculum/Dockerfile` | Present — minimal single-file |
| v0_2 module | `backend/evidence_search_reliability_v0_2/` | Present — not wired to live |
| v0_2 patch stub | `backend/pathology_hub_v04_curriculum/evidence_search_v0_2_patch.py` | Present — integration docs only |
| Reference tag patch | `project_sources/.../codex_local/tag_search_backend_patch_v1_6_1_REFERENCE.py` | Reference — not production |

**Verdict:** Backend source is **not recovered** in the authoritative sense required for production deploy.

---

## Safety rules

- Read-only gcloud/list/describe/logs only until explicit deploy approval
- Never print Secret Manager values or API keys in audit outputs
- Do not `gcloud run deploy`, `update`, or `update-traffic` from recovery workflow
- Do not mutate GCS objects during recovery
- Store audits under `audits/backend_source_recovery/<timestamp>/`

---

## Next step after recovery

1. Merge v0_2 integration into recovered `app.py` at correct hook point
2. Update Dockerfile to COPY `evidence_search_reliability_v0_2/` and rules JSON
3. Build and deploy to **staging only**
4. Run `commands/run_v0_2_staging_validation.sh`

See `docs/NEXT_10_ENGINEERING_TICKETS_20260705.md` ticket #1.
