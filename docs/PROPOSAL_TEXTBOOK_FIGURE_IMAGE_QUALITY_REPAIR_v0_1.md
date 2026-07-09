# Proposal: Textbook Figure Image Quality Flag Sidecar + Browser UI

Status: **proposal only, not yet approved or built.**

## Evidence basis

Full-population audit (52,540/52,540 unique textbook images, 0 unparsed
headers, 25 fetch errors) — see
`06_audits/curriculum_provenance_links/v0_1/figure_image_dimension_audit_v0_1/figure_image_dimension_audit_full_v0_1.json`
and the paired `flagged_figure_images_full_v0_1.csv` (4,835 flagged rows,
9.16% overall flag rate).

## Proposed tiers

Per `(source_id, fig_slot)`, using flag rate + signature homogeneity from the
full-population flagged CSV:

### Tier A — suppress rendering, high confidence systematic defect

Flag rate >=30% for that `(source_id, fig_slot)` AND a small number of
near-identical `(width, height)` signatures account for most of the flags
(fixed or near-fixed crop region, not natural figure variation):

| source_id | fig_slot | total | flagged | rate | dominant signature(s) |
|---|---|---|---|---|---|
| cyto_comprehensive_part_one | fig01 | 1,614 | 773 | 47.9% | 2592x235 (759x) |
| cyto_comprehensive_part_two | fig01 | 1,483 | 760 | 51.2% | 2592x235 (748x) |
| gu_practical | fig01 | 1,779 | 731 | 41.1% | 7x7 (478x), 6x7, 88x28, 798-9x308 |
| gu_practical | fig02 | 681 | 358 | 52.6% | 7x7 (185x) |
| gu_practical | fig03 | 45 | 29 | 64.4% | small n, mixed tiny |
| hn_gnepp | fig02 | 554 | 178 | 32.1% | 1313x118/114 |
| hn_gnepp | fig03 | 223 | 91 | 40.8% | 1313x118 |
| hn_gnepp | fig04 | 73 | 26 | 35.6% | mixed |
| gi_atlas | fig02 | 262 | 213 | 81.3% | ~4880-4912 x 288-304 (wide strip) |
| gi_atlas | fig03 | 200 | 147 | 73.5% | 48x6504 tall sliver + 16x16/24x24 icons |
| gi_atlas | fig04 | 160 | 76 | 47.5% | mixed, high rate |

Action: mark every image locator matching these `(source_id, fig_slot)`
pairs **and** falling in the audit's flagged set as `suppress_render`. Do not
suppress the whole slot blanket — only the specific flagged rows (e.g.
`gi_atlas` fig02 still has ~19% presumably-fine images; those stay visible).

### Tier B — warn but still render, moderate confidence

Flag rate 10-30% for that pair (e.g. `hn_gnepp` fig01 at 12.5%,
`cyto_comprehensive_part_one` fig02/fig03 at ~9%, `bst_horvai` fig01 at
9.1%). Action: attach a visible "suspect dimensions" badge with the specific
flag reason(s) from the audit (`extreme_aspect_ratio`, `tiny_image`, etc.),
but still render the image so a human can eyeball it in the browser.

### Tier C — no action

Flag rate <10% and no repeating fixed signature (most other books: e.g.
`hn_thompson`, `breast_atlas`, `bone_dorfman`, `derm_levers`, `gyn_atlas_*`,
`molecular_faq`, `bone_atlas`, `hn_faq`, `cyto_serous_fluids`,
`bone_pattern`, `hn_cardesa`, `breast_faq`, `cyto_gu_paris`). These
individual flagged rows still get carried into the sidecar as Tier B-style
soft warnings (no book-level suppression), since a handful of genuinely bad
extractions exist even in otherwise-healthy books.

## What gets built (sidecar-only, no index/repair-sidecar mutation)

1. **New quality-flag sidecar** (does not touch
   `curriculum_source_locator_index_v0_1.sqlite` or
   `curriculum_record_provenance_sidecar_repaired_v0_1.jsonl`):
   `outputs/curriculum_map_v0_4/curriculum_figure_image_quality_flags_v0_1.jsonl`
   — one row per flagged image locator: `record_id`, `chunk_id`, `source_id`,
   `fig_slot`, `width`, `height`, `flag_reasons`, `tier`
   (`suppress_render` / `warn_render`), derived from the existing full audit
   CSV plus the tier table above. Paired audit JSON with `schema_version`,
   counts, and known limitations.

2. **Browser UI update** (`tools/curriculum_provenance_browser/`):
   - Load the quality-flag sidecar read-only at startup, join by `record_id`
     in memory (no SQLite schema change).
   - `suppress_render` rows: hide the `<img>`, show "Known extraction
     defect — image suppressed" with the flag reason and dimensions instead.
   - `warn_render` rows: show the image with a "⚠ suspect dimensions"
     badge and reason.
   - Add a search filter: "Hide suppressed images" / "Only flagged images".

3. **Tests**: extend `tests/test_curriculum_provenance_browser.py` to cover
   the sidecar join and both render states.

## Non-goals

- Does not reassign, delete, or regenerate any `image_path`/`image_url`.
- Does not touch GCS objects.
- Does not change `scripts/build_curriculum_source_locator_repairs_v0_1.py`
  fallback logic (that's a separate, larger change — the fig01-fallback
  behavior itself — and out of scope here).

## ETA (local build, no network-bound work — the audit data is already local)

| Step | Estimate |
|---|---|
| Build quality-flag sidecar script + run it | 20-25 min |
| Extend browser `app.py` (load sidecar, join, new fields) | 15-20 min |
| Extend `static/index.html` (suppress/warn UI, filter toggle) | 15-20 min |
| Extend tests | 10-15 min |
| Update `docs/ACTIVE_CONTEXT.md` | 5 min |
| **Total** | **~65-85 minutes** |

## Approval needed before building

This proposal requires explicit go-ahead before writing the sidecar or
touching the browser, per the repair-rule stop condition already in place
for this workstream.
