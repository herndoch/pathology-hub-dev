# Schema Registry Addendum

## Journal vector manifest v4 union

Schema: `journal_vector_manifest.v4_union`

Key fields:

- `record_count`: 129209 after v4.4
- `embedding_model`: `text-embedding-3-small`
- `embedding_dim`: 1536
- `checks.embedding_rows`: 129209
- `checks.docstore_rows`: 129209
- `checks.faiss_ntotal`: 129209
- `journal_counts`: Modern Pathology, AJSP, Virchows Archiv

## Journal union coverage audit v4

Schema: `journal_union_coverage_audit.v4`

Used to compare current live vector docstore with normalized candidate chunk files.

## Journal vector append rebuild audit v4

Schema: `journal_vector_append_rebuild_audit.v4`

Confirms append/promote/restart summary.

## API response

Existing schema remains `evidence_search_response.v1.5.8`.

## Future Histopathology append

Use a new version, e.g. `journal_vector_manifest.v5_union_histopathology`, rather than overwriting v4 labels in docs. Live GCS path can remain the same after backup/promotion.
