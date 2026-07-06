# Cursor / WSL Preflight — 2026-07-05

**Purpose:** Verified current environment state before any production-adjacent work in this session.

## Workspace

```
$ pwd
/home/herndonch/pathology-hub-dev

$ git branch --show-current (before this session)
evidence-search-reliability-v0_2-prod

$ git branch --show-current (this session, created)
production-v0-2-recovery-release-20260705
```

Working tree had uncommitted changes and untracked files from a prior session (docs, scripts, backend/evidence_search_reliability_v0_2/, recovered_backend/v04_8_cloudbuild_source/, etc.) — see `audits/local_workspace_snapshot_20260705/git_status_pre_production_agent.txt` for the exact pre-session `git status --short` output.

## Tooling versions

```
$ python3 --version
Python 3.14.4

$ gcloud --version
Google Cloud SDK 575.0.0
alpha 2026.06.26
beta 2026.06.26
bq 2.1.33
bundled-python3-unix 3.14.5
core 2026.06.26
gcloud-crc32c 1.0.0
gsutil 5.37
preview 2026.06.26
```

## gcloud auth / config (no secrets)

```
$ gcloud config list --format=json
{
  "core": {
    "account": "herndon.charlie@gmail.com",
    "disable_usage_reporting": "True",
    "project": "pathology-annotation-project"
  }
}

$ gcloud auth list --format=json
[
  {"account": "admin@pathologynotebook.com", "status": ""},
  {"account": "herndon.charlie@gmail.com", "status": "ACTIVE"}
]
```

Active account matches the expected `herndon.charlie@gmail.com`; project is already set to canonical `pathology-annotation-project`. No `gcloud auth login` was required or performed.

## Directory: not a git repo per system info, but IS a git repo

The user-info block reported "Is directory a git repo: No", but `git status`/`git branch` succeeded normally, confirming this is in fact a working git repository. Treated as a git repo for all work in this session.

## Safety posture at start of session

- No production deploy, traffic shift, or GCS deletion performed prior to this preflight.
- Read-only `gcloud run services describe` on `pathology-hub-v04` is authorized and was used only for the Phase 0 snapshot below.
- No secret values printed in this document or anywhere in the session output.
