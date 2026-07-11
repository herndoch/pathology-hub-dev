# Pathology Hub local dev instructions

Treat CURRENT_MASTER_SPINE as canonical.

Canonical GCP project:
- pathology-annotation-project

Canonical buckets:
- gs://pathology_hub
- gs://pathology-hub-0 legacy/source

Keep separate:
- source files in GCS
- staged/normalized data
- chunked data
- vectorized/searchable indexes
- API-exposed capabilities

Do not overwrite original normalized records.
Write sidecars, enriched outputs, manifests, and audits.

Keep workstreams separate:
- Evidence RAG
- report-style RAG
- gross template generation
- HTML rendering
- backend API
- Custom GPT frontend

Do not claim a source is indexed, vectorized, tagged, or API-exposed unless an audit, manifest, health check, or project source proves it.

Before uploading to GCS:
- produce an audit JSON
- include schema_version
- include input paths
- include output paths
- include counts
- include known limitations

## Cursor Cloud specific instructions

Python 3.12 with a `.venv` at repo root; deps come from `backend/pathology_hub_v04_live_recovered/requirements.txt` (plus `pytest`). No linter is configured.

Services (all FastAPI/uvicorn; no Node, no DB, no docker-compose):
- Canonical backend Evidence API: `backend/pathology_hub_v04_live_recovered/` — run it, not the near-duplicate `pathology_hub_v04_curriculum`. Start with `cd backend/pathology_hub_v04_live_recovered && /workspace/.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8080`. Set `EVIDENCE_V0_2_ENABLED=true` to exercise the v0_2 reliability layer (query expansion, WHO rerank).
- Curriculum provenance browser (optional): `tools/curriculum_provenance_browser/` via `bash scripts/run_local.sh`. It requires `outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_2.sqlite` (lives in GCS, not in this mirror); without it the service exits and its tests skip.

Cloud-dependency caveats (this env has no gcloud/ADC/OpenAI creds):
- The backend still boots and serves 200s. `startup_event` swallows GCS errors, GCS env vars are unset (so `ensure_artifacts()` no-ops), and `PATHOLOGY_HUB_API_KEY` is empty so `X-API-Key` auth is disabled locally.
- `POST /evidence/search` returns 200 but `source_status` is `error`/`error_no_upstream` and `warnings` include a `DefaultCredentialsError`. This is expected graceful degradation. The v0_2 query-expansion product logic still runs (e.g. `LCIS` -> `LCIS lobular carcinoma in situ`). Real retrieval needs GCS ADC (`gs://pathology_hub`, `gs://pathology-hub-0`), `OPENAI_API_KEY`, and `PATHOLOGY_HUB_API_KEY`.
- `/health` takes ~12s per call without GCS creds (credential resolution/retry) but returns 200 — do not set a tight health-check timeout.

Full end-to-end retrieval (real WHO/textbook/journal/pathout/lecture results): the three secrets (`OPENAI_API_KEY`, `PATHOLOGY_HUB_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`) are injected only into a NEW cloud VM at boot — not into an already-running session. On a fresh run, start the backend with `bash scripts/run_backend_local.sh` (add `DRY_RUN=1` to preview env wiring). That helper writes `GOOGLE_APPLICATION_CREDENTIALS_JSON` to an ADC file, exports `GOOGLE_APPLICATION_CREDENTIALS`, and derives the non-secret GCS artifact path env vars (`TEXTBOOK_*_GCS`, `JOURNAL_*_GCS`, `PATHOUT_*`, `LECTURE_*`, `HTML_BUNDLE_GCS_PREFIX`, ...) from the canonical Cloud Run descriptor `audits/prod_deploy_20260706/upload_package/preflight/service.describe.json` (the source of truth for backend env config). First boot downloads ~2.8 GB of SQLite/FAISS indexes from `gs://pathology_hub` into `/tmp` and loads FAISS into memory (production runs this with ~12Gi RAM), so expect a slow first startup and high memory use.

Tests: run per-file, or exclude the browser test. A full `pytest` run fails with `module 'app' has no attribute 'EvidenceSearchRequest'` because three `app.py` files (two backends + the browser) share the module name `app` on `sys.path`. Reliable backend run: `pytest --ignore=tests/test_curriculum_provenance_browser.py`, and run `tests/test_curriculum_provenance_browser.py` separately. `test_evidence_v0_2_regression_gate::test_v0_1_benchmark_regression_still_passes` shells out to `06_audits/` benchmark data absent from this mirror, so it fails/skips as an expected data limitation.
