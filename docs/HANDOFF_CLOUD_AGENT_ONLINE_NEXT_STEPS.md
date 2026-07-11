# Handoff: Cloud / online agent — next steps

Date: 2026-07-10  
Workstream: `frontend/pathology_hub_chat_mvp/` (Chat MVP) + optional backend dev  
Branch: `cursor/pathology-hub-chat-mvp`  
Cloud environment: `herndoch/pathology-hub-dev` (Active, with snapshot)  
Mode: **verify cloud health, then execute user-chosen next task (default: topic-page batch)**

Prior pilot handoff (topic-page prepop):  
[`docs/HANDOFF_TOPIC_PAGE_PREPOP_PILOT_NEXT_AGENT.md`](HANDOFF_TOPIC_PAGE_PREPOP_PILOT_NEXT_AGENT.md)

---

## Read first (in order)

1. **This file** — cloud secrets workflow, health checks, branch map
2. `docs/ACTIVE_CONTEXT.md` — current pointer + figure-quality / pilot constraints
3. `docs/HANDOFF_TOPIC_PAGE_PREPOP_PILOT_NEXT_AGENT.md` — pilot results + recommended next batch (N=25–50, seed `20260711`)
4. `docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md` — schemas, STOP rules for prebuild batches
5. `.cursor/environment.json` — cloud install/start (python3.12-venv, GCP JSON materialize, uvicorn :8000)
6. `frontend/pathology_hub_chat_mvp/README.md` — run/secrets/`topic_page` behavior
7. Skim: `frontend/pathology_hub_chat_mvp/scripts/prebuild_topic_pages_pilot_v0_1.py` (reuse for next batch)

---

## Current state

### What works

| Area | Status | Notes |
|------|--------|-------|
| Cloud environment | **Active** | `herndoch/pathology-hub-dev` with snapshot |
| Secrets (4 env vars) | **Working** | Verified on fresh agent: "Local environment status" shows all set; `/api/health` → `secrets.present: true` |
| Chat MVP on cloud | **Running** | `uvicorn` on `0.0.0.0:8000` via `.cursor/environment.json` `start` hook |
| Health endpoint | **200** | `curl http://127.0.0.1:8000/api/health` returns ok |
| Topic-page pilot | **Complete** | N=6 seed `20260710`, 6/6 prebuilt, live fallback verified — see topic-page handoff |
| Browse tag index | **Built** | 8,054 leaves, 17 roots; UI loads `/static/browse_tag_index_v0_1.json` |
| Unit tests | **42/42 green** | Last verified during pilot |

### What does not work / known gaps

| Area | Status | Notes |
|------|--------|-------|
| Secrets after "Start Fresh" | **Broken until re-added** | Setup wipes secrets to "No secrets yet" — must re-add all 4, then **Save** |
| GCP SA key creation | **Sometimes blocked** | Org policy may block SA key creation; user obtained JSON manually |
| Real browser click-through | **Not verified** | Pilot verified API/JS structurally via curl + Python replay; no DOM render observed in cloud |
| Prebuilt pages on cloud | **Unknown** | `outputs/chat_mvp_topic_prepop_v0_1/pages/` is gitignored — cloud agent starts without prebuild cache unless rebuilt |
| Backend local dev branch | **Separate workstream** | `cursor/setup-dev-environment-0d85` / PR #12 — not the Chat MVP cloud default |

### Cloud environment commits (`.cursor/environment.json`)

On `cursor/pathology-hub-chat-mvp`:

- `3eb4aa8` — initial cloud environment config
- `5f69ee2` — install python3.12-venv, materialize GCP JSON
- `be7b1f8` — start uvicorn `0.0.0.0:8000`

---

## Critical secrets workflow

**If secrets break again (especially after "Start Fresh" or environment reset), follow exactly:**

### Step 1 — Open environment settings

1. In Cursor: **Settings → Cloud → Environments** (or environment detail panel for `herndoch/pathology-hub-dev`)
2. Confirm environment shows **Active** (not paused)

### Step 2 — Re-add all four secrets

Add each as **Environment Variable** type (not file upload):

