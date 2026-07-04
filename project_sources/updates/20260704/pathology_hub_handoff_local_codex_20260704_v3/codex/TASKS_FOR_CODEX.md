# Tasks for Codex

## Phase 1 — Verify v4.4 live behavior

- Read live journal manifest from GCS.
- Confirm 129,209 record count.
- Sample live docstore for Virchows exact title/DOI.
- Run API probes requiring Virchows result.
- If probes fail, inspect backend ranking/fusion/load path.

## Phase 2 — Histopathology inventory

- Count rows/articles/journals in Histopathology normalized files.
- Determine duplicate keys versus live docstore.
- Validate field coverage: journal/title/doi/url/published/year/text.

## Phase 3 — Append Histopathology

Only after Phase 1 proof or backend fix:

- Use retry/resume embedding.
- Stage under new version path, e.g. `vector_union_v5_histopathology/<timestamp>/`.
- Promote with backups.
- Restart Cloud Run.
- Run API proof requiring Histopathology result.

## Phase 4 — GPT update

Only after proof:

- Update source status to include Modern Pathology, AJSP, Virchows, Histopathology.
- Keep caveats about FTS/vector hybrid behavior.
