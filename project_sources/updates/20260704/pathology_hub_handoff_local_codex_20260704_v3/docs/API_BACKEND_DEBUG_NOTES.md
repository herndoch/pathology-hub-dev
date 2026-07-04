# API Backend Debug Notes

## Observed behavior

After v4.4 promotion, live health reports journal vector manifest `record_count = 129209`. However, manual broad API queries for Virchows returned AJSP FTS-only hits. This means health/manifest loading is not enough to prove returned journal behavior.

## Hypotheses

1. The journal search path may still be dominated by upstream FTS.
2. Vector retrieval may be loaded but RRF/fusion may rank FTS hits higher.
3. Query terms including `Virchows Archiv` match references in AJSP articles rather than Virchows source records.
4. Virchows records may have metadata fields not normalized to `journal`, `source_name`, or `source` expected by result formatting.
5. The health manifest note says vector artifacts are API exposed, but an older `api_exposed_note` mentions a v04.5 patch. Inspect backend to confirm actual vector code path.

## Debug checklist

- Query exact Virchows article title from docstore.
- Query exact Virchows DOI from docstore.
- Query an excerpt only present in a Virchows chunk.
- Inspect response `retrieval_mode`, `journal`, `source_name`, `vector_rank`, `fts_rank`.
- Temporarily add a backend debug endpoint or local script to run vector-only retrieval against journal FAISS/docstore.
- Check if backend downloads GCS artifacts fresh after Cloud Run restart or uses old local cache.
- Verify `journal_vector_docstore.jsonl` local loaded row count in Cloud Run logs/health.

## Success criteria

For Virchows:

```text
GET /health: record_count 129209
POST /evidence/search: at least one targeted query returns journal/source_name Virchows Archiv
```

For Histopathology after future append:

```text
GET /health: record_count > 129209
POST /evidence/search: at least one targeted query returns journal/source_name Histopathology
```
