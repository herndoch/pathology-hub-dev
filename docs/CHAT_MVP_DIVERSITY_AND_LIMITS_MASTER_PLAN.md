# Chat MVP: Diversity, Limits, WHO Cross-Entity Extraction & Figure Quality — Master Plan

Last updated: 2026-07-10 (single session). Workstream: `frontend/pathology_hub_chat_mvp/`
(Pathology Hub Chat MVP), branch `cursor/pathology-hub-chat-mvp`. Kept separate from the
curriculum provenance browser / other workstreams per `AGENTS.md`.

## Executive summary

Live testing of the Browse/`topic_page` feature flagged four problems:

1. `max_results` and the `topic_page` evidence caps (`TOPIC_PAGE_MAX_CARDS`,
   `TOPIC_PAGE_MAX_FIGURES`) felt arbitrary/too tight, and nobody had measured the real
   backend or model ceiling.
2. Source diversity: PathOut/WHO could still crowd out textbooks/journals/videos on real
   topic pages.
3. WHO results are single-entity-tagged at the card/page level, so a page's own
   Terminology/Microscopic/DDx prose often mentions *other* related entities (synonyms,
   subtypes, DDx) that never surface as their own retrievable hits or cross-links.
4. A known-bad figure family (`cyto_comprehensive_part_two`, part of a larger set of
   previously flagged textbook figure families) can render a blank/broken image in the
   citation/figure modal.

This session **measured** the real backend/model limits (not guessed), **shipped** revised
caps and a per-source-quota reranker, **prototyped** (and got working, with caveats) a WHO
section-scoped cross-entity extractor, **shipped** a client-side dead-image safeguard, and
**wrote this plan** for the remaining figure-quality remediation and WHO-taxonomy-breadth
work. No GCS/Cloud Run changes; no mutation of the quality-flags sidecar or curriculum
SQLite; single backend operation (`POST /evidence/search`) throughout.

---

## Part 1 — Real limits: what was measured, what shipped

### 1a. `max_results`: live-probed, NOT arbitrary

Called `PathologyHubClient.search()` directly against the live Cloud Run backend
(`pathology-hub-v04`) with `max_results` from 11 up to 100, for **every** supported source
family (`textbooks`, `who`, `pathout`, `journals`, `lectures`, `videos`), bypassing the
client-side Pydantic bound entirely.

**Result: the backend itself hard-rejects `max_results > 10` with HTTP 422** —
`{"type": "less_than_equal", "loc": ["body", "max_results"], "msg": "Input should be less
than or equal to 10", "ctx": {"le": 10}}` — for every source, every time. `max_results=10`
returns 10 results; `max_results ≤ 10` always worked (5 and 10 both tested `ok`).

**Verdict: `app.py`'s `le=10` bound was already exactly correct, not conservative.** There is
no room to raise it — comprehensiveness for `topic_page` has to keep coming from the
multi-query fan-out (more calls at 10 each), which is what was already built. Kept `le=10`
unchanged; added a code comment recording this finding so a future agent doesn't re-attempt
raising it without re-probing.

### 1b. Token/context budget: 72 cards was conservative, not a real ceiling

Measured the full deduped/diversified evidence bundle JSON size for two real topic-page
probes at the *old* cap (72 cards / 20 figures):

| Query | Bundle size (old 72-cap) | Approx tokens (`len//4`) |
|---|---|---|
| ovarian high-grade serous carcinoma | 255,170 chars | ~63,800 |
| salivary mucoepidermoid carcinoma | 248,441 chars | ~62,100 |

`OPENAI_MODEL` default is `gpt-4.1-mini`. Verified its **published context window is
1,047,576 tokens** (OpenAI API docs, current as of this session) — the colloquial "1M token"
figure. ~62k-64k tokens is **under 7% of that budget**. The real deduped/unique card count for
both probes was only ~106-112 (well under a new 120 cap), and unique figures deduped to
~39-50 (well under a new 40 cap).

**Verdict: 72/20 was a conservative guess, not a measured ceiling.** Context window is not
the binding constraint at all; the actual costs of raising the cap are OpenAI $ and synthesis
latency (more input tokens), which are modest at this scale and acceptable for a mode whose
whole purpose is comprehensiveness.

### 1c. A real bug found while measuring: `lectures`/`videos` are the same corpus

