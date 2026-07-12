# YT Skin remaster vs YT Derm

Date: 2026-07-12

## What we remastered: **YT_Skin** (not YT_Derm)

No original YouTube links needed. Playback stays **GCS MP4 `#t=`** from existing
`gs://pathology-hub-0/source_videos/YT_Skin_*.mp4` + content_library transcripts.

| Metric | Value |
|--------|------:|
| Packages converted | **21/21** |
| Segments | 2576 |
| Gated `Skin::*` chunks | **179** |
| Audit | `gs://pathology_hub/06_audits/lectures/deck_packages/yt_skin_remaster_20260712T172152Z/audit.json` |

Leaf embeddings: `outputs/skin_browse_leaf_embeddings_v0_1/` (1057 `Skin::*` leaves).

## YT_Derm (not in this remaster)

- Mostly `*_MASTER.json` / `*_RAW.json` only (different schema: `timestamp_start` / `slide_title`)
- **0** top-level converter-compatible content JSON stems
- Only 2 MP4s (`YT_Derm_Adnexal_Skupsk*`) and those lack matching content
- Would need a RAW→deck adapter and/or Colab YouTube re-ingest + original links

## Derm_Lecture / Other_Skin

Still skipped unless you ask — separate from YT_Skin.

## Next for live API

After vector promote: Cloud Shell env bump (force-redownload is already in prod image):

```bash
gcloud run services update pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --update-env-vars=LECTURE_MANIFEST_REFRESH_TS=$(date -u +%Y%m%dT%H%M%SZ)
```

Expect `/health` lecture `record_count` ≈ previous + 179 (plus any Gardner chunks if gated first).
