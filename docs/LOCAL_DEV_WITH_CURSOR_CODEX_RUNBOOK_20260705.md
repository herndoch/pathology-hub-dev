# Local Development with Cursor and Codex — Runbook

**Date:** 2026-07-05  
**Audience:** Developer on Windows PC with WSL2, Cursor IDE, and gcloud  
**Project:** Pathology Hub (`pathology-annotation-project`)

---

## Repo orientation

This workspace is a **local dev mirror** — not a full production repo clone. Canonical truth lives in:

| Location | Contents |
|----------|----------|
| `AGENTS.md` | Workspace rules — treat CURRENT_MASTER_SPINE as canonical |
| `project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/` | Primary Codex handoff (docs, schemas, notebooks, codex_local) |
| `project_sources/updates/20260704/pathology_hub_handoff_local_codex_20260704_v3/` | Journal v4.4 + local transition handoff |
| `06_audits/evidence_retrieval_writable/` | Writable benchmark and v0_2 artifacts |
| `release_artifacts/curriculum_map_v0_2/` | Local curriculum map outputs |
| `backend/` | Partial backend source + v0_2 module |
| `docs/` | Production readiness package (this workstream) |
| `commands/` | Read-only recovery and staging validation scripts |

**Note:** Numbered folders from mission brief (`00_start_here/`, `MANIFEST.csv`, etc.) are **not present** at repo root. Use handoff paths above instead.

### Workstream separation (do not blend)

- Evidence RAG ← **you are here**
- Report-style RAG
- Gross template generation
- HTML rendering
- Backend API
- Custom GPT frontend

---

## Which files matter

### Always read first

1. `AGENTS.md`
2. `project_sources/.../docs/00_MASTER_HANDOFF_FOR_CODEX.md`
3. `project_sources/.../support/CURRENT_STATUS_MACHINE_READABLE.json`
4. `project_sources/.../support/GCS_PATH_REGISTRY.csv`
5. `docs/PRODUCTION_READINESS_MASTER_PLAN_20260705.md`

### Backend / API

| File | Role |
|------|------|
| `backend/pathology_hub_v04_curriculum/app.py` | Partial FastAPI app (**1.5.7 — stale**) |
| `backend/evidence_search_reliability_v0_2/` | v0_2 expansion module |
| `backend/query_expansion_rules_v0_2.json` | Abbreviation rules |
| `project_sources/.../codex_local/api_smoke_test.py` | Live smoke test |
| `project_sources/.../reference_artifacts/openapi_pathology_hub_unified_searchEvidence_v1_5_8.yaml` | Production OpenAPI |

### Benchmark / QA

| File | Role |
|------|------|
| `06_audits/evidence_retrieval_writable/benchmark_v0_1/` | v0_1 live baseline |
| `06_audits/evidence_retrieval_writable/benchmark_v0_2/` | v0_2 comparison |
| `scripts/curriculum_map_readiness_v0.py` | Curriculum readiness audit |
| `scripts/build_curriculum_map_v0_2.py` | Local curriculum map builder |

### Curriculum

| File | Role |
|------|------|
| `release_artifacts/curriculum_map_v0_2/curriculum_browser_v0_2.html` | Local browser |
| `release_artifacts/curriculum_map_v0_2/acceptance_summary_v0_2.json` | Build acceptance |

---

## WSL + Cursor setup

### Open workspace

In Cursor: **File → Open Folder** → `\\wsl$\Ubuntu\home\herndonch\pathology-hub-dev`

Terminal: use WSL Ubuntu profile (not PowerShell) for gcloud/python consistency.

### Python environment

```bash
cd ~/pathology-hub-dev
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn google-cloud-storage pydantic pandas rapidfuzz sqlite-utils requests numpy
# Optional for local FAISS experiments:
pip install faiss-cpu openai pillow
```

### Environment variables (`.env` — never commit)

```bash
cat > .env <<'EOF'
GOOGLE_CLOUD_PROJECT=pathology-annotation-project
PATHOLOGY_HUB_API_BASE=https://pathology-hub-v04-vorn5q2kga-uc.a.run.app
PATHOLOGY_HUB_API_KEY=<paste from Secret Manager>
OPENAI_API_KEY=<only if running embeddings locally>
EOF
chmod 600 .env
```

Load in shell:

```bash
set -a && source .env && set +a
```

---

## How to avoid corrupting production

### Never without explicit approval

- `gcloud run deploy` or `gcloud run services update` on `pathology-hub-v04`
- `gcloud storage cp` uploads to `gs://pathology_hub/` live paths
- GPT Builder schema/instruction changes on production GPT
- Promoting v11 curriculum notebook outputs
- Overwriting `03_indexes/` vector artifacts

### Safe defaults

- Read-only: `gcloud storage ls`, `gcloud run services describe`, `gcloud logging read`
- Write only under: `06_audits/`, `docs/`, local `data/`, `outputs/`
- Use `backup_replace_live` promotion pattern only from governed notebooks — not from local scripts
- Treat staging URL as deploy target for v0_2 experiments

### Canonical buckets

| Bucket | Role |
|--------|------|
| `gs://pathology_hub` | Staged/normalized/indexes/audits |
| `gs://pathology-hub-0` | Legacy raw sources (PDFs, videos, WHO JSON) |

Do not overwrite original normalized records — write sidecars, manifests, audits.

---

## gcloud auth

```bash
# One-time login
gcloud auth login
gcloud auth application-default login
gcloud config set project pathology-annotation-project

# Verify
gcloud config get-value project
gcloud auth list
```

