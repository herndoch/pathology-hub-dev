# Consolidation and release plan

Inventory date: October 10, 2026. This plan records reviewed repository structure and proposed next actions. It does not certify application behavior or authorize deletion of branches.

## Observed starting point

- Public repository: `herndoch/pathology-hub-dev`; default branch: `master`.
- Default-branch commit: `5d28c0640ede278c3eaccb58b9cafb32c2002d0d`.
- 49 remote branches and 22 open PRs; 21 PRs were drafts.
- No root README on the default branch. Existing PR #45 provided a 285-line README proposal.
- The local application checkout was eight commits ahead of the default branch and had 69 short-status entries. Those entries include directory summaries; this is not an exact changed-file count.
- No root software license or tracked GitHub Actions workflow was found on the audited default branch.
- No open PR head was a Git ancestor of the default branch. That does not rule out equivalent changes already ported or squash-merged.

This update reuses PR #45 to provide a concise README, a component guide, and this consolidation plan. It preserves the earlier README in Git history.

## Recommended delivery sequence

| Stage | Concrete result | Completion evidence |
|---|---|---|
| 1. Repository orientation | Merge the reviewed documentation in PR #45. | Root README renders; all relative links resolve; component availability is accurately labeled. |
| 2. Teaching maps | Review PR #51 as the leading unified-map candidate, then reconcile the other map proposals. | Generated-data packaging is reviewed; a reader can open a map, select a topic and follow its source link. |
| 3. Application integration | Separate and integrate current application work in focused changes. | Reviewed source/config diff, appropriate offline checks, and the primary user workflow verified at the intended version. |
| 4. Reproducible release | Tag a tested version with release notes, setup instructions, dependency requirements and licensing decisions. | A clean checkout can follow the documented setup; code, external data and service requirements are explicit. |
| 5. Retire superseded work | Close superseded PRs and remove branches only after their retained changes are demonstrated. | An explicit mapping from each retired proposal to its successor or a recorded decision to omit it. |

## Open PR decisions

These are triage recommendations, not completed code reviews. Git ancestry was checked using the live remote head SHAs. "Contained" means the commit history is included, not that every historical behavior is unchanged.

| PR | Work | Recommended next action |
|---|---|---|
| [#51](https://github.com/herndoch/pathology-hub-dev/pull/51) | Unified teaching-map hub | Leading map candidate. Review its 49-file diff and generated assets before integration. |
| [#50](https://github.com/herndoch/pathology-hub-dev/pull/50) | Lecture-to-topic map | Head `96dcf54` is contained in #51 head `96a9676`. Retire only after the successor is integrated and its behavior checked. |
| [#49](https://github.com/herndoch/pathology-hub-dev/pull/49) | No-AI content map | Compare its reader workflow with #51; retain any distinct useful capability, then decide its disposition. |
| [#48](https://github.com/herndoch/pathology-hub-dev/pull/48) | Textbook OncoTree | Compare the sample-modal implementation and assets with #51. Its head is not contained in #51. |
| [#47](https://github.com/herndoch/pathology-hub-dev/pull/47) | Lecture video OncoTree | Compare clip navigation with #50/#51; determine whether it remains a distinct component. |
| [#46](https://github.com/herndoch/pathology-hub-dev/pull/46) | Cloud Run cost notes | Retain useful operational documentation; date any infrastructure observations and check assumptions before reuse. |
| [#45](https://github.com/herndoch/pathology-hub-dev/pull/45) | Project documentation | This consolidation entry point. Documentation only. |
| [#44](https://github.com/herndoch/pathology-hub-dev/pull/44) | Focused Ask queries and stream fallback | Compare with current local query handling, then test retained behavior in the application integration. |
| [#43](https://github.com/herndoch/pathology-hub-dev/pull/43) | Textbook full-text fallback | Compare with the current backend and test its failure path before integration. |
| [#42](https://github.com/herndoch/pathology-hub-dev/pull/42) | Topic-page quality review and repair | Preserve evaluation evidence; separate reusable tooling from dated generated findings. |
| [#41](https://github.com/herndoch/pathology-hub-dev/pull/41) | Remove unsupported Forensic browse entries | Reconcile with the actual current browse taxonomy and source coverage. |
| [#40](https://github.com/herndoch/pathology-hub-dev/pull/40) | Prebuild orchestrator | Keep as an optional processing tool if still used; review run scope and dependencies before executing. |
| [#38](https://github.com/herndoch/pathology-hub-dev/pull/38) | GI Browse reorganization | Compare with the default branch's #39 changes; commit ancestry alone does not establish duplication. |
| [#37](https://github.com/herndoch/pathology-hub-dev/pull/37) | Citation links and entity picker | Head `35d85b4` is contained in #38 head `bb8dfe4`. Reconcile #38 first. |
| [#32](https://github.com/herndoch/pathology-hub-dev/pull/32) | Entity disambiguation and journal retirement | Conflicting proposal. Identify the already-ported #36 portion and preserve any useful remaining changes separately. |
| [#31](https://github.com/herndoch/pathology-hub-dev/pull/31) | ARUP lecture catalog | Classify as a dated source-processing/catalog contribution; review provenance and ongoing usefulness. |
| [#29](https://github.com/herndoch/pathology-hub-dev/pull/29) | Society of '67 report | Keep as historical project reporting; do not present it as current product documentation. |
| [#12](https://github.com/herndoch/pathology-hub-dev/pull/12) | Development environment instructions | Compare with #9–#11 and the current launcher; retain one accurate setup path. |
| [#11](https://github.com/herndoch/pathology-hub-dev/pull/11) | Backend run helper | Targets `cursor/pathology-hub-chat-mvp`, not `master`. Compare with #10 before retargeting or closing. |
| [#10](https://github.com/herndoch/pathology-hub-dev/pull/10) | Development setup and helper | Compare with #9/#11/#12; integrate only the still-needed setup behavior. |
| [#9](https://github.com/herndoch/pathology-hub-dev/pull/9) | Development setup and secret loading | Review against current configuration handling; avoid carrying forward obsolete setup instructions. |
| [#8](https://github.com/herndoch/pathology-hub-dev/pull/8) | Textbook figure-record repair | Conflicting, dated data-repair proposal. Verify whether the repair was already applied and preserve its provenance. |

PR #51 reports 975,805 added lines, mostly generated data. Its diff includes two 248,558-line textbook index copies and two 26,382-line lecture index copies. Decide how the released application should package those assets before making the default branch the delivery artifact.

## First release acceptance criteria

- A new reader can identify what Hub does and reach the appropriate component from the README.
- The selected software version has one documented launch path and explicit service/data prerequisites.
- The default branch and release notes state which map and application features are included.
- Verification includes source-link behavior and a representative reader workflow, not only a successful process launch.
- Third-party assets, credentials, private records and locally generated research outputs are reviewed separately from generic code.
- License terms and the intended distribution of generated assets are settled before calling the package reusable.

The October 10 documentation verification covers links, inventory and change scope. It does not establish a runnable release, deployment parity, clinical validation, or independent educational validation.
