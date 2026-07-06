# Next Safe Work Order After v0_2 — 2026-07-06

Recommended sequencing for all work following the v0_2 production release. **This
order is a recommendation only — no step below was executed by this task beyond
step 1's initial data-gathering already captured in
`docs/POST_RELEASE_MONITORING_V0_2_20260706.md`.**

## 1. 24-hour production monitoring (in progress / ongoing — human + automated)

- Continue watching Cloud Run error rate, latency, and log warnings for
  `pathology-hub-v04` (revision `pathology-hub-v04-00028-guf`) for the standard 24h
  post-deploy window referenced in `docs/PRODUCTION_READINESS_MASTER_PLAN_20260705.md`'s
  order of operations.
- **Specifically follow up on the health-check responsiveness finding in
  `docs/POST_RELEASE_MONITORING_V0_2_20260706.md`**: two of three `/health` probes in
  this task's check took longer than 30-60s despite `min-instances=1` being
  configured, with Cloud Run logs showing `AUTOSCALING`-triggered cold starts during
  that window. This needs either (a) more monitoring data to see if it recurs, or
  (b) a deliberate investigation into why min-instances=1 did not fully prevent it
  (e.g. checking whether this coincides with real traffic bursts, or whether the
  guaranteed warm instance is being cycled for some other reason). **No config
  change should be made based on a single observation — gather more data first.**
- No code or config action required for this step beyond continued observation.

## 2. Manual GPT Builder Preview smoke test (human-performed)

- Agents cannot open or interact with GPT Builder per the canonical rules — this
  step **must be performed by a human** (Charlie or another authorized reviewer).
- Use the prepared script: `docs/GPT_BUILDER_V0_2_FRONTEND_TEST_SCRIPT_20260705.md`
  (repo root; also referenced from the project-source update package). It covers the
  v0_2.1-fixed abbreviations (LCIS/SSL/AIS), a figure request, an HTML bundle
  request, and the two known documented limitations (Bullous pemphigoid corpus gap,
  `CIS` ambiguity) to confirm the GPT handles them honestly rather than
  hallucinating.
- This step has **no dependency on any code change** — it validates the
  already-deployed production API end-to-end through the actual Custom GPT surface.

## 3. v0_3 investigation branch (investigation only, no code changes)

- Once steps 1-2 show a stable, healthy production state, create a new branch (e.g.
  `v0_3-investigation-<date>`) dedicated to the **investigation steps** described in
  `docs/V0_3_BACKLOG_FROM_V0_2_LIMITATIONS_20260706.md` for both PH-v0_3-01
  (BREAST_002/NOS) and PH-v0_3-02 (GU_005) — direct WHO upstream probes, candidate
  pool inspection, and confirming or refuting the suspected root causes.
- **This branch should not contain any change to
  `backend/pathology_hub_v04_live_recovered/` or
  `backend/evidence_search_reliability_v0_2/`** — only new, standalone probe
  scripts and their output/findings docs. The goal is to convert "suspected root
  cause" into "confirmed root cause" before writing any fix.
- Rationale for investigation-first: PH-v0_3-02 in particular carries **high**
  overfitting risk (a general WHO ranking-weight change affects every WHO query);
  confirming the actual scoring margins first, with real data, is cheaper and safer
  than iterating on a fix blind.

## 4. Actual v0_3 code changes (only after steps 1-3 are complete)

- Only after: (a) 24h monitoring shows a healthy production baseline, (b) the manual
  GPT Preview test passes, and (c) the investigation branch has confirmed (or
  refuted and reclassified) the suspected root causes for both backlog tickets --
  begin actual code changes.
- Each ticket's own "proposed investigation," "tests/benchmark needed," "acceptance
  criteria," and "stop condition" sections (in
  `docs/V0_3_BACKLOG_FROM_V0_2_LIMITATIONS_20260706.md`) govern how that work should
  proceed. In particular:
  - PH-v0_3-01 is scoped narrowly enough (a single, context-gated rule) that it could
    reasonably proceed to a code change first.
  - PH-v0_3-02 should not proceed to a code change until the investigation step
    confirms a specific, scoped scoring adjustment that can be validated against the
    full 1008-row benchmark without regression -- given its **high** overfitting
    risk, it may be reasonable to defer this indefinitely if no safe, general fix is
    found.
- Any v0_3 code change must repeat the same discipline used for v0_2: local tests
  first, staging deploy and full live benchmark rerun, explicit human Go/No-Go
  review, and only then a production deploy with the same no-traffic-candidate ->
  gradual-rollout pattern already proven safe in this release.

## Summary table

| Step | Who | Blocking on | Status |
|---|---|---|---|
| 1. 24h monitoring | Human + automated | Nothing (already started at deploy time) | In progress |
| 2. Manual GPT Preview test | Human only | Step 1 showing stability (recommended, not strictly required) | Not started |
| 3. v0_3 investigation branch | Agent or human | Steps 1-2 substantially complete | Not started |
| 4. v0_3 code changes | Agent or human | Step 3 confirming root causes | Not started |

**This session performed none of steps 2-4.** Step 1's data-gathering portion (a
point-in-time health/smoke check) was performed as part of this task and is recorded
in `docs/POST_RELEASE_MONITORING_V0_2_20260706.md`.
