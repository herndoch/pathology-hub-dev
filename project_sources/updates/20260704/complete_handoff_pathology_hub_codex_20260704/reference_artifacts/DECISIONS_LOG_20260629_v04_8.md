# Decisions Log Addendum — 2026-06-29 v04.8

## Backend/API decisions
1. Keep one GPT Action only: `searchEvidence` / `POST /evidence/search`.
2. Add `lectures` and `videos` as source values rather than adding a new lecture Action.
3. Expose PathOut AP-diagnostic vector search through existing `pathout` source.
4. Enrich textbook results with primary-tag sidecar rather than rebuilding textbook vectors.
5. Preserve fallback behavior: if a new local vector artifact fails, do not remove upstream/passthrough functionality.

## Textbook decisions
1. Use page-level primary tags first, inherited to chunks.
2. Treat textbook primary tags as reviewable routing/boosting metadata, not diagnostic truth.
3. Do not overwrite original normalized textbook chunks/pages; write sidecar/enriched outputs.
4. Keep derm_mckee and bone_dorfman figure serving excluded from public figure map because prior derivative audit was poor; text remains searchable.

## PathOut decisions
1. Use AP/diagnostic scoped subset, not full CP/lab-management corpus, for vector search.
2. Keep unmapped AP diagnostic pages searchable; do not penalize solely for `__UNMAPPED__`.
3. Metadata cleanup is deferred; API vector exposure is live despite rough metadata.

## Lecture/video decisions
1. v3/v5/v6/v7/v8 lecture job sets were superseded.
2. Use STRICT_CYTO_v9 job set only.
3. True cyto lecture jobs receive all Cyto_* tags except `Cyto_Management`.
4. Non-cyto lecture jobs receive one organ/system root tag catalog.
5. Uncertain lecture chunks are held out from the v9 routed-only vector index.
6. v04.9 should fix lecture metadata and `video_time_url` rather than changing v04.8 vector exposure.