| Name | Value source | Notes |
|------|--------------|-------|
| `OPENAI_API_KEY` | GCP Secret Manager secret `OPENAI` | Copy value from GCP console or `gcloud secrets versions access latest --secret=OPENAI` |
| `PATHOLOGY_HUB_API_KEY` | GCP Secret Manager secret `PATHOLOGY_HUB_API_KEY` | Same pattern |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Full service-account JSON | Paste entire JSON blob (single line or multiline) |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/home/ubuntu/.config/gcp/cursor-sa.json` | Path only — install hook writes JSON to this path from `GOOGLE_APPLICATION_CREDENTIALS_JSON` |

### Step 3 — Click Save

**Critical:** Adding secrets is not enough. You must click **Save** on the environment detail panel. Without Save, the next agent session will show "No secrets yet."

### Step 4 — Start a fresh agent and verify

Ask the agent (or run yourself after cloud VM boots):

```bash
curl -sS http://127.0.0.1:8000/api/health | python3 -m json.tool
```

Expect:

- HTTP 200
- `ok: true` (or equivalent health field)
- `secrets.present: true` (or all four secret names listed as present — no values logged)

If `secrets.present` is false or health fails: **stop** and repeat Steps 2–3. Do not fake synthesis or prebuild without both `OPENAI_API_KEY` and `PATHOLOGY_HUB_API_KEY`.

### What NOT to do

- **Do NOT commit secrets** to git (no `.env`, no JSON key files in repo)
- **Do NOT** assume secrets persist across "Start Fresh" — always re-add + Save
- **Do NOT** log secret values in agent output or audits

---

## Exact next task (agent: ask user, default below)

### Default: topic-page prebuild batch (scale-up from pilot)

Pilot passed cleanly (6/6 ok). Recommended next batch per topic-page handoff:

- **N:** 25–50 leaves
- **Seed:** `20260711` (or `20260710_batch2` if user prefers)
- **Priority tags:** more `Cyto_*` + high-traffic roots (Breast, GI, GU, Skin, HN, GYN)
- **Scripts to reuse:** `build_browse_tag_index_v0_1.py` (index already built — skip unless stale), `draw_pilot_sample_v0_1.py` (adapt for new N/seed), `prebuild_topic_pages_pilot_v0_1.py`

**Before batch:** run browser smoke test if possible (Browse → tile → subcategory → prebuilt leaf + non-prebuilt leaf).

**STOP after batch:** fill "Handoff to following agent" below; update `docs/ACTIVE_CONTEXT.md`; do not start GCS upload unless user reopens.

### Alternative tasks (user choice)

| Task | Branch | When to pick |
|------|--------|--------------|
| Backend local dev / `run_backend_local.sh` | `cursor/setup-dev-environment-0d85` (PR #12) | User wants evidence API changes, not Chat MVP UI |
| Cloud Run cold restart | ops / deploy workstream | Live `/health` still shows stale `textbook_figure_records_loaded` after GCS repair |
| Browse UI polish / root-alias dedupe | `cursor/pathology-hub-chat-mvp` | User wants PathOut "Eye" → ABPath "Eye_Orbit" merge before more prebuilds |
| Phone-only monitoring | any | User just wants to verify cloud agent works from browser — health checks only |

**First message to user:** confirm which task (default batch vs alternative) before large API spend.

---

## Commands for cloud agent to verify health

Run these at session start (cloud VM, repo at `/home/herndonch/pathology-hub-dev` or cloned root):

```bash
# 1. Repo + branch
cd /home/herndonch/pathology-hub-dev
git branch --show-current   # expect cursor/pathology-hub-chat-mvp
git status --short

# 2. Secrets + app health (server should already be up from environment "start" hook)
curl -sS http://127.0.0.1:8000/api/health | python3 -m json.tool

# 3. OpenAI connectivity (optional but recommended before prebuild batch)
curl -sS http://127.0.0.1:8000/api/openai_ping | python3 -m json.tool

# 4. Backend evidence path (requires PATHOLOGY_HUB_API_KEY)
curl -sS -X POST http://127.0.0.1:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"invasive ductal carcinoma breast","sources":["textbooks"],"max_results":3}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("ok", d.get("ok"), "cards", len(d.get("cards") or []))'

# 5. Topic prebuild route (if outputs exist from prior local session — often empty on fresh cloud)
curl -sS 'http://127.0.0.1:8000/api/topic_prebuild?tag=Heme::Other::Normal_Histology::Age_Related_Changes' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("found", d.get("found"), "ok", d.get("ok"))'

# 6. Live topic_page fallback probe
curl -sS -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"ASCUS cytology","mode":"topic_page","category_context":"Cytopathology > Cyto_GYN","include_figures":true,"max_figures":8}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("ok"), d.get("answer_error"), len(d.get("figures") or []))'

