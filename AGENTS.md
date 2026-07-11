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

Python-only repo (pip). The startup update script provisions a virtualenv at `.venv/`
(gitignored) with the backend deps + `pytest`. `python3.12-venv` (system pkg) is required
to create the venv. Use `.venv/bin/python` / `.venv/bin/pytest` for all commands below.

Services:
- Backend "Unified Evidence API" (`backend/pathology_hub_v04_live_recovered/`) — the core
  product; a FastAPI app whose one product endpoint is `POST /evidence/search`
  (`operationId searchEvidence`) plus `GET /health`. Prefer this dir; the
  `pathology_hub_v04_curriculum/` copy is stale. Run:
  `.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8080` from that dir.
  - It boots WITHOUT cloud creds: `ensure_artifacts()` skips unset `*_GCS` env vars, so
    `/health` returns `loaded: true`. Real retrieval (non-empty results) needs the GCS
    index artifacts + `OPENAI_API_KEY` + `PATHOLOGY_HUB_API_KEY`; without them
    `source_status` is `error_no_upstream`/empty, which is expected locally. The v0_2
    reliability layer (query expansion etc.) still runs — set `EVIDENCE_V0_2_ENABLED=true`
    and a `PATHOLOGY_HUB_API_KEY` (sent as `X-API-Key`) to exercise it.
- Curriculum Provenance Browser (`tools/curriculum_provenance_browser/`) — OPTIONAL local
  read-only debug UI. Run `.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765` from that
  dir (or `scripts/run_local.sh`). It needs a SQLite index at
  `outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_2.sqlite` (a gitignored
  generated artifact, absent in this mirror) or it returns 503; point `CURRICULUM_LOCATOR_SQLITE`
  at a local fixture to run it.

Tests (`pytest.ini` → `tests/`), gotchas:
- Run test files INDIVIDUALLY (e.g. loop `for f in tests/test_*.py; do .venv/bin/pytest "$f"; done`).
  A single-process full `pytest` run reports false failures due to a pre-existing cross-file
  isolation bug: after the browser test loads its own `app.py`, the backend helper's
  `import app` resolves to the wrong module. Each file passes on its own.
- `test_evidence_v0_2_regression_gate.py` and `test_curriculum_provenance_browser.py` depend
  on gitignored generated artifacts (`06_audits/...` and `outputs/*.sqlite`) that are not in
  this local mirror, so they fail/skip here without those artifacts (not an env problem).
