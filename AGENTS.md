# Pathology Hub local dev instructions

Treat CURRENT_MASTER_SPINE as canonical.

Canonical GCP project:
- pathology-annotation-project

Canonical buckets:
- gs://pathology_hub
- gs://pathology-hub-0 legacy/source

Keep separate:
- source files in GCS
- staged/normalized data
- chunked data
- vectorized/searchable indexes
- API-exposed capabilities

Do not overwrite original normalized records.
Write sidecars, enriched outputs, manifests, and audits.

Keep workstreams separate:
- Evidence RAG
- report-style RAG
- gross template generation
- HTML rendering
- backend API
- Custom GPT frontend

Do not claim a source is indexed, vectorized, tagged, or API-exposed unless an audit, manifest, health check, or project source proves it.

Before uploading to GCS:
- produce an audit JSON
- include schema_version
- include input paths
- include output paths
- include counts
- include known limitations

Shareable education maps hub:
- `map.pathologynotebook.com` (Cloud Run `pathology-hub-map`; DNS CNAME `map` → `ghs.googlehosted.com.`)
- Paths: `/lectures/`, `/textbooks/`, `/journals/` (WHO+PathOut); Chat stays at `chat.pathologynotebook.com`
- See `docs/HOSTING_MAP_PATHOLOGYNOTEBOOK_v0_1.md`
