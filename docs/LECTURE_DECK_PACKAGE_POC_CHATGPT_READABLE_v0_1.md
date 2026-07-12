# Lecture deck package PoC — ChatGPT-readable → Hub sidecar

Date: 2026-07-11  
Pilot: **Heme SH Aggressive B-Cell** (Sohani / Society for Hematopathology curriculum)

## What we received

`gs://pathology_hub/Heme_SH_Aggressive_B_Cell_chatgpt_readable_package.zip`

Layout (different from `_content_library` slide JSON):

| File | Role |
|------|------|
| `READ_ME_FIRST.txt` | Points at video name + transcript/index |
| `lecture_index.json` | `video_file`, `duration_seconds`, `frames[]` |
| `transcript_segments.json` | Whisper-style `{id,start,end,text}` |
| `transcript.txt` | Human-readable timed transcript |
| `frames/*.jpg` | Change-detected screenshots + `transcript_context` |
| `lecture_review.html` | Browseable frame+text review |

**Counts:** 877 timed segments, 66 frames, ~101 minutes (`duration_seconds` ≈ 6103).

## How it differs from existing GCS lecture assets

Same lecture already exists as:

- MP4: `gs://pathology-hub-0/source_videos/Other_Heme_Lecture_aggressive b cell lymphomas.mp4`
- Content JSON: `_content_library/lectures/Other_Heme_Lecture_aggressive b cell lymphomas/` (74 slide-aligned rows)
- Slides: `_asset_library/lectures/Other_Heme_Lecture_aggressive b cell lymphomas/` (~74 JPGs)

| | ChatGPT-readable package | Legacy content library |
|--|--------------------------|------------------------|
| Segment grain | ~877 fine transcript chunks | ~74 slide-tied rows |
| Timestamps | Real `start`/`end` seconds | Present but coarser |
| Visuals | Change-score frames | Slide exports |
| Titles | N/A on segments | Often noisy (e.g. desktop wallpaper titles) |
| Ready for `video_time_url` | Yes (after MP4 join) | Join often missing in live vector index |

PoC join used **filename match** to the existing `source_videos` MP4 → `raw_source_join_basis: filename_match_source_videos`.

## What we produced (sidecar only)

Converter: `scripts/build_lecture_deck_package_from_chatgpt_readable_v0_1.py`

Local:

- `outputs/lecture_deck_packages_v0_1/heme_sh_aggressive_b_cell_v0_1/`

GCS:

- `gs://pathology_hub/02_normalized/lectures/deck_packages/heme_sh_aggressive_b_cell_v0_1/{manifest,segments,frames,audit}.json(l)`
- `gs://pathology_hub/06_audits/lectures/deck_packages/poc_20260711/heme_sh_aggressive_b_cell_audit.json`

Every segment/frame row has non-null `video_url` + `video_time_url` in this sidecar.

## Tagging (heuristic v0_1)

Script: `scripts/tag_lecture_deck_package_heme_aggressive_b_v0_1.py`  
Consolidate: `scripts/consolidate_lecture_deck_chunks_v0_1.py`

| Policy | Behavior |
|--------|----------|
| ASR crumbs | Kept in `segments*.jsonl` for audit only — **do not vectorize** |
| Index grain | `chunks_indexable.jsonl` only (~2 min merges, tag-smoothed) |
| Do not index | Intro, TOC/agenda, thanks, closing recap, filler |
| Video URI | Canonical `Heme_SH_Aggressive_B_Cell.mp4` (`canonical_name_pending_upload`) |

**PoC counts:** 877 ASR utterances → ~784 tagged crumbs → **~45 indexable chunks**.

Not human-reviewed. Not vectorized / not API-exposed.

## Explicitly NOT done

- No FAISS / STRICT_CYTO docstore rebuild
- No Cloud Run redeploy
- No claim that Chat MVP Videos strip will play this lecture yet
- `primary_tag` left `null` / `tag_status: untagged_poc` (tagging = next step)

## Methods paper lock

See `docs/METHODS_LECTURE_DECK_CHUNKING_v0_1.md` for the honest chunking/tagging description (island smoothing + same-tag time/size caps; **not** semantic segmentation).

## Batch inventory (2026-07-12)

Script: `scripts/batch_process_chatgpt_readable_deck_packages_v0_1.py`

At audit time, `gs://pathology_hub/` root still showed **only** the Aggressive B-Cell zip. Same principle when more `*_chatgpt_readable_package.zip` land:

- Canonical MP4 name from package → `gs://pathology-hub-0/source_videos/<Canonical>.mp4`
- Join basis `canonical_name_pending_upload` until the object exists
- Do not rewrite to legacy `Other_*` names

## Associated pics / frames

**Operator Colab TODO** — see `docs/COLAB_TODO_LECTURE_DECK_FRAME_UPLOAD.md`.  
Upload to legacy-consistent slide path on pathology-hub-0:

`gs://pathology-hub-0/_asset_library/lectures/<CanonicalStem>/<CanonicalStem>_slide_NNNN.jpg`

Sidecar `frames.jsonl` records `image_path` / `asset_gcs_uri` pointing there; bytes can follow via Colab.

## Next steps

1. Drop additional `*_chatgpt_readable_package.zip` at bucket root (or re-run batch after upload finishes).
2. Per-lecture entity rule packs beyond Aggressive B-Cell.
3. Rebuild lecture vector index **from** `chunks_indexable.jsonl` (gate: non-null `video_time_url`).
4. API smoke → Chat MVP Videos strip.
