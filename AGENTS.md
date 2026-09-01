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
- Chat MVP (`chat.pathologynotebook.com`)
- Chat no-AI content map (`no-ai-chat.pathologynotebook.com`; static inventory)

Do not claim a source is indexed, vectorized, tagged, or API-exposed unless an audit, manifest, health check, or project source proves it.

Before uploading to GCS:
- produce an audit JSON
- include schema_version
- include input paths
- include output paths
- include counts
- include known limitations

Desktop Cursor sync with Cloud Agent work:
- see `docs/DESKTOP_CURSOR_SYNC_WITH_CLOUD_AGENTS_v0_1.md`
- GitHub PRs/branches are the source of truth; Cloud chat transcripts are not cloned to Desktop
