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

Python 3.12. The startup update script creates a `.venv` at the repo root and installs
`backend/pathology_hub_v04_curriculum/requirements.txt` +
`tools/curriculum_provenance_browser/requirements.txt` + `pytest`. Run everything with
`.venv/bin/python`. There is no configured linter; use `.venv/bin/python -m compileall backend tools scripts tests` as a syntax check.

### Tests (`pytest`, `testpaths = tests`)
- Non-obvious gotcha: running the whole suite in one process (`pytest`) FAILS with cross-file
  `sys.path` pollution. `tests/test_curriculum_provenance_browser.py` `setUpClass` calls
  `load_app_module()` (which does `sys.path.insert(0, browser_dir)`) BEFORE its skip check, so the
  browser's `app.py` then shadows the backend `app` module for every later test, causing
  `AttributeError: module 'app' has no attribute 'EvidenceSearchRequest'`. Run tests per-file for
  reliable results, e.g. `for f in tests/test_*.py; do .venv/bin/python -m pytest "$f"; done`. Each
  file passes on its own. (This is a pre-existing test-isolation issue, not an env problem.)
- Data-dependent, not present in git (both gitignored generated artifacts, expected to skip/fail
  locally without the data): `tests/test_curriculum_provenance_browser.py` skips unless
  `outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_1.sqlite` exists;
  `tests/test_evidence_v0_2_regression_gate.py::test_v0_1_benchmark_regression_still_passes` needs
  the gitignored `06_audits/evidence_retrieval_writable/benchmark_v0_1/` benchmark package.

### Services
- Backend Evidence API (`backend/pathology_hub_v04_curriculum/`, also `..._live_recovered/`): run
  from its dir with `.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8080`. It BOOTS
  offline (the `startup` event swallows the GCS "default credentials not found" errors) and serves
  `/openapi.json`. But `/health` and `/evidence/search` (the `searchEvidence` action) download FAISS/
  SQLite indexes from `gs://pathology_hub` and embed queries via OpenAI, so they HANG/fail without
  GCS ADC creds + `OPENAI_API_KEY` + `PATHOLOGY_HUB_API_KEY` + network. Real evidence search cannot
  be exercised in a credential-less cloud VM.
- Curriculum Provenance Browser (`tools/curriculum_provenance_browser/`): fully offline read-only
  FastAPI UI on port 8765 via `bash tools/curriculum_provenance_browser/scripts/run_local.sh`. It
  requires a SQLite index at `CURRICULUM_LOCATOR_SQLITE`; the default
  `outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_2.sqlite` is a gitignored
  generated artifact and is NOT in the repo, so `run_local.sh` exits early with "Missing SQLite
  index" until you point `CURRICULUM_LOCATOR_SQLITE` at an existing index file.
