# Colab: Heme SH lecture frames → pathology-hub-0 slide images

**Upload this notebook to Colab:**

`notebooks/Heme_SH_Lecture_Frame_Upload_to_Asset_Library_v0_1.ipynb`

(File → Upload notebook in Colab, or open from Drive after copying the `.ipynb` there.)

---

**Drive source:** `3-Resources/Heme/Heme_SH_Lectures`  
**GCS dest (legacy-consistent):**

`gs://pathology-hub-0/_asset_library/lectures/<CanonicalStem>/<CanonicalStem>_slide_NNNN.jpg`

Example:

`gs://pathology-hub-0/_asset_library/lectures/Heme_SH_Aggressive_B_Cell/Heme_SH_Aggressive_B_Cell_slide_0000.jpg`

Same layout as existing lectures (`BST_Lecture_1_Grossing/BST_Lecture_1_Grossing_slide_0000.jpg`).  
Use **canonical** `Heme_SH_*` stems — not legacy `Other_Heme_*`.

**Also optional:** upload canonical MP4s to

`gs://pathology-hub-0/source_videos/<CanonicalName>.mp4`

Deck sidecar `frames.jsonl` rows point at these `_asset_library` paths via `image_path` / `asset_gcs_uri`.

---

## Notebook cells (summary)

1. Auth + Drive mount + GCS client
2. Discover `lecture_index.json` + `frames/` under Drive
3. Upload slides to `_asset_library/lectures/` (`DRY_RUN = True` first)
4. Optional canonical MP4 upload
5. Write audit JSON to `gs://pathology_hub/06_audits/lectures/deck_packages/`

---

## Mapping cheat sheet

| Drive | GCS (legacy-consistent) |
|-------|-------------------------|
| `.../frames/frame_0003_00-00-38.jpg` | `gs://pathology-hub-0/_asset_library/lectures/Heme_SH_Spleen/Heme_SH_Spleen_slide_0003.jpg` |
| `Heme_SH_*.mp4` | `gs://pathology-hub-0/source_videos/Heme_SH_*.mp4` |
| deck sidecar `frames.jsonl` | `image_path` = `<stem>/<stem>_slide_NNNN.jpg` |

If a lecture only has an MP4 and no `chatgpt_readable_package/frames`, run extraction first (your Aggressive B-Cell Colab pattern).
