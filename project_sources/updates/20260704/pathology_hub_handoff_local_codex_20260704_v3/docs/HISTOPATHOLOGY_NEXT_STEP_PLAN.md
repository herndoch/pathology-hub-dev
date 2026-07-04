# Histopathology Next-Step Plan

## Status

Histopathology is located but not vectorized live.

Important discovered paths:

```text
gs://pathology_hub/02_normalized/journals_batches/histopathology/journal_articles.jsonl
gs://pathology_hub/02_normalized/journals_batches/histopathology/journal_chunks.jsonl
gs://pathology_hub/02_normalized/journals_batches/histopathology/journal_figures.jsonl
gs://pathology_hub/02_normalized/journals_batches/histopathology/journal_output_audit.json
```

Legacy/source assets also exist under:

```text
gs://pathology-hub-0/_asset_library/journals/Wiley_Histopathology/
gs://pathology-hub-0/_content_library/journals/Wiley_Histopathology/
gs://pathology-hub-0/_journal_browser/article_json/wiley_*Histopathology*/
```

## Required sequence

1. Count rows/articles/journals in the Histopathology normalized chunk file.
2. Compare article IDs/DOIs against the current live journal vector docstore to avoid duplicates.
3. Build a journal union append for missing Histopathology chunks.
4. Use retry/resume embedding logic from v4.4.
5. Rebuild FAISS/docstore/manifest and static browser.
6. Promote only after GCS staging and clear audit.
7. Restart Cloud Run.
8. Run targeted API proof requiring returned `journal == "Histopathology"`.

## Suggested v4.5/v5 scope

- Reuse v4.4 retry/resume script.
- Add candidate search path `gs://pathology_hub/02_normalized/journals_batches/**/*.jsonl`.
- Ensure Histopathology is not skipped because it lives under `journals_batches/`, not `journals/`.
- Make API proof a hard gate or at least a clearly separated post-promotion proof.

## Do not conflate

- Legacy Wiley assets are source files.
- `02_normalized/journals_batches/histopathology/journal_chunks.jsonl` is normalized/chunked content.
- The live vector index is under `03_indexes/journals/vector/` and currently does not include Histopathology by audit.
