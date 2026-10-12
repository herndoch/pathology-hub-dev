# Billing & Cloud Run cost notes (through 2026-08-22)

**Scope:** Operational cost posture for Pathology Hub Chat + evidence API in GCP
project `pathology-annotation-project`. No application code change required to
follow this doc — it records what burned money, what we changed, and how to keep
idle cost low.

**Custom domain:** `https://chat.pathologynotebook.com`  
**Evidence API:** Cloud Run service `pathology-hub-v04`  
**Chat UI:** Cloud Run service `pathology-hub-chat-mvp`

Related older docs (context only — some recommend the *opposite* of current
cost posture):

- `docs/PRODUCTION_MIN_INSTANCES_FIX_20260705.md` — set `min-instances=1` on
  `pathology-hub-v04` (warm latency); this is a primary historical cost driver.
- `docs/PRODUCTION_COLD_START_INVESTIGATION_20260706.md` /
  `docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md` — cold-start vs warm.

---

## TL;DR (current intended posture)

| Goal | Setting |
|------|---------|
| Cheap when unused | **Automatic scaling**, **`minScale` unset / 0** on all kept services |
| Site reachable | Do **not** leave services in **manual scaling with instance count 0** (that returns **503 Service is disabled**) |
| Fully off (no serve) | Manual scaling with instance count **0**, or delete the service |
| Biggest per-request cost | `pathology-hub-v04` (4 CPU, large memory — raised to **16Gi** after OOM during Compare) |

**Idle Cloud Run ≈ near $0** when everything is on auto + min=0.  
**Spikes** happen when traffic wakes `pathology-hub-v04` (Browse live queries,
Ask, Compare). **GCS storage** and **OpenAI** are separate line items.

---

## What was charging a bunch (root causes)

### 1. Always-on Cloud Run (`minScale=1`)

Earlier production hardening intentionally set `min-instances=1` on
`pathology-hub-v04` so the first user request was not a multi-minute cold start.
That keeps at least one **4 CPU / multi-GiB** instance billed **24/7**, which
dominates GCP spend vs request-only usage.

Staging / smoke / hello services with similar mins amplified the burn until
they were deleted.

### 2. Manual scaling pinned at 0 (“Service is disabled”)

Setting instances to **0** in the console under **manual** scaling is not the
same as autoscaling `min=0`:

- Manual + count `0` → service effectively **disabled** → browser shows
  `503 Service Unavailable` / “Service is disabled” on
  `chat.pathologynotebook.com`.
- Automatic + `min=0` → **scales to zero when idle**, scales up on demand.

### 3. Heavy revision under load (Compare)

Compare (`POST /api/compare`) always runs **live** per-diagnosis retrieval
against `pathology-hub-v04` (prebuilt pages are only optionally used for Key
Facts text — see Chat MVP `app.py`). Multi-entity Compare can OOM a tight
memory limit:

| When (UTC) | Revision | Limit | Observed |
|------------|----------|-------|----------|
| 2026-08-22 ~22:31 | `…-00053` | 8Gi | Memory limit exceeded |
| 2026-08-22 ~22:38 | `…-00054` | 12Gi | Still OOM under Compare |
| After | `…-00055` | **16Gi** | Intended headroom for Compare |

Higher memory **does not** create idle cost by itself when `minScale=0`; it
only costs while an instance is up serving traffic.

### 4. Not the main GCP burn: GCS

Canonical bucket `gs://pathology_hub` (plus legacy `gs://pathology-hub-0`) holds
staged/normalized data, indexes, and topic prebuilds. Storage is on the order of
**hundreds of GiB → roughly single-digit USD/month** for standard storage — not
the same order of magnitude as always-on Cloud Run CPU/RAM.

**Prebuilds are not deleted** by scaling Cloud Run to zero.

### 5. Separate from GCP: OpenAI

