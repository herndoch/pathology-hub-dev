# Master Handoff Packet — Pathology Hub Local Codex Transition, 2026-07-04

## Workstream name

Primary: **Evidence RAG / Journal vector + browser union rebuild / API verification**.

Adjacent workstreams captured for context:

- Tag governance / curriculum mapping
- Textbook and lecture metadata cleanup
- PathOut tag normalization
- Custom GPT frontend instructions
- Backend API contract for `searchEvidence`

Keep these separate:

- Evidence RAG
- report-style RAG
- gross template generation
- HTML rendering
- backend API
- Custom GPT frontend

## Purpose

Provide a local development handoff for Codex/VS Code so the next phase can proceed outside Colab/chat without losing project state.

## Inputs assumed

- GCP project: `pathology-annotation-project`
- Primary bucket: `gs://pathology_hub`
- Legacy/source bucket: `gs://pathology-hub-0`
- Cloud Run service: `pathology-hub-v04`
- Live API URL: `https://pathology-hub-v04-vorn5q2kga-uc.a.run.app`
- Search endpoint: `POST /evidence/search`
- Auth header: `X-API-Key`
- OpenAI embedding model used for journal v4.4: `text-embedding-3-small`
- Colab secrets used successfully: `OPEN_AI_KEY_01` and `HUB_API` / `X-API-Key`

## Current live journal state from audit

```json
{
  "status": "promoted_live_by_audit; API health shows record_count 129209 but content proof should be repeated with targeted Virchows queries",
  "previous_rows": 103830,
  "new_rows_added": 25379,
  "union_rows": 129209,
  "union_articles": 8654,
  "journal_counts": {
    "Modern Pathology": 22229,
    "The American Journal of Surgical Pathology": 81601,
    "Virchows Archiv": 25379
  },
  "embedding_model": "text-embedding-3-small",
  "embedding_dim": 1536,
  "faiss_ntotal": 129209,
  "zero_norm_rows": 0,
  "cloud_run_restart_returncode": 0,
  "vector_artifact_paths": {
    "embeddings_npy": "gs://pathology_hub/03_indexes/journals/vector/journal_embeddings.npy",
    "faiss_index": "gs://pathology_hub/03_indexes/journals/vector/journal_faiss.index",
    "docstore_jsonl": "gs://pathology_hub/03_indexes/journals/vector/journal_vector_docstore.jsonl",
    "manifest_json": "gs://pathology_hub/03_indexes/journals/vector/journal_vector_manifest.json"
  },
  "stage_root": "gs://pathology_hub/03_indexes/journals/vector_union_v4_4/20260704T174528Z",
  "audit_root": "gs://pathology_hub/06_audits/journals/vector_union_v4_4/20260704T174528Z",
  "backup_root": "gs://pathology_hub/99_backups/journal_union_vector_v4_4/20260704T174528Z/",
  "api_proof_file_bug": "journal_union_v4_api_proof.json failed due missing requests import; user manual proof had health 200 but broad Virchows queries returned AJSP FTS-only hits"
}
```

## Source files available in GCS versus indexed artifacts

### Source / normalized available

- Histopathology normalized chunks: `gs://pathology_hub/02_normalized/journals_batches/histopathology/journal_chunks.jsonl`
- Histopathology articles: `gs://pathology_hub/02_normalized/journals_batches/histopathology/journal_articles.jsonl`
- Histopathology figures: `gs://pathology_hub/02_normalized/journals_batches/histopathology/journal_figures.jsonl`
- Virchows normalized chunks: `gs://pathology_hub/02_normalized/journals/springer_virchows_archiv_v0_7/journal_chunks.jsonl`
- Current consolidated journal normalized chunks: `gs://pathology_hub/02_normalized/journals/journal_chunks.jsonl`

### Vectorized/searchable/API-exposed journal artifacts

- Live docstore: `gs://pathology_hub/03_indexes/journals/vector/journal_vector_docstore.jsonl`
- Live embeddings: `gs://pathology_hub/03_indexes/journals/vector/journal_embeddings.npy`
- Live FAISS: `gs://pathology_hub/03_indexes/journals/vector/journal_faiss.index`
- Live manifest: `gs://pathology_hub/03_indexes/journals/vector/journal_vector_manifest.json`

### API exposed capability

- Journal source is exposed through `searchEvidence` with `sources: ["journals"]`.
- Do not infer correct journal-level retrieval from health alone. Must prove returned `journal` values.

## Outputs produced / promoted during this conversation

- Static article browser refreshed to v4.4 union source.
- Static chunk browser refreshed.
- Journal embeddings/FAISS/docstore/manifest rebuilt and promoted.
- Cloud Run restarted successfully.
- Histopathology located but not added.
- Handoff packet generated for local Codex.

## Integration points

- Custom GPT should continue using one Action only: `searchEvidence`.
- Backend must load live GCS journal vector artifacts at service startup.
- Static browser lives under `05_html` and is not the API.
- Browser can be correct while API retrieval still ranks non-target FTS hits; verify both separately.

## Tests / audits included

- `journal_vector_append_rebuild_audit_v4.json`
- `journal_union_coverage_audit_v4.json`
- `journal_vector_manifest_union_v4.json`
- `journal_browser_union_promotion_audit_v4.json`
- `new_embeddings_checkpoint_v4_4_meta.json`
- Bad built-in API proof: `journal_union_v4_api_proof.json` documents missing `requests` import.

## Known limitations

1. Histopathology is available normalized but not live vectorized.
2. User manual broad queries returned AJSP FTS-only results despite live union manifest.
3. Need targeted Virchows proof from exact titles/DOIs or known records.
4. Backend journal ranking may overweight upstream FTS; inspect RRF/fusion implementation.
5. Curriculum tag v11 was planned/generated, but not verified live here.

## Next steps

1. Verify live journal vector manifest via GCS and health.
2. Run targeted API probes requiring `Virchows Archiv` results.
3. Inspect backend if probes still return FTS-only AJSP hits.
4. Inventory Histopathology counts from `journals_batches/histopathology`.
5. Build v4.5/v5 union append including Histopathology only after v4.4 API behavior is understood.
