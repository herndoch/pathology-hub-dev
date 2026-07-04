# Rollback and Safety

v10.4/v10.5 notebooks backup backend-consumed metadata before replacement.

Known backup prefixes:

```text
gs://pathology_hub/99_backups/governance_v10_4/<run_ts>/
gs://pathology_hub/99_backups/governance_v10_5/<run_ts>/
```

Rollback only metadata/manifest/figure-map objects. Do not delete raw source files, embeddings, FAISS indexes, raw PDFs, or raw videos.

If junk tags appear again, check whether backend returns `primary_tag` instead of `primary_tag_governed` and patch loader accordingly.
