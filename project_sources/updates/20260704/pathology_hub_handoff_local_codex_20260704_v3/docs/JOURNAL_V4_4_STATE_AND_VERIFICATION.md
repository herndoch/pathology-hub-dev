# Journal Workstream State — v4.4 and Next Steps

## What was fixed

The original public journal browser was stale. Subsequent audits showed the deeper issue: current journal vector/docstore did not include every normalized journal source. v4.4 appended Virchows Archiv to the live vector/docstore.

## v4.4 audited result

```json
{
  "previous_rows": 103830,
  "new_rows_added": 25379,
  "union_rows": 129209,
  "union_articles": 8654,
  "journal_counts": {
    "Modern Pathology": 22229,
    "The American Journal of Surgical Pathology": 81601,
    "Virchows Archiv": 25379
  },
  "cloud_run_restart_returncode": 0,
  "manifest_checks": {
    "embedding_rows": 129209,
    "docstore_rows": 129209,
    "faiss_ntotal": 129209,
    "zero_norm_rows": 0
  },
  "checkpoint": {
    "texts_count": 25379,
    "texts_fingerprint": "3bb78b2fdfc6d3e1c4b6956281ab12f333a6a1e224d5e44d7f362dc078b4c0a6",
    "embedded_rows": 25379,
    "updated_at_utc": "2026-07-04T18:13:51+00:00",
    "embedding_model": "text-embedding-3-small",
    "batch_size": 64,
    "tpm_budget": 700000
  }
}
```

## Promoted live paths

```text
gs://pathology_hub/03_indexes/journals/vector/journal_embeddings.npy
gs://pathology_hub/03_indexes/journals/vector/journal_faiss.index
gs://pathology_hub/03_indexes/journals/vector/journal_vector_docstore.jsonl
gs://pathology_hub/03_indexes/journals/vector/journal_vector_manifest.json
```

Browser live paths:

```text
gs://pathology_hub/05_html/article_browser/article_browser.html
gs://pathology_hub/05_html/article_browser/journal_chunk_browser.html
```

## Important caution

The script's built-in API proof failed because `requests` was not imported. Manual user proof showed `GET /health` status 200 and manifest `record_count=129209`, but broad queries like `Virchows Archiv colorectal carcinoma` returned AJSP FTS-only hits. This likely reflects ranking/fusion behavior or upstream FTS dominance. It does not invalidate the promoted vector artifacts, but it does mean API content retrieval is not proven.

## Targeted proof required

Codex should run targeted proof that asserts at least one returned result has:

```json
{"journal": "Virchows Archiv"}
```

Recommended probe strategy:

1. Download or sample `journal_vector_docstore.jsonl` and find exact Virchows article titles/DOIs.
2. Query exact title/DOI snippets with `sources:["journals"]`.
3. Verify returned result fields include `journal == "Virchows Archiv"` and preferably `retrieval_mode` includes vector/hybrid, not only FTS.
4. If API still returns AJSP, inspect backend journal FTS/vector fusion code.

## Do not do

- Do not rerun v4.4 just to test API.
- Do not embed Histopathology until v4.4 API behavior is verified or backend behavior is understood.
- Do not download the 1.5GB full Colab output ZIP. GCS has the artifacts.
