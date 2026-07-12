# Plan — batch Heme SH chatgpt_readable deck packages

Date: 2026-07-12  
Status: **Phase 1 done** (convert+upload). Tagging still pending except Aggressive B-Cell. Colab frames/MP4s in progress in parallel.

## Inventory (Phase 1 complete)

**21 unique packages** converted to `gs://pathology_hub/02_normalized/lectures/deck_packages/<slug>_v0_1/`.

| Package | Segs | Frames | Sidecar | Tagged+chunks | Notes |
|---------|------|--------|---------|---------------|-------|
| Aggressive_B_Cell | 877 | 66 | ✅ | ✅ ~49 chunks | Prefer original zip; `(7)` was mislabeled Reactive |
| AML | 443 | 65 | ✅ | ❌ | |
| BM_Failure_Syndromes | 476 | 22 | ✅ | ❌ | |
| BM_Intro | 700 | 47 | ✅ | ❌ | |
| BM_Systemic_Manifestations | 595 | 92 | ✅ | ❌ | |
| Histiocytic | 464 | 38 | ✅ | ❌ | |
| Hodgkin_NLP | 360 | 66 | ✅ | ❌ | |
| Hodgkin_Overview | 410 | 74 | ✅ | ❌ | |
| Hodgkin_T_NK_Cell_1 | 482 | 95 | ✅ | ❌ | |
| Hodgkin_T_NK_Cell_2 | 409 | 91 | ✅ | ❌ | |
| IA_LPD | 308 | 39 | ✅ | ❌ | |
| IHC_for_LPD | 434 | 80 | ✅ | ❌ | |
| MDS_MPN_1 | 703 | 56 | ✅ | ❌ | |
| MDS_MPN_2 | 817 | 46 | ✅ | ❌ | |
| MDS_MPN_3 | 917 | 67 | ✅ | ❌ | |
| PT_LPD | 446 | 27 | ✅ | ❌ | |
| Plasma_Cell | 447 | 34 | ✅ | ❌ | |
| Reactive_Lymphoid_Hyperplasia | 622 | 72 | ✅ | ❌ | |
| Small_B_Cell_1_of_2 | 939 | 113 | ✅ | ❌ | |
| Small_B_Cell_2_of_2 | 865 | 125 | ✅ | ❌ | |
| Spleen | 650 | 105 | ✅ | ❌ | |

All join basis: `canonical_name_pending_upload` until Colab finishes MP4s.  
`frames.jsonl` already points at `_asset_library/lectures/<stem>/<stem>_slide_NNNN.jpg`.

**Data-quality fix:** batch now prefers non-`(N)` zip names and skips zip-name vs `video_file` mismatches.
---

## Principles (unchanged)

1. Sidecar only under `02_normalized/lectures/deck_packages/<package_id>/` — do not overwrite legacy normalized lecture JSONL.
2. Canonical video URI: `gs://pathology-hub-0/source_videos/Heme_SH_<Topic>.mp4` with `canonical_name_pending_upload` until object exists.
3. **Never** vectorize `segments*.jsonl` — only `chunks_indexable.jsonl` after tagging.
4. Do not claim API / Videos strip until a rebuild + probe audit.

---

## Workstreams (parallel where possible)

```mermaid
flowchart LR
  subgraph A [Agent - GCS zips]
    Z[21 package zips] --> C[Convert to deck sidecar]
    C --> M[manifest + segments + frames.jsonl]
  end
  subgraph B [You - Colab]
    D[Drive packages] --> F[Upload slides to _asset_library]
    D --> V[Upload Heme_SH_*.mp4 to source_videos]
  end
  subgraph C2 [Agent - later]
    M --> T[Per-lecture entity tagging]
    T --> K[Consolidate chunks]
    K --> R[Lecture vector rebuild - gated]
  end
  F -.->|image_path already set| M
  V -.->|join_basis flips to filename_match| M
```

---

## Phase 1 — Convert all zips (agent, start now)

**Goal:** Every zip → untagged deck sidecar with honest video join + frame `image_path` pointers.

**How:**

```bash
python3 scripts/batch_process_chatgpt_readable_deck_packages_v0_1.py \
  --process --upload
```

(Aggressive B-Cell already done; re-convert only if we want asset-path fields refreshed on its `frames.jsonl`.)

**Outputs per package:**

- `manifest.json`, `segments.jsonl`, `frames.jsonl`, `audit.json`
- GCS: `gs://pathology_hub/02_normalized/lectures/deck_packages/<slug>_v0_1/`
- Batch audit under `06_audits/lectures/deck_packages/batch_*`

**Not in Phase 1:** tagging, consolidation, FAISS, API.

**Risk:** Zip layout drift (missing `lecture_index.json`). Mitigate with per-zip failure row in batch audit; continue others.

---

## Phase 2 — Frames + MP4s (you / Colab, parallel with Phase 1)

Run the ipynb:

1. `DRY_RUN = True` once → spot-check paths  
2. Upload slides → `_asset_library/lectures/Heme_SH_*/`  
3. Upload MP4s → `source_videos/Heme_SH_*.mp4`

**After MP4s land:** optional agent pass to flip `raw_source_join_basis` from `canonical_name_pending_upload` → `filename_match_source_videos` on manifests (small repair script).

---

## Phase 3 — Tagging (hard part — decide before bulk)

Aggressive B-Cell has a **lecture-specific** regex entity pack. The other 20 do **not**.

### Option A — Convert-only now; tag later (recommended first cut)

Ship Phase 1 for all 21. Tagging backlog as separate PRs / rule packs per lecture (or shared Heme ontology pack).

### Option B — Generic Heme tagger v0

Shared browse-index keywords (Hodgkin, MDS, AML, spleen compartments, small B entities, …) + same `do_not_index` intro/thanks gates + sticky context. Faster coverage, noisier tags. Still consolidate with same chunker.

### Option C — Hybrid

Phase 1 all → Option B pass for coarse tags → human/LLM review packs for high-value lectures (Small B, Hodgkin, MDS/MPN, Spleen).

**Recommendation:** **A then C** — don’t block the batch convert on perfect entity maps.

Consolidation (`chunks_indexable.jsonl`) runs **only after** a package has indexable tagged segments.

---

## Phase 4 — Lecture vector rebuild (gated, later)

Only when:

- Enough packages have `chunks_indexable.jsonl`
- Non-null `video_time_url` on chunks
- Prefer: matching MP4 objects exist (or accept pending-upload URLs)

Then: rebuild lecture index from deck sidecars → smoke API → Chat MVP Videos strip.

---

## Suggested execution order (when you say go)

| Step | Who | What |
|------|-----|------|
| 1 | Agent | Phase 1 batch convert + upload + audit for all 21 |
| 2 | You | Colab frames + MP4s (can overlap with 1) |
| 3 | Together | Pick tagging option A/B/C |
| 4 | Agent | Tag + consolidate for chosen set |
| 5 | Later | Vector rebuild (explicit gate) |

---

## Explicit non-goals for the first batch convert

- No FAISS / STRICT_CYTO rebuild  
- No Cloud Run redeploy  
- No claim Videos strip plays these lectures  
- No overwrite of `Other_Heme_*` legacy content/asset libraries (new canonical stems only)  
- No inventing entity tags for lectures without a rule pack (unless you choose Option B)

---

## Open choice for you

Reply with:

1. **Go Phase 1** (convert all zips now), and  
2. Tagging preference: **A** (later) / **B** (generic) / **C** (hybrid)

I’ll execute accordingly.