# 7. Unit tests (offline, no secret values printed)
frontend/pathology_hub_chat_mvp/.venv/bin/python -m unittest tests.test_pathology_hub_chat_mvp -v
```

If uvicorn is not running (rare if `start` hook succeeded):

```bash
cd frontend/pathology_hub_chat_mvp && .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```

---

## Phone / browser usage notes

User wants to run agents from **phone or browser** at [cursor.com/agents](https://cursor.com/agents).

### Setup (one-time per device)

1. Sign in to Cursor with the same account that owns `herndoch/pathology-hub-dev`
2. Open **Agents** in the mobile browser or desktop browser
3. Start or resume an agent on environment **`herndoch/pathology-hub-dev`**
4. Confirm branch `cursor/pathology-hub-chat-mvp` in the agent's first `git` check

### What works well from phone

- Kicking off a cloud agent with a short prompt ("verify health, then run N=25 prebuild batch seed 20260711")
- Reading agent summaries and handoff docs
- Approving environment secret edits (if user must re-add keys from phone — use GCP console on another device for values)

### What is awkward from phone

- Pasting long `GOOGLE_APPLICATION_CREDENTIALS_JSON` — prefer desktop for secret re-entry
- Visual Browse UI smoke tests — agent can curl APIs; human should spot-check UI on desktop when possible
- Large log output — ask agent to write audits to `outputs/` and summarize counts only

### Suggested phone-friendly prompts

```text
Read docs/HANDOFF_CLOUD_AGENT_ONLINE_NEXT_STEPS.md. Verify /api/health and secrets.present.
Then execute topic-page batch N=30 seed 20260711 per HANDOFF_TOPIC_PAGE_PREPOP pilot recommendations.
STOP and fill handoff section when done.
```

```text
Secrets check only: curl /api/health, report secrets.present and ok. Do not start prebuild.
```

---

## Files / branches map

### Chat MVP + cloud (primary)

| Item | Location |
|------|----------|
| Branch | `cursor/pathology-hub-chat-mvp` |
| App | `frontend/pathology_hub_chat_mvp/app.py` |
| UI | `frontend/pathology_hub_chat_mvp/static/app.js`, `style.css` |
| Cloud hooks | `.cursor/environment.json` |
| Local run (non-cloud) | `frontend/pathology_hub_chat_mvp/scripts/run_local.sh` |
| Prebuild scripts | `frontend/pathology_hub_chat_mvp/scripts/build_browse_tag_index_v0_1.py`, `draw_pilot_sample_v0_1.py`, `prebuild_topic_pages_pilot_v0_1.py` |
| Browse index (UI) | `frontend/pathology_hub_chat_mvp/static/browse_tag_index_v0_1.json` |
| Prebuild outputs (gitignored) | `outputs/chat_mvp_topic_prepop_v0_1/` |
| Tests | `tests/test_pathology_hub_chat_mvp.py` |

### Backend dev (separate)

| Item | Location |
|------|----------|
| Branch | `cursor/setup-dev-environment-0d85` |
| PR | #12 (`run_backend_local.sh` and related backend local setup) |
| Scope | Evidence API / Cloud Run backend — **not** the default cloud Chat MVP `start` command |

**Rule:** Stay on `cursor/pathology-hub-chat-mvp` for Chat MVP, topic prebuild, and cloud UI work unless user explicitly switches to backend branch.

### Docs cross-reference

| Doc | Purpose |
|-----|---------|
| `docs/HANDOFF_CLOUD_AGENT_ONLINE_NEXT_STEPS.md` | **This file** — cloud/on-line agent guide |
| `docs/HANDOFF_TOPIC_PAGE_PREPOP_PILOT_NEXT_AGENT.md` | Pilot results + batch parameters |
| `docs/PLAN_CHAT_MVP_TOPIC_PAGE_PREPOP_v0_1.md` | Full prebuild plan |
| `docs/ACTIVE_CONTEXT.md` | Single current-task pointer |

---

## Definition of done (next session)

### If task = health verification only

- [ ] Cloud environment Active; branch confirmed
- [ ] `/api/health` 200, `secrets.present: true`
- [ ] User informed of any blocker (secrets, uvicorn, missing venv)
- [ ] Handoff section filled with Pass/Blocked

### If task = topic-page batch (default)

- [ ] User confirmed N and seed (suggested 25–50, `20260711`)
- [ ] Health + both API keys verified before prebuild
- [ ] Sample drawn with stratification (≥1 `Cyto_*`, ≥1 PathOut-only if available)
- [ ] All sampled leaves prebuilt via live `/api/chat` `topic_page` (no filter bypass)
- [ ] `outputs/chat_mvp_topic_prepop_v0_1/` audit JSON with real counts
- [ ] Spot-check: `GET /api/topic_prebuild?tag=…` for 2+ leaves
- [ ] Unit tests green (42+ tests)
- [ ] No writes to quality-flags sidecar or curriculum SQLite
- [ ] No secrets committed
- [ ] Handoff section filled; `docs/ACTIVE_CONTEXT.md` updated
- [ ] **STOP** — no automatic next batch

### If task = user-chosen alternative

- [ ] User choice recorded in handoff section
- [ ] Work done on correct branch
- [ ] Definition of done adapted and checked off in handoff

---

## Handoff to following agent

### Status

- [ ] Pass
- [ ] Partial
- [ ] Blocked

Summary (2–4 sentences):

```text
(fill after session)
```

### Cloud / secrets

```text
Environment: herndoch/pathology-hub-dev — Active? secrets.present? /api/health ok?
Any "Start Fresh" or secret re-entry this session? (document for next agent)
```

### Artifacts

| Artifact | Path | Notes |
|----------|------|-------|
| | | |

### Commands run / results

```text
(paste key curl health output counts only — no secret values)
```

### Blockers / limitations

```text
```

### Recommended next step

```text
```

### Files changed

```text
```
