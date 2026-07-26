# Finding: rich PathOutlines normalized corpus is 100% unindexed in the live backend

**Date:** 2026-07-24
**Discovered while:** debugging why prebuilt `topic_page` answers felt shallow (user
report: "even the sources have more info on them than what you synthesized").

## Root cause

1. The live `pathology-hub-v04` backend caps PathOutlines excerpts at **~4000 chars
   from the start of the page** (`excerpt_char_limit > 4000` returns HTTP 422 — a
   real, confirmed backend ceiling, not a client-side guess). For a page like
   Pleomorphic Adenoma, that consistently excludes the Microscopic-detail,
   Immunohistochemistry, Molecular, and Differential Diagnosis sections, which all
   appear later in the raw page.
2. Multiple distinctly-worded query variants (histology-focused, IHC-focused,
   DDx-focused) do **not** reliably shift this window — the excerpt is effectively a
   head-of-document truncation, not a query-centered semantic snippet, for this
   source family.
3. A separately-staged, far richer normalized crawl already exists in GCS:
   `gs://pathology-hub-0/_pathout_raw/allsite_console_crawl_v0_1/zips/pathout_allsite_complete_normalized_v0_1 (1).zip`
   — **4,489 topics**, averaging **~30 section-typed chunks** (`epidemiology`,
   `microscopic`, `ihc_special_stains`, `molecular`, `differential_diagnosis`, ...)
   and **~11 real figure URLs** per topic (`pathout_topics.jsonl`,
   `pathout_chunks.jsonl`, `pathout_figures.jsonl`).
4. Per that dataset's own manifest flags, **0 / 4,489 topics** have
   `indexed_searchable`, `vectorized`, or `api_exposed` set to `true`. It was crawled
   and normalized in June 2026 but never wired into the live vector store the
   backend actually serves from.
5. Separately, the live WHO corpus is **missing a dedicated HN "Pleomorphic
   Adenoma" page entirely** — only `Carcinoma_Ex_Pleomorphic_Adenoma.html` (the
   malignant-transformation entity) exists under `WHO_HTML/HN/`. A WHO
   `Pleomorphic_Adenoma.html` does exist, but under `WHO_HTML/BREAST/` (a real,
   separate WHO entity for breast pleomorphic adenoma) — retrieval was pulling this
   in as if it were on-topic for the HN page.

## Interim fix shipped (Chat MVP frontend only, no backend/index changes)

- `scripts/build_pathout_deep_index_v0_1.py` reads the staged-but-unindexed
  normalized crawl (read-only) and writes a compact `page_url -> {chunks, figures}`
  JSON sidecar (`outputs/chat_mvp_topic_prepop_v0_1/pathout_deep_index_v0_1.json`,
  also uploaded to `gs://pathology_hub/chat_mvp_topic_prepop/` per this repo's GCS
  audit convention).
- `pathology_backend.enrich_cards_with_pathout_deep()` expands only the PathOutlines
  URLs the live search *already surfaced and passed root/tag filtering* using this
  sidecar — never introduces an unvetted page.
- `pathology_backend.filter_cards_by_who_volume()` / `filter_figures_by_who_volume()`
  add a **structural** organ filter using WHO's own `volume_code` / `record_id` /
  `WHO_HTML/<VOLUME>/` path metadata, since free-text matching alone missed a WHO
  Breast-book chunk that legitimately *mentions* salivary-gland PA for contrast.
- `topic_page` prompt (`prompts.py`) gained an explicit anti-conflation rule: content
  about a *different* named entity in the same evidence bundle (e.g. a DDx
  candidate) may only be used under Differential Diagnosis, never merged into the
  page's own Terminology/Etiology/Clinical sections.
- `TOPIC_PAGE_SOURCES` narrowed to `who` + `pathout` only (textbooks/journals/
  lectures/videos dropped for this mode per product decision).

## Known limitations of the interim fix

- This is a **frontend read-time enrichment**, not a backend re-index. It does not
  make PathOutlines "indexed", "vectorized", or "API-exposed" in the live backend —
  do not represent it as such elsewhere.
- Only helps PathOutlines URLs the live semantic search already returns; it cannot
  surface a PathOutlines page the live search never ranks for a given query.
- Does not fix the missing WHO HN Pleomorphic Adenoma page (a genuine content gap,
  not a retrieval bug) — WHO depth for entities lacking a dedicated page will stay
  thin until ingested.
- Cloud Run deploys of Chat MVP do not currently fetch the 51 MB deep index at
  startup; enrichment is local-dev-only for now (silent no-op if the file is
  absent, so nothing breaks — Cloud Run `topic_page` calls just fall back to the
  capped live API depth).

## Recommended follow-up (separate, larger workstream — Evidence RAG, not Chat MVP)

Properly vectorize/index the normalized PathOutlines crawl (chunks + figures) into
the live backend so every consumer (not just this frontend's topic_page mode)
benefits, and produce a real indexing audit proving `indexed_searchable` /
`vectorized` / `api_exposed` per this repo's `AGENTS.md` rule.
