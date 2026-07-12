# Plan — rebuild lecture vector index from deck packages

Date: 2026-07-12  
Status: **GCS promoted — awaiting Cloud Run cold start / new revision**

## Goal
Load gated `chunks_indexable.jsonl` from all deck packages into the searchable lecture FAISS used by `POST /evidence/search` (`lectures` + `videos`).

## Done
- Script: `scripts/build_lecture_vector_from_deck_packages_v0_1.py`
- Indexed **712** chunks from **113** packages (all with `video_time_url`)
- Versioned: `gs://pathology_hub/03_indexes/lectures/vector_deck_packages_v0_1/`
- Live STRICT_CYTO_v9 paths **overwritten** after backup
- Audit: `gs://pathology_hub/06_audits/lectures/vector_deck_packages_v0_1/20260712T144802Z/audit.json`
- Local smoke: T/NK AITL query returns playable `#t=` URLs

## Blocked here
Cloud agent SA lacks `run.services.get/update`. Live `/health` still shows old **42069** until pods re-download.

## Operator: force Cloud Run refresh
```bash
gcloud run services update pathology-hub-v04 \
  --project=pathology-annotation-project \
  --region=us-central1 \
  --update-env-vars=LECTURE_MANIFEST_REFRESH_TS=$(date -u +%Y%m%dT%H%M%SZ)
```
(Or deploy a new revision / scale to zero then back.)

## Verify after refresh
1. `/health` → `lecture_vector_records` ≈ **712**, schema `deck_packages_v0_1`
2. `POST /evidence/search` with `sources:["videos"]`, query e.g. `angioimmunoblastic` → non-null `video_time_url`
3. Chat MVP Videos strip playable links

## Policy notes
- Deck-only replace (legacy broken 42k not merged)
- Backup under `03_indexes/lectures/vector_STRICT_CYTO_v9_backup_before_deck_v0_1_*`
- Index grain remains gated `chunks_indexable.jsonl` only
