# Handoff - HTML Bundle API v1.5.10

Date: 2026-07-04

## Stop Point

Staging smoke tests passed for v1.5.10 HTML bundle mode. Stop here until production promotion is explicitly approved.

Do not deploy production from this handoff automatically. Do not update GPT Builder yet.

## Staging

Service URL:

```text
https://pathology-hub-v04-html-staging-830130787988.us-central1.run.app
```

Revision:

```text
pathology-hub-v04-html-staging-00003-fdk
```

Image:

```text
us-central1-docker.pkg.dev/pathology-annotation-project/pathology-hub/pathology-hub-v04:staging-html-v1-5-10-20260704-r3
sha256:1d7480629887c8150d40c6de8115c9e48197908759c7fc70ef32e35112a88019
```

## Backend Files Changed

```text
backend/pathology_hub_v04_curriculum/app.py
```

Docs created/updated:

```text
docs/API_CONTRACT_20260704_v1_5_10_html_bundle.md
docs/openapi_pathology_hub_unified_searchEvidence_v1_5_10_html_bundle_DRAFT.yaml
docs/GPT_INSTRUCTIONS_HTML_BUNDLE_v1_5_10_DRAFT.md
docs/REGRESSION_TEST_RUNBOOK_v1_5_10_html_bundle.md
docs/HANDOFF_HTML_BUNDLE_API_v1_5_10_20260704.md
```

## GCS

Written by staging HTML bundle requests:

```text
gs://pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/*.html
gs://pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/*.html.audit.json
```

Read by the service:

```text
gs://pathology_hub/03_indexes/textbooks/lean/textbook_lean_fts.sqlite
gs://pathology_hub/03_indexes/textbooks/lean/textbook_lean_index_manifest.json
gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_faiss.index
gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_docstore.jsonl
gs://pathology_hub/03_indexes/textbooks/vector/textbook_lean_vector_manifest.json
gs://pathology_hub/02_normalized/textbooks/lean/textbook_lean_figures.jsonl
gs://pathology_hub/02_normalized/textbooks/lean/textbook_figure_web_map_v1_FILTERED_NO_MCKEE_DORFMAN.jsonl
gs://pathology_hub/02_normalized/source_registry/source_locator_registry_v1.jsonl
gs://pathology_hub/02_normalized/source_registry/textbook_page_image_inventory_v1.jsonl
gs://pathology_hub/02_normalized/textbooks/lean/tags/textbook_primary_tagged_chunks_v1.jsonl
gs://pathology_hub/03_indexes/journals/vector/journal_faiss.index
gs://pathology_hub/03_indexes/journals/vector/journal_vector_docstore.jsonl
gs://pathology_hub/03_indexes/journals/vector/journal_vector_manifest.json
gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_faiss.index
gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_docstore.jsonl
gs://pathology_hub/03_indexes/pathology_outlines/pathout_allsite_v0_1/vector_ap_diagnostic_v1/pathout_ap_diagnostic_vector_manifest.json
gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_faiss_STRICT_CYTO_v9.index
gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_docstore_STRICT_CYTO_v9.jsonl
gs://pathology_hub/03_indexes/lectures/vector_STRICT_CYTO_v9/lecture_timecoded_vector_manifest_STRICT_CYTO_v9.json
gs://pathology_hub/02_normalized/curriculum_map/v0_2/curriculum_tag_index_v0_2.sqlite
gs://pathology_hub/02_normalized/curriculum_map/v0_2/curriculum_nodes_v0_2.csv
gs://pathology_hub/02_normalized/curriculum_map/v0_2/review_queue_v0_2.csv
gs://pathology_hub/02_normalized/curriculum_map/v0_2/rejected_tags_v0_2.csv
gs://pathology_hub/06_audits/curriculum_map/v0_2/acceptance_summary_v0_2.json
```

## API Additions

New optional request fields on existing `POST /evidence/search` / `operationId: searchEvidence`:

```text
render_html: boolean, default false
html_profile: teaching_page | gallery | evidence_packet, default teaching_page
html_title: string, optional
target_figure_count: integer 1-50, default 10
html_include_toc: boolean, default true
html_include_source_sections: boolean, default true
```

New response field when `render_html=true`:

