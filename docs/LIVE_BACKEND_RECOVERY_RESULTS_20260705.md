# Live Backend Recovery Results — 2026-07-05

**Verdict: RECOVERED (not reconstructed). High confidence.**

## Method (Path A/B/C from `docs/BACKEND_SOURCE_RECOVERY_PLAN_20260705.md`)

1. Read the currently-serving Cloud Run revision of `pathology-hub-v04`:
   - Active/latest-ready revision: `pathology-hub-v04-00027-tjm`
   - Image: `us-central1-docker.pkg.dev/pathology-annotation-project/pathology-hub/pathology-hub-v04:staging-html-v1-5-10-20260704-r3`
   - Image digest: `sha256:1d7480629887c8150d40c6de8115c9e48197908759c7fc70ef32e35112a88019`
2. Listed Cloud Build history (`gcloud builds list --limit=200`) and filtered for builds whose pushed image matches the tag/digest above.
3. Found exact match: build `8cd07783-a403-4cc7-a276-0c2b41c5ca37` (status SUCCESS, created `2026-07-05T01:12:37Z`), whose `results.images[0].digest` is **byte-for-byte identical** to the production image digest, and whose pushed tag is the exact `staging-html-v1-5-10-20260704-r3` tag currently serving 100% of production traffic.
4. That build's `source.storageSource` pointed at `gs://pathology-annotation-project_cloudbuild/source/1783213953.082741-022523da066d4db4970f9cc151a3ff94.tgz` — a Cloud Build source-upload tarball (read-only `gcloud storage cp`, no deploy, no mutation).
5. Downloaded and extracted the tarball to `recovered_backend/v04_10_live_source/`: `app.py` (3202 lines), `Dockerfile`, `requirements.txt`, `.dockerignore`.

## Verification of match

| Check | Result |
|---|---|
| Image digest of build output vs. production `service.describe.json` | **Exact match** |
| Extracted `app.py` version constant chain terminal value | `APP_VERSION_V1510 = "1.5.10-html-bundle"` (line 2718) |
| Live `/health` call (this session) | `"version": "1.5.10-html-bundle"`, `"schema_version": "pathology_hub_health.v1.5.10"`, HTTP 200 |
| `HTML_BUNDLE_VERSION` constant in source | `"v1.5.10"` — matches health `html_bundle_version` field |
| Dockerfile in tarball | Single-file `COPY app.py .` — matches production Cloud Run behavior (no multi-file layout) |

**This is the actual production source, recovered directly from Cloud Build's source-upload archive for the exact build that produced the currently-running image — not a reconstruction from metadata/behavior.** Confidence: high. The only residual uncertainty is that Cloud Build source archives can in principle be re-used/reused across builds without content change, but the digest match plus internal version-string match plus HTML bundle constant match provide three independent confirmations.

## Structure of recovered `app.py`

Single-file FastAPI app that has been incrementally patched in place through many version bumps (visible via sequential `APP_VERSION_*` constants and route re-registration blocks):

| Version tag | Feature added |
|---|---|
| 1.5.3 | Base health + evidence search |
| 1.5.5 | Route re-registration (health/evidence v2) |
| 1.5.6-source-locator-v04 | Source locator registry |
| 1.5.7-page-images-v04 | Page image locator |
| 1.5.8-pathout-lecture-tags-v04 | PathOut + lecture governed tags |
| 1.5.9-curriculum-map-v02 | Curriculum Map v0.2 as `source="curriculum"` on the same `searchEvidence` action (no new GPT Action) |
| 1.5.10-html-bundle | HTML bundle generation (`render_html`, `html_profile`, teaching_page/gallery/evidence_packet) |

Each version block ends by reassigning `base["version"]` and re-registering the `/health` and `/evidence/search` routes with FastAPI's `app.routes` manipulation (last-registered route wins), which is why the file grows monotonically rather than being refactored.

## Comparison to `backend/pathology_hub_v04_curriculum/app.py` (repo's stale copy)

The repo's stale copy is **1.5.7-page-images-v04** (2263 lines) — it stops before the 1.5.8/1.5.9/1.5.10 blocks entirely. It is missing:
- PathOut + lecture governed-tag dispatch (1.5.8)
- Curriculum Map v0.2 source (1.5.9)
- HTML bundle generation (1.5.10)
- A resilience fix in textbook vector search (try/except around `vector_search_pool` with graceful FTS-only fallback + explicit warning) that IS present in the recovered 1.5.10 source but NOT in the stale 1.5.7 copy.

See `docs/LIVE_BACKEND_VS_LOCAL_1_5_7_RECONCILIATION_REPORT.md` for the full diff-based reconciliation.

## Also inspected (read-only)

- `pathology-hub-v04-curriculum-staging` — separate Cloud Run service, exists, describe captured to `audits/prod_snapshot_pre_v0_2_20260705/`.
- Full service list in project: `pathology-hub`, `pathology-hub-journal-api`, `pathology-hub-pathout-api`, `pathology-hub-rag-v1-staging`, `pathology-hub-v04`, `pathology-hub-v04-curriculum-staging`, `pathology-hub-v04-html-staging`. Only `pathology-hub-v04` is the production GPT Action backend per canonical rules; others are inspected read-only for context and not modified.

## Files produced this phase

- `recovered_backend/v04_10_live_source/source.tgz`, extracted `app.py`, `Dockerfile`, `requirements.txt`
- `docs/LIVE_BACKEND_RECOVERY_RESULTS_20260705.md` (this file)
- `docs/LIVE_RUNTIME_AND_CLOUDRUN_MAP_20260705.md`
- `docs/LIVE_VERSION_VERIFICATION_20260705.md`
- `recovered_source_inventory_20260705.txt`
