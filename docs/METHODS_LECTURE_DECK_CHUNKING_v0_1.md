# Methods note — lecture deck chunking (v0.1)

**Status:** PoC method, not human-reviewed, not vectorized / not API-exposed.  
**Pilot package:** Heme SH Aggressive B-Cell (`chatgpt_readable` format).  
**Date locked:** 2026-07-12.

Use this note when drafting a methods paper. It describes what the pipeline *actually* does.

---

## 1. Input format (`chatgpt_readable_package`)

Each lecture arrives as a zip with:

| Artifact | Role |
|----------|------|
| `lecture_index.json` | Declared `video_file`, `duration_seconds`, change-detected `frames[]` |
| `transcript_segments.json` | Whisper-style `{id, start, end, text}` utterances |
| `frames/*.jpg` | Screenshot frames with `change_score` + `transcript_context` |
| `transcript.txt` / `lecture_review.html` | Human review only |

This is **not** the legacy `_content_library` slide JSON. Fine ASR timestamps are the reason this format is preferred for `video_time_url` joins.

**Video naming policy:** packages point at the **canonical** MP4 name declared in the zip (e.g. `Heme_SH_Aggressive_B_Cell.mp4`), written as:

`gs://pathology-hub-0/source_videos/<CanonicalName>.mp4`

with join basis `canonical_name_pending_upload` until the object exists. Do **not** rewrite packages to legacy `Other_*` filenames.

---

## 2. Pipeline stages (sidecar only)

```
zip → convert → tag (heuristic) → consolidate → audit JSON → GCS sidecar
```

Scripts:

1. `scripts/build_lecture_deck_package_from_chatgpt_readable_v0_1.py`
2. `scripts/tag_lecture_deck_package_heme_aggressive_b_v0_1.py` (entity map is lecture-specific)
3. `scripts/consolidate_lecture_deck_chunks_v0_1.py`
4. `scripts/batch_process_chatgpt_readable_deck_packages_v0_1.py` (inventory + convert batch)

Outputs live under:

`gs://pathology_hub/02_normalized/lectures/deck_packages/<package_id>/`

Audits under:

`gs://pathology_hub/06_audits/lectures/deck_packages/`

Original normalized lecture corpora are **not** overwritten.

---

## 3. What we do **not** index

| Artifact | Why |
|----------|-----|
| Raw `transcript_segments.json` / `segments.jsonl` | ASR crumbs (~5–15s); shreds retrieval |
| `segments_indexable.jsonl` | Intermediate tagged crumbs only |
| Intro / TOC / agenda / disclosures / thanks / closing multi-entity recap | Marked `indexable=false` / `do_not_index` |
| Untagged filler with no entity signal | Excluded from indexable set |

**Index grain (only):** `chunks_indexable.jsonl`

---

## 4. Tagging (heuristic v0.1 — not discourse parsing)

Per utterance:

1. Light ASR normalization (lecture-specific mangling fixes).
2. Regex entity rules → candidate `primary_tag` (browse-index path).
3. Sticky context: if no hit, keep previous entity while still in teaching flow.
4. Specificity priority when multiple entities fire (e.g. double-hit / 11q before DLBCL NOS).
5. Hard `do_not_index` gates for opening agenda window, thanks/disclosures, closing recap.

Honest label for papers: **keyword + sticky-context heuristic tagging**, not LLM topic segmentation and not human gold labels.

---

## 5. Consolidation algorithm (the “genius” bit — state it honestly)

Goal: turn ~10³ ASR utterances into ~10¹–10² teachable retrieval units.

### 5.1 Island smoothing

Short tag runs (few utterances / short duration) that flicker between neighbors are **repainted** to the surrounding tag when neighbors agree (or to previous/next otherwise). This reduces keyword-noise shredding before merge.

### 5.2 Same-tag merge with caps

Walk indexable utterances in time order. Flush buffer when any of:

- `primary_tag` changes
- inter-utterance gap > `gap_flush_sec` (default 25s)
- trial duration > `max_duration_sec` (default 150s)
- trial character count > `max_chars` (default 2800)

Absorb undersized leftovers into the previous same-tag chunk when possible.

### 5.3 Second-pass tiny-chunk absorption

Ultra-short islands after a tag flip can fold into the previous chunk (within duration/char slack) so retrieval units stay contiguous.

### Defaults that produced the pilot

| Param | Default | Pilot effect |
|-------|---------|--------------|
| `max_duration_sec` | 150 | ~2 min median chunks |
| `max_chars` | 2800 | ~1.6k char mean |
| `min_chars` | 200 | drop/absorb crumbs |
| `gap_flush_sec` | 25 | respect pauses |

**Pilot counts (Aggressive B-Cell):** 877 ASR utterances → ~784 tagged crumbs → **~45 indexable chunks**.

### What this is **not**

- Not semantic topic segmentation
- Not embedding-based boundary detection
- Not using frame `change_score` as a chunk boundary (frames are retained as visual sidecars only)
- Not discourse / rhetorical structure parsing

### Future methods upgrades (explicit backlog)

1. Frame `change_score` / slide-change boundaries as soft flush cues  
2. Embedding similarity drop as boundary signal  
3. LLM or human review of chunk boundaries + tags  
4. Per-lecture entity rule packs (batch beyond the pilot map)

---

## 6. Asset / picture upload (operator TODO)

Deck zips already contain `frames/*.jpg`. Promoting those (and any associated slide pics) into durable GCS asset prefixes — e.g. `_asset_library` or `02_normalized/lectures/deck_packages/<id>/frames/` — is an **operator / Colab upload job**, not part of the convert→tag→consolidate sidecar path.

Sidecar `frames.jsonl` already records timestamps + `video_time_url` pointers so frame bytes can be attached later without re-chunking.

---

## 7. Claims gate (do not overclaim)

Do **not** claim a lecture is indexed, vectorized, tagged for production, or API-exposed unless an audit / manifest / health check proves it.

Until a lecture vector rebuild consumes `chunks_indexable.jsonl` with non-null `video_time_url`, Chat MVP Videos strip behavior for these packages remains unproven.