While instrumenting raw card counts, found that **`sources: ["lectures"]` and
`sources: ["videos"]` return byte-identical `lecture_results`/`video_results` content (same
`chunk_id`s) from the live backend, regardless of which one is requested** — confirmed by
diffing the two result keys' `chunk_id` lists (identical) and their `source_status` (both
marked `"ok"` no matter which single one was requested). This matches the already-documented
"lecture/video corpus has one constant `source_id`" limitation, but goes further: requesting
*both* wastes an entire redundant backend call per query variant and floods the raw card pool
with literal duplicates.

**Shipped fix:** `TOPIC_PAGE_SOURCES` in `app.py` now excludes `lectures` (keeps `videos`) —
cuts topic-page call count from 24 to 20 per request with zero coverage loss. Also added
`dedupe_cards`/`dedupe_figures` to the **regular** (non-topic-page) retrieval path in
`app.py` (`api_search`, `api_chat`), which previously had no dedup at all — so a sidebar user
checking both "Lectures" and "Videos" boxes would have seen literal duplicate cards.

### 1d. Shipped: revised caps + explicit per-source-quota floor

Code changes (`frontend/pathology_hub_chat_mvp/pathology_backend.py`, `app.py`):

- `TOPIC_PAGE_MAX_CARDS`: **72 → 120**
- `TOPIC_PAGE_MAX_FIGURES`: **20 → 40**
- New `TOPIC_PAGE_MIN_CARDS_PER_SOURCE = 8` constant
- `cap_cards_diverse(cards, max_cards, min_per_source=0)` — new optional `min_per_source`
  parameter (backward compatible; default `0` reproduces the exact prior behavior). When set,
  every source family with ≥1 result is guaranteed up to `min_per_source` cards *before* the
  standard round-robin spends the remaining budget, protecting a thin family (e.g. journals)
  from being crowded out by a dominant one (e.g. PathOut) in a small-cap/large-imbalance case.
  Plain round-robin (the pre-existing behavior) already gave a roughly even split in the two
  real probes below — the explicit floor is a safety net for cases round-robin alone
  wouldn't naturally balance (see adversarial unit test
  `test_cap_cards_diverse_min_per_source_protects_thin_family`).
- `SearchRequest.max_results` in `app.py`: **unchanged** (`le=10`), now with an explanatory
  comment pointing at this doc.

### 1e. Before/after, re-probed live

Same two real topic-page queries, before (old code, 72/20 caps, `lectures`+`videos` both
requested) vs after (new code, 120/40 caps, `lectures` dropped, `min_per_source=8`):

**Ovarian high-grade serous carcinoma**

