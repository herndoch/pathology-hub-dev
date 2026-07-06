# backend/pathology_hub_v04_live_recovered/

This is the canonical recovered-and-integrated backend source tree for `pathology-hub-v04`.

## Provenance

`app.py` (the first ~3202 lines) is the **exact, verified live production source**
recovered from the Cloud Build source archive that produced the currently-serving
production image (see `docs/LIVE_BACKEND_RECOVERY_RESULTS_20260705.md`). It is not
a reconstruction. Confirmed against live `/health` (`version: 1.5.10-html-bundle`).

Everything below the `EVIDENCE SEARCH RELIABILITY v0_2 — SERVER-SIDE INTEGRATION`
banner comment in `app.py` was added in this session (Phase 3) and is additive-only:
it wraps, but does not modify, any of the recovered 1.5.10 baseline code above it.

## Contents

- `app.py` — recovered 1.5.10 baseline + v0_2 server-side integration wrapper
- `evidence_search_reliability_v0_2/` — query expansion / root gating / WHO rerank module
- `query_expansion_rules_v0_2.json` — original v0_2 rules (baseline, unmodified)
- `query_expansion_rules_v0_2_1.json` — tuned v0_2.1 rules (see `docs/V0_2_1_RULE_CHANGELOG_20260705.md`)
- `requirements.txt`, `Dockerfile` — recovered from the same Cloud Build source archive

## Feature flags (all read from environment; all default to safe/baseline behavior)

| Flag | Default | Effect |
|---|---|---|
| `EVIDENCE_V0_2_ENABLED` | `false` | Master switch. When false, behavior is byte-identical to the recovered 1.5.10 baseline. |
| `EVIDENCE_QUERY_EXPANSION_ENABLED` | `true` (only matters if V0_2_ENABLED) | Governed abbreviation/synonym expansion |
| `EVIDENCE_ROOT_GATING_ENABLED` | `true` (only matters if V0_2_ENABLED) | Blocks expansion into wrong anatomic roots |
| `EVIDENCE_WHO_RERANK_ENABLED` | `true` (only matters if V0_2_ENABLED) | WHO title/subsection reranking |
| `EVIDENCE_V0_2_DEBUG` | `false` | Adds `diagnostics`/`query_original`/`query_effective` fields to the response |
| `EVIDENCE_QUERY_EXPANSION_RULES_PATH` | `query_expansion_rules_v0_2.json` (in this dir) | Point at `query_expansion_rules_v0_2_1.json` to use the tuned rule set |
| `EVIDENCE_HUB_APP_VERSION_OVERRIDE` | unset | Override the `version` field returned by `/health` and `/evidence/search` (used for staging, e.g. `1.5.10-html-bundle-v0.2-staging`) |

## Safety contract

- If `EVIDENCE_V0_2_ENABLED=false`: 100% baseline behavior, no code path difference.
- If the v0_2 module fails to import, or query expansion / WHO rerank raises an
  exception at request time: the baseline response is still returned, with an
  explicit string appended to the `warnings` array. **No source becomes
  unavailable solely because v0_2 fails.**
- Figure/page URL behavior, HTML bundle rendering (`render_html`), and curriculum
  behavior (`source=curriculum`) are fully preserved because the wrapper's
  baseline step is the complete, unmodified v1.5.10 handler (including its own
  render_html/curriculum/figure logic).
- Exactly one Action / one route: `POST /evidence/search`. No new operationId
  was added anywhere in this file.

## Local run (do not do this without real GCS/Secret Manager credentials — it
will attempt to download ~2.8GB of real production indexes on startup)

```bash
cd backend/pathology_hub_v04_live_recovered
pip install -r requirements.txt
export PATHOLOGY_HUB_API_KEY=... # from Secret Manager, never commit
export EVIDENCE_V0_2_ENABLED=true
uvicorn app:app --host 0.0.0.0 --port 8080
```

For local unit testing WITHOUT real credentials or GCS access, see `tests/`
at the repo root — those tests import this module directly and monkeypatch
the baseline endpoints, so they never trigger `ensure_artifacts()` (which is
only invoked from `@app.on_event("startup")`, not on plain import).

## Deploy (staging only from this session; production deploy is Phase 8, NOT authorized here)

```bash
gcloud run deploy pathology-hub-v04-v0-2-staging \
  --source backend/pathology_hub_v04_live_recovered \
  --region us-central1 --project pathology-annotation-project \
  --no-allow-unauthenticated=false \
  --set-env-vars EVIDENCE_V0_2_ENABLED=true,EVIDENCE_QUERY_EXPANSION_ENABLED=true,EVIDENCE_ROOT_GATING_ENABLED=true,EVIDENCE_WHO_RERANK_ENABLED=true,EVIDENCE_V0_2_DEBUG=false,EVIDENCE_QUERY_EXPANSION_RULES_PATH=/app/query_expansion_rules_v0_2_1.json,EVIDENCE_HUB_APP_VERSION_OVERRIDE=1.5.10-html-bundle-v0.2-staging,... (plus all production data-plane env vars; see docs/STAGING_DEPLOY_LOG_V0_2_20260705.md for the exact command actually run)
```
