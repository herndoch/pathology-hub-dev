# Local VS Code / Codex Runbook

## Goal

Move from governed tags inside live metadata to a real tag-aware retrieval API and curriculum-browsing system.

## Local setup

```bash
gcloud auth login
gcloud config set project pathology-annotation-project
gcloud auth application-default login
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install fastapi uvicorn google-cloud-storage pydantic pandas rapidfuzz sqlite-utils requests
```

Optional:

```bash
pip install faiss-cpu numpy
```

## Verify GCS

```bash
gcloud storage ls gs://pathology_hub/03_indexes/textbooks/vector/
gcloud storage ls gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/ | head
```

## Verify API key

```bash
gcloud secrets versions access latest --secret=pathology-hub-api-key --project=pathology-annotation-project
```

Then test with `codex_local/api_smoke_test.py`.

## Suggested repo layout

```text
pathology-hub-local/
  backend/app/
  backend/tag_runtime/
  backend/tests/
  scripts/
  notebooks/
  tmp_artifacts/  # gitignored
```

## Initial Codex tasks

1. Recover/current backend source for `pathology-hub-v04`.
2. Add a `tag_runtime` module without breaking `/evidence/search`.
3. Build an approved-only SQLite tag index from governed metadata.
4. Add optional `search_mode`: default, `tag_auto`, `tag_exact`, `tag_prefix`, `tag_browse`.
5. Add regression tests preserving v1.5.8 behavior.
6. Deploy only after tests pass.