Chat Ask / topic synthesis / Compare synthesis / embeddings (when hybrid search
needs them) bill against OpenAI. Credit exhaustion previously forced FTS
fallbacks on textbooks (see textbook FTS fallback work / PR #43).

### 6. Out of scope for Chat: `grimoire-spellbook` Cloud SQL

A different “Hub” / Workbench stack may use Cloud SQL instance
`grimoire-spellbook`. **Pathology Hub Chat does not depend on it.** Stopping or
starting that instance is unrelated to `chat.pathologynotebook.com` Cloud Run
billing.

---

## Ops timeline (Aug 2026 cost panic → restore)

Approximate sequence (agent + owner ops on project
`pathology-annotation-project`, region `us-central1`):

1. Identified cost drivers: `pathology-hub-v04` (+ staging) with **minScale=1**,
   large CPU/RAM.
2. Set mins toward **0**; deleted staging / smoke / hello services.
3. Kept services: `pathology-hub`, `pathology-hub-chat-mvp`,
   `pathology-hub-journal-api`, `pathology-hub-pathout-api`, `pathology-hub-v04`.
4. Owner later set remaining services to **0** (manual) → site **503 disabled**.
5. Restored with:
   ```bash
   gcloud run services update SERVICE \
     --region=us-central1 \
     --project=pathology-annotation-project \
     --scaling=auto \
     --min=0 \
     --max=10
   ```
6. Bumped `pathology-hub-v04` memory **8Gi → 12Gi → 16Gi** after Compare OOMs.
7. Verified `https://chat.pathologynotebook.com/api/health` → app ok + backend ok
   (`pathology-hub-v04` `1.5.10-html-bundle`).

### Verified service posture (2026-08-22, after restore)

All five kept services: **scalingMode=automatic**, **no manualInstanceCount**,
**minScale effectively 0**.

| Service | CPU | Memory (after ops) | Notes |
|---------|-----|--------------------|--------|
| `pathology-hub-chat-mvp` | 1 | 1Gi | Chat UI + `/api/*` |
| `pathology-hub-v04` | 4 | **16Gi** | Evidence / RAG — main cost when warm |
| `pathology-hub` | 1 | 2Gi | Older hub surface |
| `pathology-hub-journal-api` | 1 | 2Gi | Journals path |
| `pathology-hub-pathout-api` | 1 | 2Gi | PathOut path |

Cold start after idle can be **~30–60+ seconds** on first hit to chat/v04; that
is the tradeoff for not paying always-on.

---

## How to stay cheap (runbook)

### Keep idle low

- Prefer **`--scaling=auto`** and **`--min=0`** (or unset minScale).
- Do **not** re-enable `min-instances=1` unless you explicitly accept 24/7 bill
  for warm latency.
- Avoid leaving Compare / multi-leaf live Browse sessions running unnecessarily
  (keeps `v04` warm longer).

### Bring site fully down

```bash
# Disables serving (503 "Service is disabled")
gcloud run services update pathology-hub-chat-mvp \
  --region=us-central1 --project=pathology-annotation-project \
  --scaling=0
gcloud run services update pathology-hub-v04 \
  --region=us-central1 --project=pathology-annotation-project \
  --scaling=0
```

(`--scaling=N` with integer N = manual fixed instance count.)

### Bring site back (cheap idle, on-demand serve)

```bash
gcloud run services update pathology-hub-chat-mvp \
  --region=us-central1 --project=pathology-annotation-project \
  --scaling=auto --min=0 --max=10
gcloud run services update pathology-hub-v04 \
  --region=us-central1 --project=pathology-annotation-project \
  --scaling=auto --min=0 --max=10
# optionally the other three kept services the same way
```

Then wake:

```bash
curl -sS -o /dev/null -w "%{http_code} %{time_total}\n" \
  --max-time 180 https://chat.pathologynotebook.com/api/health
```

### Check current scaling (when `gcloud` is available)

```bash
gcloud run services list --region=us-central1 \
  --project=pathology-annotation-project \
  --format='table(metadata.name,metadata.annotations["run.googleapis.com/scalingMode"],metadata.annotations["run.googleapis.com/manualInstanceCount"])'

gcloud run services describe pathology-hub-v04 \
  --region=us-central1 --project=pathology-annotation-project \
  --format='yaml(spec.template.spec.containers[0].resources,spec.template.metadata.annotations)'
```

---

## Cost buckets (mental model)

| Bucket | Idle | Active | Notes |
|--------|------|--------|-------|
| Cloud Run (auto, min=0) | ≈ $0 | Per vCPU-second / GiB-second while up | `v04` dominates |
| Cloud Run (min≥1) | Continuous | Same + always-on base | Avoid unless needed |
| GCS `pathology_hub` | Low monthly storage | Egress / ops | Keep; not the panic driver |
| OpenAI | $0 if unused | Per token / embedding | Ask, Compare, hybrid embeddings |
| Cloud SQL `grimoire-spellbook` | If RUNNING | Always-on DB $ | Unrelated to Chat MVP |
| Compute VM `doc-ai-processor-v2` | If STOPPED ≈ disk only | If RUNNING | Unrelated to Chat MVP |

Exact dollar amounts change with GCP price sheets and usage; use Billing →
Reports filtered to Cloud Run / Cloud Storage / and OpenAI’s usage dashboard
for authoritative totals. This doc intentionally does **not** invent a monthly
invoice figure.

---

## Product note that affects cost: Compare vs prebuilds

Browse can serve **prebuilt** topic pages via `GET /api/topic_prebuild` (instant,
no live `v04` fan-out when the sidecar exists).

Compare currently **always** runs live retrieval per entity, then optionally
pulls Key Facts from a prebuild for the synthesis `text_summary`. That makes
Compare both **slower** and **more expensive** than opening the same leaves in
Browse. Wiring Compare to prefer prebuilt cards/figures (skip live on hit) would
cut both latency and Cloud Run / OpenAI spend — not implemented as of this note.

---

## Known limitations

- Snapshot of live flags was taken **2026-08-22**; re-run the `gcloud` checks
  above before assuming the project still matches.
- This agent environment may not always have `gcloud`/`gsutil` on `PATH`; ops
  commands are for Cloud Shell / a machine with GCP CLI + project access.
- Agent SA may lack Cloud SQL / Compute list permissions; Chat cost control
  does not require them.
- Deleting Cloud Run services does **not** delete GCS prebuilds or indexes.

---

## Schema-ish audit fields (for future GCS upload of this note)

```json
{
  "schema_version": "billing_cloud_run_cost_notes.v1",
  "as_of_utc": "2026-08-22",
  "project": "pathology-annotation-project",
  "region": "us-central1",
  "custom_domain": "https://chat.pathologynotebook.com",
  "kept_services": [
    "pathology-hub",
    "pathology-hub-chat-mvp",
    "pathology-hub-journal-api",
    "pathology-hub-pathout-api",
    "pathology-hub-v04"
  ],
  "intended_idle_posture": "automatic_scaling_min_0",
  "primary_cost_driver_when_warm": "pathology-hub-v04",
  "v04_memory_after_oom_mitigation": "16Gi",
  "known_limitations": [
    "Dollar amounts not claimed; use GCP/OpenAI billing consoles",
    "Compare still live-retrieves even when prebuilds exist"
  ]
}
```