| Metric | Before | After |
|---|---|---|
| Backend call count | 24 | 20 |
| Retrieval elapsed | 33.2s | 8.3s* |
| Raw cards (pre-dedup) | 299 | 220 |
| Deduped unique cards | 112 | 115 |
| Cards sent to synthesis | 72 (capped, truncating real evidence) | 115 (**all** unique evidence — cap of 120 wasn't even hit) |
| Cards by source (post-cap/final) | who 14, textbooks 15, journals 15, pathout 14, videos 14 | who 14, textbooks 26, journals 35, pathout 17, videos 23 |
| Figures (final) | 20 (capped) | 39 |
| Bundle size (approx tokens) | ~63,800 | ~104,459 (~10% of context window) |

**Salivary mucoepidermoid carcinoma**

| Metric | Before | After |
|---|---|---|
| Backend call count | 24 | 20 |
| Retrieval elapsed | 29.3s | 7.3s* |
| Raw cards (pre-dedup) | 290 | 217 |
| Deduped unique cards | 106 | 113 |
| Cards sent to synthesis | 72 (capped) | 113 (**all** unique evidence) |
| Cards by source (post-cap/final) | who 12, textbooks 15, journals 15, pathout 15, videos 15 | who 12, textbooks 33, journals 28, pathout 19, videos 21 |
| Figures (final) | 20 (capped) | 40 (capped — 50 unique existed) |
| Bundle size (approx tokens) | ~62,100 | ~106,726 (~10% of context window) |

*\*Retrieval elapsed-time drop is real (fewer redundant calls) but the before/after runs were
not controlled for backend load variance between the two separate live sessions — treat the
directional improvement (fewer calls, less duplicate processing) as solid, the exact 4x
speedup number as anecdotal, not a guaranteed repeatable benchmark.*

**Net result:** at the new caps, **all unique deduped evidence made it to synthesis for both
real probes** (capping didn't even engage for cards on either query — 115 < 120, 113 < 120),
and per-source distribution is healthy and not obviously dominated by any one family. Token
cost roughly doubled (~63k → ~105k) but stays under 10% of the model's real context budget.

### What's NOT done in Part 1

- The `min_per_source` floor's adversarial-imbalance behavior is unit-tested but wasn't
  exercised by either live probe (cap wasn't hit). Re-verify on a topic with a much larger
  raw card pool (e.g. a very well-covered common entity) once caps have been live for a
  while.
- No monitoring/alerting was added if `cards_capped == TOPIC_PAGE_MAX_CARDS` starts happening
  frequently in practice — the `debug.cards_raw`/`cards_deduped`/`cards_capped` fields already
  in the response are enough to eyeball this manually via the debug panel for now.

---

## Part 2 — WHO section-scoped cross-entity extraction (prototype)

### Verdict: **feasible, working prototype shipped, NOT wired into the UI**

### What was probed

Live-probed `/api/search` with `sources: ["who"]` for "traditional serrated adenoma",
"sessile serrated lesion", and salivary/myoepithelial topics, at `excerpt_char_limit=4000`
(the allowed max) and `compact=False`.

**Key finding — the WHO corpus is already pre-chunked more granularly than assumed.** Every
`who_results[]` card carries explicit `entity_name` and `section` fields (section values
observed: `core`, `microscopic`, `related_terminology`, `differential_diagnosis`,
`subtypes`, ...) — **and this metadata survives `compact=True`**, so it's usable in
production, not just a debug-mode artifact. Excerpts were short (down to ~150-1,200 chars
even at the 4,000-char ceiling) — **not because of truncation**, but because each chunk is
already a specific, granular section, not a whole-page dump.

This changes the originally-planned approach: instead of regex-detecting inline
"## Terminology" markdown headers inside one long page's prose (the original hypothesis),
the section boundary is **already a first-class API field** — a much more reliable join key.
`differential_diagnosis`-section chunks turned out to be the highest-signal section in
practice (short but densely packed "includes X, Y, and Z" / "distinguished from X" real
entity enumerations), so they were added as a first-class extraction target alongside the
originally-requested Terminology/Microscopic/Histopathology.

Real example, captured live (WHO entity "Epithelial-myoepithelial carcinoma",
`section: differential_diagnosis`):

> "The differential diagnosis includes other salivary gland tumours with biphasic and/or
> clear cell morphology, such as adenoid cystic carcinoma, basal cell adenocarcinoma,
> pleomorphic adenoma, myoepithelial carcinoma, and clear cell carcinoma."

### What was built

New, isolated module `frontend/pathology_hub_chat_mvp/who_section_mentions.py` (pure Python
text processing on already-fetched card data — no new backend operation):

- `who_section_mentions(card, taxonomy_leaves=None)` — main entry point. Only processes cards
  whose `section` is in `TARGET_SECTIONS` (`differential_diagnosis`, `microscopic`,
  `histopathology`, `terminology`, `related_terminology`). Extracts DDx-signal candidate
  phrases ("such as X, Y", "distinguished from X", "differentiate from X", "vs X", "compared
  with X"), fuzzy-matches each against a taxonomy leaf, and returns **only grounded matches**:
  `{candidate_phrase, matched_leaf, snippet, source_url, source_entity, source_section}`.
  Never returns a bare unmatched phrase.
- `load_taxonomy_leaf_names()` — lightweight regex-based mirror of `BROWSE_TAXONOMY`'s leaf
  entity names out of `static/app.js` (not a full JS parser; falls back to a small built-in
  list if the regex can't find the array, so it degrades gracefully rather than crashing).
- `fuzzy_match_taxonomy()` — ported/tightened version of `app.js`'s `findTaxonomyMatch`.

**A real false-positive was found and fixed during this spike, worth flagging explicitly:**
naive token-overlap fuzzy matching initially linked "myoepithelial carcinoma" to the
unrelated leaf "Endometrioid carcinoma" (both share only the generic word "carcinoma"), and
"clear cell carcinoma" to "Clear cell renal cell carcinoma" (share only "clear cell"). Fixed
by excluding a `_GENERIC_PATHOLOGY_TOKENS` set (`carcinoma`, `tumour`, `cell`, `clear`,
`gland`, etc.) from the overlap-scoring logic — after the fix, the same live-captured excerpt
correctly matches only `Adenoid cystic carcinoma`, `Basal cell carcinoma`, and `Pleomorphic
adenoma` (verified in `tests/test_pathology_hub_chat_mvp.py`'s
`TestWhoSectionMentions.test_does_not_hallucinate_generic_word_only_overlap`, a regression
test built directly from this real failure). This is a reminder that **any future extension of
this prototype needs the same generic-token guard, not just a naive fuzzy-match port.**

5 offline unit tests added (`TestWhoSectionMentions`), all using real live-captured excerpt
text as fixtures (not invented): finds real cross-mentions, rejects the generic-overlap false
positive above, ignores non-target sections, never links an entity's own page to itself, and
handles malformed/missing cards.

### What's honestly NOT done

- **Not wired into the UI or synthesis pipeline.** This is a tested, working, standalone
  module — integrating it into the topic-page renderer (rendering matched cross-mentions as
  clickable taxonomy links, similar to the existing DDx cross-link feature) is real, non-trivial
  scope deferred to a future session (see Phase plan below).
- `extract_ddx_candidates()`'s regex-based candidate splitting is a reasonable v0, not
  bulletproof — compound phrases with unusual punctuation, semicolon-separated lists, or
  cues not in the current cue list will be missed (false negative, which is the safer failure
  mode here, but still a real coverage gap).
- Only tested against a handful of real excerpts from 2-3 topics. Broader validation across
  many more WHO entities/sections is needed before this is trusted at scale.

---

## Part 3 — Figure/Image Quality: Full Remediation Plan

The user hit a blank/broken figure modal from `cyto_comprehensive_part_two` — a family
**already known-bad** per a prior figure-quality-flag workstream. This section covers the
full remediation picture, not just that one family.

### 3a. Known-bad figure families already identified (existing audits, real numbers)

Per `06_audits/curriculum_provenance_links/v0_1/figure_image_quality_flags_audit_v0_1.json`
(read-only reference, not regenerated this session):

- **4,835 total flagged rows** across the whole textbook figure corpus: **3,382 Tier A
  (`suppress_render`)**, **1,453 Tier B (`warn_render`)**.
- Worst offenders by `source_id` (`_total` flagged / `suppress_render` count):
  - `gu_practical`: 1,118 / **1,118** (100% suppress — degenerate 7×7 images, per
    `docs/PROPOSAL_TEXTBOOK_FIGURE_IMAGE_QUALITY_REPAIR_v0_1.md`)
  - `cyto_comprehensive_part_one`: 838 / 773 (fixed 2592×235 crop bug)
  - `cyto_comprehensive_part_two`: 804 / 760 (same fixed 2592×235 crop bug — this is the
    family the user actually hit live)
  - `hn_gnepp`: 801 / 295 (similar fixed-crop signature, ~1313×118, per ACTIVE_CONTEXT.md)
  - `gi_atlas`: 457 / 436 (fig02/03/04 disproportionately affected per the proposal doc)
- Flag reasons: `extreme_aspect_ratio` 3,818, `tiny_image` 1,796,
  `wide_strip_header_footer_suspect` 565, `tall_strip_suspect` 152, `fetch_error` 25.

### 3b. Already fixed elsewhere vs. still exposed via the Chat MVP

**The curriculum provenance browser** (`tools/curriculum_provenance_browser/`) already loads
this quality-flags sidecar and suppresses/warns on flagged rows in its own UI, joined against
**its own SQLite index** (`curriculum_source_locator_index_v0_2.sqlite`).

**The Chat MVP is a completely different code path.** It talks to the **live**
`POST /evidence/search` Cloud Run endpoint (`pathology-hub-v04`), not the local SQLite index.
This session did **not** get a chance to live-probe a real textbook figure card's exact field
schema to confirm a join key against the quality-flags sidecar (`chunk_id`/`record_id` +
`source_id`/`fig_slot`) before wrap-up was requested — **this is an open, unverified question,
not a confirmed "no join key exists" finding.** From the sidecar's own schema (already
inspected this session), its `chunk_id` format is `tbchunk:<source_id>:<page>_<slot>` and
`record_id` is `textbooks:` + that same string — if the live evidence API's textbook cards use
the same `tbchunk:...` scheme for their own `chunk_id`/`record_id` fields (plausible, given the
`card_identity_key()` logic in `pathology_backend.py` already expects `chunk_id`/`record_id`
on textbook cards, but **not confirmed byte-for-byte this session**), a join is very likely
feasible and cheap. **Bottom line: as far as this session could determine, every
quality-flagged bad image is still being served live through the Chat MVP with zero
server-side suppression today** — the local browser's fix does not reach this code path at
all.

### 3c. Root cause categories to plan against

- **(a) Known fixed-crop-bug source families** — a finite, enumerable list
  (`cyto_comprehensive_part_one`/`two`, `hn_gnepp`, `gu_practical`, `gi_atlas` fig02-04, per
  the counts above). Cheap, precise fix: suppress by `(source_id, fig_slot)` pattern match
  alone if the live card carries those fields (needs verification, see 3b).
- **(b) Generically dead/404'd URLs from the earlier GCS figure-delete cleanup.**
  `docs/ACTIVE_CONTEXT.md` records a prior pass that repaired 3,055 deleted GCS URIs in the
  **docstore** and **web figure map** — but its own "Follow-ups (not done)" section explicitly
  flags that **`textbook_lean_figures.jsonl` may still reference deleted URIs** and was *not*
  covered by that repair pass. This session did not verify whether the live API actually
  serves figure URLs from `textbook_lean_figures.jsonl` or from the already-repaired
  docstore/web-map — that's a real open question for Phase 2 below.
- **(c) Unknown/un-audited images** — genuinely low-quality or mis-cropped images that were
  never flagged by any existing audit (the existing audit only covers rows already present in
  a specific flagged CSV, per that audit's own `known_limitations`). A live link-liveness
  sample (Phase 2) is the only way to estimate this category's real size.

### 3d. What shipped this session (Phase 0)

Added a global, capture-phase `error` event listener in `static/app.js` (plus a matching
`.img-broken` style in `static/style.css`) that catches **any** `<img>` load failure anywhere
in the app — figure strips, citation thumbnails, topic-page gallery, and the media preview
modal — and swaps in a small inline-SVG "Image unavailable — known extraction defect or dead
link" placeholder instead of an empty broken-image box. This is network-independent (the
placeholder is a data URI, so it can never itself 404), requires no join key, and covers
**every** root-cause category above (known-bad families, newly-dead URLs, and genuinely
unknown bad images alike) as a safety net. It does not distinguish *why* an image failed —
that's what Phases 1-2 below are for.

### 3e. Phased remediation plan (for the next agent)

- **Phase 0 (done this session):** client-side `<img>` `error` fallback — see 3d. Ships
  immediately, zero risk, covers all root causes as a blunt safety net.
- **Phase 1 (needs a join-key verification first):** if a reliable join key is confirmed (see
  3b — inspect one real live textbook evidence card's `chunk_id`/`record_id`/`source_id`
  fields side-by-side with a known Tier-A sidecar row), add a Chat-MVP-side filter (in
  `pathology_backend.py`, alongside `dedupe_cards`/`cap_cards_diverse`) that drops or
  down-ranks `suppress_render`-tier figures/cards before they ever reach the UI, using the
  **existing, read-only** `curriculum_figure_image_quality_flags_v0_1.jsonl` sidecar (do not
  regenerate or mutate it, per `AGENTS.md`). This is strictly better than Phase 0 for the
  ~3,382 already-known Tier A images, since it prevents the broken card from being cited at
  all, not just from rendering an empty image.
- **Phase 2 (do this as a real experiment, not a guess):** a live link-liveness audit of what
  the Chat MVP's evidence API **actually returns today** — HEAD-probe a real sample of
  `figure_url`/`page_image_url` values returned across several real topic-page queries, count
  dead vs. alive, report the real percentage. **Not done this session** (ran out of session
  time after the max_results/WHO-excerpt probes and a network-access review gate); this is
  the single most valuable next step before deciding how urgent Phase 3 is, since it would
  directly measure how much of the corpus is affected by category (b) (still-dead GCS URIs
  outside the prior repair's scope) and category (c) (unaudited) rather than just category
  (a) (already-known families).
- **Phase 3 (needs explicit user approval per `AGENTS.md` — do not execute without it):** if
  Phase 2 shows a meaningful dead-link rate, a backend-side audit+repair pass analogous to the
  prior `repair_textbook_figure_index_after_delete_v0_2.py` pattern, scoped to whatever new
  dead URIs Phase 2 discovers (likely including `textbook_lean_figures.jsonl` if that's
  confirmed to be the live API's figure source and confirmed unrepaired). Any such pass must
  produce an audit JSON with `schema_version`, input paths, output paths, counts, and known
  limitations, per `AGENTS.md`, and must not overwrite original normalized records — this is
  a proposal for future work, explicitly not executed now.

---

## Full WHO/WHO-like Taxonomy Coverage for Browse Navigation (Planning Only — Not Started)

**No taxonomy expansion or data-source integration was implemented this session. This section
is a documented next-phase recommendation only, per explicit user instruction to "just make a
plan for all this right now."**

### Current state, honestly

`BROWSE_TAXONOMY` in `static/app.js` is a small, hand-curated, editorially-chosen list — **17
top-level categories, ~85 leaf entities** (counted directly from the current file this
session) — deliberately built to validate the nested tile/chevron/topic-page UX pattern, not
as a real coverage map of everything the backend/WHO corpus actually has. It is explicitly
documented in `app.js`'s own comment as "NOT sourced from any live index."

### What "the entirety of WHO entities" would require

The Chat MVP's single allowed operation is `POST /evidence/search` — there is no WHO
entity-list/catalog endpoint exposed to it. Discovering the full WHO entity set from this
workstream alone would have to be **indirect**: e.g. broad per-category probe queries against
`sources: ["who"]` and aggregating the distinct `entity_name` values seen across many results
(imperfect — only surfaces entities that happen to rank for whatever query was tried, not a
guaranteed-complete enumeration).

**Separately** (read-only reference only, not a merge — different workstream per
`AGENTS.md`): the curriculum provenance browser's own SQLite index
(`outputs/curriculum_map_v0_4/curriculum_source_locator_index_v0_2.sqlite`) already has a rich
`approved_tag`/`root` taxonomy across ~160k records, including WHO-tagged rows. This is a
plausible **structure source** for a future taxonomy-generation approach, but per the same
honesty-about-counts rule as everywhere else in this doc: having that data in the *other*
index does not mean it is "indexed" or "browsable" for Chat MVP purposes — every leaf would
still need to be proven live via `/evidence/search` before being presented as browsable here.

### Two candidate approaches (described, NOT built)

- **(a) Curated expansion at scale.** Hand-grow `BROWSE_TAXONOMY` using the real WHO
  classification volumes' own tables of contents (WHO publishes ~14 organ-system "blue books,"
  each with a real chapter/entity structure) as the source of truth for what to add — still
  fully static, just much bigger (hundreds of leaves instead of ~85). *Pros:* accurate,
  editorially controlled, matches the existing curation quality bar. *Cons:* large manual
  effort, doesn't scale automatically, needs re-curation whenever WHO publishes an update.
- **(b) Data-driven generation.** A read-only bridge that generates the taxonomy tree from a
  real structured source — either WHO's own table-of-contents/entity list if obtainable, or
  the curriculum provenance SQLite's `approved_tag` hierarchy as **reference structure only**.
  *Pros:* scales far beyond hand-curation. *Cons:* needs careful boundary-respecting design (a
  read-only reference, never a merge, to keep workstreams separate per `AGENTS.md`), and needs
  an explicit step to confirm live evidence actually returns something for a generated leaf
  before presenting it as "browsable" — otherwise this approach risks silently listing dead-end
  topics.

### This is the same problem as Part 2, at a bigger scale

Expanding taxonomy **breadth** (this section) and improving per-entity **depth/relatedness**
(Part 2's WHO section-mention extraction) are two dimensions of one underlying goal: today,
clicking a WHO-classified leaf only surfaces that one entity's own isolated evidence. Part
2's extractor — since it proved feasible this session — is exactly the mechanism that would
make a larger taxonomy actually pay off: without it, more leaves just means more isolated
single-entity pages; with it, each leaf page can also surface its real cross-referenced
neighbors (synonyms, DDx, subtypes) grounded in the same live evidence.

**Recommendation for the next agent:** sequence these together, not as two unrelated backlog
items — expand breadth first (approach (a) or (b) above), *then* wire in Part 2's extraction
so each newly-added leaf page enriches beyond its own isolated WHO text, rather than building
either one in isolation.

---

## Prioritized plan for the next agent

1. **Verify the figure quality-flags join key live** (Part 3, Phase 1 prerequisite) — pull one
   real live textbook evidence card with a figure, compare its `chunk_id`/`record_id` fields
   byte-for-byte against a known Tier-A row in
   `curriculum_figure_image_quality_flags_v0_1.jsonl`. Cheap, fast, unblocks the highest-value
   figure fix.
2. **Run the Phase 2 live link-liveness audit** (Part 3) — HEAD-probe a real sample of
   `figure_url`/`page_image_url` from several real topic-page queries; report the real dead
   percentage. This determines whether Phase 3 (backend audit+repair, needs explicit user
   approval) is actually warranted.
3. **Confirm whether `textbook_lean_figures.jsonl`** (flagged as a possible remaining gap in
   `docs/ACTIVE_CONTEXT.md`'s "Follow-ups (not done)") is what the live API actually serves
   figure URLs from, and whether it needs its own repair pass analogous to the prior
   docstore/web-map repair.
4. **Wire Part 2's `who_section_mentions()` into the topic-page UI**, if the next agent judges
   the prototype solid enough — render matched cross-mentions as clickable taxonomy links
   (reusing the existing DDx cross-link pattern in `app.js`'s `renderDifferentialSection`),
   grounded strictly to the matched card's own URL/snippet, same as today's DDx links.
5. **Per-source-family quota tuning based on real usage** — `TOPIC_PAGE_MIN_CARDS_PER_SOURCE
   = 8` is a reasonable first guess, not yet stress-tested against a topic with a much larger
   raw card pool (see Part 1's "what's not done"). Revisit once the new caps have been live
   for a while.
6. **WHO/WHO-like taxonomy breadth expansion** (this doc's dedicated section above) — pick
   approach (a) or (b), sequenced *before* full Part 2 integration per that section's
   recommendation.
7. **Backend-side improvements requiring explicit user approval per `AGENTS.md`** (do not
   start without asking first): the Phase 3 figure audit+repair pass above; any request to the
   backend team for WHO subsection chunking finer than what already exists (turned out to be
   unnecessary — the existing `section` field already provides this); any change that would
   mutate the quality-flags sidecar or curriculum SQLite (should stay read-only regardless).
8. **From `docs/ACTIVE_CONTEXT.md`'s still-open items:** the journals `source_url`
   liveness caveat (still unresolved — Cloudflare bot-blocking prevented a conclusive live
   check in a prior session) and per-lecture diversification (still blocked on a more granular
   backend `source_id`/`lecture_id`, unrelated to this session's `lectures`/`videos`
   duplicate-corpus finding, which was about the *family* name, not per-lecture granularity)
   both remain open and relevant.

---

## Files touched this session

- `frontend/pathology_hub_chat_mvp/pathology_backend.py` — new/revised constants, enhanced
  `cap_cards_diverse()` with `min_per_source`.
- `frontend/pathology_hub_chat_mvp/app.py` — `TOPIC_PAGE_SOURCES` drops `lectures`,
  dedupe added to the regular retrieval path, `min_per_source` wired in, comments recording
  the live-measured `max_results` finding.
- `frontend/pathology_hub_chat_mvp/who_section_mentions.py` — new prototype module (not wired
  into the UI).
- `frontend/pathology_hub_chat_mvp/static/app.js` — global `<img>` `error` fallback.
- `frontend/pathology_hub_chat_mvp/static/style.css` — `.img-broken` placeholder style.
- `tests/test_pathology_hub_chat_mvp.py` — new/updated tests for all of the above.
- `docs/CHAT_MVP_DIVERSITY_AND_LIMITS_MASTER_PLAN.md` — this document.
- `docs/ACTIVE_CONTEXT.md` — milestone entry pointing here.