```text
html_result.status
html_result.profile
html_result.title
html_result.html_url
html_result.html_gcs_uri
html_result.audit_gcs_uri
html_result.figure_count
html_result.evidence_count
html_result.sources_used
html_result.warnings
html_result.generated_at_utc
```

Health additions:

```text
html_bundle_enabled = true
html_bundle_version = v1.5.10
```

## Smoke Tests

Passed:

```text
GET /health
POST /evidence/search normal curriculum query: ovary granulosa
POST /evidence/search normal textbook query: tubular adenoma
POST /evidence/search HTML teaching_page: ovarian granulosa cell tumor
POST /evidence/search HTML gallery: tubular adenoma, target_figure_count 50
Response size regression: no inline full HTML, no huge figure arrays
Forbidden-pattern scan: returned JSON and generated HTML clean
Audit sidecar fetch/parse: passed
```

Observed response sizes:

```text
health: 53861 bytes
normal curriculum: 3834 bytes
normal textbook: 14039 bytes
HTML teaching_page JSON: 3478 bytes
HTML gallery JSON: 2062 bytes
```

Generated HTML:

```text
Teaching page:
https://storage.googleapis.com/pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/20260705T011743Z_Ovarian_granulosa_cell_tumor_teaching_page_f12419a2646f.html

Gallery:
https://storage.googleapis.com/pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/20260705T011751Z_Tubular_adenoma_gallery_75e5dce87728.html
```

Generated audits:

```text
gs://pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/20260705T011743Z_Ovarian_granulosa_cell_tumor_teaching_page_f12419a2646f.html.audit.json
gs://pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/20260705T011751Z_Tubular_adenoma_gallery_75e5dce87728.html.audit.json
```

## Known Limitations

- Production is not deployed yet.
- GPT Builder is not updated yet.
- OpenAI embedding calls were quota-limited during staging. Textbook retrieval now falls back to local SQLite FTS and returns `ok` with warnings. PathOut vector warnings can still appear when embeddings are unavailable.
- HTML bundles include only URLs, excerpts, metadata, and figure links returned by existing sources. They do not invent citations, URLs, image URLs, page numbers, timestamps, or captions.
- Gallery quality depends on source figure metadata and returned URLs.
- Generated HTML artifacts are static GCS objects with JSON audit sidecars.

## Later Production Promotion

Use the already-built staging image unless a new commit requires a rebuild:

```bash
gcloud run deploy pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --image=us-central1-docker.pkg.dev/pathology-annotation-project/pathology-hub/pathology-hub-v04:staging-html-v1-5-10-20260704-r3 \
  --service-account=830130787988-compute@developer.gserviceaccount.com \
  --memory=12Gi \
  --cpu=4 \
  --concurrency=160 \
  --timeout=300 \
  --min-instances=0 \
  --max-instances=10 \
  --allow-unauthenticated
```

Before running production promotion, include the same production env vars and secrets currently configured on `pathology-hub-v04`, plus:

```text
HTML_BUNDLE_GCS_PREFIX=gs://pathology_hub/05_html/generated/searchEvidence_html/v1_5_10/
```

After production deploy, rerun the health, normal source, HTML teaching page, HTML gallery, response-size, forbidden-pattern, and audit-sidecar checks against production.

## GPT Builder Files To Update Later

Do not update GPT Builder until production passes.

Later Action schema draft:

```text
docs/openapi_pathology_hub_unified_searchEvidence_v1_5_10_html_bundle_DRAFT.yaml
```

Later GPT instructions draft:

```text
docs/GPT_INSTRUCTIONS_HTML_BUNDLE_v1_5_10_DRAFT.md
```

Keep one Action only:

```text
searchEvidence / POST /evidence/search
```

## Rollback

Staging rollback to the previous staging revision:

```bash
gcloud run services update-traffic pathology-hub-v04-html-staging \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --to-revisions=pathology-hub-v04-html-staging-00002-tlm=100
```

Production rollback, if production promotion is later attempted and fails:

```bash
gcloud run services update-traffic pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --to-revisions=<previous-production-revision>=100
```

Find the previous production revision before promotion:

```bash
gcloud run revisions list \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --service=pathology-hub-v04
```
