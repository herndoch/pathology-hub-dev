# Decisions Log Addendum — v0_2 Cold-Start Runtime Correction — 2026-07-06

Chronological, dated. Continues from
`project_sources/updates/20260705/pathology_hub_v0_2_production_release_20260705/docs/DECISIONS_LOG_20260705_v0_2_ADDENDUM.md`
(decisions 1-11).

12. **(2026-07-06) Investigate, read-only, why production `/health` and
    `/evidence/search` intermittently timed out (30-60s+) despite `min-instances=1`
    being reported as set**, per Charlie's explicit instruction not to change any
    Cloud Run setting during the investigation. Result: conclusive root cause found
    — `min-instances=1` had only actually been applied to a new, never-trafficked
    revision (`pathology-hub-v04-00029-rnt`), while production traffic remained
    pinned to the older `pathology-hub-v04-00028-guf`, which never received the
    setting. See `docs/PRODUCTION_COLD_START_INVESTIGATION_20260706.md` (repo root).

13. **(2026-07-06) Charlie explicitly approved applying the recommended fix**
    (shifting traffic to the existing `pathology-hub-v04-00029-rnt` revision, which
    has an identical container image to the currently-serving one) — a
    traffic-pointer-only change between two existing, identical-image revisions,
    with no new code deploy, no GCS change, and no GPT Builder change.

14. **(2026-07-06) Applied the fix and verified it via the revision's own Cloud Run
    status condition** (`MinInstancesProvisioned: True`), not merely the
    service-level setting that had previously appeared correct but was misleading.
    See `docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md` (repo root).

15. **(2026-07-06) Did not declare success on the first slow smoke-test response**
    (27.56s on a WHO+textbooks query) despite the min-instances fix being otherwise
    confirmed successful, per Charlie's explicit instruction to investigate rather
    than assume success on any observed slow/cold-start-like latency. Investigated
    (checked logs for a new instance start — none found; re-ran the identical query
    3 times immediately — consistently sub-second) and concluded this was a
    separate, one-time, first-live-request warm-up phenomenon on the WHO-source
    code path, distinct from the min-instances issue, and explicitly left
    unaddressed (out of scope for a traffic-pointer-only correction).

16. **(2026-07-06) Decided to record this correction as a narrow, superseding-only
    project-source addendum package** (this package) rather than a full new release
    package, since the underlying v0_2 application code, benchmark results, and
    accepted-limitation decisions are all unchanged — only the live-serving-revision
    and min-instances-effectiveness facts needed correcting.