### API key (for smoke tests only)

```bash
# Prints secret — do NOT pipe to files in repo
gcloud secrets versions access latest \
  --secret=pathology-hub-api-key \
  --project=pathology-annotation-project
```

Export ephemerally:

```bash
export PATHOLOGY_HUB_API_KEY="$(gcloud secrets versions access latest --secret=pathology-hub-api-key --project=pathology-annotation-project)"
```

Never echo `$PATHOLOGY_HUB_API_KEY` in Cursor chat or commit to git.

---

## How to run tests

### v10.5 smoke (production read-only)

```bash
source .venv/bin/activate
export PATHOLOGY_HUB_API_KEY="..."
python project_sources/updates/20260704/complete_handoff_pathology_hub_codex_20260704/codex_local/api_smoke_test.py
```

### v0_2 unit tests

```bash
cd ~/pathology-hub-dev
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_evidence_*_v0_2.py' -v
```

### Offline regression (no API)

```bash
python 06_audits/evidence_retrieval_writable/benchmark_v0_2/run_offline_v0_2_replay.py
```

### Curriculum map local build (no GCS upload)

```bash
python scripts/build_curriculum_map_v0_2.py \
  --input-dir data/curriculum_map_v0_2 \
  --output-dir outputs/curriculum_map_v0_2
```

### Staging validation (after deploy)

```bash
bash commands/run_v0_2_staging_validation.sh
```

---

## Inspect Cloud Run (read-only)

```bash
bash commands/read_only_cloudrun_source_recovery.sh
```

Manual quick check:

```bash
gcloud run services describe pathology-hub-v04 \
  --region=us-central1 \
  --project=pathology-annotation-project \
  --format='yaml(status.url,status.latestReadyRevisionName,spec.template.spec.containers[0].image)'
```

Health check (no key required):

```bash
curl -sS "https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/health" | python3 -m json.tool
```

---

## Verify GCS paths (read-only)

```bash
gcloud storage ls gs://pathology_hub/03_indexes/textbooks/vector/
gcloud storage ls gs://pathology-hub-0/WHO/WHO_JSON_PROCESSED/ | head
gcloud storage ls -l gs://pathology_hub/06_audits/tags/governance/v10_5/
```

Before downloading large files (>500 MB), check size:

```bash
gcloud storage ls -l gs://pathology_hub/03_indexes/journals/vector/journal_embeddings.npy
```

---

## How to package handoffs

### Production readiness handoff

Include:

- `HANDOFF_PRODUCTION_READINESS_20260705.md`
- All `docs/*_20260705.md`
- `commands/*.sh`
- SHA256 manifest of created files

```bash
cd ~/pathology-hub-dev
find docs commands HANDOFF_PRODUCTION_READINESS_20260705.md -type f | sort | xargs sha256sum > handoff.sha256.txt
tar -czvf pathology_hub_production_readiness_20260705.tgz \
  HANDOFF_PRODUCTION_READINESS_20260705.md docs/ commands/ handoff.sha256.txt
```

### Benchmark review package (existing)

```bash
python 06_audits/evidence_retrieval_writable/benchmark_v0_1/build_review_package.py
```

Do **not** include API keys, `.env`, or multi-GB vector artifacts in handoff zips.

---

## When to use GPT Builder vs Cursor

| Use GPT Builder | Use Cursor |
|-----------------|------------|
| Install/update Action OpenAPI | Edit backend Python, rules JSON |
| Write GPT system instructions | Run benchmarks and audits |
| Run QA prompts from `GPT_BUILDER_FRONTEND_QA_PLAN` | Cloud Run recovery script |
| Test conversational retrieval UX | Integrate v0_2 patch into app.py |
| Validate user-facing wording | Git, Dockerfile, unit tests |

**Rule:** Backend truth is proven by health/manifest/audit — not by GPT behavior alone.

---

## Suggested local directory layout

```text
pathology-hub-dev/
  .venv/                    # gitignored
  .env                      # gitignored — secrets
  backend/
  docs/
  commands/
  data/                     # local GCS downloads (gitignored large files)
  outputs/
  audits/
  06_audits/evidence_retrieval_writable/
  release_artifacts/
  project_sources/
  scripts/
  tests/
```

Add to `.gitignore` if missing: `.env`, `.venv/`, `data/**/*.npy`, `data/**/*.index`, `tmp_artifacts/`

---

## Cursor-specific tips

1. Pin `AGENTS.md` — Cursor reads it as workspace rules
2. Ask Agent to run **read-only** gcloud first; approve writes explicitly
3. Use `@docs/PRODUCTION_READINESS_MASTER_PLAN_20260705.md` for context in new chats
4. Do not let Agent deploy to Cloud Run without your explicit phrase approval
5. Prefer WSL terminal in Cursor over PowerShell for `bash` scripts

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| 401 from API | Use Secret Manager key; header must be `X-API-Key` |
| gcloud project wrong | `gcloud config set project pathology-annotation-project` |
| WSL path not found | Open `\\wsl$\Ubuntu\home\herndonch\pathology-hub-dev` |
| Docker pull denied | `gcloud auth configure-docker us-central1-docker.pkg.dev` |
| Huge GCS download | Use `--probe-only` or sample mode in audit scripts |

---

## Next steps

See `docs/NEXT_10_ENGINEERING_TICKETS_20260705.md` — start with ticket **PH-PR-01** (backend source recovery).
