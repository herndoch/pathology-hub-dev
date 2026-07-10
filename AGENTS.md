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
`tools/curriculum_provenance_browser/requirements.txt` + `pytest`.

**Easiest path (no virtualenv knowledge needed):** use `./scripts/dev.sh` — it always runs
the right `.venv/bin/python` for you. Commands: `setup`, `test`, `test-v02`, `check`, `browser`, `api`.

There is no configured linter; use `./scripts/dev.sh check` (compileall) as a syntax check.

### Tests (`pytest`, `testpaths = tests`)
- Run with `./scripts/dev.sh test` or `.venv/bin/python -m pytest`.
- Data-dependent, not present in git (gitignored generated artifacts): `tests/test_curriculum_provenance_browser.py`
  skips unless `outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_1.sqlite` exists;
  `tests/test_evidence_v0_2_regression_gate.py::test_v0_1_benchmark_regression_still_passes` fails without
  the gitignored `06_audits/evidence_retrieval_writable/benchmark_v0_1/` package (49 other tests pass).

### Services
- Backend Evidence API (`backend/pathology_hub_v04_curriculum/`, also `..._live_recovered/`): run
  via `./scripts/dev.sh api` or from its dir with `.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8080`.
  It boots offline (startup swallows GCS credential errors) and serves `/openapi.json`, but `/health` and `/evidence/search` (the `searchEvidence` action) download FAISS/
  SQLite indexes from `gs://pathology_hub` and embed queries via OpenAI, so they HANG/fail without
  GCS ADC creds + `OPENAI_API_KEY` + `PATHOLOGY_HUB_API_KEY` + network. Real evidence search cannot
  be exercised in a credential-less cloud VM.
- Curriculum Provenance Browser (`tools/curriculum_provenance_browser/`): fully offline read-only
  FastAPI UI on port 8765 via `./scripts/dev.sh browser`. Requires a SQLite index at
  `CURRICULUM_LOCATOR_SQLITE`; the default path is a gitignored generated artifact not in the repo.
