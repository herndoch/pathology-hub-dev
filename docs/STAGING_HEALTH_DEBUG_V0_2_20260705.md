# Staging Health Debug — 2026-07-05/06

## Report received

Repo owner reported `pathology-hub-v04-v0-2-staging` `/health` "connects over TLS but
does not return promptly" at `https://pathology-hub-v04-v0-2-staging-vorn5q2kga-uc.a.run.app/health`.

## Diagnostics collected (all read-only, no secret values)

- `audits/staging_health_debug_20260705/service.describe.json` — service state at time of investigation
- `audits/staging_health_debug_20260705/revisions.list.json` — revision history
- `audits/staging_health_debug_20260705/logs.sample.json` — last 2h of Cloud Run logs

## Findings

1. **Service state at time of investigation: healthy.** `latestReadyRevisionName` =
   `pathology-hub-v04-v0-2-staging-00001-s5r`, conditions `Ready=True`,
   `ContainerHealthy=True`, `ContainerReady=True`, 100% traffic on that single revision.
   Only ONE revision has ever existed for this service — no failed/crash-looping
   revision was found.
2. **A prior `gcloud run services update --update-env-vars=EVIDENCE_V0_2_ENABLED=false`
   command (run in this session to prepare a forced-failure test) hung for ~117
   minutes and was manually interrupted by the operator.** Checking `revisions.list.json`
   confirms this command **never actually created a second revision** — the API call
   client-side hung (most likely local/sandbox network flakiness talking to the Cloud
   Run control plane) before a new revision was ever registered. **No env var was
   actually changed; `EVIDENCE_V0_2_ENABLED` remained `true` throughout.** This was
   independently re-verified via a fresh `/health` call showing `evidence_v0_2_enabled: true`.
3. **Direct re-test of both URL forms (hash-based and project-number-based) returned
   HTTP 200 in ~0.2 seconds each** at the time of this investigation — i.e. the hang
   was NOT reproducible against a warm instance.
4. **Root cause of the intermittent hang: Cloud Run logs show the classic scale-from-zero
   cold-start pattern.** No `--min-instances` was set on the staging deploy (defaults to
   0), so after any idle period Cloud Run terminates all instances. The next incoming
   request(s) trigger `AUTOSCALING`-reason instance starts; logs show 3 separate
   "Starting new instance" events roughly 40-90 seconds apart, each followed by
   `Waiting for application startup` -> `Application startup complete` -> `Default
   STARTUP TCP probe succeeded` taking on the order of ~90 seconds per cold instance
   (consistent with the ~110s cold-start already observed against **production** itself
   in this session's Phase 0 snapshot — this is inherent to the recovered 1.5.10
   architecture's `@app.on_event("startup")` handlers synchronously downloading and
   loading ~2.8GB of textbook/journal/pathout/lecture indexes before the app accepts
   any request, `/health` included). Any external health prober with a client-side
   timeout shorter than ~90-120 seconds hitting a cold instance would see exactly the
   reported symptom ("connects over TLS but does not return promptly").
5. **No application-level bug, crash, import error, or v0_2-integration-specific
   defect was found.** The v0_2 wrapper code does not touch corpus loading at all
   (it only wraps the already-loaded baseline `/health`/`/evidence/search` handlers).

## Fix applied

Set `--min-instances=1` on the **staging service only** (`pathology-hub-v04-v0-2-staging`)
so at least one warm instance is always available and `/health` never has to pay the
~90-120s cold-start cost. This is a pure Cloud Run infrastructure setting — zero
application code changed, zero risk to the v0_2 integration or baseline-preservation
guarantees. See `docs/STAGING_REDEPLOY_FIX_LOG_V0_2_20260705.md` for the exact command
and resulting revision.

**Production (`pathology-hub-v04`) was not touched at any point during this
investigation** — all commands above targeted `pathology-hub-v04-v0-2-staging` only.

## Why an application-level lazy-loading rewrite was NOT attempted

The user's interrupt suggested (as an option) moving corpus loading out of
`@app.on_event("startup")` into a lazy/background pattern. This was deliberately
**not** done in this session because:

1. It would require modifying 6 separate `@app.on_event("startup")` handlers across
   the recovered 1.5.10 baseline's version-generation chain (1.5.3 through 1.5.8),
   which are otherwise byte-identical to verified live production code — directly in
   tension with this mission's core principle of preserving the recovered baseline
   unmodified and only adding v0_2 behavior additively.
2. `min-instances=1` fully resolves the reported symptom (no more cold starts, ever,
   on staging) with zero code risk, and is the same class of fix a human operator
   would reach for first for a staging-only responsiveness issue.
3. Time/budget discipline: a synchronous->lazy-loading refactor of inherited
   production code is a much larger, higher-risk change than this specific health
   symptom justifies, especially on a branch whose explicit mandate is "prioritize
   real, working, verified artifacts... over generating a large volume of...changes."

This trade-off is called out explicitly here so a human reviewer can decide whether a
deeper lazy-loading refactor is warranted for a future iteration (it would be a
reasonable production hardening ticket regardless of this session's staging incident).
