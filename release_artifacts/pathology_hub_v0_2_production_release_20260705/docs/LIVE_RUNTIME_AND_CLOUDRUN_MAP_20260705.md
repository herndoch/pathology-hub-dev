# Live Runtime and Cloud Run Map — 2026-07-05

## Project

`pathology-annotation-project` / `us-central1`

## Cloud Run services (all, read-only `gcloud run services list`)

| Service | URL | Latest ready revision | Role (per canonical rules / observed) |
|---|---|---|---|
| `pathology-hub-v04` | `https://pathology-hub-v04-vorn5q2kga-uc.a.run.app` | `pathology-hub-v04-00027-tjm` | **Production** — the ONLY service backing the live `searchEvidence` GPT Action |
| `pathology-hub-v04-curriculum-staging` | `https://pathology-hub-v04-curriculum-staging-vorn5q2kga-uc.a.run.app` | `pathology-hub-v04-curriculum-staging-00001-c4h` | Curriculum-map draft staging, not the GPT Action backend |
| `pathology-hub-v04-html-staging` | `https://pathology-hub-v04-html-staging-vorn5q2kga-uc.a.run.app` | `pathology-hub-v04-html-staging-00003-fdk` | HTML bundle feature staging (pre-1.5.10 promotion) |
| `pathology-hub` | `https://pathology-hub-vorn5q2kga-uc.a.run.app` | `pathology-hub-00028-dcd` | Legacy/earlier service, out of scope |
| `pathology-hub-journal-api` | `https://pathology-hub-journal-api-vorn5q2kga-uc.a.run.app` | `pathology-hub-journal-api-00026-cws` | Journal upstream FTS API consumed by `pathology-hub-v04` (`UPSTREAM_EVIDENCE_URL` points at a similar upstream host) |
| `pathology-hub-pathout-api` | `https://pathology-hub-pathout-api-vorn5q2kga-uc.a.run.app` | `pathology-hub-pathout-api-00001-c5h` | PathOut upstream API consumed by `pathology-hub-v04` |
| `pathology-hub-rag-v1-staging` | `https://pathology-hub-rag-v1-staging-vorn5q2kga-uc.a.run.app` | `pathology-hub-rag-v1-staging-00001-dxz` | Unrelated/earlier RAG staging experiment, out of scope |

Only `pathology-hub-v04` is touched (read-only) or targeted for a NEW staging sibling in this mission. None of the above pre-existing services are modified.

## Production resource profile

- CPU: 4, Memory: 12Gi (per `service.describe.json`)
- 41 environment variables (names only — see `audits/prod_snapshot_pre_v0_2_20260705/env_var_names_redacted.json`), including GCS artifact paths for textbook/journal/pathout/lecture indexes, 3 Secret-Manager-backed vars (`PATHOLOGY_HUB_API_KEY`, `OPENAI_API_KEY`, `FIGURE_PROXY_SECRET`), and an `UPSTREAM_EVIDENCE_URL` pointing to a sibling Cloud Run host for some retrieval paths.

## Data plane sizes observed via live `/health`

- Textbook SQLite: 920,174,592 bytes; FAISS: 487,342,125 bytes; docstore: 230,912,231 bytes; figures: 148,854,686 bytes (67,992 figure records; 49,498 public figure map records)
- Journal FAISS: 793,860,141 bytes; docstore: 582,635,732 bytes; 129,209 vector records (Modern Pathology 22,229 / AJSP 81,601 / Virchows Archiv 25,379)

These are loaded into memory at container start, which explains the multi-minute cold-start health-check latency observed in this session (~110s on first call) versus sub-second latency once warm (~0.8s per `/evidence/search` call observed later in this session).

## searchEvidence dispatch map (from recovered 1.5.10 source)

```
POST /evidence/search
  sources: who | textbooks | journals | pathout | lectures | videos | curriculum
  who        -> upstream WHO retrieval + who_upstream_title_boost_v0_2 rerank already present in health search_mode
  textbooks  -> hybrid SQLite FTS5 + FAISS vector, reciprocal-rank fusion; try/except vector fallback to FTS-only with explicit warning
  journals   -> hybrid upstream FTS (pathology-hub-journal-api) + local FAISS vector, RRF
  pathout    -> upstream (pathology-hub-pathout-api) keyword FTS5 + local AP-diagnostic filtered FAISS vector
  lectures/videos -> local STRICT_CYTO_v9 routed FAISS vector artifacts
  curriculum -> local SQLite tag index (Curriculum Map v0.2), review-queue-gated for non-ABPath tags
  render_html/html_profile -> HTML bundle generation (v1.5.10), teaching_page/gallery/evidence_packet profiles
```

GET /health returns schema_version `pathology_hub_health.v1.5.10`, manifest summaries per source, and load status.
