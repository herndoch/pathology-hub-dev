# Journals corpus retired (2026-07-26)

Local journal RAG (AJSP + Modern Pathology + Virchows Archiv FAISS/FTS) is **retired**
and moved to cold archive. It is no longer a supported evidence source in the Chat MVP
or backend API.

## Why

- **AJSP** (~81k chunks): systematic ingest corruption (lowercase `t` dropped from body text).
- **Modern Pathology / Virchows**: text is clean locally, but redundant for topic pages vs
  live Elsevier Scopus + PubMed abstracts with DOI links for institutional full text.
- **Operational cost**: ~7.9 GB FAISS/docstore downloaded on backend cold start.

## Archive location (GCS)

```text
gs://pathology_hub/_archive/retired_journals_20260726/
├── 01_sources/journals/
├── 02_normalized/journals/
├── 02_normalized/journals_batches/
├── 03_indexes/journals/
├── 05_html/article_browser/
└── RETIRE_AUDIT.json
```

Tombstone files: `gs://pathology_hub/<former-prefix>/RETIRED.json`

Repo audit copy: `audits/journals_retired_20260726/RETIRE_AUDIT.json`

## Code changes

| Component | Change |
|-----------|--------|
| Backend `pathology_hub_v04_live_recovered` | `JOURNALS_RETIRED=1` (default); `journals` removed from allowed `/evidence/search` sources |
| Chat MVP | `journals` removed from `SUPPORTED_SOURCES` and topic-page source lists |
| GCS | Prefixes moved with `scripts/retire_journals_corpus_gcs_v0_1.py` |

## Live literature (future, not implemented)

GCP Secret Manager credentials exist for `Elsevier`, `OncoKB`, `NCBI`, `SpringerOpen`,
`SpringerMeta`. Live probes succeeded 2026-07-26. Planned pattern: **Key Literature**
strip (Scopus/PubMed abstract + DOI link), OncoKB for molecular sections — not local FAISS.

## Cloud Run

Set on `pathology-hub-v04`:

- `JOURNALS_RETIRED=1`
- Remove `JOURNAL_FAISS_GCS`, `JOURNAL_DOCSTORE_GCS`, `JOURNAL_VECTOR_MANIFEST_GCS`

Redeploy backend image after merging backend changes.

## Do not

- Re-promote archived paths to live `03_indexes/journals/` without a full re-ingest audit.
- Feed archived AJSP `chunk_text` into LLM synthesis.
